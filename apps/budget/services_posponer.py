"""Mover al mes siguiente un gasto que no estaba planificado.

Solo eso. Lo planificado —los ingresos y los gastos del plan— se corrige en
Plan the month, que edita el mes entero; moverlo desde aqui seria una segunda
forma de hacer lo mismo, y las dos podrian discrepar.

Vive aparte de `services.py` por la misma razon que las metas: aquel ya mezcla
el ciclo del mes, la cascada y la mesada, y esto cabe en una funcion que se
prueba sola.

El mes siguiente se materializa si el hogar no habia llegado a el, con
`abrir_para_planificar`: desde ese momento es independiente del setup, igual
que cuando se planifica a mano (§2.3).
"""

from datetime import date

from django.db import transaction
from django.utils import formats

from . import services
from .models import MesCerrado


class NoEsUnGastoSuelto(ValueError):
    """Se quiso mover algo que estaba planificado, o una partida compartida."""


class SinMesSiguiente(ValueError):
    """El hogar no puede escribir, y por tanto no se le crea el mes siguiente."""


def _mes_siguiente_de(mes):
    """La fila del mes que viene, materializada."""
    anio, numero = services.mes_siguiente(mes.year, mes.month)
    siguiente = services.abrir_para_planificar(mes.household, anio, numero)
    if siguiente is None:
        raise SinMesSiguiente(f"No se puede abrir {anio}-{numero:02d} para {mes.household}.")
    return siguiente


def nombre_de_mes(mes):
    """"October", en el idioma de la peticion: para el aviso."""
    return formats.date_format(date(mes.year, mes.month, 1), "F")


@transaction.atomic
def posponer_registro(tx):
    """Imputa al mes siguiente un gasto que no estaba planificado.

    La fecha se conserva: ese dia salio el dinero, aunque cuente para el mes
    que viene. Su partida puntual se muda con el, como ya hace al corregirlo o
    quitarlo. Cualquier otra cosa —un pago contra el plan, un ingreso, una
    partida con mas de un pago— se rechaza: ver `Transaction.se_puede_posponer`.

    Las dos guardas van ANTES de tocar el mes siguiente: materializarlo ya es
    una escritura, y ni un mes cerrado ni un registro que no se mueve deben
    provocar ninguna.
    """
    mes = tx.budget_month
    if mes.esta_cerrado:
        raise MesCerrado(f"El mes {mes} está cerrado y no admite escrituras.")
    if not tx.se_puede_posponer:
        raise NoEsUnGastoSuelto(f"El registro {tx} no es un gasto sin planificar.")
    siguiente = _mes_siguiente_de(mes)
    puntual = tx.partida_propia
    puntual.budget_month = siguiente
    puntual.save(update_fields=["budget_month"])
    tx.budget_month = siguiente
    tx.save(update_fields=["budget_month"])
    return tx

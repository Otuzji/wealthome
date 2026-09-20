"""Las metas de ahorro: aportar, y el estado que se deriva de lo aportado.

Vive aparte de `services.py` porque aquel ya mezcla el mes, la cascada y la
mesada; lo de metas cabe en una pantalla y se prueba solo.

`reached` lo pone la aplicacion al cubrir el objetivo; `abandoned` solo el
usuario. Una abandonada no se mueve sola aunque le siga cayendo cascada: la
regla de reparto es del usuario, y quitarla es cosa suya.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from . import services
from .models import (
    CASCADE, MANUAL, TRANSFER_IN, TRANSFER_OUT, WITHDRAWAL, AllocationRule, Goal,
    GoalContribution,
)


class SaldoInsuficiente(ValueError):
    """Se quiso sacar mas de lo que hay (o nada)."""


class SaldoPendiente(ValueError):
    """Se quiso quitar una meta que todavia tiene dinero."""

# Las transiciones que pide el usuario. active -> reached y reached -> active
# no estan: las decide recalcular_estado a partir de lo aportado.
TRANSICIONES_A_MANO = {
    (Goal.ACTIVE, Goal.ABANDONED),
    (Goal.ABANDONED, Goal.ACTIVE),
}


def _movimiento(hogar, meta, amount, date, member, origen, note="", counterpart=None):
    """Una fila de movimiento. El mes se resuelve por la fecha y NO se crea:
    un movimiento fechado en un mes que el hogar no vivio queda sin mes (y por
    tanto no puede chocar con un cierre). `MesCerrado` sube tal cual."""
    fila = GoalContribution(
        household=hogar, goal=meta, amount=amount, date=date, member=member,
        origen=origen, note=note, counterpart=counterpart,
        budget_month=services.mes_de_fecha(hogar, date),
    )
    fila.full_clean()
    fila.save()
    return fila


def _exigir_saldo(meta, amount):
    if amount is None or amount <= 0:
        raise SaldoInsuficiente("Hay que sacar mas de cero.")
    if amount > meta.acumulado():
        raise SaldoInsuficiente(f"La meta {meta} no tiene {amount}.")


@transaction.atomic
def aportar(hogar, meta, amount, date, member, origen=MANUAL, note=""):
    """Un aporte con fecha: a mano (dinero de fuera del presupuesto) o de la
    cascada. Si cubre el objetivo, la meta pasa a alcanzada."""
    aporte = _movimiento(hogar, meta, amount, date, member, origen, note)
    recalcular_estado(meta)
    return aporte


@transaction.atomic
def retirar(hogar, meta, amount, date, member, note=""):
    """Sacar dinero de una meta: "ya lo use". Sale de la app, no vuelve al
    mes. Una meta alcanzada sigue alcanzada aunque se vacie: se cumplio."""
    _exigir_saldo(meta, amount)
    return _movimiento(hogar, meta, -amount, date, member, WITHDRAWAL, note)


@transaction.atomic
def transferir(hogar, origen, destino, amount, date, member, note=""):
    """Mover saldo de una meta a otra activa. Dos filas enlazadas por
    `counterpart`: borrar una borra la otra y las dos metas siguen cuadrando.
    Devuelve (salida, entrada)."""
    if origen.pk == destino.pk:
        raise ValueError("Una meta no se transfiere a si misma.")
    if destino.status != Goal.ACTIVE:
        raise ValueError(f"La meta {destino} no esta activa.")
    _exigir_saldo(origen, amount)
    salida = _movimiento(hogar, origen, -amount, date, member, TRANSFER_OUT, note)
    entrada = _movimiento(hogar, destino, amount, date, member, TRANSFER_IN, note,
                          counterpart=salida)
    salida.counterpart = entrada
    salida.save(update_fields=["counterpart"])
    recalcular_estado(origen, bajar=False)
    recalcular_estado(destino)
    return salida, entrada


def quitar(meta):
    """Borrar una meta, o archivarla si un cierre la referencia. Solo con el
    saldo en cero: con dinero dentro, primero se retira o se transfiere.
    Devuelve "deleted" o "archived"."""
    if meta.acumulado() != 0:
        raise SaldoPendiente(f"La meta {meta} todavia tiene saldo.")
    if meta.contributions.filter(origen=CASCADE).exists():
        # AllocationRule.target_goal es CASCADE y MonthlyAllocation.rule es
        # RESTRICT: el mes cerrado conto con ese reparto. Se guarda fuera de
        # Goals y sigue contando en Balance.
        meta.status = Goal.ARCHIVED
        meta.save(update_fields=["status"])
        return "archived"
    meta.delete()
    return "deleted"


def recalcular_estado(meta, acumulado=None, bajar=True):
    """Solo active <-> reached. Devuelve si cambio.

    `acumulado` se puede pasar ya sumado: quien pinta la lista lo tiene.
    Con `bajar=False` una alcanzada no vuelve a activa: es lo que pasa al
    sacar dinero de ella, que se cumplio y ya se uso.
    """
    if meta.status in (Goal.ABANDONED, Goal.ARCHIVED):
        return False
    if acumulado is None:
        acumulado = meta.acumulado()
    nuevo = Goal.REACHED if meta.alcanzada(acumulado) else Goal.ACTIVE
    if nuevo == meta.status:
        return False
    if nuevo == Goal.ACTIVE and not bajar:
        return False
    meta.status = nuevo
    meta.save(update_fields=["status"])
    return True


def cambiar_estado(meta, nuevo):
    """Abandonar o reactivar. Reactivar recalcula: si mientras estaba
    abandonada la cascada la cubrio, vuelve como alcanzada, no como activa."""
    if (meta.status, nuevo) not in TRANSICIONES_A_MANO:
        raise ValueError(f"No se pasa de {meta.status!r} a {nuevo!r}.")
    meta.status = nuevo
    meta.save(update_fields=["status"])
    if nuevo == Goal.ACTIVE:
        recalcular_estado(meta)


def resumen(hogar, metas, hoy=None):
    """Lo que la pantalla necesita de cada meta, en una pasada.

    `metas` viene con `contributions` prefetched (con `member__user` y
    `budget_month`): todo lo de aportes se suma en Python. Solo van a la base
    las reglas de reparto (una consulta) y el mes de hoy (otra), y ninguna
    crece con el numero de metas.
    """
    hoy = hoy or timezone.localdate()
    mes_de_hoy = services.mes_de_fecha(hogar, hoy)
    con_regla = set(
        AllocationRule.objects.for_household(hogar)
        .filter(is_active=True, target_goal__isnull=False)
        .values_list("target_goal_id", flat=True)
    )
    filas = []
    for meta in metas:
        aportes = list(meta.contributions.all())
        acumulado = sum((a.amount for a in aportes), Decimal("0.00"))
        aporte, fecha = meta.derivar(desde=hoy, acumulado=acumulado)
        # Dos numeros y no uno: el porcentaje real es un dato ("119%" no es
        # un error), pero la barra se acota a 100 o se sale de su caja.
        bruto = int(acumulado / meta.target_amount * 100) if meta.target_amount else 0
        filas.append({
            "meta": meta,
            "acumulado": acumulado,
            "aporte": aporte,
            "fecha": fecha,
            "meses_restantes": _meses_entre(hoy, fecha),
            "este_mes": sum(
                (a.amount for a in aportes
                 if mes_de_hoy is not None and a.budget_month_id == mes_de_hoy.pk),
                Decimal("0.00"),
            ),
            "porcentaje": bruto,
            "porcentaje_barra": min(100, bruto),
            "tiene_regla": meta.pk in con_regla,
            "alcanzada_el": (_fecha_en_que_se_cubrio(meta, aportes)
                             if meta.status == Goal.REACHED else None),
            "aportes": [(a, _editable(a)) for a in aportes],
            "se_puede_borrar": not any(a.origen == "cascade" for a in aportes),
        })
    return filas


def _editable(aporte):
    """Un aporte manual de un mes que no esta cerrado. El de cascada es del
    cierre, y el de un mes cerrado ya conto en su balance."""
    if aporte.origen != "manual":
        return False
    return aporte.budget_month_id is None or not aporte.budget_month.esta_cerrado


def _fecha_en_que_se_cubrio(meta, aportes):
    """Los aportes vienen del mas reciente al mas viejo (Meta.ordering); se
    recorren al reves acumulando hasta el que la cubrio."""
    total = Decimal("0.00")
    for aporte in reversed(aportes):
        total += aporte.amount
        if meta.alcanzada(total):
            return aporte.date
    return None


def _meses_entre(desde, hasta):
    return max(0, (hasta.year - desde.year) * 12 + hasta.month - desde.month)

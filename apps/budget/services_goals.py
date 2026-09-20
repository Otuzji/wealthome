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
from .scopes import acotar_por_dueno


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
        saldo = sum((a.amount for a in aportes), Decimal("0.00"))
        aporte, fecha = meta.derivar(desde=hoy, acumulado=saldo)
        if meta.target_amount:
            # Dos numeros y no uno: el porcentaje real es un dato ("119%" no
            # es un error), pero la barra se acota a 100 o se sale de su caja.
            bruto = int(saldo / meta.target_amount * 100)
            porcentaje, barra = bruto, max(0, min(100, bruto))
        else:
            porcentaje = barra = None
        filas.append({
            "meta": meta,
            "acumulado": saldo,
            "saldo": saldo,
            "es_fondo": meta.es_fondo,
            "aporte": aporte,
            "fecha": fecha,
            "meses_restantes": _meses_entre(hoy, fecha) if fecha else None,
            # Lo que ENTRO este mes: lo que se saco no descuenta del esfuerzo.
            "este_mes": sum(
                (a.amount for a in aportes
                 if a.amount > 0 and mes_de_hoy is not None
                 and a.budget_month_id == mes_de_hoy.pk),
                Decimal("0.00"),
            ),
            "porcentaje": porcentaje,
            "porcentaje_barra": barra,
            "tiene_regla": meta.pk in con_regla,
            "tiene_cascada": any(a.origen == CASCADE for a in aportes),
            "alcanzada_el": (_fecha_en_que_se_cubrio(meta, aportes)
                             if meta.status == Goal.REACHED else None),
            "aportes": [(a, _editable(a), _borrable(a)) for a in aportes],
            "puede_sacar": saldo > 0,
            "puede_quitar": saldo == 0,
        })
    return filas


def _mes_abierto(aporte):
    return aporte.budget_month_id is None or not aporte.budget_month.esta_cerrado


def _editable(aporte):
    """Solo un aporte manual de un mes que no esta cerrado se corrige. Un
    retiro o una transferencia se quitan y se rehacen; el de cascada es del
    cierre, y el de un mes cerrado ya conto en su balance."""
    return aporte.origen == MANUAL and _mes_abierto(aporte)


def _borrable(aporte):
    return aporte.origen != CASCADE and _mes_abierto(aporte)


def resumen_ahorro(hogar, ambito, membresia):
    """El ahorro del hogar (o el personal de quien mira) para Balance: por
    mes, lo que entro de la cascada, lo que entro a mano y lo que salio; el
    saldo acumulado; y el saldo de cada meta, archivadas incluidas. Las
    transferencias se anulan entre si y no se listan por mes.

    Se agrupa por el ano-mes de la FECHA del movimiento y no por
    `budget_month`: un aporte fechado en un mes que el hogar no vivio no tiene
    fila de mes y aun asi es ahorro.
    """
    metas = list(acotar_por_dueno(Goal.objects.for_household(hogar), ambito, membresia))
    movimientos = (
        GoalContribution.objects.for_household(hogar)
        .filter(goal__in=metas).order_by("date", "pk")
    )
    por_mes = {}
    saldo_por_meta = {m.pk: Decimal("0.00") for m in metas}
    for mov in movimientos:
        saldo_por_meta[mov.goal_id] += mov.amount
        if mov.origen in (TRANSFER_IN, TRANSFER_OUT):
            continue
        fila = por_mes.setdefault((mov.date.year, mov.date.month), {
            "anio": mov.date.year, "mes": mov.date.month,
            "cascada": Decimal("0.00"), "a_mano": Decimal("0.00"),
            "retiros": Decimal("0.00"),
        })
        if mov.origen == CASCADE:
            fila["cascada"] += mov.amount
        elif mov.origen == MANUAL:
            fila["a_mano"] += mov.amount
        else:
            fila["retiros"] += mov.amount
    saldo = Decimal("0.00")
    filas = []
    for clave in sorted(por_mes):
        fila = por_mes[clave]
        fila["neto"] = fila["cascada"] + fila["a_mano"] + fila["retiros"]
        saldo += fila["neto"]
        fila["saldo"] = saldo
        filas.append(fila)
    filas.reverse()
    return {
        "filas": filas,
        "saldo_total": saldo,
        "por_meta": [{"meta": m, "saldo": saldo_por_meta[m.pk]} for m in metas],
    }


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

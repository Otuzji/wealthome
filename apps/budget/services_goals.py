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
from .models import AllocationRule, Goal, GoalContribution

# Las transiciones que pide el usuario. active -> reached y reached -> active
# no estan: las decide recalcular_estado a partir de lo aportado.
TRANSICIONES_A_MANO = {
    (Goal.ACTIVE, Goal.ABANDONED),
    (Goal.ABANDONED, Goal.ACTIVE),
}


@transaction.atomic
def aportar(hogar, meta, amount, date, member, origen="manual"):
    """Un aporte con fecha. El mes se resuelve por la fecha y NO se crea: un
    aporte fechado en un mes que el hogar no vivio queda sin mes (y por tanto
    no puede chocar con un cierre). `MesCerrado` sube tal cual."""
    aporte = GoalContribution(
        household=hogar, goal=meta, amount=amount, date=date, member=member,
        origen=origen, budget_month=services.mes_de_fecha(hogar, date),
    )
    aporte.full_clean()
    aporte.save()
    recalcular_estado(meta)
    return aporte


def recalcular_estado(meta, acumulado=None):
    """Solo active <-> reached. Devuelve si cambio.

    `acumulado` se puede pasar ya sumado: quien pinta la lista lo tiene.
    """
    if meta.status == Goal.ABANDONED:
        return False
    if acumulado is None:
        acumulado = meta.acumulado()
    nuevo = Goal.REACHED if meta.alcanzada(acumulado) else Goal.ACTIVE
    if nuevo == meta.status:
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

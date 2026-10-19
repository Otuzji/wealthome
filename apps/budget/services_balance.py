"""El balance del hogar: activos, pasivos y patrimonio neto.

Casi todo se teclea a mano (`BalanceItem`). Dos filas NO: el ahorro, que es
el saldo de las metas, y el efectivo, que es lo que el mes abierto lleva de
verdad —lo que entro menos lo que salio, la cifra de Cash Float—. Ambas se
calculan al mirar y se muestran junto a lo tecleado, en "Cash and
equivalents", marcadas como automaticas.
"""

from decimal import Decimal

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

from apps.budget.engine.money import centavos

from . import services_goals
from .models import AllowanceLedger, BalanceItem, BudgetMonth, Transaction
from .models.balance import ASSET, GRUPOS, LIABILITY, LIQUID
from .models.catalog import EXPENSE, HOUSEHOLD, INCOME
from .scopes import HOGAR, PERSONAL

CERO = Decimal("0.00")


def _mes_abierto(hogar):
    return (
        BudgetMonth.objects.for_household(hogar)
        .filter(status=BudgetMonth.OPEN).order_by("-year", "-month").first()
    )


def efectivo_del_mes_abierto(hogar):
    """Lo que el mes abierto lleva en mano: ingresos reales menos gastos
    reales del HOGAR, como la tarjeta Cash Float. Lo personal sale de la
    mesada, no de aqui. Sin mes abierto, cero."""
    mes = _mes_abierto(hogar)
    if mes is None:
        return CERO
    por_tipo = dict(
        Transaction.objects.for_household(hogar).filter(budget_month=mes, scope=HOUSEHOLD)
        .values_list("category__kind").annotate(total=Sum("amount"))
    )
    return centavos((por_tipo.get(INCOME) or CERO) - (por_tipo.get(EXPENSE) or CERO))


def efectivo_personal(hogar, membresia):
    """Lo que le queda de mesada al miembro en el mes abierto: lo recibido
    (arrastre, asignado y ajuste) menos lo gastado en lo personal hasta hoy.
    Se lee el libro sin crearlo: mirar el balance no escribe nada."""
    from . import services

    mes = _mes_abierto(hogar)
    if mes is None:
        return CERO
    libro = AllowanceLedger.objects.for_household(hogar).filter(
        member=membresia, budget_month=mes
    ).first()
    recibido = (libro.carried_in + libro.granted + libro.adjustment) if libro else CERO
    return centavos(recibido - services.gasto_personal_del_mes(membresia, mes))


def filas_personales(hogar, membresia):
    """Balance en Personal: solo lo del miembro. Las partidas tecleadas (casa,
    coche, prestamos) son del hogar y no tienen dueno: alli se quedan."""
    ahorro = services_goals.resumen_ahorro(hogar, PERSONAL, membresia)["saldo_total"]
    return [
        {"nombre": _("Savings"), "importe": ahorro, "automatico": True,
         "nota": _("The balance of your personal goals.")},
        {"nombre": _("Cash"), "importe": efectivo_personal(hogar, membresia), "automatico": True,
         "nota": _("What is left of your allowance this month.")},
    ]


def filas_automaticas(hogar, membresia):
    """Las dos lineas que la aplicacion ya sabe. Sin `pk`: no son filas de
    la tabla y no se editan."""
    ahorro = services_goals.resumen_ahorro(hogar, HOGAR, membresia)["saldo_total"]
    return [
        {"nombre": _("Savings"), "importe": ahorro, "automatico": True,
         "nota": _("The balance of your goals.")},
        {"nombre": _("Cash"), "importe": efectivo_del_mes_abierto(hogar), "automatico": True,
         "nota": _("What this month has in hand.")},
    ]


def patrimonio(hogar, membresia, ambito=HOGAR):
    """Los grupos con sus lineas y su total, y las tres cifras de cabecera.

    En Personal, un solo grupo (efectivo) con las filas del miembro."""
    if ambito == PERSONAL:
        filas = filas_personales(hogar, membresia)
        total = centavos(sum((f["importe"] for f in filas), CERO))
        etiqueta = next(e for clave, _t, e in GRUPOS if clave == LIQUID)
        grupo = {"clave": LIQUID, "tipo": ASSET, "etiqueta": etiqueta,
                 "filas": filas, "total": total}
        return {"grupos": [grupo], "activos": [grupo], "pasivos": [],
                "total_activos": total, "total_pasivos": CERO, "neto": total}
    items = list(BalanceItem.objects.for_household(hogar))
    grupos = []
    activos = pasivos = CERO
    for clave, tipo, etiqueta in GRUPOS:
        filas = [
            {"item": i, "nombre": i.name, "importe": i.amount, "nota": i.note,
             "automatico": False}
            for i in items if i.group == clave
        ]
        if clave == LIQUID:
            filas = filas_automaticas(hogar, membresia) + filas
        total = centavos(sum((f["importe"] for f in filas), CERO))
        if tipo == ASSET:
            activos += total
        else:
            pasivos += total
        grupos.append({"clave": clave, "tipo": tipo, "etiqueta": etiqueta,
                       "filas": filas, "total": total})
    return {
        "grupos": grupos,
        "activos": [g for g in grupos if g["tipo"] == ASSET],
        "pasivos": [g for g in grupos if g["tipo"] == LIABILITY],
        "total_activos": centavos(activos),
        "total_pasivos": centavos(pasivos),
        "neto": centavos(activos - pasivos),
    }

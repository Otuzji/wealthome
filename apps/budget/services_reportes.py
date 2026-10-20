"""Reportes: los registros de un periodo, filtrados, con sus totales y desgloses.

Es la consulta "¿cuanto gastamos en Walmart este ano?" que el §12 del diseno de
la Fase 1 dejaba para la Fase 2, y que el esquema ya permitia: categoria,
comercio, miembro, fecha y ambito estan en cada registro desde el Plan 2.

Lo personal de otro miembro no entra nunca, filtre quien filtre: el punto de
partida es `visibles`, la misma regla que abrir un registro por su pk.
"""

from collections import defaultdict
from decimal import Decimal

from apps.budget.engine.money import centavos

from .models import Transaction
from .models.catalog import EXPENSE, INCOME
from .scopes import HOGAR, PERSONAL, visibles

CERO = Decimal("0.00")

# El ambito del reporte. AMBOS es lo del hogar y lo propio, que es todo lo que
# un miembro puede ver.
AMBOS = "all"


def registros(hogar, membresia, filtros):
    """Los registros que cumplen los filtros, de mas reciente a mas antiguo.

    `filtros` es el `cleaned_data` de ReporteForm: `desde` y `hasta` siempre;
    `tipo`, `ambito`, `categoria`, `miembro` y `comercio` opcionales.
    """
    qs = visibles(Transaction.objects.for_household(hogar), membresia).filter(
        date__gte=filtros["desde"], date__lte=filtros["hasta"],
    )
    if filtros.get("tipo") in (INCOME, EXPENSE):
        qs = qs.filter(category__kind=filtros["tipo"])
    ambito = filtros.get("ambito") or AMBOS
    if ambito == HOGAR:
        qs = qs.filter(scope=HOGAR)
    elif ambito == PERSONAL:
        qs = qs.filter(scope=PERSONAL, member=membresia)
    if filtros.get("categoria"):
        qs = qs.filter(category=filtros["categoria"])
    if filtros.get("miembro"):
        qs = qs.filter(member=filtros["miembro"])
    if filtros.get("comercio"):
        qs = qs.filter(merchant__name__icontains=filtros["comercio"])
    return qs.select_related("category", "merchant", "member__user").order_by("-date", "-pk")


def _desglose(filas, clave):
    """Totales por `clave(fila)`, de mayor a menor, con su porcentaje del total.

    Los ingresos y los gastos no se suman entre si: el desglose es de lo que
    pese mas en el reporte, y mezclar el sueldo con el super no dice nada. Si
    hay de los dos, se desglosan los gastos.
    """
    hay_gastos = any(t.category.kind == EXPENSE for t in filas)
    kind = EXPENSE if hay_gastos else INCOME
    totales = defaultdict(lambda: CERO)
    objetos = {}
    for t in filas:
        if t.category.kind != kind:
            continue
        objeto = clave(t)
        totales[objeto.pk] += t.amount
        objetos[objeto.pk] = objeto
    suma = sum(totales.values(), CERO)
    resultado = [
        {"objeto": objetos[pk], "total": centavos(total),
         "porcentaje": round(total * 100 / suma) if suma else 0}
        for pk, total in totales.items()
    ]
    resultado.sort(key=lambda f: (-f["total"], str(f["objeto"])))
    return kind, resultado


def generar(hogar, membresia, filtros):
    filas = list(registros(hogar, membresia, filtros))
    ingresos = sum((t.amount for t in filas if t.category.kind == INCOME), CERO)
    gastos = sum((t.amount for t in filas if t.category.kind == EXPENSE), CERO)
    kind, por_categoria = _desglose(filas, lambda t: t.category)
    _kind, por_miembro = _desglose(filas, lambda t: t.member)
    return {
        "desde": filtros["desde"],
        "hasta": filtros["hasta"],
        "filas": filas,
        "total_ingresos": centavos(ingresos),
        "total_gastos": centavos(gastos),
        "neto": centavos(ingresos - gastos),
        "desglose_kind": kind,
        "por_categoria": [{"categoria": f["objeto"], "total": f["total"],
                           "porcentaje": f["porcentaje"]} for f in por_categoria],
        "por_miembro": [{"miembro": f["objeto"], "total": f["total"],
                         "porcentaje": f["porcentaje"]} for f in por_miembro],
    }

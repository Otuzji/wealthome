"""Summary: lo que los meses cerrados dicen, en filas y en series.

Un cierre (`MonthlyClose`) guarda los cuatro totales, la varianza y el
balance; lo que se fue al ahorro y a las mesadas vive en el reparto
materializado del mes (`MonthlyAllocation.actual_amount`), y lo planeado y lo
real por categoria en las lineas y los registros del mes, que un mes cerrado
conserva. Aqui se junta todo en una sola pasada por hogar para que la
pantalla no haga una consulta por mes.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from .models import BudgetLine, Category, MonthlyAllocation, MonthlyClose, Transaction
from .models.catalog import EXPENSE, INCOME

# Las graficas mes a mes muestran el ultimo ano; la tabla, todo.
MESES_EN_LAS_GRAFICAS = 12

CERO = Decimal("0.00")


def _etiqueta(mes):
    return f"{mes.year}-{mes.month:02d}"


def _repartos(hogar, ids):
    """Por mes: lo que fue al ahorro (reglas sin miembro: una meta o un fondo)
    y lo que se repartio de mesada (reglas con miembro). Lo real del cierre y,
    si el cierre no llego a ajustar la fila, lo planeado."""
    ahorro, mesada = defaultdict(lambda: CERO), defaultdict(lambda: CERO)
    repartos = MonthlyAllocation.objects.for_household(hogar).filter(budget_month_id__in=ids)
    for r in repartos:
        importe = r.actual_amount if r.actual_amount is not None else r.planned_amount
        if r.member_id is None:
            ahorro[r.budget_month_id] += importe
        else:
            mesada[r.budget_month_id] += importe
    return ahorro, mesada


def _por_categoria(hogar, ids):
    """(mes, categoria) → planeado y real, en dos consultas agregadas."""
    planeado, real = {}, {}
    lineas = (
        BudgetLine.objects.for_household(hogar).filter(budget_month_id__in=ids)
        .values("budget_month_id", "category_id").annotate(total=Sum("planned_amount"))
    )
    for fila in lineas:
        planeado[(fila["budget_month_id"], fila["category_id"])] = fila["total"]
    registros = (
        Transaction.objects.for_household(hogar).filter(budget_month_id__in=ids)
        .values("budget_month_id", "category_id").annotate(total=Sum("amount"))
    )
    for fila in registros:
        real[(fila["budget_month_id"], fila["category_id"])] = fila["total"]
    return planeado, real


def resumen_de_cierres(hogar):
    """Las filas de la tabla (del mas reciente al mas antiguo) y las series de
    las graficas (del mas antiguo al mas reciente, ultimos 12).

    Las series viajan como `str` y no como Decimal: json_script no sabe
    serializar Decimal, y pasar por float seria meter coma flotante en una
    aplicacion financiera por comodidad de una grafica.
    """
    cierres = list(
        MonthlyClose.objects.for_household(hogar)
        .select_related("budget_month")
        .order_by("budget_month__year", "budget_month__month")
    )
    ids = [c.budget_month_id for c in cierres]
    ahorro, mesada = _repartos(hogar, ids)
    planeado, real = _por_categoria(hogar, ids)

    ids_categorias = {cat for _, cat in list(planeado) + list(real)}
    for cierre in cierres:
        ids_categorias.update(int(k) for k in cierre.varianza_por_categoria)
    categorias = {
        c.pk: c for c in Category.objects.for_household(hogar).filter(pk__in=ids_categorias)
    }

    filas = []
    for cierre in cierres:
        varianza = [
            {"categoria": categorias[int(pk)], "importe": Decimal(importe)}
            for pk, importe in cierre.varianza_por_categoria.items()
            if int(pk) in categorias
        ]
        # De la peor desviacion a la mejor: lo que se fue de madre primero.
        varianza.sort(key=lambda v: v["importe"])
        filas.append({
            "cierre": cierre, "mes": cierre.budget_month,
            "etiqueta": _etiqueta(cierre.budget_month),
            "ingresos": cierre.ingresos_reales,
            "ingresos_plan": cierre.ingresos_presupuestados,
            "gastos": cierre.egresos_reales,
            "gastos_plan": cierre.egresos_presupuestados,
            "ahorro": ahorro[cierre.budget_month_id],
            "mesada": mesada[cierre.budget_month_id],
            "balance": cierre.balance,
            "varianza": varianza,
        })

    recientes = filas[-MESES_EN_LAS_GRAFICAS:]
    series = {
        "meses": {
            "etiquetas": [f["etiqueta"] for f in recientes],
            "ingresos": [str(f["ingresos"]) for f in recientes],
            "gastos": [str(f["gastos"]) for f in recientes],
            "ahorro": [str(f["ahorro"]) for f in recientes],
            "mesada": [str(f["mesada"]) for f in recientes],
        },
        "por_mes": _series_por_mes(recientes, categorias, planeado, real),
        "categorias": _series_por_categoria(recientes, categorias, planeado, real),
    }
    filas.reverse()
    return {"filas": filas, "series": series}


def _series_por_mes(filas, categorias, planeado, real):
    """Para "planned against real": por mes y por tipo, una barra planeada y
    una real por categoria. Dos series por mes y no una: la del sueldo
    aplasta a la del super si van juntas."""
    por_mes = {}
    for fila in filas:
        mes_id = fila["mes"].pk
        series = {}
        for kind in (INCOME, EXPENSE):
            cats = sorted(
                (c for c in categorias.values() if c.kind == kind
                 and ((mes_id, c.pk) in planeado or (mes_id, c.pk) in real)),
                key=lambda c: c.etiqueta(),
            )
            series[kind] = {
                "etiquetas": [c.etiqueta() for c in cats],
                "planeado": [str(planeado.get((mes_id, c.pk), CERO)) for c in cats],
                "real": [str(real.get((mes_id, c.pk), CERO)) for c in cats],
            }
        por_mes[fila["etiqueta"]] = series
    return por_mes


def _series_por_categoria(filas, categorias, planeado, real):
    """Para "by category": una categoria a lo largo de los meses, planeado y
    real. Los gastos primero y de mayor a menor gasto real: lo que mas pesa
    es lo que se quiere mirar."""
    etiquetas = [f["etiqueta"] for f in filas]
    lista, serie_plan, serie_real = [], {}, {}
    totales = defaultdict(lambda: CERO)
    for fila in filas:
        for c in categorias.values():
            totales[c.pk] += real.get((fila["mes"].pk, c.pk), CERO)
    usadas = [
        c for c in categorias.values()
        if any((f["mes"].pk, c.pk) in planeado or (f["mes"].pk, c.pk) in real for f in filas)
    ]
    usadas.sort(key=lambda c: (c.kind != EXPENSE, -totales[c.pk], c.etiqueta()))
    for c in usadas:
        clave = str(c.pk)
        lista.append({"id": clave, "nombre": c.etiqueta(), "kind": c.kind})
        serie_plan[clave] = [str(planeado.get((f["mes"].pk, c.pk), CERO)) for f in filas]
        serie_real[clave] = [str(real.get((f["mes"].pk, c.pk), CERO)) for f in filas]
    return {"etiquetas": etiquetas, "lista": lista, "planeado": serie_plan, "real": serie_real}

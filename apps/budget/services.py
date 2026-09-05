"""El único módulo que cruza el ORM y el motor.

Lee modelos, llama a apps/budget/engine/ y escribe el resultado. Que la
frontera esté en un solo archivo es lo que la hace auditable de un vistazo.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.budget.engine import closing as motor_closing
from apps.budget.engine.money import centavos
from apps.budget.models import (
    DIAS_PARA_EL_CIERRE_AUTOMATICO,
    BudgetLine,
    BudgetMonth,
    ExpenseRule,
    IncomeSource,
    MesCerrado,
    MonthlyClose,
    Transaction,
)
from apps.budget.models.catalog import EXPENSE, INCOME


@dataclass(frozen=True)
class LineaProyectada:
    categoria_id: int          # nunca None: los ingresos usan la categoria de ingreso
    kind: str
    importe: Decimal
    origen: str          # "income" | "expense"
    origen_id: int
    nombre: str


@dataclass(frozen=True)
class ProyeccionDeMes:
    anio: int
    mes: int
    lineas: tuple
    total_ingresos: Decimal
    total_egresos: Decimal
    sobrante: Decimal


def _ultimo_dia(anio, mes):
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def historial_de_ingreso(fuente, hasta):
    """Los totales mensuales reales de esa fuente, del más antiguo al último.

    Es lo que alimenta el modo rolling_average del §4.1. Sin
    Transaction.income_source (desviación 4) no se podría calcular.
    """
    desde = date(hasta.year - 1, hasta.month, 1)
    filas = (
        Transaction.objects.for_household(fuente.household)
        .filter(income_source=fuente, date__gte=desde, date__lt=hasta)
        .values("budget_month__year", "budget_month__month")
        .annotate(total=Sum("amount"))
        .order_by("budget_month__year", "budget_month__month")
    )
    return [centavos(f["total"]) for f in filas]


def proyectar(hogar, anio, mes):
    """Un mes calculado desde las reglas vigentes, sin persistir nada."""
    primero = date(anio, mes, 1)
    categoria_de_ingreso = _categoria_de_ingreso(hogar)
    lineas = []

    for fuente in IncomeSource.objects.for_household(hogar):
        veces = len(fuente.ocurrencias_en(anio, mes))
        if not veces:
            continue
        cifra = fuente.cifra_del_mes(historial=historial_de_ingreso(fuente, primero))
        if cifra is None:
            # rolling_average sin historia: aún no hay datos, y no se inventa
            # un número. La interfaz lo dice con todas sus letras.
            continue
        lineas.append(
            LineaProyectada(
                categoria_id=categoria_de_ingreso.pk, kind=INCOME,
                importe=centavos(cifra * veces),
                origen="income", origen_id=fuente.pk, nombre=fuente.name,
            )
        )

    for regla in ExpenseRule.objects.for_household(hogar).select_related("category"):
        importe = regla.importe_del_mes(anio, mes)
        if importe <= 0:
            continue
        lineas.append(
            LineaProyectada(
                categoria_id=regla.category_id, kind=EXPENSE, importe=importe,
                origen="expense", origen_id=regla.pk, nombre=regla.name,
            )
        )

    ingresos = centavos(sum(l.importe for l in lineas if l.kind == INCOME))
    egresos = centavos(sum(l.importe for l in lineas if l.kind == EXPENSE))
    return ProyeccionDeMes(
        anio=anio, mes=mes, lineas=tuple(lineas),
        total_ingresos=ingresos, total_egresos=egresos,
        sobrante=centavos(ingresos - egresos),
    )


@transaction.atomic
def materializar(hogar, anio, mes):
    """Convierte la proyección de un mes en filas editables (§4.2)."""
    fila, creado = BudgetMonth.unscoped.get_or_create(
        household=hogar, year=anio, month=mes,
        defaults={"status": BudgetMonth.OPEN, "opened_at": timezone.now()},
    )
    # Bloquea la fila: dos pestañas abiertas el día 1 es el caso normal.
    fila = BudgetMonth.unscoped.select_for_update().get(pk=fila.pk)
    if fila.lineas.exists():
        return fila

    for proyectada in proyectar(hogar, anio, mes).lineas:
        linea = BudgetLine(
            household=hogar, budget_month=fila, kind=proyectada.kind,
            planned_amount=proyectada.importe,
            category_id=proyectada.categoria_id,
        )
        if proyectada.origen == "income":
            linea.source_income_id = proyectada.origen_id
        else:
            linea.source_expense_rule_id = proyectada.origen_id
        # Hallazgo de la revisión previa a esta tarea: BudgetLine.clean()
        # rechaza una línea cuyo kind no coincida con el de su categoría. Sin
        # full_clean() aquí, una ExpenseRule mal configurada (apuntando a una
        # categoría de ingreso) escribiría igual la línea contradictoria, y el
        # error solo aparecería mucho después, dentro de engine.closing.cerrar,
        # señalando una categoría y nada más.
        linea.full_clean()
        linea.save()
    return fila


def _categoria_de_ingreso(hogar):
    """La categoría donde caen las líneas de ingreso.

    Falla aquí y con su motivo si el hogar no tiene ninguna: un hogar sin
    árbol sembrado es un hogar mal creado (`crear_hogar` lo siembra), y
    devolver None haría reventar la proyección con un AttributeError lejos
    de la causa.
    """
    from apps.budget.models import Category

    categoria = Category.objects.for_household(hogar).filter(kind=INCOME).first()
    if categoria is None:
        raise LookupError(
            f"El hogar {hogar.pk} no tiene ninguna categoría de ingreso. "
            "¿Se creó sin pasar por households.services.crear_hogar, que "
            "siembra el árbol de apps/budget/seeds.py?"
        )
    return categoria


@transaction.atomic
def cerrar_mes(mes):
    """Escribe el MonthlyClose y congela el mes (§4.2)."""
    if mes.esta_cerrado:
        raise MesCerrado(f"El mes {mes} ya está cerrado.")

    reales = _reales_por_categoria(mes)

    renglones = []
    vistos = set()
    for linea in mes.lineas.all():
        clave = (linea.category_id, linea.kind)
        vistos.add(clave)
        renglones.append(
            motor_closing.Renglon(
                categoria_id=linea.category_id, kind=linea.kind,
                presupuestado=linea.planned_amount,
                real=reales.get(clave, Decimal("0.00")),
            )
        )
    # Lo real sin línea planeada (un gasto en una categoría que nadie
    # presupuestó) cuenta igual: si no, el balance no cuadraría.
    for clave, real in reales.items():
        if clave in vistos:
            continue
        renglones.append(
            motor_closing.Renglon(
                categoria_id=clave[0], kind=clave[1],
                presupuestado=Decimal("0.00"), real=real,
            )
        )

    cierre_calculado = motor_closing.cerrar(renglones, _arrastre_previo(mes))

    cierre = MonthlyClose(
        household=mes.household, budget_month=mes,
        ingresos_presupuestados=cierre_calculado.ingresos_presupuestados,
        ingresos_reales=cierre_calculado.ingresos_reales,
        egresos_presupuestados=cierre_calculado.egresos_presupuestados,
        egresos_reales=cierre_calculado.egresos_reales,
        varianza_por_categoria={str(k): str(v) for k, v in cierre_calculado.varianza_por_categoria.items()},
        balance=cierre_calculado.balance,
        arrastre=cierre_calculado.arrastre,
    )
    cierre.save()

    mes.status = BudgetMonth.CLOSED
    mes.closed_at = timezone.now()
    mes.save(update_fields=["status", "closed_at"])
    return cierre


def _reales_por_categoria(mes):
    reales = {}
    for tx in Transaction.objects.for_household(mes.household).filter(
        budget_month=mes
    ).select_related("category"):
        clave = (tx.category_id, tx.category.kind)
        reales[clave] = reales.get(clave, Decimal("0.00")) + tx.amount
    return {k: centavos(v) for k, v in reales.items()}


def _arrastre_previo(mes):
    anterior = (
        MonthlyClose.objects.for_household(mes.household)
        .filter(budget_month__year__lte=mes.year)
        .exclude(budget_month=mes)
        .order_by("-budget_month__year", "-budget_month__month")
        .first()
    )
    return anterior.arrastre if anterior else Decimal("0.00")


def _esta_vencido(mes, hoy):
    fin = _ultimo_dia(mes.year, mes.month)
    return hoy > fin + timedelta(days=DIAS_PARA_EL_CIERRE_AUTOMATICO)


def _mes_siguiente(anio, mes):
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def cerrar_vencidos(hogar, hoy=None):
    """Cierra en cadena, EN ORDEN, porque cada cierre arrastra su saldo.

    No se limita a las filas ya materializadas: un hogar que faltó dos meses
    puede no haber visitado nunca febrero (ninguna fila `BudgetMonth` para
    él). Por eso, tras cerrar el mes abierto más antiguo, materializa el
    siguiente antes de volver a mirar — así febrero se crea, se comprueba y,
    si también está vencido, se cierra, todo antes de llegar a marzo.
    """
    hoy = hoy or timezone.localdate()
    cerrados = []
    while True:
        mes = (
            BudgetMonth.objects.for_household(hogar)
            .filter(status=BudgetMonth.OPEN)
            .order_by("year", "month")
            .first()
        )
        if mes is None or not _esta_vencido(mes, hoy):
            break
        cerrados.append(cerrar_mes(mes))
        siguiente_anio, siguiente_mes = _mes_siguiente(mes.year, mes.month)
        materializar(hogar, siguiente_anio, siguiente_mes)
    return cerrados


def obtener_mes(hogar, anio, mes, hoy=None):
    """El único punto de entrada al ciclo del mes (§2.3).

    Cierra los vencidos, materializa el corriente, proyecta el futuro y
    devuelve el cierre congelado si ya pasó.
    """
    hoy = hoy or timezone.localdate()
    cerrar_vencidos(hogar, hoy)

    existente = BudgetMonth.objects.for_household(hogar).filter(year=anio, month=mes).first()
    if existente is not None:
        return existente

    if (anio, mes) > (hoy.year, hoy.month):
        return proyectar(hogar, anio, mes)

    return materializar(hogar, anio, mes)


@transaction.atomic
def reemplazar_regla(regla, nuevo_importe, desde):
    """§3.2: las reglas nunca se mutan.

    Subir el alquiler cierra la regla vieja con effective_to = el día anterior
    y crea su sucesora. El historial queda intacto sin un modelo adicional, y
    ningún mes ya cerrado cambia.
    """
    regla.effective_to = desde - timedelta(days=1)
    regla.save(update_fields=["effective_to"])

    sucesora = ExpenseRule(
        household=regla.household, category=regla.category, name=regla.name,
        amount=nuevo_importe, periodicity=regla.periodicity,
        effective_from=desde, is_essential=regla.is_essential,
        owner=regla.owner, scope=regla.scope,
    )
    sucesora.save()
    return sucesora

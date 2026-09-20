"""Summary: las filas de los meses cerrados y las series de sus graficas."""

import json
from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services_summary
from apps.budget.engine import cascade as motor_cascade
from apps.budget.models import BudgetMonth
from tests.factories import HouseholdFactory, MembershipFactory
from tests.factories_budget import (
    AllocationRuleFactory, BudgetLineFactory, BudgetMonthFactory, CategoryFactory,
    MonthlyAllocationFactory, MonthlyCloseFactory, TransactionFactory,
)

pytestmark = pytest.mark.django_db


def _cerrar(mes):
    """La guarda de EscrituraAcotadaAlMes no deja sembrar contra un mes
    cerrado: se siembra abierto y se cierra despues."""
    mes.status = BudgetMonth.CLOSED
    mes.save(update_fields=["status"])


def _mes_cerrado(hogar, anio, numero, ingresos="3000.00", gastos="2000.00", balance="1000.00"):
    mes = BudgetMonthFactory(household=hogar, year=anio, month=numero)
    MonthlyCloseFactory(
        household=hogar, budget_month=mes,
        ingresos_reales=Decimal(ingresos), egresos_reales=Decimal(gastos),
        balance=Decimal(balance), arrastre=Decimal(balance),
    )
    return mes


def test_sin_cierres_da_filas_y_series_vacias():
    hogar = HouseholdFactory()

    resumen = services_summary.resumen_de_cierres(hogar)

    assert resumen["filas"] == []
    assert resumen["series"]["meses"]["etiquetas"] == []
    assert resumen["series"]["por_mes"] == {}
    assert resumen["series"]["categorias"]["lista"] == []


def test_las_filas_van_del_mas_reciente_al_mas_antiguo_y_las_series_al_reves():
    hogar = HouseholdFactory()
    for numero in (1, 2, 3):
        _cerrar(_mes_cerrado(hogar, 2026, numero))

    resumen = services_summary.resumen_de_cierres(hogar)

    assert [f["etiqueta"] for f in resumen["filas"]] == ["2026-03", "2026-02", "2026-01"]
    assert resumen["series"]["meses"]["etiquetas"] == ["2026-01", "2026-02", "2026-03"]


def test_el_ahorro_y_la_mesada_salen_del_reparto_real_del_mes():
    hogar = HouseholdFactory()
    miembro = MembershipFactory(household=hogar)
    mes = _mes_cerrado(hogar, 2026, 1)
    ahorro = AllocationRuleFactory(household=hogar, target_type=motor_cascade.GOAL,
                                   method=motor_cascade.FIXED, amount=Decimal("200.00"))
    mesada = AllocationRuleFactory(household=hogar, target_type=motor_cascade.ALLOWANCE,
                                   method=motor_cascade.FIXED, amount=Decimal("50.00"))
    MonthlyAllocationFactory(household=hogar, budget_month=mes, rule=ahorro,
                             planned_amount=Decimal("200.00"), actual_amount=Decimal("180.00"))
    MonthlyAllocationFactory(household=hogar, budget_month=mes, rule=mesada, member=miembro,
                             planned_amount=Decimal("50.00"), actual_amount=Decimal("50.00"))
    _cerrar(mes)

    fila = services_summary.resumen_de_cierres(hogar)["filas"][0]

    assert fila["ahorro"] == Decimal("180.00")
    assert fila["mesada"] == Decimal("50.00")
    assert fila["ingresos"] == Decimal("3000.00")
    assert fila["gastos"] == Decimal("2000.00")
    assert fila["balance"] == Decimal("1000.00")


def test_lo_planeado_y_lo_real_por_categoria_van_en_las_series():
    hogar = HouseholdFactory()
    mes = _mes_cerrado(hogar, 2026, 1)
    comida = CategoryFactory(household=hogar, slug="groceries", name="Groceries")
    sueldo = CategoryFactory(household=hogar, slug="salary", name="Salary", kind="income")
    BudgetLineFactory(household=hogar, budget_month=mes, category=comida,
                      kind="expense", planned_amount=Decimal("400.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=comida,
                       amount=Decimal("250.00"), date=date(2026, 1, 4))
    TransactionFactory(household=hogar, budget_month=mes, category=comida,
                       amount=Decimal("100.00"), date=date(2026, 1, 20))
    TransactionFactory(household=hogar, budget_month=mes, category=sueldo,
                       amount=Decimal("3000.00"), date=date(2026, 1, 1))
    _cerrar(mes)

    series = services_summary.resumen_de_cierres(hogar)["series"]

    gastos = series["por_mes"]["2026-01"]["expense"]
    assert gastos == {"etiquetas": ["Groceries"], "planeado": ["400.00"], "real": ["350.00"]}
    ingresos = series["por_mes"]["2026-01"]["income"]
    assert ingresos == {"etiquetas": ["Salary"], "planeado": ["0.00"], "real": ["3000.00"]}
    # Gastos primero, y todo serializable de verdad: ni un Decimal suelto.
    assert [c["nombre"] for c in series["categorias"]["lista"]] == ["Groceries", "Salary"]
    assert series["categorias"]["real"][str(comida.pk)] == ["350.00"]
    assert json.dumps(series)


def test_la_varianza_del_cierre_se_ordena_de_peor_a_mejor():
    hogar = HouseholdFactory()
    mes = BudgetMonthFactory(household=hogar, year=2026, month=1)
    comida = CategoryFactory(household=hogar, slug="groceries")
    luz = CategoryFactory(household=hogar, slug="power")
    MonthlyCloseFactory(household=hogar, budget_month=mes, varianza_por_categoria={
        str(comida.pk): "-120.00", str(luz.pk): "15.00",
    })
    _cerrar(mes)

    fila = services_summary.resumen_de_cierres(hogar)["filas"][0]

    assert [v["categoria"] for v in fila["varianza"]] == [comida, luz]
    assert fila["varianza"][0]["importe"] == Decimal("-120.00")


def test_las_graficas_se_quedan_con_los_ultimos_doce_meses():
    hogar = HouseholdFactory()
    for i in range(14):
        anio, numero = 2025 + i // 12, i % 12 + 1
        _cerrar(_mes_cerrado(hogar, anio, numero))

    resumen = services_summary.resumen_de_cierres(hogar)

    assert len(resumen["filas"]) == 14
    assert resumen["series"]["meses"]["etiquetas"][0] == "2025-03"
    assert len(resumen["series"]["meses"]["etiquetas"]) == 12

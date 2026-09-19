"""Una linea por vencimiento, con su fecha y su estado de pago.

La fecha ya estaba en el setup: `effective_from` es el ancla (alquiler desde
el 1 → vence el 1 de cada mes). Aqui llega a cada linea del mes: un gasto
quincenal da dos o tres lineas, cada una con su importe por pago y su fecha,
y cada una se paga por separado.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services
from apps.budget.engine.periodicity import BIWEEKLY, MONTHLY
from apps.budget.models import BudgetLine, Transaction
from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import CategoryFactory, ExpenseRuleFactory, IncomeSourceFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar():
    return crear_hogar(UserFactory(), "Family Thompson", family_size=2)


def test_la_proyeccion_da_una_linea_por_vencimiento(hogar):
    ExpenseRuleFactory(household=hogar, name="Bell", amount=Decimal("74.00"),
                       periodicity=BIWEEKLY, effective_from=date(2026, 10, 2))
    ExpenseRuleFactory(household=hogar, name="Alquiler", amount=Decimal("1750.00"),
                       periodicity=MONTHLY, effective_from=date(2026, 1, 1))

    lineas = [l for l in services.proyectar(hogar, 2026, 10).lineas if l.kind == "expense"]

    bell = [l for l in lineas if l.nombre == "Bell"]
    assert [(l.importe, l.fecha) for l in bell] == [
        (Decimal("74.00"), date(2026, 10, 2)),
        (Decimal("74.00"), date(2026, 10, 16)),
        (Decimal("74.00"), date(2026, 10, 30)),
    ]
    alquiler = [l for l in lineas if l.nombre == "Alquiler"]
    assert [(l.importe, l.fecha) for l in alquiler] == [(Decimal("1750.00"), date(2026, 10, 1))]
    assert services.proyectar(hogar, 2026, 10).total_egresos == Decimal("1972.00")


def test_los_ingresos_tambien_van_por_pago(hogar):
    IncomeSourceFactory(household=hogar, owner=hogar.active_memberships().first(),
                        amount=Decimal("1300.00"), periodicity=BIWEEKLY,
                        effective_from=date(2026, 10, 2))

    ingresos = [l for l in services.proyectar(hogar, 2026, 10).lineas if l.kind == "income"]

    assert [l.importe for l in ingresos] == [Decimal("1300.00")] * 3
    assert [l.fecha for l in ingresos] == [date(2026, 10, 2), date(2026, 10, 16), date(2026, 10, 30)]


def test_materializar_escribe_la_fecha_en_cada_linea(hogar):
    ExpenseRuleFactory(household=hogar, name="Bell", amount=Decimal("74.00"),
                       periodicity=BIWEEKLY, effective_from=date(2026, 10, 2))

    mes = services.materializar(hogar, 2026, 10)

    assert sorted(mes.lineas.values_list("due_date", flat=True)) == [
        date(2026, 10, 2), date(2026, 10, 16), date(2026, 10, 30)
    ]
    assert services.totales_del_mes(mes).total_egresos == Decimal("222.00")


def test_refrescar_casa_por_regla_y_fecha(hogar):
    """Pasar Bell de mensual a quincenal y refrescar deja tres lineas, no una."""
    regla = ExpenseRuleFactory(household=hogar, name="Bell", amount=Decimal("74.00"),
                               periodicity=MONTHLY, effective_from=date(2026, 10, 2))
    mes = services.materializar(hogar, 2026, 10)
    assert mes.lineas.count() == 1
    regla.periodicity = BIWEEKLY
    regla.save()

    services.refrescar_desde_las_reglas(hogar, mes)

    assert sorted(mes.lineas.values_list("due_date", flat=True)) == [
        date(2026, 10, 2), date(2026, 10, 16), date(2026, 10, 30)
    ]


def test_el_estado_de_una_linea_sale_de_lo_pagado(hogar):
    ExpenseRuleFactory(household=hogar, name="Alquiler", amount=Decimal("1750.00"),
                       effective_from=date(2026, 1, 1))
    mes = services.materializar(hogar, 2026, 10)
    linea = mes.lineas.get()
    miembro = hogar.active_memberships().first()
    assert linea.estado == BudgetLine.PENDIENTE
    assert linea.pagado == Decimal("0.00")

    Transaction(household=hogar, budget_month=mes, budget_line=linea, category=linea.category,
                amount=Decimal("1000.00"), date=date(2026, 10, 1), member=miembro).save()
    linea = BudgetLine.objects.for_household(hogar).get(pk=linea.pk)
    assert linea.estado == BudgetLine.PARCIAL
    assert linea.restante == Decimal("750.00")

    Transaction(household=hogar, budget_month=mes, budget_line=linea, category=linea.category,
                amount=Decimal("750.00"), date=date(2026, 10, 2), member=miembro).save()
    linea = BudgetLine.objects.for_household(hogar).get(pk=linea.pk)
    assert linea.estado == BudgetLine.PAGADA
    assert linea.restante == Decimal("0.00")


def test_una_partida_puntual_lleva_su_fecha(hogar):
    mes = services.materializar(hogar, 2026, 10)
    categoria = CategoryFactory(household=hogar, slug="viaje", kind="expense")
    linea = BudgetLine(household=hogar, budget_month=mes, category=categoria, kind="expense",
                       planned_amount=Decimal("900.00"), is_exceptional=True,
                       due_date=date(2026, 10, 20))
    linea.full_clean()
    linea.save()

    assert mes.lineas.get().due_date == date(2026, 10, 20)

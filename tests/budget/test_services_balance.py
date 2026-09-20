"""El balance del hogar: activos, pasivos y neto, con el ahorro y el efectivo
calculados y no tecleados."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.budget import services_balance
from apps.budget.models import BalanceItem, BudgetMonth
from apps.budget.models.balance import LIQUID, LONG_TERM, PROPERTY, SHORT_TERM
from tests.factories import HouseholdFactory, MembershipFactory
from tests.factories_budget import (
    BudgetMonthFactory, CategoryFactory, GoalContributionFactory, GoalFactory,
    TransactionFactory,
)

pytestmark = pytest.mark.django_db


def _hogar():
    hogar = HouseholdFactory()
    return hogar, MembershipFactory(household=hogar)


def test_el_neto_es_activos_menos_pasivos_por_grupo():
    hogar, membresia = _hogar()
    BalanceItem.unscoped.create(household=hogar, group=PROPERTY, name="Casa",
                               amount=Decimal("400000.00"))
    BalanceItem.unscoped.create(household=hogar, group=LONG_TERM, name="Hipoteca",
                               amount=Decimal("250000.00"))
    BalanceItem.unscoped.create(household=hogar, group=SHORT_TERM, name="Visa",
                               amount=Decimal("1200.00"))

    p = services_balance.patrimonio(hogar, membresia)

    assert p["total_activos"] == Decimal("400000.00")
    assert p["total_pasivos"] == Decimal("251200.00")
    assert p["neto"] == Decimal("148800.00")
    por_clave = {g["clave"]: g for g in p["grupos"]}
    assert por_clave[PROPERTY]["total"] == Decimal("400000.00")
    assert [f["nombre"] for f in por_clave[SHORT_TERM]["filas"]] == ["Visa"]


def test_el_ahorro_y_el_efectivo_son_filas_automaticas_en_liquidos():
    hogar, membresia = _hogar()
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("300.00"))
    mes = BudgetMonthFactory(household=hogar, year=2026, month=9, status=BudgetMonth.OPEN)
    entra = CategoryFactory(household=hogar, slug="entra", kind="income")
    sale = CategoryFactory(household=hogar, slug="sale", kind="expense")
    TransactionFactory(household=hogar, budget_month=mes, category=entra,
                       amount=Decimal("2000.00"), date=date(2026, 9, 1))
    TransactionFactory(household=hogar, budget_month=mes, category=sale,
                       amount=Decimal("450.00"), date=date(2026, 9, 5))
    BalanceItem.unscoped.create(household=hogar, group=LIQUID, name="Chequing",
                               amount=Decimal("1000.00"))

    p = services_balance.patrimonio(hogar, membresia)

    liquidos = next(g for g in p["grupos"] if g["clave"] == LIQUID)
    assert [(str(f["nombre"]), f["importe"], f["automatico"]) for f in liquidos["filas"]] == [
        ("Savings", Decimal("300.00"), True),
        ("Cash", Decimal("1550.00"), True),
        ("Chequing", Decimal("1000.00"), False),
    ]
    assert p["total_activos"] == Decimal("2850.00")


def test_sin_mes_abierto_el_efectivo_es_cero():
    hogar, _ = _hogar()
    assert services_balance.efectivo_del_mes_abierto(hogar) == Decimal("0.00")


def test_una_deuda_se_teclea_en_positivo():
    hogar, _ = _hogar()
    item = BalanceItem(household=hogar, group=SHORT_TERM, name="Visa", amount=Decimal("-5.00"))
    with pytest.raises(ValidationError):
        item.full_clean()
    assert BalanceItem(group=SHORT_TERM).es_pasivo
    assert not BalanceItem(group=PROPERTY).es_pasivo

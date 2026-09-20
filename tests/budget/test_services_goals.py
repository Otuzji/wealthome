"""El dominio de las metas: aportar, y el estado que se deriva de lo aportado.

`reached` lo pone la aplicacion al cubrir el objetivo; `abandoned` solo el
usuario. Una abandonada no se mueve sola aunque le siga cayendo cascada.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services_goals
from apps.budget.models import BudgetMonth, Goal, GoalContribution, MesCerrado
from tests.factories import HouseholdFactory, MembershipFactory
from tests.factories_budget import BudgetMonthFactory, GoalContributionFactory, GoalFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar():
    return HouseholdFactory()


# --- aportar ------------------------------------------------------------------


def test_aportar_resuelve_el_mes_por_la_fecha(hogar):
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    meta = GoalFactory(household=hogar)
    miembro = MembershipFactory(household=hogar)

    aporte = services_goals.aportar(hogar, meta, Decimal("50.00"), date(2026, 3, 10), miembro)

    assert aporte.budget_month == mes
    assert aporte.member == miembro
    assert aporte.origen == "manual"


def test_aportar_en_un_mes_que_el_hogar_no_vivio_deja_el_mes_nulo(hogar):
    meta = GoalFactory(household=hogar)

    aporte = services_goals.aportar(
        hogar, meta, Decimal("50.00"), date(2025, 1, 10), MembershipFactory(household=hogar)
    )

    assert aporte.budget_month is None


def test_aportar_contra_un_mes_cerrado_revienta_y_no_escribe(hogar):
    BudgetMonthFactory(household=hogar, year=2026, month=3, status=BudgetMonth.CLOSED)
    meta = GoalFactory(household=hogar)

    with pytest.raises(MesCerrado):
        services_goals.aportar(
            hogar, meta, Decimal("50.00"), date(2026, 3, 10), MembershipFactory(household=hogar)
        )

    assert not GoalContribution.objects.for_household(hogar).exists()


def test_el_aporte_que_cubre_el_objetivo_marca_la_meta_alcanzada(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    services_goals.aportar(
        hogar, meta, Decimal("100.00"), date(2026, 3, 1), MembershipFactory(household=hogar)
    )

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


def test_un_aporte_parcial_deja_la_meta_activa(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    services_goals.aportar(
        hogar, meta, Decimal("99.99"), date(2026, 3, 1), MembershipFactory(household=hogar)
    )

    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


# --- recalcular_estado --------------------------------------------------------


def test_recalcular_reabre_una_alcanzada_que_ya_no_lo_esta(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("40.00"))

    assert services_goals.recalcular_estado(meta) is True
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_recalcular_no_toca_una_abandonada_aunque_este_cubierta(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.ABANDONED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))

    assert services_goals.recalcular_estado(meta) is False
    meta.refresh_from_db()
    assert meta.status == Goal.ABANDONED


def test_recalcular_dice_que_nada_cambio_cuando_nada_cambia(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("10.00"))

    assert services_goals.recalcular_estado(meta) is False


def test_recalcular_acepta_el_acumulado_ya_calculado(hogar):
    """Quien pinta la lista ya sumo los aportes: no se vuelve a la base."""
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    assert services_goals.recalcular_estado(meta, acumulado=Decimal("100.00")) is True
    assert meta.status == Goal.REACHED


# --- cambiar_estado -----------------------------------------------------------


def test_abandonar_y_reactivar(hogar):
    meta = GoalFactory(household=hogar)

    services_goals.cambiar_estado(meta, Goal.ABANDONED)
    meta.refresh_from_db()
    assert meta.status == Goal.ABANDONED

    services_goals.cambiar_estado(meta, Goal.ACTIVE)
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_reactivar_una_abandonada_ya_cubierta_la_da_por_alcanzada(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.ABANDONED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))

    services_goals.cambiar_estado(meta, Goal.ACTIVE)

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


@pytest.mark.parametrize("desde,hasta", [
    (Goal.ACTIVE, Goal.ACTIVE),
    (Goal.ACTIVE, Goal.REACHED),
    (Goal.REACHED, Goal.ABANDONED),
    (Goal.REACHED, Goal.ACTIVE),
    (Goal.ABANDONED, Goal.REACHED),
    (Goal.ACTIVE, "cualquier-cosa"),
])
def test_las_demas_transiciones_se_rechazan(hogar, desde, hasta):
    meta = GoalFactory(household=hogar, status=desde)

    with pytest.raises(ValueError):
        services_goals.cambiar_estado(meta, hasta)

    meta.refresh_from_db()
    assert meta.status == desde

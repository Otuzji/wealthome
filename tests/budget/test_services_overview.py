"""El servicio del Overview: Forecast, Real y Expenses.

Salen de las mismas funciones que This month (`totales`, `real_contra_planeado`);
estas pruebas fijan las cifras que el Overview deriva de ellas.
"""

from decimal import Decimal

import pytest

from apps.budget import services_overview
from apps.budget.engine import cascade as motor_cascade
from apps.budget.models import AllowanceLedger
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import (
    AllocationRuleFactory, AllowanceLedgerFactory, BudgetLineFactory,
    BudgetMonthFactory, CategoryFactory, GoalFactory, TransactionFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar_y_mes():
    """Un hogar sembrado y su octubre de 2026, el mes del calendario fijo de
    estas pruebas (nada depende de la fecha de hoy)."""
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=10)
    entra = CategoryFactory(household=hogar, slug="lo-que-entra", kind="income")
    sale = CategoryFactory(household=hogar, slug="lo-que-sale", kind="expense")
    return hogar, mes, entra, sale, hogar.active_memberships().get(user=user)


def _linea(hogar, mes, categoria, importe, **extra):
    return BudgetLineFactory(
        household=hogar, budget_month=mes, category=categoria,
        kind=categoria.kind, planned_amount=Decimal(importe), **extra,
    )


def _totales_del_hogar(hogar, mes, miembro):
    lineas = services_overview.lineas_del_ambito(mes, "household", miembro)
    txs = services_overview.transacciones_del_ambito(mes, "household", miembro)
    donas = services_overview.real_contra_planeado(lineas, txs)
    return services_overview.totales(
        donas["income"]["planeado"], donas["expense"]["planeado"],
        donas["income"]["real"], donas["expense"]["real"],
    )


# --- forecast del hogar -------------------------------------------------------


def test_forecast_hogar_reparte_el_sobrante_como_plan_the_month(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _linea(hogar, mes, entra, "5000.00")
    _linea(hogar, mes, sale, "3000.00")
    _linea(hogar, mes, sale, "500.00", is_exceptional=True)
    AllocationRuleFactory(household=hogar, order=1, target_type=motor_cascade.GOAL,
                          target_goal=GoalFactory(household=hogar),
                          method=motor_cascade.FIXED, amount=Decimal("500.00"))
    AllocationRuleFactory(household=hogar, order=2, target_type=motor_cascade.ALLOWANCE,
                          method=motor_cascade.REMAINDER, amount=None)

    f = services_overview.forecast_hogar(hogar, _totales_del_hogar(hogar, mes, otto))

    assert (f["ingresos"], f["egresos"]) == (Decimal("5000.00"), Decimal("3500.00"))
    assert f["sobrante"] == Decimal("1500.00")
    assert f["ahorro"] == Decimal("500.00")
    assert f["mesada"] == Decimal("1000.00")
    assert f["sin_asignar"] == Decimal("0.00")


def test_forecast_hogar_sin_sobrante_no_reparte(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _linea(hogar, mes, entra, "1000.00")
    _linea(hogar, mes, sale, "1500.00")
    AllocationRuleFactory(household=hogar, order=1, target_type=motor_cascade.ALLOWANCE,
                          method=motor_cascade.REMAINDER, amount=None)

    f = services_overview.forecast_hogar(hogar, _totales_del_hogar(hogar, mes, otto))

    assert f["sobrante"] == Decimal("-500.00")
    assert f["ahorro"] == f["mesada"] == f["sin_asignar"] == Decimal("0.00")


def test_forecast_hogar_deja_sin_asignar_lo_que_ninguna_regla_agota(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _linea(hogar, mes, entra, "3000.00")
    _linea(hogar, mes, sale, "1500.00")
    AllocationRuleFactory(household=hogar, order=1, target_type=motor_cascade.GOAL,
                          target_goal=GoalFactory(household=hogar),
                          method=motor_cascade.FIXED, amount=Decimal("500.00"))

    f = services_overview.forecast_hogar(hogar, _totales_del_hogar(hogar, mes, otto))

    assert f["ahorro"] == Decimal("500.00")
    assert f["mesada"] == Decimal("0.00")
    assert f["sin_asignar"] == Decimal("1000.00")


# --- expenses -----------------------------------------------------------------


def test_expenses_separa_budget_de_one_off(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    de_regla = _linea(hogar, mes, sale, "400.00")
    puntual = _linea(hogar, mes, sale, "200.00", is_exceptional=True)
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("300.00"), budget_line=de_regla)
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("200.00"), budget_line=puntual)
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("50.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=entra, member=otto,
                       amount=Decimal("1000.00"))

    txs = services_overview.transacciones_del_ambito(mes, "household", otto)

    assert services_overview.expenses(txs) == {
        "budget": Decimal("300.00"), "one_off": Decimal("250.00"),
    }


# --- forecast personal --------------------------------------------------------


def _hogar_de_dos(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    diana = MembershipFactory(household=hogar, role=Membership.MEMBER, user=UserFactory())
    # Sobrante del hogar: 1000, todo a la mesada, 500 para cada uno.
    _linea(hogar, mes, entra, "3000.00")
    _linea(hogar, mes, sale, "2000.00")
    AllocationRuleFactory(household=hogar, order=1, target_type=motor_cascade.ALLOWANCE,
                          method=motor_cascade.REMAINDER, amount=None)
    return hogar, mes, sale, otto, diana


def _totales_personales(mes, miembro):
    lineas = services_overview.lineas_del_ambito(mes, "personal", miembro)
    txs = services_overview.transacciones_del_ambito(mes, "personal", miembro)
    donas = services_overview.real_contra_planeado(lineas, txs)
    return services_overview.totales(
        donas["income"]["planeado"], donas["expense"]["planeado"],
        donas["income"]["real"], donas["expense"]["real"],
    )


def test_forecast_personal_mesada_arrastre_y_lo_que_queda(hogar_y_mes):
    hogar, mes, sale, otto, diana = _hogar_de_dos(hogar_y_mes)
    # Se toma a Otto: la primera membresia por pk, la primera de la mesada.
    AllowanceLedgerFactory(household=hogar, member=otto, budget_month=mes,
                           carried_in=Decimal("40.00"), adjustment=Decimal("-10.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("120.00"), scope="personal")

    f = services_overview.forecast_personal(hogar, mes, otto, _totales_personales(mes, otto))

    assert f["mesada"] == Decimal("500.00")
    assert f["arrastre"] == Decimal("40.00")
    assert f["ajuste"] == Decimal("-10.00")
    assert f["disponible"] == Decimal("530.00")
    assert f["queda"] == Decimal("410.00")


def test_forecast_personal_trae_las_cifras_personales(hogar_y_mes):
    hogar, mes, sale, otto, diana = _hogar_de_dos(hogar_y_mes)
    entra = CategoryFactory(household=hogar, slug="mi-ingreso", kind="income")
    _linea(hogar, mes, entra, "200.00", scope="personal", owner=otto)
    _linea(hogar, mes, sale, "80.00", scope="personal", owner=otto)

    f = services_overview.forecast_personal(hogar, mes, otto, _totales_personales(mes, otto))

    assert (f["ingresos"], f["egresos"]) == (Decimal("200.00"), Decimal("80.00"))


def test_forecast_personal_sin_libro_no_lo_crea(hogar_y_mes):
    hogar, mes, sale, otto, diana = _hogar_de_dos(hogar_y_mes)

    f = services_overview.forecast_personal(hogar, mes, diana, _totales_personales(mes, diana))

    assert (f["arrastre"], f["ajuste"]) == (Decimal("0.00"), Decimal("0.00"))
    assert f["mesada"] == Decimal("500.00")
    assert f["queda"] == Decimal("500.00")
    assert not AllowanceLedger.objects.for_household(hogar).exists()

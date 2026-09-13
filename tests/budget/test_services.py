"""La cascada aplicada a datos reales, y el libro mayor de la mesada."""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services
from apps.budget.engine.cascade import ALLOWANCE, FIXED, GOAL, REMAINDER
from apps.budget.models import AllowanceLedger, GoalContribution, MonthlyAllocation
from apps.households.services import crear_hogar
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory
from tests.factories_budget import (
    AllocationRuleFactory,
    BudgetMonthFactory,
    CategoryFactory,
    GoalFactory,
    TransactionFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar_con_cascada():
    """El ejemplo canónico del §4.5.2: ahorro fijo de $600, mesada el resto."""
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=2)
    otra = MembershipFactory(household=hogar)
    meta = GoalFactory(household=hogar, target_amount=Decimal("10000.00"))
    AllocationRuleFactory(
        household=hogar, order=1, target_type=GOAL, target_goal=meta,
        method=FIXED, amount=Decimal("600.00"),
    )
    AllocationRuleFactory(
        household=hogar, order=2, target_type=ALLOWANCE, method=REMAINDER,
        target_goal=None,
    )
    return hogar


def test_planificar_escribe_las_asignaciones_y_las_mesadas(hogar_con_cascada):
    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)

    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))

    assert MonthlyAllocation.objects.for_household(hogar_con_cascada).count() == 3
    mesadas = AllowanceLedger.objects.for_household(hogar_con_cascada).filter(budget_month=mes)
    assert [m.granted for m in mesadas.order_by("member_id")] == [
        Decimal("100.00"), Decimal("100.00")
    ]


def test_cada_miembro_sabe_su_mesada_desde_el_dia_uno(hogar_con_cascada):
    """§13.5: cada uno sabe desde el día 1 cuánta mesada tiene."""
    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))

    membresia = hogar_con_cascada.active_memberships().first()
    assert services.mesada_de(membresia, mes).saldo() == Decimal("100.00")


def test_planificar_dos_veces_no_duplica(hogar_con_cascada):
    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))
    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))

    assert MonthlyAllocation.objects.for_household(hogar_con_cascada).count() == 3


def test_un_sobrante_negativo_no_genera_mesada(hogar_con_cascada):
    """§9."""
    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)

    services.planificar_mes(hogar_con_cascada, mes, Decimal("-100.00"))

    assert MonthlyAllocation.objects.for_household(hogar_con_cascada).count() == 0
    assert AllowanceLedger.objects.for_household(hogar_con_cascada).count() == 0


def test_planificar_dos_veces_no_duplica_las_mesadas():
    hogar = HouseholdFactory()
    MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    AllocationRuleFactory(
        household=hogar, order=1, target_type="allowance",
        method="fixed", amount=Decimal("100.00"),
    )

    services.planificar_mes(hogar, mes, Decimal("500.00"))
    services.planificar_mes(hogar, mes, Decimal("500.00"))

    assert MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes).count() == 1
    assert AllowanceLedger.objects.for_household(hogar).filter(budget_month=mes).count() == 1


@pytest.mark.django_db(transaction=True)
def test_la_base_impide_dos_repartos_de_la_misma_regla_y_miembro():
    """La barrera de verdad no es el exists(): es el esquema."""
    from django.db.utils import IntegrityError

    hogar = HouseholdFactory()
    miembro = MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    regla = AllocationRuleFactory(household=hogar, order=1)

    MonthlyAllocation.unscoped.create(
        household=hogar, budget_month=mes, rule=regla,
        member=miembro, planned_amount=Decimal("100.00"),
    )
    with pytest.raises(IntegrityError):
        MonthlyAllocation.unscoped.create(
            household=hogar, budget_month=mes, rule=regla,
            member=miembro, planned_amount=Decimal("100.00"),
        )


@pytest.mark.django_db(transaction=True)
def test_la_base_impide_dos_repartos_de_la_misma_regla_sin_miembro():
    """Dos NULL no chocan en Postgres: hace falta la segunda constraint parcial."""
    from django.db.utils import IntegrityError

    hogar = HouseholdFactory()
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    regla = AllocationRuleFactory(household=hogar, order=1)

    MonthlyAllocation.unscoped.create(
        household=hogar, budget_month=mes, rule=regla,
        member=None, planned_amount=Decimal("100.00"),
    )
    with pytest.raises(IntegrityError):
        MonthlyAllocation.unscoped.create(
            household=hogar, budget_month=mes, rule=regla,
            member=None, planned_amount=Decimal("100.00"),
        )


def test_el_faltante_ajusta_la_mesada_del_mes_siguiente(hogar_con_cascada):
    """§13.6, el ejemplo literal del §4.5.3: proyectado $800, real $720. El
    ahorro conserva sus $600; las mesadas de octubre bajan $40 cada una."""
    septiembre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    octubre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=10)
    services.planificar_mes(hogar_con_cascada, septiembre, Decimal("800.00"))

    services.aplicar_cascada_al_cierre(septiembre, Decimal("720.00"))

    ahorro = MonthlyAllocation.objects.for_household(hogar_con_cascada).get(
        budget_month=septiembre, member__isnull=True
    )
    assert ahorro.actual_amount == Decimal("600.00")

    ajustes = AllowanceLedger.objects.for_household(hogar_con_cascada).filter(
        budget_month=octubre
    )
    assert [a.adjustment for a in ajustes.order_by("member_id")] == [
        Decimal("-40.00"), Decimal("-40.00")
    ]


def test_la_mesada_ya_asignada_no_se_reduce_dentro_del_mes(hogar_con_cascada):
    """§9: de nada sirve enterarse el día 30 de que tenías $100 para gastar."""
    septiembre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=10)
    services.planificar_mes(hogar_con_cascada, septiembre, Decimal("800.00"))

    services.aplicar_cascada_al_cierre(septiembre, Decimal("720.00"))

    mesadas = AllowanceLedger.objects.for_household(hogar_con_cascada).filter(
        budget_month=septiembre
    )
    assert all(m.granted == Decimal("100.00") for m in mesadas)


def test_lo_gastado_con_ambito_personal_baja_la_mesada(hogar_con_cascada):
    septiembre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, septiembre, Decimal("800.00"))
    membresia = hogar_con_cascada.active_memberships().order_by("pk").first()
    TransactionFactory(
        household=hogar_con_cascada, budget_month=septiembre, member=membresia,
        scope="personal", amount=Decimal("30.00"), date=date(2026, 9, 5),
        category=CategoryFactory(household=hogar_con_cascada),
    )

    assert services.gasto_personal_del_mes(membresia, septiembre) == Decimal("30.00")


def test_un_gasto_del_hogar_no_baja_la_mesada(hogar_con_cascada):
    """§4.5.5: entretenimiento familiar ≠ mesada personal. Confundirlas es lo
    que hace que las parejas discutan por dinero."""
    septiembre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, septiembre, Decimal("800.00"))
    membresia = hogar_con_cascada.active_memberships().order_by("pk").first()
    TransactionFactory(
        household=hogar_con_cascada, budget_month=septiembre, member=membresia,
        scope="household", amount=Decimal("30.00"), date=date(2026, 9, 5),
        category=CategoryFactory(household=hogar_con_cascada),
    )

    assert services.gasto_personal_del_mes(membresia, septiembre) == Decimal("0.00")


def test_la_cascada_aporta_a_la_meta(hogar_con_cascada):
    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))
    services.aplicar_cascada_al_cierre(mes, Decimal("800.00"))

    aporte = GoalContribution.objects.for_household(hogar_con_cascada).get()
    assert aporte.amount == Decimal("600.00")
    assert aporte.origen == "cascade"
    assert aporte.budget_month == mes


@pytest.mark.django_db
def test_el_aporte_de_la_cascada_no_se_atribuye_a_nadie():
    """Un ahorro del hogar no es de quien tenga el pk mas bajo."""
    hogar = HouseholdFactory()
    MembershipFactory(household=hogar)
    MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    meta = GoalFactory(household=hogar)
    AllocationRuleFactory(
        household=hogar, order=1, target_type="goal", target_goal=meta,
        method="fixed", amount=Decimal("200.00"),
    )
    services.planificar_mes(hogar, mes, Decimal("500.00"))

    services.aplicar_cascada_al_cierre(mes, Decimal("500.00"))

    aporte = GoalContribution.objects.for_household(hogar).get(origen="cascade")
    assert aporte.member is None


@pytest.mark.django_db
def test_la_cascada_no_revienta_si_no_hay_membresias_activas():
    hogar = HouseholdFactory()
    miembro = MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    meta = GoalFactory(household=hogar)
    AllocationRuleFactory(
        household=hogar, order=1, target_type="goal", target_goal=meta,
        method="fixed", amount=Decimal("200.00"),
    )
    services.planificar_mes(hogar, mes, Decimal("500.00"))
    miembro.is_active = False
    miembro.save()

    services.aplicar_cascada_al_cierre(mes, Decimal("500.00"))

    assert GoalContribution.objects.for_household(hogar).filter(origen="cascade").count() == 1

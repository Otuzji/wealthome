"""Hogar y Personal no se mezclan en las cifras (decision del 2026-10-18).

Lo personal sale de la mesada de cada miembro: si el cierre del hogar lo
contara tambien, el mismo dinero saldria dos veces —una como mesada repartida
y otra como gasto—. Por eso el cierre, el sobrante que reparte la cascada, el
Summary y el efectivo del hogar cuentan solo lo del hogar; y Summary y
Balance en Personal ensenan solo lo de quien mira.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget import services, services_balance, services_summary
from apps.budget.engine.periodicity import MONTHLY
from apps.budget.models import BalanceItem, BudgetLine
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import (
    CategoryFactory,
    ExpenseRuleFactory,
    GoalContributionFactory,
    GoalFactory,
    IncomeSourceFactory,
    TransactionFactory,
)

pytestmark = pytest.mark.django_db

HOY = date(2026, 1, 10)


@pytest.fixture
def mezcla():
    """Un mes con lo del hogar (3000 de ingreso, 1800 de gasto previstos; 500
    gastados) y lo personal de A (300 previstos, 250 gastados)."""
    a = UserFactory()
    hogar = crear_hogar(a, "Family Test", family_size=2)
    mem_a = Membership.objects.get(household=hogar, user=a)
    mem_b = MembershipFactory(household=hogar, can_view_reports=True)
    IncomeSourceFactory(household=hogar, amount=Decimal("3000.00"), periodicity=MONTHLY,
                        effective_from=date(2026, 1, 1))
    ExpenseRuleFactory(household=hogar, amount=Decimal("1800.00"), periodicity=MONTHLY,
                       effective_from=date(2026, 1, 1))
    mes = services.obtener_mes(hogar, 2026, 1, hoy=HOY)
    del_hogar = mes.lineas.get(kind="expense")
    TransactionFactory(household=hogar, budget_month=mes, amount=Decimal("500.00"),
                       date=date(2026, 1, 20), category=del_hogar.category,
                       budget_line=del_hogar, member=mem_a)

    personal = CategoryFactory(household=hogar, name="CATEGORIA-PERSONAL-A",
                               slug="personal-a", kind="expense")
    linea = BudgetLine(household=hogar, budget_month=mes, category=personal, kind="expense",
                       planned_amount=Decimal("300.00"), is_exceptional=True,
                       scope="personal", owner=mem_a, note="PARTIDA-PERSONAL-A")
    linea.save()
    TransactionFactory(household=hogar, budget_month=mes, amount=Decimal("250.00"),
                       date=date(2026, 1, 21), category=personal, budget_line=linea,
                       member=mem_a, scope="personal")
    return {"hogar": hogar, "a": mem_a, "b": mem_b, "mes": mes, "personal": personal}


# --- el hogar cuenta solo lo del hogar -------------------------------------------


def test_el_cierre_no_cuenta_lo_personal(mezcla):
    cierre = services.cerrar_mes(mezcla["mes"])

    assert cierre.ingresos_presupuestados == Decimal("3000.00")
    assert cierre.egresos_presupuestados == Decimal("1800.00")
    assert cierre.egresos_reales == Decimal("500.00")
    assert str(mezcla["personal"].pk) not in cierre.varianza_por_categoria


def test_el_cierre_sigue_bajando_la_mesada_con_lo_personal(mezcla):
    """Lo personal sale del cierre del hogar, pero no de la mesada de A."""
    services.mesada_de(mezcla["a"], mezcla["mes"])  # el libro existe al planificar
    services.cerrar_mes(mezcla["mes"])
    libro = services.mesada_de(mezcla["a"], mezcla["mes"])
    assert libro.spent == Decimal("250.00")


def test_el_sobrante_que_reparte_la_cascada_no_cuenta_lo_personal(mezcla):
    totales = services.totales_del_mes(mezcla["mes"])
    assert totales.total_egresos == Decimal("1800.00")
    assert totales.sobrante == Decimal("1200.00")


def test_el_summary_del_hogar_no_ensena_categorias_personales(mezcla):
    services.cerrar_mes(mezcla["mes"])
    resumen = services_summary.resumen_de_cierres(mezcla["hogar"])
    ids = {c["id"] for c in resumen["series"]["categorias"]["lista"]}
    assert str(mezcla["personal"].pk) not in ids


def test_el_efectivo_del_hogar_no_cuenta_lo_personal(mezcla):
    ingreso = mezcla["mes"].lineas.get(kind="income")
    TransactionFactory(household=mezcla["hogar"], budget_month=mezcla["mes"],
                       amount=Decimal("1000.00"), date=date(2026, 1, 5),
                       category=ingreso.category, budget_line=ingreso, member=mezcla["a"])
    assert services_balance.efectivo_del_mes_abierto(mezcla["hogar"]) == Decimal("500.00")


# --- Summary en Personal: solo lo de quien mira ------------------------------------


def test_el_summary_personal_ensena_lo_de_a(client, mezcla):
    services.cerrar_mes(mezcla["mes"])
    client.force_login(mezcla["a"].user)

    html = client.get(reverse("budget:summary", args=["personal"])).content.decode()

    assert "250.00" in html
    assert "CATEGORIA-PERSONAL-A" in html
    assert "3,000.00" not in html, "los ingresos del hogar no son de A"


def test_el_summary_personal_de_b_no_ensena_lo_de_a(client, mezcla):
    services.cerrar_mes(mezcla["mes"])
    client.force_login(mezcla["b"].user)

    html = client.get(reverse("budget:summary", args=["personal"])).content.decode()

    assert "CATEGORIA-PERSONAL-A" not in html
    assert "250.00" not in html


def test_el_summary_del_hogar_no_ensena_lo_personal(client, mezcla):
    services.cerrar_mes(mezcla["mes"])
    client.force_login(mezcla["a"].user)

    html = client.get(reverse("budget:summary", args=["household"])).content.decode()

    assert "CATEGORIA-PERSONAL-A" not in html


def test_resumen_personal_por_mes(mezcla):
    services.cerrar_mes(mezcla["mes"])
    resumen = services_summary.resumen_personal(mezcla["hogar"], mezcla["a"])
    (fila,) = resumen["filas"]
    assert fila["gastos"] == Decimal("250.00")
    assert fila["balance"] == fila["ingresos"] - Decimal("250.00")
    ids = {c["id"] for c in resumen["series"]["categorias"]["lista"]}
    assert ids == {str(mezcla["personal"].pk)}


# --- Balance en Personal: solo lo de quien mira -----------------------------------


@pytest.fixture
def con_balance(mezcla):
    hogar = mezcla["hogar"]
    item = BalanceItem(household=hogar, name="CASA-DEL-HOGAR", group="property",
                       amount=Decimal("250000.00"))
    item.full_clean()
    item.save()
    meta_a = GoalFactory(household=hogar, name="META-A", scope="personal", owner=mezcla["a"],
                         target_amount=Decimal("1000.00"))
    GoalContributionFactory(household=hogar, goal=meta_a, amount=Decimal("123.00"),
                            date=date(2026, 1, 12))
    return mezcla


def test_el_balance_personal_no_ensena_lo_del_hogar(client, con_balance):
    client.force_login(con_balance["a"].user)
    html = client.get(reverse("budget:balance", args=["personal"])).content.decode()

    assert "CASA-DEL-HOGAR" not in html
    assert "250,000.00" not in html
    assert "123.00" in html, "el ahorro personal de A"


def test_el_balance_personal_de_b_no_ensena_el_ahorro_de_a(client, con_balance):
    client.force_login(con_balance["b"].user)
    html = client.get(reverse("budget:balance", args=["personal"])).content.decode()

    assert "123.00" not in html


def test_el_balance_del_hogar_sigue_con_sus_partidas(client, con_balance):
    client.force_login(con_balance["a"].user)
    html = client.get(reverse("budget:balance", args=["household"])).content.decode()

    assert "CASA-DEL-HOGAR" in html


def test_el_efectivo_personal_es_lo_que_queda_de_mesada(con_balance):
    mes = con_balance["mes"]
    libro = services.mesada_de(con_balance["a"], mes)
    libro.granted = Decimal("400.00")
    libro.save(update_fields=["granted"])

    efectivo = services_balance.efectivo_personal(con_balance["hogar"], con_balance["a"])

    assert efectivo == Decimal("150.00")  # 400 de mesada - 250 gastados

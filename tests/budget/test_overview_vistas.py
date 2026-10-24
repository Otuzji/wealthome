"""La pantalla Overview: el mes de un vistazo, solo lectura.

Sus cifras salen de las mismas funciones que This month; aqui se comprueba que
las dos pantallas cuadran, que el ambito personal no filtra lo de otro miembro
y que los casos de borde (sin presupuesto, mes cerrado, hogar sin escritura)
se ensenan sin escribir nada.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget.models import BudgetMonth
from tests.budget.test_cash_float import mes_con_dinero  # noqa: F401
from tests.budget.test_views import _miembro, admin_con_hogar  # noqa: F401
from tests.factories_budget import (
    BudgetLineFactory, CategoryFactory, IncomeSourceFactory, TransactionFactory,
)

pytestmark = pytest.mark.django_db


def test_el_overview_del_hogar_cuadra_con_this_month(client, mes_con_dinero):
    r = client.get(reverse("budget:overview", args=["household"]))
    m = client.get(reverse("budget:mes", args=["household"]))

    assert r.status_code == 200
    assert r.context["real"] == m.context["totales"]
    assert r.context["forecast"]["ingresos"] == m.context["totales"]["ingresos"]
    assert r.context["alerta"] is not None
    html = r.content.decode()
    assert 'id="overview-alerta"' in html and "No upcoming income planned" in html


def test_sin_presupuesto_invita_a_crearlo(client, admin_con_hogar):
    user, _hogar = admin_con_hogar
    client.force_login(user)

    r = client.get(reverse("budget:overview", args=["household"]))

    assert r.context["sin_presupuesto"] is True
    assert reverse("budget:configurar") in r.content.decode()


def test_sin_presupuesto_y_sin_permiso_pide_al_dueno(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    r = client.get(reverse("budget:overview", args=["household"]))
    html = r.content.decode()

    assert r.context["sin_presupuesto"] is True
    assert "Ask the household owner to set up the budget." in html
    assert reverse("budget:configurar") not in html


def test_personal_no_tiene_alerta_y_ensena_la_mesada(client, mes_con_dinero):
    r = client.get(reverse("budget:overview", args=["personal"]))

    assert r.context["alerta"] is None and "mesada" in r.context["forecast"]


def test_personal_no_cuenta_lo_de_otro_miembro(client, mes_con_dinero):
    user, hogar, mes, otto, diana = mes_con_dinero
    sale = mes.lineas.filter(kind="expense").first().category
    # Diana: una linea personal de 500 y un gasto personal de 999.
    BudgetLineFactory(household=hogar, budget_month=mes, category=sale, kind="expense",
                      planned_amount=Decimal("500.00"), scope="personal", owner=diana)
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=diana,
                       scope="personal", amount=Decimal("999.00"), date=timezone.localdate())

    r = client.get(reverse("budget:overview", args=["personal"]))   # sesion de Otto

    assert r.context["real"]["egresos_real"] == Decimal("0.00")
    assert r.context["forecast"]["egresos"] == Decimal("0.00")
    h = client.get(reverse("budget:overview", args=["household"]))
    # Lo del hogar: 500 pagados del alquiler + 500 sueltos, sin los 999 de Diana.
    assert h.context["real"]["egresos_real"] == Decimal("1000.00")


def test_un_exceso_se_ensena_con_su_enlace_al_mes(client, mes_con_dinero):
    _user, hogar, mes, otto, _diana = mes_con_dinero
    cafe = CategoryFactory(household=hogar, slug="cafe", kind="expense")
    linea = BudgetLineFactory(household=hogar, budget_month=mes, category=cafe,
                              kind="expense", planned_amount=Decimal("100.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=cafe, member=otto,
                       amount=Decimal("120.00"), date=timezone.localdate(), budget_line=linea)

    r = client.get(reverse("budget:overview", args=["household"]))
    html = r.content.decode()

    assert [d.diferencia for d in r.context["desvios"]] == [Decimal("20.00")]
    assert "over plan" in html and "$20.00" in html
    assert reverse("budget:mes", args=["household"]) + "?orden=categoria" in html


def test_un_mes_cerrado_se_ensena_sin_alerta(client, mes_con_dinero):
    _user, hogar, mes, _otto, _diana = mes_con_dinero
    BudgetMonth.objects.for_household(hogar).filter(pk=mes.pk).update(status="closed")

    r = client.get(reverse("budget:overview", args=["household"]))
    html = r.content.decode()

    assert r.context["cerrado"] is True and r.context["alerta"] is None
    assert "is closed." in html
    anio, numero = (mes.year + 1, 1) if mes.month == 12 else (mes.year, mes.month + 1)
    assert reverse("budget:planificar_mes", args=["household", anio, numero, 1]) in html


def test_un_hogar_sin_escritura_ve_la_proyeccion(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    IncomeSourceFactory(household=hogar, owner=hogar.active_memberships().get(user=user),
                        effective_from=timezone.localdate().replace(day=1))
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    r = client.get(reverse("budget:overview", args=["household"]))

    assert r.status_code == 200 and r.context["es_proyeccion"] is True
    assert r.context["sin_presupuesto"] is False
    assert r.context["alerta"] is None
    assert r.context["forecast"]["ingresos"] == Decimal("3000.00")
    assert not BudgetMonth.objects.for_household(hogar).exists()


def test_un_ambito_inventado_es_404(client, admin_con_hogar):
    user, _hogar = admin_con_hogar
    client.force_login(user)

    assert client.get("/budget/inventado/").status_code == 404

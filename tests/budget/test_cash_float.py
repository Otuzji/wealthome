"""Cash Float: el dinero que hay en mano y a que esta destinado.

"Left over" pasa a llamarse Cash Float. En This month, una tarjeta a todo el
ancho lo desglosa: lo que falta pagar del plan (Pending Expenses) y, de lo
que queda, lo que las reglas de reparto mandan a ahorro y a la mesada de cada
miembro — en vivo, con cada registro, no del plan confirmado.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget.engine import cascade as motor_cascade
from apps.households.models import Membership
from tests.budget.test_views import admin_con_hogar  # noqa: F401
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import (
    AllocationRuleFactory, BudgetLineFactory, BudgetMonthFactory, CategoryFactory,
    GoalFactory, TransactionFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def mes_con_dinero(client, admin_con_hogar):
    """4000 en mano, 3000 por pagar, y reglas: 500 fijos a una meta y el resto
    a la mesada a partes iguales entre Otto y Diana."""
    user, hogar = admin_con_hogar
    user.display_name = "Otto"
    user.save()
    diana = MembershipFactory(household=hogar, role=Membership.MEMBER,
                              user=UserFactory(display_name="Diana"))
    client.force_login(user)
    hoy = timezone.localdate()
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    entra = CategoryFactory(household=hogar, slug="lo-que-entra", kind="income")
    sale = CategoryFactory(household=hogar, slug="lo-que-sale", kind="expense")
    otto = hogar.active_memberships().get(user=user)
    BudgetLineFactory(household=hogar, budget_month=mes, category=entra,
                      kind="income", planned_amount=Decimal("5000.00"))
    alquiler = BudgetLineFactory(household=hogar, budget_month=mes, category=sale,
                                 kind="expense", planned_amount=Decimal("2000.00"))
    BudgetLineFactory(household=hogar, budget_month=mes, category=sale,
                      kind="expense", planned_amount=Decimal("1500.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=entra,
                       member=otto, amount=Decimal("5000.00"), date=hoy)
    # 500 pagados del alquiler: quedan 1500 + 1500 = 3000 por pagar.
    TransactionFactory(household=hogar, budget_month=mes, category=sale,
                       member=otto, amount=Decimal("500.00"), date=hoy, budget_line=alquiler)
    # Y un gasto fuera del plan, para que Cash Float sea 4000 y no 4500.
    TransactionFactory(household=hogar, budget_month=mes, category=sale,
                       member=otto, amount=Decimal("500.00"), date=hoy)
    meta = GoalFactory(household=hogar)
    AllocationRuleFactory(household=hogar, order=1, target_type=motor_cascade.GOAL,
                          target_goal=meta, method=motor_cascade.FIXED, amount=Decimal("500.00"))
    AllocationRuleFactory(household=hogar, order=2, target_type=motor_cascade.ALLOWANCE,
                          method=motor_cascade.REMAINDER, amount=None)
    return user, hogar, mes, otto, diana


def _this_month(client, ambito="household"):
    hoy = timezone.localdate()
    return client.get(reverse("budget:mes", args=[ambito, hoy.year, hoy.month]))


def test_la_tarjeta_desglosa_el_cash_float(client, mes_con_dinero):
    user, hogar, mes, otto, diana = mes_con_dinero

    respuesta = _this_month(client)
    flotante = respuesta.context["cash_float"]

    assert flotante["total"] == Decimal("4000.00")
    assert flotante["pendiente"] == Decimal("3000.00")
    assert flotante["ahorro"] == Decimal("500.00")
    assert flotante["mesadas"] == [("Otto", Decimal("250.00")), ("Diana", Decimal("250.00"))]
    assert flotante["mesada_total"] == Decimal("500.00")
    assert flotante["sin_asignar"] == Decimal("0.00")
    html = respuesta.content.decode()
    assert "Cash Float" in html and "Pending Expenses" in html
    assert "Otto" in html and "Diana" in html
    assert "Left over" not in html


def test_sin_margen_no_hay_ahorro_ni_mesada(client, mes_con_dinero):
    user, hogar, mes, otto, diana = mes_con_dinero
    sale = mes.lineas.filter(kind="expense").first().category
    # 1500 mas que salieron: Cash Float 2500, y faltan 3000 por pagar.
    TransactionFactory(household=hogar, budget_month=mes, category=sale,
                       member=otto, amount=Decimal("1500.00"), date=timezone.localdate())

    flotante = _this_month(client).context["cash_float"]

    assert flotante["total"] == Decimal("2500.00")
    assert flotante["pendiente"] == Decimal("3000.00")
    assert flotante["ahorro"] == Decimal("0.00")
    assert flotante["mesadas"] == [("Otto", Decimal("0.00")), ("Diana", Decimal("0.00"))]
    assert flotante["falta"] is True


def test_lo_que_las_reglas_no_agotan_queda_sin_asignar(client, mes_con_dinero):
    from apps.budget.models import AllocationRule

    user, hogar, mes, otto, diana = mes_con_dinero
    AllocationRule.objects.for_household(hogar).filter(order=2).delete()

    flotante = _this_month(client).context["cash_float"]

    assert flotante["ahorro"] == Decimal("500.00")
    assert flotante["mesadas"] == []
    assert flotante["sin_asignar"] == Decimal("500.00")


def test_la_tarjeta_es_del_hogar_y_no_del_ambito_personal(client, mes_con_dinero):
    respuesta = _this_month(client, "personal")

    assert "cash_float" not in respuesta.context
    assert "Pending Expenses" not in respuesta.content.decode()


def test_el_mes_proyectado_no_tiene_cash_float(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)
    hoy = timezone.localdate()
    anio, numero = (hoy.year + 1, 1)

    respuesta = client.get(reverse("budget:mes", args=["household", anio, numero]))

    assert respuesta.context["es_proyeccion"]
    assert "Pending Expenses" not in respuesta.content.decode()
    assert "Cash Float" in respuesta.content.decode()   # la cifra, renombrada


def test_left_over_ya_no_existe_en_las_pantallas(client, mes_con_dinero):
    overview = client.get(reverse("budget:overview", args=["household"])).content.decode()

    assert "Cash Float" in overview and "Left over" not in overview

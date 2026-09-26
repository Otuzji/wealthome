"""Move to next month desde This month: un icono en los gastos registrados
que no estaban planificados, y en nada mas. Solo por POST, con el permiso de
registrar, y de vuelta a This month del mes de origen con un aviso que dice a
que mes se fue.

Lo planificado se corrige en Plan the month: por eso las partidas de la
tarjeta Planned no llevan este boton ni tienen ruta propia.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.budget import services
from apps.budget.models import BudgetMonth, Transaction
from apps.households.models import Membership
from tests.budget.test_registrar_contra_el_plan import _pago, hogar_con_plan  # noqa: F401
from tests.factories import MembershipFactory
from tests.factories_budget import CategoryFactory

pytestmark = pytest.mark.django_db


def _mes_siguiente_de(mes):
    anio, numero = services.mes_siguiente(mes.year, mes.month)
    return BudgetMonth.objects.for_household(mes.household).filter(year=anio, month=numero).first()


def _avisos(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


@pytest.fixture
def con_registros(client, hogar_con_plan):
    """Un gasto "not planned" de 38.20, y un pago del alquiler contra el plan."""
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    categoria = CategoryFactory(household=hogar, slug="farmacia", kind="expense", name="Farmacia")
    client.post(reverse("budget:registrar"), _pago(
        budget_line="", category=categoria.pk, name="Antibiotico", amount="38.20",
    ))
    suelto = Transaction.objects.for_household(hogar).get()
    alquiler = mes.lineas.get(kind="expense", is_exceptional=False)
    client.post(reverse("budget:registrar"), _pago(budget_line=alquiler.pk))
    del_plan = Transaction.objects.for_household(hogar).exclude(pk=suelto.pk).get()
    return admin, hogar, mes, suelto, del_plan


# --- lo planificado ya no se mueve ------------------------------------------


def test_las_partidas_del_plan_no_tienen_ruta_para_moverse():
    with pytest.raises(NoReverseMatch):
        reverse("budget:linea_posponer", args=["household", 1])


def test_this_month_no_ofrece_mover_ninguna_partida(client, con_registros):
    admin, hogar, mes, suelto, del_plan = con_registros

    html = client.get(reverse("budget:mes", args=["household"])).content.decode()

    # Un solo boton en toda la pantalla: el del gasto no planificado.
    assert html.count("Move to next month") == 2   # aria-label y title del mismo boton
    assert reverse("budget:registro_posponer", args=[suelto.pk]) in html


def test_un_pago_contra_el_plan_no_ofrece_moverse(client, con_registros):
    admin, hogar, mes, suelto, del_plan = con_registros

    html = client.get(reverse("budget:mes", args=["household"])).content.decode()

    assert reverse("budget:registro_posponer", args=[del_plan.pk]) not in html


def test_mover_un_pago_contra_el_plan_avisa_y_no_hace_nada(client, con_registros):
    admin, hogar, mes, suelto, del_plan = con_registros

    respuesta = client.post(reverse("budget:registro_posponer", args=[del_plan.pk]))

    assert respuesta.status_code == 302
    assert _mes_siguiente_de(mes) is None
    assert _avisos(respuesta) == [
        "Only an expense that was not planned can be moved. Change the plan in Plan the month."
    ]


# --- el gasto no planificado ------------------------------------------------


def test_mover_un_gasto_suelto_vuelve_a_this_month_con_aviso(client, con_registros):
    admin, hogar, mes, suelto, del_plan = con_registros

    respuesta = client.post(reverse("budget:registro_posponer", args=[suelto.pk]))

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("budget:mes", args=["household", mes.year, mes.month])
    siguiente = _mes_siguiente_de(mes)
    suelto.refresh_from_db()
    assert suelto.budget_month_id == siguiente.pk
    assert suelto.budget_line.budget_month_id == siguiente.pk
    assert suelto.amount == Decimal("38.20")
    nombre = date(siguiente.year, siguiente.month, 1).strftime("%B")
    assert _avisos(respuesta) == [f"Moved to {nombre}."]


def test_mover_solo_por_post(client, con_registros):
    admin, hogar, mes, suelto, del_plan = con_registros

    assert client.get(reverse("budget:registro_posponer", args=[suelto.pk])).status_code == 405
    assert _mes_siguiente_de(mes) is None


def test_un_mes_cerrado_no_ofrece_mover_ni_deja(client, con_registros):
    admin, hogar, mes, suelto, del_plan = con_registros
    mes.status = "closed"
    mes.save()

    html = client.get(reverse("budget:mes", args=["household", mes.year, mes.month])).content.decode()
    respuesta = client.post(reverse("budget:registro_posponer", args=[suelto.pk]))

    assert reverse("budget:registro_posponer", args=[suelto.pk]) not in html
    assert respuesta.status_code == 302
    assert _mes_siguiente_de(mes) is None
    assert _avisos(respuesta) == ["This month is already closed."]


def test_el_registro_de_otro_hogar_es_un_404(client, con_registros):
    from apps.households.services import crear_hogar
    from tests.factories import UserFactory

    admin, hogar, mes, suelto, del_plan = con_registros
    ajeno = UserFactory()
    crear_hogar(ajeno, "Family García", family_size=2)
    client.force_login(ajeno)

    assert client.post(reverse("budget:registro_posponer", args=[suelto.pk])).status_code == 404
    assert Transaction.unscoped.get(pk=suelto.pk).budget_month_id == mes.pk


def test_sin_can_add_transactions_no_se_mueve(client, con_registros):
    admin, hogar, mes, suelto, del_plan = con_registros
    mirón = MembershipFactory(household=hogar, role=Membership.MEMBER, can_view_budget=True,
                              can_add_transactions=False)
    client.force_login(mirón.user)

    assert client.post(reverse("budget:registro_posponer", args=[suelto.pk])).status_code == 403

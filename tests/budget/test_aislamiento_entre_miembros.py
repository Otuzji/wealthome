"""Lo personal de un miembro no lo ve ni lo toca el otro miembro del MISMO hogar.

test_aislamiento.py cubre la frontera entre hogares. Esta es la otra: dentro de
un hogar, un pk de un registro o una partida personal ajena tiene que ser un
404 identico al de un pk inventado, tambien escribiendo la URL a mano.
"""
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget import services
from apps.budget.models import BudgetLine, Transaction
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import CategoryFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def pareja():
    """A (admin) y B (miembro con permiso de editar el presupuesto), y el mes
    corriente con un gasto y una partida personales de A."""
    a = UserFactory()
    hogar = crear_hogar(a, "Family Test", family_size=2)
    mem_a = Membership.objects.get(household=hogar, user=a)
    mem_b = MembershipFactory(household=hogar, can_edit_budget=True)

    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    categoria = CategoryFactory(household=hogar, slug="personal-a", kind="expense")
    linea = BudgetLine(
        household=hogar, budget_month=mes, category=categoria, kind="expense",
        planned_amount=Decimal("77.00"), is_exceptional=True, no_planeada=True,
        scope="personal", owner=mem_a, note="REGALO-SECRETO-DE-A",
    )
    linea.save()
    tx = Transaction(
        household=hogar, budget_month=mes, category=categoria, budget_line=linea,
        amount=Decimal("77.00"), date=hoy, member=mem_a, scope="personal",
        note="NOTA-SECRETA-DE-A",
    )
    tx.save()
    return {"hogar": hogar, "a": mem_a, "b": mem_b, "mes": mes, "linea": linea, "tx": tx}


def test_b_no_ve_el_gasto_personal_de_a(client, pareja):
    client.force_login(pareja["b"].user)
    respuesta = client.get(reverse("budget:registro_editar", args=[pareja["tx"].pk]))
    assert respuesta.status_code == 404


def test_b_no_edita_el_gasto_personal_de_a(client, pareja):
    client.force_login(pareja["b"].user)
    respuesta = client.post(reverse("budget:registro_editar", args=[pareja["tx"].pk]),
                            {"amount": "1.00", "scope": "household"})
    assert respuesta.status_code == 404
    pareja["tx"].refresh_from_db()
    assert pareja["tx"].amount == Decimal("77.00")
    assert pareja["tx"].scope == "personal"


def test_b_no_borra_el_gasto_personal_de_a(client, pareja):
    client.force_login(pareja["b"].user)
    respuesta = client.post(reverse("budget:registro_borrar", args=[pareja["tx"].pk]))
    assert respuesta.status_code == 404
    assert Transaction.objects.for_household(pareja["hogar"]).filter(pk=pareja["tx"].pk).exists()


def test_b_no_pospone_el_gasto_personal_de_a(client, pareja):
    client.force_login(pareja["b"].user)
    respuesta = client.post(reverse("budget:registro_posponer", args=[pareja["tx"].pk]))
    assert respuesta.status_code == 404
    pareja["tx"].refresh_from_db()
    assert pareja["tx"].budget_month_id == pareja["mes"].pk


def test_a_si_ve_su_propio_gasto_personal(client, pareja):
    client.force_login(pareja["a"].user)
    respuesta = client.get(reverse("budget:registro_editar", args=[pareja["tx"].pk]))
    assert respuesta.status_code == 200


def test_b_no_quita_la_partida_personal_de_a(client, pareja):
    client.force_login(pareja["b"].user)
    for ambito in ("household", "personal"):
        respuesta = client.post(
            reverse("budget:linea_quitar", args=[ambito, pareja["linea"].pk])
        )
        assert respuesta.status_code == 404
    assert BudgetLine.objects.for_household(pareja["hogar"]).filter(pk=pareja["linea"].pk).exists()


@pytest.mark.parametrize("ambito", ["household", "personal"])
@pytest.mark.parametrize("paso", [1, 2])
def test_planificar_no_ensena_a_b_las_partidas_personales_de_a(client, pareja, ambito, paso):
    client.force_login(pareja["b"].user)
    mes = pareja["mes"]
    html = client.get(
        reverse("budget:planificar_mes", args=[ambito, mes.year, mes.month, paso])
    ).content.decode()
    assert "REGALO-SECRETO-DE-A" not in html


def test_planificar_personal_ensena_a_a_sus_partidas(client, pareja):
    client.force_login(pareja["a"].user)
    mes = pareja["mes"]
    html = client.get(
        reverse("budget:planificar_mes", args=["personal", mes.year, mes.month, 2])
    ).content.decode()
    assert "REGALO-SECRETO-DE-A" in html


def test_planificar_hogar_no_mezcla_las_partidas_personales(client, pareja):
    client.force_login(pareja["a"].user)
    mes = pareja["mes"]
    html = client.get(
        reverse("budget:planificar_mes", args=["household", mes.year, mes.month, 2])
    ).content.decode()
    assert "REGALO-SECRETO-DE-A" not in html

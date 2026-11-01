"""Hasta que un mes se cierra, el siguiente no empieza.

El 1 de noviembre, con octubre aun abierto, el Overview sigue en octubre y el
modal de registro ofrece lo que quedo pendiente de octubre: la lavanderia del
30 se registra en octubre, no en un noviembre que todavia no ha empezado.
Al cerrar octubre (a mano, o solo a los DIAS_PARA_EL_CIERRE_AUTOMATICO), el
mes activo pasa a ser el del calendario.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget import services
from apps.budget.models import DIAS_PARA_EL_CIERRE_AUTOMATICO, BudgetMonth, Transaction
from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import BudgetLineFactory, BudgetMonthFactory, CategoryFactory

pytestmark = pytest.mark.django_db

PRIMERO_DE_NOVIEMBRE = date(2026, 11, 1)


def _fijar_hoy(monkeypatch, dia):
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: dia)


@pytest.fixture
def octubre_abierto(monkeypatch):
    """Octubre abierto con la lavanderia del 30 sin pagar, y hoy 1 de noviembre."""
    _fijar_hoy(monkeypatch, PRIMERO_DE_NOVIEMBRE)
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=2)
    octubre = BudgetMonthFactory(household=hogar, year=2026, month=10)
    lavanderia = BudgetLineFactory(
        household=hogar, budget_month=octubre, kind="expense", is_exceptional=True,
        category=CategoryFactory(household=hogar, slug="lavanderia", kind="expense"),
        planned_amount=Decimal("35.00"), due_date=date(2026, 10, 30), note="Lavanderia",
    )
    return admin, hogar, octubre, lavanderia


def test_con_octubre_abierto_el_mes_activo_es_octubre(octubre_abierto):
    _admin, hogar, _octubre, _linea = octubre_abierto

    assert services.mes_activo(hogar, PRIMERO_DE_NOVIEMBRE) == (2026, 10)


def test_con_octubre_cerrado_el_mes_activo_es_noviembre(octubre_abierto):
    _admin, hogar, octubre, _linea = octubre_abierto
    services.cerrar_mes(octubre)

    assert services.mes_activo(hogar, PRIMERO_DE_NOVIEMBRE) == (2026, 11)


def test_pasado_el_plazo_octubre_se_cierra_solo_y_el_activo_es_noviembre(octubre_abierto):
    _admin, hogar, octubre, _linea = octubre_abierto
    vencido = date(2026, 10, 31) + timedelta(days=DIAS_PARA_EL_CIERRE_AUTOMATICO + 1)

    assert services.mes_activo(hogar, vencido) == (2026, 11)
    octubre.refresh_from_db()
    assert octubre.esta_cerrado


def test_el_mes_activo_no_fabrica_noviembre(octubre_abierto):
    _admin, hogar, _octubre, _linea = octubre_abierto

    services.mes_activo(hogar, PRIMERO_DE_NOVIEMBRE)

    assert not BudgetMonth.objects.for_household(hogar).filter(year=2026, month=11).exists()


def test_el_overview_sigue_en_octubre_hasta_cerrarlo(client, octubre_abierto):
    admin, hogar, octubre, _linea = octubre_abierto
    client.force_login(admin)

    r = client.get(reverse("budget:overview", args=["household"]))

    assert r.context["primer_dia"] == date(2026, 10, 1)
    assert r.context["cerrado"] is False
    assert r.context["real"]["egresos"] == Decimal("35.00")

    services.cerrar_mes(octubre)
    r = client.get(reverse("budget:overview", args=["household"]))

    assert r.context["primer_dia"] == date(2026, 11, 1)


def test_el_modal_ofrece_lo_pendiente_de_octubre_y_lo_registra_en_octubre(client, octubre_abierto):
    admin, hogar, octubre, lavanderia = octubre_abierto
    client.force_login(admin)

    html = client.get(reverse("budget:registrar"), HTTP_HX_REQUEST="true").content.decode()
    assert "Lavanderia" in html

    r = client.post(reverse("budget:registrar"), {
        "budget_line": lavanderia.pk, "amount": "35.00",
        "date": PRIMERO_DE_NOVIEMBRE.isoformat(),
        "payment_method": "debit", "scope": "household",
    })

    assert r.status_code == 302
    tx = Transaction.objects.for_household(hogar).get()
    assert tx.budget_month_id == octubre.pk and tx.budget_line_id == lavanderia.pk


def test_this_month_sin_fecha_es_octubre_mientras_este_abierto(client, octubre_abierto):
    admin, _hogar, _octubre, _linea = octubre_abierto
    client.force_login(admin)

    r = client.get(reverse("budget:mes", args=["household"]))

    assert (r.context["anio"], r.context["numero"]) == (2026, 10)
    assert r.context["se_puede_cerrar"] is True

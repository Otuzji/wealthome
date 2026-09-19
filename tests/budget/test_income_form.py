"""El formulario de ingreso ensena solo los importes del modo elegido.

Con los tres importes siempre a la vista nadie sabia cual contaba: un ingreso
`estimated` se guardo con `amount_min` y `amount_max` rellenos y `amount`
vacio. Los campos se muestran por modo (Alpine, en la plantilla generica) y
lo que no pertenece al modo no se guarda.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget.forms import IncomeSourceForm
from apps.budget.models import IncomeSource
from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import IncomeSourceFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_con_hogar():
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    return user, hogar


def _datos(hogar, **cambios):
    datos = {
        "owner": hogar.active_memberships().first().pk, "name": "Sueldo",
        "source_type": "salary", "amount_type": "fixed", "amount": "3000.00",
        "periodicity": "monthly", "effective_from": "2026-01-01", "scope": "household",
    }
    datos.update(cambios)
    return datos


def test_el_alta_de_ingreso_enseña_los_importes_por_modo(client, admin_con_hogar):
    admin, _ = admin_con_hogar
    client.force_login(admin)

    html = client.get(reverse("budget:ingreso_nuevo")).content.decode()

    assert 'x-model="modo"' in html                        # el <select> de "How much"
    assert "x-data=\"{ modo: '' }\"" in html               # sin modo elegido aun
    assert "x-show=\"['fixed', 'estimated'].includes(modo)\"" in html   # Amount
    assert html.count("x-show=\"['range'].includes(modo)\"") == 2      # At least / At most


def test_la_edicion_arranca_en_el_modo_guardado(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    fuente = IncomeSourceFactory(household=hogar, owner=hogar.active_memberships().first(),
                                 amount_type="range", amount=None,
                                 amount_min=Decimal("1000"), amount_max=Decimal("1500"))
    client.force_login(admin)

    html = client.get(reverse("budget:ingreso_editar", args=[fuente.pk])).content.decode()

    assert "x-data=\"{ modo: 'range' }\"" in html


def test_los_importes_ajenos_al_modo_no_se_guardan(admin_con_hogar):
    """Lo que el usuario no ve no puede quedarse guardado: un rango tecleado y
    luego cambiado a fijo dejaria un amount_min fantasma."""
    _, hogar = admin_con_hogar
    form = IncomeSourceForm(
        _datos(hogar, amount_type="fixed", amount="3000.00",
               amount_min="1000.00", amount_max="1500.00"),
        household=hogar,
    )

    assert form.is_valid(), form.errors
    fuente = form.save()
    assert fuente.amount == Decimal("3000.00")
    assert fuente.amount_min is None and fuente.amount_max is None


def test_un_rango_no_guarda_amount(admin_con_hogar):
    _, hogar = admin_con_hogar
    form = IncomeSourceForm(
        _datos(hogar, amount_type="range", amount="3000.00",
               amount_min="1000.00", amount_max="1500.00"),
        household=hogar,
    )

    assert form.is_valid(), form.errors
    assert form.save().amount is None


def test_un_fijo_sin_importe_lo_dice_en_el_campo(admin_con_hogar):
    _, hogar = admin_con_hogar
    form = IncomeSourceForm(_datos(hogar, amount=""), household=hogar)

    assert not form.is_valid()
    assert "amount" in form.errors


def test_la_ayuda_dice_que_el_importe_es_por_pago(client, admin_con_hogar):
    admin, _ = admin_con_hogar
    client.force_login(admin)

    html = client.get(reverse("budget:ingreso_nuevo")).content.decode()

    assert "Per payment" in html
    assert "first payment" in html


def test_los_demas_formularios_siguen_igual(client, admin_con_hogar):
    """La plantilla generica cambia para todos: un formulario sin modos no
    puede salir con x-data ni perder sus campos."""
    admin, _ = admin_con_hogar
    client.force_login(admin)

    html = client.get(reverse("budget:gasto_nuevo")).content.decode()

    assert "x-data" not in html.split("<form")[1].split(">")[0]
    assert 'name="amount"' in html and 'name="periodicity"' in html

"""Un ingreso tiene su propio formulario, separado del de gasto.

Antes los dos entraban por "Record a spend", con el sueldo mezclado entre
el alquiler y el parking en "What is it". El [+] ahora pregunta primero que
se quiere registrar, y cada formulario lista solo las lineas de su tipo, con
las categorias de su tipo. El de ingreso no pregunta donde ni con que se pago.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget.models import BudgetLine, Transaction
from tests.budget.test_registrar_contra_el_plan import _pago, hogar_con_plan  # noqa: F401
from tests.factories_budget import CategoryFactory

pytestmark = pytest.mark.django_db


def _cobro(**extra):
    datos = {"amount": "3000.00", "date": timezone.localdate().isoformat(), "scope": "household"}
    datos.update(extra)
    return datos


def test_el_formulario_de_ingreso_solo_lista_ingresos_y_no_pide_comercio(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)

    html = client.get(reverse("budget:registrar_ingreso")).content.decode()

    assert "Sueldo" in html and "Alquiler" not in html
    assert "Something not planned" in html
    assert 'name="merchant_name"' not in html
    assert 'name="payment_method"' not in html
    assert "Record an income" in html
    # Ni la ayuda del nombre habla de una tienda.
    assert "the store" not in html


def test_el_formulario_de_gasto_ya_no_lista_ingresos(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)

    html = client.get(reverse("budget:registrar")).content.decode()

    assert "Alquiler" in html and "Sueldo" not in html
    assert "Income received" not in html


def test_cobrar_un_ingreso_conserva_su_income_source(client, hogar_con_plan):
    """La media movil del §4.1 sigue teniendo de donde calcularse."""
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    sueldo = mes.lineas.get(kind="income")

    respuesta = client.post(reverse("budget:registrar_ingreso"), _cobro(budget_line=sueldo.pk))

    assert respuesta.status_code == 302
    tx = Transaction.objects.for_household(hogar).get()
    assert tx.income_source_id == sueldo.source_income_id
    assert tx.category.kind == "income"
    assert BudgetLine.objects.for_household(hogar).get(pk=sueldo.pk).estado == BudgetLine.PAGADA


def test_una_linea_de_gasto_no_entra_por_el_formulario_de_ingreso(client, hogar_con_plan):
    """Esconder la opcion no basta: un POST con el id no pasa por el navegador."""
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    alquiler = mes.lineas.get(kind="expense")
    sueldo = mes.lineas.get(kind="income")

    ingreso = client.post(reverse("budget:registrar_ingreso"), _cobro(budget_line=alquiler.pk))
    gasto = client.post(reverse("budget:registrar"), _pago(budget_line=sueldo.pk))

    assert ingreso.status_code == 200 and "budget_line" in ingreso.context["form"].errors
    assert gasto.status_code == 200 and "budget_line" in gasto.context["form"].errors
    assert not Transaction.objects.for_household(hogar).exists()


def test_un_ingreso_no_planeado_crea_una_partida_puntual_de_ingreso(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    categoria = CategoryFactory(household=hogar, slug="extra", kind="income")

    respuesta = client.post(reverse("budget:registrar_ingreso"), _cobro(
        budget_line="", category=categoria.pk, name="Devolucion", amount="120.00",
    ))

    assert respuesta.status_code == 302
    linea = Transaction.objects.for_household(hogar).get().budget_line
    assert linea.is_exceptional and linea.kind == "income" and linea.note == "Devolucion"
    assert linea.planned_amount == Decimal("120.00")


def test_cada_formulario_ofrece_solo_las_categorias_de_su_tipo(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    gasto = CategoryFactory(household=hogar, slug="farmacia", kind="expense", name="Farmacia")
    ingreso = CategoryFactory(household=hogar, slug="extra", kind="income", name="Extra")

    en_ingreso = client.get(reverse("budget:registrar_ingreso")).context["form"]
    en_gasto = client.get(reverse("budget:registrar")).context["form"]

    assert ingreso in en_ingreso.fields["category"].queryset
    assert {c.kind for c in en_ingreso.fields["category"].queryset} == {"income"}
    assert gasto in en_gasto.fields["category"].queryset
    assert {c.kind for c in en_gasto.fields["category"].queryset} == {"expense"}


def test_el_fragmento_htmx_trae_el_titulo_del_modal_fuera_de_banda(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)

    ingreso = client.get(reverse("budget:registrar_ingreso"), HTTP_HX_REQUEST="true").content.decode()
    gasto = client.get(reverse("budget:registrar"), HTTP_HX_REQUEST="true").content.decode()

    assert 'id="modal-gasto-titulo" hx-swap-oob="true"' in ingreso and "Record an income" in ingreso
    assert 'id="modal-gasto-titulo" hx-swap-oob="true"' in gasto and "Record a spend" in gasto
    assert "<html" not in ingreso


def test_el_fab_abre_un_selector_entre_gasto_e_ingreso(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)

    html = client.get(reverse("budget:mes", args=["household"])).content.decode()

    assert 'id="modal-gasto-selector"' in html
    assert f'hx-get="{reverse("budget:registrar")}"' in html
    assert f'hx-get="{reverse("budget:registrar_ingreso")}"' in html
    assert "What do you want to record?" in html

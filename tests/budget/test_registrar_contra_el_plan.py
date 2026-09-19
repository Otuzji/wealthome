"""Record a spend elige una linea del plan, no una categoria.

Antes pedia categoria e income source, dos cosas que a quien paga el alquiler
no le dicen nada. Ahora pregunta "What is it": las lineas del mes en curso
(la categoria y el income source salen de la linea), o "Something not
planned" — y entonces si pide categoria y nombre, y crea una partida puntual
ya pagada para que el plan refleje todo lo que salio.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget import services
from apps.budget.models import BudgetLine, Transaction
from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import CategoryFactory, ExpenseRuleFactory, IncomeSourceFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar_con_plan():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=2)
    hoy = timezone.localdate()
    IncomeSourceFactory(household=hogar, owner=hogar.active_memberships().first(),
                        name="Sueldo", amount=Decimal("3000.00"))
    ExpenseRuleFactory(household=hogar, name="Alquiler", amount=Decimal("1750.00"),
                       category=CategoryFactory(household=hogar, slug="mi-rent"))
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    return admin, hogar, mes


def _pago(**extra):
    datos = {"amount": "1750.00", "date": timezone.localdate().isoformat(),
             "payment_method": "debit", "scope": "household"}
    datos.update(extra)
    return datos


def test_el_formulario_pregunta_que_es_y_no_la_categoria(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)

    html = client.get(reverse("budget:registrar")).content.decode()

    assert 'name="income_source"' not in html
    assert 'name="budget_line"' in html
    assert "Alquiler" in html and "Sueldo" in html
    assert "Something not planned" in html
    # La categoria y el nombre solo aparecen al elegir "not planned".
    assert "x-show=\"linea === ''\"" in html
    # Y al elegir una linea, el importe se rellena con lo que falta por pagar.
    alquiler = mes.lineas.get(kind="expense")
    assert f"'{alquiler.pk}': '1750.00'" in html
    assert '@change="rellenar"' in html and 'x-ref="importe"' in html


def test_pagar_una_linea_la_liga_y_toma_su_categoria(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    alquiler = mes.lineas.get(kind="expense")

    respuesta = client.post(reverse("budget:registrar"), _pago(budget_line=alquiler.pk))

    assert respuesta.status_code == 302
    tx = Transaction.objects.for_household(hogar).get()
    assert tx.budget_line_id == alquiler.pk
    assert tx.category_id == alquiler.category_id
    assert BudgetLine.objects.for_household(hogar).get(pk=alquiler.pk).estado == BudgetLine.PAGADA


def test_cobrar_un_ingreso_conserva_su_income_source(client, hogar_con_plan):
    """La media movil del §4.1 sigue teniendo de donde calcularse."""
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    sueldo = mes.lineas.get(kind="income")

    client.post(reverse("budget:registrar"), _pago(budget_line=sueldo.pk, amount="3000.00"))

    tx = Transaction.objects.for_household(hogar).get()
    assert tx.income_source_id == sueldo.source_income_id
    assert tx.category.kind == "income"


def test_un_gasto_no_planeado_crea_una_partida_puntual_pagada(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    categoria = CategoryFactory(household=hogar, slug="farmacia", kind="expense")

    respuesta = client.post(reverse("budget:registrar"), _pago(
        budget_line="", category=categoria.pk, name="Antibiotico", amount="38.20",
    ))

    assert respuesta.status_code == 302
    tx = Transaction.objects.for_household(hogar).get()
    linea = tx.budget_line
    assert linea.is_exceptional and linea.note == "Antibiotico"
    assert linea.category_id == categoria.pk and linea.kind == "expense"
    assert linea.planned_amount == Decimal("38.20")
    assert linea.due_date == tx.date
    assert linea.estado == BudgetLine.PAGADA


def test_no_planeado_sin_categoria_se_rechaza(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)

    respuesta = client.post(reverse("budget:registrar"), _pago(budget_line="", name="Algo"))

    assert respuesta.status_code == 200
    assert "category" in respuesta.context["form"].errors
    assert not Transaction.objects.for_household(hogar).exists()


def test_no_planeado_sin_nombre_toma_el_del_comercio_o_la_categoria(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    categoria = CategoryFactory(household=hogar, slug="farmacia", kind="expense", name="Farmacia")

    client.post(reverse("budget:registrar"), _pago(
        budget_line="", category=categoria.pk, merchant_name="Jean Coutu", amount="12.00",
    ))
    client.post(reverse("budget:registrar"), _pago(
        budget_line="", category=categoria.pk, amount="5.00",
    ))

    nombres = sorted(BudgetLine.objects.for_household(hogar)
                     .filter(is_exceptional=True).values_list("note", flat=True))
    assert nombres == ["Farmacia", "Jean Coutu"]


def test_una_linea_de_otro_hogar_no_se_puede_pagar(client, hogar_con_plan):
    admin, hogar, _ = hogar_con_plan
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    ExpenseRuleFactory(household=ajeno, category=CategoryFactory(household=ajeno, slug="su-rent"))
    hoy = timezone.localdate()
    linea_ajena = services.obtener_mes(ajeno, hoy.year, hoy.month).lineas.get()
    client.force_login(admin)

    respuesta = client.post(reverse("budget:registrar"), _pago(budget_line=linea_ajena.pk))

    assert respuesta.status_code == 200
    assert not Transaction.unscoped.filter(budget_line=linea_ajena).exists()


def test_las_lineas_pagadas_van_al_final_del_desplegable(client, hogar_con_plan):
    """Lo pendiente primero: es lo que se viene a registrar."""
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    alquiler = mes.lineas.get(kind="expense")
    client.post(reverse("budget:registrar"), _pago(budget_line=alquiler.pk))
    ExpenseRuleFactory(household=hogar, name="Internet", amount=Decimal("60.00"),
                       category=CategoryFactory(household=hogar, slug="net"))
    services.refrescar_desde_las_reglas(hogar, mes)

    html = client.get(reverse("budget:registrar")).content.decode()

    assert html.index("Internet") < html.index("Alquiler")
    assert "paid" in html.lower()

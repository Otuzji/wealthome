"""Un registro mal tecleado se corrige o se quita desde "What actually happened".

Edit es una pagina con el mismo formulario del registro; Remove es un POST.
La partida puntual que nacio de un registro "not planned" SIGUE al registro:
se actualiza al editarlo y se borra al quitarlo, para que el plan no se quede
con un "planned $38.20 / paid $32.80" fantasma. Un mes cerrado no admite ni
lo uno ni lo otro.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget.models import BudgetLine, Transaction
from apps.households.models import Membership
from tests.budget.test_registrar_contra_el_plan import _pago, hogar_con_plan  # noqa: F401
from tests.factories import MembershipFactory
from tests.factories_budget import CategoryFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def registro_no_planeado(client, hogar_con_plan):
    """Un gasto "not planned" de 38.20 con su partida puntual."""
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    categoria = CategoryFactory(household=hogar, slug="farmacia", kind="expense", name="Farmacia")
    client.post(reverse("budget:registrar"), _pago(
        budget_line="", category=categoria.pk, name="Antibiotico", amount="38.20",
    ))
    tx = Transaction.objects.for_household(hogar).get()
    return admin, hogar, mes, tx


def _edicion(tx, **extra):
    """Lo que el formulario de edicion trae puesto: un registro "not planned"
    se corrige como tal, con su categoria y su nombre."""
    linea = tx.budget_line
    puntual = linea is not None and linea.is_exceptional
    datos = _pago(amount=str(tx.amount), date=tx.date.isoformat(),
                  budget_line="" if puntual else (tx.budget_line_id or ""),
                  category=tx.category_id, name=linea.note if puntual else "")
    datos.update(extra)
    return datos


def test_el_mes_abierto_ofrece_editar_y_quitar_cada_registro(client, registro_no_planeado):
    admin, hogar, mes, tx = registro_no_planeado

    html = client.get(reverse("budget:mes", args=["household"])).content.decode()

    assert reverse("budget:registro_editar", args=[tx.pk]) in html
    assert reverse("budget:registro_borrar", args=[tx.pk]) in html


def test_editar_muestra_el_registro_con_su_nombre_y_su_titulo(client, registro_no_planeado):
    admin, hogar, mes, tx = registro_no_planeado

    respuesta = client.get(reverse("budget:registro_editar", args=[tx.pk]))

    assert respuesta.status_code == 200
    assert "Edit record" in respuesta.content.decode()
    form = respuesta.context["form"]
    assert form.instance.pk == tx.pk
    assert form["name"].value() == "Antibiotico"
    assert form["amount"].value() == Decimal("38.20")
    # Se corrige como "not planned": su propia partida no esta en "What is it".
    assert form["budget_line"].value() is None
    assert tx.budget_line_id not in [pk for pk, _ in form.fields["budget_line"].choices]


def test_corregir_el_importe_actualiza_la_partida_puntual(client, registro_no_planeado):
    admin, hogar, mes, tx = registro_no_planeado

    respuesta = client.post(reverse("budget:registro_editar", args=[tx.pk]),
                            _edicion(tx, amount="32.80", name="Antibiotico Olivia"))

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("budget:mes", args=["household", mes.year, mes.month])
    tx.refresh_from_db()
    assert tx.amount == Decimal("32.80")
    linea = tx.budget_line
    assert linea.planned_amount == Decimal("32.80") and linea.note == "Antibiotico Olivia"
    assert linea.estado == BudgetLine.PAGADA
    assert BudgetLine.objects.for_household(hogar).filter(is_exceptional=True).count() == 1


def test_pasar_el_registro_a_una_linea_del_plan_borra_la_puntual_huerfana(client, registro_no_planeado):
    admin, hogar, mes, tx = registro_no_planeado
    alquiler = mes.lineas.get(kind="expense", is_exceptional=False)
    puntual_pk = tx.budget_line_id

    client.post(reverse("budget:registro_editar", args=[tx.pk]),
                _edicion(tx, budget_line=alquiler.pk, amount="1750.00"))

    tx.refresh_from_db()
    assert tx.budget_line_id == alquiler.pk and tx.category_id == alquiler.category_id
    assert not BudgetLine.objects.for_household(hogar).filter(pk=puntual_pk).exists()


def test_quitar_el_registro_se_lleva_su_partida_puntual(client, registro_no_planeado):
    admin, hogar, mes, tx = registro_no_planeado
    puntual_pk = tx.budget_line_id

    respuesta = client.post(reverse("budget:registro_borrar", args=[tx.pk]))

    assert respuesta.status_code == 302
    assert not Transaction.objects.for_household(hogar).exists()
    assert not BudgetLine.objects.for_household(hogar).filter(pk=puntual_pk).exists()


def test_quitar_un_pago_contra_el_plan_deja_la_linea_pendiente(client, hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    alquiler = mes.lineas.get(kind="expense")
    client.post(reverse("budget:registrar"), _pago(budget_line=alquiler.pk))
    tx = Transaction.objects.for_household(hogar).get()

    client.post(reverse("budget:registro_borrar", args=[tx.pk]))

    assert BudgetLine.objects.for_household(hogar).get(pk=alquiler.pk).estado == BudgetLine.PENDIENTE


def test_quitar_solo_por_post(client, registro_no_planeado):
    admin, hogar, mes, tx = registro_no_planeado

    respuesta = client.get(reverse("budget:registro_borrar", args=[tx.pk]))

    assert respuesta.status_code == 405
    assert Transaction.objects.for_household(hogar).filter(pk=tx.pk).exists()


def test_un_mes_cerrado_no_deja_corregir_ni_quitar(client, registro_no_planeado):
    admin, hogar, mes, tx = registro_no_planeado
    mes.status = "closed"
    mes.save()

    html = client.get(reverse("budget:mes", args=["household"])).content.decode()
    editar = client.post(reverse("budget:registro_editar", args=[tx.pk]), _edicion(tx, amount="1.00"))
    borrar = client.post(reverse("budget:registro_borrar", args=[tx.pk]))

    assert reverse("budget:registro_borrar", args=[tx.pk]) not in html
    assert editar.status_code == 200 and editar.context["form"].non_field_errors()
    assert borrar.status_code == 302
    tx.refresh_from_db()
    assert tx.amount == Decimal("38.20")


def test_el_registro_de_otro_hogar_es_un_404(client, registro_no_planeado):
    from apps.households.services import crear_hogar
    from tests.factories import UserFactory

    admin, hogar, mes, tx = registro_no_planeado
    ajeno = UserFactory()
    crear_hogar(ajeno, "Family García", family_size=2)
    client.force_login(ajeno)

    assert client.get(reverse("budget:registro_editar", args=[tx.pk])).status_code == 404
    assert client.post(reverse("budget:registro_borrar", args=[tx.pk])).status_code == 404
    assert Transaction.unscoped.filter(pk=tx.pk).exists()


def test_sin_can_add_transactions_no_se_corrige(client, registro_no_planeado):
    admin, hogar, mes, tx = registro_no_planeado
    mirón = MembershipFactory(household=hogar, role=Membership.MEMBER, can_view_budget=True,
                              can_add_transactions=False)
    client.force_login(mirón.user)

    assert client.get(reverse("budget:registro_editar", args=[tx.pk])).status_code == 403
    assert client.post(reverse("budget:registro_borrar", args=[tx.pk])).status_code == 403

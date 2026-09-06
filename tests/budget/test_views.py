"""Las pantallas mínimas, y los permisos que las gobiernan.

Primer uso real de @requiere_permiso: hasta el lote de puertas estaba probado
y no lo llamaba ningún código de producción. Aquí queda ejercitado el
adolescente del §6.2 — registra sus gastos y no ve la hipoteca.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget.models import ExpenseRule, IncomeSource
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import CategoryFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_con_hogar():
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    return user, hogar


def _miembro(hogar, **permisos):
    base = dict(can_view_budget=False, can_edit_budget=False,
                can_add_transactions=False, can_view_reports=False)
    base.update(permisos)
    return MembershipFactory(household=hogar, role=Membership.MEMBER, **base)


# --- los permisos gobiernan de verdad ----------------------------------------


def test_configurar_exige_can_edit_budget(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    sin_permiso = _miembro(hogar, can_add_transactions=True)
    client.force_login(sin_permiso.user)

    respuesta = client.get(reverse("budget:configurar"))

    assert respuesta.status_code == 403


def test_el_403_de_presupuesto_esta_traducido(client, admin_con_hogar):
    """No una página en blanco: la deuda que el lote de puertas cerró."""
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar).user)

    respuesta = client.get(reverse("budget:configurar"))

    assert "You do not have permission" in respuesta.content.decode()


def test_quien_tiene_el_permiso_entra(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_edit_budget=True).user)

    assert client.get(reverse("budget:configurar")).status_code == 200


def test_un_anonimo_va_al_login(client):
    respuesta = client.get(reverse("budget:configurar"))

    assert respuesta.status_code == 302


# --- los formularios no filtran datos de otras familias ----------------------


def test_el_desplegable_de_categorias_solo_trae_las_del_hogar(client, admin_con_hogar):
    """La fuga del <select> que el lote de puertas cerró, verificada en una
    pantalla real."""
    admin, hogar = admin_con_hogar
    CategoryFactory(household=hogar, name="Hipoteca Thompson", slug="mi-rent")
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    CategoryFactory(household=ajeno, name="Hipoteca García", slug="su-rent")
    client.force_login(admin)

    html = client.get(reverse("budget:gasto_nuevo")).content.decode()

    assert "Hipoteca Thompson" in html
    assert "Hipoteca García" not in html


def test_no_se_puede_crear_un_gasto_contra_una_categoria_ajena(client, admin_con_hogar):
    """El <select> filtrado es cosmético: lo que importa es que el POST con
    un id ajeno tampoco pase."""
    admin, hogar = admin_con_hogar
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    categoria_ajena = CategoryFactory(household=ajeno, slug="su-rent")
    client.force_login(admin)

    client.post(reverse("budget:gasto_nuevo"), {
        "category": categoria_ajena.pk, "name": "Intento",
        "amount": "100.00", "periodicity": "monthly",
        "effective_from": "2026-01-01", "scope": "household",
        "is_essential": "on",
    })

    assert not ExpenseRule.unscoped.filter(name="Intento").exists()


# --- crear las cosas ----------------------------------------------------------


def test_el_admin_crea_un_gasto_fijo(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-rent")
    client.force_login(admin)

    respuesta = client.post(reverse("budget:gasto_nuevo"), {
        "category": categoria.pk, "name": "Alquiler",
        "amount": "1800.00", "periodicity": "monthly",
        "effective_from": "2026-01-01", "scope": "household",
        "is_essential": "on",
    })

    assert respuesta.status_code == 302
    regla = ExpenseRule.objects.for_household(hogar).get(name="Alquiler")
    assert regla.amount == Decimal("1800.00")


def test_el_admin_crea_un_ingreso(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    membresia = hogar.active_memberships().first()
    client.force_login(admin)

    client.post(reverse("budget:ingreso_nuevo"), {
        "owner": membresia.pk, "name": "Sueldo", "source_type": "salary",
        "amount_type": "fixed", "amount": "3000.00",
        "periodicity": "monthly", "effective_from": "2026-01-01",
        "scope": "household",
    })

    assert IncomeSource.objects.for_household(hogar).filter(name="Sueldo").exists()


def test_la_pantalla_de_configuracion_lista_lo_creado(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-rent")
    from tests.factories_budget import ExpenseRuleFactory

    ExpenseRuleFactory(household=hogar, category=categoria, name="Alquiler")
    client.force_login(admin)

    html = client.get(reverse("budget:configurar")).content.decode()

    assert "Alquiler" in html

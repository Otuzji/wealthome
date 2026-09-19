"""Editar y borrar las reglas del setup.

Hasta aqui Configurar solo tenia altas: quien tecleaba 1.800 en vez de 1.800,00
o 18.000 no tenia forma de corregirlo. Se edita EN SITIO: es una correccion, no
un cambio en el tiempo (para eso estan effective_to y una regla nueva). Y solo
afecta a los meses que aun no tienen filas: el abierto y los cerrados ya
copiaron sus importes.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget import services
from apps.budget.engine.cascade import ALLOWANCE, FIXED, GOAL, REMAINDER
from apps.budget.models import AllocationRule, ExpenseRule, IncomeSource
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import (
    AllocationRuleFactory,
    CategoryFactory,
    ExpenseRuleFactory,
    GoalFactory,
    IncomeSourceFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_con_hogar():
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    return user, hogar


def _gasto(hogar, **extra):
    datos = dict(
        household=hogar, name="Alquiler", amount=Decimal("18000.00"),
        category=CategoryFactory(household=hogar, slug="mi-rent"),
    )
    datos.update(extra)
    return ExpenseRuleFactory(**datos)


def _payload_gasto(regla, **cambios):
    datos = {
        "category": regla.category_id, "name": regla.name, "amount": str(regla.amount),
        "periodicity": regla.periodicity,
        "effective_from": regla.effective_from.isoformat(),
        "scope": regla.scope, "is_essential": "on",
    }
    datos.update(cambios)
    return datos


# --- editar -------------------------------------------------------------------


def test_el_admin_corrige_el_importe_de_un_gasto_fijo(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    regla = _gasto(hogar)
    client.force_login(admin)

    respuesta = client.post(
        reverse("budget:gasto_editar", args=[regla.pk]),
        _payload_gasto(regla, amount="1800.00"),
    )

    assert respuesta.status_code == 302
    regla.refresh_from_db()
    assert regla.amount == Decimal("1800.00")
    assert ExpenseRule.objects.for_household(hogar).count() == 1   # en sitio, no sucesora


def test_la_edicion_viene_rellena_con_lo_que_hay(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    regla = _gasto(hogar)
    client.force_login(admin)

    html = client.get(reverse("budget:gasto_editar", args=[regla.pk])).content.decode()

    assert 'value="Alquiler"' in html
    assert "18000.00" in html


def test_el_admin_corrige_un_ingreso(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    membresia = hogar.active_memberships().first()
    fuente = IncomeSourceFactory(household=hogar, owner=membresia, amount=Decimal("300.00"))
    client.force_login(admin)

    respuesta = client.post(reverse("budget:ingreso_editar", args=[fuente.pk]), {
        "owner": membresia.pk, "name": fuente.name, "source_type": fuente.source_type,
        "amount_type": "fixed", "amount": "3000.00",
        "periodicity": fuente.periodicity,
        "effective_from": fuente.effective_from.isoformat(), "scope": "household",
    })

    assert respuesta.status_code == 302
    fuente.refresh_from_db()
    assert fuente.amount == Decimal("3000.00")


def test_el_admin_corrige_una_regla_de_reparto(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    regla = AllocationRuleFactory(household=hogar, order=1, target_type=GOAL,
                                  target_goal=meta, method=FIXED, amount=Decimal("60.00"))
    client.force_login(admin)

    respuesta = client.post(reverse("budget:reparto_editar", args=[regla.pk]), {
        "order": 1, "target_type": GOAL, "target_goal": meta.pk,
        "method": FIXED, "amount": "600.00", "split": "equal", "is_active": "on",
    })

    assert respuesta.status_code == 302
    regla.refresh_from_db()
    assert regla.amount == Decimal("600.00")


def test_una_regla_ajena_no_se_puede_editar(client, admin_con_hogar):
    """La barrera del §2.2 tambien en la edicion: el pk de otra familia es un 404."""
    admin, _ = admin_con_hogar
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    regla = _gasto(ajeno)
    client.force_login(admin)

    assert client.get(reverse("budget:gasto_editar", args=[regla.pk])).status_code == 404
    respuesta = client.post(
        reverse("budget:gasto_editar", args=[regla.pk]),
        _payload_gasto(regla, amount="1.00"),
    )
    assert respuesta.status_code == 404
    regla.refresh_from_db()
    assert regla.amount == Decimal("18000.00")


def test_editar_exige_can_edit_budget(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    regla = _gasto(hogar)
    miembro = MembershipFactory(
        household=hogar, role=Membership.MEMBER,
        can_view_budget=True, can_edit_budget=False,
        can_add_transactions=True, can_view_reports=False,
    )
    client.force_login(miembro.user)

    assert client.get(reverse("budget:gasto_editar", args=[regla.pk])).status_code == 403


def test_corregir_una_regla_cambia_la_proyeccion_pero_no_el_mes_abierto(client, admin_con_hogar):
    """§2.3: el mes abierto ya copio sus filas; la correccion vale de ahi en adelante."""
    admin, hogar = admin_con_hogar
    regla = _gasto(hogar, effective_from=date(2026, 1, 1))
    hoy = date(2026, 9, 19)
    mes = services.obtener_mes(hogar, 2026, 9, hoy=hoy)
    client.force_login(admin)

    client.post(reverse("budget:gasto_editar", args=[regla.pk]),
                _payload_gasto(regla, amount="1800.00"))

    linea = mes.lineas.get(source_expense_rule=regla)
    assert linea.planned_amount == Decimal("18000.00")
    assert services.proyectar(hogar, 2026, 10).total_egresos == Decimal("1800.00")


# --- borrar -------------------------------------------------------------------


def test_el_admin_borra_un_gasto_fijo(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    regla = _gasto(hogar)
    client.force_login(admin)

    respuesta = client.post(reverse("budget:gasto_borrar", args=[regla.pk]))

    assert respuesta.status_code == 302
    assert not ExpenseRule.objects.for_household(hogar).filter(pk=regla.pk).exists()


def test_borrar_solo_por_post(client, admin_con_hogar):
    """Un GET no destruye nada: un enlace prefetched o un rastreador no puede borrar."""
    admin, hogar = admin_con_hogar
    regla = _gasto(hogar)
    client.force_login(admin)

    respuesta = client.get(reverse("budget:gasto_borrar", args=[regla.pk]))

    assert respuesta.status_code == 405
    assert ExpenseRule.objects.for_household(hogar).filter(pk=regla.pk).exists()


def test_borrar_un_ingreso_y_una_regla_de_reparto(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    membresia = hogar.active_memberships().first()
    fuente = IncomeSourceFactory(household=hogar, owner=membresia)
    reparto = AllocationRuleFactory(household=hogar, order=1, target_type=ALLOWANCE,
                                    method=REMAINDER, target_goal=None)
    client.force_login(admin)

    client.post(reverse("budget:ingreso_borrar", args=[fuente.pk]))
    client.post(reverse("budget:reparto_borrar", args=[reparto.pk]))

    assert not IncomeSource.objects.for_household(hogar).exists()
    assert not AllocationRule.objects.for_household(hogar).exists()


def test_una_regla_ajena_no_se_puede_borrar(client, admin_con_hogar):
    admin, _ = admin_con_hogar
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    regla = _gasto(ajeno)
    client.force_login(admin)

    assert client.post(reverse("budget:gasto_borrar", args=[regla.pk])).status_code == 404
    assert ExpenseRule.unscoped.filter(pk=regla.pk).exists()


def test_borrar_una_regla_conserva_las_lineas_del_mes_abierto(client, admin_con_hogar):
    """La linea materializada se queda (source_expense_rule pasa a NULL): el mes
    en curso ya conto con ese gasto y borrar la regla es 'de ahora en adelante'."""
    admin, hogar = admin_con_hogar
    regla = _gasto(hogar, effective_from=date(2026, 1, 1))
    mes = services.obtener_mes(hogar, 2026, 9, hoy=date(2026, 9, 19))
    client.force_login(admin)

    client.post(reverse("budget:gasto_borrar", args=[regla.pk]))

    assert mes.lineas.filter(planned_amount=Decimal("18000.00")).exists()


def test_configurar_enlaza_a_editar_y_borrar(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    regla = _gasto(hogar)
    client.force_login(admin)

    html = client.get(reverse("budget:configurar")).content.decode()

    assert reverse("budget:gasto_editar", args=[regla.pk]) in html
    assert reverse("budget:gasto_borrar", args=[regla.pk]) in html

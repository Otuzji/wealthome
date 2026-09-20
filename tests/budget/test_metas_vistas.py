"""La pantalla de metas: por ambito, por estado, y sus escrituras.

Fuera de test_views.py a proposito: aquel tiene 55 pruebas y ~500 s.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget.models import Goal
from apps.households.models import Membership
from tests.budget.test_views import admin_con_hogar  # noqa: F401
from tests.factories import HouseholdFactory, MembershipFactory
from tests.factories_budget import GoalContributionFactory, GoalFactory

pytestmark = pytest.mark.django_db


def _miembro(hogar, **permisos):
    base = dict(can_view_budget=True, can_edit_budget=False,
                can_add_transactions=True, can_view_reports=False)
    base.update(permisos)
    return MembershipFactory(household=hogar, role=Membership.MEMBER, **base)


def _mia(hogar, user):
    return hogar.memberships.get(user=user)


# --- la lista -----------------------------------------------------------------


def test_household_lista_las_del_hogar_y_personal_solo_las_mias(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    otro = _miembro(hogar)
    del_hogar = GoalFactory(household=hogar, name="Techo nuevo", scope="household")
    mia = GoalFactory(household=hogar, name="Mi bici", scope="personal", owner=_mia(hogar, user))
    ajena = GoalFactory(household=hogar, name="Su consola", scope="personal", owner=otro)
    client.force_login(user)

    hogar_html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    personal_html = client.get(reverse("budget:metas", args=["personal"])).content.decode()

    assert del_hogar.name in hogar_html and mia.name not in hogar_html
    assert mia.name in personal_html and del_hogar.name not in personal_html
    assert ajena.name not in hogar_html and ajena.name not in personal_html


def test_la_lista_agrupa_por_estado(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    activa = GoalFactory(household=hogar, name="Activa")
    alcanzada = GoalFactory(household=hogar, name="Alcanzada", status=Goal.REACHED)
    abandonada = GoalFactory(household=hogar, name="Abandonada", status=Goal.ABANDONED)
    client.force_login(user)

    respuesta = client.get(reverse("budget:metas", args=["household"]))

    contexto = respuesta.context
    assert [f["meta"] for f in contexto["activas"]] == [activa]
    assert [f["meta"] for f in contexto["alcanzadas"]] == [alcanzada]
    assert [f["meta"] for f in contexto["abandonadas"]] == [abandonada]
    html = respuesta.content.decode()
    assert "Reached" in html and "Abandoned" in html


def test_una_meta_alcanzada_dice_cuando_y_no_pide_mas(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"),
                            date=date(2026, 2, 14))
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert "You got there" in html
    assert "Put in" not in html


def test_una_meta_de_hogar_sin_regla_lo_dice_y_una_personal_tambien(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    GoalFactory(household=hogar, scope="household")
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert "add a split rule" in html

    GoalFactory(household=hogar, scope="personal", owner=_mia(hogar, user))
    html = client.get(reverse("budget:metas", args=["personal"])).content.decode()
    assert "only manual contributions" in html


def test_los_aportes_de_cascada_se_distinguen(client, admin_con_hogar):
    from apps.budget.models import GoalContribution

    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    GoalContribution.unscoped.create(
        household=hogar, goal=meta, amount=Decimal("50.00"), date=date(2026, 3, 31),
        member=None, origen="cascade",
    )
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert "From the monthly split" in html


def test_una_meta_de_otro_hogar_no_aparece(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    GoalFactory(household=HouseholdFactory(), name="De otra familia")
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert "De otra familia" not in html

"""Aportar a una meta, y corregir o quitar un aporte.

Un aporte es un registro como un gasto: quien lo teclea puede equivocarse.
El de la cascada no: lo escribio el cierre del mes y cuadra con el reparto.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget.forms import GoalContributionForm
from apps.budget.models import Goal
from apps.households.models import Membership
from tests.budget.test_views import admin_con_hogar  # noqa: F401
from tests.factories import MembershipFactory
from tests.factories_budget import GoalFactory

pytestmark = pytest.mark.django_db


def _miembro(hogar, **permisos):
    base = dict(can_view_budget=True, can_edit_budget=True,
                can_add_transactions=True, can_view_reports=False)
    base.update(permisos)
    return MembershipFactory(household=hogar, role=Membership.MEMBER, **base)


def _mia(hogar, user):
    return hogar.memberships.get(user=user)


# --- el formulario ------------------------------------------------------------


def test_el_formulario_solo_ofrece_metas_activas_que_puedo_ver(admin_con_hogar):
    user, hogar = admin_con_hogar
    yo = _mia(hogar, user)
    otro = _miembro(hogar)
    del_hogar = GoalFactory(household=hogar, scope="household")
    mia = GoalFactory(household=hogar, scope="personal", owner=yo)
    GoalFactory(household=hogar, scope="personal", owner=otro)
    GoalFactory(household=hogar, status=Goal.REACHED)
    GoalFactory(household=hogar, status=Goal.ABANDONED)

    form = GoalContributionForm(household=hogar, membresia=yo)

    assert set(form.fields["goal"].queryset) == {del_hogar, mia}


def test_al_editar_el_formulario_conserva_la_meta_aunque_ya_no_este_activa(admin_con_hogar):
    from tests.factories_budget import GoalContributionFactory

    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, status=Goal.REACHED)
    aporte = GoalContributionFactory(household=hogar, goal=meta)

    form = GoalContributionForm(household=hogar, membresia=_mia(hogar, user), instance=aporte)

    assert meta in form.fields["goal"].queryset


def test_una_fecha_futura_se_rechaza(admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    manana = timezone.localdate() + timedelta(days=1)

    form = GoalContributionForm(
        {"goal": meta.pk, "amount": "10.00", "date": manana.isoformat()},
        household=hogar, membresia=_mia(hogar, user),
    )

    assert not form.is_valid()
    assert "date" in form.errors


def test_un_importe_de_cero_se_rechaza(admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)

    form = GoalContributionForm(
        {"goal": meta.pk, "amount": "0.00", "date": "2026-03-01"},
        household=hogar, membresia=_mia(hogar, user),
    )

    assert not form.is_valid()
    assert "amount" in form.errors

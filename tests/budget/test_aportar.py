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


# --- aportar ------------------------------------------------------------------

HTMX = {"HTTP_HX_REQUEST": "true"}


def test_aportar_exige_can_edit_budget(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_edit_budget=False).user)

    assert client.get(reverse("budget:aportar")).status_code == 403
    assert client.post(reverse("budget:aportar"), {}).status_code == 403


def test_por_htmx_llega_el_fragmento_con_el_titulo_fuera_de_banda(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    GoalFactory(household=hogar)
    client.force_login(user)

    html = client.get(reverse("budget:aportar"), **HTMX).content.decode()

    assert 'id="modal-gasto-titulo" hx-swap-oob="true"' in html
    assert "Add to a goal" in html
    assert "hx-post" in html
    assert "<html" not in html


def test_sin_metas_activas_el_fragmento_lo_dice_en_vez_de_un_select_vacio(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    GoalFactory(household=hogar, status=Goal.REACHED)
    client.force_login(user)

    html = client.get(reverse("budget:aportar"), **HTMX).content.decode()

    assert "No active goals yet" in html
    assert reverse("budget:meta_nueva") in html
    assert "<select" not in html


def test_goal_en_la_query_preselecciona_la_meta(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    respuesta = client.get(reverse("budget:aportar") + f"?goal={meta.pk}", **HTMX)

    assert respuesta.context["form"]["goal"].value() == meta.pk


def test_un_aporte_por_htmx_devuelve_la_tarjeta_fuera_de_banda_y_cierra_el_modal(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("1000.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aportar"), {
        "goal": meta.pk, "amount": "150.00", "date": timezone.localdate().isoformat(),
    }, **HTMX)

    assert respuesta.status_code == 200
    assert respuesta["HX-Trigger"] == "gasto-registrado"
    html = respuesta.content.decode()
    assert f'id="meta-{meta.pk}"' in html and "hx-swap-oob" in html
    assert "150" in html
    aporte = meta.contributions.get()
    assert aporte.member == _mia(hogar, user)
    assert aporte.origen == "manual"
    # Y el formulario vuelve limpio, con la fecha de hoy.
    assert respuesta.context["form"]["date"].value() == timezone.localdate()


def test_un_aporte_por_la_pagina_entera_vuelve_a_metas_del_ambito(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, scope="personal", owner=_mia(hogar, user))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aportar"), {
        "goal": meta.pk, "amount": "20.00", "date": timezone.localdate().isoformat(),
    })

    assert respuesta.status_code == 302
    assert respuesta["Location"] == reverse("budget:metas", args=["personal"])


def test_aportar_a_la_meta_personal_de_otro_se_rechaza(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    ajena = GoalFactory(household=hogar, scope="personal", owner=_miembro(hogar))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aportar"), {
        "goal": ajena.pk, "amount": "20.00", "date": timezone.localdate().isoformat(),
    })

    assert respuesta.status_code == 200
    assert "goal" in respuesta.context["form"].errors
    assert not ajena.contributions.exists()


def test_aportar_en_un_mes_cerrado_lo_dice_el_formulario(client, admin_con_hogar):
    from apps.budget.models import BudgetMonth
    from tests.factories_budget import BudgetMonthFactory

    user, hogar = admin_con_hogar
    BudgetMonthFactory(household=hogar, year=2026, month=1, status=BudgetMonth.CLOSED)
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    respuesta = client.post(reverse("budget:aportar"), {
        "goal": meta.pk, "amount": "20.00", "date": "2026-01-15",
    })

    assert respuesta.status_code == 200
    assert "This month is already closed." in respuesta.content.decode()
    assert not meta.contributions.exists()


def test_la_tarjeta_activa_ofrece_aportar_y_la_alcanzada_no(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    activa = GoalFactory(household=hogar)
    GoalFactory(household=hogar, status=Goal.REACHED)
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert html.count("Add to it") == 1
    assert f"?goal={activa.pk}" in html


# --- corregir y quitar --------------------------------------------------------

from tests.factories_budget import BudgetMonthFactory, GoalContributionFactory  # noqa: E402


def _cascada(hogar, meta, **campos):
    from apps.budget.models import GoalContribution

    base = dict(household=hogar, goal=meta, amount=Decimal("50.00"),
                date=date(2026, 3, 31), member=None, origen="cascade")
    base.update(campos)
    return GoalContribution.unscoped.create(**base)


def test_corregir_un_aporte_recalcula_el_estado(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))
    aporte = GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("40.00"),
                                     date=date(2026, 3, 1))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aporte_editar", args=[aporte.pk]), {
        "goal": meta.pk, "amount": "100.00", "date": "2026-03-01",
    })

    assert respuesta.status_code == 302
    aporte.refresh_from_db()
    assert aporte.amount == Decimal("100.00")
    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


def test_quitar_un_aporte_reabre_la_meta(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    aporte = GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aporte_borrar", args=[aporte.pk]))

    assert respuesta.status_code == 302
    assert not meta.contributions.exists()
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_un_aporte_de_cascada_no_se_toca(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    aporte = _cascada(hogar, meta)
    client.force_login(user)

    assert client.get(reverse("budget:aporte_editar", args=[aporte.pk])).status_code == 403
    assert client.post(reverse("budget:aporte_borrar", args=[aporte.pk])).status_code == 403
    assert meta.contributions.filter(pk=aporte.pk).exists()


def test_un_aporte_de_un_mes_cerrado_no_se_toca(client, admin_con_hogar):
    from apps.budget.models import BudgetMonth

    user, hogar = admin_con_hogar
    # Se cierra DESPUES de sembrar el aporte: la guarda del modelo no deja
    # escribir contra un mes cerrado, ni desde una factory.
    mes = BudgetMonthFactory(household=hogar, year=2026, month=1)
    meta = GoalFactory(household=hogar)
    aporte = GoalContributionFactory(household=hogar, goal=meta, date=date(2026, 1, 10),
                                     budget_month=mes)
    mes.status = BudgetMonth.CLOSED
    mes.save(update_fields=["status"])
    client.force_login(user)

    editar = client.post(reverse("budget:aporte_editar", args=[aporte.pk]), {
        "goal": meta.pk, "amount": "1.00", "date": "2026-02-10",
    }, follow=True)
    borrar = client.post(reverse("budget:aporte_borrar", args=[aporte.pk]), follow=True)

    assert "This month is already closed." in editar.content.decode()
    assert "This month is already closed." in borrar.content.decode()
    aporte.refresh_from_db()
    assert aporte.amount == Decimal("50.00")


def test_mover_un_aporte_a_un_mes_cerrado_lo_dice_el_formulario(client, admin_con_hogar):
    from apps.budget.models import BudgetMonth

    user, hogar = admin_con_hogar
    BudgetMonthFactory(household=hogar, year=2026, month=1, status=BudgetMonth.CLOSED)
    meta = GoalFactory(household=hogar)
    aporte = GoalContributionFactory(household=hogar, goal=meta, date=date(2026, 3, 10))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aporte_editar", args=[aporte.pk]), {
        "goal": meta.pk, "amount": "50.00", "date": "2026-01-10",
    })

    assert respuesta.status_code == 200
    assert "This month is already closed." in respuesta.content.decode()
    aporte.refresh_from_db()
    assert aporte.date == date(2026, 3, 10)


def test_los_aportes_editables_llevan_acciones_y_los_demas_no(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    manual = GoalContributionFactory(household=hogar, goal=meta)
    cascada = _cascada(hogar, meta)
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert reverse("budget:aporte_editar", args=[manual.pk]) in html
    assert reverse("budget:aporte_editar", args=[cascada.pk]) not in html


def test_tocar_un_aporte_exige_can_edit_budget(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    aporte = GoalContributionFactory(household=hogar, goal=GoalFactory(household=hogar))
    client.force_login(_miembro(hogar, can_edit_budget=False).user)

    assert client.get(reverse("budget:aporte_editar", args=[aporte.pk])).status_code == 403
    assert client.post(reverse("budget:aporte_borrar", args=[aporte.pk])).status_code == 403


def test_el_aporte_de_la_meta_personal_de_otro_es_un_404(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    ajena = GoalFactory(household=hogar, scope="personal", owner=_miembro(hogar))
    aporte = GoalContributionFactory(household=hogar, goal=ajena)
    client.force_login(user)

    assert client.get(reverse("budget:aporte_editar", args=[aporte.pk])).status_code == 404
    assert client.post(reverse("budget:aporte_borrar", args=[aporte.pk])).status_code == 404

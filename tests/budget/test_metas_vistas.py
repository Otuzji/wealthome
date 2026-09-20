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


# --- el formulario de meta ----------------------------------------------------


def test_el_ambito_de_una_meta_con_aportes_no_se_cambia(admin_con_hogar):
    from apps.budget.forms import GoalForm

    _user, hogar = admin_con_hogar
    con = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=con)
    sin = GoalFactory(household=hogar)

    assert GoalForm(household=hogar, instance=con).fields["scope"].disabled is True
    assert GoalForm(household=hogar, instance=con).fields["owner"].disabled is True
    assert GoalForm(household=hogar, instance=sin).fields["scope"].disabled is False


# --- editar, borrar, estado ---------------------------------------------------


def _datos(meta, **cambios):
    base = {
        "name": meta.name, "scope": meta.scope, "owner": meta.owner_id or "",
        "contribution_mode": meta.contribution_mode,
        "target_amount": str(meta.target_amount),
        "target_date": meta.target_date.isoformat() if meta.target_date else "",
        "monthly_amount": str(meta.monthly_amount) if meta.monthly_amount else "",
    }
    base.update(cambios)
    return base


def test_subir_el_objetivo_reabre_una_meta_alcanzada(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_editar", args=[meta.pk]),
                            _datos(meta, target_amount="200.00"))

    assert respuesta.status_code == 302
    meta.refresh_from_db()
    assert meta.target_amount == Decimal("200.00")
    assert meta.status == Goal.ACTIVE


def test_bajar_el_objetivo_la_da_por_alcanzada(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("500.00"))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("120.00"))
    client.force_login(user)

    client.post(reverse("budget:meta_editar", args=[meta.pk]), _datos(meta, target_amount="100.00"))

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


def test_borrar_una_meta_sin_cascada_se_lleva_sus_aportes(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta)
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_borrar", args=[meta.pk]))

    assert respuesta.status_code == 302
    assert not Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()


def test_una_meta_con_cascada_no_se_borra_se_abandona(client, admin_con_hogar):
    from apps.budget.models import GoalContribution

    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    GoalContribution.unscoped.create(
        household=hogar, goal=meta, amount=Decimal("50.00"), date=date(2026, 3, 31),
        member=None, origen="cascade",
    )
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_borrar", args=[meta.pk]), follow=True)

    assert Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()
    assert "abandon it instead" in respuesta.content.decode()
    html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert reverse("budget:meta_borrar", args=[meta.pk]) not in html
    assert reverse("budget:meta_estado", args=[meta.pk, "abandoned"]) in html


def test_borrar_por_get_no_destruye_nada(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    assert client.get(reverse("budget:meta_borrar", args=[meta.pk])).status_code == 405
    assert Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()


def test_abandonar_y_reactivar_desde_la_pantalla(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    client.post(reverse("budget:meta_estado", args=[meta.pk, "abandoned"]))
    meta.refresh_from_db()
    assert meta.status == Goal.ABANDONED

    client.post(reverse("budget:meta_estado", args=[meta.pk, "active"]))
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_una_transicion_imposible_es_un_400(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, status=Goal.REACHED)
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_estado", args=[meta.pk, "abandoned"]))

    assert respuesta.status_code == 400
    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


@pytest.mark.parametrize("ruta,metodo", [
    ("budget:meta_editar", "get"),
    ("budget:meta_borrar", "post"),
])
def test_escribir_una_meta_exige_can_edit_budget(client, admin_con_hogar, ruta, metodo):
    _user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(_miembro(hogar).user)

    respuesta = getattr(client, metodo)(reverse(ruta, args=[meta.pk]))

    assert respuesta.status_code == 403


def test_cambiar_el_estado_exige_can_edit_budget(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(_miembro(hogar).user)

    assert client.post(reverse("budget:meta_estado", args=[meta.pk, "abandoned"])).status_code == 403


def test_la_meta_de_otro_hogar_es_un_404(client, admin_con_hogar):
    user, _hogar = admin_con_hogar
    ajena = GoalFactory(household=HouseholdFactory())
    client.force_login(user)

    assert client.get(reverse("budget:meta_editar", args=[ajena.pk])).status_code == 404
    assert client.post(reverse("budget:meta_borrar", args=[ajena.pk])).status_code == 404


def test_la_meta_personal_de_otro_miembro_es_un_404(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    ajena = GoalFactory(household=hogar, scope="personal", owner=_miembro(hogar))
    client.force_login(user)

    assert client.get(reverse("budget:meta_editar", args=[ajena.pk])).status_code == 404


def test_el_enlace_de_la_tarjeta_preselecciona_la_regla_de_reparto(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    respuesta = client.get(reverse("budget:reparto_nuevo") + f"?target_type=goal&target_goal={meta.pk}")

    form = respuesta.context["form"]
    assert form["target_type"].value() == "goal"
    assert form["target_goal"].value() == meta.pk

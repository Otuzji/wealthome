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


def test_borrar_una_meta_vacia_sin_cascada_se_lleva_su_historial(client, admin_con_hogar):
    from apps.budget import services_goals

    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("50.00"))
    services_goals.retirar(hogar, meta, Decimal("50.00"), date(2026, 4, 1), _mia(hogar, user))
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_borrar", args=[meta.pk]))

    assert respuesta.status_code == 302
    assert not Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()


def test_una_meta_con_saldo_no_se_borra(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("50.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_borrar", args=[meta.pk]), follow=True)

    assert Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()
    assert "Withdraw or transfer its balance first." in respuesta.content.decode()
    html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert reverse("budget:meta_borrar", args=[meta.pk]) not in html
    assert reverse("budget:meta_retirar", args=[meta.pk]) in html
    assert reverse("budget:meta_transferir", args=[meta.pk]) in html


def test_una_meta_vacia_con_cascada_se_archiva_y_sale_de_goals(client, admin_con_hogar):
    from apps.budget import services_goals
    from apps.budget.models import GoalContribution

    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, name="Techo viejo")
    GoalContribution.unscoped.create(
        household=hogar, goal=meta, amount=Decimal("50.00"), date=date(2026, 3, 31),
        member=None, origen="cascade",
    )
    services_goals.retirar(hogar, meta, Decimal("50.00"), date(2026, 4, 1), _mia(hogar, user))
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert 'title="Archive"' in html

    respuesta = client.post(reverse("budget:meta_borrar", args=[meta.pk]), follow=True)

    meta.refresh_from_db()
    assert meta.status == Goal.ARCHIVED
    assert "Archived" in respuesta.content.decode()
    assert "Techo viejo" not in client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert client.get(reverse("budget:meta_editar", args=[meta.pk])).status_code == 404


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


# --- retirar, transferir, el fondo y Balance (Metas II) ------------------------


def test_retirar_desde_la_pantalla_baja_el_saldo_y_vuelve_a_goals(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("500.00"))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("500.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_retirar", args=[meta.pk]), {
        "amount": "120.00", "date": "2026-09-01", "note": "Vuelos",
    })

    assert respuesta.status_code == 302
    assert respuesta["Location"] == reverse("budget:metas", args=["household"])
    assert meta.acumulado() == Decimal("380.00")
    html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert "Withdrawal" in html and "Vuelos" in html and "-$120.00" in html


def test_retirar_de_mas_lo_dice_el_formulario(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("50.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_retirar", args=[meta.pk]), {
        "amount": "80.00", "date": "2026-09-01", "note": "",
    })

    assert respuesta.status_code == 200
    assert "more than the goal holds" in respuesta.content.decode()
    assert meta.acumulado() == Decimal("50.00")


def test_transferir_desde_la_pantalla_crea_la_pareja(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    origen = GoalFactory(household=hogar, name="Fondo")
    destino = GoalFactory(household=hogar, name="Viaje", target_amount=Decimal("100.00"))
    GoalContributionFactory(household=hogar, goal=origen, amount=Decimal("300.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_transferir", args=[origen.pk]), {
        "to_goal": destino.pk, "amount": "100.00", "date": "2026-09-01", "note": "",
    })

    assert respuesta.status_code == 302
    assert origen.acumulado() == Decimal("200.00")
    assert destino.acumulado() == Decimal("100.00")
    destino.refresh_from_db()
    assert destino.status == Goal.REACHED
    html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert "To Viaje" in html and "From Fondo" in html


def test_el_destino_de_la_transferencia_no_ofrece_la_propia_ni_las_no_activas(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    origen = GoalFactory(household=hogar)
    activa = GoalFactory(household=hogar)
    GoalFactory(household=hogar, status=Goal.REACHED)
    GoalFactory(household=hogar, status=Goal.ABANDONED)
    GoalFactory(household=hogar, scope="personal", owner=_miembro(hogar))
    client.force_login(user)

    form = client.get(reverse("budget:meta_transferir", args=[origen.pk])).context["form"]

    assert list(form.fields["to_goal"].queryset) == [activa]


def test_el_fondo_abierto_se_crea_sin_objetivo_y_su_tarjeta_ensena_el_saldo(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_nueva"), {
        "name": "Emergencias", "scope": "household", "owner": "",
        "contribution_mode": "open_fund", "target_amount": "", "target_date": "",
        "monthly_amount": "200.00",
    })

    assert respuesta.status_code == 302
    fondo = Goal.objects.for_household(hogar).get(name="Emergencias")
    assert fondo.target_amount is None and fondo.monthly_amount == Decimal("200.00")
    html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert "Balance: $0.00" in html
    assert "of the $200.00 you set" in html
    assert 'class="progreso"' not in html


def test_al_pasar_a_fondo_abierto_el_objetivo_se_vacia(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("900.00"), target_date=date(2027, 1, 1))
    client.force_login(user)

    client.post(reverse("budget:meta_editar", args=[meta.pk]), {
        "name": meta.name, "scope": "household", "owner": "",
        "contribution_mode": "open_fund", "target_amount": "900.00",
        "target_date": "2027-01-01", "monthly_amount": "",
    })

    meta.refresh_from_db()
    assert meta.contribution_mode == "open_fund"
    assert meta.target_amount is None and meta.target_date is None


def test_balance_lleva_el_bloque_de_ahorro(client, admin_con_hogar):
    from apps.budget import services_goals

    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, name="Viaje")
    services_goals.aportar(hogar, meta, Decimal("300.00"), date(2026, 7, 10), _mia(hogar, user))
    services_goals.retirar(hogar, meta, Decimal("50.00"), date(2026, 8, 2), _mia(hogar, user))
    client.force_login(user)

    respuesta = client.get(reverse("budget:summary", args=["household"]))

    html = respuesta.content.decode()
    assert "Savings" in html and "Saved, total" in html
    assert respuesta.context["ahorro"]["saldo_total"] == Decimal("250.00")
    assert "2026-08" in html and "-$50.00" in html and "Viaje" in html


def test_balance_sin_ahorro_lo_dice(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)

    html = client.get(reverse("budget:summary", args=["household"])).content.decode()

    assert "Nothing saved yet." in html


@pytest.mark.parametrize("ruta", ["budget:meta_retirar", "budget:meta_transferir"])
def test_sacar_dinero_exige_can_edit_budget_y_una_meta_propia(client, admin_con_hogar, ruta):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    ajena = GoalFactory(household=hogar, scope="personal", owner=_miembro(hogar))
    client.force_login(_miembro(hogar).user)
    assert client.get(reverse(ruta, args=[meta.pk])).status_code == 403

    client.force_login(user)
    assert client.get(reverse(ruta, args=[ajena.pk])).status_code == 404

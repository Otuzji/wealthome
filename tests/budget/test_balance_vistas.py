"""La pantalla Balance (activos y pasivos del hogar) y sus escrituras."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget.models import BalanceItem
from apps.budget.models.balance import LONG_TERM, PROPERTY, SHORT_TERM
from apps.households.models import Membership
from tests.budget.test_views import admin_con_hogar  # noqa: F401
from tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db


def _miembro(hogar, **permisos):
    base = dict(can_view_budget=True, can_edit_budget=False,
                can_add_transactions=True, can_view_reports=True)
    base.update(permisos)
    return MembershipFactory(household=hogar, role=Membership.MEMBER, **base)


def _casa(hogar):
    return BalanceItem.unscoped.create(household=hogar, group=PROPERTY, name="Casa",
                                       amount=Decimal("400000.00"))


def test_balance_ensena_activos_pasivos_y_neto(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    _casa(hogar)
    BalanceItem.unscoped.create(household=hogar, group=LONG_TERM, name="Hipoteca",
                                amount=Decimal("250000.00"))
    client.force_login(user)

    respuesta = client.get(reverse("budget:balance", args=["household"]))

    assert respuesta.status_code == 200
    assert respuesta.context["patrimonio"]["neto"] == Decimal("150000.00")
    html = respuesta.content.decode()
    assert "Net worth" in html and "Casa" in html and "Hipoteca" in html
    # Las dos filas automaticas, marcadas, y sin lapiz.
    assert html.count("Automatic") == 2
    assert "Savings" in html and "Cash" in html


def test_balance_exige_can_view_reports(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_view_reports=False).user)
    assert client.get(reverse("budget:balance", args=["household"])).status_code == 403


def test_quien_no_edita_no_ve_los_botones(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    casa = _casa(hogar)
    client.force_login(_miembro(hogar).user)

    html = client.get(reverse("budget:balance", args=["household"])).content.decode()

    assert "Add an item" not in html
    assert reverse("budget:balance_item_editar", args=[casa.pk]) not in html
    assert client.get(reverse("budget:balance_item_nuevo")).status_code == 403


def test_anadir_una_linea_con_el_grupo_preelegido(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)

    form = client.get(reverse("budget:balance_item_nuevo") + f"?group={SHORT_TERM}")
    assert form.context["form"].initial["group"] == SHORT_TERM

    respuesta = client.post(reverse("budget:balance_item_nuevo"), {
        "group": SHORT_TERM, "name": "Visa", "amount": "1200.00", "note": "",
    })

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("budget:balance", args=["household"])
    item = BalanceItem.objects.for_household(hogar).get()
    assert item.name == "Visa" and item.amount == Decimal("1200.00")


def test_una_deuda_negativa_no_pasa_el_formulario(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)

    respuesta = client.post(reverse("budget:balance_item_nuevo"), {
        "group": SHORT_TERM, "name": "Visa", "amount": "-5.00",
    })

    assert respuesta.status_code == 200
    assert "positive" in respuesta.content.decode()
    assert not BalanceItem.objects.for_household(hogar).exists()


def test_editar_y_quitar_una_linea(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    casa = _casa(hogar)
    client.force_login(user)

    editada = client.post(reverse("budget:balance_item_editar", args=[casa.pk]), {
        "group": PROPERTY, "name": "Casa", "amount": "410000.00", "note": "Tasacion 2026",
    })
    assert editada.status_code == 302
    casa.refresh_from_db()
    assert casa.amount == Decimal("410000.00") and casa.note == "Tasacion 2026"

    assert client.get(reverse("budget:balance_item_borrar", args=[casa.pk])).status_code == 405
    borrada = client.post(reverse("budget:balance_item_borrar", args=[casa.pk]))
    assert borrada.status_code == 302
    assert not BalanceItem.objects.for_household(hogar).exists()


def test_la_linea_de_otro_hogar_es_un_404(client, admin_con_hogar):
    from apps.households.services import crear_hogar
    from tests.factories import UserFactory

    user, _hogar = admin_con_hogar
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    suya = _casa(ajeno)
    client.force_login(user)

    assert client.get(reverse("budget:balance_item_editar", args=[suya.pk])).status_code == 404
    assert client.post(reverse("budget:balance_item_borrar", args=[suya.pk])).status_code == 404
    assert BalanceItem.unscoped.filter(pk=suya.pk).exists()

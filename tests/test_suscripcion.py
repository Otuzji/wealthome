import pytest
from datetime import timedelta

from django.utils import timezone

from apps.households.services import crear_hogar
from apps.subscriptions.models import Subscription
from tests.factories import HouseholdFactory, UserFactory


@pytest.mark.django_db
def test_un_hogar_nuevo_nace_con_catorce_dias_y_sin_tarjeta():
    user = UserFactory()
    hogar = crear_hogar(user, "Los Perez", 3)

    suscripcion = hogar.subscription
    assert suscripcion.status == Subscription.TRIALING
    assert suscripcion.paid_at is None
    assert 13 <= suscripcion.dias_restantes <= 14
    assert suscripcion.esta_vigente is True
    assert suscripcion.estado_visible == "trialing"


@pytest.mark.django_db
def test_el_dia_quince_deja_de_estar_vigente():
    hogar = HouseholdFactory()
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    assert hogar.subscription.esta_vigente is False
    assert hogar.subscription.estado_visible == "expired"


@pytest.mark.django_db
def test_una_suscripcion_pagada_esta_vigente_para_siempre():
    hogar = HouseholdFactory()
    suscripcion = hogar.subscription
    suscripcion.status = Subscription.ACTIVE
    suscripcion.paid_at = timezone.now()
    suscripcion.trial_ends_at = timezone.now() - timedelta(days=400)
    suscripcion.save()

    assert suscripcion.esta_vigente is True
    assert suscripcion.estado_visible == "active"
    assert suscripcion.dias_restantes is None


@pytest.mark.django_db
def test_la_fabrica_tambien_crea_la_suscripcion():
    """§2.4 del spec: la ausencia de fila significa 'puede escribir', pero el
    caso no debe poder aparecer. Los tres sitios que crean hogares la crean."""
    hogar = HouseholdFactory()
    assert hogar.subscription is not None


@pytest.mark.django_db
def test_un_hogar_sin_fila_de_suscripcion_puede_escribir():
    """Fallar cerrado romperia toda fabrica que no pase por crear_hogar."""
    hogar = HouseholdFactory()
    hogar.subscription.delete()
    hogar = type(hogar).objects.get(pk=hogar.pk)

    assert hogar.puede_escribir is True


@pytest.mark.django_db
def test_un_hogar_expirado_lee_pero_no_escribe(client):
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    assert client.get(reverse("budget:configurar")).status_code == 200
    assert client.post(reverse("budget:ingreso_nuevo"), {}).status_code == 403


@pytest.mark.django_db
def test_la_capa_de_modelo_lanza_aunque_se_rodee_la_vista():
    from apps.subscriptions.models import SuscripcionVencidaError
    from tests.factories_budget import CategoryFactory

    hogar = HouseholdFactory()
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    hogar = type(hogar).objects.get(pk=hogar.pk)   # limpia la cached_property

    with pytest.raises(SuscripcionVencidaError):
        CategoryFactory(household=hogar)


@pytest.mark.django_db
def test_un_hogar_en_prueba_escribe_sin_problema(client):
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    assert client.get(reverse("budget:configurar")).status_code == 200
    # 200 porque el formulario vacio se re-renderiza con errores, no 403.
    assert client.post(reverse("budget:ingreso_nuevo"), {}).status_code == 200


@pytest.mark.django_db
def test_pagar_manda_a_stripe_con_el_idioma_y_el_hogar(client, monkeypatch):
    from django.urls import reverse

    from tests.factories import MembershipFactory

    capturado = {}

    def falso_crear(*, household, locale, url_exito, url_cancelacion):
        capturado["household"] = household
        capturado["locale"] = locale
        return "https://checkout.stripe.com/c/pay/fake"

    monkeypatch.setattr("apps.subscriptions.views.crear_sesion_de_pago", falso_crear)

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.post(reverse("subscriptions:pagar"))

    assert respuesta.status_code == 302
    assert respuesta["Location"].startswith("https://checkout.stripe.com/")
    assert capturado["household"] == hogar
    assert capturado["locale"] == "en"


@pytest.mark.django_db
def test_un_hogar_expirado_si_puede_pagar(client, monkeypatch):
    """La exencion del §2.2: si la guardia cubriera esto, un hogar expirado no
    podria pagar para dejar de estarlo."""
    from django.urls import reverse

    from tests.factories import MembershipFactory

    monkeypatch.setattr(
        "apps.subscriptions.views.crear_sesion_de_pago",
        lambda **kw: "https://checkout.stripe.com/c/pay/fake",
    )

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    assert client.post(reverse("subscriptions:pagar")).status_code == 302


@pytest.mark.django_db
def test_el_retorno_no_concede_nada(client):
    """§5.2: cualquiera puede visitar la URL de exito sin haber pagado."""
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.get(reverse("subscriptions:retorno"))

    assert respuesta.status_code == 200
    hogar.refresh_from_db()
    assert hogar.subscription.status == "trialing"
    assert hogar.subscription.paid_at is None


@pytest.mark.django_db
def test_un_get_a_pagar_no_revienta(client):
    """El plan mandaba a subscriptions:estado, que no existe hasta la Tarea 11.

    Sin esta prueba, un GET a esa ruta se iba en la rama como un 500 latente:
    ninguna otra prueba de la tarea entra por ahi.
    """
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.get(reverse("subscriptions:pagar"))

    assert respuesta.status_code == 302
    assert "checkout.stripe.com" not in respuesta["Location"]

import pytest
from datetime import timedelta

from django.test import override_settings
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
@override_settings(STRIPE_SECRET_KEY="sk_test_falsa")
def test_pagar_manda_a_stripe_con_el_idioma_y_el_hogar(client, monkeypatch):
    """La clave se declara aqui porque la vista comprueba que este puesta antes
    de llamar a la pasarela: sin ella la prueba pasaria por el aviso de
    "pagos sin configurar" y no llegaria a la funcion sustituida."""
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
@override_settings(STRIPE_SECRET_KEY="sk_test_falsa")
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

    respuesta = client.post(reverse("subscriptions:pagar"))
    assert respuesta.status_code == 302
    # Se comprueba el destino y no solo el 302: un 302 a la pantalla de estado
    # tambien es un 302, y entonces la prueba pasaria sin que el hogar expirado
    # hubiera llegado a la pasarela — que es justo lo que verifica.
    assert respuesta["Location"].startswith("https://checkout.stripe.com/")


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="")
def test_sin_clave_de_stripe_pagar_avisa_en_vez_de_reventar(client):
    """Sin clave, `stripe` lanzaria AuthenticationError y el administrador veria
    un 500 en el momento exacto en que intenta pagar para recuperar la escritura
    de su hogar. Tiene que ver un aviso y la pantalla de estado."""
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.post(reverse("subscriptions:pagar"), follow=True)

    assert respuesta.status_code == 200
    assert respuesta.redirect_chain[-1][0] == reverse("subscriptions:estado")
    avisos = [m.message for m in respuesta.context["messages"]]
    assert any("not configured" in a for a in avisos), avisos


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


@pytest.mark.django_db
def test_la_pantalla_de_suscripcion_dice_cuantos_dias_quedan(client):
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.get(reverse("subscriptions:estado"))

    assert respuesta.status_code == 200
    assert respuesta.context["suscripcion"].estado_visible == "trialing"


@pytest.mark.django_db
def test_un_403_por_suscripcion_ofrece_pagar(client):
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    respuesta = client.post(reverse("budget:ingreso_nuevo"), {})

    assert respuesta.status_code == 403
    assert reverse("subscriptions:estado") in respuesta.content.decode()


@pytest.mark.django_db
def test_un_get_a_pagar_lleva_a_la_pantalla_de_estado(client):
    """Cierra el apano de la Tarea 9: ese redirect apuntaba a households:ajustes
    porque subscriptions:estado no existia. Sin esta asercion, olvidarse de
    cambiarlo no habria roto ninguna prueba — el redirect funcionaba igual.
    """
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.get(reverse("subscriptions:pagar"))

    assert respuesta.status_code == 302
    assert respuesta["Location"] == reverse("subscriptions:estado")


@pytest.mark.django_db
def test_un_hogar_expirado_ve_el_boton_de_pagar(client):
    """La pantalla tiene que OFRECER pagar justo cuando hace falta."""
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    cuerpo = client.get(reverse("subscriptions:estado")).content.decode()

    assert respuesta_tiene_formulario_de_pago(cuerpo)


@pytest.mark.django_db
def test_un_hogar_ya_pagado_no_ve_el_boton_de_pagar(client):
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    hogar.subscription.status = Subscription.ACTIVE
    hogar.subscription.paid_at = timezone.now()
    hogar.subscription.save()
    client.force_login(user)

    cuerpo = client.get(reverse("subscriptions:estado")).content.decode()

    assert not respuesta_tiene_formulario_de_pago(cuerpo)


def respuesta_tiene_formulario_de_pago(cuerpo):
    from django.urls import reverse

    return f'action="{reverse("subscriptions:pagar")}"' in cuerpo

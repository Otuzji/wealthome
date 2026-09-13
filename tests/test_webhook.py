"""El webhook es publico y sin autenticar: se prueba hostil, no feliz."""

import json

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.subscriptions.models import StripeEvent, Subscription
from tests.factories import HouseholdFactory

URL = "/subscription/webhook/"


def _evento(hogar_pk, event_id="evt_1", tipo="checkout.session.completed"):
    return {
        "id": event_id,
        "type": tipo,
        "data": {"object": {
            "client_reference_id": str(hogar_pk),
            "id": "cs_test_1",
            "customer": "cus_1",
        }},
    }


@pytest.fixture
def sin_verificar_firma(monkeypatch):
    """Sustituye la verificacion: probamos el flujo, no la criptografia de Stripe."""
    def leer(cuerpo, firma):
        if firma != "buena":
            raise ValueError("firma invalida")
        return json.loads(cuerpo)

    monkeypatch.setattr("apps.subscriptions.views.leer_evento", leer)


@pytest.mark.django_db
def test_la_ruta_del_webhook_es_la_que_documenta_el_readme():
    """URL es una constante literal en este archivo: si alguien renombra la ruta,
    las otras ocho pruebas fallarian con un 404 despistante en vez de decir esto.
    """
    assert reverse("subscriptions:webhook") == URL


@pytest.mark.django_db
def test_un_pago_acredita_la_suscripcion(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk))

    respuesta = client.post(URL, cuerpo, content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="buena")

    assert respuesta.status_code == 200
    hogar.refresh_from_db()
    assert hogar.subscription.status == Subscription.ACTIVE
    assert hogar.subscription.paid_at is not None


@pytest.mark.django_db
def test_sin_firma_no_escribe_nada(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk))

    respuesta = client.post(URL, cuerpo, content_type="application/json")

    assert respuesta.status_code == 400
    hogar.refresh_from_db()
    assert hogar.subscription.status == Subscription.TRIALING
    assert not StripeEvent.objects.exists()


@pytest.mark.django_db
def test_con_firma_ajena_no_escribe_nada(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk))

    respuesta = client.post(URL, cuerpo, content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="mala")

    assert respuesta.status_code == 400
    assert not StripeEvent.objects.exists()


@pytest.mark.django_db
def test_el_mismo_evento_tres_veces_deja_el_mismo_estado(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk))
    for _i in range(3):
        respuesta = client.post(URL, cuerpo, content_type="application/json",
                                HTTP_STRIPE_SIGNATURE="buena")
        assert respuesta.status_code == 200

    assert StripeEvent.objects.count() == 1
    hogar.refresh_from_db()
    assert hogar.subscription.status == Subscription.ACTIVE


@pytest.mark.django_db
def test_un_tipo_desconocido_se_registra_y_devuelve_200(client, sin_verificar_firma):
    """Devolver error por un evento que no nos interesa hace que Stripe lo
    reintente para siempre."""
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk, event_id="evt_2", tipo="invoice.paid"))

    respuesta = client.post(URL, cuerpo, content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="buena")

    assert respuesta.status_code == 200
    assert StripeEvent.objects.filter(type="invoice.paid").exists()
    hogar.refresh_from_db()
    assert hogar.subscription.status == Subscription.TRIALING


@pytest.mark.django_db
def test_un_hogar_que_no_existe_devuelve_200_y_no_revienta(client, sin_verificar_firma):
    cuerpo = json.dumps(_evento(999999))

    respuesta = client.post(URL, cuerpo, content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="buena")

    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_una_referencia_que_no_es_un_numero_devuelve_200(client, sin_verificar_firma):
    """Entrada hostil: client_reference_id lo rellena quien llama, no nosotros.
    Sin el isdigit(), int() reventaria con un 500 y Stripe reintentaria eterno.
    """
    evento = _evento(1)
    evento["data"]["object"]["client_reference_id"] = "; DROP TABLE"

    respuesta = client.post(URL, json.dumps(evento), content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="buena")

    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_un_hogar_ya_activo_no_pierde_su_fecha_de_pago(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    antes = timezone.now()
    hogar.subscription.status = Subscription.ACTIVE
    hogar.subscription.paid_at = antes
    hogar.subscription.save()

    cuerpo = json.dumps(_evento(hogar.pk, event_id="evt_3"))
    client.post(URL, cuerpo, content_type="application/json",
                HTTP_STRIPE_SIGNATURE="buena")

    hogar.refresh_from_db()
    assert hogar.subscription.paid_at == antes


@pytest.mark.django_db
def test_un_cuerpo_que_no_es_json_devuelve_400(client, sin_verificar_firma):
    respuesta = client.post(URL, b"esto no es json", content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="buena")

    assert respuesta.status_code == 400


@pytest.mark.django_db
def test_un_get_al_webhook_no_pasa(client, sin_verificar_firma):
    """@require_POST: Stripe siempre manda POST, y un GET no debe llegar al cuerpo."""
    assert client.get(URL).status_code == 405

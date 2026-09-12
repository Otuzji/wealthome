"""Lo que se puede hacer con una suscripcion. No importa `stripe`."""

from django.db import transaction
from django.utils import timezone

from apps.households.models import Household

from .models import StripeEvent, Subscription

TIPO_QUE_ACREDITA = "checkout.session.completed"


def crear_suscripcion(household):
    """La suscripcion de un hogar recien creado: catorce dias, sin tarjeta."""
    suscripcion, _creada = Subscription.objects.get_or_create(household=household)
    return suscripcion


@transaction.atomic
def procesar_evento(evento):
    """Aplica un evento de Stripe una sola vez. Devuelve True si acredito pago.

    La idempotencia del §5.2 vive en el unique de StripeEvent.event_id mas el
    select_for_update sobre esa fila: Stripe reintenta, y reintenta EN
    PARALELO, asi que comprobar processed_at sin bloquear dejaria pasar dos.
    """
    fila, _creada = StripeEvent.objects.get_or_create(
        event_id=evento.get("id", ""),
        defaults={"type": evento.get("type", ""), "payload": evento},
    )
    fila = StripeEvent.objects.select_for_update().get(pk=fila.pk)
    if fila.processed_at is not None:
        return False

    acredito = False
    if fila.type == TIPO_QUE_ACREDITA:
        acredito = _acreditar(evento)

    fila.processed_at = timezone.now()
    fila.save(update_fields=["processed_at"])
    return acredito


def _acreditar(evento):
    objeto = evento.get("data", {}).get("object", {})
    referencia = objeto.get("client_reference_id") or ""
    # isdigit() y no un try/int: la referencia la rellena quien llama, y un 500
    # aqui haria que Stripe reintentara el mismo evento para siempre.
    if not referencia.isdigit():
        return False

    # Household NO es HouseholdScoped: .objects aqui es el manager normal.
    hogar = Household.objects.filter(pk=int(referencia)).first()
    if hogar is None:
        return False

    suscripcion = crear_suscripcion(hogar)
    if suscripcion.status == Subscription.ACTIVE:
        # Ya pagada: no se le pisa la fecha del pago de verdad.
        return False

    suscripcion.status = Subscription.ACTIVE
    suscripcion.paid_at = timezone.now()
    suscripcion.stripe_session_id = objeto.get("id", "") or ""
    suscripcion.stripe_customer_id = objeto.get("customer", "") or ""
    suscripcion.save(update_fields=[
        "status", "paid_at", "stripe_session_id", "stripe_customer_id",
    ])
    return True

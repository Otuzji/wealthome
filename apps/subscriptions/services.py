"""Lo que se puede hacer con una suscripcion. No importa `stripe`."""

from .models import Subscription


def crear_suscripcion(household):
    """La suscripcion de un hogar recien creado: catorce dias, sin tarjeta."""
    suscripcion, _creada = Subscription.objects.get_or_create(household=household)
    return suscripcion

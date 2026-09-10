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

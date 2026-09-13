"""La suscripcion del §5: un pago unico de CAD $25 tras catorce dias de prueba.

Ninguno de los dos modelos es HouseholdScoped. Subscription pertenece a un
hogar en el sentido de la titularidad, no del aislamiento —hay exactamente una
por hogar y se llega a ella por el hogar—, y StripeEvent no pertenece a
ninguno: es el registro de lo que Stripe nos conto.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField
from apps.households.models import Household


class SuscripcionVencidaError(Exception):
    """Se intento escribir en un hogar cuya suscripcion vencio (§5.2)."""


def _fin_de_la_prueba():
    return timezone.now() + timedelta(days=settings.DIAS_DE_PRUEBA)


class Subscription(models.Model):
    """El estado de pago de un hogar.

    `status` guarda `trialing` o `active`. **`expired` no se guarda nunca**: se
    deriva comparando trial_ends_at con el reloj. Un estado guardado exigiria
    que alguien lo escribiera a medianoche, y no hay cron en este stack — la
    misma razon que hizo perezoso el ciclo del mes.
    """

    TRIALING, ACTIVE = "trialing", "active"
    STATUS_CHOICES = [(TRIALING, _("Trial")), (ACTIVE, _("Active"))]
    EXPIRED = "expired"      # solo para estado_visible; nunca se guarda

    household = models.OneToOneField(
        Household, on_delete=models.CASCADE, related_name="subscription"
    )
    status = models.CharField(_("status"), max_length=10, choices=STATUS_CHOICES, default=TRIALING)
    trial_ends_at = models.DateTimeField(_("trial ends at"), default=_fin_de_la_prueba)
    stripe_customer_id = models.CharField(max_length=120, blank=True, default="")
    stripe_session_id = models.CharField(max_length=120, blank=True, default="")
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    # Se guardan para que un cambio de precio no reescriba lo que alguien pago.
    amount = MoneyField(_("amount"), default=None, null=True, blank=True)
    currency = models.CharField(max_length=3, default="CAD")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")

    def __str__(self):
        return f"{self.household} · {self.estado_visible}"

    @property
    def esta_vigente(self):
        if self.status == self.ACTIVE:
            return True
        return self.trial_ends_at > timezone.now()

    @property
    def estado_visible(self):
        if self.status == self.ACTIVE:
            return self.ACTIVE
        return self.TRIALING if self.esta_vigente else self.EXPIRED

    @property
    def dias_restantes(self):
        """Dias enteros de prueba que quedan. None si ya esta pagada."""
        if self.status == self.ACTIVE:
            return None
        return max(0, (self.trial_ends_at - timezone.now()).days)


class StripeEvent(models.Model):
    """La idempotencia del §5.2, hecha esquema.

    Stripe reintenta los webhooks, y los reintenta en paralelo. `event_id`
    unico es toda la idempotencia: sin el, un hogar puede quedar en un estado
    inconsistente por un reintento perfectamente normal.
    """

    event_id = models.CharField(max_length=120, unique=True)
    type = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Stripe event")
        verbose_name_plural = _("Stripe events")
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.type} · {self.event_id}"

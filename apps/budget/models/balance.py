from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

ASSET, LIABILITY = "asset", "liability"

# Los grupos del balance del hogar. El tipo (activo o pasivo) se deriva del
# grupo y no se guarda aparte: un dato que se puede contradecir no se
# almacena dos veces.
LIQUID, INVESTMENT, PROPERTY, VALUABLE = "liquid", "investment", "property", "valuable"
SHORT_TERM, LONG_TERM = "short_term", "long_term"

GRUPOS = [
    (LIQUID, ASSET, _("Cash and equivalents")),
    (INVESTMENT, ASSET, _("Investments")),
    (PROPERTY, ASSET, _("Property and real estate")),
    (VALUABLE, ASSET, _("Valuables")),
    (SHORT_TERM, LIABILITY, _("Short-term debt")),
    (LONG_TERM, LIABILITY, _("Long-term debt")),
]
GROUP_CHOICES = [(clave, etiqueta) for clave, _tipo, etiqueta in GRUPOS]
TIPO_DE_GRUPO = {clave: tipo for clave, tipo, _etiqueta in GRUPOS}


class BalanceItem(HouseholdScoped):
    """Una linea del balance del hogar: la casa, el auto, la hipoteca, la
    tarjeta. Se teclea y se actualiza a mano; el ahorro y el efectivo NO
    son filas de esta tabla, salen de lo que la aplicacion ya sabe (ver
    services_balance)."""

    group = models.CharField(_("group"), max_length=12, choices=GROUP_CHOICES)
    name = models.CharField(_("name"), max_length=80)
    amount = MoneyField(_("current value"))
    note = models.CharField(_("note"), max_length=200, blank=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("balance item")
        verbose_name_plural = _("balance items")
        ordering = ["group", "name"]

    def __str__(self):
        return f"{self.name} · {self.amount}"

    @property
    def kind(self):
        return TIPO_DE_GRUPO[self.group]

    @property
    def es_pasivo(self):
        return self.kind == LIABILITY

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount < Decimal("0.00"):
            # Una deuda se teclea en positivo: el grupo ya dice que resta.
            raise ValidationError({"amount": _("Enter the value as a positive number.")})

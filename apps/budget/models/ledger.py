from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .catalog import HOUSEHOLD, SCOPE_CHOICES
from .months import BudgetMonth, EscrituraAcotadaAlMes

PAYMENT_METHOD_CHOICES = [
    ("debit", _("Debit card")),
    ("credit", _("Credit card")),
    ("cash", _("Cash")),
    ("transfer", _("Transfer")),
    ("other", _("Other")),
]


class Transaction(EscrituraAcotadaAlMes, HouseholdScoped):
    """Lo que realmente pasó."""

    budget_month = models.ForeignKey(BudgetMonth, on_delete=models.PROTECT, related_name="transacciones")
    category = models.ForeignKey("budget.Category", on_delete=models.PROTECT, related_name="transacciones")
    merchant = models.ForeignKey(
        "budget.Merchant", on_delete=models.SET_NULL, null=True, blank=True, related_name="transacciones"
    )
    # Desviación 4: sin esta FK, el modo rolling_average del §4.1 no se puede
    # calcular — §3.3 definía Transaction sin ningún vínculo con IncomeSource.
    income_source = models.ForeignKey(
        "budget.IncomeSource", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transacciones",
        help_text=_("Which income this belongs to, so its average can be computed."),
    )
    amount = MoneyField(_("amount"))
    date = models.DateField(_("date"))
    member = models.ForeignKey("households.Membership", on_delete=models.PROTECT, related_name="transacciones")
    payment_method = models.CharField(
        _("paid with"), max_length=20, choices=PAYMENT_METHOD_CHOICES, default="debit"
    )
    scope = models.CharField(_("scope"), max_length=10, choices=SCOPE_CHOICES, default=HOUSEHOLD)
    note = models.CharField(_("note"), max_length=200, blank=True)
    budget_line = models.ForeignKey(
        "budget.BudgetLine", on_delete=models.SET_NULL, null=True, blank=True, related_name="transacciones"
    )
    # Fase 2. Entra anulable y sin usar; el destino real es Supabase Storage.
    receipt_image = models.ImageField(_("receipt"), upload_to="receipts/", null=True, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("transaction")
        verbose_name_plural = _("transactions")
        ordering = ["-date", "-pk"]

    def __str__(self):
        return f"{self.date} · {self.category} · {self.amount}"

    def clean(self):
        super().clean()
        for campo in ("category", "merchant", "income_source", "member", "budget_line"):
            relacionado = getattr(self, campo, None)
            if relacionado is not None and relacionado.household_id != self.household_id:
                raise ValidationError({campo: _("That belongs to another household.")})

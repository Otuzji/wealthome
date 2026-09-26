from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .catalog import EXPENSE, HOUSEHOLD, SCOPE_CHOICES
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

    # RESTRICT, no PROTECT: borrar el mes o la categoría por sí solos sigue
    # prohibido mientras existan transacciones — el registro de dinero que
    # realmente se movió no se puede destruir así. Pero borrar el hogar
    # entero tiene que funcionar, y con PROTECT nunca podría: el recolector
    # de Django encuentra estas mismas filas por la FK household en cascada
    # y, a la vez, por esta FK con PROTECT, y PROTECT no distingue — lanza
    # aunque la fila proscrita ya esté siendo borrada por la otra ruta.
    # RESTRICT sí distingue: solo lanza si la fila protegida NO va a
    # borrarse también en cascada dentro de la misma operación.
    budget_month = models.ForeignKey(BudgetMonth, on_delete=models.RESTRICT, related_name="transacciones")
    category = models.ForeignKey("budget.Category", on_delete=models.RESTRICT, related_name="transacciones")
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
    member = models.ForeignKey("households.Membership", on_delete=models.RESTRICT, related_name="transacciones")
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

    @property
    def partida_propia(self):
        """La partida puntual que nacio de este registro, si sigue siendo solo
        suya: alguien pudo haber pagado despues contra ella desde "What is it".
        La partida sigue al registro: se corrige, se borra y se muda con el.

        Con `pagos_en_su_linea` anotado no consulta: quien pinte muchas filas
        debe anotarlo (ver la vista del mes) o son dos consultas por fila.
        """
        linea = self.budget_line
        if linea is None or not linea.is_exceptional:
            return None
        if hasattr(self, "pagos_en_su_linea"):
            return linea if (self.pagos_en_su_linea or 0) <= 1 else None
        return None if linea.transacciones.exclude(pk=self.pk).exists() else linea

    @property
    def se_puede_posponer(self):
        """Solo un gasto que no estaba planificado se lleva al mes siguiente.

        Lo planificado —los ingresos y los gastos del plan— no se mueve: se
        corrige en Plan the month, que edita el mes entero. Y una partida
        puntual con mas de un pago tampoco: mudarla se llevaria pagos ajenos.
        """
        return self.category.kind == EXPENSE and self.partida_propia is not None

    def clean(self):
        super().clean()
        for campo in ("category", "merchant", "income_source", "member", "budget_line"):
            relacionado = getattr(self, campo, None)
            if relacionado is not None and relacionado.household_id != self.household_id:
                raise ValidationError({campo: _("That belongs to another household.")})

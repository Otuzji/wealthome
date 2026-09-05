from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.budget.engine import income as motor_income
from apps.budget.engine import periodicity as motor_periodicity
from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .catalog import HOUSEHOLD, SCOPE_CHOICES

PERIODICITY_CHOICES = [
    (motor_periodicity.WEEKLY, _("Weekly")),
    (motor_periodicity.BIWEEKLY, _("Every two weeks")),
    (motor_periodicity.SEMIMONTHLY, _("Twice a month")),
    (motor_periodicity.MONTHLY, _("Monthly")),
    (motor_periodicity.BIMONTHLY, _("Every two months")),
    (motor_periodicity.QUARTERLY, _("Quarterly")),
    (motor_periodicity.SEMIANNUAL, _("Twice a year")),
    (motor_periodicity.ANNUAL, _("Yearly")),
]

AMOUNT_TYPE_CHOICES = [
    (motor_income.FIXED, _("A fixed amount")),
    (motor_income.ESTIMATED, _("An amount I estimate each month")),
    (motor_income.RANGE, _("A range — the budget uses the minimum")),
    (motor_income.ROLLING_AVERAGE, _("The average of my last months")),
    (motor_income.IRREGULAR, _("Irregular — the budget counts zero")),
]

SOURCE_TYPE_CHOICES = [
    ("salary", _("Salary")),
    ("freelance", _("Freelance")),
    ("rental", _("Rental")),
    ("pension", _("Pension")),
    ("benefits", _("Benefits")),
    ("other", _("Other")),
]


class ReglaVigente(HouseholdScoped):
    """Lo común a las dos clases de regla.

    §3.2: LAS REGLAS NUNCA SE MUTAN. Subir el alquiler de $1800 a $1950 cierra
    la regla vieja con effective_to = 31 de marzo y crea una nueva con
    effective_from = 1 de abril. El historial queda intacto sin un modelo
    adicional, y "¿desde cuándo pagamos más?" es una consulta y no una
    investigación. Lo hace apps/budget/services.py::reemplazar_regla.
    """

    name = models.CharField(_("name"), max_length=120)
    periodicity = models.CharField(_("how often"), max_length=20, choices=PERIODICITY_CHOICES)
    effective_from = models.DateField(_("in effect from"))
    effective_to = models.DateField(_("in effect until"), null=True, blank=True)
    scope = models.CharField(_("scope"), max_length=10, choices=SCOPE_CHOICES, default=HOUSEHOLD)

    class Meta(HouseholdScoped.Meta):
        abstract = True

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": _("A rule cannot end before it starts.")})

    def ocurrencias_en(self, anio, mes):
        return motor_periodicity.ocurrencias(
            self.periodicity, self.effective_from, anio, mes, self.effective_to
        )


class IncomeSource(ReglaVigente):
    owner = models.ForeignKey(
        "households.Membership", on_delete=models.RESTRICT, related_name="income_sources"
    )
    source_type = models.CharField(_("kind of income"), max_length=20, choices=SOURCE_TYPE_CHOICES)
    amount_type = models.CharField(_("how much"), max_length=20, choices=AMOUNT_TYPE_CHOICES)
    amount = MoneyField(verbose_name=_("amount"), null=True, blank=True)
    amount_min = MoneyField(verbose_name=_("at least"), null=True, blank=True)
    amount_max = MoneyField(verbose_name=_("at most"), null=True, blank=True)

    class Meta(ReglaVigente.Meta):
        verbose_name = _("income source")
        verbose_name_plural = _("income sources")

    def clean(self):
        super().clean()
        if self.owner_id and self.owner.household_id != self.household_id:
            raise ValidationError({"owner": _("That member belongs to another household.")})
        if (
            self.amount_min is not None
            and self.amount_max is not None
            and self.amount_min > self.amount_max
        ):
            raise ValidationError(
                {"amount_max": _("The maximum cannot be lower than the minimum.")}
            )

    def cifra_del_mes(self, historial=()):
        """La cifra conservadora del §4.1. None significa 'aún no hay datos'."""
        return motor_income.cifra_conservadora(
            self.amount_type,
            amount=self.amount,
            amount_min=self.amount_min,
            amount_max=self.amount_max,
            historial=historial,
        )


class ExpenseRule(ReglaVigente):
    category = models.ForeignKey("budget.Category", on_delete=models.RESTRICT, related_name="expense_rules")
    amount = MoneyField(verbose_name=_("amount"))
    is_essential = models.BooleanField(
        _("essential"),
        default=True,
        help_text=_("Essential expenses are the last ones a recommendation will touch."),
    )
    owner = models.ForeignKey(
        "households.Membership", on_delete=models.RESTRICT,
        null=True, blank=True, related_name="expense_rules",
    )

    class Meta(ReglaVigente.Meta):
        verbose_name = _("fixed expense")
        verbose_name_plural = _("fixed expenses")

    def clean(self):
        super().clean()
        if self.category_id and self.category.household_id != self.household_id:
            raise ValidationError({"category": _("That category belongs to another household.")})
        if self.owner_id and self.owner.household_id != self.household_id:
            raise ValidationError({"owner": _("That member belongs to another household.")})

    def importe_del_mes(self, anio, mes):
        return motor_periodicity.importe_del_mes(
            self.amount, self.periodicity, self.effective_from, anio, mes, self.effective_to
        )

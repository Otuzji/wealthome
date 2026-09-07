from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.budget.engine import goals as motor_goals
from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .catalog import HOUSEHOLD, SCOPE_CHOICES
from .months import BudgetMonth, EscrituraAcotadaAlMes

CONTRIBUTION_MODE_CHOICES = [
    (motor_goals.BY_TARGET_DATE, _("By a target date")),
    (motor_goals.BY_MONTHLY_AMOUNT, _("By a monthly amount")),
]

ORIGEN_CHOICES = [("manual", _("Added by hand")), ("cascade", _("From the monthly split"))]


class Goal(HouseholdScoped):
    ACTIVE, REACHED, ABANDONED = "active", "reached", "abandoned"
    STATUS_CHOICES = [
        (ACTIVE, _("Active")), (REACHED, _("Reached")), (ABANDONED, _("Abandoned"))
    ]

    name = models.CharField(_("goal"), max_length=120)
    scope = models.CharField(_("scope"), max_length=10, choices=SCOPE_CHOICES, default=HOUSEHOLD)
    owner = models.ForeignKey(
        "households.Membership", on_delete=models.RESTRICT, null=True, blank=True, related_name="goals"
    )
    status = models.CharField(_("status"), max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    contribution_mode = models.CharField(
        _("how to reach it"), max_length=20, choices=CONTRIBUTION_MODE_CHOICES
    )
    target_amount = MoneyField(_("target amount"))
    target_date = models.DateField(_("target date"), null=True, blank=True)
    monthly_amount = MoneyField(_("monthly amount"), null=True, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("goal")
        verbose_name_plural = _("goals")

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.contribution_mode == motor_goals.BY_TARGET_DATE and not self.target_date:
            raise ValidationError({"target_date": _("Pick the date you want to reach it by.")})
        if self.contribution_mode == motor_goals.BY_MONTHLY_AMOUNT and not self.monthly_amount:
            raise ValidationError({"monthly_amount": _("Say how much you will put in each month.")})

    def acumulado(self):
        total = self.contributions.aggregate(total=models.Sum("amount"))["total"]
        return total if total is not None else Decimal("0.00")

    def derivar(self, desde=None):
        """El dato que falta: el aporte mensual o la fecha de llegada."""
        return motor_goals.derivar(
            self.contribution_mode,
            objetivo=self.target_amount,
            acumulado=self.acumulado(),
            desde=desde or timezone.localdate(),
            fecha_objetivo=self.target_date,
            aporte_mensual=self.monthly_amount,
        )


class GoalContribution(EscrituraAcotadaAlMes, HouseholdScoped):
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="contributions")
    amount = MoneyField(_("amount"))
    date = models.DateField(_("date"))
    budget_month = models.ForeignKey(
        BudgetMonth, on_delete=models.CASCADE, null=True, blank=True,
        related_name="aportes",
        help_text=_("Nulo si la fecha cae en un mes que el hogar no ha vivido."),
    )
    member = models.ForeignKey(
        "households.Membership", on_delete=models.RESTRICT,
        null=True, blank=True, related_name="goal_contributions",
        help_text=_("Nulo cuando el aporte viene del reparto: ahorra el hogar, no una persona."),
    )
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default="manual")

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("contribution")
        verbose_name_plural = _("contributions")
        ordering = ["-date", "-pk"]

    def __str__(self):
        return f"{self.goal} · {self.amount}"

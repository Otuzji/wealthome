from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.budget.engine import allowance as motor_allowance
from apps.budget.engine import cascade as motor_cascade
from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .months import BudgetMonth

TARGET_TYPE_CHOICES = [
    (motor_cascade.GOAL, _("A savings goal")),
    (motor_cascade.ALLOWANCE, _("Personal allowance")),
    (motor_cascade.CATEGORY, _("A category or fund")),
]

METHOD_CHOICES = [
    (motor_cascade.FIXED, _("A fixed amount")),
    (motor_cascade.PERCENTAGE, _("A percentage of what is left over")),
    (motor_cascade.REMAINDER, _("Everything that is left")),
]

EQUAL = "equal"
WEIGHTED = "weighted"
SPLIT_CHOICES = [(EQUAL, _("Equally")), (WEIGHTED, _("By weights"))]


class AllocationRule(HouseholdScoped):
    """Una regla del reparto en cascada (§4.5).

    `order` define la prioridad: el sobrante cae por las reglas de menor a
    mayor. Con el ahorro arriba y las mesadas abajo, un mes flojo se come la
    diversión y no el ahorro; una familia que prefiera lo contrario solo
    reordena las reglas.
    """

    order = models.PositiveSmallIntegerField(_("priority"))
    target_type = models.CharField(_("goes to"), max_length=12, choices=TARGET_TYPE_CHOICES)
    target_goal = models.ForeignKey(
        "budget.Goal", on_delete=models.CASCADE, null=True, blank=True, related_name="allocation_rules"
    )
    target_category = models.ForeignKey(
        "budget.Category", on_delete=models.RESTRICT, null=True, blank=True, related_name="allocation_rules"
    )
    method = models.CharField(_("how much"), max_length=12, choices=METHOD_CHOICES)
    amount = MoneyField(_("amount"), null=True, blank=True)
    percentage = models.DecimalField(
        _("percentage"), max_digits=5, decimal_places=4, null=True, blank=True,
        help_text=_("0.10 means ten percent of what is left over."),
    )
    split = models.CharField(_("split"), max_length=10, choices=SPLIT_CHOICES, default=EQUAL)
    pesos = models.JSONField(default=dict, blank=True, help_text=_("Membership id to weight."))
    is_active = models.BooleanField(_("active"), default=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("split rule")
        verbose_name_plural = _("split rules")
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["household", "order"], name="un_orden_de_reparto_por_hogar")
        ]

    def __str__(self):
        return f"{self.order}. {self.get_target_type_display()}"

    def clean(self):
        super().clean()
        if self.method == motor_cascade.FIXED and self.amount is None:
            raise ValidationError({"amount": _("A fixed rule needs an amount.")})
        if self.method == motor_cascade.PERCENTAGE and self.percentage is None:
            raise ValidationError({"percentage": _("A percentage rule needs a percentage.")})
        if self.target_type == motor_cascade.GOAL and not self.target_goal_id:
            raise ValidationError({"target_goal": _("Pick the goal this goes to.")})
        if self.target_type == motor_cascade.CATEGORY and not self.target_category_id:
            raise ValidationError({"target_category": _("Pick the category this goes to.")})
        if self.target_goal_id and self.target_category_id:
            # a_regla_de_reparto resuelve destino_id = target_goal_id or
            # target_category_id, que preferiría el objetivo en silencio.
            # Como BudgetLine.kind frente a Category.kind, o amount_min
            # frente a amount_max en IncomeSource: un dato contradictorio se
            # rechaza aquí, no se resuelve por orden de campo.
            raise ValidationError(
                {"target_category": _("A rule cannot go to both a goal and a category at once.")}
            )

    def a_regla_de_reparto(self, miembros=()):
        """La traduce al tipo del motor. Es el único puente ORM → engine."""
        miembros = tuple(miembros)
        pesos = None
        if self.split == WEIGHTED and self.pesos:
            pesos = tuple(Decimal(str(self.pesos.get(str(m), 1))) for m in miembros)
        return motor_cascade.ReglaReparto(
            orden=self.order,
            destino=self.target_type,
            metodo=self.method,
            importe=self.amount,
            porcentaje=self.percentage,
            destino_id=self.target_goal_id or self.target_category_id,
            miembros=miembros if self.target_type == motor_cascade.ALLOWANCE else (),
            pesos=pesos,
        )


class MonthlyAllocation(HouseholdScoped):
    """El reparto materializado de un mes."""

    budget_month = models.ForeignKey(BudgetMonth, on_delete=models.CASCADE, related_name="asignaciones")
    rule = models.ForeignKey(AllocationRule, on_delete=models.RESTRICT, related_name="asignaciones")
    planned_amount = MoneyField(_("planned"))
    actual_amount = MoneyField(_("actual"), null=True, blank=True)
    member = models.ForeignKey(
        "households.Membership", on_delete=models.RESTRICT, null=True, blank=True, related_name="asignaciones"
    )

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("monthly split")
        verbose_name_plural = _("monthly splits")


class AllowanceLedger(HouseholdScoped):
    """El saldo de mesada de cada miembro (§3.3).

    Es un libro mayor, no un campo mutable: cada mes es una fila y el saldo se
    deriva sumando. Así "¿por qué tengo $145 este mes?" siempre tiene
    respuesta.
    """

    member = models.ForeignKey(
        "households.Membership", on_delete=models.RESTRICT, related_name="mesadas"
    )
    budget_month = models.ForeignKey(BudgetMonth, on_delete=models.CASCADE, related_name="mesadas")
    granted = MoneyField(_("granted"), default=Decimal("0.00"))
    spent = MoneyField(_("spent"), default=Decimal("0.00"))
    adjustment = MoneyField(_("adjustment"), default=Decimal("0.00"))
    carried_in = MoneyField(_("carried in"), default=Decimal("0.00"))
    carried_out = MoneyField(_("carried out"), default=Decimal("0.00"))

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("allowance")
        verbose_name_plural = _("allowances")
        constraints = [
            models.UniqueConstraint(
                fields=["household", "member", "budget_month"], name="una_mesada_por_miembro_y_mes"
            )
        ]

    def __str__(self):
        return f"{self.member} · {self.budget_month} · {self.saldo()}"

    def saldo(self):
        return motor_allowance.saldo(self.carried_in, self.granted, self.adjustment, self.spent)

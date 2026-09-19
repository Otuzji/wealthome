from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .catalog import EXPENSE, HOUSEHOLD, KIND_CHOICES, SCOPE_CHOICES

DIAS_PARA_EL_CIERRE_AUTOMATICO = 5


class MesCerrado(Exception):
    """Se intentó escribir en un mes que ya está cerrado."""


class BudgetMonth(HouseholdScoped):
    """El ciclo de vida del §4.2: futuro → abierto → cerrado.

    Los meses `future` NO existen como filas: se calculan desde las reglas al
    consultarlos, para que cambiar el alquiler se refleje al instante en todos
    los meses futuros (§2.3). El estado FUTURE existe solo para el instante
    entre crear la fila y materializarla.
    """

    FUTURE, OPEN, CLOSED = "future", "open", "closed"
    STATUS_CHOICES = [(FUTURE, _("Upcoming")), (OPEN, _("Open")), (CLOSED, _("Closed"))]

    year = models.PositiveSmallIntegerField(_("year"))
    month = models.PositiveSmallIntegerField(_("month"))
    status = models.CharField(_("status"), max_length=10, choices=STATUS_CHOICES, default=OPEN)
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("budget month")
        verbose_name_plural = _("budget months")
        ordering = ["year", "month"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "year", "month"], name="un_mes_por_hogar"
            )
        ]

    def __str__(self):
        return f"{self.year}-{self.month:02d}"

    @property
    def esta_cerrado(self):
        return self.status == self.CLOSED


class EscrituraAcotadaAlMes(models.Model):
    """Base de todo lo que se escribe dentro de un mes.

    Rechaza la escritura si el mes está cerrado (§9) y comprueba que el hogar
    denormalizado coincida con el de su mes. Un CheckConstraint no puede
    cruzar tablas, así que esto vive en Python.

    Alcance real de la guarda, para que Tarea 12 y el Plan 3 no lean aquí más
    de lo que hay: cubre todo `save()`, incluido con `update_fields`, porque
    ambos pasan por este método sobrescrito. NO cubre `queryset.update()` ni
    `bulk_create()` — ninguno de los dos llama a `save()`, así que quedan
    prohibidos por convención sobre estos modelos, no por esta guarda.
    """

    class Meta:
        abstract = True

    def _mes(self):
        return self.budget_month

    def clean(self):
        super().clean()
        if self.budget_month_id and self.household_id != self.budget_month.household_id:
            raise ValidationError(
                {"household": _("This row does not belong to the same household as its month.")}
            )

    def save(self, *args, **kwargs):
        if self.budget_month_id and self._mes().esta_cerrado:
            raise MesCerrado(
                f"El mes {self._mes()} está cerrado y no admite escrituras."
            )
        super().save(*args, **kwargs)


class BudgetLine(EscrituraAcotadaAlMes, HouseholdScoped):
    """Las filas materializadas de un mes abierto.

    Lo excepcional vive aquí: el viaje, la matrícula, los regalos de Navidad.
    Se agregan al mes abierto y no afectan a ningún otro mes.
    """

    budget_month = models.ForeignKey(BudgetMonth, on_delete=models.CASCADE, related_name="lineas")
    category = models.ForeignKey("budget.Category", on_delete=models.RESTRICT, related_name="lineas")
    kind = models.CharField(_("kind"), max_length=10, choices=KIND_CHOICES, default=EXPENSE)
    planned_amount = MoneyField(_("planned"))
    is_exceptional = models.BooleanField(_("one-off"), default=False)
    # Desviación 2: dos FK anulables en vez de un source_rule genérico. Una
    # regla es o una IncomeSource o una ExpenseRule; una FK genérica
    # arrastraría contenttypes a cambio de nada.
    source_income = models.ForeignKey(
        "budget.IncomeSource", on_delete=models.SET_NULL, null=True, blank=True, related_name="lineas"
    )
    source_expense_rule = models.ForeignKey(
        "budget.ExpenseRule", on_delete=models.SET_NULL, null=True, blank=True, related_name="lineas"
    )
    owner = models.ForeignKey(
        "households.Membership", on_delete=models.RESTRICT, null=True, blank=True, related_name="lineas"
    )
    scope = models.CharField(_("scope"), max_length=10, choices=SCOPE_CHOICES, default=HOUSEHOLD)
    note = models.CharField(_("note"), max_length=200, blank=True)
    # El vencimiento. Para una linea nacida de una regla es la fecha en que esa
    # regla dispara (una linea por disparo); para una puntual, la que se teclee.
    due_date = models.DateField(_("due date"), null=True, blank=True)

    PENDIENTE, PARCIAL, PAGADA = "pending", "partial", "paid"

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("budget line")
        verbose_name_plural = _("budget lines")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(source_income__isnull=True) | models.Q(source_expense_rule__isnull=True),
                name="una_linea_viene_de_una_sola_regla",
            )
        ]

    def __str__(self):
        return f"{self.category} · {self.planned_amount}"

    @property
    def nombre(self):
        """Como la nombra el asistente: la regla de la que viene, o su nota."""
        regla = self.source_income or self.source_expense_rule
        if regla is not None:
            return regla.name
        return self.note or self.category.etiqueta()

    @property
    def pagado(self):
        """Lo registrado contra esta linea. Una consulta por linea: quien pinte
        muchas lineas debe anotar `pagado_total` en el queryset (ver
        `BudgetLine.con_pagos`)."""
        if hasattr(self, "pagado_total"):
            return self.pagado_total or Decimal("0.00")
        total = self.transacciones.aggregate(total=models.Sum("amount"))["total"]
        return total or Decimal("0.00")

    @property
    def restante(self):
        return max(self.planned_amount - self.pagado, Decimal("0.00"))

    @property
    def estado(self):
        """Pagada si lo registrado alcanza lo planeado; parcial si hay algo."""
        pagado = self.pagado
        if pagado >= self.planned_amount:
            return self.PAGADA
        if pagado > 0:
            return self.PARCIAL
        return self.PENDIENTE

    def clean(self):
        super().clean()
        # Hallazgo de la revisión de la Tarea 7: engine/closing.py podía
        # producir una varianza inatribuible si una categoría llegaba con una
        # línea de ingreso y otra de gasto. Tarea 12 lee linea.kind para lo
        # presupuestado y tx.category.kind para lo real: dos fuentes que no
        # pueden discrepar, así que se valida aquí que coincidan.
        if self.category_id and self.kind != self.category.kind:
            raise ValidationError(
                {"kind": _("This line's kind must match its category's kind.")}
            )


class MonthlyClose(HouseholdScoped):
    """La foto congelada del mes. INMUTABLE una vez escrita (§3.3).

    Un balance que se puede reescribir no es un balance: el usuario que
    consulta enero dentro de un año tiene que ver lo que vio entonces.
    """

    budget_month = models.OneToOneField(BudgetMonth, on_delete=models.CASCADE, related_name="cierre")
    ingresos_presupuestados = MoneyField()
    ingresos_reales = MoneyField()
    egresos_presupuestados = MoneyField()
    egresos_reales = MoneyField()
    varianza_por_categoria = models.JSONField(default=dict)
    balance = MoneyField()
    arrastre = MoneyField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("monthly close")
        verbose_name_plural = _("monthly closes")

    def __str__(self):
        return f"Cierre de {self.budget_month}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise MesCerrado("Un cierre mensual es inmutable: no se puede modificar.")
        super().save(*args, **kwargs)

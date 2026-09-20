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
    (motor_goals.OPEN_FUND, _("An open fund, no target")),
]

# Un GoalContribution es EL MOVIMIENTO de una meta, con signo: lo que entra
# (a mano, de la cascada, de otra meta) es positivo; lo que sale (un retiro,
# a otra meta) es negativo. El saldo de la meta es la suma de sus filas.
MANUAL, CASCADE, WITHDRAWAL, TRANSFER_OUT, TRANSFER_IN = (
    "manual", "cascade", "withdrawal", "transfer_out", "transfer_in"
)
ORIGEN_CHOICES = [
    (MANUAL, _("Added by hand")),
    (CASCADE, _("From the monthly split")),
    (WITHDRAWAL, _("Withdrawal")),
    (TRANSFER_OUT, _("Transfer to another goal")),
    (TRANSFER_IN, _("Transfer from another goal")),
]
ENTRADAS = (MANUAL, CASCADE, TRANSFER_IN)
SALIDAS = (WITHDRAWAL, TRANSFER_OUT)


class Goal(HouseholdScoped):
    ACTIVE, REACHED, ABANDONED, ARCHIVED = "active", "reached", "abandoned", "archived"
    STATUS_CHOICES = [
        (ACTIVE, _("Active")), (REACHED, _("Reached")), (ABANDONED, _("Abandoned")),
        # Saldo cero y un cierre que la referencia: no se puede borrar, se
        # guarda fuera de Goals y sigue contando en Balance.
        (ARCHIVED, _("Archived")),
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
    target_amount = MoneyField(_("target amount"), null=True, blank=True)
    target_date = models.DateField(_("target date"), null=True, blank=True)
    monthly_amount = MoneyField(_("monthly amount"), null=True, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("goal")
        verbose_name_plural = _("goals")

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        modo = self.contribution_mode
        if modo == motor_goals.OPEN_FUND:
            # Un fondo no tiene a donde llegar: un objetivo o una fecha aqui
            # es un dato contradictorio, y se rechaza en vez de ignorarse.
            if self.target_amount is not None:
                raise ValidationError({"target_amount": _("An open fund has no target amount.")})
            if self.target_date is not None:
                raise ValidationError({"target_date": _("An open fund has no target date.")})
            return
        if self.target_amount is None:
            raise ValidationError({"target_amount": _("Say how much you want to reach.")})
        if modo == motor_goals.BY_TARGET_DATE and not self.target_date:
            raise ValidationError({"target_date": _("Pick the date you want to reach it by.")})
        if modo == motor_goals.BY_MONTHLY_AMOUNT and not self.monthly_amount:
            raise ValidationError({"monthly_amount": _("Say how much you will put in each month.")})

    @property
    def es_fondo(self):
        return self.contribution_mode == motor_goals.OPEN_FUND

    @property
    def esta_activa(self):
        return self.status == self.ACTIVE

    def alcanzada(self, acumulado):
        """Cubierta con lo aportado. Es lo UNICO que decide `reached`: la
        fecha objetivo no cuenta, una meta tarde sigue activa. Un fondo
        abierto no tiene a donde llegar y nunca lo esta."""
        if self.target_amount is None:
            return False
        return acumulado >= self.target_amount

    def acumulado(self):
        """Lo aportado a esta meta hasta hoy.

        Si `contributions` ya viene prefetched, suma en PYTHON. `.aggregate()`
        va siempre a la base y no mira el prefetch, asi que en una pantalla que
        liste metas era una consulta por meta — un N+1 que el tope de consultas
        de la Tarea 4 no vio porque se fijo con cinco metas y solo comprobaba
        que no creciera con las TRANSACCIONES, no con las metas. Con 20 metas se
        iban 26 consultas donde ahora van 11.
        """
        if "contributions" in getattr(self, "_prefetched_objects_cache", {}):
            return sum((c.amount for c in self.contributions.all()), Decimal("0.00"))
        total = self.contributions.aggregate(total=models.Sum("amount"))["total"]
        return total if total is not None else Decimal("0.00")

    def derivar(self, desde=None, acumulado=None):
        """El dato que falta: el aporte mensual o la fecha de llegada.

        `acumulado` se puede pasar ya calculado: quien pinta una lista de metas
        lo necesita tambien para la barra de progreso, y calcularlo dos veces
        es una consulta por meta y por pantalla.
        """
        return motor_goals.derivar(
            self.contribution_mode,
            objetivo=self.target_amount,
            acumulado=self.acumulado() if acumulado is None else acumulado,
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
    origen = models.CharField(max_length=12, choices=ORIGEN_CHOICES, default=MANUAL)
    note = models.CharField(_("note"), max_length=200, blank=True,
                            help_text=_("Where it came from, or what it went to."))
    # Los dos lados de una transferencia se apuntan entre si. CASCADE: borrar
    # un lado borra el otro, y el saldo de las dos metas vuelve a cuadrar.
    counterpart = models.OneToOneField(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="+",
    )

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("contribution")
        verbose_name_plural = _("contributions")
        ordering = ["-date", "-pk"]

    def __str__(self):
        return f"{self.goal} · {self.amount}"

    @property
    def es_salida(self):
        return self.origen in SALIDAS

    def clean(self):
        super().clean()
        if self.amount is None or self.amount == 0:
            raise ValidationError({"amount": _("Put in more than zero.")})
        if self.origen in ENTRADAS and self.amount < 0:
            raise ValidationError({"amount": _("Money coming in is a positive amount.")})
        if self.origen in SALIDAS and self.amount > 0:
            raise ValidationError({"amount": _("Money going out is a negative amount.")})

"""Los formularios de alta del presupuesto.

Todos heredan de `HouseholdScopedModelForm`: el hogar es obligatorio y de solo
palabra clave, y acota tanto el render como la validación. Un `<select>` con
las categorías de otra familia no llega a existir.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.budget.engine.merchants import normalizar
from apps.households.scoped_forms import HouseholdScopedModelForm

from .models import (
    AllocationRule,
    BudgetLine,
    Category,
    ExpenseRule,
    Goal,
    GoalContribution,
    IncomeSource,
    Merchant,
    Transaction,
)


class CategoryForm(HouseholdScopedModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "kind"]


class IncomeSourceForm(HouseholdScopedModelForm):
    class Meta:
        model = IncomeSource
        fields = [
            "owner", "name", "source_type", "amount_type",
            "amount", "amount_min", "amount_max",
            "periodicity", "effective_from", "effective_to", "scope",
        ]
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `owner` es una Membership, que no hereda de HouseholdScoped, así que
        # la base no lo acota: hay que hacerlo aquí o el <select> traería los
        # miembros de todas las familias.
        self.fields["owner"].queryset = self.household.active_memberships()


class ExpenseRuleForm(HouseholdScopedModelForm):
    class Meta:
        model = ExpenseRule
        fields = [
            "category", "name", "amount", "periodicity",
            "effective_from", "effective_to", "is_essential", "owner", "scope",
        ]
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = self.household.active_memberships()
        self.fields["owner"].required = False


class AllocationRuleForm(HouseholdScopedModelForm):
    class Meta:
        model = AllocationRule
        fields = [
            "order", "target_type", "target_goal", "target_category",
            "method", "amount", "percentage", "split", "is_active",
        ]


class TransactionForm(HouseholdScopedModelForm):
    """`member` y `budget_month` NO son campos: salen de la petición y del
    ciclo del mes. Si `member` lo fuera, cualquiera podría registrar gastos a
    nombre de otro.

    `merchant` tampoco es un desplegable: nadie da de alta un comercio antes
    de comprar en él. Se teclea el nombre tal como aparece en el recibo y
    `Merchant.normalized_name` decide si es uno que ya existe — que es
    exactamente para lo que existe engine/merchants.py. Un `<select>` de
    comercios estaría vacío el primer día y sería inservible el centésimo.
    """

    merchant_name = forms.CharField(
        label=_("Where"), max_length=120, required=False,
        help_text=_("Type it as it appears on the receipt."),
    )

    class Meta:
        model = Transaction
        fields = ["category", "income_source", "amount", "date",
                  "payment_method", "scope", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def comercio(self):
        """El comercio tecleado, reutilizando el que ya exista en el hogar."""
        nombre = self.cleaned_data.get("merchant_name", "").strip()
        if not nombre:
            return None
        normalizado = normalizar(nombre)
        existente = Merchant.objects.for_household(self.household).filter(
            normalized_name=normalizado
        ).first()
        if existente is not None:
            return existente
        comercio = Merchant(household=self.household, name=nombre)
        comercio.save()
        return comercio


class GoalForm(HouseholdScopedModelForm):
    class Meta:
        model = Goal
        fields = ["name", "scope", "owner", "contribution_mode",
                  "target_amount", "target_date", "monthly_amount"]
        widgets = {"target_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = self.household.active_memberships()
        self.fields["owner"].required = False


class GoalContributionForm(HouseholdScopedModelForm):
    class Meta:
        model = GoalContribution
        fields = ["goal", "amount", "date"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


class BudgetLineForm(HouseholdScopedModelForm):
    """Las partidas excepcionales del paso 2 del §4.5.6.

    Sin este formulario, `is_exceptional` era un campo que nadie podia poner:
    materializar solo escribe lineas nacidas de una regla. Una linea sin
    source_income ni source_expense_rule ES una linea excepcional (§5.3 del
    diseno del Plan 2), asi que el formulario no ofrece esos dos campos y la
    vista marca is_exceptional.
    """

    class Meta:
        model = BudgetLine
        fields = ["category", "kind", "planned_amount", "scope", "owner", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `owner` es una Membership, que no hereda de HouseholdScoped, asi que la
        # base no lo acota: mismo caso que IncomeSourceForm.
        self.fields["owner"].queryset = self.household.active_memberships()
        self.fields["owner"].required = False

"""Los formularios de alta del presupuesto.

Todos heredan de `HouseholdScopedModelForm`: el hogar es obligatorio y de solo
palabra clave, y acota tanto el render como la validación. Un `<select>` con
las categorías de otra familia no llega a existir.
"""

from django import forms

from apps.households.scoped_forms import HouseholdScopedModelForm

from .models import AllocationRule, Category, ExpenseRule, IncomeSource


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

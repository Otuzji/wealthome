from django.contrib import admin

from apps.households.admin import HouseholdScopedAdmin

from .models import (
    AllocationRule,
    AllowanceLedger,
    BalanceItem,
    BudgetLine,
    BudgetMonth,
    Category,
    ExpenseRule,
    Goal,
    GoalContribution,
    IncomeSource,
    Merchant,
    MonthlyAllocation,
    MonthlyClose,
    Transaction,
)

# Todos con el mixin: un ModelAdmin normal lanza RuntimeError al listar y al
# construir su formulario, porque el manager estricto es _default_manager.
for modelo in (
    Category, Merchant, IncomeSource, ExpenseRule, BudgetMonth, BudgetLine,
    MonthlyClose, Transaction, Goal, GoalContribution, AllocationRule,
    MonthlyAllocation, AllowanceLedger, BalanceItem,
):
    admin.site.register(modelo, HouseholdScopedAdmin)

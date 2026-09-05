from datetime import date
from decimal import Decimal

import factory

from apps.budget.engine import cascade as motor_cascade
from apps.budget.engine.goals import BY_TARGET_DATE
from apps.budget.engine.income import FIXED
from apps.budget.engine.periodicity import MONTHLY
from tests.factories import HouseholdFactory, HouseholdScopedFactory, MembershipFactory


class CategoryFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.Category"

    household = factory.SubFactory(HouseholdFactory)
    slug = factory.Sequence(lambda n: f"categoria-{n}")
    kind = "expense"


class MerchantFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.Merchant"

    household = factory.SubFactory(HouseholdFactory)
    name = factory.Sequence(lambda n: f"Comercio {n}")


class IncomeSourceFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.IncomeSource"

    household = factory.SubFactory(HouseholdFactory)
    owner = factory.LazyAttribute(
        lambda o: MembershipFactory(household=o.household)
    )
    name = factory.Sequence(lambda n: f"Ingreso {n}")
    source_type = "salary"
    amount_type = FIXED
    amount = Decimal("3000.00")
    periodicity = MONTHLY
    effective_from = date(2026, 1, 1)


class ExpenseRuleFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.ExpenseRule"

    household = factory.SubFactory(HouseholdFactory)
    category = factory.LazyAttribute(lambda o: CategoryFactory(household=o.household))
    name = factory.Sequence(lambda n: f"Gasto {n}")
    amount = Decimal("1800.00")
    periodicity = MONTHLY
    effective_from = date(2026, 1, 1)


class BudgetMonthFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.BudgetMonth"

    household = factory.SubFactory(HouseholdFactory)
    year = 2026
    month = factory.Sequence(lambda n: (n % 12) + 1)
    status = "open"


class BudgetLineFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.BudgetLine"

    household = factory.SubFactory(HouseholdFactory)
    budget_month = factory.LazyAttribute(lambda o: BudgetMonthFactory(household=o.household))
    category = factory.LazyAttribute(lambda o: CategoryFactory(household=o.household))
    kind = "expense"
    planned_amount = Decimal("100.00")


class TransactionFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.Transaction"

    household = factory.SubFactory(HouseholdFactory)
    budget_month = factory.LazyAttribute(lambda o: BudgetMonthFactory(household=o.household))
    category = factory.LazyAttribute(lambda o: CategoryFactory(household=o.household))
    member = factory.LazyAttribute(lambda o: MembershipFactory(household=o.household))
    amount = Decimal("50.00")
    date = date(2026, 1, 15)


class MonthlyCloseFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.MonthlyClose"

    household = factory.SubFactory(HouseholdFactory)
    budget_month = factory.LazyAttribute(lambda o: BudgetMonthFactory(household=o.household))
    ingresos_presupuestados = Decimal("0.00")
    ingresos_reales = Decimal("0.00")
    egresos_presupuestados = Decimal("0.00")
    egresos_reales = Decimal("0.00")
    balance = Decimal("0.00")
    arrastre = Decimal("0.00")


class GoalFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.Goal"

    household = factory.SubFactory(HouseholdFactory)
    name = factory.Sequence(lambda n: f"Meta {n}")
    contribution_mode = BY_TARGET_DATE
    target_amount = Decimal("1000.00")
    target_date = date(2027, 1, 1)


class GoalContributionFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.GoalContribution"

    household = factory.SubFactory(HouseholdFactory)
    goal = factory.LazyAttribute(lambda o: GoalFactory(household=o.household))
    member = factory.LazyAttribute(lambda o: MembershipFactory(household=o.household))
    amount = Decimal("50.00")
    date = date(2026, 1, 15)


class AllocationRuleFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.AllocationRule"

    household = factory.SubFactory(HouseholdFactory)
    order = factory.Sequence(lambda n: n + 1)
    target_type = motor_cascade.ALLOWANCE
    method = motor_cascade.FIXED
    amount = Decimal("50.00")


class MonthlyAllocationFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.MonthlyAllocation"

    household = factory.SubFactory(HouseholdFactory)
    budget_month = factory.LazyAttribute(lambda o: BudgetMonthFactory(household=o.household))
    rule = factory.LazyAttribute(lambda o: AllocationRuleFactory(household=o.household))
    planned_amount = Decimal("50.00")


class AllowanceLedgerFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.AllowanceLedger"

    household = factory.SubFactory(HouseholdFactory)
    member = factory.LazyAttribute(lambda o: MembershipFactory(household=o.household))
    budget_month = factory.LazyAttribute(lambda o: BudgetMonthFactory(household=o.household))
    granted = Decimal("0.00")
    spent = Decimal("0.00")
    adjustment = Decimal("0.00")
    carried_in = Decimal("0.00")
    carried_out = Decimal("0.00")

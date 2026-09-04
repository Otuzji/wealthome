from datetime import date
from decimal import Decimal

import factory

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

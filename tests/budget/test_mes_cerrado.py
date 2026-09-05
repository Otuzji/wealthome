"""Un mes cerrado rechaza toda escritura (§9).

En DOS capas: el servicio la rechaza (Tarea 12) y el modelo también. Dos
capas porque el Plan 3 añadirá caminos de escritura que hoy no existen, y la
capa de modelo es la que no se puede rodear.
"""

from decimal import Decimal

import pytest

from apps.budget.models import BudgetMonth, MesCerrado
from tests.factories_budget import (
    BudgetLineFactory,
    BudgetMonthFactory,
    MonthlyCloseFactory,
    TransactionFactory,
)

pytestmark = pytest.mark.django_db


def test_no_se_puede_anadir_una_linea_a_un_mes_cerrado():
    mes = BudgetMonthFactory(status=BudgetMonth.CLOSED)

    with pytest.raises(MesCerrado):
        BudgetLineFactory(budget_month=mes, household=mes.household)


def test_no_se_puede_registrar_una_transaccion_en_un_mes_cerrado():
    mes = BudgetMonthFactory(status=BudgetMonth.CLOSED)

    with pytest.raises(MesCerrado):
        TransactionFactory(budget_month=mes, household=mes.household)


def test_no_se_puede_editar_una_linea_de_un_mes_que_se_cerro_despues():
    mes = BudgetMonthFactory(status=BudgetMonth.OPEN)
    linea = BudgetLineFactory(budget_month=mes, household=mes.household)
    mes.status = BudgetMonth.CLOSED
    mes.save()

    linea.planned_amount = Decimal("1.00")
    with pytest.raises(MesCerrado):
        linea.save()


def test_un_mes_abierto_acepta_escrituras():
    mes = BudgetMonthFactory(status=BudgetMonth.OPEN)

    linea = BudgetLineFactory(budget_month=mes, household=mes.household)

    assert linea.pk is not None


def test_el_cierre_es_inmutable():
    """§3.3: MonthlyClose es inmutable una vez escrito. Un balance que se
    puede reescribir no es un balance."""
    cierre = MonthlyCloseFactory()

    cierre.balance = Decimal("999.00")
    with pytest.raises(MesCerrado):
        cierre.save()


def test_un_mes_solo_existe_una_vez_por_hogar():
    from django.db.utils import IntegrityError

    mes = BudgetMonthFactory(year=2026, month=3)

    with pytest.raises(IntegrityError):
        BudgetMonthFactory(household=mes.household, year=2026, month=3)


def test_dos_hogares_pueden_tener_el_mismo_mes():
    BudgetMonthFactory(year=2026, month=3)
    BudgetMonthFactory(year=2026, month=3)

    assert BudgetMonth.unscoped.filter(year=2026, month=3).count() == 2


def test_la_linea_no_puede_pertenecer_a_un_hogar_distinto_al_de_su_mes():
    """Desviación 2.6: se denormaliza `household` en todos los modelos, y la
    consistencia se valida aquí porque un CheckConstraint no cruza tablas."""
    from django.core.exceptions import ValidationError

    from tests.factories import HouseholdFactory

    mes = BudgetMonthFactory()
    linea = BudgetLineFactory.build(budget_month=mes, household=HouseholdFactory())

    with pytest.raises(ValidationError):
        linea.full_clean()


def test_una_linea_no_puede_venir_de_dos_reglas_a_la_vez():
    """Desviación 2: source_rule se parte en dos FK anulables, con un
    CheckConstraint que exige como máximo una."""
    from django.db.utils import IntegrityError

    from tests.factories_budget import ExpenseRuleFactory, IncomeSourceFactory

    mes = BudgetMonthFactory()
    with pytest.raises(IntegrityError):
        BudgetLineFactory(
            budget_month=mes,
            household=mes.household,
            source_income=IncomeSourceFactory(household=mes.household),
            source_expense_rule=ExpenseRuleFactory(household=mes.household),
        )

"""Ningún endpoint devuelve datos de otro hogar (§9, §13.10).

"Esta es la clase de bug que no se descubre en desarrollo": una familia que
ve las finanzas de otra no lanza ningún error, y quien lo sufre no lo reporta
porque no sabe que está pasando.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import CategoryFactory, ExpenseRuleFactory, GoalFactory

pytestmark = pytest.mark.django_db

RUTAS_DE_LECTURA = [
    "budget:configurar", "budget:mes", "budget:metas",
    "budget:registrar", "budget:planificar", "budget:ingreso_nuevo",
    "budget:gasto_nuevo", "budget:categoria_nueva", "budget:reparto_nuevo",
    "budget:meta_nueva", "budget:aportar",
]


@pytest.fixture
def dos_hogares():
    thompson = crear_hogar(UserFactory(), "Family Thompson", family_size=4)
    garcia = crear_hogar(UserFactory(), "Family García", family_size=3)

    ExpenseRuleFactory(household=garcia, name="SECRETO-GARCIA",
                       category=CategoryFactory(household=garcia, slug="su-rent"),
                       amount=Decimal("4321.99"))
    GoalFactory(household=garcia, name="META-SECRETA-GARCIA")
    CategoryFactory(household=garcia, name="CATEGORIA-SECRETA-GARCIA", slug="su-cat")
    return thompson, garcia


@pytest.mark.parametrize("nombre", RUTAS_DE_LECTURA)
def test_ninguna_pantalla_filtra_datos_del_otro_hogar(client, dos_hogares, nombre):
    thompson, _ = dos_hogares
    client.force_login(thompson.active_memberships().first().user)

    html = client.get(reverse(nombre)).content.decode()

    assert "SECRETO-GARCIA" not in html
    assert "META-SECRETA-GARCIA" not in html
    assert "CATEGORIA-SECRETA-GARCIA" not in html
    assert "4,321.99" not in html and "4 321,99" not in html


def test_todo_modelo_del_motor_esta_acotado():
    """La guardia del lote de puertas, aplicada a los trece modelos nuevos."""
    from apps.budget import models as m
    from apps.households.scoping import HouseholdScoped

    esperados = [
        m.Category, m.Merchant, m.IncomeSource, m.ExpenseRule, m.BudgetMonth,
        m.BudgetLine, m.MonthlyClose, m.Transaction, m.Goal, m.GoalContribution,
        m.AllocationRule, m.MonthlyAllocation, m.AllowanceLedger,
    ]
    assert len(esperados) == 13
    for modelo in esperados:
        assert issubclass(modelo, HouseholdScoped), modelo.__name__
        assert modelo._meta.base_manager_name == "unscoped", modelo.__name__
        with pytest.raises(RuntimeError):
            list(modelo.objects.all())

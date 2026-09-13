"""Los diez criterios de aceptación del §10 del diseño del Plan 2.

Varios ya están cubiertos por las pruebas de su tarea. Se escriben aquí otra
vez, en su forma de extremo a extremo, porque son el contrato del plan: si
alguno se rompiera, hay que enterarse por su propio nombre y no por el de una
prueba unitaria tres capas más abajo.
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget import services
from apps.budget.engine.cascade import ALLOWANCE, FIXED, GOAL, REMAINDER
from apps.budget.engine.income import RANGE
from apps.budget.models import (
    AllowanceLedger,
    BudgetMonth,
    GoalContribution,
    MonthlyAllocation,
)
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import (
    AllocationRuleFactory,
    BudgetMonthFactory,
    CategoryFactory,
    ExpenseRuleFactory,
    GoalFactory,
    IncomeSourceFactory,
    TransactionFactory,
)

pytestmark = pytest.mark.django_db


def _normalizar(texto):
    """CLDR usa espacios finos o duros según la versión; los unificamos."""
    return re.sub(r"[\s  ]+", " ", texto)


@pytest.fixture
def hogar_configurado():
    """Un hogar con ingresos, gastos fijos y reglas de reparto: lo que un
    administrador deja montado tras pasar por la pantalla de configuración."""
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=2)
    MembershipFactory(household=hogar, role=Membership.MEMBER)
    IncomeSourceFactory(
        household=hogar, owner=hogar.active_memberships().order_by("pk").first(),
        amount=Decimal("3000.00"), effective_from=date(2026, 1, 1),
    )
    ExpenseRuleFactory(
        household=hogar, amount=Decimal("1800.00"),
        category=CategoryFactory(household=hogar, slug="mi-rent"),
        effective_from=date(2026, 1, 1),
    )
    meta = GoalFactory(household=hogar, target_amount=Decimal("10000.00"))
    AllocationRuleFactory(household=hogar, order=1, target_type=GOAL,
                          target_goal=meta, method=FIXED, amount=Decimal("600.00"))
    AllocationRuleFactory(household=hogar, order=2, target_type=ALLOWANCE,
                          method=REMAINDER, target_goal=None)
    return admin, hogar


# --- 1 -----------------------------------------------------------------------


def test_criterio_1_un_mes_futuro_se_calcula_desde_las_reglas_sin_persistir(
    client, hogar_configurado
):
    """El administrador ve el presupuesto de un mes futuro, sin filas."""
    admin, hogar = hogar_configurado
    client.force_login(admin)

    html = client.get(reverse("budget:mes", args=["household", 2030, 5])).content.decode()

    assert "3,000.00" in html          # el ingreso proyectado desde la regla
    assert "1,200.00" in html          # el sobrante
    assert not BudgetMonth.objects.for_household(hogar).filter(year=2030).exists()


# --- 2 -----------------------------------------------------------------------


def test_criterio_2_un_ingreso_range_presupuesta_el_minimo_y_el_exceso_es_superavit():
    """§13.4."""
    hogar = crear_hogar(UserFactory(), "Thompson", family_size=2)
    fuente = IncomeSourceFactory(
        household=hogar, owner=hogar.active_memberships().first(),
        amount_type=RANGE, amount_min=Decimal("800.00"), amount_max=Decimal("2400.00"),
        effective_from=date(2026, 1, 1),
    )
    mes = services.obtener_mes(hogar, 2026, 1, hoy=date(2026, 1, 10))
    TransactionFactory(
        household=hogar, budget_month=mes, amount=Decimal("2400.00"),
        date=date(2026, 1, 20), income_source=fuente,
        category=mes.lineas.get(kind="income").category,
        member=hogar.active_memberships().first(),
    )

    cierre = services.cerrar_mes(mes)

    assert cierre.ingresos_presupuestados == Decimal("800.00")
    assert cierre.ingresos_reales == Decimal("2400.00")
    assert cierre.balance == Decimal("2400.00")


# --- 3 -----------------------------------------------------------------------


def test_criterio_3_la_pareja_planifica_y_cada_uno_sabe_su_mesada(client, hogar_configurado):
    """§13.5: el sobrante repartido según sus reglas, y la mesada desde el día 1.

    En TRES PASOS desde la Tarea 26, que es lo que el criterio de aceptación 3 del
    Plan 3 pide de verdad: el Plan 2 lo dio por bueno sobre una pantalla única. El
    sobrante se ve en el paso 3, y solo el paso 3 escribe.
    """
    admin, hogar = hogar_configurado
    client.force_login(admin)

    # Paso 1 y 2: se recorren, y no escriben nada.
    assert client.get(
        reverse("budget:planificar_paso", args=["household", 1])
    ).status_code == 200
    assert client.post(
        reverse("budget:planificar_paso", args=["household", 1])
    ).status_code == 302
    assert client.post(
        reverse("budget:planificar_paso", args=["household", 2])
    ).status_code == 302
    assert not AllowanceLedger.objects.for_household(hogar).exists()

    # Paso 3: aquí se ve el sobrante y aquí se confirma.
    html = client.get(
        reverse("budget:planificar_paso", args=["household", 3])
    ).content.decode()
    assert "1,200.00" in html          # el sobrante que van a repartir

    assert client.post(
        reverse("budget:planificar_paso", args=["household", 3])
    ).status_code == 302

    mesadas = AllowanceLedger.objects.for_household(hogar).order_by("member_id")
    assert [m.granted for m in mesadas] == [Decimal("300.00"), Decimal("300.00")]
    assert all(m.saldo() == Decimal("300.00") for m in mesadas)


# --- 4 -----------------------------------------------------------------------


def test_criterio_4_el_faltante_deja_el_ahorro_intacto_y_ajusta_el_mes_siguiente(
    hogar_configurado
):
    """§13.6: nada de lo ya asignado se retira dentro del mes."""
    _, hogar = hogar_configurado
    septiembre = BudgetMonthFactory(household=hogar, year=2026, month=9)
    octubre = BudgetMonthFactory(household=hogar, year=2026, month=10)
    services.planificar_mes(hogar, septiembre, Decimal("800.00"))

    services.aplicar_cascada_al_cierre(septiembre, Decimal("720.00"))

    ahorro = MonthlyAllocation.objects.for_household(hogar).get(
        budget_month=septiembre, member__isnull=True
    )
    assert ahorro.actual_amount == Decimal("600.00")     # el ahorro, intacto

    de_septiembre = AllowanceLedger.objects.for_household(hogar).filter(
        budget_month=septiembre
    )
    assert all(m.granted == Decimal("100.00") for m in de_septiembre)   # nada retirado

    de_octubre = AllowanceLedger.objects.for_household(hogar).filter(
        budget_month=octubre
    ).order_by("member_id")
    assert [m.adjustment for m in de_octubre] == [Decimal("-40.00"), Decimal("-40.00")]


# --- 5 -----------------------------------------------------------------------


def test_criterio_5_editar_el_alquiler_en_marzo_no_altera_enero():
    """§13.7."""
    hogar = crear_hogar(UserFactory(), "Thompson", family_size=2)
    regla = ExpenseRuleFactory(
        household=hogar, amount=Decimal("1800.00"),
        category=CategoryFactory(household=hogar, slug="mi-rent"),
        effective_from=date(2026, 1, 1),
    )
    enero = services.obtener_mes(hogar, 2026, 1, hoy=date(2026, 1, 10))
    cierre_enero = services.cerrar_mes(enero)
    antes = cierre_enero.egresos_presupuestados

    services.reemplazar_regla(regla, Decimal("1950.00"), desde=date(2026, 4, 1))

    cierre_enero.refresh_from_db()
    assert cierre_enero.egresos_presupuestados == antes
    assert services.proyectar(hogar, 2026, 5).total_egresos == Decimal("1950.00")


# --- 6 -----------------------------------------------------------------------


def test_criterio_6_el_saldo_del_mes_cerrado_arranca_el_siguiente():
    """§13.3: se gasta un mes, se cierra, y el saldo viaja al mes siguiente."""
    hogar = crear_hogar(UserFactory(), "Thompson", family_size=2)
    membresia = hogar.active_memberships().first()
    IncomeSourceFactory(household=hogar, owner=membresia, amount=Decimal("3000.00"),
                        effective_from=date(2026, 1, 1))
    alquiler = CategoryFactory(household=hogar, slug="mi-rent")
    ExpenseRuleFactory(household=hogar, amount=Decimal("1800.00"), category=alquiler,
                       effective_from=date(2026, 1, 1))

    enero = services.obtener_mes(hogar, 2026, 1, hoy=date(2026, 1, 10))
    TransactionFactory(household=hogar, budget_month=enero, member=membresia,
                       category=enero.lineas.get(kind="income").category,
                       amount=Decimal("3000.00"), date=date(2026, 1, 15))
    TransactionFactory(household=hogar, budget_month=enero, member=membresia,
                       category=alquiler, amount=Decimal("1800.00"),
                       date=date(2026, 1, 3))
    cierre_enero = services.cerrar_mes(enero)
    assert cierre_enero.arrastre == Decimal("1200.00")

    febrero = services.obtener_mes(hogar, 2026, 2, hoy=date(2026, 2, 10))
    cierre_febrero = services.cerrar_mes(febrero)

    # Febrero no movió un centavo: su balance es exactamente lo que arrastró.
    assert cierre_febrero.balance == Decimal("1200.00")
    assert cierre_febrero.arrastre == Decimal("1200.00")


# --- 7 -----------------------------------------------------------------------


def test_criterio_7_el_adolescente_registra_y_recibe_un_403_traducido(client, hogar_configurado):
    """§6.2: registra su gasto, y las pantallas de presupuesto le dicen que no
    en su propio idioma."""
    from apps.budget.models import Transaction

    _, hogar = hogar_configurado
    adolescente = MembershipFactory(
        household=hogar, role=Membership.MEMBER,
        can_view_budget=False, can_edit_budget=False,
        can_add_transactions=True, can_view_reports=False,
    )
    adolescente.user.profile.language = "fr"
    adolescente.user.profile.save()
    client.force_login(adolescente.user)

    alta = client.post(reverse("budget:registrar"), {
        "category": CategoryFactory(household=hogar, slug="mi-groceries").pk,
        "amount": "45.50", "date": "2026-09-05",
        "payment_method": "debit", "scope": "personal",
    })

    assert alta.status_code == 302
    assert Transaction.objects.for_household(hogar).count() == 1

    negado = client.get(reverse("budget:configurar"))
    assert negado.status_code == 403
    assert "Vous n" in negado.content.decode()   # "Vous n'avez pas l'autorisation…"


# --- 8 -----------------------------------------------------------------------


def test_criterio_8_ninguna_escritura_alcanza_a_otro_hogar(client, hogar_configurado):
    """§13.10. La batería de lectura vive en test_aislamiento.py; esto es la
    otra mitad: tampoco se puede escribir contra una fila ajena."""
    admin, hogar = hogar_configurado
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    meta_ajena = GoalFactory(household=ajeno, name="META-SECRETA-GARCIA")
    client.force_login(admin)

    client.post(reverse("budget:aportar"), {
        "goal": meta_ajena.pk, "amount": "100.00", "date": "2026-09-05",
    })

    assert not GoalContribution.unscoped.filter(goal=meta_ajena).exists()


# --- 9 -----------------------------------------------------------------------


def test_criterio_9_tres_quincenas_y_un_seguro_anual():
    """La decisión §2.2, de punta a punta."""
    from apps.budget.engine.periodicity import ANNUAL, BIWEEKLY

    hogar = crear_hogar(UserFactory(), "Thompson", family_size=2)
    IncomeSourceFactory(
        household=hogar, owner=hogar.active_memberships().first(),
        amount=Decimal("1400.00"), periodicity=BIWEEKLY,
        effective_from=date(2026, 1, 2),
    )
    ExpenseRuleFactory(
        household=hogar, amount=Decimal("1200.00"), periodicity=ANNUAL,
        category=CategoryFactory(household=hogar, slug="mi-insurance"),
        effective_from=date(2026, 8, 15),
    )

    enero = services.proyectar(hogar, 2026, 1)      # tres quincenas
    julio = services.proyectar(hogar, 2026, 7)
    agosto = services.proyectar(hogar, 2026, 8)     # el seguro

    assert enero.total_ingresos == Decimal("4200.00")
    assert julio.total_egresos == Decimal("0.00")
    assert agosto.total_egresos == Decimal("1200.00")


# --- 10 ----------------------------------------------------------------------


def test_criterio_10_la_aplicacion_entera_funciona_en_frances(client, hogar_configurado):
    """El bilingüismo es un requisito legal del producto, no un adorno: la
    pantalla en francés, y el dinero como lo escribe Quebec."""
    admin, hogar = hogar_configurado
    ExpenseRuleFactory(
        household=hogar, amount=Decimal("2847.50"),
        category=CategoryFactory(household=hogar, slug="mi-insurance"),
        effective_from=date(2026, 1, 1),
    )
    admin.profile.language = "fr"
    admin.profile.save()
    client.force_login(admin)

    html = _normalizar(client.get(reverse("budget:mes", args=["household", 2030, 5])).content.decode())

    assert "2 847,50 $" in html
    assert "Ce mois-ci" in html
    assert "Surplus" in html

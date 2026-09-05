"""Los modelos del motor: lo que garantizan por sí solos."""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget.engine.income import RANGE, ROLLING_AVERAGE
from apps.budget.engine.periodicity import BIWEEKLY, MONTHLY
from apps.budget.models import Category, ExpenseRule, IncomeSource, Merchant
from apps.budget.seeds import ARBOL, sembrar
from apps.households.services import crear_hogar
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory
from tests.factories_budget import (
    BudgetLineFactory,
    BudgetMonthFactory,
    CategoryFactory,
    ExpenseRuleFactory,
    IncomeSourceFactory,
    MerchantFactory,
    TransactionFactory,
)

pytestmark = pytest.mark.django_db


# --- la barrera sigue puesta --------------------------------------------------


def test_ningun_modelo_del_motor_se_consulta_sin_hogar():
    """La barrera del lote de puertas aplica igual a los modelos nuevos."""
    for modelo in (Category, Merchant, IncomeSource, ExpenseRule):
        with pytest.raises(RuntimeError):
            list(modelo.objects.all())


def test_for_household_acota_cada_modelo():
    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    CategoryFactory(household=thompson, slug="rent")
    CategoryFactory(household=garcia, slug="rent")

    assert Category.objects.for_household(thompson).count() == 1


# --- Category -----------------------------------------------------------------


def test_crear_un_hogar_siembra_el_arbol_de_categorias():
    """Desviación 1 del diseño: las categorías del sistema se copian por
    hogar, porque HouseholdScoped.household no admite nulo y ablandarlo
    destriparía la barrera."""
    hogar = crear_hogar(UserFactory(), "Family Thompson", family_size=4)

    sembradas = Category.objects.for_household(hogar)
    assert sembradas.count() == len(ARBOL)
    assert sembradas.filter(is_system=True).count() == len(ARBOL)


def test_el_arbol_sembrado_tiene_los_padres_del_spec():
    hogar = crear_hogar(UserFactory(), "Family Thompson", family_size=4)

    alquiler = Category.objects.for_household(hogar).get(slug="rent")
    assert alquiler.parent.slug == "housing"


def test_una_categoria_del_sistema_se_muestra_desde_su_slug():
    """Se muestra traducida mientras `name` esté vacío."""
    hogar = HouseholdFactory()
    sembrar(hogar)

    alquiler = Category.objects.for_household(hogar).get(slug="rent")
    assert alquiler.name == ""
    assert alquiler.etiqueta() == "Rent"


def test_renombrar_una_categoria_del_sistema_solo_escribe_name():
    """§3.2: 'el hogar puede añadir y renombrar'. Con el árbol sembrado por
    hogar eso es cierto sin una tabla de anulaciones."""
    hogar = HouseholdFactory()
    sembrar(hogar)
    alquiler = Category.objects.for_household(hogar).get(slug="rent")

    alquiler.name = "Loyer de la maison"
    alquiler.save()

    assert alquiler.etiqueta() == "Loyer de la maison"
    assert alquiler.is_system is True


def test_sembrar_dos_veces_no_duplica_el_arbol():
    """`sembrar()` debe ser idempotente: si `crear_hogar` ya lo llamó, una
    segunda entrada (una migración de datos, un reintento) no debe duplicar
    el árbol."""
    hogar = HouseholdFactory()
    sembrar(hogar)
    sembrar(hogar)

    assert Category.objects.for_household(hogar).count() == len(ARBOL)


def test_renombrar_en_un_hogar_no_toca_al_otro():
    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    sembrar(thompson)
    sembrar(garcia)

    suyo = Category.objects.for_household(thompson).get(slug="rent")
    suyo.name = "Hipoteca"
    suyo.save()

    ajeno = Category.objects.for_household(garcia).get(slug="rent")
    assert ajeno.name == ""


def test_el_slug_es_unico_dentro_del_hogar():
    from django.db.utils import IntegrityError

    hogar = HouseholdFactory()
    CategoryFactory(household=hogar, slug="rent")

    with pytest.raises(IntegrityError):
        CategoryFactory(household=hogar, slug="rent")


# --- Merchant -----------------------------------------------------------------


def test_el_comercio_normaliza_su_nombre_al_guardar():
    comercio = MerchantFactory(name="WALMART #3421")

    assert comercio.normalized_name == "WALMART"


def test_dos_variantes_del_mismo_comercio_chocan_dentro_del_hogar():
    from django.db.utils import IntegrityError

    hogar = HouseholdFactory()
    MerchantFactory(household=hogar, name="WALMART #3421")

    with pytest.raises(IntegrityError):
        MerchantFactory(household=hogar, name="walmart")


def test_el_mismo_comercio_puede_existir_en_dos_hogares():
    MerchantFactory(household=HouseholdFactory(), name="Walmart")
    MerchantFactory(household=HouseholdFactory(), name="Walmart")

    assert Merchant.unscoped.count() == 2


# --- IncomeSource -------------------------------------------------------------


def test_el_ingreso_calcula_su_cifra_conservadora():
    fuente = IncomeSourceFactory(
        amount_type=RANGE, amount_min=Decimal("800"), amount_max=Decimal("2400")
    )

    assert fuente.cifra_del_mes() == Decimal("800.00")


def test_el_ingreso_en_media_movil_sin_historia_devuelve_none():
    fuente = IncomeSourceFactory(amount_type=ROLLING_AVERAGE)

    assert fuente.cifra_del_mes(historial=[]) is None


def test_el_dueno_de_un_ingreso_es_una_membresia_no_un_usuario():
    """Desviación 3: con FK a User se podría asignar el sueldo de una casa a
    alguien que no vive en ella; con FK a Membership eso es irrepresentable."""
    campo = IncomeSource._meta.get_field("owner")

    assert campo.related_model.__name__ == "Membership"


def test_el_ingreso_en_rango_exige_que_el_minimo_no_supere_al_maximo():
    """Hallazgo de una revisión de la Tarea 4:
    `cifra_conservadora(RANGE, amount_min=5000, amount_max=100)` devuelve
    5000 sin quejarse — el motor toma lo que se le da. La guardia va aquí,
    en el modelo, que es quien conoce los datos de verdad."""
    from django.core.exceptions import ValidationError

    hogar = HouseholdFactory()
    fuente = IncomeSourceFactory.build(
        household=hogar,
        owner=MembershipFactory(household=hogar),
        amount_type=RANGE, amount_min=Decimal("5000"), amount_max=Decimal("100"),
    )

    with pytest.raises(ValidationError):
        fuente.full_clean()


# --- ExpenseRule --------------------------------------------------------------


def test_la_regla_de_gasto_calcula_el_importe_de_un_mes():
    regla = ExpenseRuleFactory(
        amount=Decimal("1400.00"), periodicity=BIWEEKLY,
        effective_from=date(2026, 1, 2),
    )

    assert regla.importe_del_mes(2026, 1) == Decimal("4200.00")


def test_una_regla_cerrada_no_aporta_a_los_meses_posteriores():
    """§3.2: las reglas nunca se mutan; subir el alquiler cierra la vieja."""
    regla = ExpenseRuleFactory(
        amount=Decimal("1800.00"), periodicity=MONTHLY,
        effective_from=date(2026, 1, 1), effective_to=date(2026, 3, 31),
    )

    assert regla.importe_del_mes(2026, 3) == Decimal("1800.00")
    assert regla.importe_del_mes(2026, 4) == Decimal("0.00")


def test_una_regla_de_gasto_solo_acepta_una_categoria_de_su_hogar():
    """La barrera aplica también entre modelos del motor."""
    from django.core.exceptions import ValidationError

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    ajena = CategoryFactory(household=garcia, slug="rent")
    regla = ExpenseRuleFactory.build(household=thompson, category=ajena)

    with pytest.raises(ValidationError):
        regla.full_clean()


# --- BudgetLine -----------------------------------------------------------


def test_la_linea_no_puede_tener_un_kind_distinto_al_de_su_categoria():
    """Hallazgo de la revisión de la Tarea 7: engine/closing.py podía producir
    una varianza inatribuible si una categoría llegaba con una línea de
    ingreso y otra de gasto. BudgetLine.kind y Category.kind son dos fuentes
    que pueden discrepar — Tarea 12 leerá linea.kind para lo presupuestado y
    tx.category.kind para lo real —, así que esta fila contradictoria no
    puede llegar a existir."""
    from django.core.exceptions import ValidationError

    hogar = HouseholdFactory()
    categoria = CategoryFactory(household=hogar, kind="expense")
    mes = BudgetMonthFactory(household=hogar)
    linea = BudgetLineFactory.build(
        household=hogar, budget_month=mes, category=categoria, kind="income"
    )

    with pytest.raises(ValidationError):
        linea.full_clean()


def test_la_linea_acepta_un_kind_igual_al_de_su_categoria():
    hogar = HouseholdFactory()
    categoria = CategoryFactory(household=hogar, kind="expense")
    mes = BudgetMonthFactory(household=hogar)
    linea = BudgetLineFactory.build(
        household=hogar, budget_month=mes, category=categoria, kind="expense"
    )

    linea.full_clean()


# --- borrar el hogar entero (revisión, ronda 1) ----------------------------


def test_borrar_un_hogar_con_transacciones_reales_no_falla():
    """Hallazgo de la ronda 1 de revisión: con `on_delete=PROTECT` en las FK
    de Transaction/BudgetLine/IncomeSource/ExpenseRule hacia Category,
    BudgetMonth y Membership, borrar el hogar entero era IMPOSIBLE en cuanto
    existía una sola transacción. El recolector de Django baja de Household
    a BudgetMonth por cascada, encuentra la transacción a través de la FK
    con PROTECT y lanza — aunque esa misma fila ya está siendo borrada por
    su propia FK `household` en la misma operación. `test_scoping.py` no lo
    detecta porque su modelo de juguete (`Nota`) no tiene relaciones
    protegidas. Con `RESTRICT`, el recolector solo lanza si la fila
    protegida NO va a borrarse también en cascada — que es exactamente este
    caso, así que el borrado debe completarse."""
    from apps.budget.models import BudgetLine, Category, ExpenseRule, Transaction
    from apps.households.models import Membership

    hogar = crear_hogar(UserFactory(), "Familia Test", family_size=2)
    membresia = Membership.objects.get(household=hogar)
    categoria = Category.objects.for_household(hogar).get(slug="rent")
    regla = ExpenseRuleFactory(
        household=hogar, category=categoria, owner=membresia,
        effective_from=date(2026, 1, 1),
    )
    mes = BudgetMonthFactory(household=hogar, year=2026, month=1)
    linea = BudgetLineFactory(
        household=hogar, budget_month=mes, category=categoria,
        source_expense_rule=regla, owner=membresia,
    )
    TransactionFactory(
        household=hogar, budget_month=mes, category=categoria,
        member=membresia, budget_line=linea,
    )

    hogar_id = hogar.pk
    hogar.delete()

    assert Category.unscoped.filter(household_id=hogar_id).count() == 0
    assert ExpenseRule.unscoped.filter(household_id=hogar_id).count() == 0
    assert BudgetLine.unscoped.filter(household_id=hogar_id).count() == 0
    assert Transaction.unscoped.filter(household_id=hogar_id).count() == 0


def test_borrar_un_mes_con_transacciones_sigue_prohibido():
    """La otra mitad de la garantía: RESTRICT no es un PROTECT disfrazado.
    Borrar el BudgetMonth *por sí solo*, sin arrastrar también sus
    transacciones en la misma operación, debe seguir levantando."""
    from django.db.models.deletion import RestrictedError

    mes = BudgetMonthFactory()
    TransactionFactory(budget_month=mes, household=mes.household)

    with pytest.raises(RestrictedError):
        mes.delete()


# --- Goal ---------------------------------------------------------------------


def test_la_meta_deriva_su_aporte_mensual_desde_la_fecha():
    from apps.budget.engine.goals import BY_TARGET_DATE
    from tests.factories_budget import GoalFactory

    meta = GoalFactory(
        contribution_mode=BY_TARGET_DATE,
        target_amount=Decimal("7200.00"),
        target_date=date(2027, 6, 30),
    )

    aporte, fecha = meta.derivar(desde=date(2026, 9, 3))

    assert aporte == Decimal("720.00")
    assert fecha == date(2027, 6, 30)


def test_la_meta_descuenta_sus_contribuciones():
    from apps.budget.engine.goals import BY_TARGET_DATE
    from tests.factories_budget import GoalContributionFactory, GoalFactory

    meta = GoalFactory(
        contribution_mode=BY_TARGET_DATE,
        target_amount=Decimal("7200.00"),
        target_date=date(2027, 6, 30),
    )
    GoalContributionFactory(goal=meta, household=meta.household, amount=Decimal("2200.00"))

    assert meta.acumulado() == Decimal("2200.00")
    assert meta.derivar(desde=date(2026, 9, 3))[0] == Decimal("500.00")


def test_la_meta_no_guarda_el_dato_derivado():
    """§3.3: el tercer dato se deriva al mostrarlo, o quedaría obsoleto en
    cuanto cambie el acumulado."""
    from apps.budget.models import Goal

    campos = {c.name for c in Goal._meta.get_fields()}
    assert "aporte_derivado" not in campos
    assert "fecha_derivada" not in campos


# --- AllocationRule y el libro mayor -----------------------------------------


def test_la_regla_de_reparto_se_traduce_al_tipo_del_motor():
    from apps.budget.engine.cascade import ALLOWANCE, REMAINDER
    from tests.factories_budget import AllocationRuleFactory

    regla = AllocationRuleFactory(target_type=ALLOWANCE, method=REMAINDER, order=2)

    del_motor = regla.a_regla_de_reparto(miembros=(10, 20))

    assert del_motor.orden == 2
    assert del_motor.destino == ALLOWANCE
    assert del_motor.miembros == (10, 20)


def test_el_orden_de_reparto_es_unico_dentro_del_hogar():
    from django.db.utils import IntegrityError

    from tests.factories_budget import AllocationRuleFactory

    regla = AllocationRuleFactory(order=1)

    with pytest.raises(IntegrityError):
        AllocationRuleFactory(household=regla.household, order=1)


def test_el_libro_mayor_deriva_su_saldo():
    from tests.factories_budget import AllowanceLedgerFactory

    fila = AllowanceLedgerFactory(
        carried_in=Decimal("45.00"), granted=Decimal("100.00"),
        adjustment=Decimal("0.00"), spent=Decimal("30.00"),
    )

    assert fila.saldo() == Decimal("115.00")


def test_hay_una_sola_fila_de_mesada_por_miembro_y_mes():
    from django.db.utils import IntegrityError

    from tests.factories_budget import AllowanceLedgerFactory

    fila = AllowanceLedgerFactory()

    with pytest.raises(IntegrityError):
        AllowanceLedgerFactory(
            household=fila.household, member=fila.member, budget_month=fila.budget_month
        )


# --- correcciones de la revisión del brief (Tarea 11) ------------------------


def test_a_regla_de_reparto_no_trunca_si_pesos_no_trae_a_todos_los_miembros():
    """Hallazgo de la Tarea 5: el motor hace zip(miembros, partes), que
    trunca en silencio si las dos tuplas no miden igual — un miembro de la
    mesada desaparece sin error ni rastro. a_regla_de_reparto construye
    `pesos` iterando `miembros`, así que las longitudes coinciden por
    construcción incluso si el JSON guardado no trae entrada para todos: al
    miembro que falta se le asigna peso 1."""
    from apps.budget.engine.cascade import ALLOWANCE, REMAINDER
    from tests.factories_budget import AllocationRuleFactory

    regla = AllocationRuleFactory(
        target_type=ALLOWANCE, method=REMAINDER, split="weighted",
        pesos={"10": "2"},
    )

    del_motor = regla.a_regla_de_reparto(miembros=(10, 20, 30))

    assert len(del_motor.pesos) == len(del_motor.miembros) == 3
    assert del_motor.pesos == (Decimal("2"), Decimal("1"), Decimal("1"))


def test_borrar_un_hogar_con_metas_reparto_y_mesada_no_falla():
    """La misma garantía que test_borrar_un_hogar_con_transacciones_reales_no_falla
    (ronda 1), para las seis FK que la Tarea 11 convierte de PROTECT a
    RESTRICT: Goal.owner, GoalContribution.member, AllocationRule.target_category,
    MonthlyAllocation.rule, MonthlyAllocation.member y AllowanceLedger.member.
    Con PROTECT, borrar el hogar entero sería imposible en cuanto existiera
    una sola meta o una sola regla de reparto."""
    from apps.budget.engine.cascade import CATEGORY, FIXED
    from apps.budget.engine.goals import BY_TARGET_DATE
    from apps.budget.models import AllocationRule, AllowanceLedger, Goal, MonthlyAllocation
    from apps.households.models import Membership
    from tests.factories_budget import (
        AllocationRuleFactory,
        AllowanceLedgerFactory,
        GoalFactory,
        MonthlyAllocationFactory,
    )

    hogar = crear_hogar(UserFactory(), "Familia Reparto", family_size=2)
    membresia = Membership.objects.get(household=hogar)
    categoria = Category.objects.for_household(hogar).get(slug="rent")

    GoalFactory(
        household=hogar, owner=membresia, contribution_mode=BY_TARGET_DATE,
        target_amount=Decimal("1000.00"), target_date=date(2027, 1, 1),
    )
    regla = AllocationRuleFactory(
        household=hogar, order=1, target_type=CATEGORY, target_category=categoria,
        method=FIXED, amount=Decimal("50.00"),
    )
    mes = BudgetMonthFactory(household=hogar, year=2026, month=1)
    MonthlyAllocationFactory(
        household=hogar, budget_month=mes, rule=regla,
        planned_amount=Decimal("50.00"), member=membresia,
    )
    AllowanceLedgerFactory(household=hogar, member=membresia, budget_month=mes)

    hogar_id = hogar.pk
    hogar.delete()

    assert Goal.unscoped.filter(household_id=hogar_id).count() == 0
    assert AllocationRule.unscoped.filter(household_id=hogar_id).count() == 0
    assert MonthlyAllocation.unscoped.filter(household_id=hogar_id).count() == 0
    assert AllowanceLedger.unscoped.filter(household_id=hogar_id).count() == 0

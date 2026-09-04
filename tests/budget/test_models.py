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
    CategoryFactory,
    ExpenseRuleFactory,
    IncomeSourceFactory,
    MerchantFactory,
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

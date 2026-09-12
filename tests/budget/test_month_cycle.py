"""El ciclo de vida del mes (§4.2) y el arrastre (§4.4).

FUTURO (proyección desde reglas, sin filas) → ABIERTO (filas reales,
editables) → CERRADO (foto congelada, inmutable).

El disparador es entrar (decisión §2.3 del diseño del Plan 2): no hay cron ni
Celery en el stack, y un comando programado como único disparador no correría
en desarrollo.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.budget import services
from apps.budget.engine.periodicity import MONTHLY
from apps.budget.models import BudgetMonth, MonthlyClose
from apps.budget.seeds import sembrar
from apps.households.services import crear_hogar
from tests.factories import HouseholdFactory, UserFactory
from tests.factories_budget import (
    BudgetMonthFactory,
    CategoryFactory,
    ExpenseRuleFactory,
    IncomeSourceFactory,
    TransactionFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar_con_reglas():
    hogar = crear_hogar(UserFactory(), "Family Thompson", family_size=4)
    IncomeSourceFactory(
        household=hogar, amount=Decimal("3000.00"), periodicity=MONTHLY,
        effective_from=date(2026, 1, 1),
    )
    ExpenseRuleFactory(
        household=hogar, amount=Decimal("1800.00"), periodicity=MONTHLY,
        effective_from=date(2026, 1, 1),
    )
    return hogar


# --- futuro: proyección sin filas --------------------------------------------


def test_un_mes_futuro_se_proyecta_y_no_persiste(hogar_con_reglas):
    """§2.3: los meses future NO existen como filas."""
    proyeccion = services.obtener_mes(hogar_con_reglas, 2027, 5, hoy=date(2026, 3, 10))

    assert isinstance(proyeccion, services.ProyeccionDeMes)
    assert not BudgetMonth.objects.for_household(hogar_con_reglas).filter(
        year=2027, month=5
    ).exists()


def test_la_proyeccion_suma_las_reglas_vigentes(hogar_con_reglas):
    proyeccion = services.proyectar(hogar_con_reglas, 2027, 5)

    assert proyeccion.total_ingresos == Decimal("3000.00")
    assert proyeccion.total_egresos == Decimal("1800.00")
    assert proyeccion.sobrante == Decimal("1200.00")


def test_cambiar_una_regla_se_refleja_al_instante_en_los_meses_futuros(hogar_con_reglas):
    """§2.3, la razón de que los meses futuros no se persistan."""
    regla = hogar_con_reglas.budget_expenserule_set.first()
    regla.amount = Decimal("1950.00")
    regla.save()

    assert services.proyectar(hogar_con_reglas, 2027, 5).total_egresos == Decimal("1950.00")


# --- abierto: materialización -------------------------------------------------


def test_entrar_al_mes_corriente_lo_materializa(hogar_con_reglas):
    mes = services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))

    assert isinstance(mes, BudgetMonth)
    assert mes.status == BudgetMonth.OPEN
    assert mes.lineas.count() == 2


def test_materializar_dos_veces_no_duplica_lineas(hogar_con_reglas):
    """Dos pestañas abiertas el día 1 es el caso normal, no el raro."""
    services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))
    mes = services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))

    assert mes.lineas.count() == 2


def test_las_lineas_materializadas_recuerdan_su_regla(hogar_con_reglas):
    mes = services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))

    gasto = mes.lineas.get(kind="expense")
    assert gasto.source_expense_rule is not None
    assert gasto.planned_amount == Decimal("1800.00")


def test_editar_una_linea_de_un_mes_abierto_no_toca_la_regla(hogar_con_reglas):
    """§4.3: la vista mensual toca las líneas; la anual toca la regla."""
    mes = services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))
    linea = mes.lineas.get(kind="expense")
    linea.planned_amount = Decimal("2000.00")
    linea.save()

    regla = hogar_con_reglas.budget_expenserule_set.first()
    assert regla.amount == Decimal("1800.00")


# --- cerrado ------------------------------------------------------------------


def test_cerrar_escribe_el_cierre_y_congela_el_mes(hogar_con_reglas):
    mes = services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))
    TransactionFactory(
        household=hogar_con_reglas, budget_month=mes, amount=Decimal("500.00"),
        date=date(2026, 1, 20),
        category=mes.lineas.get(kind="expense").category,
    )

    cierre = services.cerrar_mes(mes)
    mes.refresh_from_db()

    assert mes.status == BudgetMonth.CLOSED
    assert cierre.egresos_reales == Decimal("500.00")


def test_entrar_tras_dos_meses_fuera_cierra_en_cadena(hogar_con_reglas):
    """El caso del §2.3: la familia vuelve el 12 de marzo tras dos meses. Se
    cierran enero y febrero EN ORDEN, porque cada cierre arrastra su saldo."""
    services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))

    services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 12))

    cerrados = BudgetMonth.objects.for_household(hogar_con_reglas).filter(
        status=BudgetMonth.CLOSED
    )
    assert [(m.year, m.month) for m in cerrados] == [(2026, 1), (2026, 2)]


def test_el_saldo_se_arrastra_de_un_cierre_al_siguiente(hogar_con_reglas):
    """§13.3: el mes siguiente arranca con el saldo arrastrado correcto."""
    enero = services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))
    TransactionFactory(
        household=hogar_con_reglas, budget_month=enero, amount=Decimal("3000.00"),
        date=date(2026, 1, 5),
        category=enero.lineas.get(kind="income").category,
    )
    cierre_enero = services.cerrar_mes(enero)

    febrero = services.materializar(hogar_con_reglas, 2026, 2)
    cierre_febrero = services.cerrar_mes(febrero)

    assert cierre_febrero.balance == cierre_enero.arrastre


def test_un_mes_ya_cerrado_no_se_cierra_dos_veces(hogar_con_reglas):
    mes = services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))
    services.cerrar_mes(mes)

    with pytest.raises(Exception):
        services.cerrar_mes(mes)


def test_editar_una_regla_no_altera_un_cierre_anterior(hogar_con_reglas):
    """§13.7: editar el alquiler en marzo no altera ningún cierre de enero."""
    enero = services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))
    cierre = services.cerrar_mes(enero)
    antes = cierre.egresos_presupuestados

    services.reemplazar_regla(
        hogar_con_reglas.budget_expenserule_set.first(),
        nuevo_importe=Decimal("1950.00"),
        desde=date(2026, 4, 1),
    )

    cierre.refresh_from_db()
    assert cierre.egresos_presupuestados == antes


# --- el comando de reserva ----------------------------------------------------


def test_el_comando_cierra_los_meses_vencidos_de_todos_los_hogares(hogar_con_reglas):
    """§2.3: la misma lógica, disponible sin una petición HTTP, para que el
    Plan 3 pueda enchufarle un cron o un correo sin extraerla de una vista."""
    from django.core.management import call_command

    services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))

    call_command("cerrar_meses_vencidos", "--hoy", "2026-03-12")

    assert MonthlyClose.unscoped.count() >= 1


# --- los tres huecos que encontró la revisión de la rama ----------------------


def test_un_mes_pasado_que_nunca_se_vivio_no_se_materializa(hogar_con_reglas):
    """Entrar a enero de 2020 no puede fabricar historia.

    Materializarlo dejaba una fila abierta en 2020, y la siguiente petición
    la cerraba en cadena mes a mes hasta hoy, escribiendo ochenta MonthlyClose
    que son inmutables por construcción: historial financiero inventado que
    solo se puede borrar, no corregir. Un mes anterior a la vida del hogar es
    una proyección de solo lectura, como cualquier mes que no se está viviendo.
    """
    hogar = hogar_con_reglas

    resultado = services.obtener_mes(hogar, 2020, 1, hoy=date(2026, 9, 6))

    assert isinstance(resultado, services.ProyeccionDeMes)
    assert not BudgetMonth.objects.for_household(hogar).filter(year=2020).exists()
    assert not MonthlyClose.objects.for_household(hogar).exists()


def test_entrar_a_un_mes_abierto_sin_lineas_lo_materializa(hogar_con_reglas):
    """La fila puede existir vacía: el ajuste del §4.5.3 crea la del mes
    siguiente solo para escribir en ella el descuento de la mesada.

    Si entrar no la materializara, ese mes se quedaría con presupuesto cero
    para siempre —nunca se materializa, porque materializar solo se llamaba
    cuando NO había fila—, la pantalla saldría vacía, planificar repartiría
    sobre cero y al vencer se cerraría con «presupuestado 0».
    """
    hogar = hogar_con_reglas
    vacio = BudgetMonth.unscoped.create(
        household=hogar, year=2026, month=9,
        status=BudgetMonth.OPEN, opened_at=timezone.now(),
    )
    assert not vacio.lineas.exists()

    resultado = services.obtener_mes(hogar, 2026, 9, hoy=date(2026, 9, 6))

    assert resultado.pk == vacio.pk
    assert resultado.lineas.count() == 2      # el sueldo y el alquiler


def test_la_media_movil_no_se_multiplica_por_las_quincenas():
    """§4.1: la media de rolling_average es de totales MENSUALES.

    Multiplicarla por las ocurrencias del mes presupuestaba el doble en un
    ingreso quincenal y el triple en el mes de tres quincenas — justo el
    optimismo que el modo existe para evitar.
    """
    from apps.budget.engine.income import ROLLING_AVERAGE
    from apps.budget.engine.periodicity import BIWEEKLY

    hogar = crear_hogar(UserFactory(), "Thompson", family_size=2)
    membresia = hogar.active_memberships().first()
    fuente = IncomeSourceFactory(
        household=hogar, owner=membresia, amount_type=ROLLING_AVERAGE,
        amount=None, periodicity=BIWEEKLY, effective_from=date(2026, 1, 1),
    )
    for numero in (1, 2, 3):
        mes = services.obtener_mes(hogar, 2026, numero, hoy=date(2026, numero, 10))
        TransactionFactory(
            household=hogar, budget_month=mes, member=membresia,
            category=mes.lineas.filter(kind="income").first().category
            if mes.lineas.filter(kind="income").exists()
            else CategoryFactory(household=hogar, slug=f"ingreso-{numero}", kind="income"),
            income_source=fuente, amount=Decimal("2000.00"),
            date=date(2026, numero, 15),
        )

    proyeccion = services.proyectar(hogar, 2026, 4)

    assert proyeccion.total_ingresos == Decimal("2000.00")


def test_el_arrastre_no_toma_el_saldo_de_un_mes_posterior(hogar_con_reglas):
    """El arrastre viene del mes ANTERIOR, no del último cerrado.

    `cerrar_mes` es público y nada obliga a cerrar en orden. Filtrando por
    `year__lte` y ordenando descendente, cerrar marzo con diciembre ya cerrado
    tomaba el arrastre de diciembre — y lo congelaba en un MonthlyClose que es
    inmutable por construcción.
    """
    hogar = hogar_con_reglas
    diciembre = services.obtener_mes(hogar, 2026, 12, hoy=date(2026, 12, 10))
    TransactionFactory(
        household=hogar, budget_month=diciembre,
        member=hogar.active_memberships().first(),
        category=diciembre.lineas.get(kind="income").category,
        amount=Decimal("5000.00"), date=date(2026, 12, 15),
    )
    cierre_diciembre = services.cerrar_mes(diciembre)
    assert cierre_diciembre.arrastre == Decimal("5000.00")

    marzo = services.obtener_mes(hogar, 2026, 3, hoy=date(2026, 3, 10))
    cierre_marzo = services.cerrar_mes(marzo)

    assert cierre_marzo.arrastre == Decimal("0.00")


def test_un_hogar_expirado_no_materializa_el_mes_corriente():
    hogar = HouseholdFactory()
    sembrar(hogar)
    hoy = timezone.localdate()
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    hogar = type(hogar).objects.get(pk=hogar.pk)   # limpia la cached_property

    resultado = services.obtener_mes(hogar, hoy.year, hoy.month)

    assert isinstance(resultado, services.ProyeccionDeMes)
    assert not BudgetMonth.objects.for_household(hogar).exists()


def test_un_hogar_expirado_ve_su_historia_pero_no_cierra_nada():
    hogar = HouseholdFactory()
    sembrar(hogar)
    viejo = BudgetMonthFactory(household=hogar, year=2020, month=1, status="open")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    hogar = type(hogar).objects.get(pk=hogar.pk)

    resultado = services.obtener_mes(hogar, 2020, 1)

    assert resultado.pk == viejo.pk
    # Vencido de sobra, y aun asi sigue abierto: no se cerro en cadena.
    assert BudgetMonth.objects.for_household(hogar).get(pk=viejo.pk).status == "open"
    assert not MonthlyClose.objects.for_household(hogar).exists()


def test_al_pagar_la_cadena_de_cierres_se_pone_al_dia():
    """El caso del §4 del documento de estado: expira, pasan meses, paga.

    El mes abierto se ancla al ANTERIOR, no a uno fijo de hace anios, y no es
    cosmetico: `cerrar_vencidos` cierra en cadena mes a mes, asi que con 2020
    esta prueba hacia ~80 cierres contra el pooler —241 s ella sola— y crecia
    otra vuelta cada mes que pasaba en el mundo real. Lo que se comprueba es
    que la cadena ARRANCA al pagar; su longitud no aporta nada.
    """
    from apps.subscriptions.models import Subscription

    hogar = HouseholdFactory()
    sembrar(hogar)
    hoy = timezone.localdate()
    anterior = date(hoy.year, hoy.month, 1) - timedelta(days=1)
    BudgetMonthFactory(
        household=hogar, year=anterior.year, month=anterior.month, status="open"
    )
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    hogar.subscription.status = Subscription.ACTIVE
    hogar.subscription.paid_at = timezone.now()
    hogar.subscription.save()
    hogar = type(hogar).objects.get(pk=hogar.pk)

    services.obtener_mes(hogar, anterior.year, anterior.month)

    cerrado = BudgetMonth.objects.for_household(hogar).get(
        year=anterior.year, month=anterior.month
    )
    assert cerrado.status == "closed"


def test_un_hogar_expirado_puede_mirar_su_mes(client):
    """El sintoma del §5.2 tal y como lo vive el usuario: entrar no escribe.

    Vive aqui y no en test_views.py a proposito: la llamada 2 de la particion va
    ya por 360 s y el plan pide vigilarla; esta tiene mas holgura.
    """
    from django.urls import reverse

    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    sembrar(hogar)
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    assert client.get(reverse("budget:mes")).status_code == 200
    assert not BudgetMonth.objects.for_household(hogar).exists()

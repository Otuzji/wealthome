"""El ciclo de vida del mes (§4.2) y el arrastre (§4.4).

FUTURO (proyección desde reglas, sin filas) → ABIERTO (filas reales,
editables) → CERRADO (foto congelada, inmutable).

El disparador es entrar (decisión §2.3 del diseño del Plan 2): no hay cron ni
Celery en el stack, y un comando programado como único disparador no correría
en desarrollo.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services
from apps.budget.engine.periodicity import MONTHLY
from apps.budget.models import BudgetMonth, MonthlyClose
from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import ExpenseRuleFactory, IncomeSourceFactory, TransactionFactory

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

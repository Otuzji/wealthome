"""El servicio del Overview: Forecast, Real y Expenses.

Salen de las mismas funciones que This month (`totales`, `real_contra_planeado`);
estas pruebas fijan las cifras que el Overview deriva de ellas.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services_overview
from apps.budget.engine import cascade as motor_cascade
from apps.budget.models import AllowanceLedger, BudgetLine, BudgetMonth
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import (
    AllocationRuleFactory, AllowanceLedgerFactory, BudgetLineFactory,
    BudgetMonthFactory, CategoryFactory, ExpenseRuleFactory, GoalFactory,
    IncomeSourceFactory, MonthlyCloseFactory, TransactionFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar_y_mes():
    """Un hogar sembrado y su octubre de 2026, el mes del calendario fijo de
    estas pruebas (nada depende de la fecha de hoy)."""
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=10)
    entra = CategoryFactory(household=hogar, slug="lo-que-entra", kind="income")
    sale = CategoryFactory(household=hogar, slug="lo-que-sale", kind="expense")
    return hogar, mes, entra, sale, hogar.active_memberships().get(user=user)


def _linea(hogar, mes, categoria, importe, **extra):
    return BudgetLineFactory(
        household=hogar, budget_month=mes, category=categoria,
        kind=categoria.kind, planned_amount=Decimal(importe), **extra,
    )


def _totales_del_hogar(hogar, mes, miembro):
    lineas = services_overview.lineas_del_ambito(mes, "household", miembro)
    txs = services_overview.transacciones_del_ambito(mes, "household", miembro)
    donas = services_overview.real_contra_planeado(lineas, txs)
    return services_overview.totales(
        donas["income"]["planeado"], donas["expense"]["planeado"],
        donas["income"]["real"], donas["expense"]["real"],
    )


# --- forecast del hogar -------------------------------------------------------


def test_forecast_hogar_reparte_el_sobrante_como_plan_the_month(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _linea(hogar, mes, entra, "5000.00")
    _linea(hogar, mes, sale, "3000.00")
    _linea(hogar, mes, sale, "500.00", is_exceptional=True)
    AllocationRuleFactory(household=hogar, order=1, target_type=motor_cascade.GOAL,
                          target_goal=GoalFactory(household=hogar),
                          method=motor_cascade.FIXED, amount=Decimal("500.00"))
    AllocationRuleFactory(household=hogar, order=2, target_type=motor_cascade.ALLOWANCE,
                          method=motor_cascade.REMAINDER, amount=None)

    f = services_overview.forecast_hogar(hogar, _totales_del_hogar(hogar, mes, otto))

    assert (f["ingresos"], f["egresos"]) == (Decimal("5000.00"), Decimal("3500.00"))
    assert f["sobrante"] == Decimal("1500.00")
    assert f["ahorro"] == Decimal("500.00")
    assert f["mesada"] == Decimal("1000.00")
    assert f["sin_asignar"] == Decimal("0.00")


def test_forecast_hogar_sin_sobrante_no_reparte(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _linea(hogar, mes, entra, "1000.00")
    _linea(hogar, mes, sale, "1500.00")
    AllocationRuleFactory(household=hogar, order=1, target_type=motor_cascade.ALLOWANCE,
                          method=motor_cascade.REMAINDER, amount=None)

    f = services_overview.forecast_hogar(hogar, _totales_del_hogar(hogar, mes, otto))

    assert f["sobrante"] == Decimal("-500.00")
    assert f["ahorro"] == f["mesada"] == f["sin_asignar"] == Decimal("0.00")


def test_forecast_hogar_deja_sin_asignar_lo_que_ninguna_regla_agota(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _linea(hogar, mes, entra, "3000.00")
    _linea(hogar, mes, sale, "1500.00")
    AllocationRuleFactory(household=hogar, order=1, target_type=motor_cascade.GOAL,
                          target_goal=GoalFactory(household=hogar),
                          method=motor_cascade.FIXED, amount=Decimal("500.00"))

    f = services_overview.forecast_hogar(hogar, _totales_del_hogar(hogar, mes, otto))

    assert f["ahorro"] == Decimal("500.00")
    assert f["mesada"] == Decimal("0.00")
    assert f["sin_asignar"] == Decimal("1000.00")


# --- expenses -----------------------------------------------------------------


def test_expenses_separa_budget_de_one_off(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    de_regla = _linea(hogar, mes, sale, "400.00")
    puntual = _linea(hogar, mes, sale, "200.00", is_exceptional=True)
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("300.00"), budget_line=de_regla)
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("200.00"), budget_line=puntual)
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("50.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=entra, member=otto,
                       amount=Decimal("1000.00"))

    txs = services_overview.transacciones_del_ambito(mes, "household", otto)

    assert services_overview.expenses(txs) == {
        "budget": Decimal("300.00"), "one_off": Decimal("250.00"),
    }


# --- forecast personal --------------------------------------------------------


def _hogar_de_dos(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    diana = MembershipFactory(household=hogar, role=Membership.MEMBER, user=UserFactory())
    # Sobrante del hogar: 1000, todo a la mesada, 500 para cada uno.
    _linea(hogar, mes, entra, "3000.00")
    _linea(hogar, mes, sale, "2000.00")
    AllocationRuleFactory(household=hogar, order=1, target_type=motor_cascade.ALLOWANCE,
                          method=motor_cascade.REMAINDER, amount=None)
    return hogar, mes, sale, otto, diana


def _totales_personales(mes, miembro):
    lineas = services_overview.lineas_del_ambito(mes, "personal", miembro)
    txs = services_overview.transacciones_del_ambito(mes, "personal", miembro)
    donas = services_overview.real_contra_planeado(lineas, txs)
    return services_overview.totales(
        donas["income"]["planeado"], donas["expense"]["planeado"],
        donas["income"]["real"], donas["expense"]["real"],
    )


def test_forecast_personal_mesada_arrastre_y_lo_que_queda(hogar_y_mes):
    hogar, mes, sale, otto, diana = _hogar_de_dos(hogar_y_mes)
    # Se toma a Otto: la primera membresia por pk, la primera de la mesada.
    AllowanceLedgerFactory(household=hogar, member=otto, budget_month=mes,
                           carried_in=Decimal("40.00"), adjustment=Decimal("-10.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("120.00"), scope="personal")

    f = services_overview.forecast_personal(hogar, mes, otto, _totales_personales(mes, otto))

    assert f["mesada"] == Decimal("500.00")
    assert f["arrastre"] == Decimal("40.00")
    assert f["ajuste"] == Decimal("-10.00")
    assert f["disponible"] == Decimal("530.00")
    assert f["queda"] == Decimal("410.00")


def test_forecast_personal_trae_las_cifras_personales(hogar_y_mes):
    hogar, mes, sale, otto, diana = _hogar_de_dos(hogar_y_mes)
    entra = CategoryFactory(household=hogar, slug="mi-ingreso", kind="income")
    _linea(hogar, mes, entra, "200.00", scope="personal", owner=otto)
    _linea(hogar, mes, sale, "80.00", scope="personal", owner=otto)

    f = services_overview.forecast_personal(hogar, mes, otto, _totales_personales(mes, otto))

    assert (f["ingresos"], f["egresos"]) == (Decimal("200.00"), Decimal("80.00"))


def test_forecast_personal_sin_libro_no_lo_crea(hogar_y_mes):
    hogar, mes, sale, otto, diana = _hogar_de_dos(hogar_y_mes)

    f = services_overview.forecast_personal(hogar, mes, diana, _totales_personales(mes, diana))

    assert (f["arrastre"], f["ajuste"]) == (Decimal("0.00"), Decimal("0.00"))
    assert f["mesada"] == Decimal("500.00")
    assert f["queda"] == Decimal("500.00")
    assert not AllowanceLedger.objects.for_household(hogar).exists()


# --- desvios por categoria ----------------------------------------------------


def _desvios(hogar, mes, miembro, cerrado=False):
    lineas = services_overview.lineas_del_ambito(mes, "household", miembro)
    txs = services_overview.transacciones_del_ambito(mes, "household", miembro)
    return services_overview.desvios(lineas, txs, cerrado=cerrado)


def _gasto(hogar, mes, miembro, linea, importe):
    return TransactionFactory(household=hogar, budget_month=mes, category=linea.category,
                              member=miembro, amount=Decimal(importe), budget_line=linea,
                              date=date(2026, 10, 5))


def test_un_exceso_aparece_con_el_mes_abierto(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    fuel = CategoryFactory(household=hogar, slug="gasolina-prueba", name="Fuel", kind="expense")
    linea = _linea(hogar, mes, fuel, "100.00", due_date=date(2026, 10, 28))
    _gasto(hogar, mes, otto, linea, "120.00")

    [d] = _desvios(hogar, mes, otto)

    assert (d.diferencia, d.exceso) == (Decimal("20.00"), True)
    assert d.categoria == fuel
    assert (d.planeado, d.real) == (Decimal("100.00"), Decimal("120.00"))


def test_con_el_mes_abierto_un_pago_parcial_no_es_ahorro(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    linea = _linea(hogar, mes, sale, "100.00", due_date=date(2026, 10, 5))     # vencida
    _gasto(hogar, mes, otto, linea, "40.00")

    assert _desvios(hogar, mes, otto, cerrado=False) == []


def test_con_el_mes_abierto_lo_pagado_de_mas_no_se_compensa(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    a = _linea(hogar, mes, sale, "100.00")
    b = _linea(hogar, mes, sale, "110.00")
    _gasto(hogar, mes, otto, a, "108.00")
    _gasto(hogar, mes, otto, b, "50.00")

    [d] = _desvios(hogar, mes, otto, cerrado=False)

    assert d.diferencia == Decimal("8.00")
    assert (d.planeado, d.real) == (Decimal("210.00"), Decimal("218.00"))


def test_lo_no_planeado_es_exceso_de_su_categoria(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    sorpresa = CategoryFactory(household=hogar, slug="sorpresa-prueba", name="Sorpresa", kind="expense")
    partida = _linea(hogar, mes, sorpresa, "30.00", is_exceptional=True, no_planeada=True)
    _gasto(hogar, mes, otto, partida, "30.00")
    TransactionFactory(household=hogar, budget_month=mes, category=sorpresa, member=otto,
                       amount=Decimal("15.51"), date=date(2026, 10, 6))

    [d] = _desvios(hogar, mes, otto, cerrado=False)

    assert d.categoria == sorpresa
    assert (d.planeado, d.diferencia) == (Decimal("0.00"), Decimal("45.51"))


def test_lo_no_planeado_se_suma_al_exceso_de_las_lineas(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    linea = _linea(hogar, mes, sale, "100.00")
    _gasto(hogar, mes, otto, linea, "90.00")
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("25.00"), date=date(2026, 10, 6))

    [d] = _desvios(hogar, mes, otto, cerrado=False)

    assert (d.planeado, d.real, d.diferencia) == (
        Decimal("100.00"), Decimal("125.00"), Decimal("25.00"))


def test_una_partida_de_plan_the_month_cuenta_como_planificada(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    halloween = CategoryFactory(household=hogar, slug="halloween-prueba", name="Halloween", kind="expense")
    partida = _linea(hogar, mes, halloween, "60.00", is_exceptional=True)
    _gasto(hogar, mes, otto, partida, "67.00")

    [d] = _desvios(hogar, mes, otto, cerrado=False)

    assert (d.planeado, d.diferencia) == (Decimal("60.00"), Decimal("7.00"))


def test_con_el_mes_cerrado_aparece_lo_gastado_de_menos(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    linea = _linea(hogar, mes, sale, "100.00", due_date=date(2026, 10, 28))
    _gasto(hogar, mes, otto, linea, "80.00")

    [d] = _desvios(hogar, mes, otto, cerrado=True)

    assert d.diferencia == Decimal("-20.00")
    assert d.exceso is False


def test_con_el_mes_cerrado_se_cuenta_todo_lo_gastado_de_la_categoria(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    linea = _linea(hogar, mes, sale, "100.00")
    _gasto(hogar, mes, otto, linea, "70.00")
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("45.00"), date=date(2026, 10, 6))

    [d] = _desvios(hogar, mes, otto, cerrado=True)

    assert (d.planeado, d.real, d.diferencia) == (
        Decimal("100.00"), Decimal("115.00"), Decimal("15.00"))


def test_lo_cuadrado_y_los_ingresos_no_desvian(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    cuadrada = CategoryFactory(household=hogar, slug="cuadrada", name="Cuadrada", kind="expense")
    linea = _linea(hogar, mes, cuadrada, "100.00", due_date=date(2026, 10, 5))
    _gasto(hogar, mes, otto, linea, "100.00")
    sueldo = _linea(hogar, mes, entra, "500.00")
    _gasto(hogar, mes, otto, sueldo, "700.00")

    assert _desvios(hogar, mes, otto, cerrado=False) == []
    assert _desvios(hogar, mes, otto, cerrado=True) == []


def test_los_desvios_van_por_tamano(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    for slug, plan, real in (
        ("a", "100.00", "120.00"),     # +20
        ("b", "100.00", "50.00"),      # -50 (solo al cerrar)
        ("c", "100.00", "105.00"),     # +5
    ):
        categoria = CategoryFactory(household=hogar, slug=slug, name=slug.upper(), kind="expense")
        linea = _linea(hogar, mes, categoria, plan)
        _gasto(hogar, mes, otto, linea, real)

    abierto = _desvios(hogar, mes, otto, cerrado=False)
    cerrado = _desvios(hogar, mes, otto, cerrado=True)

    assert [d.diferencia for d in abierto] == [Decimal("20.00"), Decimal("5.00")]
    assert [d.diferencia for d in cerrado] == [Decimal("-50.00"), Decimal("20.00"), Decimal("5.00")]
    assert [d.magnitud for d in cerrado] == [Decimal("50.00"), Decimal("20.00"), Decimal("5.00")]


def test_hay_presupuesto_con_las_lineas_del_mes(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    hoy = date(2026, 10, 10)
    assert services_overview.hay_presupuesto(hogar, mes, hoy) is False

    _linea(hogar, mes, sale, "100.00")

    assert services_overview.hay_presupuesto(hogar, mes, hoy) is True


# --- alerta de cash float -----------------------------------------------------

HOY = date(2026, 10, 10)


def _alerta(hogar, mes, miembro, real="0.00", hoy=HOY):
    lineas = services_overview.lineas_del_ambito(mes, "household", miembro)
    return services_overview.alerta_cash_float(hogar, mes, lineas, Decimal(real), hoy)


def _con_saldo(mes, saldo):
    mes.opening_balance = Decimal(saldo)
    mes.save()


def test_cubierto_hasta_el_proximo_ingreso(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "1000.00")
    _linea(hogar, mes, entra, "3000.00", due_date=date(2026, 10, 15))
    _linea(hogar, mes, sale, "300.00", due_date=date(2026, 10, 12))
    _linea(hogar, mes, sale, "900.00", due_date=date(2026, 10, 20))

    a = _alerta(hogar, mes, otto, "200.00")

    # Todo lo pendiente cuenta, tambien lo que vence despues del ingreso.
    assert a["proximo_ingreso"] == date(2026, 10, 15)
    assert (a["en_mano"], a["pendiente"], a["margen"], a["cubierto"]) == (
        Decimal("1200.00"), Decimal("1200.00"), Decimal("0.00"), True)


def test_no_cubierto(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "100.00")
    _linea(hogar, mes, entra, "3000.00", due_date=date(2026, 10, 15))
    _linea(hogar, mes, sale, "300.00", due_date=date(2026, 10, 12))

    a = _alerta(hogar, mes, otto)

    assert a["cubierto"] is False and a["margen"] == Decimal("-200.00")
    assert a["faltante"] == Decimal("200.00")      # lo que falta, sin signo


def test_un_gasto_del_dia_del_ingreso_tambien_es_pendiente(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "0.00")
    _linea(hogar, mes, entra, "3000.00", due_date=date(2026, 10, 15))
    _linea(hogar, mes, sale, "500.00", due_date=date(2026, 10, 15))

    assert _alerta(hogar, mes, otto)["pendiente"] == Decimal("500.00")


def test_los_gastos_sin_vencimiento_siempre_cuentan(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "0.00")
    _linea(hogar, mes, entra, "3000.00", due_date=date(2026, 10, 15))
    _linea(hogar, mes, sale, "150.00")

    assert _alerta(hogar, mes, otto)["pendiente"] == Decimal("150.00")


def test_un_ingreso_ya_cobrado_o_pasado_no_es_el_proximo(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "0.00")
    cobrado = _linea(hogar, mes, entra, "1000.00", due_date=date(2026, 10, 12))
    TransactionFactory(household=hogar, budget_month=mes, category=entra, member=otto,
                       amount=Decimal("1000.00"), budget_line=cobrado)
    _linea(hogar, mes, entra, "500.00", due_date=date(2026, 10, 5))
    _linea(hogar, mes, entra, "2000.00", due_date=date(2026, 10, 25))

    assert _alerta(hogar, mes, otto)["proximo_ingreso"] == date(2026, 10, 25)


def test_proximo_ingreso_en_el_mes_siguiente_suma_lo_que_vence_antes(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "5000.00")
    IncomeSourceFactory(household=hogar, owner=otto, effective_from=date(2026, 1, 15))
    ExpenseRuleFactory(household=hogar, effective_from=date(2026, 1, 1), amount=Decimal("1800.00"))
    ExpenseRuleFactory(household=hogar, effective_from=date(2026, 1, 2), amount=Decimal("777.00"),
                       scope="personal", owner=otto)
    parcial = _linea(hogar, mes, sale, "400.00", due_date=date(2026, 10, 20))
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("100.00"), budget_line=parcial)
    restante_octubre = Decimal("300.00")

    a = _alerta(hogar, mes, otto)

    assert a["proximo_ingreso"] == date(2026, 11, 15)
    assert a["pendiente"] == restante_octubre + Decimal("1800.00")
    assert not BudgetMonth.objects.for_household(hogar).filter(year=2026, month=11).exists()


def test_mes_siguiente_vacio_se_proyecta_sin_escribir(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    noviembre = BudgetMonthFactory(household=hogar, year=2026, month=11)
    IncomeSourceFactory(household=hogar, owner=otto, effective_from=date(2026, 1, 15))

    a = _alerta(hogar, mes, otto)

    assert a["proximo_ingreso"] == date(2026, 11, 15)
    assert not BudgetLine.objects.for_household(hogar).filter(budget_month=noviembre).exists()


def test_mes_siguiente_con_lineas_usa_las_lineas_del_hogar(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "0.00")
    noviembre = BudgetMonthFactory(household=hogar, year=2026, month=11)
    _linea(hogar, noviembre, entra, "3000.00", due_date=date(2026, 11, 14))
    _linea(hogar, noviembre, entra, "999.00", due_date=date(2026, 11, 3), scope="personal", owner=otto)
    _linea(hogar, noviembre, sale, "250.00", due_date=date(2026, 11, 2))
    _linea(hogar, noviembre, sale, "888.00", due_date=date(2026, 11, 2), scope="personal", owner=otto)
    _linea(hogar, noviembre, sale, "600.00", due_date=date(2026, 11, 20))

    a = _alerta(hogar, mes, otto)

    assert a["proximo_ingreso"] == date(2026, 11, 14)
    assert a["pendiente"] == Decimal("250.00")


def test_sin_ingresos_planificados(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "100.00")
    _linea(hogar, mes, sale, "300.00", due_date=date(2026, 10, 12))
    _linea(hogar, mes, sale, "50.00", due_date=date(2026, 10, 28))

    a = _alerta(hogar, mes, otto)

    assert a["sin_ingreso"] is True and a["proximo_ingreso"] is None
    assert a["pendiente"] == Decimal("350.00")


def test_sin_saldo_inicial_lo_pide(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _linea(hogar, mes, entra, "3000.00", due_date=date(2026, 10, 15))

    a = _alerta(hogar, mes, otto, "200.00")

    assert a["falta_saldo"] is True and a["saldo_inicial"] is None
    assert a["en_mano"] == Decimal("200.00")


def test_la_sugerencia_es_el_arrastre_del_ultimo_cierre(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    septiembre = BudgetMonthFactory(household=hogar, year=2026, month=9)
    MonthlyCloseFactory(household=hogar, budget_month=septiembre, arrastre=Decimal("640.00"))

    assert services_overview.sugerencia_saldo_inicial(mes) == Decimal("640.00")


def test_sin_cierre_previo_no_hay_sugerencia(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes

    assert services_overview.sugerencia_saldo_inicial(mes) is None


def test_un_cierre_mas_viejo_no_se_sugiere_si_el_mes_previo_no_cerro(hogar_y_mes):
    """Dias 1-5: el mes previo aun no se cierra solo. Sugerir el cierre de hace
    dos meses contradice el "last month closed at" de la tarjeta."""
    hogar, mes, entra, sale, otto = hogar_y_mes
    agosto = BudgetMonthFactory(household=hogar, year=2026, month=8)
    MonthlyCloseFactory(household=hogar, budget_month=agosto, arrastre=Decimal("640.00"))
    BudgetMonthFactory(household=hogar, year=2026, month=9)    # septiembre, sin cierre

    assert services_overview.sugerencia_saldo_inicial(mes) is None


def test_con_el_mes_previo_cerrado_se_sugiere_el_suyo_y_no_el_de_antes(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    agosto = BudgetMonthFactory(household=hogar, year=2026, month=8)
    MonthlyCloseFactory(household=hogar, budget_month=agosto, arrastre=Decimal("100.00"))
    septiembre = BudgetMonthFactory(household=hogar, year=2026, month=9)
    MonthlyCloseFactory(household=hogar, budget_month=septiembre, arrastre=Decimal("640.00"))

    assert services_overview.sugerencia_saldo_inicial(mes) == Decimal("640.00")


def test_el_mes_previo_de_enero_es_diciembre_del_anio_anterior(hogar_y_mes):
    hogar, _mes, entra, sale, otto = hogar_y_mes
    enero = BudgetMonthFactory(household=hogar, year=2027, month=1)
    diciembre = BudgetMonthFactory(household=hogar, year=2026, month=12)
    MonthlyCloseFactory(household=hogar, budget_month=diciembre, arrastre=Decimal("75.00"))

    assert services_overview.sugerencia_saldo_inicial(enero) == Decimal("75.00")


def test_real_contra_planeado_excluye_lo_no_planeado_del_plan(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _linea(hogar, mes, sale, "100.00")
    partida = _linea(hogar, mes, sale, "40.00", is_exceptional=True, no_planeada=True)
    TransactionFactory(household=hogar, budget_month=mes, category=sale,
                       amount=Decimal("100.00"), date=date(2026, 10, 5))
    TransactionFactory(household=hogar, budget_month=mes, category=sale, budget_line=partida,
                       amount=Decimal("40.00"), date=date(2026, 10, 6))
    lineas = services_overview.lineas_del_ambito(mes, "household", otto)
    txs = services_overview.transacciones_del_ambito(mes, "household", otto)

    d = services_overview.real_contra_planeado(lineas, txs)

    assert d["expense"]["planeado"] == Decimal("100.00")
    assert d["expense"]["real"] == Decimal("140.00")


# --- pendiente, esperado y desvio ----------------------------------------------


def _totales_con_pendiente(hogar, mes, miembro):
    lineas = services_overview.lineas_del_ambito(mes, "household", miembro)
    txs = services_overview.transacciones_del_ambito(mes, "household", miembro)
    d = services_overview.real_contra_planeado(lineas, txs)
    return services_overview.totales(
        d["income"]["planeado"], d["expense"]["planeado"], d["income"]["real"],
        d["expense"]["real"], d["income"]["pendiente"], d["expense"]["pendiente"],
    )


def test_lo_pendiente_no_se_compensa_con_lo_pagado_de_mas(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    a = _linea(hogar, mes, sale, "100.00")
    b = _linea(hogar, mes, sale, "100.00")
    partida = _linea(hogar, mes, sale, "30.00", is_exceptional=True, no_planeada=True)
    for linea, importe in ((a, "150.00"), (b, "40.00"), (partida, "30.00")):
        TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                           budget_line=linea, amount=Decimal(importe), date=date(2026, 10, 5))

    t = _totales_con_pendiente(hogar, mes, otto)

    assert t["egresos"] == Decimal("200.00")
    assert t["egresos_real"] == Decimal("220.00")
    assert t["egresos_pendiente"] == Decimal("60.00")
    assert t["egresos_esperado"] == Decimal("280.00")
    assert t["egresos_desvio"] == Decimal("80.00")
    assert t["ingresos_pendiente"] == Decimal("0.00")


def test_el_pendiente_de_ingresos_sale_de_las_lineas_de_ingreso(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    sueldo = _linea(hogar, mes, entra, "1000.00")
    TransactionFactory(household=hogar, budget_month=mes, category=entra, member=otto,
                       budget_line=sueldo, amount=Decimal("700.00"), date=date(2026, 10, 5))

    t = _totales_con_pendiente(hogar, mes, otto)

    assert t["ingresos_pendiente"] == Decimal("300.00")
    assert t["ingresos_esperado"] == Decimal("1000.00")
    assert t["ingresos_desvio"] == Decimal("0.00")


def test_un_mes_sin_nada_planificado(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("25.00"), date=date(2026, 10, 5))

    t = _totales_con_pendiente(hogar, mes, otto)

    assert t["egresos"] == Decimal("0.00")
    assert t["egresos_pendiente"] == Decimal("0.00")
    assert t["egresos_desvio"] == t["egresos_esperado"] == Decimal("25.00")


def test_totales_sin_pendiente_lo_toma_como_cero():
    t = services_overview.totales(Decimal("10.00"), Decimal("5.00"), Decimal("0.00"), Decimal("0.00"))

    assert t["egresos_pendiente"] == Decimal("0.00")
    assert t["egresos_desvio"] == Decimal("-5.00")


def test_la_alerta_cuenta_todo_lo_pendiente_aunque_venza_despues_del_ingreso(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "0.00")
    _linea(hogar, mes, entra, "3000.00", due_date=date(2026, 10, 15))
    _linea(hogar, mes, sale, "300.00", due_date=date(2026, 10, 12))
    _linea(hogar, mes, sale, "900.00", due_date=date(2026, 10, 20))
    parcial = _linea(hogar, mes, sale, "200.00", due_date=date(2026, 10, 28))
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       budget_line=parcial, amount=Decimal("50.00"), date=date(2026, 10, 5))
    _linea(hogar, mes, sale, "40.00", is_exceptional=True, no_planeada=True,
           due_date=date(2026, 10, 6))

    a = _alerta(hogar, mes, otto)

    assert a["proximo_ingreso"] == date(2026, 10, 15)
    assert a["pendiente"] == Decimal("300.00") + Decimal("900.00") + Decimal("150.00")


def test_la_alerta_no_cuenta_lo_no_planeado_del_mes_siguiente(hogar_y_mes):
    hogar, mes, entra, sale, otto = hogar_y_mes
    _con_saldo(mes, "0.00")
    noviembre = BudgetMonthFactory(household=hogar, year=2026, month=11)
    _linea(hogar, noviembre, entra, "3000.00", due_date=date(2026, 11, 14))
    _linea(hogar, noviembre, sale, "250.00", due_date=date(2026, 11, 2))
    _linea(hogar, noviembre, sale, "70.00", due_date=date(2026, 11, 3),
           is_exceptional=True, no_planeada=True)

    a = _alerta(hogar, mes, otto)

    assert a["pendiente"] == Decimal("250.00")

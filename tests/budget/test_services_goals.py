"""El dominio de las metas: aportar, y el estado que se deriva de lo aportado.

`reached` lo pone la aplicacion al cubrir el objetivo; `abandoned` solo el
usuario. Una abandonada no se mueve sola aunque le siga cayendo cascada.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services_goals
from apps.budget.models import BudgetMonth, Goal, GoalContribution, MesCerrado
from tests.factories import HouseholdFactory, MembershipFactory
from tests.factories_budget import BudgetMonthFactory, GoalContributionFactory, GoalFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar():
    return HouseholdFactory()


# --- aportar ------------------------------------------------------------------


def test_aportar_resuelve_el_mes_por_la_fecha(hogar):
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    meta = GoalFactory(household=hogar)
    miembro = MembershipFactory(household=hogar)

    aporte = services_goals.aportar(hogar, meta, Decimal("50.00"), date(2026, 3, 10), miembro)

    assert aporte.budget_month == mes
    assert aporte.member == miembro
    assert aporte.origen == "manual"


def test_aportar_en_un_mes_que_el_hogar_no_vivio_deja_el_mes_nulo(hogar):
    meta = GoalFactory(household=hogar)

    aporte = services_goals.aportar(
        hogar, meta, Decimal("50.00"), date(2025, 1, 10), MembershipFactory(household=hogar)
    )

    assert aporte.budget_month is None


def test_aportar_contra_un_mes_cerrado_revienta_y_no_escribe(hogar):
    BudgetMonthFactory(household=hogar, year=2026, month=3, status=BudgetMonth.CLOSED)
    meta = GoalFactory(household=hogar)

    with pytest.raises(MesCerrado):
        services_goals.aportar(
            hogar, meta, Decimal("50.00"), date(2026, 3, 10), MembershipFactory(household=hogar)
        )

    assert not GoalContribution.objects.for_household(hogar).exists()


def test_el_aporte_que_cubre_el_objetivo_marca_la_meta_alcanzada(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    services_goals.aportar(
        hogar, meta, Decimal("100.00"), date(2026, 3, 1), MembershipFactory(household=hogar)
    )

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


def test_un_aporte_parcial_deja_la_meta_activa(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    services_goals.aportar(
        hogar, meta, Decimal("99.99"), date(2026, 3, 1), MembershipFactory(household=hogar)
    )

    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


# --- recalcular_estado --------------------------------------------------------


def test_recalcular_reabre_una_alcanzada_que_ya_no_lo_esta(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("40.00"))

    assert services_goals.recalcular_estado(meta) is True
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_recalcular_no_toca_una_abandonada_aunque_este_cubierta(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.ABANDONED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))

    assert services_goals.recalcular_estado(meta) is False
    meta.refresh_from_db()
    assert meta.status == Goal.ABANDONED


def test_recalcular_dice_que_nada_cambio_cuando_nada_cambia(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("10.00"))

    assert services_goals.recalcular_estado(meta) is False


def test_recalcular_acepta_el_acumulado_ya_calculado(hogar):
    """Quien pinta la lista ya sumo los aportes: no se vuelve a la base."""
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    assert services_goals.recalcular_estado(meta, acumulado=Decimal("100.00")) is True
    assert meta.status == Goal.REACHED


# --- cambiar_estado -----------------------------------------------------------


def test_abandonar_y_reactivar(hogar):
    meta = GoalFactory(household=hogar)

    services_goals.cambiar_estado(meta, Goal.ABANDONED)
    meta.refresh_from_db()
    assert meta.status == Goal.ABANDONED

    services_goals.cambiar_estado(meta, Goal.ACTIVE)
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_reactivar_una_abandonada_ya_cubierta_la_da_por_alcanzada(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.ABANDONED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))

    services_goals.cambiar_estado(meta, Goal.ACTIVE)

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


@pytest.mark.parametrize("desde,hasta", [
    (Goal.ACTIVE, Goal.ACTIVE),
    (Goal.ACTIVE, Goal.REACHED),
    (Goal.REACHED, Goal.ABANDONED),
    (Goal.REACHED, Goal.ACTIVE),
    (Goal.ABANDONED, Goal.REACHED),
    (Goal.ACTIVE, "cualquier-cosa"),
])
def test_las_demas_transiciones_se_rechazan(hogar, desde, hasta):
    meta = GoalFactory(household=hogar, status=desde)

    with pytest.raises(ValueError):
        services_goals.cambiar_estado(meta, hasta)

    meta.refresh_from_db()
    assert meta.status == desde


# --- resumen ------------------------------------------------------------------

from django.db.models import Prefetch  # noqa: E402

from apps.budget.engine.goals import BY_MONTHLY_AMOUNT  # noqa: E402
from tests.factories_budget import AllocationRuleFactory  # noqa: E402


def _con_aportes(hogar):
    return Goal.objects.for_household(hogar).prefetch_related(
        Prefetch(
            "contributions",
            queryset=GoalContribution.objects.for_household(hogar)
            .select_related("member__user", "budget_month"),
        )
    )


def test_resumen_suma_solo_lo_del_mes_de_hoy_en_este_mes(hogar):
    hoy = date(2026, 9, 20)
    septiembre = BudgetMonthFactory(household=hogar, year=2026, month=9)
    agosto = BudgetMonthFactory(household=hogar, year=2026, month=8)
    meta = GoalFactory(household=hogar, target_amount=Decimal("1000.00"))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"),
                            date=date(2026, 9, 3), budget_month=septiembre)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("70.00"),
                            date=date(2026, 8, 3), budget_month=agosto)

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar), hoy=hoy)

    assert fila["acumulado"] == Decimal("170.00")
    assert fila["este_mes"] == Decimal("100.00")


def test_resumen_sin_mes_vivido_deja_este_mes_a_cero(hogar):
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("10.00"))

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar), hoy=date(2026, 9, 20))

    assert fila["este_mes"] == Decimal("0.00")


def test_resumen_sabe_si_una_regla_de_reparto_la_alimenta(hogar):
    con = GoalFactory(household=hogar)
    sin = GoalFactory(household=hogar)
    AllocationRuleFactory(household=hogar, order=1, target_type="goal", target_goal=con,
                          method="fixed", amount=Decimal("50.00"))
    apagada = GoalFactory(household=hogar)
    AllocationRuleFactory(household=hogar, order=2, target_type="goal", target_goal=apagada,
                          method="fixed", amount=Decimal("50.00"), is_active=False)

    por_meta = {f["meta"].pk: f["tiene_regla"]
                for f in services_goals.resumen(hogar, _con_aportes(hogar))}

    assert por_meta == {con.pk: True, sin.pk: False, apagada.pk: False}


def test_resumen_cuenta_los_meses_que_faltan(hogar):
    meta = GoalFactory(household=hogar, contribution_mode=BY_MONTHLY_AMOUNT,
                       target_amount=Decimal("300.00"), monthly_amount=Decimal("100.00"),
                       target_date=None)

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar), hoy=date(2026, 9, 20))

    # 300 a 100 por mes: hoy, en un mes y en dos -> llega en noviembre.
    assert fila["fecha"] == date(2026, 11, 20)
    assert fila["meses_restantes"] == 2


def test_resumen_marca_que_aportes_se_pueden_tocar(hogar):
    # El mes se cierra DESPUES de sembrar el aporte: la guarda del modelo no
    # deja escribir contra un mes cerrado, ni siquiera desde una factory.
    cerrado = BudgetMonthFactory(household=hogar, year=2026, month=3)
    abierto = BudgetMonthFactory(household=hogar, year=2026, month=9)
    meta = GoalFactory(household=hogar)
    manual_abierto = GoalContributionFactory(household=hogar, goal=meta, date=date(2026, 9, 1),
                                             budget_month=abierto)
    manual_cerrado = GoalContributionFactory(household=hogar, goal=meta, date=date(2026, 3, 1),
                                             budget_month=cerrado)
    cerrado.status = BudgetMonth.CLOSED
    cerrado.save(update_fields=["status"])
    sin_mes = GoalContributionFactory(household=hogar, goal=meta, date=date(2020, 1, 1))
    cascada = GoalContribution.unscoped.create(
        household=hogar, goal=meta, amount=Decimal("5.00"), date=date(2026, 9, 30),
        member=None, origen="cascade", budget_month=abierto,
    )

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar))

    editable = {a.pk: e for a, e in fila["aportes"]}
    assert editable == {manual_abierto.pk: True, manual_cerrado.pk: False,
                        sin_mes.pk: True, cascada.pk: False}
    assert fila["se_puede_borrar"] is False


def test_una_meta_sin_cascada_se_puede_borrar(hogar):
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta)

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar))

    assert fila["se_puede_borrar"] is True


def test_resumen_dice_cuando_se_alcanzo(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("60.00"), date=date(2026, 1, 1))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("40.00"), date=date(2026, 2, 1))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("25.00"), date=date(2026, 3, 1))

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar))

    assert fila["alcanzada_el"] == date(2026, 2, 1)
    assert fila["porcentaje"] == 125
    assert fila["porcentaje_barra"] == 100


def test_resumen_no_hace_una_consulta_por_meta(hogar, django_assert_num_queries):
    for _i in range(20):
        meta = GoalFactory(household=hogar)
        for _j in range(5):
            GoalContributionFactory(household=hogar, goal=meta)
    metas = list(_con_aportes(hogar))

    # Las reglas de reparto y el mes de hoy: dos, y no crecen con las metas.
    with django_assert_num_queries(2):
        filas = services_goals.resumen(hogar, metas)

    assert len(filas) == 20


# --- el modelo: modos y signo de los movimientos -------------------------------

from django.core.exceptions import ValidationError  # noqa: E402

from apps.budget.engine.goals import BY_TARGET_DATE, OPEN_FUND  # noqa: E402


def _fondo(hogar, **campos):
    base = dict(household=hogar, contribution_mode=OPEN_FUND, target_amount=None,
                target_date=None)
    base.update(campos)
    return GoalFactory(**base)


def test_un_fondo_abierto_no_necesita_objetivo_ni_fecha(hogar):
    fondo = _fondo(hogar, monthly_amount=Decimal("200.00"))

    fondo.full_clean()

    assert fondo.es_fondo is True
    assert fondo.alcanzada(Decimal("999999.00")) is False


def test_un_fondo_abierto_rechaza_un_objetivo(hogar):
    fondo = _fondo(hogar, target_amount=Decimal("100.00"))

    with pytest.raises(ValidationError) as exc:
        fondo.full_clean()

    assert "target_amount" in exc.value.message_dict


def test_una_meta_por_fecha_sigue_exigiendo_objetivo(hogar):
    meta = GoalFactory(household=hogar, contribution_mode=BY_TARGET_DATE,
                       target_amount=None, target_date=date(2027, 1, 1))

    with pytest.raises(ValidationError) as exc:
        meta.full_clean()

    assert "target_amount" in exc.value.message_dict


@pytest.mark.parametrize("origen,importe,valido", [
    ("manual", "10.00", True), ("manual", "-10.00", False),
    ("cascade", "10.00", True), ("transfer_in", "10.00", True),
    ("withdrawal", "-10.00", True), ("withdrawal", "10.00", False),
    ("transfer_out", "-10.00", True), ("transfer_out", "10.00", False),
    ("manual", "0.00", False),
])
def test_el_signo_del_movimiento_va_con_su_origen(hogar, origen, importe, valido):
    meta = GoalFactory(household=hogar)
    movimiento = GoalContribution(household=hogar, goal=meta, origen=origen,
                                  amount=Decimal(importe), date=date(2026, 3, 1))

    if valido:
        movimiento.full_clean()
    else:
        with pytest.raises(ValidationError) as exc:
            movimiento.full_clean()
        assert "amount" in exc.value.message_dict


# --- retirar, transferir, quitar ---------------------------------------------


def _con_saldo(hogar, saldo="500.00", **campos):
    meta = GoalFactory(household=hogar, **campos)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal(saldo))
    return meta


def test_retirar_escribe_un_movimiento_negativo_con_su_motivo(hogar):
    meta = _con_saldo(hogar)
    miembro = MembershipFactory(household=hogar)

    retiro = services_goals.retirar(hogar, meta, Decimal("120.00"), date(2026, 3, 5),
                                    miembro, note="Vuelos")

    assert retiro.amount == Decimal("-120.00")
    assert retiro.origen == "withdrawal"
    assert retiro.note == "Vuelos"
    assert retiro.member == miembro
    assert meta.acumulado() == Decimal("380.00")


@pytest.mark.parametrize("importe", ["500.01", "0.00", "-10.00"])
def test_no_se_retira_mas_del_saldo_ni_cero(hogar, importe):
    meta = _con_saldo(hogar)

    with pytest.raises(services_goals.SaldoInsuficiente):
        services_goals.retirar(hogar, meta, Decimal(importe), date(2026, 3, 5),
                               MembershipFactory(household=hogar), note="")

    assert meta.acumulado() == Decimal("500.00")


def test_retirar_contra_un_mes_cerrado_revienta(hogar):
    BudgetMonthFactory(household=hogar, year=2026, month=3, status=BudgetMonth.CLOSED)
    meta = _con_saldo(hogar)

    with pytest.raises(MesCerrado):
        services_goals.retirar(hogar, meta, Decimal("10.00"), date(2026, 3, 5),
                               MembershipFactory(household=hogar), note="")


def test_retirar_no_baja_una_meta_alcanzada(hogar):
    """Se cumplio y se uso: sigue cumplida, aunque el saldo quede en cero."""
    meta = _con_saldo(hogar, target_amount=Decimal("500.00"), status=Goal.REACHED)

    services_goals.retirar(hogar, meta, Decimal("500.00"), date(2026, 3, 5),
                           MembershipFactory(household=hogar), note="Ya viajamos")

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED
    assert meta.acumulado() == Decimal("0.00")


def test_transferir_escribe_los_dos_lados_enlazados(hogar):
    origen = _con_saldo(hogar)
    destino = GoalFactory(household=hogar, target_amount=Decimal("1000.00"))
    miembro = MembershipFactory(household=hogar)

    salida, entrada = services_goals.transferir(
        hogar, origen, destino, Decimal("200.00"), date(2026, 3, 5), miembro, note="Al viaje"
    )

    assert (salida.origen, salida.amount, salida.goal) == ("transfer_out", Decimal("-200.00"), origen)
    assert (entrada.origen, entrada.amount, entrada.goal) == ("transfer_in", Decimal("200.00"), destino)
    assert salida.counterpart == entrada and entrada.counterpart == salida
    assert salida.note == entrada.note == "Al viaje"
    assert origen.acumulado() == Decimal("300.00")
    assert destino.acumulado() == Decimal("200.00")


def test_transferir_puede_cubrir_el_destino(hogar):
    origen = _con_saldo(hogar)
    destino = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    services_goals.transferir(hogar, origen, destino, Decimal("100.00"), date(2026, 3, 5),
                              MembershipFactory(household=hogar), note="")

    destino.refresh_from_db()
    assert destino.status == Goal.REACHED


def test_transferir_no_baja_el_origen_alcanzado(hogar):
    origen = _con_saldo(hogar, target_amount=Decimal("500.00"), status=Goal.REACHED)
    destino = GoalFactory(household=hogar)

    services_goals.transferir(hogar, origen, destino, Decimal("500.00"), date(2026, 3, 5),
                              MembershipFactory(household=hogar), note="")

    origen.refresh_from_db()
    assert origen.status == Goal.REACHED


@pytest.mark.parametrize("estado", [Goal.REACHED, Goal.ABANDONED, Goal.ARCHIVED])
def test_solo_se_transfiere_a_una_meta_activa(hogar, estado):
    origen = _con_saldo(hogar)
    destino = GoalFactory(household=hogar, status=estado)

    with pytest.raises(ValueError):
        services_goals.transferir(hogar, origen, destino, Decimal("10.00"), date(2026, 3, 5),
                                  MembershipFactory(household=hogar), note="")

    assert origen.acumulado() == Decimal("500.00")
    assert not destino.contributions.exists()


def test_no_se_transfiere_a_la_misma_meta_ni_mas_del_saldo(hogar):
    origen = _con_saldo(hogar)
    destino = GoalFactory(household=hogar)
    miembro = MembershipFactory(household=hogar)

    with pytest.raises(ValueError):
        services_goals.transferir(hogar, origen, origen, Decimal("10.00"), date(2026, 3, 5), miembro, note="")
    with pytest.raises(services_goals.SaldoInsuficiente):
        services_goals.transferir(hogar, origen, destino, Decimal("500.01"), date(2026, 3, 5), miembro, note="")

    assert origen.contributions.count() == 1


def test_quitar_exige_saldo_cero(hogar):
    meta = _con_saldo(hogar)

    with pytest.raises(services_goals.SaldoPendiente):
        services_goals.quitar(meta)

    assert Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()


def test_quitar_borra_una_meta_sin_cascada(hogar):
    meta = _con_saldo(hogar)
    services_goals.retirar(hogar, meta, Decimal("500.00"), date(2026, 3, 5),
                           MembershipFactory(household=hogar), note="")

    assert services_goals.quitar(meta) == "deleted"
    assert not Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()


def test_quitar_archiva_una_meta_que_recibio_cascada(hogar):
    meta = GoalFactory(household=hogar)
    GoalContribution.unscoped.create(household=hogar, goal=meta, amount=Decimal("50.00"),
                                     date=date(2026, 3, 31), member=None, origen="cascade")
    services_goals.retirar(hogar, meta, Decimal("50.00"), date(2026, 4, 1),
                           MembershipFactory(household=hogar), note="")

    assert services_goals.quitar(meta) == "archived"
    meta.refresh_from_db()
    assert meta.status == Goal.ARCHIVED
    assert meta.contributions.count() == 2


def test_recalcular_con_bajar_false_no_reabre(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)

    assert services_goals.recalcular_estado(meta, acumulado=Decimal("0.00"), bajar=False) is False
    assert meta.status == Goal.REACHED


def test_un_fondo_nunca_se_da_por_alcanzado(hogar):
    fondo = _fondo(hogar)

    services_goals.aportar(hogar, fondo, Decimal("99999.00"), date(2026, 3, 1),
                           MembershipFactory(household=hogar), note="Un bono")

    fondo.refresh_from_db()
    assert fondo.status == Goal.ACTIVE
    assert fondo.contributions.get().note == "Un bono"

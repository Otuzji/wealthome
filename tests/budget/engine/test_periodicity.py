"""Cuándo dispara una regla dentro de un mes concreto.

La decisión §2.2 del diseño del Plan 2: calendario real, no prorrateo. Se
cuentan las ocurrencias reales ancladas en effective_from, así que un mes con
tres quincenas presupuesta tres sueldos y el seguro anual cae entero en su mes
de aniversario.

Prorratear habría dado doce meses idénticos y cómodos, y luego el seguro de
$1.200 llega en agosto contra un presupuesto que decía $100: once meses
cuadran y uno se descuadra por $1.100 sin que el plan lo hubiera anunciado.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget.engine.periodicity import (
    ANNUAL,
    BIMONTHLY,
    BIWEEKLY,
    MONTHLY,
    PERIODICIDADES,
    QUARTERLY,
    SEMIANNUAL,
    SEMIMONTHLY,
    WEEKLY,
    importe_del_mes,
    ocurrencias,
)


def test_las_ocho_periodicidades_del_spec_existen():
    assert set(PERIODICIDADES) == {
        WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY,
        BIMONTHLY, QUARTERLY, SEMIANNUAL, ANNUAL,
    }


# --- semanal y quincenal -----------------------------------------------------


def test_semanal_dispara_cada_siete_dias_desde_el_ancla():
    # 2026-01-02 es viernes. Enero de 2026 tiene cinco viernes.
    assert ocurrencias(WEEKLY, date(2026, 1, 2), 2026, 1) == [
        date(2026, 1, 2), date(2026, 1, 9), date(2026, 1, 16),
        date(2026, 1, 23), date(2026, 1, 30),
    ]


def test_un_mes_de_cuatro_semanas_y_uno_de_cinco_se_distinguen():
    """El mes de cinco viernes es más caro, y el presupuesto tiene que
    decirlo antes de que pase."""
    cinco = ocurrencias(WEEKLY, date(2026, 1, 2), 2026, 1)
    cuatro = ocurrencias(WEEKLY, date(2026, 1, 2), 2026, 2)

    assert len(cinco) == 5
    assert len(cuatro) == 4


def test_quincenal_dispara_cada_catorce_dias():
    assert ocurrencias(BIWEEKLY, date(2026, 1, 2), 2026, 1) == [
        date(2026, 1, 2), date(2026, 1, 16), date(2026, 1, 30),
    ]


def test_el_mes_de_tres_quincenas_es_el_que_genera_el_sobrante():
    """El caso del §2.2: tres sueldos en un mes es sobrante de verdad, y la
    cascada del §4.5 lo reparte."""
    assert len(ocurrencias(BIWEEKLY, date(2026, 1, 2), 2026, 1)) == 3
    assert len(ocurrencias(BIWEEKLY, date(2026, 1, 2), 2026, 2)) == 2


# --- bimensual (dos veces al mes) --------------------------------------------


def test_bimensual_dispara_el_dia_del_ancla_y_ese_dia_mas_quince():
    assert ocurrencias(SEMIMONTHLY, date(2026, 1, 5), 2026, 3) == [
        date(2026, 3, 5), date(2026, 3, 20),
    ]


def test_bimensual_recorta_su_segunda_fecha_a_fin_de_mes():
    """Ancla el 20: la segunda fecha sería el 35, que no existe."""
    assert ocurrencias(SEMIMONTHLY, date(2026, 1, 20), 2026, 2) == [
        date(2026, 2, 20), date(2026, 2, 28),
    ]


# --- mensual y los múltiplos --------------------------------------------------


def test_mensual_dispara_una_vez_el_dia_del_ancla():
    assert ocurrencias(MONTHLY, date(2026, 1, 15), 2026, 7) == [date(2026, 7, 15)]


def test_una_regla_anclada_el_31_dispara_el_ultimo_dia_de_los_meses_cortos():
    """Nunca se salta un mes: el alquiler de febrero se paga en febrero."""
    assert ocurrencias(MONTHLY, date(2026, 1, 31), 2026, 2) == [date(2026, 2, 28)]
    assert ocurrencias(MONTHLY, date(2026, 1, 31), 2026, 4) == [date(2026, 4, 30)]
    assert ocurrencias(MONTHLY, date(2026, 1, 31), 2026, 5) == [date(2026, 5, 31)]


def test_una_regla_anclada_el_29_en_un_ano_bisiesto():
    assert ocurrencias(MONTHLY, date(2024, 1, 29), 2024, 2) == [date(2024, 2, 29)]


def test_bimestral_dispara_en_los_meses_a_distancia_par():
    ancla = date(2026, 1, 10)
    assert ocurrencias(BIMONTHLY, ancla, 2026, 1) == [date(2026, 1, 10)]
    assert ocurrencias(BIMONTHLY, ancla, 2026, 2) == []
    assert ocurrencias(BIMONTHLY, ancla, 2026, 3) == [date(2026, 3, 10)]


def test_trimestral_dispara_cada_tres_meses():
    ancla = date(2026, 2, 10)
    assert ocurrencias(QUARTERLY, ancla, 2026, 2) == [date(2026, 2, 10)]
    assert ocurrencias(QUARTERLY, ancla, 2026, 4) == []
    assert ocurrencias(QUARTERLY, ancla, 2026, 5) == [date(2026, 5, 10)]


def test_semestral_dispara_cada_seis_meses():
    ancla = date(2026, 3, 1)
    assert ocurrencias(SEMIANNUAL, ancla, 2026, 3) == [date(2026, 3, 1)]
    assert ocurrencias(SEMIANNUAL, ancla, 2026, 9) == [date(2026, 9, 1)]
    assert ocurrencias(SEMIANNUAL, ancla, 2026, 6) == []


def test_anual_cae_entero_en_su_mes_de_aniversario():
    """El seguro del §2.2: $1.200 en agosto, no $100 cada mes."""
    ancla = date(2026, 8, 15)
    assert ocurrencias(ANNUAL, ancla, 2027, 8) == [date(2027, 8, 15)]
    assert ocurrencias(ANNUAL, ancla, 2027, 7) == []
    assert ocurrencias(ANNUAL, ancla, 2027, 9) == []


# --- vigencia ----------------------------------------------------------------


def test_una_regla_no_dispara_antes_de_su_ancla():
    assert ocurrencias(MONTHLY, date(2026, 6, 1), 2026, 5) == []


def test_effective_to_corta_la_regla():
    """§3.2: subir el alquiler cierra la regla vieja con effective_to y crea
    una nueva. La vieja no puede seguir disparando."""
    assert ocurrencias(MONTHLY, date(2026, 1, 1), 2026, 3, hasta=date(2026, 3, 31)) == [
        date(2026, 3, 1)
    ]
    assert ocurrencias(MONTHLY, date(2026, 1, 1), 2026, 4, hasta=date(2026, 3, 31)) == []


def test_effective_to_corta_a_media_semana():
    ocs = ocurrencias(WEEKLY, date(2026, 1, 2), 2026, 1, hasta=date(2026, 1, 16))

    assert ocs == [date(2026, 1, 2), date(2026, 1, 9), date(2026, 1, 16)]


# --- el importe del mes -------------------------------------------------------


def test_el_importe_del_mes_multiplica_por_las_ocurrencias():
    assert importe_del_mes(
        Decimal("1400.00"), BIWEEKLY, date(2026, 1, 2), 2026, 1
    ) == Decimal("4200.00")


def test_el_importe_de_un_mes_sin_ocurrencias_es_cero():
    assert importe_del_mes(
        Decimal("1200.00"), ANNUAL, date(2026, 8, 15), 2027, 7
    ) == Decimal("0.00")


def test_el_importe_del_mes_esta_redondeado_a_centavos():
    assert importe_del_mes(
        Decimal("33.333"), MONTHLY, date(2026, 1, 1), 2026, 1
    ) == Decimal("33.33")


def test_una_periodicidad_desconocida_revienta():
    """Un valor no soportado es un error de programación, no un mes vacío que
    haría desaparecer el alquiler del presupuesto sin decir nada."""
    with pytest.raises(ValueError, match="Periodicidad desconocida"):
        ocurrencias("cada_luna_llena", date(2026, 1, 1), 2026, 1)

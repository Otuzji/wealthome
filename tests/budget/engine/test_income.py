"""Los cinco modos de ingreso variable del §4.1.

La regla que gobierna todo el motor: EL PRESUPUESTO SIEMPRE USA LA CIFRA
CONSERVADORA. Un hogar que presupuesta el mejor mes de un ingreso variable se
endeuda en el peor. El optimismo va en la proyección; nunca en el plan.
"""

from decimal import Decimal

import pytest

from apps.budget.engine.income import (
    ESTIMATED,
    FIXED,
    IRREGULAR,
    MESES_MINIMOS_PARA_MEDIA,
    MODOS,
    RANGE,
    ROLLING_AVERAGE,
    cifra_conservadora,
)


def test_los_cinco_modos_del_spec_existen():
    assert set(MODOS) == {FIXED, ESTIMATED, RANGE, ROLLING_AVERAGE, IRREGULAR}


def test_fixed_presupuesta_el_monto_declarado():
    assert cifra_conservadora(FIXED, amount=Decimal("4000")) == Decimal("4000.00")


def test_estimated_presupuesta_la_estimacion_del_usuario():
    assert cifra_conservadora(ESTIMATED, amount=Decimal("2500")) == Decimal("2500.00")


def test_range_presupuesta_el_minimo_y_no_el_maximo():
    """Comisiones y propinas: se presupuesta el mínimo, y lo que exceda es
    superávit al cierre (§13.4). Presupuestar el máximo es exactamente cómo
    una familia se endeuda en un mes flojo."""
    cifra = cifra_conservadora(
        RANGE, amount_min=Decimal("800"), amount_max=Decimal("2400")
    )

    assert cifra == Decimal("800.00")


def test_range_no_presupuesta_ni_el_promedio_del_rango():
    cifra = cifra_conservadora(
        RANGE, amount_min=Decimal("800"), amount_max=Decimal("2400")
    )

    assert cifra != Decimal("1600.00")


def test_irregular_presupuesta_cero():
    """Trabajos esporádicos y bonos: cuando entra, es ingreso excepcional."""
    assert cifra_conservadora(IRREGULAR, amount=Decimal("5000")) == Decimal("0.00")


def test_rolling_average_promedia_los_meses_con_datos():
    historial = [Decimal("3000"), Decimal("3600"), Decimal("2400")]

    assert cifra_conservadora(ROLLING_AVERAGE, historial=historial) == Decimal("3000.00")


def test_rolling_average_redondea_a_centavos():
    historial = [Decimal("1000"), Decimal("1000"), Decimal("1001")]

    assert cifra_conservadora(ROLLING_AVERAGE, historial=historial) == Decimal("1000.33")


def test_rolling_average_devuelve_none_sin_historia_suficiente():
    """§4.1: el modo solo se ofrece cuando existe historia suficiente. Antes
    de eso la interfaz dice explícitamente que aún no hay datos, EN VEZ DE
    INVENTAR UN NÚMERO."""
    assert cifra_conservadora(ROLLING_AVERAGE, historial=[]) is None
    assert cifra_conservadora(ROLLING_AVERAGE, historial=[Decimal("3000")]) is None
    assert (
        cifra_conservadora(ROLLING_AVERAGE, historial=[Decimal("3000"), Decimal("3000")])
        is None
    )


def test_rolling_average_se_habilita_justo_en_el_tercer_mes():
    historial = [Decimal("3000")] * MESES_MINIMOS_PARA_MEDIA

    assert cifra_conservadora(ROLLING_AVERAGE, historial=historial) == Decimal("3000.00")


def test_rolling_average_usa_como_mucho_los_ultimos_seis_meses():
    """Doce meses de historia: solo cuentan los seis últimos."""
    historial = [Decimal("9999")] * 6 + [Decimal("1000")] * 6

    assert cifra_conservadora(ROLLING_AVERAGE, historial=historial) == Decimal("1000.00")


def test_un_modo_desconocido_revienta():
    with pytest.raises(ValueError, match="Modo de ingreso desconocido"):
        cifra_conservadora("adivinalo", amount=Decimal("100"))


def test_fixed_sin_monto_revienta():
    """Un ingreso fijo sin monto es un dato roto, no un cero silencioso que
    haría desaparecer un sueldo del presupuesto."""
    with pytest.raises(ValueError):
        cifra_conservadora(FIXED)


def test_range_sin_minimo_revienta():
    with pytest.raises(ValueError):
        cifra_conservadora(RANGE, amount_max=Decimal("2400"))

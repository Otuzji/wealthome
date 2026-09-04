"""Las dos formas de expresar una meta (§3.3).

Son la misma cosa vista al revés: el usuario da dos datos y la aplicación
deriva el tercero. Ambas formas deben existir, porque las familias piensan de
las dos maneras.

El tercer dato NUNCA se guarda: se deriva al mostrarlo, o quedaría obsoleto en
cuanto cambie el acumulado.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget.engine.goals import BY_MONTHLY_AMOUNT, BY_TARGET_DATE, derivar


def test_por_fecha_objetivo_deriva_el_aporte_mensual():
    """"$7.200 para el 30 de junio de 2027", desde septiembre de 2026: son
    diez meses contando septiembre y junio, así que $720 al mes."""
    aporte, fecha = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("7200.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 9, 3),
        fecha_objetivo=date(2027, 6, 30),
    )

    assert aporte == Decimal("720.00")
    assert fecha == date(2027, 6, 30)


def test_por_fecha_objetivo_descuenta_lo_ya_acumulado():
    aporte, _ = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("7200.00"),
        acumulado=Decimal("2200.00"),
        desde=date(2026, 9, 3),
        fecha_objetivo=date(2027, 6, 30),
    )

    assert aporte == Decimal("500.00")


def test_por_fecha_objetivo_redondea_hacia_arriba_al_centavo():
    """$1.000 en tres meses: 333,34 y no 333,33, o el último mes falta un
    centavo y la meta no se alcanza en su fecha."""
    aporte, _ = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("1000.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 1, 1),
        fecha_objetivo=date(2026, 3, 31),
    )

    assert aporte == Decimal("333.34")


def test_por_monto_mensual_deriva_la_fecha_de_llegada():
    """"$600 cada mes" sobre $7.200: doce meses."""
    aporte, fecha = derivar(
        BY_MONTHLY_AMOUNT,
        objetivo=Decimal("7200.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 9, 1),
        aporte_mensual=Decimal("600.00"),
    )

    assert aporte == Decimal("600.00")
    assert fecha == date(2027, 8, 1)


def test_por_monto_mensual_redondea_hacia_arriba_los_meses():
    """$1.000 a $300 al mes son cuatro meses, no tres y un tercio."""
    _, fecha = derivar(
        BY_MONTHLY_AMOUNT,
        objetivo=Decimal("1000.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 1, 1),
        aporte_mensual=Decimal("300.00"),
    )

    assert fecha == date(2026, 4, 1)


def test_una_meta_ya_alcanzada_no_pide_mas_aportes():
    aporte, fecha = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("1000.00"),
        acumulado=Decimal("1000.00"),
        desde=date(2026, 1, 1),
        fecha_objetivo=date(2026, 6, 30),
    )

    assert aporte == Decimal("0.00")
    assert fecha == date(2026, 1, 1)


def test_una_fecha_objetivo_ya_pasada_pide_todo_de_una_vez():
    """No se divide entre cero meses ni se inventa un plazo: lo que falta se
    pide ahora, que es la verdad."""
    aporte, _ = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("1000.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 6, 1),
        fecha_objetivo=date(2026, 1, 1),
    )

    assert aporte == Decimal("1000.00")


def test_un_aporte_mensual_de_cero_revienta():
    with pytest.raises(ValueError):
        derivar(
            BY_MONTHLY_AMOUNT,
            objetivo=Decimal("1000.00"),
            acumulado=Decimal("0.00"),
            desde=date(2026, 1, 1),
            aporte_mensual=Decimal("0.00"),
        )


def test_un_modo_desconocido_revienta():
    with pytest.raises(ValueError, match="Modo de meta desconocido"):
        derivar("algun_dia", objetivo=Decimal("1"), acumulado=Decimal("0"),
                desde=date(2026, 1, 1))

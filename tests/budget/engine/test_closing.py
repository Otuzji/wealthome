"""El cierre del mes y el arrastre del saldo (§4.4).

El balance de un mes es: saldo arrastrado del cierre anterior + ingresos
reales − egresos reales. El superávit o déficit se arrastra al mes siguiente
al cerrar.
"""

from decimal import Decimal

import pytest

from apps.budget.engine.closing import Cierre, Renglon, cerrar

INGRESO, GASTO = "income", "expense"


def _renglones():
    return [
        Renglon(1, INGRESO, Decimal("3000.00"), Decimal("3200.00")),
        Renglon(2, GASTO, Decimal("1800.00"), Decimal("1800.00")),
        Renglon(3, GASTO, Decimal("400.00"), Decimal("520.00")),
    ]


def test_los_cuatro_totales():
    cierre = cerrar(_renglones(), Decimal("0.00"))

    assert cierre.ingresos_presupuestados == Decimal("3000.00")
    assert cierre.ingresos_reales == Decimal("3200.00")
    assert cierre.egresos_presupuestados == Decimal("2200.00")
    assert cierre.egresos_reales == Decimal("2320.00")


def test_el_balance_es_arrastrado_mas_ingresos_reales_menos_egresos_reales():
    cierre = cerrar(_renglones(), Decimal("150.00"))

    assert cierre.balance == Decimal("1030.00")


def test_el_balance_del_mes_es_el_arrastre_del_siguiente():
    cierre = cerrar(_renglones(), Decimal("150.00"))

    assert cierre.arrastre == cierre.balance


def test_un_deficit_se_arrastra_igual_que_un_superavit():
    """§4.4 no distingue: el déficit también viaja al mes siguiente. Ocultarlo
    haría que un mes malo desapareciera del historial."""
    renglones = [Renglon(1, GASTO, Decimal("100.00"), Decimal("900.00"))]

    cierre = cerrar(renglones, Decimal("0.00"))

    assert cierre.balance == Decimal("-900.00")
    assert cierre.arrastre == Decimal("-900.00")


def test_el_arrastre_entre_cierres_consecutivos_cuadra_al_centavo():
    """§9: la prueba que el spec exige explícitamente. Tres meses seguidos,
    con importes que no dividen redondo."""
    mes1 = cerrar([Renglon(1, INGRESO, Decimal("1000.00"), Decimal("1000.03"))],
                  Decimal("0.00"))
    mes2 = cerrar([Renglon(2, GASTO, Decimal("300.00"), Decimal("333.34"))],
                  mes1.arrastre)
    mes3 = cerrar([Renglon(1, INGRESO, Decimal("500.00"), Decimal("500.00"))],
                  mes2.arrastre)

    assert mes1.arrastre == Decimal("1000.03")
    assert mes2.arrastre == Decimal("666.69")
    assert mes3.arrastre == Decimal("1166.69")


def test_la_varianza_por_categoria_es_real_menos_presupuestado():
    """Signo: en ingresos, positivo es haber ganado más; en gastos, positivo
    es haber gastado más. Es el mismo cálculo y la interfaz lo colorea según
    el kind."""
    cierre = cerrar(_renglones(), Decimal("0.00"))

    assert cierre.varianza_por_categoria == {
        1: Decimal("200.00"),
        2: Decimal("0.00"),
        3: Decimal("120.00"),
    }


def test_dos_renglones_de_la_misma_categoria_se_suman():
    renglones = [
        Renglon(7, GASTO, Decimal("100.00"), Decimal("110.00")),
        Renglon(7, GASTO, Decimal("50.00"), Decimal("45.00")),
    ]

    cierre = cerrar(renglones, Decimal("0.00"))

    assert cierre.varianza_por_categoria == {7: Decimal("5.00")}
    assert cierre.egresos_reales == Decimal("155.00")


def test_un_mes_sin_movimiento_arrastra_lo_que_recibio():
    cierre = cerrar([], Decimal("42.00"))

    assert cierre.balance == Decimal("42.00")
    assert cierre.arrastre == Decimal("42.00")
    assert cierre.varianza_por_categoria == {}


def test_el_ingreso_en_modo_range_deja_su_exceso_como_superavit():
    """§13.4: un ingreso `range` presupuesta el mínimo y el exceso aparece
    como superávit al cierre."""
    renglones = [Renglon(1, INGRESO, Decimal("800.00"), Decimal("2400.00"))]

    cierre = cerrar(renglones, Decimal("0.00"))

    assert cierre.balance == Decimal("2400.00")
    assert cierre.varianza_por_categoria[1] == Decimal("1600.00")


def test_rechaza_tipo_de_renglon_desconocido():
    """Un renglón con kind inválido es rechazado: el dinero no puede
    desaparecer silenciosamente."""
    renglones = [Renglon(5, "Income", Decimal("100.00"), Decimal("150.00"))]

    with pytest.raises(ValueError, match="Tipo de renglón desconocido: 'Income'"):
        cerrar(renglones, Decimal("0.00"))


def test_rechaza_categoria_con_tipos_distintos():
    """Una categoría no puede aparecer con tipos distintos: una deuda no
    se puede atribuir si no se sabe si es ingreso o gasto."""
    renglones = [
        Renglon(7, INGRESO, Decimal("100.00"), Decimal("150.00")),
        Renglon(7, GASTO, Decimal("50.00"), Decimal("75.00")),
    ]

    with pytest.raises(
        ValueError,
        match="Categoría 7 aparece con tipos distintos: 'income' y 'expense'",
    ):
        cerrar(renglones, Decimal("0.00"))

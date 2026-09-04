"""El redondeo del dinero, en un solo sitio.

El §3.4 del diseño de la Fase 1 exige que el redondeo sea explícito, a dos
decimales, y siempre en el mismo punto del cálculo. Este módulo ES ese punto:
ninguna otra función del proyecto redondea dinero.

repartir_proporcional es la que hace que una mesada de $100 entre tres
miembros dé 33,34 / 33,33 / 33,33 y no 33,33 tres veces. Diez centavos
perdidos al mes durante un año son $1,20 que no cuadran, y un usuario que ve
un balance que no cuadra deja de confiar en la aplicación entera.
"""

from decimal import Decimal

import pytest

from apps.budget.engine.money import centavos, repartir_proporcional


def test_centavos_redondea_a_dos_decimales():
    assert centavos(Decimal("10.004")) == Decimal("10.00")
    assert centavos(Decimal("10.005")) == Decimal("10.01")
    assert centavos(Decimal("10.006")) == Decimal("10.01")


def test_centavos_redondea_hacia_arriba_en_el_empate():
    """ROUND_HALF_UP y no el ROUND_HALF_EVEN por defecto de Decimal: el
    banquero redondea 2,675 a 2,68 y Python a 2,67, y la diferencia aparece
    en el extracto del usuario."""
    assert centavos(Decimal("2.675")) == Decimal("2.68")
    assert centavos(Decimal("2.665")) == Decimal("2.67")


def test_centavos_acepta_enteros_y_cadenas():
    assert centavos(100) == Decimal("100.00")
    assert centavos("3.1") == Decimal("3.10")


def test_centavos_conserva_el_signo():
    assert centavos(Decimal("-10.005")) == Decimal("-10.01")


def test_repartir_en_partes_iguales_que_dividen_exacto():
    assert repartir_proporcional(Decimal("90.00"), [1, 1, 1]) == [
        Decimal("30.00"),
        Decimal("30.00"),
        Decimal("30.00"),
    ]


def test_repartir_en_partes_iguales_que_no_dividen_exacto():
    """El caso del spec: $100 entre tres da 33,34 / 33,33 / 33,33."""
    partes = repartir_proporcional(Decimal("100.00"), [1, 1, 1])

    assert partes == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum(partes) == Decimal("100.00")


def test_repartir_con_pesos_explicitos():
    partes = repartir_proporcional(Decimal("100.00"), [Decimal("3"), Decimal("1")])

    assert partes == [Decimal("75.00"), Decimal("25.00")]
    assert sum(partes) == Decimal("100.00")


def test_la_suma_es_exactamente_el_total_en_todos_los_casos_feos():
    """La invariante que importa, contra los repartos que más rompen."""
    casos = [
        (Decimal("0.01"), [1, 1, 1]),
        (Decimal("100.00"), [1, 1, 1, 1, 1, 1]),
        (Decimal("0.10"), [1, 1, 1, 1, 1, 1, 1]),
        (Decimal("1000.00"), [Decimal("1"), Decimal("2"), Decimal("7")]),
        (Decimal("999.99"), [1, 1]),
    ]
    for total, pesos in casos:
        assert sum(repartir_proporcional(total, pesos)) == total, (total, pesos)


def test_repartir_da_siempre_el_mismo_resultado():
    """Dos ejecuciones del mismo reparto tienen que coincidir al centavo, o
    replanificar un mes movería la mesada de sitio sin que nadie tocara nada."""
    primera = repartir_proporcional(Decimal("100.00"), [1, 1, 1])
    segunda = repartir_proporcional(Decimal("100.00"), [1, 1, 1])

    assert primera == segunda


def test_repartir_cero_da_ceros():
    assert repartir_proporcional(Decimal("0.00"), [1, 1]) == [
        Decimal("0.00"),
        Decimal("0.00"),
    ]


def test_repartir_sin_pesos_da_lista_vacia():
    assert repartir_proporcional(Decimal("100.00"), []) == []


def test_repartir_con_pesos_que_suman_cero_da_lista_vacia():
    """Una regla de mesada con todos los pesos a cero no reparte nada, en vez
    de dividir por cero."""
    assert repartir_proporcional(Decimal("100.00"), [0, 0]) == []


def test_repartir_un_importe_negativo_reparte_el_signo():
    """Los ajustes del §4.5.3 son negativos: el faltante que se descuenta de
    la mesada del mes siguiente se reparte con el mismo mecanismo."""
    partes = repartir_proporcional(Decimal("-80.00"), [1, 1])

    assert partes == [Decimal("-40.00"), Decimal("-40.00")]
    assert sum(partes) == Decimal("-80.00")

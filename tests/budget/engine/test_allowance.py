"""El libro mayor de la mesada (§3.3, §4.5.4).

Es un libro mayor, no un campo mutable: cada mes es una fila y el saldo se
deriva sumando. Así "¿por qué tengo $145 este mes?" siempre tiene respuesta.
"""

from decimal import Decimal

from apps.budget.engine.allowance import carried_out, saldo


def test_el_saldo_es_la_suma_del_libro():
    assert saldo(
        carried_in=Decimal("45.00"),
        granted=Decimal("100.00"),
        adjustment=Decimal("0.00"),
        spent=Decimal("30.00"),
    ) == Decimal("115.00")


def test_el_ajuste_negativo_del_mes_anterior_baja_el_saldo():
    """El faltante del §4.5.3 llega aquí: $40 menos en octubre."""
    assert saldo(
        carried_in=Decimal("0.00"),
        granted=Decimal("100.00"),
        adjustment=Decimal("-40.00"),
        spent=Decimal("0.00"),
    ) == Decimal("60.00")


def test_gastar_mas_que_la_mesada_deja_saldo_negativo():
    """No se impide gastar de más: se registra. Bloquear una compra ya hecha
    no la deshace, y un saldo negativo es información."""
    assert saldo(
        carried_in=Decimal("0.00"),
        granted=Decimal("100.00"),
        adjustment=Decimal("0.00"),
        spent=Decimal("130.00"),
    ) == Decimal("-30.00")


def test_con_acumulacion_activada_el_saldo_viaja_al_mes_siguiente():
    """§4.5.4, activada por defecto: guardar $100 durante tres meses para
    comprar algo de $300 es lo que hace que se sienta dinero propio y no una
    asignación que caduca."""
    assert carried_out(Decimal("70.00"), rollover=True) == Decimal("70.00")


def test_con_acumulacion_desactivada_lo_no_gastado_vuelve_al_hogar():
    assert carried_out(Decimal("70.00"), rollover=False) == Decimal("0.00")


def test_un_saldo_negativo_viaja_aunque_la_acumulacion_este_desactivada():
    """Una deuda no se perdona por apagar una opción: quien gastó de más lo
    arrastra igual, o la opción sería una forma de gastar gratis."""
    assert carried_out(Decimal("-30.00"), rollover=False) == Decimal("-30.00")
    assert carried_out(Decimal("-30.00"), rollover=True) == Decimal("-30.00")


def test_el_acumulado_cuadra_al_centavo_a_lo_largo_de_varios_meses():
    """§9: la prueba que el spec exige. Tres meses con acumulación."""
    entra = Decimal("0.00")
    for gastado in [Decimal("30.00"), Decimal("0.00"), Decimal("45.50")]:
        s = saldo(entra, Decimal("100.00"), Decimal("0.00"), gastado)
        entra = carried_out(s, rollover=True)

    # 100-30 = 70; 70+100 = 170; 170+100-45,50 = 224,50
    assert entra == Decimal("224.50")


def test_el_acumulado_sin_acumulacion_no_pasa_de_la_mesada_del_mes():
    entra = Decimal("0.00")
    for gastado in [Decimal("30.00"), Decimal("0.00"), Decimal("45.50")]:
        s = saldo(entra, Decimal("100.00"), Decimal("0.00"), gastado)
        entra = carried_out(s, rollover=False)

    assert entra == Decimal("0.00")

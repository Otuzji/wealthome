"""El reparto en cascada del sobrante (§4.5).

Cada AllocationRule tiene un destino (una meta, la mesada de los miembros, una
categoría) y un método (monto fijo, porcentaje del sobrante, o todo el resto).
Las reglas se ordenan por prioridad y el sobrante cae por ellas en cascada.
"""

from decimal import Decimal

import pytest

from apps.budget.engine.cascade import (
    ALLOWANCE,
    CATEGORY,
    FIXED,
    GOAL,
    PERCENTAGE,
    REMAINDER,
    Asignacion,
    ReglaReparto,
    repartir,
)


def _ahorro(orden=1, importe="600"):
    return ReglaReparto(orden=orden, destino=GOAL, metodo=FIXED,
                        importe=Decimal(importe), destino_id=1)


def _mesada(orden=2, miembros=(10, 20), pesos=None, metodo=REMAINDER, **kw):
    return ReglaReparto(orden=orden, destino=ALLOWANCE, metodo=metodo,
                        miembros=miembros, pesos=pesos, **kw)


# --- el ejemplo canónico del §4.5.2 -------------------------------------------


def test_el_ejemplo_canonico_del_spec():
    """(1) Ahorro familiar, monto fijo $600. (2) Mesada personal, el resto,
    repartido en partes iguales."""
    asignaciones = repartir(Decimal("800.00"), [_ahorro(), _mesada()])

    assert asignaciones == [
        Asignacion(orden=1, importe=Decimal("600.00"), miembro_id=None),
        Asignacion(orden=2, importe=Decimal("100.00"), miembro_id=10),
        Asignacion(orden=2, importe=Decimal("100.00"), miembro_id=20),
    ]


def test_la_suma_del_reparto_no_excede_nunca_el_sobrante():
    for sobrante in ["800.00", "600.00", "599.99", "0.01", "1234.56"]:
        asignaciones = repartir(Decimal(sobrante), [_ahorro(), _mesada()])
        assert sum(a.importe for a in asignaciones) <= Decimal(sobrante)


def test_con_una_regla_remainder_la_suma_es_exactamente_el_sobrante():
    for sobrante in ["800.00", "1000.03", "0.07", "1234.56"]:
        asignaciones = repartir(Decimal(sobrante), [_ahorro(), _mesada()])
        assert sum(a.importe for a in asignaciones) == Decimal(sobrante)


# --- los tres métodos ---------------------------------------------------------


def test_fixed_toma_su_monto_declarado():
    asignaciones = repartir(Decimal("1000.00"), [_ahorro(importe="600")])

    assert asignaciones == [Asignacion(1, Decimal("600.00"), None)]


def test_fixed_se_limita_a_lo_que_queda():
    """Una regla fija de $600 sobre un sobrante de $400 toma $400, no $600.
    Repartir más de lo que hay es inventar dinero."""
    asignaciones = repartir(Decimal("400.00"), [_ahorro(importe="600")])

    assert asignaciones == [Asignacion(1, Decimal("400.00"), None)]


def test_percentage_es_sobre_el_sobrante_que_entro_a_la_cascada():
    """§4.3 del diseño del Plan 2: '10% al fondo de vacaciones' significa el
    10% del sobrante, que es como lo dice una familia — no el 10% de lo que
    sobrevivió a las reglas anteriores."""
    vacaciones = ReglaReparto(orden=2, destino=CATEGORY, metodo=PERCENTAGE,
                              porcentaje=Decimal("0.10"), destino_id=5)

    asignaciones = repartir(Decimal("1000.00"), [_ahorro(importe="600"), vacaciones])

    # 10% de 1000, no 10% de los 400 que quedaban.
    assert asignaciones[1] == Asignacion(2, Decimal("100.00"), None)


def test_percentage_se_limita_a_lo_que_queda():
    grande = ReglaReparto(orden=2, destino=CATEGORY, metodo=PERCENTAGE,
                          porcentaje=Decimal("0.90"), destino_id=5)

    asignaciones = repartir(Decimal("1000.00"), [_ahorro(importe="600"), grande])

    assert asignaciones[1].importe == Decimal("400.00")


def test_remainder_toma_todo_lo_que_queda():
    resto = ReglaReparto(orden=2, destino=CATEGORY, metodo=REMAINDER, destino_id=5)

    asignaciones = repartir(Decimal("1000.00"), [_ahorro(importe="600"), resto])

    assert asignaciones[1].importe == Decimal("400.00")


# --- el orden importa ---------------------------------------------------------


def test_las_reglas_se_recorren_por_orden_y_no_por_posicion_en_la_lista():
    asignaciones = repartir(Decimal("800.00"), [_mesada(orden=2), _ahorro(orden=1)])

    assert asignaciones[0].orden == 1
    assert asignaciones[0].importe == Decimal("600.00")


def test_reordenar_las_reglas_cambia_quien_cobra_primero():
    """§4.5.3: con el ahorro arriba y las mesadas abajo, un mes flojo se come
    la diversión y no el ahorro. Una familia que prefiera lo contrario solo
    reordena las reglas."""
    ahorro_arriba = repartir(Decimal("500.00"), [_ahorro(orden=1), _mesada(orden=2)])
    mesada_arriba = repartir(
        Decimal("500.00"),
        [_mesada(orden=1, metodo=FIXED, importe=Decimal("400")), _ahorro(orden=2)],
    )

    assert ahorro_arriba[0].importe == Decimal("500.00")   # el ahorro se lleva todo
    assert mesada_arriba[-1].importe == Decimal("100.00")  # al ahorro le queda el resto


def test_una_regla_sin_nada_disponible_no_produce_asignacion():
    asignaciones = repartir(Decimal("600.00"), [_ahorro(importe="600"), _mesada()])

    assert [a.orden for a in asignaciones] == [1]


# --- la mesada ----------------------------------------------------------------


def test_la_mesada_se_reparte_entre_los_miembros():
    asignaciones = repartir(Decimal("700.00"), [_ahorro(), _mesada(miembros=(10, 20))])

    mesadas = [a for a in asignaciones if a.miembro_id is not None]
    assert [a.miembro_id for a in mesadas] == [10, 20]
    assert [a.importe for a in mesadas] == [Decimal("50.00"), Decimal("50.00")]


def test_la_mesada_cuadra_al_centavo_entre_tres_miembros():
    """El caso del spec: $100 entre tres da 33,34 / 33,33 / 33,33."""
    asignaciones = repartir(Decimal("700.00"), [_ahorro(), _mesada(miembros=(10, 20, 30))])

    mesadas = [a.importe for a in asignaciones if a.miembro_id is not None]
    assert mesadas == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum(mesadas) == Decimal("100.00")


def test_la_mesada_admite_pesos_explicitos():
    """§3.3: `split` es `equal` o pesos explícitos — $50 a cada hijo no tiene
    por qué ser lo mismo que la mitad para cada adulto."""
    regla = _mesada(miembros=(10, 20), pesos=(Decimal("3"), Decimal("1")))

    asignaciones = repartir(Decimal("700.00"), [_ahorro(), regla])

    mesadas = [a.importe for a in asignaciones if a.miembro_id is not None]
    assert mesadas == [Decimal("75.00"), Decimal("25.00")]


def test_una_mesada_sin_miembros_no_asigna_nada():
    """Un hogar cuyo único miembro se dio de baja no debe recibir una
    asignación huérfana ni dividir por cero."""
    asignaciones = repartir(Decimal("700.00"), [_ahorro(), _mesada(miembros=())])

    assert [a.orden for a in asignaciones] == [1]


# --- los bordes ---------------------------------------------------------------


def test_un_sobrante_negativo_no_reparte_nada():
    """§9: un mes deficitario no reparte nada y no genera mesada."""
    assert repartir(Decimal("-200.00"), [_ahorro(), _mesada()]) == []


def test_un_sobrante_de_cero_no_reparte_nada():
    assert repartir(Decimal("0.00"), [_ahorro(), _mesada()]) == []


def test_sin_reglas_no_reparte_nada():
    assert repartir(Decimal("800.00"), []) == []


def test_lo_que_las_reglas_no_agotan_se_queda_sin_asignar():
    """§2.7: una familia cuyas reglas reparten $600 de un sobrante de $800
    deja $200 a propósito; esos $200 se quedan en el balance y se arrastran.
    Empujarlos a la última regla sería inventarle una decisión que no tomó."""
    asignaciones = repartir(Decimal("800.00"), [_ahorro(importe="600")])

    assert sum(a.importe for a in asignaciones) == Decimal("600.00")


def test_dos_ejecuciones_dan_el_mismo_reparto():
    reglas = [_ahorro(), _mesada(miembros=(10, 20, 30))]

    assert repartir(Decimal("1000.03"), reglas) == repartir(Decimal("1000.03"), reglas)


def test_un_metodo_desconocido_revienta():
    regla = ReglaReparto(orden=1, destino=GOAL, metodo="a_ojo", destino_id=1)

    with pytest.raises(ValueError, match="Método de reparto desconocido"):
        repartir(Decimal("800.00"), [regla])

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
    Ajuste,
    Asignacion,
    ReglaReparto,
    absorber_faltante,
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


def test_dos_reglas_con_el_mismo_orden_revienta():
    """El orden identifica a la regla, así que debe ser único."""
    reglas = [_ahorro(orden=1), _mesada(orden=1)]

    with pytest.raises(ValueError, match="mismo orden"):
        repartir(Decimal("800.00"), reglas)


# --- el faltante (§4.5.3) -----------------------------------------------------


def test_el_ejemplo_literal_del_spec_4_5_3():
    """Sobrante proyectado $800 → $600 al ahorro, $100 a cada uno. Sobrante
    real $720. El ahorro recibe sus $600 íntegros; el faltante de $80 se
    descuenta de las mesadas de octubre, $40 a cada uno. Nadie pierde dinero
    que ya gastó."""
    reglas = [_ahorro(), _mesada(miembros=(10, 20))]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("720.00"))

    assert final == planeado, "la mesada ya asignada NUNCA se retira"
    assert ajustes == [
        Ajuste(miembro_id=10, importe=Decimal("-40.00")),
        Ajuste(miembro_id=20, importe=Decimal("-40.00")),
    ]


def test_sin_faltante_no_hay_ni_ajustes_ni_cambios():
    reglas = [_ahorro(), _mesada()]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("800.00"))

    assert final == planeado
    assert ajustes == []


def test_un_sobrante_real_mayor_al_proyectado_no_cambia_nada():
    """El exceso es superávit y se arrastra; no se reparte retroactivamente."""
    reglas = [_ahorro(), _mesada()]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("900.00"))

    assert final == planeado
    assert ajustes == []


def test_el_faltante_se_absorbe_desde_la_ultima_regla_hacia_arriba():
    """Con una categoría abajo (que sí se puede reducir), el ahorro de arriba
    queda intacto."""
    fondo = ReglaReparto(orden=2, destino=CATEGORY, metodo=REMAINDER, destino_id=5)
    reglas = [_ahorro(importe="600"), fondo]
    planeado = repartir(Decimal("800.00"), reglas)   # 600 + 200

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("700.00"))

    assert final == [
        Asignacion(1, Decimal("600.00"), None),
        Asignacion(2, Decimal("100.00"), None),
    ]
    assert ajustes == []


def test_si_la_ultima_no_alcanza_el_faltante_sube_a_la_penultima():
    fondo = ReglaReparto(orden=2, destino=CATEGORY, metodo=REMAINDER, destino_id=5)
    reglas = [_ahorro(importe="600"), fondo]
    planeado = repartir(Decimal("800.00"), reglas)   # 600 + 200

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("500.00"))

    # Faltan 300: la regla 2 aporta sus 200 y la regla 1 los 100 restantes.
    assert final == [Asignacion(1, Decimal("500.00"), None)]
    assert ajustes == []


def test_una_regla_reducida_a_cero_desaparece_del_reparto():
    fondo = ReglaReparto(orden=2, destino=CATEGORY, metodo=REMAINDER, destino_id=5)
    reglas = [_ahorro(importe="600"), fondo]
    planeado = repartir(Decimal("800.00"), reglas)

    final, _ = absorber_faltante(planeado, reglas, Decimal("600.00"))

    assert [a.orden for a in final] == [1]


def test_la_mesada_nunca_se_reduce_aunque_el_faltante_la_supere():
    """De nada sirve enterarse el día 30 de que tenías $100 para gastar."""
    reglas = [_ahorro(importe="600"), _mesada(miembros=(10, 20))]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("400.00"))

    mesadas = [a for a in final if a.miembro_id is not None]
    assert [a.importe for a in mesadas] == [Decimal("100.00"), Decimal("100.00")]
    # Faltan 400: la mesada aporta sus 200 como ajuste, el ahorro los otros 200.
    assert sum(a.importe for a in ajustes) == Decimal("-200.00")
    assert [a for a in final if a.miembro_id is None] == [
        Asignacion(1, Decimal("400.00"), None)
    ]


def test_los_ajustes_se_reparten_en_la_misma_proporcion_que_la_mesada():
    regla = _mesada(miembros=(10, 20), pesos=(Decimal("3"), Decimal("1")))
    reglas = [_ahorro(importe="600"), regla]
    planeado = repartir(Decimal("800.00"), reglas)   # mesada 150 / 50

    _, ajustes = absorber_faltante(planeado, reglas, Decimal("720.00"))

    assert ajustes == [
        Ajuste(miembro_id=10, importe=Decimal("-60.00")),
        Ajuste(miembro_id=20, importe=Decimal("-20.00")),
    ]


def test_los_ajustes_suman_exactamente_el_faltante_de_la_mesada():
    regla = _mesada(miembros=(10, 20, 30))
    reglas = [_ahorro(importe="600"), regla]
    planeado = repartir(Decimal("800.00"), reglas)

    _, ajustes = absorber_faltante(planeado, reglas, Decimal("799.99"))

    assert sum(a.importe for a in ajustes) == Decimal("-0.01")


def test_un_sobrante_real_negativo_deja_la_mesada_y_vacia_el_resto():
    reglas = [_ahorro(importe="600"), _mesada(miembros=(10, 20))]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("-50.00"))

    assert [a for a in final if a.miembro_id is None] == []
    assert sum(a.importe for a in ajustes) == Decimal("-200.00")


def test_dos_reglas_con_el_mismo_orden_en_absorber_faltante_revienta():
    """El orden identifica a la regla en la cascada, así que debe ser único."""
    # Construir planeado manualmente sin llamar a repartir (que también valida).
    planeado = [
        Asignacion(orden=1, importe=Decimal("600.00"), miembro_id=None),
        Asignacion(orden=1, importe=Decimal("100.00"), miembro_id=10),
        Asignacion(orden=1, importe=Decimal("100.00"), miembro_id=20),
    ]
    reglas = [_ahorro(orden=1, importe="600"), _mesada(orden=1)]

    with pytest.raises(ValueError, match="mismo orden"):
        absorber_faltante(planeado, reglas, Decimal("700.00"))


def test_miembro_con_peso_cero_no_produce_ajuste():
    """Un miembro excluido de la mesada (peso 0) no recibe Ajuste."""
    regla = _mesada(miembros=(10, 20), pesos=(Decimal("1"), Decimal("0")))
    reglas = [_ahorro(importe="600"), regla]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("700.00"))

    # Solo el miembro 10 tiene peso, así que solo uno recibe ajuste.
    assert ajustes == [Ajuste(miembro_id=10, importe=Decimal("-100.00"))]
    # El ajuste suma exactamente el faltante de la mesada.
    assert sum(a.importe for a in ajustes) == Decimal("-100.00")

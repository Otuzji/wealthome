"""Normalización de nombres de comercio (§3.3).

Es la base de las consultas tipo "¿cuánto gastamos en Walmart este año?" que
llegan en la Fase 2.

LÍMITE CONOCIDO, documentado aquí para que nadie confíe de más: la
normalización unifica variantes del MISMO nombre —mayúsculas, puntuación,
número de sucursal— pero no puede unificar nombres distintos. "WALMART #3421"
y "Walmart Supercentre" siguen siendo dos comercios: fundirlos exige una
acción del usuario, que llega con los reportes de la Fase 2. El ejemplo del
§3.3 promete más de lo que la normalización sola puede dar.
"""

from apps.budget.engine.merchants import normalizar


def test_pone_en_mayusculas():
    assert normalizar("walmart") == "WALMART"


def test_quita_el_numero_de_sucursal():
    assert normalizar("WALMART #3421") == "WALMART"
    assert normalizar("Metro #14") == "METRO"


def test_unifica_las_variantes_del_mismo_nombre():
    assert normalizar("WALMART #3421") == normalizar("walmart")
    assert normalizar("  Tim Hortons  ") == normalizar("TIM HORTONS")


def test_quita_la_puntuacion():
    assert normalizar("Couche-Tard") == "COUCHE TARD"
    assert normalizar("A&W") == "A W"


def test_colapsa_los_espacios():
    assert normalizar("SUPER   C") == "SUPER C"


def test_quita_los_acentos():
    """fr-CA: 'Métro' y 'Metro' son el mismo comercio."""
    assert normalizar("Métro") == "METRO"


def test_no_funde_nombres_distintos():
    """El límite documentado arriba, fijado como prueba para que nadie lo
    'arregle' con heurísticas que fundirían comercios de verdad distintos."""
    assert normalizar("WALMART #3421") != normalizar("Walmart Supercentre")


def test_un_nombre_vacio_da_cadena_vacia():
    assert normalizar("") == ""
    assert normalizar("   ") == ""


def test_quita_ligaduras_francesas():
    """fr-CA: 'œuf' (huevo) y 'bœuf' (carne) contienen ligaduras que NFKD
    no descompone. Deben convertirse a 'OE' para que la identificación
    funcione."""
    assert normalizar("Boulangerie Œuf") == "BOULANGERIE OEUF"
    assert normalizar("Boucherie Bœuf") == "BOUCHERIE BOEUF"


def test_nombres_degenerados_no_colisionan():
    """Evita que nombres como '#123' y '!!!' colapsen al mismo string vacío."""
    normalizado_hash = normalizar("#123")
    normalizado_bang = normalizar("!!!")
    # Ambos deben ser no-vacíos y distintos
    assert normalizado_hash != ""
    assert normalizado_bang != ""
    assert normalizado_hash != normalizado_bang

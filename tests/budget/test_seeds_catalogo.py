"""El punto ciego que test_catalogo_exhaustivo.py nombra en su propio docstring.

`apps/budget/seeds.py::etiqueta_de_slug` traduce con
`_(ETIQUETAS.get(slug, slug))` — `gettext` aplicado a una variable, no a un
literal. La guardia de exhaustividad
(`tests/test_catalogo_exhaustivo.py`) solo reconoce `_("literal")`, así que
nunca ve estas 17 etiquetas; las 17 se añadieron a mano a ambos catálogos en
la Tarea 9, pero nada impedía que una Tarea futura sumara una fila 18 a
`seeds.ARBOL` sin tocar el `.po` y pasara las dos pruebas de traducción de
todos modos — esa categoría se habría mostrado en inglés bajo `fr` a todo
hogar, sin que ninguna prueba lo notara. El bilingüismo es un requisito legal
del producto, no un adorno.

Esta prueba vigila justo ese único punto en el árbol que usa esa forma:
recorre `seeds.ARBOL` directamente (no una expresión regular sobre texto
fuente) y exige que cada etiqueta tenga un `msgstr` no vacío en AMBOS
catálogos. Reusa el parser de `.po` de tests/test_traducciones.py — el mismo
que ya usa tests/test_catalogo_exhaustivo.py — en vez de escribir un tercero.
"""

from pathlib import Path

import pytest
from django.conf import settings

from apps.budget.seeds import ARBOL
from tests.test_traducciones import _ENTRADA_RE, _texto_de_cadenas

CATALOGO_EN = Path(settings.BASE_DIR) / "locale/en/LC_MESSAGES/django.po"
CATALOGO_FR = Path(settings.BASE_DIR) / "locale/fr/LC_MESSAGES/django.po"


def _msgstrs_del_catalogo(texto_po):
    """{msgid: msgstr} de cada entrada no vacía del .po."""
    return {
        _texto_de_cadenas(m.group("msgid")): _texto_de_cadenas(m.group("msgstr"))
        for m in _ENTRADA_RE.finditer(texto_po)
    }


@pytest.mark.parametrize(
    "etiqueta", sorted({etiqueta for _slug, etiqueta, _padre, _kind in ARBOL})
)
def test_cada_etiqueta_del_arbol_sembrado_esta_traducida_en_ambos_catalogos(etiqueta):
    for catalogo in (CATALOGO_EN, CATALOGO_FR):
        msgstrs = _msgstrs_del_catalogo(catalogo.read_text(encoding="utf-8"))
        assert msgstrs.get(etiqueta), (
            f"'{etiqueta}' (apps/budget/seeds.py::ARBOL) no tiene una entrada "
            f"traducida en {catalogo}"
        )

"""Prueba de exhaustividad del catálogo francés (fix #6 de la ola final).

tests/test_traducciones.py prueba que ningún msgstr del .po esté vacío o
fuzzy, pero eso no dice nada sobre si TODA cadena traducible del código
llegó siquiera a tener una entrada msgid. Los catálogos de este proyecto se
escriben a mano —la cadena de herramientas GNU gettext no está disponible en
esta máquina—, así que una cadena nueva envuelta en gettext que nadie
trasladó al .po se renderiza en inglés bajo fr sin que ninguna prueba lo
note. El bilingüismo es un requisito legal del producto, no un adorno.

Límites de esta guardia — documentados aquí, no solo en un ledger, para que
nadie confíe en ella más de lo que puede dar (mismo espíritu que el
comentario de puntos ciegos de R-7 en tests/test_scoping.py):

- **Es una expresión regular sobre texto fuente, no un parser de Python ni
  de la gramática de plantillas de Django.** Una cadena construida en
  tiempo de ejecución (`_(variable)`, `_("Hola " + nombre)`, un f-string) es
  invisible: solo se detectan llamadas con un literal de cadena simple.
- **Solo reconoce `_(...)`, `gettext(...)` y `gettext_lazy(...)` en Python**,
  y `{% translate %}` / `{% trans %}` / `{% blocktranslate %}` /
  `{% blocktrans %}` en plantillas. Un alias distinto de gettext_lazy
  (`from django.utils.translation import gettext_lazy as _t`) no se
  reconocería.
- **Un literal partido en varias líneas dentro de los paréntesis de Python**
  (concatenación implícita `_("a" "b")` o una cadena con saltos de línea
  reales) no se recompone; solo se captura la primera subcadena.
- **La normalización de `{% blocktranslate %}` es aproximada.** Django
  colapsa el cuerpo a través de su propio compilador de plantillas; aquí se
  colapsa con un `split()/join()` simple y se traduce `{{ variable }}` a
  `%(variable)s` sin soportar filtros (`{{ variable|filtro }}`) ni bloques
  `{% plural %}`. El único blocktranslate real del árbol hoy
  (templates/households/permisos.html) es justo ese caso simple.
- **Solo mira `apps/` y `templates/`.** Cualquier cadena traducible que
  viviera en otro directorio no se vería.

Con esas salvedades, un `faltantes == []` contra el árbol real es evidencia
razonable de que ninguna cadena se quedó fuera del catálogo — no una
garantía formal.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

from tests.test_traducciones import _ENTRADA_RE, _texto_de_cadenas

CATALOGO_FR = Path(settings.BASE_DIR) / "locale/fr/LC_MESSAGES/django.po"

# --- Extracción de literales del código fuente ------------------------------

_LLAMADA_PYTHON_RE = re.compile(
    r"(?<!\w)(?:_|gettext|gettext_lazy)\(\s*"
    r"(?P<q>['\"])(?P<cad>(?:\\.|(?!(?P=q)).)*)(?P=q)"
)

_TAG_SIMPLE_RE = re.compile(
    r"\{%-?\s*(?:translate|trans)\s+"
    r"(?P<q>['\"])(?P<cad>(?:\\.|(?!(?P=q)).)*)(?P=q)"
)

_BLOCKTRANS_RE = re.compile(
    r"\{%-?\s*block(?:translate|trans)\b[^%]*%\}"
    r"(?P<cuerpo>.*?)"
    r"\{%-?\s*end(?:blocktranslate|blocktrans)\s*-?%\}",
    re.DOTALL,
)

_VARIABLE_RE = re.compile(r"\{\{\s*(\w+)(?:\|[^}]*)?\s*\}\}")


def _cadenas_python(texto):
    return [m.group("cad") for m in _LLAMADA_PYTHON_RE.finditer(texto)]


def _cadenas_plantilla(texto):
    cadenas = [m.group("cad") for m in _TAG_SIMPLE_RE.finditer(texto)]
    for m in _BLOCKTRANS_RE.finditer(texto):
        cuerpo = " ".join(m.group("cuerpo").split())
        cuerpo = _VARIABLE_RE.sub(lambda mm: "%(" + mm.group(1) + ")s", cuerpo)
        cadenas.append(cuerpo)
    return cadenas


def _literales_traducibles_en_el_codigo(raiz_apps, raiz_templates):
    literales = set()
    for archivo in sorted(raiz_apps.rglob("*.py")):
        if "migrations" in archivo.parts or "__pycache__" in archivo.parts:
            continue
        literales.update(_cadenas_python(archivo.read_text(encoding="utf-8")))
    for archivo in sorted(raiz_templates.rglob("*.html")):
        literales.update(_cadenas_plantilla(archivo.read_text(encoding="utf-8")))
    literales.discard("")
    return literales


def _msgids_del_catalogo(texto_po):
    return {_texto_de_cadenas(m.group("msgid")) for m in _ENTRADA_RE.finditer(texto_po)} - {""}


def _cadenas_faltantes(raiz_apps, raiz_templates, texto_po):
    literales = _literales_traducibles_en_el_codigo(raiz_apps, raiz_templates)
    catalogo = _msgids_del_catalogo(texto_po)
    return sorted(literales - catalogo)


# --- Pruebas -----------------------------------------------------------------


def test_todo_literal_traducible_del_arbol_real_esta_en_el_catalogo_frances():
    raiz = Path(settings.BASE_DIR)
    faltantes = _cadenas_faltantes(raiz / "apps", raiz / "templates", CATALOGO_FR.read_text(encoding="utf-8"))
    assert not faltantes, (
        "Cadenas traducibles del código que no llegaron al catálogo francés:\n"
        + "\n".join(faltantes)
    )


def test_la_deteccion_de_cadenas_faltantes_falla_ante_un_literal_no_catalogado(tmp_path):
    """Prueba de la prueba: si esta guardia no puede fallar, no vigila nada.
    Se construye un árbol apps/ + templates/ de juguete (no el real) con una
    cadena Python sin traducir, una plantilla con {% translate %} sin
    traducir y un blocktranslate con variable sin traducir; se comprueba que
    las tres se detectan y que, al completarse el catálogo, dejan de
    detectarse."""
    apps_falsas = tmp_path / "apps"
    (apps_falsas / "demo").mkdir(parents=True)
    (apps_falsas / "demo" / "views.py").write_text(
        "from django.utils.translation import gettext_lazy as _\n"
        'MENSAJE = _("Cadena de prueba sin traducir")\n',
        encoding="utf-8",
    )

    templates_falsas = tmp_path / "templates"
    templates_falsas.mkdir()
    (templates_falsas / "demo.html").write_text(
        '<h1>{% translate "Título de prueba" %}</h1>\n'
        "<p>{% blocktranslate with nombre=usuario %}Hola {{ nombre }}{% endblocktranslate %}</p>\n",
        encoding="utf-8",
    )

    po_vacio = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'

    faltantes = _cadenas_faltantes(apps_falsas, templates_falsas, po_vacio)
    assert faltantes == [
        "Cadena de prueba sin traducir",
        "Hola %(nombre)s",
        "Título de prueba",
    ]

    po_completo = po_vacio + (
        '\nmsgid "Cadena de prueba sin traducir"\nmsgstr "Chaîne de test"\n'
        '\nmsgid "Título de prueba"\nmsgstr "Titre de test"\n'
        '\nmsgid "Hola %(nombre)s"\nmsgstr "Bonjour %(nombre)s"\n'
    )
    assert _cadenas_faltantes(apps_falsas, templates_falsas, po_completo) == []

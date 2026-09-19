"""`{% estatico %}` anade la fecha de modificacion del archivo a la URL.

Sin esto, runserver sirve /static/ con Last-Modified y sin Cache-Control, y el
navegador aplica cache heuristica: tras cambiar un CSS la pagina seguia
pintandose con la hoja vieja hasta un Ctrl+F5. El service worker en
produccion tenia el mismo problema con su cache-first.
"""

import os
import re

from django.template import Context, Template


def _render(ruta):
    return Template("{% load estaticos %}{% estatico '" + ruta + "' %}").render(Context())


def test_la_url_lleva_la_fecha_de_modificacion_del_archivo():
    url = _render("css/base.css")
    assert re.fullmatch(r"/static/css/base\.css\?v=\d+", url), url


def test_cambiar_el_archivo_cambia_la_url(tmp_path, settings):
    hoja = tmp_path / "prueba.css"
    hoja.write_text("a{}")
    settings.STATICFILES_DIRS = [tmp_path]
    antes = _render("prueba.css")
    os.utime(hoja, (1_700_000_000, 1_700_000_000))
    despues = _render("prueba.css")
    assert antes != despues
    assert despues.endswith("?v=1700000000")


def test_un_archivo_inexistente_no_rompe_la_plantilla():
    assert _render("no/existe.css") == "/static/no/existe.css"


def test_base_html_usa_la_etiqueta_para_todo_css_y_js():
    from pathlib import Path

    from django.conf import settings as s

    base = (Path(s.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
    assert "{% static 'css/" not in base
    assert "{% static 'vendor/" not in base
    assert "{% estatico 'css/components.css' %}" in base

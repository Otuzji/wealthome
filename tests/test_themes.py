import pytest
from django.urls import reverse

from tests.factories import UserFactory


@pytest.mark.django_db
def test_la_pagina_lleva_el_tema_del_perfil(client):
    user = UserFactory()
    user.profile.theme = "nocturno"
    user.profile.save()
    client.force_login(user)

    html = client.get(reverse("accounts:inicio")).content.decode()
    assert 'data-theme="nocturno"' in html


@pytest.mark.django_db
def test_el_tema_por_defecto_es_sereno(client):
    user = UserFactory()
    client.force_login(user)
    html = client.get(reverse("accounts:inicio")).content.decode()
    assert 'data-theme="sereno"' in html


@pytest.mark.django_db
def test_un_visitante_sin_sesion_ve_el_tema_sereno(client):
    html = client.get(reverse("accounts:login")).content.decode()
    assert 'data-theme="sereno"' in html


@pytest.mark.django_db
def test_el_idioma_del_perfil_manda_sobre_el_del_navegador(client):
    user = UserFactory()
    user.profile.language = "fr"
    user.profile.save()
    client.force_login(user)

    respuesta = client.get(reverse("accounts:inicio"), HTTP_ACCEPT_LANGUAGE="en")
    html = respuesta.content.decode()
    assert 'lang="fr"' in html


@pytest.mark.django_db
def test_el_idioma_del_perfil_manda_tambien_en_content_language(client):
    """El header Content-Language no debe quedar corrompido por deactivate()."""
    user = UserFactory()
    user.profile.language = "fr"
    user.profile.save()
    client.force_login(user)

    respuesta = client.get(reverse("accounts:inicio"), HTTP_ACCEPT_LANGUAGE="en")
    assert respuesta.headers["Content-Language"] == "fr"


def _leer_tokens_css():
    from pathlib import Path

    from django.conf import settings

    return Path(settings.BASE_DIR / "static/css/tokens.css").read_text(encoding="utf-8")


def _extraer_bloque(css, selector):
    """Devuelve {variable: valor} de las declaraciones --var: valor; dentro
    del bloque del selector dado, para no depender de que la subcadena
    aparezca en cualquier parte del archivo (lo que dejaría pasar un bloque
    vacío o un valor equivocado)."""
    import re

    patron = re.escape(selector) + r"\s*\{([^}]*)\}"
    coincidencia = re.search(patron, css)
    assert coincidencia, f'selector {selector!r} no encontrado en tokens.css'
    cuerpo = coincidencia.group(1)
    return {
        declaracion.group(1): declaracion.group(2).strip()
        for declaracion in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", cuerpo)
    }


# Tokens que base.css/components.css referencian con var(...); si faltan en
# :root, algún componente quedaría con un valor sin definir.
TOKENS_QUE_USAN_LOS_COMPONENTES = [
    "--bg",
    "--surface",
    "--text",
    "--accent",
    "--accent-strong",
    "--font-family",
    "--font-size-base",
    "--font-weight-strong",
    "--radius",
    "--radius-sm",
    "--border-width",
    "--border-color",
    "--shadow-raised",
    "--touch-target",
]


@pytest.mark.django_db
def test_los_tres_temas_estan_definidos_en_tokens_css():
    css = _leer_tokens_css()
    raiz = _extraer_bloque(css, ":root")
    nocturno = _extraer_bloque(css, '[data-theme="nocturno"]')
    accesible = _extraer_bloque(css, '[data-theme="accesible"]')

    for token in TOKENS_QUE_USAN_LOS_COMPONENTES:
        assert token in raiz, f"falta {token} en :root (Sereno)"

    # Nocturno y Accesible deben redefinir variables de verdad, no ser
    # selectores vacíos que ganan la prueba por solo existir en el texto.
    assert nocturno, "el bloque nocturno no redefine ninguna variable"
    assert accesible, "el bloque accesible no redefine ninguna variable"

    # Nocturno invierte la paleta de verdad, no un bloque vacío que "existe".
    assert nocturno["--bg"] != raiz["--bg"]
    assert nocturno["--text"] != raiz["--text"]


@pytest.mark.django_db
def test_el_tema_accesible_usa_bordes_y_no_solo_sombras():
    """Spec §7.4: en Accesible el relieve se sustituye por bordes sólidos.

    No basta con que --border-width y --font-size-base aparezcan en el
    bloque: hay que comprobar que valen lo que deben valer y que de verdad
    difieren de Sereno, para que un revertido silencioso (p. ej. un bloque
    accesible idéntico a :root) haga fallar la prueba.
    """
    css = _leer_tokens_css()
    raiz = _extraer_bloque(css, ":root")
    accesible = _extraer_bloque(css, '[data-theme="accesible"]')

    assert accesible["--border-width"] == "3px"
    assert accesible["--border-width"] != raiz["--border-width"]

    assert accesible["--font-size-base"] == "20px"
    assert accesible["--font-size-base"] != raiz["--font-size-base"]

    assert accesible["--shadow-inset"] == "none"

    assert accesible["--touch-target"] == "56px"
    assert accesible["--touch-target"] != raiz["--touch-target"]

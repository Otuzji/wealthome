"""Las garantías que sólo importan cuando la aplicación está en internet.

Tres cosas distintas, juntas porque las tres se rompen igual —en silencio, y
sólo en producción, donde nadie las mira hasta que ya ha pasado algo:

1. El `x-data` de Alpine no puede reflejar lo que llegó en el POST sin
   escaparlo (XSS reflejado).
2. `DJANGO_REGISTRO_ABIERTO=0` cierra de verdad el alta pública.
3. La configuración de producción no reabre ninguno de los cuatro avisos de
   `manage.py check --deploy` que se cerraron antes del piloto.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template
from django.test import Client, override_settings
from django.urls import reverse

from apps.budget.forms import IncomeSourceForm
from apps.households.services import crear_hogar
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


# Cierra el atributo, cierra el formulario y abre una etiqueta propia: es la
# carga que funcionaba antes de escapar `x_data`.
CARGA = "'\"><script>alert(1)</script>"


def test_x_data_no_refleja_el_post_sin_escapar():
    """Un `amount_type` hostil no puede salirse del atributo `x-data`.

    El formulario se vuelve a pintar precisamente cuando es inválido, y
    `BoundField.value()` devuelve entonces el dato CRUDO del POST — sin pasar
    por la validación. La plantilla lo pinta con `|safe`, así que el escape
    tiene que estar puesto en el formulario.
    """
    hogar = crear_hogar(UserFactory(), "Casa", 2)
    form = IncomeSourceForm(data={"amount_type": CARGA}, household=hogar)

    assert not form.is_valid(), "la carga tiene que ser un valor inválido"

    render = Template('<form x-data="{{ form.x_data|safe }}">').render(
        Context({"form": form})
    )
    assert "<script>" not in render
    assert "</form>" not in render
    # El valor sigue llegando a Alpine, sólo escapado: si se hubiera perdido,
    # el formulario se pintaría con el modo equivocado.
    assert "\\u003C" in render or "u003c" in render.lower()


@override_settings(REGISTRO_ABIERTO=False)
def test_registro_cerrado_contesta_404(client):
    """404 y no 403: un 403 confirma que el formulario existe y está apagado."""
    assert client.get(reverse("accounts:registro")).status_code == 404
    assert client.post(reverse("accounts:registro"), {}).status_code == 404


@override_settings(REGISTRO_ABIERTO=False)
def test_login_no_ofrece_crear_hogar_con_el_registro_cerrado(client):
    respuesta = client.get(reverse("accounts:login"))
    assert reverse("accounts:registro") not in respuesta.content.decode()


@override_settings(REGISTRO_ABIERTO=True)
def test_registro_abierto_sigue_sirviendo_el_formulario(client):
    assert client.get(reverse("accounts:registro")).status_code == 200


# Los cuatro que estaban abiertos antes del piloto: la cookie de sesión y la de
# CSRF viajando en claro, sin redirección a https y sin HSTS. W005 y W021
# quedan fuera a propósito —son "sube HSTS a un año y añade subdominios", que
# se hace cuando el certificado lleva unos días estable.
AVISOS_QUE_NO_PUEDEN_VOLVER = ["W004", "W008", "W012", "W016"]


def test_la_configuracion_de_produccion_no_reabre_los_avisos_cerrados():
    """`manage.py check --deploy`, pero desde la suite.

    Se ejecuta con los ajustes de producción forzados a mano porque las pruebas
    corren con DEBUG y el bloque `if not DEBUG` de settings.py no se evalúa.
    """
    from django.core.checks import registry as registro_de_comprobaciones

    produccion = dict(
        DEBUG=False,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=3600,
        ALLOWED_HOSTS=["wealthome.site"],
        CSRF_TRUSTED_ORIGINS=["https://wealthome.site"],
    )
    with override_settings(**produccion):
        avisos = registro_de_comprobaciones.run_checks(
            tags=["security"], include_deployment_checks=True
        )
    ids = {aviso.id for aviso in avisos}
    reabiertos = [a for a in AVISOS_QUE_NO_PUEDEN_VOLVER if f"security.{a}" in ids]
    assert not reabiertos, f"vuelven a estar abiertos: {reabiertos} — {ids}"


def test_settings_de_produccion_derivan_csrf_trusted_origins_de_allowed_hosts():
    """Las dos listas no se mantienen a mano: olvidar un dominio en
    CSRF_TRUSTED_ORIGINS da un 403 en todos los formularios de ese dominio."""
    import importlib
    import os

    entorno = {
        "DJANGO_DEBUG": "0",
        "DJANGO_SECRET_KEY": "x" * 60,
        "DATABASE_URL": "postgresql://u:p@localhost:5432/x",
        # Con un espacio de sobra a propósito: es como se escribe la variable.
        "DJANGO_ALLOWED_HOSTS": "wealthome.site, www.wealthome.site",
    }
    previos = {k: os.environ.get(k) for k in entorno}
    os.environ.update(entorno)
    try:
        modulo = importlib.import_module("config.settings")
        recargado = importlib.reload(modulo)
        assert recargado.ALLOWED_HOSTS == ["wealthome.site", "www.wealthome.site"]
        assert recargado.CSRF_TRUSTED_ORIGINS == [
            "https://wealthome.site",
            "https://www.wealthome.site",
        ]
    finally:
        for k, v in previos.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        # Deja el módulo como estaba: si se queda con DEBUG=False, las pruebas
        # que corran después heredan la configuración de producción.
        importlib.reload(importlib.import_module("config.settings"))


# ---------------------------------------------------------------------------
# El cableado que solo existe con DEBUG=0. Se prueba con override_settings y no
# arrancando un servidor porque lo que puede fallar es la configuracion, no el
# codigo: detras de nginx, olvidar X-Forwarded-Proto da un bucle infinito de
# redirecciones y un 403 en todos los formularios, y las dos cosas se ven desde
# el cliente de pruebas.
# ---------------------------------------------------------------------------
PROD = dict(
    DEBUG=False,
    ALLOWED_HOSTS=["testserver"],
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    CSRF_TRUSTED_ORIGINS=["https://testserver"],
)


@override_settings(**PROD)
def test_http_redirige_a_https():
    r = Client().get("/login/")
    assert r.status_code == 301, r.status_code
    assert r["Location"].startswith("https://"), r["Location"]


@override_settings(**PROD)
def test_con_x_forwarded_proto_no_redirige():
    """La cabecera de nginx evita el bucle infinito de redirecciones."""
    r = Client().get("/login/", HTTP_X_FORWARDED_PROTO="https")
    assert r.status_code == 200, r.status_code


@override_settings(**PROD)
def test_login_por_post_no_da_403_de_csrf():
    """El 403 en todos los formularios es el fallo clasico detras de un proxy."""
    user = UserFactory()
    user.set_password("contrasena-larga-de-prueba-9")
    user.save()
    crear_hogar(user, "Casa", 2)

    c = Client(enforce_csrf_checks=True)
    pagina = c.get("/login/", HTTP_X_FORWARDED_PROTO="https")
    token = pagina.cookies["csrftoken"].value

    r = c.post(
        "/login/",
        {"username": user.email, "password": "contrasena-larga-de-prueba-9",
         "csrfmiddlewaretoken": token},
        HTTP_X_FORWARDED_PROTO="https",
        HTTP_ORIGIN="https://testserver",
    )
    assert r.status_code != 403, "CSRF rechazo el POST"
    assert r.status_code == 302, r.status_code


@override_settings(**PROD)
def test_la_cookie_de_sesion_es_secure_y_httponly():
    user = UserFactory()
    user.set_password("contrasena-larga-de-prueba-9")
    user.save()
    crear_hogar(user, "Casa", 2)
    c = Client()
    c.post("/login/", {"username": user.email,
                       "password": "contrasena-larga-de-prueba-9"},
           HTTP_X_FORWARDED_PROTO="https")
    cookie = c.cookies["sessionid"]
    assert cookie["secure"], "la cookie de sesion viajaria en claro"
    assert cookie["httponly"], "JavaScript podria leer la cookie de sesion"


@override_settings(**PROD)
def test_whitenoise_sirve_los_estaticos_sin_debug():
    """Sin esto el piloto se veria en HTML pelado.

    WhiteNoise sirve desde STATIC_ROOT, que lo llena `collectstatic`. En un
    clon recien hecho ese directorio no existe todavia, y la prueba se salta en
    vez de fallar: lo que verifica es el cableado, no que alguien haya corrido
    collectstatic en su portatil.
    """
    if not settings.STATIC_ROOT or not Path(settings.STATIC_ROOT).is_dir():
        pytest.skip("STATIC_ROOT vacio: correr `manage.py collectstatic` primero")

    r = Client().get("/static/css/base.css", HTTP_X_FORWARDED_PROTO="https")
    assert r.status_code == 200, f"WhiteNoise no sirvio el CSS: {r.status_code}"
    assert "css" in r["Content-Type"]


@override_settings(**PROD)
def test_la_aplicacion_responde_en_modo_produccion():
    """Las pantallas principales, con DEBUG=0 y la plantilla 500 de verdad."""
    user = UserFactory()
    user.set_password("contrasena-larga-de-prueba-9")
    user.save()
    crear_hogar(user, "Casa", 2)
    c = Client()
    c.force_login(user)
    for nombre in ("accounts:inicio", "households:ajustes",
                   "subscriptions:estado", "accounts:preferencias"):
        r = c.get(reverse(nombre), HTTP_X_FORWARDED_PROTO="https")
        assert r.status_code == 200, f"{nombre} -> {r.status_code}"


def test_la_pagina_500_se_pinta_sin_peticion_y_sin_contexto():
    """`server_error` la renderiza con `template.render()`, sin peticion.

    Si alguien le pone `{% extends "base.html" %}`, base.html pide los `nav_*`
    de los procesadores de contexto —que no corren— y Django acaba sirviendo su
    propia pagina gris de reserva justo cuando no se la quiere ensenar. Esta
    prueba es la que lo nota.
    """
    from django.template import loader
    from django.utils import translation

    plantilla = loader.get_template("500.html")
    for idioma, esperado in (("en", "Something went wrong"),
                             ("fr", "Une erreur est survenue")):
        with translation.override(idioma):
            html = plantilla.render()      # sin contexto y sin request, a proposito
        assert esperado in html, f"{idioma}: {html[:200]}"
        assert "<style>" in html, "los estilos van dentro: /static/ puede ser lo roto"

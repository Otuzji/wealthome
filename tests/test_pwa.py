"""La PWA: manifiesto, iconos y service worker."""

import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def test_el_manifiesto_es_json_valido_y_completo():
    manifiesto = json.loads(
        (RAIZ / "static" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifiesto["name"]
    assert manifiesto["start_url"]
    assert manifiesto["display"] == "standalone"
    tamanos = {icono["sizes"] for icono in manifiesto["icons"]}
    assert {"192x192", "512x512"} <= tamanos


def test_los_iconos_que_el_manifiesto_promete_existen_y_miden_lo_que_dice():
    """No esta en el plan. Un manifiesto que apunta a un icono que no existe pasa
    la prueba de JSON valido y falla en el movil, donde nadie lo esta mirando.
    """
    from PIL import Image

    manifiesto = json.loads(
        (RAIZ / "static" / "manifest.json").read_text(encoding="utf-8")
    )
    for icono in manifiesto["icons"]:
        ruta = RAIZ / icono["src"].lstrip("/")
        assert ruta.exists(), f"{icono['src']} no existe"
        ancho, alto = Image.open(ruta).size
        assert f"{ancho}x{alto}" == icono["sizes"], (
            f"{icono['src']} mide {ancho}x{alto} y el manifiesto dice "
            f"{icono['sizes']}"
        )


@pytest.mark.django_db
def test_la_pagina_enlaza_el_manifiesto(client):
    from django.urls import reverse

    respuesta = client.get(reverse("accounts:login"))

    assert b"manifest.json" in respuesta.content


# --- el service worker (Tarea 30) ---------------------------------------------


def test_el_service_worker_no_cachea_el_webhook_ni_el_login():
    sw = (RAIZ / "static" / "js" / "sw.js").read_text(encoding="utf-8")

    assert "/subscription/webhook/" in sw
    assert "logout" in sw
    # Solo GET: cachear un POST serviria una respuesta de escritura vieja.
    assert "request.method" in sw or "peticion.method" in sw


def test_el_service_worker_precarga_solo_cosas_que_existen():
    """No esta en el plan, y es la clase de fallo que rompe el service worker
    ENTERO: cache.addAll rechaza si UNA sola entrada da 404, asi que un archivo
    mal escrito en PRECARGA deja la aplicacion sin nada cacheado y sin aviso.
    """
    import re

    sw = (RAIZ / "static" / "js" / "sw.js").read_text(encoding="utf-8")
    bloque = sw.split("var PRECARGA = [", 1)[1].split("];", 1)[0]
    rutas = re.findall(r'"([^"]+)"', bloque)
    assert rutas, "no encontre la lista de precarga"

    for ruta in rutas:
        if ruta.startswith("/static/"):
            archivo = RAIZ / ruta.lstrip("/")
            assert archivo.exists(), f"PRECARGA apunta a {ruta}, que no existe"
        else:
            # Las rutas de Django se comprueban resolviendolas.
            from django.urls import resolve
            assert resolve(ruta), f"PRECARGA apunta a {ruta}, que no resuelve"


@pytest.mark.django_db
def test_el_service_worker_no_se_registra_en_desarrollo(client, settings):
    from django.urls import reverse

    settings.DEBUG = True
    assert b"serviceWorker" not in client.get(reverse("accounts:login")).content

    settings.DEBUG = False
    assert b"serviceWorker" in client.get(reverse("accounts:login")).content


@pytest.mark.django_db
def test_la_pagina_de_sin_conexion_no_exige_sesion(client):
    """El service worker tiene que poder precargarla sin estar autenticado."""
    from django.urls import reverse

    respuesta = client.get(reverse("sin_conexion"))

    assert respuesta.status_code == 200

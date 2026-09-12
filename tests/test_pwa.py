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

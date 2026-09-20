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
    sw = (RAIZ / "templates" / "sw.js").read_text(encoding="utf-8")

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

    sw = (RAIZ / "templates" / "sw.js").read_text(encoding="utf-8")
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


# --- la purga al cerrar sesion (Tarea 31) -------------------------------------


@pytest.mark.django_db
def test_cerrar_sesion_manda_clear_site_data(client):
    from django.urls import reverse

    from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.post(reverse("accounts:logout"))

    cabecera = respuesta.headers.get("Clear-Site-Data", "")
    assert "cache" in cabecera
    assert "storage" in cabecera


@pytest.mark.django_db
def test_hay_por_donde_cerrar_sesion(client):
    """No esta en el plan, y hacia falta: la ruta de logout existia desde el Plan 1
    y NINGUNA plantilla enlazaba a ella. Nadie podia cerrar sesion desde la
    interfaz, y la prueba de navegador de esta tarea no habria encontrado el boton
    que va a pulsar.
    """
    from django.urls import reverse

    from apps.budget.seeds import sembrar
    from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

    hogar = HouseholdFactory()
    sembrar(hogar)
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    cuerpo = client.get(reverse("households:ajustes")).content.decode()

    assert f'action="{reverse("accounts:logout")}"' in cuerpo
    # POST, no GET: Django 5 exige POST para cerrar sesion.
    assert 'method="post"' in cuerpo


@pytest.mark.navegador
@pytest.mark.django_db(transaction=True)
def test_cerrar_sesion_deja_la_cache_vacia(page, live_server, settings):
    """La unica prueba de navegador del plan.

    La purga es una garantia de privacidad: la cache guarda las finanzas de una
    familia en un dispositivo que puede ser compartido. Una comprobacion manual
    se hace una vez; esta se hace siempre.
    """
    from apps.budget.seeds import sembrar
    from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

    settings.DEBUG = False
    hogar = HouseholdFactory()
    sembrar(hogar)
    user = UserFactory()
    user.set_password("clave-larga-123")
    user.save()
    MembershipFactory(user=user, household=hogar, role="admin")

    page.goto(live_server.url + "/login/")
    # El formulario es el AuthenticationForm de Django, cuyo campo se llama
    # `username` aunque USERNAME_FIELD sea el correo. Verificado, no supuesto.
    page.fill("input[name='username']", user.email)
    page.fill("input[name='password']", "clave-larga-123")
    page.click("button[type='submit']")

    page.goto(live_server.url + "/household/settings/")
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    page.wait_for_function("caches.keys().then(k => k.length > 0)")

    # Antes de salir, la cache de PAGINAS tiene la pantalla del hogar.
    paginas_antes = page.evaluate(
        "caches.open('paginas-wealthome-v15')"
        ".then(c => c.keys()).then(k => k.map(r => new URL(r.url).pathname))"
    )
    assert any("/household/settings/" in ruta for ruta in paginas_antes), (
        f"la cache de paginas no llego a guardar la pantalla: {paginas_antes}"
    )

    # Sign out vive en el drawer del avatar: hay que abrirlo antes de pulsarlo.
    page.click(".barra__avatar")
    page.click("form[action*='logout'] button[type='submit']")
    # Lo que se afirma es la GARANTIA, no `caches.keys() == []`.
    #
    # El plan pedia que no quedara ninguna cache, pero eso contradice su propio
    # diseno: al salir, el navegador va a /login/, esa pagina vuelve a registrar
    # el service worker y su `install` reprecarga el armazon. Asi que `armazon-`
    # reaparece siempre, y eso esta BIEN — solo lleva CSS, JS, el manifiesto y el
    # icono. Lo que no puede sobrevivir es la cache de PAGINAS, que es la que
    # guarda las finanzas de la familia. Eso es lo que se comprueba.
    page.wait_for_function(
        "caches.keys().then(k => k.every(n => !n.startsWith('paginas-')))",
        timeout=10000,
    )

    claves = page.evaluate("caches.keys()")
    assert not [n for n in claves if n.startswith("paginas-")], claves

    # Y por si alguien renombra las caches: ninguna respuesta guardada puede ser
    # una pagina del hogar, se llame la cache como se llame.
    rutas = page.evaluate(
        "caches.keys()"
        ".then(ns => Promise.all(ns.map(n => caches.open(n).then(c => c.keys()))))"
        ".then(ls => ls.flat().map(r => new URL(r.url).pathname))"
    )
    fugas = [
        ruta for ruta in rutas
        if not ruta.startswith("/static/") and ruta != "/offline/"
    ]
    assert not fugas, f"quedan paginas cacheadas tras cerrar sesion: {fugas}"


@pytest.mark.navegador
@pytest.mark.django_db(transaction=True)
def test_sin_senal_se_ve_lo_ya_visitado_y_lo_demas_cae_en_la_pagina_de_offline(
    page, live_server, settings
):
    """El criterio 11, la mitad que faltaba.

    La prueba de la purga cubria cerrar sesion; esto cubre la promesa de al lado:
    "abre sin senal ensenando lo ya visitado". Se corta la red de verdad con
    page.route y se comprueba lo UNO y lo OTRO — que la pagina visitada sigue
    ahi, y que una que no se visito cae en /offline/ en vez de en el dinosaurio
    del navegador.
    """
    from apps.budget.seeds import sembrar
    from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

    settings.DEBUG = False
    hogar = HouseholdFactory()
    sembrar(hogar)
    user = UserFactory()
    user.set_password("clave-larga-123")
    user.save()
    MembershipFactory(user=user, household=hogar, role="admin")

    page.goto(live_server.url + "/login/")
    page.fill("input[name='username']", user.email)
    page.fill("input[name='password']", "clave-larga-123")
    page.click("button[type='submit']")

    # Se visita la pantalla del mes: eso la mete en la cache de paginas.
    page.goto(live_server.url + "/budget/household/month/")
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    page.wait_for_function(
        "caches.open('paginas-wealthome-v15').then(c => c.keys())"
        ".then(k => k.some(r => r.url.includes('/month/')))"
    )

    # Y ahora se corta la red. El service worker ya esta instalado y es quien
    # responde: lo que tenga cacheado lo sirve, y lo que no, va a /offline/.
    page.context.route("**", lambda ruta: ruta.abort())

    page.goto(live_server.url + "/budget/household/month/")
    assert "This month" in page.content() or "2026" in page.content(), (
        "la pantalla ya visitada no se sirvio desde la cache"
    )

    # Una que no se visito nunca: no hay copia, asi que toca la de sin conexion.
    page.goto(live_server.url + "/budget/household/goals/")
    assert "No connection" in page.content(), (
        "una pagina sin cachear deberia caer en /offline/, no en el error del "
        "navegador"
    )


def test_el_service_worker_sirve_la_precarga_si_falta_la_version_exacta():
    """Las URLs de estaticos llevan ?v=<mtime> (ver test_estaticos_versionados).
    Cache-first por URL completa hace que una version nueva se pida a la red;
    sin red, la copia precargada (sin ?v) tiene que valer, o la aplicacion
    offline se queda sin estilos."""
    sw = (RAIZ / "templates" / "sw.js").read_text(encoding="utf-8")
    rama = sw.split('indexOf("/static/") === 0', 1)[1].split("return;", 1)[0]
    assert "ignoreSearch: true" in rama
    assert "cache.put(peticion" in rama, "lo que llega de la red debe quedar cacheado para la proxima vez sin senal"


def test_el_service_worker_se_sirve_sin_error(client):
    """sw.js pasa por el motor de plantillas: un `{%` en un comentario lo
    tumba con un 500 y ningun navegador vuelve a instalarlo."""
    respuesta = client.get("/sw.js")
    assert respuesta.status_code == 200
    assert b"ignoreSearch" in respuesta.content

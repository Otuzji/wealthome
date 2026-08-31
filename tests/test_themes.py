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
def test_los_tres_temas_estan_definidos_en_tokens_css():
    from pathlib import Path

    from django.conf import settings

    css = Path(settings.BASE_DIR / "static/css/tokens.css").read_text(encoding="utf-8")
    assert ":root" in css
    assert '[data-theme="nocturno"]' in css
    assert '[data-theme="accesible"]' in css


@pytest.mark.django_db
def test_el_tema_accesible_usa_bordes_y_no_solo_sombras():
    """Spec §7.4: en Accesible el relieve se sustituye por bordes sólidos."""
    from pathlib import Path

    from django.conf import settings

    css = Path(settings.BASE_DIR / "static/css/tokens.css").read_text(encoding="utf-8")
    bloque = css.split('[data-theme="accesible"]')[1].split("}")[0]
    assert "--border-width" in bloque
    assert "--font-size-base" in bloque

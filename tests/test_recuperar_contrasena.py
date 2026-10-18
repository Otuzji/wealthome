"""Recuperar la contrasena con un enlace por correo.

Es el mecanismo de Django (token de un solo uso que caduca y que deja de valer
en cuanto cambia la contrasena), con las pantallas de Wealthome, el correo en el
idioma del dueno, y un efecto propio: cambiarla desbloquea la cuenta.
"""
import re
from datetime import timedelta

import pytest
from django.conf import settings as ajustes
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from tests.factories import UserFactory

User = get_user_model()

NUEVA = "otra-clave-muy-larga-2026"


def pedir(client, email):
    return client.post(reverse("accounts:password_reset"), {"email": email})


def enlace_del_correo(correo):
    return re.search(r"https?://testserver(/\S+/)", correo.body).group(1)


def cambiar(client, enlace, clave=NUEVA):
    # Django canjea el token por la sesion y redirige a una URL sin token.
    respuesta = client.get(enlace)
    assert respuesta.status_code == 302
    return client.post(respuesta.url, {"new_password1": clave, "new_password2": clave})


@pytest.mark.django_db
def test_la_pantalla_de_entrada_ofrece_recuperar_la_contrasena(client):
    respuesta = client.get(reverse("accounts:login"))
    assert reverse("accounts:password_reset") in respuesta.content.decode()


@pytest.mark.django_db
def test_pedirla_envia_un_enlace_al_correo(client):
    UserFactory(email="ana@example.com")

    respuesta = pedir(client, "ana@example.com")

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 1
    correo = mail.outbox[0]
    assert correo.to == ["ana@example.com"]
    assert "/password-reset/" in enlace_del_correo(correo)
    assert correo.alternatives, "el correo lleva version HTML"


@pytest.mark.django_db
def test_pedirla_no_depende_de_mayusculas(client):
    UserFactory(email="ana@example.com")
    pedir(client, "Ana@Example.com")
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_un_correo_desconocido_responde_igual_y_no_envia_nada(client):
    UserFactory(email="ana@example.com")
    conocido = pedir(client, "ana@example.com")
    desconocido = pedir(client, "nadie@example.com")

    assert desconocido.status_code == conocido.status_code == 302
    assert desconocido.url == conocido.url
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_la_pantalla_de_enviado_no_confirma_que_la_cuenta_exista(client):
    respuesta = client.get(reverse("accounts:password_reset_done"))
    assert "If an account exists" in respuesta.content.decode()


@pytest.mark.django_db
def test_el_enlace_cambia_la_contrasena_y_vuelve_a_la_entrada_con_aviso(client):
    user = UserFactory(email="ana@example.com")
    pedir(client, "ana@example.com")

    respuesta = cambiar(client, enlace_del_correo(mail.outbox[0]))

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("accounts:login")
    user.refresh_from_db()
    assert user.check_password(NUEVA)
    assert "_auth_user_id" not in client.session, "no entra sola"
    aviso = client.get(respuesta.url).content.decode()
    assert "Your password has been changed" in aviso


@pytest.mark.django_db
def test_el_enlace_sirve_una_sola_vez(client):
    UserFactory(email="ana@example.com")
    pedir(client, "ana@example.com")
    enlace = enlace_del_correo(mail.outbox[0])
    cambiar(client, enlace)

    respuesta = client.get(enlace, follow=True)

    assert "no longer valid" in respuesta.content.decode()


@pytest.mark.django_db
def test_el_enlace_caduca_a_las_24_horas():
    assert ajustes.PASSWORD_RESET_TIMEOUT == 24 * 60 * 60


@pytest.mark.django_db
def test_la_clave_nueva_pasa_los_validadores(client):
    user = UserFactory(email="ana@example.com")
    pedir(client, "ana@example.com")

    respuesta = cambiar(client, enlace_del_correo(mail.outbox[0]), clave="corta1")

    assert respuesta.status_code == 200
    user.refresh_from_db()
    assert not user.check_password("corta1")


@pytest.mark.django_db
def test_cambiarla_desbloquea_la_cuenta(client):
    user = UserFactory(email="ana@example.com")
    User.objects.filter(pk=user.pk).update(
        failed_logins=3,
        last_failed_login=timezone.now(),
        locked_until=timezone.now() + timedelta(minutes=30),
    )
    pedir(client, "ana@example.com")

    cambiar(client, enlace_del_correo(mail.outbox[0]))

    user.refresh_from_db()
    assert user.locked_until is None
    assert user.failed_logins == 0
    respuesta = client.post(
        reverse("accounts:login"), {"username": "ana@example.com", "password": NUEVA}
    )
    assert respuesta.status_code == 302


@pytest.mark.django_db
def test_el_correo_llega_en_el_idioma_del_dueno(client):
    user = UserFactory(email="ana@example.com")
    user.profile.language = "fr"
    user.profile.save()

    pedir(client, "ana@example.com")

    assert "mot de passe" in mail.outbox[0].subject.lower()


@pytest.mark.django_db
def test_las_pantallas_de_recuperar_no_se_cachean_en_el_service_worker(client):
    sw = client.get(reverse("service_worker")).content.decode()
    assert '"/password-reset/"' in sw

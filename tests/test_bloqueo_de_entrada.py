"""Tres fallos seguidos bloquean la cuenta 30 minutos y avisan por correo.

El bloqueo va por CUENTA, no por dispositivo: lo que se protege es la
contrasena de una persona, se pruebe desde donde se pruebe. El precio es que un
desconocido puede bloquear a alguien tecleando su correo; por eso cambiar la
contrasena con el enlace de recuperacion desbloquea al momento.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from tests.factories import UserFactory

User = get_user_model()

CLAVE = "clave-larga-123"


def entrar(client, email, clave):
    return client.post(reverse("accounts:login"), {"username": email, "password": clave})


def fallar(client, email, veces=1):
    for _ in range(veces):
        respuesta = entrar(client, email, "no-es-la-clave")
    return respuesta


@pytest.mark.django_db
def test_dos_fallos_no_bloquean(client):
    user = UserFactory(email="ana@example.com")
    fallar(client, "ana@example.com", 2)

    respuesta = entrar(client, "ana@example.com", CLAVE)

    assert respuesta.status_code == 302
    user.refresh_from_db()
    assert user.locked_until is None
    assert user.failed_logins == 0
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_el_tercer_fallo_bloquea_treinta_minutos(client):
    user = UserFactory(email="ana@example.com")
    antes = timezone.now()

    respuesta = fallar(client, "ana@example.com", 3)

    assert respuesta.status_code == 200
    assert "temporarily locked" in respuesta.content.decode()
    user.refresh_from_db()
    assert user.locked_until >= antes + timedelta(minutes=30)
    assert user.locked_until <= timezone.now() + timedelta(minutes=30)


@pytest.mark.django_db
def test_bloqueada_no_entra_ni_con_la_clave_correcta(client):
    UserFactory(email="ana@example.com")
    fallar(client, "ana@example.com", 3)

    respuesta = entrar(client, "ana@example.com", CLAVE)

    assert respuesta.status_code == 200
    assert "temporarily locked" in respuesta.content.decode()
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_el_mensaje_de_bloqueo_no_dice_cuanto_falta(client):
    UserFactory(email="ana@example.com")
    respuesta = fallar(client, "ana@example.com", 3)

    contenido = respuesta.content.decode().lower()
    assert "minute" not in contenido


@pytest.mark.django_db
def test_pasados_los_treinta_minutos_entra(client):
    user = UserFactory(email="ana@example.com")
    fallar(client, "ana@example.com", 3)
    User.objects.filter(pk=user.pk).update(locked_until=timezone.now() - timedelta(seconds=1))

    respuesta = entrar(client, "ana@example.com", CLAVE)

    assert respuesta.status_code == 302
    user.refresh_from_db()
    assert user.locked_until is None
    assert user.failed_logins == 0


@pytest.mark.django_db
def test_pasado_el_bloqueo_el_contador_empieza_de_cero(client):
    user = UserFactory(email="ana@example.com")
    fallar(client, "ana@example.com", 3)
    User.objects.filter(pk=user.pk).update(locked_until=timezone.now() - timedelta(seconds=1))

    fallar(client, "ana@example.com", 1)

    user.refresh_from_db()
    assert user.failed_logins == 1
    assert user.locked_until is None


@pytest.mark.django_db
def test_entrar_bien_pone_el_contador_a_cero(client):
    user = UserFactory(email="ana@example.com")
    fallar(client, "ana@example.com", 2)
    entrar(client, "ana@example.com", CLAVE)
    client.logout()

    fallar(client, "ana@example.com", 2)

    user.refresh_from_db()
    assert user.failed_logins == 2
    assert user.locked_until is None


@pytest.mark.django_db
def test_fallos_viejos_no_cuentan(client):
    """Dos fallos el mes pasado y uno hoy no son 'tres seguidos'."""
    user = UserFactory(email="ana@example.com")
    fallar(client, "ana@example.com", 2)
    User.objects.filter(pk=user.pk).update(
        last_failed_login=timezone.now() - timedelta(minutes=31)
    )

    fallar(client, "ana@example.com", 1)

    user.refresh_from_db()
    assert user.failed_logins == 1
    assert user.locked_until is None


@pytest.mark.django_db
def test_el_bloqueo_no_depende_de_mayusculas(client):
    user = UserFactory(email="ana@example.com")
    fallar(client, "ANA@example.com", 1)
    fallar(client, "Ana@Example.com", 1)
    fallar(client, "ana@example.com", 1)

    user.refresh_from_db()
    assert user.locked_until is not None


@pytest.mark.django_db
def test_un_correo_desconocido_responde_igual_y_no_envia_nada(client):
    UserFactory(email="ana@example.com")
    conocida = fallar(client, "ana@example.com", 1).content.decode()
    desconocida = fallar(client, "nadie@example.com", 3).content.decode()

    assert "temporarily locked" not in desconocida
    assert "Please enter a correct email" in conocida
    assert "Please enter a correct email" in desconocida
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_al_bloquearse_llega_un_correo_al_dueno(client):
    UserFactory(email="ana@example.com")
    fallar(client, "ana@example.com", 3)

    assert len(mail.outbox) == 1
    correo = mail.outbox[0]
    assert correo.to == ["ana@example.com"]
    assert "sign-in" in correo.subject.lower()
    cuerpo = correo.body
    assert "3" in cuerpo
    # Que hacer si no fue ella: el enlace de recuperacion, absoluto.
    assert "http://testserver" + reverse("accounts:password_reset") in cuerpo
    html = correo.alternatives[0][0]
    assert reverse("accounts:password_reset") in html


@pytest.mark.django_db
def test_un_solo_correo_por_bloqueo(client):
    UserFactory(email="ana@example.com")
    fallar(client, "ana@example.com", 6)
    entrar(client, "ana@example.com", CLAVE)

    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_el_correo_llega_en_el_idioma_del_dueno(client):
    user = UserFactory(email="ana@example.com")
    user.profile.language = "fr"
    user.profile.save()

    fallar(client, "ana@example.com", 3)

    assert "connexion" in mail.outbox[0].subject.lower()


@pytest.mark.django_db
def test_si_el_correo_falla_el_bloqueo_sigue(client, settings):
    settings.EMAIL_BACKEND = "tests.test_bloqueo_de_entrada.BackendQueFalla"
    user = UserFactory(email="ana@example.com")

    respuesta = fallar(client, "ana@example.com", 3)

    assert respuesta.status_code == 200
    user.refresh_from_db()
    assert user.locked_until is not None


class BackendQueFalla:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, mensajes):
        raise OSError("SMTP caido")


@pytest.mark.django_db
def test_el_admin_tambien_respeta_el_bloqueo(client):
    """/admin/login/ no puede ser la puerta trasera para probar contrasenas."""
    UserFactory(email="jefe@example.com", is_staff=True, is_superuser=True)
    for _ in range(3):
        client.post(reverse("admin:login"), {"username": "jefe@example.com", "password": "mal"})

    client.post(reverse("admin:login"), {"username": "jefe@example.com", "password": CLAVE})

    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_el_admin_puede_desbloquear_a_mano(client):
    user = UserFactory(email="ana@example.com")
    fallar(client, "ana@example.com", 3)
    user.refresh_from_db()
    user.locked_until = None
    user.failed_logins = 0
    user.save()

    assert entrar(client, "ana@example.com", CLAVE).status_code == 302

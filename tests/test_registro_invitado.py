"""El invitado que no tiene cuenta.

Antes el enlace de la invitación exigía sesión y la única salida era
"Create a household": el invitado acababa con un hogar propio y la invitación
sin aceptar. Ahora el enlace abre sin sesión y ofrece crear la cuenta como
miembro del hogar que ya existe.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.households.models import Invitation, Membership
from apps.households.services import crear_hogar, invitar
from tests.factories import UserFactory

User = get_user_model()

DATOS = {
    "display_name": "Marie",
    "email": "marie@example.com",
    "password1": "clave-muy-larga-2026",
    "password2": "clave-muy-larga-2026",
}


@pytest.fixture
def invitacion(db):
    admin = UserFactory(display_name="Anne")
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    return invitar(admin, hogar, "marie@example.com", language="fr")


def _url(inv):
    return reverse("households:aceptar", args=[inv.token])


def test_sin_sesion_el_enlace_da_la_bienvenida_con_hogar_e_invitador(client, invitacion):
    respuesta = client.get(_url(invitacion))

    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert "Family Thompson" in html
    assert "Anne" in html
    assert 'name="password1"' in html
    assert 'value="marie@example.com"' in html
    assert reverse("accounts:login") + "?next=" + _url(invitacion) in html


def test_sin_sesion_un_token_malo_muestra_el_error_y_no_el_formulario(client, db):
    respuesta = client.get(reverse("households:aceptar", args=["no-existe"]))

    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert "not valid" in html
    assert 'name="password1"' not in html


def test_registrarse_desde_la_invitacion_crea_la_cuenta_como_miembro(client, invitacion):
    respuesta = client.post(_url(invitacion), DATOS)

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("accounts:inicio")
    marie = User.objects.get(email="marie@example.com")
    membresia = Membership.objects.get(user=marie)
    assert membresia.household == invitacion.household
    assert membresia.role == Membership.MEMBER
    invitacion.refresh_from_db()
    assert invitacion.accepted_at is not None
    # Sin hogar propio: el que la invitó ya tiene uno.
    assert Membership.objects.filter(user=marie).count() == 1


def test_registrarse_desde_la_invitacion_deja_la_sesion_iniciada(client, invitacion):
    client.post(_url(invitacion), DATOS)
    assert client.get(reverse("accounts:inicio")).status_code == 200


def test_el_perfil_nace_en_el_idioma_de_la_invitacion(client, invitacion):
    client.post(_url(invitacion), DATOS)
    assert User.objects.get(email="marie@example.com").profile.language == "fr"


def test_el_invitado_puede_registrarse_con_otro_correo(client, invitacion):
    client.post(_url(invitacion), {**DATOS, "email": "marie.otro@example.com"})
    marie = User.objects.get(email="marie.otro@example.com")
    assert Membership.objects.filter(user=marie, household=invitacion.household).exists()


def test_un_correo_ya_registrado_no_crea_nada_y_apunta_al_login(client, invitacion):
    UserFactory(email="marie@example.com")

    respuesta = client.post(_url(invitacion), DATOS)

    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert "already exists" in html
    assert User.objects.filter(email="marie@example.com").count() == 1
    assert not Membership.objects.filter(household=invitacion.household, role=Membership.MEMBER).exists()


def test_si_el_correo_invitado_ya_tiene_cuenta_la_bienvenida_lo_dice(client, invitacion):
    UserFactory(email="marie@example.com")
    html = client.get(_url(invitacion)).content.decode()
    assert "already have an account" in html


def test_una_invitacion_caducada_no_deja_registrarse(client, invitacion):
    Invitation.objects.filter(pk=invitacion.pk).update(expires_at=timezone.now())

    respuesta = client.post(_url(invitacion), DATOS)

    assert respuesta.status_code == 200
    assert "expired" in respuesta.content.decode()
    assert not User.objects.filter(email="marie@example.com").exists()


def test_contrasenas_distintas_no_crean_la_cuenta(client, invitacion):
    respuesta = client.post(_url(invitacion), {**DATOS, "password2": "otra-cosa-distinta"})
    assert respuesta.status_code == 200
    assert "do not match" in respuesta.content.decode()
    assert not User.objects.filter(email="marie@example.com").exists()


def test_con_sesion_iniciada_se_sigue_ofreciendo_aceptar_sin_formulario(client, invitacion):
    marie = UserFactory()
    client.force_login(marie)

    html = client.get(_url(invitacion)).content.decode()

    assert "Family Thompson" in html
    assert "Accept invitation" in html
    assert 'name="password1"' not in html

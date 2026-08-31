import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.households.models import Membership

User = get_user_model()

DATOS = {
    "email": "otton@example.com",
    "display_name": "Otton",
    "password1": "clave-muy-larga-2026",
    "password2": "clave-muy-larga-2026",
    "household_name": "Family Thompson",
    "family_size": 4,
}


@pytest.mark.django_db
def test_registrarse_crea_usuario_perfil_hogar_y_membresia_admin(client):
    respuesta = client.post(reverse("accounts:registro"), DATOS)
    assert respuesta.status_code == 302

    user = User.objects.get(email="otton@example.com")
    assert user.profile.theme == "sereno"

    membresia = Membership.objects.get(user=user)
    assert membresia.role == Membership.ADMIN
    assert membresia.household.name == "Family Thompson"
    assert membresia.household.family_size == 4


@pytest.mark.django_db
def test_registrarse_deja_la_sesion_iniciada(client):
    client.post(reverse("accounts:registro"), DATOS)
    respuesta = client.get(reverse("accounts:inicio"))
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_no_se_puede_registrar_dos_veces_el_mismo_email(client):
    client.post(reverse("accounts:registro"), DATOS)
    client.logout()
    respuesta = client.post(reverse("accounts:registro"), DATOS)
    assert respuesta.status_code == 200  # vuelve al formulario con errores
    assert User.objects.filter(email="otton@example.com").count() == 1


@pytest.mark.django_db
def test_las_claves_deben_coincidir(client):
    datos = DATOS | {"password2": "otra-clave-distinta-2026"}
    respuesta = client.post(reverse("accounts:registro"), datos)
    assert respuesta.status_code == 200
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_inicio_exige_sesion(client):
    respuesta = client.get(reverse("accounts:inicio"))
    assert respuesta.status_code == 302
    assert reverse("accounts:login") in respuesta.url


@pytest.mark.django_db
def test_una_clave_demasiado_corta_no_registra(client):
    datos = DATOS | {"password1": "corta1", "password2": "corta1"}
    respuesta = client.post(reverse("accounts:registro"), datos)
    assert respuesta.status_code == 200
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_family_size_fuera_de_rango_no_registra(client):
    datos = DATOS | {"family_size": 21}
    respuesta = client.post(reverse("accounts:registro"), datos)
    assert respuesta.status_code == 200
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_usuario_autenticado_no_ve_el_formulario_de_registro(client):
    client.post(reverse("accounts:registro"), DATOS)
    respuesta = client.get(reverse("accounts:registro"))
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("accounts:inicio")

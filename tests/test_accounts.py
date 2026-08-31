import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


@pytest.mark.django_db
def test_usuario_se_identifica_por_email():
    user = User.objects.create_user(email="marie@example.com", password="clave-larga-123")
    assert user.email == "marie@example.com"
    assert user.USERNAME_FIELD == "email"
    assert user.check_password("clave-larga-123")


@pytest.mark.django_db
def test_el_email_es_unico():
    User.objects.create_user(email="marie@example.com", password="clave-larga-123")
    with pytest.raises(Exception):
        User.objects.create_user(email="marie@example.com", password="otra-clave-123")


@pytest.mark.django_db
def test_crear_usuario_crea_su_perfil_con_valores_por_defecto():
    user = User.objects.create_user(email="otton@example.com", password="clave-larga-123")
    assert user.profile is not None
    assert user.profile.theme == "sereno"
    assert user.profile.language == "en"


@pytest.mark.django_db
def test_el_perfil_rechaza_un_tema_desconocido():
    user = User.objects.create_user(email="otton@example.com", password="clave-larga-123")
    user.profile.theme = "neon"
    with pytest.raises(ValidationError):
        user.profile.full_clean()


@pytest.mark.django_db
def test_el_perfil_acepta_los_tres_temas():
    user = User.objects.create_user(email="otton@example.com", password="clave-larga-123")
    for tema in ("sereno", "nocturno", "accesible"):
        user.profile.theme = tema
        user.profile.full_clean()  # no debe lanzar

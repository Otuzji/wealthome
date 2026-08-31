import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

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
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(email="marie@example.com", password="otra-clave-123")


@pytest.mark.django_db
def test_el_email_es_unico_sin_importar_mayusculas_via_create_user():
    """R-13: normalize_email baja la dirección completa, no solo el dominio,
    así que create_user/create_superuser ya no pueden crear dos cuentas que
    difieran solo en mayúsculas."""
    User.objects.create_user(email="marie@example.com", password="clave-larga-123")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(email="Marie@Example.com", password="otra-clave-123")


@pytest.mark.django_db
def test_la_restriccion_de_unicidad_insensible_a_mayusculas_protege_a_nivel_de_bd():
    """Si algo instancia el modelo a mano en vez de pasar por create_user/
    create_superuser (saltándose normalize_email), la UniqueConstraint(Lower)
    de la base de datos sigue impidiendo el duplicado por mayúsculas."""
    User.objects.create_user(email="marie@example.com", password="clave-larga-123")
    otro = User(email="MARIE@EXAMPLE.COM")
    otro.set_password("otra-clave-123")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            otro.save()


@pytest.mark.django_db
def test_create_superuser_rechaza_is_staff_false_explicito():
    """Como el UserManager estándar de Django: pasar is_staff=False a
    create_superuser no debe producir en silencio un "superusuario" sin
    privilegios de staff."""
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="root@example.com", password="clave-larga-123", is_staff=False
        )


@pytest.mark.django_db
def test_create_superuser_rechaza_is_superuser_false_explicito():
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="root2@example.com", password="clave-larga-123", is_superuser=False
        )


@pytest.mark.django_db
def test_admin_add_form_hashea_la_contrasena():
    """apps/accounts/admin.py registraba User con admin.site.register(User) a
    secas: sin UserAdmin, el ModelForm genérico trata "password" como texto
    plano y lo guarda tal cual. Esta prueba crea un usuario a través del
    formulario de alta del admin y comprueba que la contraseña quedó
    hasheada, no almacenada literal."""
    from apps.accounts.admin import UserCreationForm

    form = UserCreationForm(
        data={
            "email": "nuevo@example.com",
            "password1": "SuperClaveFuerte2026",
            "password2": "SuperClaveFuerte2026",
        }
    )
    assert form.is_valid(), form.errors
    user = form.save()
    assert user.check_password("SuperClaveFuerte2026")
    assert user.password != "SuperClaveFuerte2026"


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

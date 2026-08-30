# Wealthome Fase 1 · Plan 1: Fundación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir la base multi-inquilino de Wealthome — usuarios, hogares, membresías con permisos, aislamiento estricto entre hogares, invitaciones, bilingüismo EN/FR y los tres temas visuales — hasta tener una aplicación en la que un administrador se registra, crea su hogar, invita miembros y cada uno elige su tema e idioma.

**Architecture:** Django monolítico contra Postgres de Supabase. Django es dueño de toda la lógica de autorización: no se usan Supabase Auth ni políticas RLS. El aislamiento entre hogares se concentra en una capa central (`HouseholdScoped` + `require_permission`) en lugar de repartirse por las vistas. Frontend con plantillas de Django, sin build step.

**Tech Stack:** Python 3.11, Django 5.1, Postgres (Supabase), psycopg 3, Babel (formato de moneda por locale), pytest + pytest-django + factory_boy, CSS puro.

**Spec:** `docs/superpowers/specs/2026-08-30-wealthome-nucleo-financiero-design.md`

**Planes siguientes:** Plan 2 (motor financiero) y Plan 3 (interfaz y comercio) dependen de este.

## Global Constraints

- **Python 3.11**, **Django 5.1**. En Django 5.x el ajuste `USE_L10N` fue eliminado — la localización siempre está activa. No lo escribas en settings.
- **Todo importe monetario es `DecimalField(max_digits=12, decimal_places=2)`. Nunca `float`.** (Spec §3.4)
- **Todo texto visible al usuario pasa por `gettext`** (`{% trans %}` en plantillas, `gettext_lazy as _` en Python). Sin excepciones, desde la primera línea. (Spec §8)
- **Toda consulta con ámbito de hogar se filtra por el hogar del usuario autenticado.** (Spec §6.1)
- **Moneda: CAD.** Idiomas: `en` (por defecto) y `fr`.
- **Temas:** `sereno` (por defecto), `nocturno`, `accesible`. (Spec §7.4)
- **Máximo 6 membresías por hogar** (1 admin + 5). (Spec §3.1)
- Mensajes de commit en español, en imperativo.

---

## Estructura de archivos

```
manage.py
requirements.txt
.env.example
pytest.ini
config/
  settings.py          # un solo módulo; se divide si crece
  urls.py
  wsgi.py
apps/
  accounts/
    models.py          # User, Profile
    forms.py           # registro, login, preferencias
    views.py
    urls.py
    admin.py
    migrations/
  households/
    models.py          # Household, Membership, Invitation
    scoping.py         # HouseholdScoped, HouseholdScopedManager
    permissions.py     # require_permission, get_active_membership
    services.py        # crear hogar, invitar, aceptar
    forms.py
    views.py
    urls.py
    admin.py
    migrations/
  core/
    templatetags/
      money.py         # filtro de formato monetario por locale
templates/
  base.html
  accounts/
  households/
static/css/
  tokens.css           # los tres temas
  base.css
  components.css
  modules.css
locale/{en,fr}/LC_MESSAGES/
tests/
  conftest.py
  factories.py
  test_accounts.py
  test_households.py
  test_scoping.py
  test_invitations.py
  test_i18n.py
  test_themes.py
```

**Por qué así:** `scoping.py` y `permissions.py` son archivos propios y pequeños a propósito. Son el código con más consecuencias de seguridad del proyecto; separados, se auditan de un vistazo, y ninguna vista tiene excusa para reimplementar el filtrado a mano.

---

### Task 1: Andamiaje del proyecto y conexión a Supabase

**Files:**
- Create: `requirements.txt`, `.env.example`, `manage.py`, `pytest.ini`
- Create: `config/__init__.py`, `config/settings.py`, `config/urls.py`, `config/wsgi.py`
- Create: `apps/__init__.py`, `apps/core/__init__.py`
- Test: `tests/conftest.py`, `tests/test_smoke.py`

**Interfaces:**
- Consumes: nada (primera tarea)
- Produce: proyecto Django ejecutable; `pytest` operativo; ajustes `DATABASES`, `LANGUAGES`, `AUTH_USER_MODEL` listos para las tareas siguientes.

- [ ] **Step 1: Escribir la prueba de humo que falla**

`tests/test_smoke.py`:

```python
import pytest
from django.conf import settings


def test_django_configurado():
    assert settings.configured
    assert settings.LANGUAGE_CODE == "en"
    assert [code for code, _ in settings.LANGUAGES] == ["en", "fr"]


@pytest.mark.django_db
def test_base_de_datos_responde():
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL — no existe el proyecto Django (`ImproperlyConfigured` o `ModuleNotFoundError: config`)

- [ ] **Step 3: Crear el andamiaje**

`requirements.txt`:

```
Django==5.1.*
psycopg[binary]==3.2.*
python-dotenv==1.0.*
Babel==2.16.*
pytest==8.3.*
pytest-django==4.9.*
factory-boy==3.3.*
```

`.env.example`:

```
# Supabase → Project Settings → Database → Connection string → Transaction pooler
DATABASE_URL=postgresql://postgres.PROJECTREF:PASSWORD@aws-0-ca-central-1.pooler.supabase.com:6543/postgres
DJANGO_SECRET_KEY=cambiame-en-produccion
DJANGO_DEBUG=1
```

`config/settings.py`:

```python
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "inseguro-solo-para-tests")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_db = urlparse(os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/wealthome"))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.path.lstrip("/"),
        "USER": _db.username,
        "PASSWORD": _db.password,
        "HOST": _db.hostname,
        "PORT": _db.port or 5432,
        # El pooler de Supabase (puerto 6543) es un pgbouncer en modo transacción:
        # no soporta cursores del lado del servidor ni sentencias preparadas.
        "DISABLE_SERVER_SIDE_CURSORS": True,
        "OPTIONS": {"sslmode": "require"},
    }
}

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("fr", _("Français"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "America/Toronto"
USE_I18N = True
USE_TZ = True

# Moneda única del producto (spec §5.2)
DEFAULT_CURRENCY = "CAD"

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

`config/urls.py`:

```python
from django.contrib import admin
from django.urls import path

urlpatterns = [path("admin/", admin.site.urls)]
```

`config/wsgi.py`:

```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
```

`manage.py`:

```python
#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
```

`pytest.ini`:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py
testpaths = tests
```

`tests/conftest.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def _activar_idioma_por_defecto():
    """Cada prueba arranca en inglés salvo que active otro idioma."""
    from django.utils import translation

    translation.activate("en")
    yield
    translation.deactivate()
```

Crea también los `__init__.py` vacíos de `apps/`, `apps/core/` y `tests/`.

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `pip install -r requirements.txt && pytest tests/test_smoke.py -v`
Expected: PASS (2 pruebas)

Si `test_base_de_datos_responde` falla por conexión, copia `.env.example` a `.env` y pon la cadena real de Supabase. El usuario de Supabase debe poder crear la base de datos de pruebas; si no, ejecuta con `--reuse-db` tras crearla a mano.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example manage.py pytest.ini config apps tests
git commit -m "Añade el andamiaje del proyecto Django y la conexión a Supabase"
```

---

### Task 2: Usuario y perfil con tema e idioma

**Files:**
- Create: `apps/accounts/__init__.py`, `apps/accounts/models.py`, `apps/accounts/admin.py`, `apps/accounts/apps.py`
- Modify: `config/settings.py` (añadir `apps.accounts` e `AUTH_USER_MODEL`)
- Test: `tests/test_accounts.py`, `tests/factories.py`

**Interfaces:**
- Consumes: proyecto de la Task 1
- Produce:
  - `accounts.User` — usuario con `email` como identificador (`USERNAME_FIELD = "email"`), campos `email`, `display_name`, `is_active`, `is_staff`
  - `accounts.Profile` — `user` (OneToOne), `avatar`, `theme`, `language`
  - `Profile.THEMES = ["sereno", "nocturno", "accesible"]`, `Profile.LANGUAGES = ["en", "fr"]`
  - Se crea un `Profile` automáticamente al crear un `User`
  - `tests/factories.py::UserFactory`

**Nota crítica:** `AUTH_USER_MODEL` debe fijarse **antes** de aplicar la primera migración. Si ya corriste `migrate` en la Task 1, borra la base de datos de pruebas antes de continuar.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_accounts.py`:

```python
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
```

`tests/factories.py`:

```python
import factory
from django.contrib.auth import get_user_model


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"miembro{n}@example.com")
    display_name = factory.Sequence(lambda n: f"Miembro {n}")

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "clave-larga-123")
        if create:
            obj.save()
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_accounts.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.accounts` / el modelo de usuario por defecto no usa email

- [ ] **Step 3: Implementar**

`apps/accounts/apps.py`:

```python
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
```

`apps/accounts/models.py`:

```python
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError(_("An email address is required."))
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_("email address"), unique=True)
    display_name = models.CharField(_("display name"), max_length=80, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff status"), default=False)
    date_joined = models.DateTimeField(_("date joined"), auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.display_name or self.email


class Profile(models.Model):
    SERENO = "sereno"
    NOCTURNO = "nocturno"
    ACCESIBLE = "accesible"
    THEME_CHOICES = [
        (SERENO, _("Serene")),
        (NOCTURNO, _("Nocturne")),
        (ACCESIBLE, _("Accessible")),
    ]
    LANGUAGE_CHOICES = [("en", _("English")), ("fr", _("Français"))]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(_("avatar"), upload_to="avatars/", blank=True, null=True)
    theme = models.CharField(_("theme"), max_length=16, choices=THEME_CHOICES, default=SERENO)
    language = models.CharField(_("language"), max_length=5, choices=LANGUAGE_CHOICES, default="en")

    class Meta:
        verbose_name = _("profile")
        verbose_name_plural = _("profiles")

    def __str__(self):
        return f"{self.user} · {self.theme}/{self.language}"


@receiver(post_save, sender=User)
def crear_perfil(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
```

`apps/accounts/admin.py`:

```python
from django.contrib import admin

from .models import Profile, User

admin.site.register(User)
admin.site.register(Profile)
```

En `config/settings.py`, añade a `INSTALLED_APPS` la entrada `"apps.accounts"` y al final del archivo:

```python
AUTH_USER_MODEL = "accounts.User"
```

- [ ] **Step 4: Migrar, ejecutar y verificar que pasa**

Run:
```bash
python manage.py makemigrations accounts
pytest tests/test_accounts.py -v
```
Expected: PASS (5 pruebas)

- [ ] **Step 5: Commit**

```bash
git add apps/accounts config/settings.py tests/test_accounts.py tests/factories.py
git commit -m "Añade el usuario con email y el perfil con tema e idioma"
```

---

### Task 3: Hogar y membresías con permisos

**Files:**
- Create: `apps/households/__init__.py`, `apps/households/apps.py`, `apps/households/models.py`, `apps/households/admin.py`
- Modify: `config/settings.py` (`INSTALLED_APPS`), `tests/factories.py`
- Test: `tests/test_households.py`

**Interfaces:**
- Consumes: `accounts.User` (Task 2), `UserFactory`
- Produce:
  - `households.Household` — `name`, `currency` (default `"CAD"`), `timezone`, `budget_start_month`, `family_size`, `allowance_rollover` (default `True`), `created_at`
  - `households.Membership` — `user`, `household`, `role` (`admin`|`member`), los cuatro permisos booleanos, `joined_at`, `is_active`
  - `Membership.MAX_PER_HOUSEHOLD = 6`
  - `Household.active_memberships()` → QuerySet
  - `tests/factories.py::HouseholdFactory`, `MembershipFactory`

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_households.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.households.models import Household, Membership
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


@pytest.mark.django_db
def test_hogar_tiene_valores_por_defecto_canadienses():
    hogar = Household.objects.create(name="Family Thompson", family_size=4)
    assert hogar.currency == "CAD"
    assert hogar.allowance_rollover is True


@pytest.mark.django_db
def test_family_size_es_independiente_del_numero_de_cuentas():
    """Un hogar de cinco personas puede tener dos cuentas (spec §3.1)."""
    hogar = HouseholdFactory(family_size=5)
    MembershipFactory(household=hogar, role=Membership.ADMIN)
    MembershipFactory(household=hogar, role=Membership.MEMBER)
    assert hogar.family_size == 5
    assert hogar.active_memberships().count() == 2


@pytest.mark.django_db
def test_el_administrador_tiene_los_cuatro_permisos():
    membresia = MembershipFactory(role=Membership.ADMIN)
    assert membresia.can_view_budget
    assert membresia.can_edit_budget
    assert membresia.can_add_transactions
    assert membresia.can_view_reports


@pytest.mark.django_db
def test_un_miembro_puede_tener_permisos_recortados():
    membresia = MembershipFactory(role=Membership.MEMBER, can_view_budget=False, can_edit_budget=False)
    assert not membresia.can_view_budget
    assert membresia.can_add_transactions  # sigue pudiendo registrar sus gastos


@pytest.mark.django_db
def test_un_usuario_no_puede_estar_dos_veces_en_el_mismo_hogar():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user)
    with pytest.raises(Exception):
        Membership.objects.create(household=hogar, user=user, role=Membership.MEMBER)


@pytest.mark.django_db
def test_el_hogar_no_admite_una_septima_membresia():
    hogar = HouseholdFactory()
    MembershipFactory(household=hogar, role=Membership.ADMIN)
    for _ in range(5):
        MembershipFactory(household=hogar, role=Membership.MEMBER)
    assert hogar.active_memberships().count() == 6

    septima = Membership(household=hogar, user=UserFactory(), role=Membership.MEMBER)
    with pytest.raises(ValidationError):
        septima.full_clean()


@pytest.mark.django_db
def test_una_membresia_inactiva_libera_un_puesto():
    hogar = HouseholdFactory()
    MembershipFactory(household=hogar, role=Membership.ADMIN)
    ocupantes = [MembershipFactory(household=hogar, role=Membership.MEMBER) for _ in range(5)]
    ocupantes[0].is_active = False
    ocupantes[0].save()

    nueva = Membership(household=hogar, user=UserFactory(), role=Membership.MEMBER)
    nueva.full_clean()  # no debe lanzar
```

Añade a `tests/factories.py`:

```python
from apps.households.models import Household, Membership


class HouseholdFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Household

    name = factory.Sequence(lambda n: f"Hogar {n}")
    family_size = 4


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    household = factory.SubFactory(HouseholdFactory)
    role = Membership.MEMBER
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_households.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.households`

- [ ] **Step 3: Implementar**

`apps/households/apps.py`:

```python
from django.apps import AppConfig


class HouseholdsConfig(AppConfig):
    name = "apps.households"
    label = "households"
```

`apps/households/models.py`:

```python
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class Household(models.Model):
    name = models.CharField(_("household name"), max_length=120)
    currency = models.CharField(_("currency"), max_length=3, default="CAD")
    timezone = models.CharField(_("time zone"), max_length=64, default="America/Toronto")
    budget_start_month = models.PositiveSmallIntegerField(_("budget start month"), default=1)
    family_size = models.PositiveSmallIntegerField(
        _("family size"),
        default=1,
        help_text=_("How many people live in the home. Not the same as how many use the app."),
    )
    allowance_rollover = models.BooleanField(
        _("allowance rolls over"),
        default=True,
        help_text=_("Unspent personal allowance carries into the next month."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("household")
        verbose_name_plural = _("households")

    def __str__(self):
        return self.name

    def active_memberships(self):
        return self.memberships.filter(is_active=True)


class Membership(models.Model):
    MAX_PER_HOUSEHOLD = 6

    ADMIN = "admin"
    MEMBER = "member"
    ROLE_CHOICES = [(ADMIN, _("Administrator")), (MEMBER, _("Member"))]

    PERMISSION_FIELDS = (
        "can_view_budget",
        "can_edit_budget",
        "can_add_transactions",
        "can_view_reports",
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(_("role"), max_length=10, choices=ROLE_CHOICES, default=MEMBER)

    can_view_budget = models.BooleanField(_("can view the budget"), default=True)
    can_edit_budget = models.BooleanField(_("can edit the budget"), default=False)
    can_add_transactions = models.BooleanField(_("can add transactions"), default=True)
    can_view_reports = models.BooleanField(_("can view reports"), default=True)

    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        constraints = [
            models.UniqueConstraint(fields=["user", "household"], name="una_membresia_por_usuario_y_hogar")
        ]

    def __str__(self):
        return f"{self.user} @ {self.household} ({self.role})"

    def save(self, *args, **kwargs):
        if self.role == self.ADMIN:
            for campo in self.PERMISSION_FIELDS:
                setattr(self, campo, True)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.is_active and self.household_id:
            ocupadas = Membership.objects.filter(household_id=self.household_id, is_active=True)
            if self.pk:
                ocupadas = ocupadas.exclude(pk=self.pk)
            if ocupadas.count() >= self.MAX_PER_HOUSEHOLD:
                raise ValidationError(
                    _("A household can have at most %(max)d members.")
                    % {"max": self.MAX_PER_HOUSEHOLD}
                )
```

`apps/households/admin.py`:

```python
from django.contrib import admin

from .models import Household, Membership

admin.site.register(Household)
admin.site.register(Membership)
```

Añade `"apps.households"` a `INSTALLED_APPS`.

- [ ] **Step 4: Migrar, ejecutar y verificar que pasa**

Run:
```bash
python manage.py makemigrations households
pytest tests/test_households.py -v
```
Expected: PASS (7 pruebas)

- [ ] **Step 5: Commit**

```bash
git add apps/households config/settings.py tests/test_households.py tests/factories.py
git commit -m "Añade el hogar y las membresías con permisos y límite de seis"
```

---

### Task 4: La capa de aislamiento entre hogares

Esta es la tarea con más consecuencias de seguridad del plan. Todo modelo con ámbito de hogar hereda de `HouseholdScoped`, y la única forma soportada de consultarlo desde una vista es `Modelo.objects.for_user(user)`.

**Files:**
- Create: `apps/households/scoping.py`, `apps/households/permissions.py`
- Test: `tests/test_scoping.py`

**Interfaces:**
- Consumes: `Household`, `Membership` (Task 3)
- Produce:
  - `apps.households.scoping.HouseholdScopedManager` con `.for_user(user)` y `.for_household(household)`
  - `apps.households.scoping.HouseholdScoped` — modelo abstracto con `household = FK(Household)` y `objects = HouseholdScopedManager()`
  - `apps.households.permissions.get_membership(user, household)` → `Membership | None`
  - `apps.households.permissions.require_permission(user, household, permiso)` → lanza `PermissionDenied` si no procede
  - `apps.households.permissions.PermissionDenied` (reexporta el de Django)

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_scoping.py`:

```python
import pytest
from django.core.exceptions import PermissionDenied
from django.db import models

from apps.households.models import Membership
from apps.households.permissions import get_membership, require_permission
from apps.households.scoping import HouseholdScoped
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


@pytest.mark.django_db
def test_for_user_solo_devuelve_datos_del_hogar_del_usuario():
    """La prueba que impide que los Thompson vean las finanzas de los García."""
    from tests.scoping_models import Nota  # modelo de prueba, ver Step 3

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    papa = UserFactory()
    MembershipFactory(household=thompson, user=papa, role=Membership.ADMIN)

    Nota.objects.create(household=thompson, texto="hipoteca de los Thompson")
    Nota.objects.create(household=garcia, texto="hipoteca de los García")

    visibles = Nota.objects.for_user(papa)
    assert [n.texto for n in visibles] == ["hipoteca de los Thompson"]


@pytest.mark.django_db
def test_for_user_no_devuelve_nada_a_quien_no_tiene_membresia():
    from tests.scoping_models import Nota

    hogar = HouseholdFactory()
    Nota.objects.create(household=hogar, texto="secreto")
    assert Nota.objects.for_user(UserFactory()).count() == 0


@pytest.mark.django_db
def test_una_membresia_inactiva_no_da_acceso():
    from tests.scoping_models import Nota

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, is_active=False)
    Nota.objects.create(household=hogar, texto="secreto")
    assert Nota.objects.for_user(user).count() == 0


@pytest.mark.django_db
def test_todo_modelo_con_hogar_hereda_de_household_scoped():
    """Un modelo con FK a Household que no herede de HouseholdScoped es un agujero.

    Esta prueba vigila al Plan 2 y al Plan 3: cada modelo nuevo con ámbito de
    hogar la rompe hasta que hereda de HouseholdScoped, que es justo lo que
    queremos que pase.
    """
    from django.apps import apps as django_apps

    from apps.households.models import Household

    # Relacionan usuarios con el hogar; no son datos del hogar.
    EXCEPCIONES = {"Membership", "Invitation"}

    infractores = []
    for modelo in django_apps.get_models():
        if modelo is Household or modelo.__name__ in EXCEPCIONES:
            continue
        tiene_fk_a_hogar = any(
            isinstance(campo, models.ForeignKey) and campo.related_model is Household
            for campo in modelo._meta.get_fields()
            if isinstance(campo, models.ForeignKey)
        )
        if tiene_fk_a_hogar and not issubclass(modelo, HouseholdScoped):
            infractores.append(modelo.__name__)

    assert infractores == [], f"Modelos con hogar sin HouseholdScoped: {infractores}"


@pytest.mark.django_db
def test_get_membership_devuelve_none_para_un_extrano():
    assert get_membership(UserFactory(), HouseholdFactory()) is None


@pytest.mark.django_db
def test_require_permission_deja_pasar_al_que_lo_tiene():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=True)
    require_permission(user, hogar, "can_edit_budget")  # no debe lanzar


@pytest.mark.django_db
def test_require_permission_bloquea_al_que_no_lo_tiene():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=False)
    with pytest.raises(PermissionDenied):
        require_permission(user, hogar, "can_edit_budget")


@pytest.mark.django_db
def test_require_permission_bloquea_a_quien_no_es_del_hogar():
    with pytest.raises(PermissionDenied):
        require_permission(UserFactory(), HouseholdFactory(), "can_view_budget")


@pytest.mark.django_db
def test_require_permission_rechaza_un_permiso_inexistente():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user)
    with pytest.raises(ValueError):
        require_permission(user, hogar, "can_do_anything")
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_scoping.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.households.scoping`

- [ ] **Step 3: Implementar**

`apps/households/scoping.py`:

```python
from django.db import models

from .models import Household


class HouseholdScopedQuerySet(models.QuerySet):
    def for_household(self, household):
        return self.filter(household=household)

    def for_user(self, user):
        """Todo lo visible para este usuario, en todos sus hogares activos.

        Es el único punto de entrada soportado desde una vista. Filtrar a mano
        en cada vista es como se filtran mal los datos de otras familias.
        """
        if not getattr(user, "is_authenticated", False):
            return self.none()
        hogares = Household.objects.filter(memberships__user=user, memberships__is_active=True)
        return self.filter(household__in=hogares)


class HouseholdScopedManager(models.Manager.from_queryset(HouseholdScopedQuerySet)):
    pass


class HouseholdScoped(models.Model):
    """Todo dato que pertenece a un hogar hereda de aquí."""

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="%(class)ss")

    objects = HouseholdScopedManager()

    class Meta:
        abstract = True
```

`apps/households/permissions.py`:

```python
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from .models import Membership

__all__ = ["PermissionDenied", "get_membership", "require_permission"]


def get_membership(user, household):
    """La membresía activa del usuario en el hogar, o None."""
    if not getattr(user, "is_authenticated", False):
        return None
    return Membership.objects.filter(user=user, household=household, is_active=True).first()


def require_permission(user, household, permission):
    """Lanza PermissionDenied si el usuario no tiene ese permiso en ese hogar."""
    if permission not in Membership.PERMISSION_FIELDS:
        raise ValueError(f"Permiso desconocido: {permission!r}")

    membresia = get_membership(user, household)
    if membresia is None or not getattr(membresia, permission):
        raise PermissionDenied(_("You do not have permission to do that in this household."))
    return membresia
```

Crea el modelo de prueba `tests/scoping_models.py`. Existe solo para probar el andamiaje de aislamiento sin depender de los modelos del Plan 2:

```python
from django.db import models

from apps.households.scoping import HouseholdScoped


class Nota(HouseholdScoped):
    texto = models.CharField(max_length=100)

    class Meta:
        app_label = "households"
```

Para que Django cree su tabla en las pruebas, añade `"tests"` a `INSTALLED_APPS` **solo bajo pytest**. Al final de `config/settings.py`:

```python
import sys

if "pytest" in sys.modules:
    INSTALLED_APPS += ["tests"]
```

y crea `tests/__init__.py` (si no existe) más `tests/models.py` que reexporte el modelo:

```python
from tests.scoping_models import Nota  # noqa: F401
```

- [ ] **Step 4: Migrar, ejecutar y verificar que pasa**

Run:
```bash
python manage.py makemigrations households
pytest tests/test_scoping.py -v
```
Expected: PASS (9 pruebas)

- [ ] **Step 5: Commit**

```bash
git add apps/households/scoping.py apps/households/permissions.py config/settings.py tests/
git commit -m "Añade la capa central de aislamiento y permisos entre hogares"
```

---

### Task 5: Invitaciones con doble validación del límite

**Files:**
- Modify: `apps/households/models.py` (añadir `Invitation`)
- Create: `apps/households/services.py`
- Test: `tests/test_invitations.py`

**Interfaces:**
- Consumes: `Household`, `Membership` (Task 3), `require_permission` (Task 4)
- Produce:
  - `households.Invitation` — `household`, `email`, `token`, `language`, `expires_at`, `accepted_at`, `invited_by`, `is_valid()`
  - `apps.households.services.crear_hogar(user, nombre, family_size)` → `Household` (el usuario queda admin)
  - `apps.households.services.invitar(invitador, household, email, language)` → `Invitation`
  - `apps.households.services.aceptar_invitacion(user, token)` → `Membership`
  - `apps.households.services.HouseholdLleno` (excepción)
  - `apps.households.services.InvitacionInvalida` (excepción)

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_invitations.py`:

```python
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.households.models import Invitation, Membership
from apps.households.services import (
    HouseholdLleno,
    InvitacionInvalida,
    aceptar_invitacion,
    crear_hogar,
    invitar,
)
from tests.factories import MembershipFactory, UserFactory


@pytest.mark.django_db
def test_crear_hogar_deja_al_creador_como_admin():
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    membresia = Membership.objects.get(user=user, household=hogar)
    assert membresia.role == Membership.ADMIN
    assert membresia.can_edit_budget


@pytest.mark.django_db
def test_invitar_crea_una_invitacion_valida_por_siete_dias():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    inv = invitar(admin, hogar, "marie@example.com", language="fr")

    assert inv.token
    assert inv.language == "fr"
    assert inv.is_valid()
    assert timedelta(days=6) < (inv.expires_at - timezone.now()) <= timedelta(days=7)


@pytest.mark.django_db
def test_un_miembro_sin_rol_admin_no_puede_invitar():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    otro = UserFactory()
    MembershipFactory(household=hogar, user=otro, role=Membership.MEMBER)

    with pytest.raises(PermissionDenied):
        invitar(otro, hogar, "nuevo@example.com", language="en")


@pytest.mark.django_db
def test_no_se_puede_invitar_cuando_el_hogar_esta_lleno():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    for _ in range(5):
        MembershipFactory(household=hogar, role=Membership.MEMBER)

    with pytest.raises(HouseholdLleno):
        invitar(admin, hogar, "septimo@example.com", language="en")


@pytest.mark.django_db
def test_seis_invitaciones_pendientes_no_desbordan_el_hogar():
    """La validación al aceptar es la que impide el desbordamiento por carrera (spec §6.3)."""
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)

    # El límite al crear cuenta las pendientes: solo caben 5 más.
    invitaciones = [invitar(admin, hogar, f"m{i}@example.com", language="en") for i in range(5)]
    with pytest.raises(HouseholdLleno):
        invitar(admin, hogar, "sexto@example.com", language="en")

    for inv in invitaciones:
        aceptar_invitacion(UserFactory(), inv.token)

    assert hogar.active_memberships().count() == 6


@pytest.mark.django_db
def test_aceptar_dos_veces_la_misma_invitacion_falla():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    inv = invitar(admin, hogar, "marie@example.com", language="en")

    aceptar_invitacion(UserFactory(), inv.token)
    with pytest.raises(InvitacionInvalida):
        aceptar_invitacion(UserFactory(), inv.token)


@pytest.mark.django_db
def test_una_invitacion_caducada_no_se_acepta():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    inv = invitar(admin, hogar, "marie@example.com", language="en")
    token = inv.token
    Invitation.objects.filter(pk=inv.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

    with pytest.raises(InvitacionInvalida):
        aceptar_invitacion(UserFactory(), token)


@pytest.mark.django_db
def test_un_token_inventado_no_se_acepta():
    with pytest.raises(InvitacionInvalida):
        aceptar_invitacion(UserFactory(), "token-que-no-existe")


@pytest.mark.django_db
def test_el_invitado_entra_con_permisos_de_miembro_no_de_admin():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    inv = invitar(admin, hogar, "hijo@example.com", language="en")

    membresia = aceptar_invitacion(UserFactory(), inv.token)
    assert membresia.role == Membership.MEMBER
    assert not membresia.can_edit_budget
    assert membresia.can_add_transactions
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_invitations.py -v`
Expected: FAIL — `ImportError: cannot import name 'Invitation'`

- [ ] **Step 3: Implementar**

Añade al final de `apps/households/models.py`:

```python
import secrets
from datetime import timedelta

from django.utils import timezone


def _token_invitacion():
    return secrets.token_urlsafe(32)


class Invitation(models.Model):
    VIGENCIA = timedelta(days=7)

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField(_("email address"))
    token = models.CharField(max_length=64, unique=True, default=_token_invitacion, editable=False)
    language = models.CharField(_("language"), max_length=5, default="en")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_invitations")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("invitation")
        verbose_name_plural = _("invitations")

    def __str__(self):
        return f"{self.email} → {self.household}"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + self.VIGENCIA
        super().save(*args, **kwargs)

    def is_valid(self):
        return self.accepted_at is None and self.expires_at > timezone.now()
```

`apps/households/services.py`:

```python
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Household, Invitation, Membership
from .permissions import PermissionDenied, get_membership


class HouseholdLleno(Exception):
    """El hogar ya llegó a su máximo de miembros contando invitaciones pendientes."""


class InvitacionInvalida(Exception):
    """El token no existe, ya se usó o caducó."""


def _puestos_libres(household):
    ocupados = household.active_memberships().count()
    pendientes = Invitation.objects.filter(
        household=household, accepted_at__isnull=True, expires_at__gt=timezone.now()
    ).count()
    return Membership.MAX_PER_HOUSEHOLD - ocupados - pendientes


@transaction.atomic
def crear_hogar(user, nombre, family_size):
    household = Household.objects.create(name=nombre, family_size=family_size)
    Membership.objects.create(user=user, household=household, role=Membership.ADMIN)
    return household


@transaction.atomic
def invitar(invitador, household, email, language):
    membresia = get_membership(invitador, household)
    if membresia is None or membresia.role != Membership.ADMIN:
        raise PermissionDenied(_("Only the administrator can invite members."))

    if _puestos_libres(household) <= 0:
        raise HouseholdLleno(_("This household has no free seats left."))

    return Invitation.objects.create(
        household=household, email=email, language=language, invited_by=invitador
    )


@transaction.atomic
def aceptar_invitacion(user, token):
    try:
        invitacion = Invitation.objects.select_for_update().get(token=token)
    except Invitation.DoesNotExist:
        raise InvitacionInvalida(_("This invitation link is not valid."))

    if not invitacion.is_valid():
        raise InvitacionInvalida(_("This invitation has expired or was already used."))

    # Segunda validación del límite: es la que impide que seis invitaciones
    # pendientes se acepten a la vez y desborden el hogar (spec §6.3).
    if invitacion.household.active_memberships().count() >= Membership.MAX_PER_HOUSEHOLD:
        raise HouseholdLleno(_("This household is already full."))

    membresia = Membership.objects.create(
        user=user, household=invitacion.household, role=Membership.MEMBER
    )
    invitacion.accepted_at = timezone.now()
    invitacion.save(update_fields=["accepted_at"])
    return membresia
```

- [ ] **Step 4: Migrar, ejecutar y verificar que pasa**

Run:
```bash
python manage.py makemigrations households
pytest tests/test_invitations.py -v
```
Expected: PASS (9 pruebas)

- [ ] **Step 5: Commit**

```bash
git add apps/households tests/test_invitations.py
git commit -m "Añade invitaciones con doble validación del límite de miembros"
```

---

### Task 6: Formato de dinero y fechas por locale

Django localiza números pero **no formatea moneda**: la posición del símbolo `$` no la resuelve. En inglés canadiense es `$2,847.50` y en francés canadiense `2 847,50 $`. Se resuelve con Babel.

**Files:**
- Create: `apps/core/apps.py`, `apps/core/templatetags/__init__.py`, `apps/core/templatetags/money.py`
- Modify: `config/settings.py` (`INSTALLED_APPS`)
- Test: `tests/test_i18n.py`

**Interfaces:**
- Consumes: `settings.DEFAULT_CURRENCY` (Task 1)
- Produce:
  - `apps.core.templatetags.money.format_money(amount, locale=None, currency=None)` → `str`
  - filtro de plantilla `{{ importe|money }}`

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_i18n.py`:

```python
from decimal import Decimal

import pytest
from django.template import Context, Template
from django.utils import translation

from apps.core.templatetags.money import format_money


def _normalizar(texto):
    """CLDR usa espacios finos o duros según la versión; los unificamos."""
    return texto.replace(" ", " ").replace(" ", " ")


def test_dinero_en_ingles_canadiense():
    assert _normalizar(format_money(Decimal("2847.50"), locale="en_CA")) == "$2,847.50"


def test_dinero_en_frances_canadiense():
    """El signo va después, decimal con coma, miles con espacio (spec §8)."""
    assert _normalizar(format_money(Decimal("2847.50"), locale="fr_CA")) == "2 847,50 $"


def test_dinero_negativo_en_los_dos_idiomas():
    assert "2,847.50" in _normalizar(format_money(Decimal("-2847.50"), locale="en_CA"))
    assert "2 847,50" in _normalizar(format_money(Decimal("-2847.50"), locale="fr_CA"))


def test_dinero_usa_dos_decimales_siempre():
    assert _normalizar(format_money(Decimal("100"), locale="en_CA")) == "$100.00"


def test_el_filtro_sigue_el_idioma_activo():
    plantilla = Template("{% load money %}{{ importe|money }}")
    with translation.override("fr"):
        salida = _normalizar(plantilla.render(Context({"importe": Decimal("2847.50")})))
    assert salida == "2 847,50 $"

    with translation.override("en"):
        salida = _normalizar(plantilla.render(Context({"importe": Decimal("2847.50")})))
    assert salida == "$2,847.50"


def test_el_filtro_tolera_valores_vacios():
    plantilla = Template("{% load money %}{{ importe|money }}")
    assert plantilla.render(Context({"importe": None})) == ""
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_i18n.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.core.templatetags.money`

- [ ] **Step 3: Implementar**

`apps/core/apps.py`:

```python
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
```

`apps/core/templatetags/money.py`:

```python
from decimal import Decimal

from babel.numbers import format_currency
from django import template
from django.conf import settings
from django.utils.translation import get_language

register = template.Library()

# Idioma de Django → locale de Babel. Canadá en ambos casos.
LOCALES = {"en": "en_CA", "fr": "fr_CA"}


def _locale_activo():
    return LOCALES.get((get_language() or "en")[:2], "en_CA")


def format_money(amount, locale=None, currency=None):
    """Formatea un importe según la convención del locale.

    en_CA → $2,847.50    ·    fr_CA → 2 847,50 $
    """
    if amount is None or amount == "":
        return ""
    return format_currency(
        Decimal(amount),
        currency or settings.DEFAULT_CURRENCY,
        locale=locale or _locale_activo(),
    )


@register.filter(name="money")
def money(amount):
    return format_money(amount)
```

Añade `"apps.core"` a `INSTALLED_APPS`.

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `pytest tests/test_i18n.py -v`
Expected: PASS (6 pruebas)

- [ ] **Step 5: Commit**

```bash
git add apps/core config/settings.py tests/test_i18n.py
git commit -m "Añade el formato de moneda por locale con Babel"
```

---

### Task 7: Registro, sesión y creación del hogar

**Files:**
- Create: `apps/accounts/forms.py`, `apps/accounts/views.py`, `apps/accounts/urls.py`
- Create: `templates/base.html`, `templates/accounts/registro.html`, `templates/accounts/login.html`
- Modify: `config/urls.py`, `config/settings.py` (`LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL`)
- Test: `tests/test_auth_flow.py`

**Interfaces:**
- Consumes: `User`, `Profile` (Task 2), `crear_hogar` (Task 5)
- Produce:
  - Rutas nombradas: `accounts:registro`, `accounts:login`, `accounts:logout`, `accounts:inicio`
  - `apps.accounts.forms.RegistroForm` — campos `email`, `display_name`, `password1`, `password2`, `household_name`, `family_size`
  - Al registrarse: se crea `User` + `Profile` + `Household` con el usuario como admin, y queda con la sesión iniciada

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_auth_flow.py`:

```python
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
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_auth_flow.py -v`
Expected: FAIL — `NoReverseMatch: 'accounts' is not a registered namespace`

- [ ] **Step 3: Implementar**

`apps/accounts/forms.py`:

```python
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class RegistroForm(forms.Form):
    email = forms.EmailField(label=_("Email address"))
    display_name = forms.CharField(label=_("Your name"), max_length=80)
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Confirm password"), widget=forms.PasswordInput)
    household_name = forms.CharField(label=_("Household name"), max_length=120)
    family_size = forms.IntegerField(label=_("How many live in your home?"), min_value=1, max_value=20)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password)
        return password

    def clean(self):
        datos = super().clean()
        if datos.get("password1") and datos.get("password1") != datos.get("password2"):
            self.add_error("password2", _("The two passwords do not match."))
        return datos
```

`apps/accounts/views.py`:

```python
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from apps.households.services import crear_hogar

from .forms import RegistroForm

User = get_user_model()


def registro(request):
    if request.method == "POST":
        form = RegistroForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = User.objects.create_user(
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password1"],
                    display_name=form.cleaned_data["display_name"],
                )
                crear_hogar(user, form.cleaned_data["household_name"], form.cleaned_data["family_size"])
            login(request, user)
            return redirect("accounts:inicio")
    else:
        form = RegistroForm()
    return render(request, "accounts/registro.html", {"form": form})


class Login(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class Logout(LogoutView):
    next_page = reverse_lazy("accounts:login")


@login_required
def inicio(request):
    return render(request, "accounts/inicio.html")
```

`apps/accounts/urls.py`:

```python
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("registro/", views.registro, name="registro"),
    path("entrar/", views.Login.as_view(), name="login"),
    path("salir/", views.Logout.as_view(), name="logout"),
    path("", views.inicio, name="inicio"),
]
```

`config/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
]
```

En `config/settings.py`:

```python
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:inicio"
LOGOUT_REDIRECT_URL = "accounts:login"
```

`templates/base.html` (versión mínima; la Task 8 le añade el tema):

```html
{% load i18n static %}<!doctype html>
<html lang="{{ LANGUAGE_CODE }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Wealthome{% endblock %}</title>
  <link rel="stylesheet" href="{% static 'css/tokens.css' %}">
  <link rel="stylesheet" href="{% static 'css/base.css' %}">
  <link rel="stylesheet" href="{% static 'css/components.css' %}">
  <link rel="stylesheet" href="{% static 'css/modules.css' %}">
</head>
<body>
  <main class="shell">{% block content %}{% endblock %}</main>
</body>
</html>
```

`templates/accounts/registro.html`:

```html
{% extends "base.html" %}{% load i18n %}
{% block title %}{% translate "Create your household" %}{% endblock %}
{% block content %}
  <h1>{% translate "Create your household" %}</h1>
  <form method="post" class="card">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit" class="btn btn--primary">{% translate "Start my 14-day trial" %}</button>
  </form>
  <p><a href="{% url 'accounts:login' %}">{% translate "I already have an account" %}</a></p>
{% endblock %}
```

`templates/accounts/login.html`:

```html
{% extends "base.html" %}{% load i18n %}
{% block title %}{% translate "Sign in" %}{% endblock %}
{% block content %}
  <h1>{% translate "Sign in" %}</h1>
  <form method="post" class="card">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit" class="btn btn--primary">{% translate "Sign in" %}</button>
  </form>
  <p><a href="{% url 'accounts:registro' %}">{% translate "Create a household" %}</a></p>
{% endblock %}
```

`templates/accounts/inicio.html`:

```html
{% extends "base.html" %}{% load i18n %}
{% block content %}<h1>{% translate "Welcome" %}</h1>{% endblock %}
```

Crea `static/css/tokens.css`, `base.css`, `components.css` y `modules.css` vacíos por ahora; la Task 8 los llena.

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `pytest tests/test_auth_flow.py -v`
Expected: PASS (5 pruebas)

- [ ] **Step 5: Commit**

```bash
git add apps/accounts config templates static tests/test_auth_flow.py
git commit -m "Añade registro, sesión y creación del hogar al registrarse"
```

---

### Task 8: Los tres temas y el idioma del perfil

**Files:**
- Create: `apps/accounts/middleware.py`
- Modify: `config/settings.py` (middleware), `templates/base.html`
- Modify: `static/css/tokens.css`, `static/css/base.css`, `static/css/components.css`
- Test: `tests/test_themes.py`

**Interfaces:**
- Consumes: `Profile` (Task 2), `base.html` (Task 7)
- Produce:
  - `apps.accounts.middleware.PerfilLocaleMiddleware` — activa el idioma del perfil en cada petición autenticada
  - `base.html` emite `<html lang="…" data-theme="…">` a partir del perfil
  - `tokens.css` define los tres temas mediante variables CSS

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_themes.py`:

```python
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
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_themes.py -v`
Expected: FAIL — no aparece `data-theme` en el HTML

- [ ] **Step 3: Implementar**

`apps/accounts/middleware.py`:

```python
from django.utils import translation


class PerfilLocaleMiddleware:
    """Activa el idioma guardado en el perfil del usuario.

    Va DESPUÉS de LocaleMiddleware y de AuthenticationMiddleware: el perfil
    manda sobre la cabecera Accept-Language del navegador (spec §8).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        perfil = getattr(getattr(request, "user", None), "profile", None)
        if perfil is not None:
            translation.activate(perfil.language)
            request.LANGUAGE_CODE = perfil.language
        respuesta = self.get_response(request)
        translation.deactivate()
        return respuesta
```

En `config/settings.py`, añade al final de `MIDDLEWARE`:

```python
MIDDLEWARE += ["apps.accounts.middleware.PerfilLocaleMiddleware"]
```

En `templates/base.html`, sustituye la etiqueta `<html>` por:

```html
<html lang="{{ LANGUAGE_CODE }}" data-theme="{{ user.profile.theme|default:'sereno' }}">
```

`static/css/tokens.css`:

```css
/* Wealthome · sistema de temas.
   Un solo juego de variables por tema; los componentes se escriben una vez. */

/* ---------- Sereno (por defecto) ---------- */
:root {
  --bg:            #e9edf1;
  --surface:       #e9edf1;
  --text:          #33404f;
  --text-muted:    #8a94a3;
  --accent:        #3f8f6f;
  --accent-strong: #2f7d5d;
  --danger:        #b0603f;

  --font-family:    'Segoe UI', system-ui, -apple-system, sans-serif;
  --font-size-base: 15px;
  --font-weight-strong: 600;

  --radius:      17px;
  --radius-sm:   13px;
  --border-width: 0px;
  --border-color: transparent;

  --shadow-light: #ffffff;
  --shadow-dark:  #c3c9d1;
  --shadow-raised: 8px 8px 16px var(--shadow-dark), -8px -8px 16px var(--shadow-light);
  --shadow-inset:  inset 5px 5px 10px var(--shadow-dark), inset -5px -5px 10px var(--shadow-light);

  --touch-target: 44px;
}

/* ---------- Nocturno ---------- */
[data-theme="nocturno"] {
  --bg:            #232830;
  --surface:       #232830;
  --text:          #eef2f6;
  --text-muted:    #8993a1;
  --accent:        #5cc196;
  --accent-strong: #3f9d78;
  --danger:        #d98b6a;

  --shadow-light: #2c333c;
  --shadow-dark:  #1a1e24;
}

/* ---------- Accesible ----------
   El neomorfismo comunica profundidad con sombras suaves, y esa es la primera
   señal que se pierde con la vista cansada. Aquí se sustituye por bordes. */
[data-theme="accesible"] {
  --bg:            #f2f4f6;
  --surface:       #ffffff;
  --text:          #14181d;
  --text-muted:    #3a424c;
  --accent:        #0a5c3a;
  --accent-strong: #084a2e;
  --danger:        #8c2f14;

  --font-size-base: 20px;
  --font-weight-strong: 800;

  --radius:      14px;
  --radius-sm:   11px;
  --border-width: 3px;
  --border-color: #14181d;

  --shadow-raised: 0 4px 0 #14181d;
  --shadow-inset:  none;

  --touch-target: 56px;
}
```

`static/css/base.css`:

```css
*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-family);
  font-size: var(--font-size-base);
  line-height: 1.5;
}

a { color: var(--accent); }

.shell { max-width: 960px; margin: 0 auto; padding: 24px 18px 96px; }
```

`static/css/components.css`:

```css
.card {
  background: var(--surface);
  border-radius: var(--radius);
  border: var(--border-width) solid var(--border-color);
  box-shadow: var(--shadow-raised);
  padding: 20px;
}

.btn {
  min-height: var(--touch-target);
  padding: 0 18px;
  border: var(--border-width) solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--accent);
  font-family: inherit;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-strong);
  box-shadow: var(--shadow-raised);
  cursor: pointer;
}

.btn--primary { color: var(--accent-strong); }
```

Deja `static/css/modules.css` vacío con un comentario; se llena en el Plan 3.

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `pytest tests/test_themes.py -v`
Expected: PASS (6 pruebas)

- [ ] **Step 5: Commit**

```bash
git add apps/accounts/middleware.py config/settings.py templates static tests/test_themes.py
git commit -m "Añade los tres temas y el idioma del perfil en cada petición"
```

---

### Task 9: Pantalla de ajustes — miembros, permisos, tema e idioma

**Files:**
- Create: `apps/households/forms.py`, `apps/households/views.py`, `apps/households/urls.py`
- Create: `templates/households/ajustes.html`, `templates/households/invitar.html`, `templates/households/aceptar.html`
- Modify: `config/urls.py`, `apps/accounts/forms.py` (añadir `PreferenciasForm`), `apps/accounts/views.py`, `apps/accounts/urls.py`, `templates/accounts/inicio.html`
- Test: `tests/test_settings_views.py`

**Interfaces:**
- Consumes: todo lo anterior
- Produce:
  - Rutas: `households:ajustes`, `households:invitar`, `households:aceptar` (con `<token>`), `households:permisos` (con `<pk>` de membresía), `accounts:preferencias`
  - `apps.accounts.forms.PreferenciasForm` — `theme`, `language`
  - `apps.households.forms.InvitarForm` — `email`, `language`
  - `apps.households.forms.PermisosForm` — un `ModelForm` sobre `Membership.PERMISSION_FIELDS`

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_settings_views.py`:

```python
import pytest
from django.urls import reverse

from apps.households.models import Invitation, Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory


@pytest.fixture
def admin_con_hogar(db):
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    return user, hogar


@pytest.mark.django_db
def test_el_admin_ve_la_lista_de_miembros(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    otro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    client.force_login(admin)

    html = client.get(reverse("households:ajustes")).content.decode()
    assert str(otro.user) in html


@pytest.mark.django_db
def test_el_admin_invita_y_se_crea_la_invitacion(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    client.force_login(admin)

    respuesta = client.post(reverse("households:invitar"), {"email": "marie@example.com", "language": "fr"})
    assert respuesta.status_code == 302
    inv = Invitation.objects.get(household=hogar)
    assert inv.email == "marie@example.com"
    assert inv.language == "fr"


@pytest.mark.django_db
def test_un_miembro_normal_no_puede_invitar(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    miembro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    client.force_login(miembro.user)

    respuesta = client.post(reverse("households:invitar"), {"email": "x@example.com", "language": "en"})
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_el_admin_cambia_los_permisos_de_un_miembro(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    miembro = MembershipFactory(household=hogar, role=Membership.MEMBER, can_view_budget=True)
    client.force_login(admin)

    client.post(
        reverse("households:permisos", args=[miembro.pk]),
        {"can_add_transactions": "on", "can_view_reports": "on"},
    )
    miembro.refresh_from_db()
    assert not miembro.can_view_budget
    assert miembro.can_add_transactions


@pytest.mark.django_db
def test_un_admin_no_puede_tocar_los_permisos_de_otro_hogar(client, admin_con_hogar):
    admin, _ = admin_con_hogar
    ajena = MembershipFactory(role=Membership.MEMBER)  # otro hogar
    client.force_login(admin)

    respuesta = client.post(reverse("households:permisos", args=[ajena.pk]), {"can_view_reports": "on"})
    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_aceptar_una_invitacion_desde_el_enlace(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    from apps.households.services import invitar

    inv = invitar(admin, hogar, "marie@example.com", language="en")
    marie = UserFactory()
    client.force_login(marie)

    respuesta = client.post(reverse("households:aceptar", args=[inv.token]))
    assert respuesta.status_code == 302
    assert Membership.objects.filter(user=marie, household=hogar).exists()


@pytest.mark.django_db
def test_el_usuario_cambia_su_tema_y_su_idioma(client):
    user = UserFactory()
    client.force_login(user)

    client.post(reverse("accounts:preferencias"), {"theme": "accesible", "language": "fr"})
    user.profile.refresh_from_db()
    assert user.profile.theme == "accesible"
    assert user.profile.language == "fr"


@pytest.mark.django_db
def test_cambiar_el_tema_no_afecta_a_los_demas_miembros(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    otro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    client.force_login(admin)

    client.post(reverse("accounts:preferencias"), {"theme": "accesible", "language": "en"})
    otro.user.profile.refresh_from_db()
    assert otro.user.profile.theme == "sereno"
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_settings_views.py -v`
Expected: FAIL — `NoReverseMatch: 'households' is not a registered namespace`

- [ ] **Step 3: Implementar**

Añade a `apps/accounts/forms.py`:

```python
from apps.accounts.models import Profile


class PreferenciasForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["theme", "language"]
```

Añade a `apps/accounts/views.py`:

```python
from .forms import PreferenciasForm


@login_required
def preferencias(request):
    form = PreferenciasForm(request.POST or None, instance=request.user.profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("accounts:preferencias")
    return render(request, "accounts/preferencias.html", {"form": form})
```

y a `apps/accounts/urls.py` la ruta `path("preferencias/", views.preferencias, name="preferencias")`.

`apps/households/forms.py`:

```python
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Membership


class InvitarForm(forms.Form):
    email = forms.EmailField(label=_("Email address of the person you are inviting"))
    language = forms.ChoiceField(
        label=_("Send the invitation in"),
        choices=[("en", _("English")), ("fr", _("Français"))],
    )


class PermisosForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = list(Membership.PERMISSION_FIELDS)
```

`apps/households/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .forms import InvitarForm, PermisosForm
from .models import Membership
from .permissions import get_membership
from .services import HouseholdLleno, InvitacionInvalida, aceptar_invitacion, invitar


def _hogar_activo(request):
    """El primer hogar activo del usuario. En Fase 1 un usuario tiene uno."""
    membresia = Membership.objects.filter(user=request.user, is_active=True).select_related("household").first()
    if membresia is None:
        raise PermissionDenied
    return membresia.household


@login_required
def ajustes(request):
    hogar = _hogar_activo(request)
    return render(
        request,
        "households/ajustes.html",
        {
            "hogar": hogar,
            "miembros": hogar.active_memberships().select_related("user"),
            "es_admin": get_membership(request.user, hogar).role == Membership.ADMIN,
        },
    )


@login_required
def invitar_view(request):
    hogar = _hogar_activo(request)
    form = InvitarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            invitar(request.user, hogar, form.cleaned_data["email"], form.cleaned_data["language"])
        except PermissionDenied:
            return HttpResponseForbidden()
        except HouseholdLleno as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("households:ajustes")
    return render(request, "households/invitar.html", {"form": form})


@login_required
def permisos(request, pk):
    hogar = _hogar_activo(request)
    if get_membership(request.user, hogar).role != Membership.ADMIN:
        return HttpResponseForbidden()

    # Acotado al hogar del admin: una membresía ajena da 404, no 403,
    # para no revelar que existe.
    membresia = get_object_or_404(Membership, pk=pk, household=hogar)
    form = PermisosForm(request.POST or None, instance=membresia)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("households:ajustes")
    return render(request, "households/permisos.html", {"form": form, "membresia": membresia})


@login_required
def aceptar(request, token):
    if request.method == "POST":
        try:
            aceptar_invitacion(request.user, token)
        except (InvitacionInvalida, HouseholdLleno) as exc:
            return render(request, "households/aceptar.html", {"error": str(exc), "token": token})
        return redirect("households:ajustes")
    return render(request, "households/aceptar.html", {"token": token})
```

`apps/households/urls.py`:

```python
from django.urls import path

from . import views

app_name = "households"

urlpatterns = [
    path("ajustes/", views.ajustes, name="ajustes"),
    path("ajustes/invitar/", views.invitar_view, name="invitar"),
    path("ajustes/permisos/<int:pk>/", views.permisos, name="permisos"),
    path("invitacion/<str:token>/", views.aceptar, name="aceptar"),
]
```

En `config/urls.py`, añade antes de la línea de `accounts` (que captura la raíz):

```python
    path("hogar/", include("apps.households.urls")),
```

Plantillas mínimas — `templates/households/ajustes.html`:

```html
{% extends "base.html" %}{% load i18n %}
{% block title %}{% translate "Settings" %}{% endblock %}
{% block content %}
  <h1>{{ hogar.name }}</h1>

  <section class="card">
    <h2>{% translate "Members" %}</h2>
    <ul>
      {% for m in miembros %}
        <li>
          {{ m.user }} — {{ m.get_role_display }}
          {% if es_admin and m.role != "admin" %}
            <a href="{% url 'households:permisos' m.pk %}">{% translate "Permissions" %}</a>
          {% endif %}
        </li>
      {% endfor %}
    </ul>
    {% if es_admin %}
      <a class="btn" href="{% url 'households:invitar' %}">{% translate "Invite a member" %}</a>
    {% endif %}
  </section>

  <p><a href="{% url 'accounts:preferencias' %}">{% translate "My preferences" %}</a></p>
{% endblock %}
```

`templates/households/invitar.html`, `templates/households/permisos.html` y
`templates/accounts/preferencias.html` siguen el mismo patrón: `{% extends "base.html" %}`,
un `<form method="post">` con `{% csrf_token %}`, `{{ form.as_p }}` y un botón
`class="btn btn--primary"`.

`templates/households/aceptar.html`:

```html
{% extends "base.html" %}{% load i18n %}
{% block content %}
  <h1>{% translate "Join this household" %}</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post">{% csrf_token %}
    <button type="submit" class="btn btn--primary">{% translate "Accept invitation" %}</button>
  </form>
{% endblock %}
```

Añade en `templates/accounts/inicio.html` un enlace a `{% url 'households:ajustes' %}`.

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `pytest tests/test_settings_views.py -v`
Expected: PASS (8 pruebas)

- [ ] **Step 5: Commit**

```bash
git add apps/households apps/accounts config/urls.py templates tests/test_settings_views.py
git commit -m "Añade la pantalla de ajustes con miembros, permisos y preferencias"
```

---

### Task 10: Traducciones al francés y verificación final

**Files:**
- Create: `locale/fr/LC_MESSAGES/django.po` (generado), `locale/en/LC_MESSAGES/django.po` (generado)
- Create: `README.md`
- Test: `tests/test_traducciones.py`

**Interfaces:**
- Consumes: todo lo anterior
- Produce: catálogo francés completo; instrucciones de puesta en marcha

- [ ] **Step 1: Escribir la prueba que falla**

`tests/test_traducciones.py`:

```python
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

from tests.factories import UserFactory


def test_existe_el_catalogo_frances():
    po = Path(settings.BASE_DIR / "locale/fr/LC_MESSAGES/django.po")
    assert po.exists(), "Ejecuta: python manage.py makemessages -l fr"


def test_no_quedan_cadenas_francesas_sin_traducir():
    po = Path(settings.BASE_DIR / "locale/fr/LC_MESSAGES/django.po").read_text(encoding="utf-8")
    bloques = [b for b in po.split("\n\n") if b.startswith("msgid") or "\nmsgid" in b]
    vacias = [b for b in bloques if 'msgstr ""' in b and 'msgid ""' not in b.split("\n")[0]]
    # Se permite la cabecera (msgid "") pero ninguna otra cadena vacía.
    assert not vacias, f"Cadenas sin traducir en fr: {len(vacias)}"


@pytest.mark.django_db
def test_la_interfaz_aparece_en_frances(client):
    user = UserFactory()
    user.profile.language = "fr"
    user.profile.save()
    client.force_login(user)

    html = client.get(reverse("households:ajustes")).content.decode()
    assert "Membres" in html or "Paramètres" in html


def test_los_idiomas_declarados_son_solo_en_y_fr():
    assert [c for c, _ in settings.LANGUAGES] == ["en", "fr"]
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `pytest tests/test_traducciones.py -v`
Expected: FAIL — no existe `locale/fr/LC_MESSAGES/django.po`

- [ ] **Step 3: Generar y traducir el catálogo**

```bash
mkdir -p locale/en/LC_MESSAGES locale/fr/LC_MESSAGES
python manage.py makemessages -l fr -l en --ignore=.venv
```

Traduce cada `msgstr` vacío en `locale/fr/LC_MESSAGES/django.po`. Las cadenas de esta fase, con su traducción canadiense:

| `msgid` | `msgstr` (fr-CA) |
|---|---|
| `Email address` | `Adresse courriel` |
| `Your name` | `Votre nom` |
| `Password` | `Mot de passe` |
| `Confirm password` | `Confirmer le mot de passe` |
| `Household name` | `Nom du foyer` |
| `How many live in your home?` | `Combien de personnes vivent chez vous?` |
| `Create your household` | `Créer votre foyer` |
| `Start my 14-day trial` | `Commencer mon essai de 14 jours` |
| `I already have an account` | `J'ai déjà un compte` |
| `Sign in` | `Se connecter` |
| `Create a household` | `Créer un foyer` |
| `Welcome` | `Bienvenue` |
| `Settings` | `Paramètres` |
| `Members` | `Membres` |
| `Permissions` | `Permissions` |
| `Invite a member` | `Inviter un membre` |
| `My preferences` | `Mes préférences` |
| `Join this household` | `Rejoindre ce foyer` |
| `Accept invitation` | `Accepter l'invitation` |
| `Email address of the person you are inviting` | `Adresse courriel de la personne invitée` |
| `Send the invitation in` | `Envoyer l'invitation en` |
| `household` | `foyer` |
| `household name` | `nom du foyer` |
| `family size` | `taille de la famille` |
| `allowance rolls over` | `report de l'argent de poche` |
| `membership` | `adhésion` |
| `role` | `rôle` |
| `Administrator` | `Administrateur` |
| `Member` | `Membre` |
| `can view the budget` | `peut consulter le budget` |
| `can edit the budget` | `peut modifier le budget` |
| `can add transactions` | `peut saisir des transactions` |
| `can view reports` | `peut consulter les rapports` |
| `invitation` | `invitation` |
| `user` | `utilisateur` |
| `profile` | `profil` |
| `theme` | `thème` |
| `language` | `langue` |
| `avatar` | `avatar` |
| `display name` | `nom affiché` |
| `Serene` | `Sereine` |
| `Nocturne` | `Nocturne` |
| `Accessible` | `Accessible` |
| `English` | `Anglais` |
| `Français` | `Français` |
| `An email address is required.` | `Une adresse courriel est requise.` |
| `An account with this email already exists.` | `Un compte utilise déjà cette adresse courriel.` |
| `The two passwords do not match.` | `Les deux mots de passe ne correspondent pas.` |
| `A household can have at most %(max)d members.` | `Un foyer peut compter au maximum %(max)d membres.` |
| `Only the administrator can invite members.` | `Seul l'administrateur peut inviter des membres.` |
| `This household has no free seats left.` | `Ce foyer n'a plus de place disponible.` |
| `This household is already full.` | `Ce foyer est déjà complet.` |
| `This invitation link is not valid.` | `Ce lien d'invitation n'est pas valide.` |
| `This invitation has expired or was already used.` | `Cette invitation a expiré ou a déjà été utilisée.` |
| `You do not have permission to do that in this household.` | `Vous n'avez pas la permission de faire cela dans ce foyer.` |
| `How many people live in the home. Not the same as how many use the app.` | `Combien de personnes vivent dans le foyer. Ce n'est pas le nombre d'utilisateurs de l'application.` |
| `Unspent personal allowance carries into the next month.` | `L'argent de poche non dépensé est reporté au mois suivant.` |

Después compila:

```bash
python manage.py compilemessages
```

Escribe también `README.md` con: requisitos, cómo copiar `.env.example`, cómo obtener la cadena de Supabase, `pip install -r requirements.txt`, `python manage.py migrate`, `python manage.py runserver`, y cómo ejecutar `pytest`.

- [ ] **Step 4: Ejecutar la suite completa**

Run: `pytest -v`
Expected: PASS — todas las pruebas del plan (≈55)

- [ ] **Step 5: Commit**

```bash
git add locale README.md tests/test_traducciones.py
git commit -m "Añade el catálogo francés completo y el README de puesta en marcha"
```

---

## Autorrevisión de este plan

**Cobertura del spec (Plan 1).** §3.1 completo (Household, Membership, Invitation, Profile) → Tasks 2, 3, 5. §6.1 aislamiento → Task 4. §6.2 los cuatro permisos → Tasks 3, 9. §6.3 doble validación → Task 5. §7.4 los tres temas → Task 8. §7.5 los cuatro CSS → Tasks 7, 8. §8 i18n completo, incluidos los formatos fr-CA → Tasks 6, 8, 10. §3.4 Decimal → constraint global (no hay importes en este plan; se ejerce en el Plan 2).

**Fuera de este plan, por diseño.** `Subscription` y `StripeEvent` (§3.1, §5) van al Plan 3 junto con el resto del comercio, porque el trial no significa nada hasta que exista algo que bloquear. Todos los modelos de §3.2 y §3.3, el motor de §4 y las pruebas de §9 relativas al presupuesto van al Plan 2. El PWA de §10 va al Plan 3.

**Consistencia de nombres verificada.** `Membership.PERMISSION_FIELDS` se define en Task 3 y se consume en Tasks 4 y 9. `HouseholdScoped`/`for_user` se definen en Task 4 y los hereda todo el Plan 2. `crear_hogar` se define en Task 5 y se consume en Task 7. `format_money` se define en Task 6 y se consume en el Plan 3.

**Deuda conocida y deliberada.** El envío real de los correos de invitación queda en el Plan 3, junto con la configuración SMTP; en este plan la invitación se crea y su enlace se copia a mano. `_hogar_activo()` asume un hogar por usuario, cierto en Fase 1; si algún día un usuario pertenece a dos hogares, ese es el punto que hay que cambiar.

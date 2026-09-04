import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

# Fuera de DEBUG, exigimos estas variables del entorno en vez de arrancar con
# un valor por defecto: la clave de repuesto era literal en este repositorio
# público y la URL de base de datos apuntaba a un localhost inexistente en
# producción. Un despliegue que olvide DJANGO_SECRET_KEY arrancaba "bien" con
# una clave conocida por cualquiera — sesiones y tokens de restablecimiento de
# contraseña falsificables en silencio. En DEBUG (pruebas y desarrollo local)
# se conservan los valores por defecto de siempre.
if DEBUG:
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "inseguro-solo-para-tests")
    _database_url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/wealthome"
    )
else:
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
    if not SECRET_KEY:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY es obligatoria fuera de DEBUG."
        )
    _database_url = os.environ.get("DATABASE_URL")
    if not _database_url:
        raise ImproperlyConfigured("DATABASE_URL es obligatoria fuera de DEBUG.")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.accounts",
    "apps.households",
    "apps.budget",
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

MIDDLEWARE += ["apps.accounts.middleware.PerfilLocaleMiddleware"]

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
                "apps.core.context_processors.hogar",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_db = urlparse(_database_url)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.path.lstrip("/"),
        "USER": unquote(_db.username) if _db.username else _db.username,
        "PASSWORD": unquote(_db.password) if _db.password else _db.password,
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

# Disco local solo para desarrollo: el destino de despliegue no tiene sistema
# de archivos local durable. Una implementación real debe servir Profile.avatar
# (y cualquier otro archivo subido) desde almacenamiento de objetos — Supabase
# Storage — no desde MEDIA_ROOT.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:inicio"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# La app "tests" solo existe para las pruebas (ver apps/households/scoping.py y
# tests/models.py): trae modelos de andamiaje como Nota que no deben viajar a
# producción, así que se registra únicamente cuando pytest está cargado.
if "pytest" in sys.modules:
    INSTALLED_APPS += ["tests"]

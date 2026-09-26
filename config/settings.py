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

# El .strip() no es cosmetico: "wealthome.site, www.wealthome.site" es como
# cualquiera escribe la variable, y el espacio sobrante hacia que Django
# rechazara ese host con un 400 DisallowedHost imposible de diagnosticar.
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

# ---------------------------------------------------------------------------
# Endurecimiento para produccion. Todo va dentro de `not DEBUG` para no romper
# el desarrollo local, que se sirve por http://127.0.0.1 sin certificado.
#
# SECURE_PROXY_SSL_HEADER es el que no se puede omitir: detras de nginx, Django
# ve la peticion por http aunque el navegador la haya hecho por https, y eso
# rompe DOS cosas a la vez. SECURE_SSL_REDIRECT entra en un bucle infinito de
# redirecciones (Django redirige a https, nginx vuelve a entregar http), y la
# comprobacion de CSRF compara el Origin del navegador
# ("https://wealthome.site") contra el esquema que Django cree
# ("http://wealthome.site") y contesta 403 a TODO formulario. nginx tiene que
# mandar la cabecera: proxy_set_header X-Forwarded-Proto $scheme.
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True

    # La cookie de sesion de una aplicacion financiera no viaja en claro.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # Lax y no Strict a proposito: Strict rompe el retorno de Stripe Checkout,
    # que llega como navegacion desde otro sitio y necesita la sesion para
    # saber a que hogar mirar.
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"

    # HSTS es IRREVERSIBLE mientras dure: el navegador se niega a hablar http
    # con el dominio y el servidor no puede retirarlo. Por eso arranca en una
    # hora — si el certificado da problemas el dia del piloto, el dano caduca
    # en una hora y no en un ano. Subir a 31536000 (y anadir subdominios)
    # cuando lleve unos dias estable.
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

    # Django compara el Origin de cada POST contra esta lista. Se deriva de
    # ALLOWED_HOSTS para que no haya dos listas que mantener: olvidar un
    # dominio en esta da un 403 en todos los formularios de ese dominio.
    CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]

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
    "apps.subscriptions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Justo detras de SecurityMiddleware, que es donde WhiteNoise documenta que
    # tiene que ir: asi los estaticos se sirven sin pasar por sesiones, i18n ni
    # autenticacion, y la redireccion a https sigue ocurriendo antes.
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
                "apps.core.context_processors.navegacion",
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

# Fuera de DEBUG, Django NO sirve /static/: runserver lo hace como cortesia del
# desarrollo y gunicorn no. Sin esto el piloto se veria sin una sola hoja de
# estilos ni un solo script — la aplicacion entera en HTML pelado. WhiteNoise
# los sirve desde el propio proceso de gunicorn, que para dos usuarios es de
# sobra y evita tener que ensenarle las rutas a nginx.
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_MAX_AGE = 31536000  # un ano: la etiqueta {% estatico %} versiona por mtime

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

# Stripe (§5). Vacias en desarrollo y en pruebas: la suite NUNCA llama a Stripe.
# Correo saliente (invitaciones). Con EMAIL_HOST_USER definido se envia por
# SMTP (Gmail con contrasena de aplicacion, ver .env.example); sin el, el
# backend de consola imprime el correo en la terminal, que es lo que quiere el
# desarrollo local. Las pruebas no pasan por aqui: pytest-django fuerza el
# backend en memoria (`mailoutbox`).
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 10  # segundos: el envio es sincrono dentro de la peticion
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "wealthome@localhost")
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST_USER
    else "django.core.mail.backends.console.EmailBackend"
)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRECIO_CENTAVOS = 2500      # CAD $25, pago unico (§5.1)
DIAS_DE_PRUEBA = 14

# El registro publico de /signup/ se puede cerrar sin tocar codigo. Durante un
# piloto privado esta en 0: el hogar lo crea el administrador una sola vez y el
# resto entra por invitacion, asi que dejar abierto un formulario que cualquiera
# puede encontrar solo anade cuentas basura y filas en la base de datos. Con la
# puerta cerrada, /signup/ contesta 404 en vez de 403: un 403 confirma que el
# formulario existe y que solo esta apagado.
REGISTRO_ABIERTO = os.environ.get("DJANGO_REGISTRO_ABIERTO", "1") == "1"

# Sin esto, en produccion una excepcion se convierte en un 500 silencioso: el
# correo de ADMINS no esta configurado y Django no escribe el traceback en
# ningun sitio. Mandarlo a stdout lo deja en el journal de systemd, que es
# donde se va a mirar (`journalctl -u wealthome -f`).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detallado": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "consola": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "detallado",
        },
    },
    "root": {"handlers": ["consola"], "level": "INFO"},
    "loggers": {
        # El traceback de cualquier 500. propagate=False para que no salga dos
        # veces por el root.
        "django.request": {"handlers": ["consola"], "level": "ERROR", "propagate": False},
        # Cada peticion en una linea seria ruido en produccion: gunicorn y nginx
        # ya llevan su propio registro de accesos.
        "django.server": {"handlers": ["consola"], "level": "WARNING", "propagate": False},
    },
}

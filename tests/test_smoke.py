import os
import subprocess
import sys
from pathlib import Path

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


def _importar_settings_en_subproceso(env_extra):
    """Ejecuta `django.setup()` en un intérprete nuevo con el entorno dado.

    config/settings.py ya se ejecutó en ESTE proceso de pytest (con DEBUG=1,
    según el .env real) al arrancar la suite; reimportarlo aquí no vuelve a
    correr su código de módulo, así que el único modo de ejercitar el guardia
    que exige DJANGO_SECRET_KEY/DATABASE_URL fuera de DEBUG es en un proceso
    aparte que lo importe desde cero con ese entorno.

    load_dotenv() se llama con override=False, así que una variable ya
    presente en el entorno del subproceso (aunque sea cadena vacía) no la
    pisa el .env real del repo: por eso basta con pasar DJANGO_SECRET_KEY=""
    o DATABASE_URL="" para forzar la rama que falta, sin tocar el .env.
    """
    env = os.environ.copy()
    env.update(env_extra)
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=str(Path(settings.BASE_DIR)),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_settings_exige_secret_key_fuera_de_debug():
    resultado = _importar_settings_en_subproceso(
        {
            "DJANGO_DEBUG": "0",
            "DJANGO_SECRET_KEY": "",
            "DATABASE_URL": "postgresql://user:pass@host:5432/db",
        }
    )
    assert resultado.returncode != 0
    assert "ImproperlyConfigured" in resultado.stderr
    assert "DJANGO_SECRET_KEY" in resultado.stderr


def test_settings_exige_database_url_fuera_de_debug():
    resultado = _importar_settings_en_subproceso(
        {
            "DJANGO_DEBUG": "0",
            "DJANGO_SECRET_KEY": "una-clave-de-prueba-no-vacia",
            "DATABASE_URL": "",
        }
    )
    assert resultado.returncode != 0
    assert "ImproperlyConfigured" in resultado.stderr
    assert "DATABASE_URL" in resultado.stderr


def test_settings_no_falla_en_debug_sin_variables():
    """En DEBUG, aunque el entorno no traiga las variables, arranca con los
    valores de repuesto de siempre (los que usan la suite y el desarrollo
    local)."""
    env = os.environ.copy()
    env.pop("DJANGO_SECRET_KEY", None)
    env.pop("DATABASE_URL", None)
    env["DJANGO_DEBUG"] = "1"
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    resultado = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=str(Path(settings.BASE_DIR)),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert resultado.returncode == 0, resultado.stderr

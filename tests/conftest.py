import os

import pytest

# El API SINCRONO de Playwright corre sobre un bucle de eventos (usa greenlets),
# y Django bloquea el acceso a la base de datos desde un contexto asincrono. Esta
# es la valvula documentada para exactamente este caso: pruebas y notebooks.
#
# Se pone aqui y no dentro de la prueba porque el fallo ocurre montando la
# fixture `django_db(transaction=True)` que `live_server` necesita, o sea ANTES
# de que el cuerpo de la prueba llegue a ejecutarse.
#
# El riesgo de ponerlo para toda la sesion es enmascarar un uso asincrono
# genuinamente inseguro. Se acepta porque esta aplicacion no tiene codigo
# asincrono: no hay vistas async, ni ORM async, ni canales. Si algun dia los
# hubiera, esto pasa a ser un fixture con `monkeypatch.setenv` en la unica
# prueba de navegador.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")


@pytest.fixture(autouse=True)
def _activar_idioma_por_defecto():
    """Cada prueba arranca en inglés salvo que active otro idioma."""
    from django.utils import translation

    translation.activate("en")
    yield
    translation.deactivate()

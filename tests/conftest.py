import pytest


@pytest.fixture(autouse=True)
def _activar_idioma_por_defecto():
    """Cada prueba arranca en inglés salvo que active otro idioma."""
    from django.utils import translation

    translation.activate("en")
    yield
    translation.deactivate()

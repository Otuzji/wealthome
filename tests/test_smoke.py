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

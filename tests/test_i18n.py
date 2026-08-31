import re
from decimal import Decimal

import pytest
from django.template import Context, Template
from django.utils import translation

from apps.core.templatetags.money import format_money


def _normalizar(texto):
    """CLDR usa espacios finos o duros segun la version; los unificamos."""
    return re.sub(r"[\s\u00a0\u202f]+", " ", texto)


def test_dinero_en_ingles_canadiense():
    assert _normalizar(format_money(Decimal("2847.50"), locale="en_CA")) == "$2,847.50"


def test_dinero_en_frances_canadiense():
    """El signo va despues, decimal con coma, miles con espacio (spec parr. 8)."""
    assert _normalizar(format_money(Decimal("2847.50"), locale="fr_CA")) == "2 847,50 $"


def test_dinero_negativo_en_los_dos_idiomas():
    assert "2,847.50" in _normalizar(format_money(Decimal("-2847.50"), locale="en_CA"))
    assert "2 847,50" in _normalizar(format_money(Decimal("-2847.50"), locale="fr_CA"))


def test_dinero_usa_dos_decimales_siempre():
    assert _normalizar(format_money(Decimal("100"), locale="en_CA")) == "$100.00"


def test_dinero_desde_float_redondea_via_str_no_via_binario():
    """Decimal(2.675) truncaria a $2.67 por el valor binario exacto del float;
    pasar por str primero da el redondeo decimal correcto."""
    assert _normalizar(format_money(2.675, locale="en_CA")) == "$2.68"
    assert _normalizar(format_money(2.665, locale="en_CA")) == "$2.66"


def test_dinero_desde_entero():
    assert _normalizar(format_money(100, locale="en_CA")) == "$100.00"


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

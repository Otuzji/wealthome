from decimal import Decimal

from babel.numbers import format_currency
from django import template
from django.conf import settings
from django.utils.translation import get_language

register = template.Library()

# Idioma de Django -> locale de Babel. Canadá en ambos casos.
LOCALES = {"en": "en_CA", "fr": "fr_CA"}


def _locale_activo():
    return LOCALES.get((get_language() or "en")[:2], "en_CA")


def format_money(amount, locale=None, currency=None):
    """Formatea un importe según la convención del locale.

    en_CA -> $2,847.50    ·    fr_CA -> 2 847,50 $
    """
    if amount is None or amount == "":
        return ""
    if not isinstance(amount, Decimal):
        # Convertir un float directamente a Decimal usa su valor binario
        # exacto y puede redondear al centavo equivocado
        # (Decimal(2.675) -> Decimal('2.67499999999999...')). Pasar por
        # str primero evita ese error de redondeo para float, int o str.
        amount = Decimal(str(amount))
    return format_currency(
        amount,
        currency or settings.DEFAULT_CURRENCY,
        locale=locale or _locale_activo(),
    )


@register.filter(name="money")
def money(amount):
    return format_money(amount)

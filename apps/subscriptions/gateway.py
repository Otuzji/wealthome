"""El unico modulo del proyecto que importa `stripe`.

Que la frontera este en un solo archivo es lo que permite que la suite entera
corra sin claves y sin red: las pruebas sustituyen esta funcion, no la libreria.
"""

import stripe
from django.conf import settings


def crear_sesion_de_pago(*, household, locale, url_exito, url_cancelacion):
    """Una sesion de Stripe Checkout en modo `payment` (§5.1). Devuelve su URL.

    `client_reference_id` lleva el pk del hogar: es como el webhook sabra a
    quien acreditar el pago. NO se usa el correo del cliente, que el usuario
    puede cambiar dentro de la pasarela.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY
    sesion = stripe.checkout.Session.create(
        mode="payment",
        client_reference_id=str(household.pk),
        locale=locale,
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "cad",
                "unit_amount": settings.STRIPE_PRECIO_CENTAVOS,
                "product_data": {"name": "Wealthome"},
            },
        }],
        success_url=url_exito,
        cancel_url=url_cancelacion,
    )
    return sesion.url

from django.shortcuts import redirect, render
from django.utils.translation import get_language

from apps.households.permissions import con_hogar, sin_guardia_de_suscripcion, solo_admin

from .gateway import crear_sesion_de_pago


@solo_admin
@sin_guardia_de_suscripcion
def pagar(request, hogar):
    """Manda a la pasarela. Es @solo_admin porque pagar es gobernar el hogar,
    no editar sus finanzas: los cuatro permisos del §6.2 son otra cosa.

    El orden de los decoradores no es negociable: sin_guardia_de_suscripcion
    tiene que quedar DENTRO, sobre la funcion que solo_admin envuelve, o la
    marca de exencion no se ve y un hogar expirado no podria pagar para dejar
    de estarlo — que es justo el punto muerto que el §2.2 quiere evitar.
    """
    if request.method != "POST":
        # Destino temporal: subscriptions:estado lo crea la Tarea 11, y hasta
        # entonces este redirect reventaria con NoReverseMatch. Mismo apano y
        # mismo motivo que el enlace de templates/403.html en la Tarea 7.
        # LA TAREA 11 TIENE QUE CAMBIARLO a "subscriptions:estado".
        return redirect("households:ajustes")
    url = crear_sesion_de_pago(
        household=hogar,
        locale=get_language() or "en",
        url_exito=request.build_absolute_uri("/subscription/return/"),
        url_cancelacion=request.build_absolute_uri("/subscription/"),
    )
    return redirect(url)


@con_hogar
def retorno(request, hogar):
    """§5.2: NO concede nada. Cualquiera puede visitar esta URL sin pagar.
    Quien acredita el pago es el webhook, y solo el webhook."""
    return render(request, "subscriptions/retorno.html", {
        "suscripcion": getattr(hogar, "subscription", None),
    })

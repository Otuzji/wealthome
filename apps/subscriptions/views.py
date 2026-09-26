from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import get_language, gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.households.permissions import con_hogar, sin_guardia_de_suscripcion, solo_admin

from .gateway import crear_sesion_de_pago, leer_evento
from .services import procesar_evento


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
        return redirect("subscriptions:estado")
    # Sin clave, `stripe` lanzaria AuthenticationError y el administrador veria
    # un 500 en el momento exacto en que intenta pagar para recuperar la
    # escritura de su hogar. Se comprueba aqui para que vea la pantalla de
    # estado con un aviso y sepa que el problema es del despliegue, no suyo.
    if not settings.STRIPE_SECRET_KEY:
        # El literal va en UNA sola linea, y no partido en dos por el ancho:
        # tests/test_catalogo_exhaustivo.py busca las cadenas traducibles con una
        # expresion regular sobre el texto fuente y NO recompone la concatenacion
        # implicita de Python (lo dice su docstring). Partido, la prueba buscaria
        # en el catalogo la primera mitad —que no es el msgid que usa Django en
        # tiempo de ejecucion— y daria la cadena por no traducida para siempre.
        messages.error(request, _("Payments are not configured on this server yet."))
        return redirect("subscriptions:estado")
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


@con_hogar
def estado(request, hogar):
    """La pantalla del §5.4. Plana y fea a proposito: la Tarea 16 la viste."""
    return render(request, "subscriptions/estado.html", {
        "suscripcion": getattr(hogar, "subscription", None),
        "precio": settings.STRIPE_PRECIO_CENTAVOS / 100,
    })


@csrf_exempt
@require_POST
def webhook(request):
    """La UNICA fuente de verdad del pago (§5.2).

    Publico y sin autenticar por definicion: quien llama es Stripe, no un
    usuario. Sin decoradores de hogar, porque no hay sesion. Su unica defensa
    es la firma, y por eso se prueba hostil.
    """
    firma = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        evento = leer_evento(request.body, firma)
    except ValueError:
        return HttpResponse(status=400)

    procesar_evento(evento)
    # 200 siempre que la firma cuadre, aunque no hubiera nada que hacer: un
    # error por un evento que no nos interesa hace que Stripe lo reintente
    # para siempre.
    return HttpResponse(status=200)

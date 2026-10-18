from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import TemplateView

from apps.households.permissions import SuscripcionVencida


def sin_conexion(request):
    """La pagina que el service worker ensena sin red. Se genera SIEMPRE como
    anonima: se precarga con la sesion de quien instalo la app, y si llevara su
    nombre y su hogar los ensenaria a quien tenga el telefono despues. Y sin
    purga: ensenarla sin red no puede borrar lo que si estaba guardado."""
    from django.contrib.auth.models import AnonymousUser

    request.user = AnonymousUser()
    return render(request, "sin-conexion.html", {"sin_purga": True})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("household/", include("apps.households.urls")),
    path("budget/", include("apps.budget.urls")),
    path("subscription/", include("apps.subscriptions.urls")),
    # Sin decorador de sesion a proposito: el service worker tiene que poder
    # precargarla, y es una pagina sin datos.
    path("offline/", sin_conexion, name="sin_conexion"),
    # Desde la raiz y no desde /static/: el alcance de un service worker es su
    # propio directorio, asi que uno servido en /static/js/ no puede controlar
    # el sitio entero. Ver el comentario de templates/sw.js.
    path("sw.js", TemplateView.as_view(
        template_name="sw.js", content_type="application/javascript",
    ), name="service_worker"),
    path("", include("apps.accounts.urls")),
]


def permiso_denegado(request, exception=None):
    """El handler403 propio: le pasa a la plantilla si el motivo fue una
    suscripcion vencida (§5.2), para que ofrezca pagar en vez del 403 llano.
    """
    return render(
        request,
        "403.html",
        {
            "es_suscripcion_vencida": isinstance(exception, SuscripcionVencida),
            "mensaje": str(exception) if exception else "",
        },
        status=403,
    )


handler403 = "config.urls.permiso_denegado"

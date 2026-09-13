from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import TemplateView

from apps.households.permissions import SuscripcionVencida

urlpatterns = [
    path("admin/", admin.site.urls),
    path("household/", include("apps.households.urls")),
    path("budget/", include("apps.budget.urls")),
    path("subscription/", include("apps.subscriptions.urls")),
    # Sin decorador de sesion a proposito: el service worker tiene que poder
    # precargarla, y es una pagina sin datos.
    path("offline/", TemplateView.as_view(template_name="sin-conexion.html"),
         name="sin_conexion"),
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

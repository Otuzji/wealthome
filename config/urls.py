from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path

from apps.households.permissions import SuscripcionVencida

urlpatterns = [
    path("admin/", admin.site.urls),
    path("household/", include("apps.households.urls")),
    path("budget/", include("apps.budget.urls")),
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

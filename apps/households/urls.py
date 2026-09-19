from django.urls import path

from . import views

app_name = "households"

urlpatterns = [
    path("settings/", views.ajustes, name="ajustes"),
    path("settings/invite/", views.invitar_view, name="invitar"),
    path("settings/permissions/<int:pk>/", views.permisos, name="permisos"),
    path("settings/invitations/<int:pk>/revoke/", views.revocar, name="revocar"),
    path("settings/invitations/<int:pk>/resend/", views.reenviar, name="reenviar"),
    path("invitation/<str:token>/", views.aceptar, name="aceptar"),
]

from django.urls import path

from . import views

app_name = "households"

urlpatterns = [
    path("settings/", views.ajustes, name="ajustes"),
    path("settings/invite/", views.invitar_view, name="invitar"),
    path("settings/permissions/<int:pk>/", views.permisos, name="permisos"),
    path("invitation/<str:token>/", views.aceptar, name="aceptar"),
]

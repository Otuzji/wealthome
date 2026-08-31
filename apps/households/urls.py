from django.urls import path

from . import views

app_name = "households"

urlpatterns = [
    path("ajustes/", views.ajustes, name="ajustes"),
    path("ajustes/invitar/", views.invitar_view, name="invitar"),
    path("ajustes/permisos/<int:pk>/", views.permisos, name="permisos"),
    path("invitacion/<str:token>/", views.aceptar, name="aceptar"),
]

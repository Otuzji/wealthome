from django.urls import path

from . import views

app_name = "budget"

urlpatterns = [
    path("", views.configurar, name="configurar"),
    path("income/new/", views.ingreso_nuevo, name="ingreso_nuevo"),
    path("expense/new/", views.gasto_nuevo, name="gasto_nuevo"),
    path("category/new/", views.categoria_nueva, name="categoria_nueva"),
    path("split/new/", views.reparto_nuevo, name="reparto_nuevo"),
    path("spend/", views.registrar, name="registrar"),
    path("month/", views.mes, name="mes"),
    path("month/<int:anio>/<int:numero>/", views.mes, name="mes"),
    path("plan/", views.planificar, name="planificar"),
    path("close/", views.cerrar, name="cerrar"),
    path("goals/", views.metas, name="metas"),
    path("goals/new/", views.meta_nueva, name="meta_nueva"),
    path("goals/contribute/", views.aportar, name="aportar"),
]

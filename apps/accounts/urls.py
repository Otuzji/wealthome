from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("registro/", views.registro, name="registro"),
    path("entrar/", views.Login.as_view(), name="login"),
    path("salir/", views.Logout.as_view(), name="logout"),
    path("", views.inicio, name="inicio"),
]

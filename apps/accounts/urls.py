from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.registro, name="registro"),
    path("login/", views.Login.as_view(), name="login"),
    path("logout/", views.Logout.as_view(), name="logout"),
    path("preferences/", views.preferencias, name="preferencias"),
    path("", views.inicio, name="inicio"),
]

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.registro, name="registro"),
    path("login/", views.Login.as_view(), name="login"),
    path("logout/", views.Logout.as_view(), name="logout"),
    # Todo bajo /password-reset/: el service worker no cachea ese prefijo.
    path("password-reset/", views.OlvideContrasena.as_view(), name="password_reset"),
    path("password-reset/sent/", views.EnlaceEnviado.as_view(), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", views.ContrasenaNueva.as_view(),
         name="password_reset_confirm"),
    path("preferences/", views.preferencias, name="preferencias"),
    path("", views.inicio, name="inicio"),
]

from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("pay/", views.pagar, name="pagar"),
    path("return/", views.retorno, name="retorno"),
]

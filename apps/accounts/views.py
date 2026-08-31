from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from apps.households.services import crear_hogar

from .forms import RegistroForm

User = get_user_model()


def registro(request):
    if request.user.is_authenticated:
        return redirect("accounts:inicio")

    if request.method == "POST":
        form = RegistroForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = User.objects.create_user(
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password1"],
                    display_name=form.cleaned_data["display_name"],
                )
                crear_hogar(user, form.cleaned_data["household_name"], form.cleaned_data["family_size"])
            login(request, user)
            return redirect("accounts:inicio")
    else:
        form = RegistroForm()
    return render(request, "accounts/registro.html", {"form": form})


class Login(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class Logout(LogoutView):
    next_page = reverse_lazy("accounts:login")


@login_required
def inicio(request):
    return render(request, "accounts/inicio.html")

from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from apps.households.services import crear_hogar

from .forms import PreferenciasForm, RegistroForm

User = get_user_model()


def registro(request):
    if request.user.is_authenticated:
        return redirect("accounts:inicio")

    if request.method == "POST":
        form = RegistroForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.crear_usuario()
                crear_hogar(user, form.cleaned_data["household_name"], form.cleaned_data["family_size"])
            login(request, user)
            # Al paso 2 del asistente y no a la portada: el paso 1 acaba de
            # crear el hogar, y sin esto nadie descubre los cinco que faltan.
            return redirect("budget:incorporacion", paso=2)
    else:
        form = RegistroForm()
    return render(request, "accounts/registro.html", {"form": form})


class Login(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class Logout(LogoutView):
    next_page = reverse_lazy("accounts:login")

    def dispatch(self, request, *args, **kwargs):
        """Purga la cache del navegador al salir.

        La PWA cachea las paginas financieras que el miembro haya abierto para
        que pueda consultarlas sin senal (§10). En un dispositivo compartido,
        dejarlas ahi despues de cerrar sesion seria entregarle el presupuesto de
        una familia a la siguiente persona que lo use.

        Dos mecanismos, porque ninguno basta solo: Clear-Site-Data lo hace el
        navegador, y el mensaje al service worker (ver base.html) cubre a los
        navegadores que no la implementan.
        """
        respuesta = super().dispatch(request, *args, **kwargs)
        respuesta.headers["Clear-Site-Data"] = '"cache", "storage"'
        return respuesta


@login_required
def inicio(request):
    """El menú no ofrece lo que el miembro no puede hacer.

    Un 403 al hacer clic es correcto pero grosero.
    """
    from apps.households.permissions import membresia_actual

    try:
        membresia = membresia_actual(request)
    except PermissionDenied:
        membresia = None
    return render(request, "accounts/inicio.html", {
        "perms_presupuesto": bool(membresia and membresia.can_edit_budget),
    })


@login_required
def preferencias(request):
    form = PreferenciasForm(request.POST or None, instance=request.user.profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("accounts:preferencias")
    return render(request, "accounts/preferencias.html", {"form": form})

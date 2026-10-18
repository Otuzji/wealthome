from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

from apps.households.services import crear_hogar

from . import bloqueo
from .forms import EntradaForm, OlvideContrasenaForm, PreferenciasForm, RegistroForm

User = get_user_model()


def registro(request):
    """Alta de un hogar nuevo. Se puede cerrar con DJANGO_REGISTRO_ABIERTO=0.

    Cerrada, contesta 404 y no 403: un 403 confirmaria que el formulario existe
    y que solo esta apagado. Se comprueba antes de mirar la sesion para que la
    respuesta no dependa de quien pregunta.
    """
    if not settings.REGISTRO_ABIERTO:
        raise Http404("El registro publico esta cerrado.")

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
    authentication_form = EntradaForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        # Para que la pagina no ofrezca "Create a household" cuando ese enlace
        # lleva a un 404. El menu no ofrece lo que no se puede hacer, igual que
        # en `inicio`.
        return super().get_context_data(**kwargs) | {
            "registro_abierto": settings.REGISTRO_ABIERTO,
        }


class OlvideContrasena(PasswordResetView):
    """Pedir el enlace. Responde lo mismo exista o no la cuenta: el formulario
    no sirve para averiguar que correos estan registrados."""

    template_name = "accounts/olvide_contrasena.html"
    form_class = OlvideContrasenaForm
    email_template_name = "accounts/email/recuperar.txt"
    html_email_template_name = "accounts/email/recuperar.html"
    subject_template_name = "accounts/email/recuperar_asunto.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class EnlaceEnviado(PasswordResetDoneView):
    template_name = "accounts/enlace_enviado.html"


class ContrasenaNueva(PasswordResetConfirmView):
    """Poner la contrasena nueva desde el enlace. No inicia sesion: vuelve a la
    entrada con un aviso, y la persona entra con la clave que acaba de poner."""

    template_name = "accounts/contrasena_nueva.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        # Quien demuestra que controla el correo recupera la cuenta al momento,
        # aunque un desconocido la hubiera bloqueado probando contrasenas.
        bloqueo.desbloquear(form.user)
        messages.success(self.request, _("Your password has been changed. You can sign in now."))
        return respuesta


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

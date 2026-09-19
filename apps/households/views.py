import smtplib

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _

from .emails import enviar_invitacion
from apps.accounts.forms import RegistroInvitadoForm

from .forms import InvitarForm, PermisosForm
from .models import Invitation, Membership
from .permissions import con_hogar, membresia_actual, solo_admin
from .services import (
    HouseholdLleno,
    InvitacionInvalida,
    aceptar_invitacion,
    invitacion_por_token,
    invitaciones_pendientes,
    invitar,
    registrar_invitado,
    revocar_invitacion,
)

User = get_user_model()


@con_hogar
def ajustes(request, hogar):
    es_admin = membresia_actual(request).role == Membership.ADMIN
    # Solo el admin ve las pendientes: llevan el enlace, que vale por una entrada.
    pendientes = (
        [(inv, _enlace_de(request, inv)) for inv in invitaciones_pendientes(hogar)]
        if es_admin
        else []
    )
    return render(
        request,
        "households/ajustes.html",
        {
            "hogar": hogar,
            "miembros": hogar.active_memberships().select_related("user"),
            "es_admin": es_admin,
            "pendientes": pendientes,
        },
    )


@solo_admin
def invitar_view(request, hogar):
    form = InvitarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            invitacion = invitar(
                request.user, hogar, form.cleaned_data["email"], form.cleaned_data["language"]
            )
        except HouseholdLleno as exc:
            form.add_error(None, str(exc))
        else:
            _enviar_o_avisar(request, invitacion)
            return redirect("households:ajustes")
    return render(request, "households/invitar.html", {"form": form})


def _enlace_de(request, invitacion):
    return request.build_absolute_uri(reverse("households:aceptar", args=[invitacion.token]))


def _enviar_o_avisar(request, invitacion):
    """Un fallo del SMTP no tira la invitación: el token ya existe y Ajustes
    muestra el enlace para compartirlo a mano."""
    try:
        enviar_invitacion(invitacion, _enlace_de(request, invitacion))
    except (smtplib.SMTPException, OSError):
        messages.warning(
            request,
            _("The invitation was created but we could not send the email. Share the link below with %(email)s.")
            % {"email": invitacion.email},
        )
    else:
        messages.success(request, _("Invitation sent to %(email)s.") % {"email": invitacion.email})


@solo_admin
def permisos(request, hogar, pk):
    # Acotado al hogar del admin: una membresía ajena da 404, no 403,
    # para no revelar que existe.
    membresia = get_object_or_404(Membership, pk=pk, household=hogar)
    form = PermisosForm(request.POST or None, instance=membresia)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("households:ajustes")
    return render(request, "households/permisos.html", {"form": form, "membresia": membresia})


def _invitacion_del_hogar(hogar, pk):
    # Acotada al hogar del admin igual que `permisos`: la de otro hogar da 404.
    return get_object_or_404(Invitation, pk=pk, household=hogar, accepted_at__isnull=True)


@solo_admin
@require_POST
def revocar(request, hogar, pk):
    invitacion = _invitacion_del_hogar(hogar, pk)
    revocar_invitacion(invitacion)
    messages.success(
        request, _("Invitation to %(email)s revoked.") % {"email": invitacion.email}
    )
    return redirect("households:ajustes")


@solo_admin
@require_POST
def reenviar(request, hogar, pk):
    _enviar_o_avisar(request, _invitacion_del_hogar(hogar, pk))
    return redirect("households:ajustes")


def aceptar(request, token):
    """La única vista del hogar sin guardia de sesión, y a propósito: quien
    llega por el enlace puede no tener cuenta todavía. Con sesión, acepta;
    sin ella, ve quién le invita y crea su cuenta como miembro de ese hogar
    (o va a iniciar sesión si ya tiene una)."""
    if request.user.is_authenticated:
        return _aceptar_con_sesion(request, token)
    return _aceptar_sin_sesion(request, token)


def _contexto_invitacion(token):
    try:
        invitacion = invitacion_por_token(token)
    except InvitacionInvalida as exc:
        return {"token": token, "error": str(exc)}
    return {"token": token, "invitacion": invitacion}


def _aceptar_con_sesion(request, token):
    contexto = _contexto_invitacion(token)
    if request.method == "POST":
        try:
            aceptar_invitacion(request.user, token)
        except (InvitacionInvalida, HouseholdLleno) as exc:
            contexto["error"] = str(exc)
            return render(request, "households/aceptar.html", contexto)
        return redirect("households:ajustes")
    return render(request, "households/aceptar.html", contexto)


def _aceptar_sin_sesion(request, token):
    contexto = _contexto_invitacion(token)
    invitacion = contexto.get("invitacion")
    if invitacion is None:
        return render(request, "households/aceptar.html", contexto)

    contexto["ya_tiene_cuenta"] = User.objects.filter(email__iexact=invitacion.email).exists()
    contexto["url_login"] = f"{reverse('accounts:login')}?next={request.path}"
    form = RegistroInvitadoForm(request.POST or None, initial={"email": invitacion.email})
    if request.method == "POST" and form.is_valid():
        try:
            user = registrar_invitado(form, token)
        except (InvitacionInvalida, HouseholdLleno) as exc:
            contexto["error"] = str(exc)
        else:
            login(request, user)
            return redirect("accounts:inicio")
    contexto["form"] = form
    return render(request, "households/aceptar.html", contexto)

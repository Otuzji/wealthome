from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .forms import InvitarForm, PermisosForm
from .models import Membership
from .permissions import get_membership
from .services import HouseholdLleno, InvitacionInvalida, aceptar_invitacion, invitar


def _hogar_activo(request):
    """El primer hogar activo del usuario.

    Asume que un usuario pertenece a un único hogar activo — cierto en la
    Fase 1. Quien añada soporte para varios hogares por usuario debe empezar
    por aquí: esta función es el único punto donde se elige "el" hogar.
    """
    membresia = Membership.objects.filter(user=request.user, is_active=True).select_related("household").first()
    if membresia is None:
        raise PermissionDenied
    return membresia.household


@login_required
def ajustes(request):
    hogar = _hogar_activo(request)
    return render(
        request,
        "households/ajustes.html",
        {
            "hogar": hogar,
            "miembros": hogar.active_memberships().select_related("user"),
            "es_admin": get_membership(request.user, hogar).role == Membership.ADMIN,
        },
    )


@login_required
def invitar_view(request):
    hogar = _hogar_activo(request)
    form = InvitarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            invitar(request.user, hogar, form.cleaned_data["email"], form.cleaned_data["language"])
        except PermissionDenied:
            return HttpResponseForbidden()
        except HouseholdLleno as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("households:ajustes")
    return render(request, "households/invitar.html", {"form": form})


@login_required
def permisos(request, pk):
    hogar = _hogar_activo(request)
    if get_membership(request.user, hogar).role != Membership.ADMIN:
        return HttpResponseForbidden()

    # Acotado al hogar del admin: una membresía ajena da 404, no 403,
    # para no revelar que existe.
    membresia = get_object_or_404(Membership, pk=pk, household=hogar)
    form = PermisosForm(request.POST or None, instance=membresia)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("households:ajustes")
    return render(request, "households/permisos.html", {"form": form, "membresia": membresia})


@login_required
def aceptar(request, token):
    if request.method == "POST":
        try:
            aceptar_invitacion(request.user, token)
        except (InvitacionInvalida, HouseholdLleno) as exc:
            return render(request, "households/aceptar.html", {"error": str(exc), "token": token})
        return redirect("households:ajustes")
    return render(request, "households/aceptar.html", {"token": token})

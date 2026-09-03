from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import InvitarForm, PermisosForm
from .models import Membership
from .permissions import con_hogar, membresia_actual, solo_admin
from .services import HouseholdLleno, InvitacionInvalida, aceptar_invitacion, invitar


@con_hogar
def ajustes(request, hogar):
    return render(
        request,
        "households/ajustes.html",
        {
            "hogar": hogar,
            "miembros": hogar.active_memberships().select_related("user"),
            "es_admin": membresia_actual(request).role == Membership.ADMIN,
        },
    )


@solo_admin
def invitar_view(request, hogar):
    form = InvitarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            invitar(request.user, hogar, form.cleaned_data["email"], form.cleaned_data["language"])
        except HouseholdLleno as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("households:ajustes")
    return render(request, "households/invitar.html", {"form": form})


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


@login_required
def aceptar(request, token):
    """La única vista sin @con_hogar, y a propósito: quien acepta una
    invitación todavía no pertenece a ningún hogar. Resolver el hogar antes
    de aceptar sería negarle la entrada a todo invitado nuevo."""
    if request.method == "POST":
        try:
            aceptar_invitacion(request.user, token)
        except (InvitacionInvalida, HouseholdLleno) as exc:
            return render(request, "households/aceptar.html", {"error": str(exc), "token": token})
        return redirect("households:ajustes")
    return render(request, "households/aceptar.html", {"token": token})

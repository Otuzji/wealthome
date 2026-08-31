from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Household, Invitation, Membership
from .permissions import PermissionDenied, get_membership


class HouseholdLleno(Exception):
    """El hogar ya llegó a su máximo de miembros contando invitaciones pendientes."""


class InvitacionInvalida(Exception):
    """El token no existe, ya se usó o caducó."""


def _puestos_libres(household):
    ocupados = household.active_memberships().count()
    pendientes = Invitation.objects.filter(
        household=household, accepted_at__isnull=True, expires_at__gt=timezone.now()
    ).count()
    return Membership.MAX_PER_HOUSEHOLD - ocupados - pendientes


@transaction.atomic
def crear_hogar(user, nombre, family_size):
    household = Household.objects.create(name=nombre, family_size=family_size)
    Membership.objects.create(user=user, household=household, role=Membership.ADMIN)
    return household


@transaction.atomic
def invitar(invitador, household, email, language):
    membresia = get_membership(invitador, household)
    if membresia is None or membresia.role != Membership.ADMIN:
        raise PermissionDenied(_("Only the administrator can invite members."))

    if _puestos_libres(household) <= 0:
        raise HouseholdLleno(_("This household has no free seats left."))

    return Invitation.objects.create(
        household=household, email=email, language=language, invited_by=invitador
    )


@transaction.atomic
def aceptar_invitacion(user, token):
    try:
        invitacion = Invitation.objects.select_for_update().get(token=token)
    except Invitation.DoesNotExist:
        raise InvitacionInvalida(_("This invitation link is not valid."))

    if not invitacion.is_valid():
        raise InvitacionInvalida(_("This invitation has expired or was already used."))

    # Bloquea la fila del hogar: dos invitaciones distintas bloquean filas de
    # invitación distintas y no se serializan entre sí, así que el conteo tiene
    # que protegerse sobre lo que se cuenta.
    household = Household.objects.select_for_update().get(pk=invitacion.household_id)
    if household.active_memberships().count() >= Membership.MAX_PER_HOUSEHOLD:
        raise HouseholdLleno(_("This household is already full."))

    membresia = Membership.objects.create(user=user, household=household, role=Membership.MEMBER)
    invitacion.accepted_at = timezone.now()
    invitacion.save(update_fields=["accepted_at"])
    return membresia

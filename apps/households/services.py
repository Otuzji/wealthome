from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Household, Invitation, Membership
from .permissions import PermissionDenied, get_membership


class HouseholdLleno(Exception):
    """El hogar ya llegó a su máximo de miembros contando invitaciones pendientes."""


class InvitacionInvalida(Exception):
    """El token no existe, ya se usó o caducó."""


def invitaciones_pendientes(household):
    """Las que aún ocupan un puesto: ni aceptadas ni caducadas."""
    return Invitation.objects.filter(
        household=household, accepted_at__isnull=True, expires_at__gt=timezone.now()
    ).order_by("created_at")


def revocar_invitacion(invitacion):
    """Borrarla basta: `_puestos_libres` solo cuenta las que existen y siguen
    vigentes, así que el puesto se libera en el acto."""
    invitacion.delete()


def _puestos_libres(household):
    ocupados = household.active_memberships().count()
    return Membership.MAX_PER_HOUSEHOLD - ocupados - invitaciones_pendientes(household).count()


@transaction.atomic
def crear_hogar(user, nombre, family_size):
    household = Household.objects.create(name=nombre, family_size=family_size)
    Membership.objects.create(user=user, household=household, role=Membership.ADMIN)

    # El árbol de categorías del §3.2 se copia por hogar (desviación 1 del
    # diseño del Plan 2): HouseholdScoped.household no admite nulo, y sembrar
    # por hogar hace además que renombrar una categoría del sistema no
    # necesite una tabla de anulaciones.
    from apps.budget.seeds import sembrar

    sembrar(household)

    from apps.subscriptions.services import crear_suscripcion

    crear_suscripcion(household)
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


def invitacion_por_token(token):
    """La invitación si existe y sigue viva; si no, InvitacionInvalida con el
    motivo. Es la misma comprobación que hace `aceptar_invitacion`, expuesta
    para la página que el invitado ve ANTES de tener cuenta."""
    try:
        invitacion = Invitation.objects.select_related("household", "invited_by").get(token=token)
    except Invitation.DoesNotExist:
        raise InvitacionInvalida(_("This invitation link is not valid."))
    if not invitacion.is_valid():
        raise InvitacionInvalida(_("This invitation has expired or was already used."))
    return invitacion


@transaction.atomic
def registrar_invitado(form, token):
    """Crea la cuenta y la mete en el hogar en la misma transacción: si la
    invitación caducó entre el GET y el POST, no queda un usuario huérfano
    sin hogar. El perfil nace en el idioma en que se escribió la invitación."""
    invitacion = invitacion_por_token(token)
    user = form.crear_usuario()
    aceptar_invitacion(user, token)
    user.profile.language = invitacion.language
    user.profile.save(update_fields=["language"])
    return user


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

    # Hallazgo de la Tarea 5: si la invitación llega a alguien que ya es
    # miembro de este hogar, insertar chocaría con la restricción única
    # una_membresia_por_usuario_y_hogar y saldría una IntegrityError cruda.
    # Se comprueba aquí, dentro del mismo candado de la fila del hogar, para
    # que siga siendo seguro ante condiciones de carrera.
    if Membership.objects.filter(user=user, household=household).exists():
        raise InvitacionInvalida(_("You are already a member of this household."))

    if household.active_memberships().count() >= Membership.MAX_PER_HOUSEHOLD:
        raise HouseholdLleno(_("This household is already full."))

    membresia = Membership.objects.create(user=user, household=household, role=Membership.MEMBER)
    invitacion.accepted_at = timezone.now()
    invitacion.save(update_fields=["accepted_at"])
    return membresia

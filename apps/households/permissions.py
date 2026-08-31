from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from .models import Membership

__all__ = ["PermissionDenied", "get_membership", "require_permission"]


def get_membership(user, household):
    """La membresía activa del usuario en el hogar, o None."""
    if not getattr(user, "is_authenticated", False):
        return None
    return Membership.objects.filter(user=user, household=household, is_active=True).first()


def require_permission(user, household, permission):
    """Lanza PermissionDenied si el usuario no tiene ese permiso en ese hogar."""
    if permission not in Membership.PERMISSION_FIELDS:
        raise ValueError(f"Permiso desconocido: {permission!r}")

    membresia = get_membership(user, household)
    if membresia is None or not getattr(membresia, permission):
        raise PermissionDenied(_("You do not have permission to do that in this household."))
    return membresia

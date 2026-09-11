"""La capa central de autorización.

Spec §6.1: los permisos viven aquí y las vistas los invocan, en vez de estar
*"repartidos a mano vista por vista, donde tarde o temprano uno se olvida"*.

Dos responsabilidades, deliberadamente juntas porque toda vista necesita las
dos a la vez:

1. **Qué hogar es este** (`hogar_actual`). Una sola respuesta para toda la
   aplicación. La Fase 1 asume un hogar por usuario, pero "asume" no es
   "impide": cuando hay dos, se elige el de la membresía más antigua, y esa
   elección es estable entre peticiones. La alternativa —devolver los dos—
   sumaría el dinero de dos familias en un presupuesto sin lanzar ningún
   error, que es el peor modo de fallo posible en software financiero.

2. **Quién puede hacer qué** (`requiere_permiso`, `solo_admin`, `con_hogar`).

Los tres decoradores resuelven el hogar y lo pasan a la vista como segundo
argumento, después de `request`:

    @requiere_permiso("can_edit_budget")
    def editar_presupuesto(request, hogar):
        lineas = BudgetLine.objects.for_household(hogar)

Cada uno incluye `login_required`, para que no haya dos cosas que recordar.
Un anónimo no es un intruso —no ha dicho quién es—, así que se le manda a
iniciar sesión; a un autenticado sin derecho se le niega con
`PermissionDenied`, que Django convierte en la página 403 traducida.
"""

import functools

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from .models import Membership

__all__ = [
    "PermissionDenied",
    "SuscripcionVencida",
    "con_hogar",
    "get_membership",
    "hogar_actual",
    "require_permission",
    "requiere_permiso",
    "sin_guardia_de_suscripcion",
    "solo_admin",
]

METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class SuscripcionVencida(PermissionDenied):
    """La prueba termino y el hogar no ha pagado: solo lectura (§5.2).

    Subclase de PermissionDenied para que la maquinaria de 403 que ya existe la
    sirva sin middleware nuevo. La plantilla 403 la distingue y ofrece pagar.
    """


def sin_guardia_de_suscripcion(vista):
    """Marca una vista como exenta de la guardia de suscripcion.

    Existe con nombre y no como una condicion escondida dentro de la guardia:
    si la guardia cubriera las vistas de pago, un hogar expirado no podria
    pagar para dejar de estarlo. Es la unica exencion, y se ve en la revision.
    """
    vista.permite_escritura_expirada = True
    return vista


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


def membresia_actual(request):
    """La membresía con la que este usuario actúa en esta petición.

    Se cachea en la petición: cada vista del Plan 2 preguntará por el hogar
    varias veces —el queryset, el formulario, la plantilla— y una capa
    central que cobra una consulta cada vez deja de usarse.
    """
    cacheada = getattr(request, "_membresia_actual", None)
    if cacheada is not None:
        return cacheada

    membresia = (
        Membership.objects.filter(user=request.user, is_active=True)
        .select_related("household")
        # joined_at antes que pk: si dos hogares se crearan en la misma
        # transacción, el id de fila no dice cuál llegó primero.
        .order_by("joined_at", "pk")
        .first()
    )
    if membresia is None:
        raise PermissionDenied(_("You do not belong to a household."))

    request._membresia_actual = membresia
    request.hogar = membresia.household
    return membresia


def hogar_actual(request):
    """El hogar de esta petición. El único sitio donde se elige "el" hogar."""
    return membresia_actual(request).household


def _decorador(comprobar):
    """Fábrica de los tres decoradores: resuelven el hogar, comprueban, y lo
    pasan a la vista. Comparten cuerpo para que no puedan divergir."""

    def envolver(vista):
        @login_required
        @functools.wraps(vista)
        def envuelta(request, *args, **kwargs):
            membresia = membresia_actual(request)
            comprobar(membresia)
            # La guardia de suscripcion, por METODO y no por vista: asi las
            # vistas de htmx que aun no existen nacen cubiertas, y "expirar no
            # destruye datos" (§5.2) se cumple por construccion.
            if (
                request.method not in METODOS_SEGUROS
                and not getattr(vista, "permite_escritura_expirada", False)
                and not membresia.household.puede_escribir
            ):
                raise SuscripcionVencida(
                    _("Your trial has ended. Subscribe to keep adding to your budget.")
                )
            return vista(request, membresia.household, *args, **kwargs)

        return envuelta

    return envolver


def _pertenecer(membresia):
    """Pertenecer al hogar ya es la comprobación: membresia_actual lanzó si no."""


def _ser_admin(membresia):
    if membresia.role != Membership.ADMIN:
        raise PermissionDenied(_("Only the administrator can do that."))


con_hogar = _decorador(_pertenecer)
"""Solo exige pertenecer al hogar. Para las pantallas que cualquier miembro ve."""


solo_admin = _decorador(_ser_admin)
"""Para lo que gobierna el hogar en sí: invitar, quitar, repartir permisos.

Es una comprobación de **rol**, no de los cuatro permisos del spec §6.2:
esos dicen qué puede ver y tocar un miembro de las finanzas, no quién manda.
"""


def requiere_permiso(permission):
    """Exige uno de los cuatro permisos del spec §6.2.

    El nombre del permiso se valida al declarar la vista, no al servirla: un
    permiso mal escrito es un error de programación y tiene que reventar al
    importar el módulo de vistas, no la primera vez que alguien entre a esa
    pantalla.
    """
    if permission not in Membership.PERMISSION_FIELDS:
        raise ValueError(
            f"Permiso desconocido: {permission!r}. "
            f"Los permisos son {', '.join(Membership.PERMISSION_FIELDS)}."
        )

    def comprobar(membresia):
        if not getattr(membresia, permission):
            raise PermissionDenied(
                _("You do not have permission to do that in this household.")
            )

    return _decorador(comprobar)

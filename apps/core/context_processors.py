"""Lo que toda plantilla necesita saber.

El hogar de la petición lo fija `apps.households.permissions.membresia_actual`
cuando un decorador resuelve el hogar, así que aquí solo se lee: una plantilla
que necesite la moneda del hogar (`{{ importe|money:hogar.currency }}`) no
cuesta una consulta por render.

`navegacion` es la única fuente del menú. Que sea una sola lista y no HTML
repartido por las plantillas es lo que permite que tests/test_navegacion.py la
recorra entera y afirme, por perfil de permiso, que no falta ni sobra ninguna
pantalla. El Plan 2 enlazaba 1 de 6 porque el menú era prosa.

Devuelve `None` —y no revienta— en las pantallas sin hogar: registro, login
y aceptar una invitación.
"""

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _


def hogar(request):
    return {"hogar": getattr(request, "hogar", None)}


def _permiso(membresia, nombre):
    return membresia is not None and getattr(membresia, nombre, False)


def _sin_menu():
    """Las dos salidas tempranas, con la MISMA forma que la salida normal.

    `debug` va en las tres a propósito. Django trae su propio context processor
    `debug`, pero solo expone la variable si DEBUG está activo **y** la IP de la
    petición está en INTERNAL_IPS, así que en la página de login no existe y una
    plantilla que haga `{% if not debug %}` la evalúa como falsa. El service
    worker de la Tarea 30 se decide con esa condición: sin esto se registraría
    también en desarrollo, y el §7 del spec avisa de que media tanda se va en
    depurar una versión cacheada.
    """
    return {"nav_entradas": [], "nav_puede_escribir": False, "debug": settings.DEBUG}


def navegacion(request):
    from apps.households.permissions import membresia_actual

    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return _sin_menu()

    try:
        # membresia_actual y no get_membership(user, hogar): la primera ya viene
        # cacheada en la peticion con su household por select_related, asi que
        # esto no cuesta ninguna consulta extra. Preguntar por la membresia otra
        # vez seria una consulta por cada pagina renderizada de la aplicacion, y
        # tests/test_presupuesto_consultas.py la contaria.
        membresia = membresia_actual(request)
    except Exception:
        # Un usuario autenticado sin hogar (invitacion a medias): no hay menu
        # que ensenarle, y reventar aqui romperia hasta la pagina de login.
        return _sin_menu()

    hogar_actual = membresia.household
    puede_escribir = hogar_actual.puede_escribir

    entradas = []
    if _permiso(membresia, "can_view_budget"):
        entradas.append({
            "nombre": "hogar", "url": reverse("budget:overview", args=["household"]),
            "etiqueta": _("Household"), "icono": "home",
        })
        entradas.append({
            "nombre": "personal", "url": reverse("budget:overview", args=["personal"]),
            "etiqueta": _("Personal"), "icono": "persona",
        })
    if _permiso(membresia, "can_add_transactions") and puede_escribir:
        # El [+] del §7.1: la accion mas frecuente, siempre a un toque, y
        # dependiendo SOLO de can_add_transactions. Es el camino del
        # adolescente del §6.2, que hasta el Plan 3 no tenia ninguno.
        entradas.append({
            "nombre": "registrar", "url": reverse("budget:registrar"),
            "etiqueta": _("Add"), "icono": "mas",
        })
    if _permiso(membresia, "can_view_budget"):
        entradas.append({
            "nombre": "metas", "url": reverse("budget:metas", args=["household"]),
            "etiqueta": _("Goals"), "icono": "meta",
        })
    entradas.append({
        "nombre": "ajustes", "url": reverse("households:ajustes"),
        "etiqueta": _("Settings"), "icono": "ajustes",
    })
    return {
        "nav_entradas": entradas,
        "nav_puede_escribir": puede_escribir,
        "debug": settings.DEBUG,
    }

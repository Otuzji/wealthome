"""Lo que toda plantilla necesita saber.

El hogar de la petición lo fija `apps.households.permissions.membresia_actual`
cuando un decorador resuelve el hogar, así que aquí solo se lee: una plantilla
que necesite la moneda del hogar (`{{ importe|money:hogar.currency }}`) no
cuesta una consulta por render.

`navegacion` es la única fuente del menú. Que sean listas de datos y no HTML
repartido por las plantillas es lo que permite que tests/test_navegacion.py las
recorra enteras y afirme, por perfil de permiso, que no falta ni sobra ninguna
pantalla. El Plan 2 enlazaba 1 de 6 porque el menú era prosa.

El menú tiene cuatro piezas, que son las cuatro claves que devuelve:

- `nav_ambitos`: el conmutador Household | Personal de la barra superior. No es
  navegación, es un cambio de ámbito: conserva la pantalla en la que estás.
- `nav_pantallas`: las pestañas del ámbito actual. En móvil, barra inferior; en
  escritorio, fila bajo la barra. Plan y Close NO están: son el ciclo de vida
  del mes y viven como botones dentro de This month.
- `nav_drawer`: lo que abre el avatar. Aquí vive todo lo que era "Settings".
- `nav_fab`: si se pinta el botón flotante de registrar un gasto. Depende SOLO
  de can_add_transactions: es el camino del adolescente del §6.2.

Devuelve las cuatro vacías —y no revienta— en las pantallas sin hogar:
registro, login y aceptar una invitación.
"""

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _

HOGAR = "household"
PERSONAL = "personal"


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
    return {
        "nav_ambitos": [], "nav_pantallas": [], "nav_drawer": [],
        "nav_fab": False, "nav_ambito": None, "nav_hogar": None, "nav_puede_escribir": False,
        "debug": settings.DEBUG,
    }


def _ambito_de(ruta):
    """A qué ámbito pertenece la URL pedida, o None fuera del presupuesto."""
    for ambito in (PERSONAL, HOGAR):
        if ruta.startswith(reverse("budget:overview", args=[ambito])):
            return ambito
    return None


def _pantallas(membresia, ambito):
    """Las pestañas de un ámbito, con los permisos ya aplicados.

    `rutas` son los prefijos de URL que encienden la pestaña. This month lleva
    también Plan y Close: estar planificando el mes ES estar en el mes.
    """
    if not _permiso(membresia, "can_view_budget"):
        return []
    pantallas = [
        {"nombre": "resumen", "vista": "budget:overview", "etiqueta": _("Overview"),
         "icono": "resumen"},
        {"nombre": "mes", "vista": "budget:mes", "etiqueta": _("This month"),
         "icono": "mes",
         "rutas": [reverse("budget:planificar", args=[ambito]),
                   reverse("budget:cerrar", args=[ambito])]},
        {"nombre": "metas", "vista": "budget:metas", "etiqueta": _("Goals"),
         "icono": "meta"},
    ]
    if _permiso(membresia, "can_view_reports"):
        # Bajo can_view_reports y no can_view_budget: Balance es un informe, y
        # un enlace que da 403 al tocarlo seria correcto y grosero (§7).
        pantallas.append({"nombre": "balance", "vista": "budget:balance",
                          "etiqueta": _("Balance"), "icono": "balance"})
    for p in pantallas:
        p["url"] = reverse(p["vista"], args=[ambito])
        p.setdefault("rutas", [])
        p["rutas"].append(p["url"])
    if ambito == PERSONAL:
        # Sin <ambito> en su ruta: la mesada es de un miembro por definicion, y
        # una "mesada del hogar" no significa nada.
        url = reverse("budget:mesada")
        pantallas.append({"nombre": "mesada", "vista": "budget:mesada",
                          "etiqueta": _("Allowance"), "icono": "mesada",
                          "url": url, "rutas": [url]})
    return pantallas


def _encender(pantallas, ruta):
    """Marca `activa` en la pestaña cuyo prefijo coincide, y solo en esa.

    Gana la coincidencia MAS LARGA: /budget/household/ es prefijo de todas las
    demas, y sin esto Overview estaria siempre encendida.
    """
    mejor, largo = None, -1
    for p in pantallas:
        for prefijo in p["rutas"]:
            if ruta.startswith(prefijo) and len(prefijo) > largo:
                mejor, largo = p, len(prefijo)
    for p in pantallas:
        p["activa"] = p is mejor
    return mejor


def _ambitos(membresia, ambito_actual, pantalla_actual):
    """El conmutador. Cada ámbito lleva a la MISMA pantalla en el otro lado, y
    al Overview cuando esa pantalla no existe allí (la mesada) o cuando no
    estamos en el presupuesto."""
    if not _permiso(membresia, "can_view_budget"):
        return []
    vista = "budget:overview"
    if pantalla_actual and pantalla_actual["vista"] != "budget:mesada":
        vista = pantalla_actual["vista"]
    return [
        {"nombre": nombre, "ambito": ambito, "etiqueta": etiqueta,
         "url": reverse(vista, args=[ambito]), "activo": ambito == ambito_actual}
        for nombre, ambito, etiqueta in (("hogar", HOGAR, _("Household")),
                                         ("personal", PERSONAL, _("Personal")))
    ]


def _drawer(membresia):
    """Lo que abre el avatar: tú, tu hogar, y salir. En ese orden."""
    entradas = [{"nombre": "preferencias", "url": reverse("accounts:preferencias"),
                 "etiqueta": _("My preferences"), "grupo": "yo"}]
    if _permiso(membresia, "can_edit_budget"):
        entradas.append({"nombre": "configurar", "url": reverse("budget:configurar"),
                         "etiqueta": _("Budget setup"), "grupo": "hogar"})
    entradas.append({"nombre": "miembros", "url": reverse("households:ajustes"),
                     "etiqueta": _("Members"), "grupo": "hogar"})
    if membresia.role == membresia.ADMIN:
        entradas.append({"nombre": "invitar", "url": reverse("households:invitar"),
                         "etiqueta": _("Invite a member"), "grupo": "hogar"})
    entradas.append({"nombre": "suscripcion", "url": reverse("subscriptions:estado"),
                     "etiqueta": _("Subscription"), "grupo": "hogar"})
    return entradas


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

    ambito = _ambito_de(request.path)
    # Fuera del presupuesto las pestañas siguen siendo las del hogar: es lo que
    # se ve al volver. Pero ninguna esta encendida.
    pantallas = _pantallas(membresia, ambito or HOGAR)
    pantalla_actual = _encender(pantallas, request.path if ambito else "")

    return {
        "nav_ambitos": _ambitos(membresia, ambito, pantalla_actual),
        "nav_pantallas": pantallas,
        "nav_drawer": _drawer(membresia),
        # El [+] del §7.1: la accion mas frecuente, siempre a un toque, y
        # dependiendo SOLO de can_add_transactions. Un hogar expirado lo pierde
        # en vez de dejarlo dar un 403 (§5.2).
        "nav_fab": bool(_permiso(membresia, "can_add_transactions") and puede_escribir),
        "nav_ambito": ambito,
        "nav_hogar": hogar_actual,
        "nav_puede_escribir": puede_escribir,
        "debug": settings.DEBUG,
    }

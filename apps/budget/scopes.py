"""El eje Hogar / Personal (§2.4 y §7.1).

"Household y Personal son la misma vista con un parametro de filtro, no vistas
duplicadas": este modulo es ese parametro, y el unico sitio donde se traduce en
un filtro. Que este solo aqui es lo que impide que la mitad de las pantallas
filtren y la otra mitad se olvide.

El ambito viaja en la RUTA y no en un parametro de consulta ni en la sesion,
porque el service worker cachea por URL: con el ambito fuera de la ruta, la
cache servira la pagina del hogar a quien pidio la personal.
"""

from django.http import Http404
from django.utils.translation import gettext_lazy as _

HOGAR = "household"
PERSONAL = "personal"
AMBITOS = (HOGAR, PERSONAL)

ETIQUETAS = {HOGAR: _("Household"), PERSONAL: _("Personal")}


def validar(ambito):
    """Se llega a estas URLs escribiendolas. Un ambito inventado es un 404."""
    if ambito not in AMBITOS:
        raise Http404(_("That view does not exist."))
    return ambito


def acotar(queryset, ambito, membresia):
    """Filtra al ambito pedido.

    En Personal se filtra por `scope` Y por miembro: "lo personal" de otro no
    es lo personal de este. En Hogar no se filtra por miembro, porque un gasto
    del hogar es de todos.
    """
    if ambito == PERSONAL:
        return queryset.filter(scope=PERSONAL, member=membresia)
    return queryset.filter(scope=HOGAR)


def acotar_por_dueno(queryset, ambito, membresia):
    """Igual, para los modelos que llaman `owner` a lo que Transaction llama
    `member`: BudgetLine y Goal. Dos funciones y no un parametro con el nombre
    del campo: es mas corto de leer y no hay una tercera forma esperando a
    aparecer."""
    if ambito == PERSONAL:
        return queryset.filter(scope=PERSONAL, owner=membresia)
    return queryset.filter(scope=HOGAR)

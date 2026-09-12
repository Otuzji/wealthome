"""El Overview y el Balance, las dos pantallas nuevas del §7.1.

Vacias a proposito en la Tarea 18: existen para que las rutas del eje
Hogar/Personal resuelvan. Las Tareas 19 y 20 las llenan.
"""

from django.shortcuts import render

from apps.households.permissions import requiere_permiso

from .scopes import validar


@requiere_permiso("can_view_budget")
def overview(request, hogar, ambito):
    ambito = validar(ambito)
    return render(request, "budget/overview.html", {"ambito": ambito})


@requiere_permiso("can_view_reports")
def balance(request, hogar, ambito):
    ambito = validar(ambito)
    return render(request, "budget/balance.html", {"ambito": ambito})

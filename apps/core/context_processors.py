"""El hogar de la petición, disponible en toda plantilla.

Lo fija `apps.households.permissions.membresia_actual` cuando un decorador
resuelve el hogar, así que aquí solo se lee: una plantilla que necesite la
moneda del hogar (`{{ importe|money:hogar.currency }}`) no cuesta una
consulta por render.

Devuelve `None` —y no revienta— en las pantallas sin hogar: registro, login
y aceptar una invitación.
"""


def hogar(request):
    return {"hogar": getattr(request, "hogar", None)}

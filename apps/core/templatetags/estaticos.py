import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def estatico(ruta):
    """`{% static %}` con `?v=<mtime>`: cambia el archivo, cambia la URL.

    runserver sirve /static/ con Last-Modified y sin Cache-Control, asi que el
    navegador aplica cache heuristica y tras editar un CSS seguia pintando la
    hoja vieja hasta un Ctrl+F5. Con la version en la URL el navegador (y el
    service worker, que cachea por URL completa) piden la nueva sin mas.
    """
    url = static(ruta)
    archivo = finders.find(ruta)
    if not archivo:
        return url
    return f"{url}?v={int(os.path.getmtime(archivo))}"

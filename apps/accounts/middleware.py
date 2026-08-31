from django.utils import translation


class PerfilLocaleMiddleware:
    """Activa el idioma guardado en el perfil del usuario.

    Va DESPUÉS de LocaleMiddleware y de AuthenticationMiddleware: el perfil
    manda sobre la cabecera Accept-Language del navegador (spec §8).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        perfil = getattr(getattr(request, "user", None), "profile", None)
        if perfil is not None:
            translation.activate(perfil.language)
            request.LANGUAGE_CODE = perfil.language

        # Deliberadamente NO hay translation.deactivate() aquí. Esta
        # middleware es la más interna (va al final de MIDDLEWARE), así que
        # el código posterior a get_response corre ANTES de que el control
        # vuelva a LocaleMiddleware.process_response, que lee
        # translation.get_language() para fijar el header Content-Language.
        # Desactivar aquí corrompía ese header (siempre caía al idioma por
        # defecto). Tampoco hace falta desactivar por otra razón: no hay fuga
        # de idioma entre peticiones que evitar, porque
        # LocaleMiddleware.process_request ya activa el idioma correcto al
        # principio de cada petición.
        return self.get_response(request)

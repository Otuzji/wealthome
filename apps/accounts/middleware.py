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
        respuesta = self.get_response(request)
        translation.deactivate()
        return respuesta

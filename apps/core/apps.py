from django.apps import AppConfig
from django.conf import settings
from django.utils.autoreload import autoreload_started


def _vigilar_env(sender, **kwargs):
    """El autoreloader de runserver solo mira .py y plantillas; `.env` se lee
    una vez al arrancar. Sin esto, cambiar EMAIL_* o cualquier otra variable
    parecia no hacer nada hasta que uno se acordaba de reiniciar el servidor."""
    sender.watch_dir(settings.BASE_DIR, ".env")


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self):
        autoreload_started.connect(_vigilar_env)

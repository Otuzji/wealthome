"""Cierra los meses vencidos de todos los hogares.

§2.3: el disparador normal es entrar a la aplicación. Este comando existe
para que el Plan 3 pueda enchufar un cron o un correo de aviso sin extraer la
lógica de dentro de una vista. Hoy no lo llama nadie, y eso es correcto.
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _

from apps.budget import services
from apps.households.models import Household


class Command(BaseCommand):
    help = _("Closes the overdue months of every household.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--hoy", help=_("Date in YYYY-MM-DD format, for testing.")
        )

    def handle(self, *args, **opciones):
        hoy = date.fromisoformat(opciones["hoy"]) if opciones.get("hoy") else None
        total = 0
        for hogar in Household.objects.all():
            cerrados = services.cerrar_vencidos(hogar, hoy)
            total += len(cerrados)
            for cierre in cerrados:
                self.stdout.write(str(_("%(hogar)s: closed %(mes)s")) % {
                    "hogar": hogar, "mes": cierre.budget_month,
                })
        self.stdout.write(
            self.style.SUCCESS(str(_("%(total)s months closed.")) % {"total": total})
        )

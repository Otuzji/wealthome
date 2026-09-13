"""Da suscripcion a los hogares que ya existen.

trial_ends_at = HOY + 14 dias, no created_at + 14. Una migracion no debe dejar
a nadie fuera retroactivamente: con la fecha de creacion, cada hogar existente
quedaria expirado en el instante de aplicarla, y el primer efecto visible del
Plan 3 seria que la aplicacion deja de aceptar escrituras.
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def _dar_suscripcion(apps, schema_editor):
    Household = apps.get_model("households", "Household")
    Subscription = apps.get_model("subscriptions", "Subscription")

    fin = timezone.now() + timedelta(days=14)
    for hogar in Household.objects.filter(subscription__isnull=True):
        Subscription.objects.create(
            household=hogar, status="trialing", trial_ends_at=fin, currency="CAD",
        )


def _quitarlas(apps, schema_editor):
    apps.get_model("subscriptions", "Subscription").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0001_initial"),
        ("households", "0003_invitation"),
    ]

    operations = [migrations.RunPython(_dar_suscripcion, _quitarlas)]

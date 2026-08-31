from django.db import models

from apps.households.models import Household
from apps.households.scoping import HouseholdScoped


class Nota(HouseholdScoped):
    """Modelo de prueba: existe solo para ejercitar el aislamiento por hogar.

    Redefine el FK heredado de HouseholdScoped con db_constraint=False. La app
    "tests" no tiene migraciones, así que Django crea su tabla vía
    run_syncdb — y run_syncdb corre ANTES de aplicar las migraciones de las
    apps migradas (ver django.core.management.commands.migrate: la fase
    "Synchronize unmigrated apps" precede a "Running migrations"). Con una
    restricción de clave foránea real, esa tabla intentaría referenciar
    households_household antes de que exista y la creación de la base de
    datos de pruebas fallaría por completo. Sin la restricción a nivel de
    base de datos el comportamiento a nivel de ORM que estas pruebas
    ejercitan (household_id, for_user, for_household) es idéntico; ningún
    modelo de producción usa este atajo.
    """

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="notas", db_constraint=False
    )
    texto = models.CharField(max_length=100)

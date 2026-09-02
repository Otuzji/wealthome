from django.db import models

from apps.households.models import Household
from apps.households.scoping import HouseholdScoped


class Etiqueta(HouseholdScoped):
    """Modelo de prueba: el destino de una clave foránea con ámbito de hogar.

    Existe para ejercitar la barrera de formularios: un ModelForm sobre Nota
    con el campo `etiqueta` es exactamente la fuga que describe el traspaso —
    un <select> con los nombres de todas las familias. Sin un segundo modelo
    con hogar, esa fuga no se puede probar.

    Redefine el FK a Household con db_constraint=False por la misma razón que
    Nota; ver su docstring.
    """

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="etiquetas", db_constraint=False
    )
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre


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
    ejercitan (household_id, for_household) es idéntico; ningún modelo de
    producción usa este atajo.
    """

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="notas", db_constraint=False
    )
    etiqueta = models.ForeignKey(
        Etiqueta, on_delete=models.CASCADE, related_name="notas", null=True, blank=True,
        db_constraint=False,
    )
    texto = models.CharField(max_length=100)

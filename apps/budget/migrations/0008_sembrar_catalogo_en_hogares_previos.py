"""Siembra el arbol de categorias en los hogares creados antes del Plan 2.

seeds.sembrar() solo corre dentro de households.services.crear_hogar, asi que
un hogar anterior no tiene arbol y hace estallar _categoria_de_ingreso con su
LookupError en cuanto alguien mire un mes.

Se usa ARBOL directamente y no seeds.sembrar(): sembrar() escribe con el modelo
real, y una migracion tiene que escribir con el historico. La forma del arbol
puede cambiar despues de esta migracion; lo que se siembre aqui sera el arbol
de entonces, y eso es correcto para un hogar que hoy no tiene ninguno.
"""

from django.db import migrations

from apps.budget.seeds import ARBOL


def _sembrar_los_que_falten(apps, schema_editor):
    Household = apps.get_model("households", "Household")
    Category = apps.get_model("budget", "Category")

    for hogar in Household.objects.all():
        if Category.objects.filter(household=hogar).exists():
            continue
        creadas = {}
        for slug, _etiqueta, padre, kind in ARBOL:
            creadas[slug] = Category.objects.create(
                household=hogar, slug=slug, is_system=True,
                kind=kind, parent=creadas.get(padre), name="",
            )


def _no_se_deshace(apps, schema_editor):
    """Borrar categorias podria llevarse por delante reglas que las usan."""


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0007_un_reparto_por_regla_y_miembro"),
        ("households", "0003_invitation"),
    ]

    operations = [
        migrations.RunPython(_sembrar_los_que_falten, _no_se_deshace),
    ]

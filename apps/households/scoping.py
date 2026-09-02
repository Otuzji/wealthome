"""El aislamiento entre hogares, como barrera y no como convención.

Spec §6.1: *"un manager por defecto en los modelos con ámbito de hogar que
exige el hogar como parámetro"*. Aquí está ese manager. Su forma —lanzar
desde `get_queryset()`— tiene consecuencias que conviene conocer antes de
tocar este archivo, porque son deliberadas:

- `Modelo.objects.all()`, `.filter()`, `.get()` lanzan `RuntimeError`. La
  única entrada es `Modelo.objects.for_household(hogar)`.
- `get_object_or_404(Modelo, pk=pk)` **también lanza**, porque
  `django.shortcuts` resuelve el modelo por `_default_manager`. Era el punto
  ciego más peligroso de la Fase 1: no escribe `.objects.` en ninguna parte,
  así que ninguna guardia de texto podía verlo.
- Declarar un `ModelForm` con clave foránea a un modelo con hogar lanza **al
  importar el módulo**, porque `ForeignKey.formfield()` evalúa
  `_default_manager` de forma ansiosa. Es la fuga del `<select>` con los
  datos de todas las familias, cerrada antes de que el proceso arranque.
  La forma soportada es `apps.households.scoped_forms.HouseholdScopedModelForm`.
- Los **accesores inversos** (`hogar.gastos.all()`, `mes.lineas.all()`) sí
  funcionan: la instancia dueña ya ES el ámbito, así que están acotados por
  construcción. Django los construye subclasando este manager y fijando
  `self.instance`, que es el discriminador que usa `get_queryset()`.
- El ORM por dentro —borrado en cascada, `refresh_from_db`, los descriptores
  de clave foránea— usa `_base_manager`, y `base_manager_name` lo manda a
  `unscoped`. Sin eso, borrar un hogar reventaría desde las tripas de Django.

`unscoped` es la salida de emergencia explícita, para migraciones de datos,
el admin y los scripts de mantenimiento. Que haya que escribirla es el punto:
se ve en la revisión.
"""

from django.db import models

from .models import Household

MENSAJE = (
    "{modelo} tiene ámbito de hogar: no se puede consultar sin decir de qué "
    "hogar. Usa {modelo}.objects.for_household(hogar) — el hogar de la "
    "petición lo resuelve apps.households.permissions.hogar_actual — o, si "
    "de verdad necesitas todas las familias (migración de datos, admin, "
    "mantenimiento), {modelo}.unscoped."
)


class HouseholdScopedQuerySet(models.QuerySet):
    def for_household(self, household):
        return self.filter(household=household)


class HouseholdScopedManager(models.Manager.from_queryset(HouseholdScopedQuerySet)):
    def get_queryset(self):
        if getattr(self, "instance", None) is not None:
            # Accesor inverso (hogar.notas, mes.lineas): Django construye ese
            # manager subclasando esta clase y fija self.instance. Ya viene
            # acotado por su dueño, así que dejarlo pasar no abre nada.
            return super().get_queryset()
        raise RuntimeError(MENSAJE.format(modelo=self.model.__name__))

    def for_household(self, household):
        # No pasa por get_queryset() a propósito: es la puerta, no una
        # excepción a la puerta.
        return super().get_queryset().filter(household=household)


class HouseholdScoped(models.Model):
    """Todo dato que pertenece a un hogar hereda de aquí.

    Una subclase que declare su propia `Meta` debe heredarla
    (`class Meta(HouseholdScoped.Meta):`) o repetir `base_manager_name`;
    perderlo rompe el ORM por dentro de una forma difícil de diagnosticar.
    `tests/test_scoping.py::test_todo_modelo_con_hogar_conserva_base_manager_name`
    nombra al infractor.
    """

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_set"
    )

    # El orden importa: el primero declarado es _default_manager, y que el
    # estricto sea el manager por defecto es lo que cierra get_object_or_404
    # y los ModelForm ingenuos.
    objects = HouseholdScopedManager()
    unscoped = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "unscoped"

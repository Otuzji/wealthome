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

import contextvars
from contextlib import contextmanager

from django.db import models

from .models import Household

# Ver _validando_unicidad() más abajo: por diseño solo Model.full_clean() (por
# validate_constraints() y validate_unique()) debe poner esto en True, y solo
# mientras dura esa llamada.
_VALIDANDO_UNICIDAD = contextvars.ContextVar("validando_unicidad", default=False)


@contextmanager
def _validando_unicidad():
    """Destraba el manager estricto solo mientras Django valida sus propias
    restricciones de unicidad — nada más.

    Privado a propósito: existe únicamente para que
    `HouseholdScoped.validate_constraints()` y `.validate_unique()` envuelvan
    su `super()`. No es una puerta de conveniencia para código de vistas o
    scripts — envolver una consulta ordinaria en este context manager
    ensancharía esa consulta a través de todos los hogares, sin lanzar nada
    que lo delate. Si hace falta ver todas las familias fuera de la
    validación de Django, la puerta es `Modelo.unscoped`, no esto.

    `Model.validate_constraints()` (`UniqueConstraint.validate()`) y
    `Model.validate_unique()` (`_perform_unique_checks()`) resuelven su
    queryset con `model._default_manager`, que en un modelo con hogar es
    HouseholdScopedManager: por diseño lanza RuntimeError salvo por accesor
    inverso o `for_household()`. Sin esta puerta, `full_clean()` —el candado
    que el resto del plan pone justo antes de `save()` para atajar escrituras
    entre hogares— reventaría con RuntimeError en cualquier modelo con hogar
    que tenga un UniqueConstraint, en vez de devolver como mucho una
    ValidationError.

    Que esto sea seguro depende de que cada restricción de unicidad de un
    modelo con hogar lleve `household` entre sus propios campos (p. ej.
    `UniqueConstraint(fields=["household", "slug"])`): así el queryset sin
    acotar que arma Django ya viene filtrado al hogar de la instancia, y
    destrabar el manager aquí no ensancha lo que la restricción ve, solo
    permite que Django la consulte. Esa condición no la impone el tipo —
    `test_toda_unique_constraint_de_un_modelo_con_hogar_incluye_household` en
    tests/test_scoping.py es la que la vigila.

    Se implementa con un ContextVar —no cambiando `_default_manager` ni
    `_meta.default_manager_name` del modelo— a propósito: mutar el manager,
    aunque fuera brevemente y se restaurase después, es una mutación global
    del modelo entero, y con vistas async o hilos concurrentes dejaría la
    barrera abajo para la petición de otra familia mientras esta valida. Un
    ContextVar es propio de cada hilo y de cada tarea async, así que la
    relajación no puede escaparse de esta llamada — y el `finally` la cierra
    incluso si la validación lanza, para que una excepción a mitad de
    full_clean() no deje el candado abierto para la siguiente consulta de
    esta misma petición.
    """
    token = _VALIDANDO_UNICIDAD.set(True)
    try:
        yield
    finally:
        _VALIDANDO_UNICIDAD.reset(token)


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
        if _VALIDANDO_UNICIDAD.get():
            # full_clean() del propio Django, validando una restricción de
            # unicidad que ya lleva household entre sus campos. Ver
            # _validando_unicidad().
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

    def validate_constraints(self, exclude=None):
        # Ver _validando_unicidad(): sin esto, cualquier UniqueConstraint de
        # un modelo con hogar hace que full_clean() lance RuntimeError en
        # vez de, como mucho, ValidationError.
        with _validando_unicidad():
            super().validate_constraints(exclude=exclude)

    def validate_unique(self, exclude=None):
        # Mismo motivo que validate_constraints(): _perform_unique_checks()
        # llega a _default_manager por el mismo camino, para unique=True o
        # unique_together en vez de un UniqueConstraint explícito.
        with _validando_unicidad():
            super().validate_unique(exclude=exclude)

    def save(self, *args, **kwargs):
        """Rechaza la escritura si la suscripcion del hogar vencio (§5.2).

        Es la capa que no se puede rodear: cubre el comando de gestion, los
        scripts y cualquier camino que no pase por una vista. La otra capa esta
        en apps/households/permissions.py::_decorador.

        Alcance real, para que nadie lea aqui mas de lo que hay: cubre todo
        `save()`, incluido con update_fields. NO cubre `queryset.update()` ni
        `bulk_create()`, que no llaman a save() — exactamente el mismo punto
        ciego que EscrituraAcotadaAlMes documenta en su docstring. Quedan
        prohibidos por convencion sobre estos modelos.
        """
        from apps.subscriptions.models import SuscripcionVencidaError

        if self.household_id and not self.household.puede_escribir:
            raise SuscripcionVencidaError(
                f"La suscripcion del hogar {self.household_id} vencio: solo lectura."
            )
        super().save(*args, **kwargs)

from django.contrib import admin

from .models import Household, Membership
from .scoped_forms import campo_de_relacion_acotado
from .scoping import HouseholdScoped


class HouseholdScopedAdmin(admin.ModelAdmin):
    """Base del admin para los modelos con ámbito de hogar.

    El admin es cross-hogar a propósito —lo usa el superusuario para
    mantenimiento, no una familia—, así que entra por `unscoped`. Que ese
    permiso viva en una sola clase, y no repartido por cada `ModelAdmin`, es
    lo que lo mantiene auditable.

    Todo `ModelAdmin` del Plan 2 sobre un modelo con hogar debe heredar de
    aquí; uno normal lanza `RuntimeError` al listar y al construir su
    formulario.
    """

    def get_queryset(self, request):
        return self.model.unscoped.get_queryset()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        return self._campo_de_relacion(db_field, super().formfield_for_foreignkey, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        return self._campo_de_relacion(db_field, super().formfield_for_manytomany, request, **kwargs)

    def _campo_de_relacion(self, db_field, delegar, request, **kwargs):
        relacionado = db_field.remote_field.model
        if isinstance(relacionado, type) and issubclass(relacionado, HouseholdScoped):
            # No se delega en super(): acaba en db_field.formfield(), que
            # evalúa _default_manager de forma ansiosa y lanza.
            kwargs.setdefault("queryset", relacionado.unscoped.get_queryset())
            return campo_de_relacion_acotado(db_field, **kwargs)
        return delegar(db_field, request, **kwargs)


admin.site.register(Household)
admin.site.register(Membership)

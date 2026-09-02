"""La base de formularios para modelos con ámbito de hogar.

Un `ModelForm` con clave foránea a un modelo con hogar renderiza por defecto
todas las filas de la tabla en un `<select>`: los nombres de categoría, de
comercio o de meta de **todas** las familias, en el HTML, sin que ninguna
vista contenga `.objects.`. El Plan 2 está lleno de formularios así.

El manager estricto (`apps.households.scoping`) hace que ese formulario no
llegue a existir —`ForeignKey.formfield()` evalúa `_default_manager` de forma
ansiosa y lanza al importar el módulo—, y esta es la forma soportada de
escribirlo:

    class GastoForm(HouseholdScopedModelForm):
        class Meta:
            model = ExpenseRule
            fields = ["category", "name", "amount"]

    form = GastoForm(request.POST or None, household=hogar)

El hogar es un argumento **obligatorio y de solo palabra clave**: olvidarlo es
un `TypeError` al instanciar, no un desplegable con los datos de otra familia.
"""

from django import forms
from django.utils.text import capfirst

from .scoping import HouseholdScoped


def campo_de_relacion_acotado(db_field, **kwargs):
    """El campo de formulario para una clave foránea a un modelo con hogar.

    Construye el `ModelChoiceField` a mano en vez de delegar en
    `db_field.formfield()`, porque ese método evalúa
    `remote_field.model._default_manager.using(...)` **antes** de mezclar los
    kwargs — pasarle un `queryset` no evita que el manager estricto lance.

    El queryset arranca vacío. Lo llena `HouseholdScopedModelForm.__init__`
    con el hogar de la petición; si algo se saltara ese paso, el desplegable
    saldría vacío en vez de salir con los datos de todas las familias.
    """
    modelo = db_field.remote_field.model
    clase = forms.ModelMultipleChoiceField if db_field.many_to_many else forms.ModelChoiceField
    opciones = {
        "queryset": modelo.unscoped.none(),
        "required": not db_field.blank,
        "label": capfirst(db_field.verbose_name),
        "help_text": db_field.help_text,
    }
    if not db_field.many_to_many:
        opciones["to_field_name"] = db_field.remote_field.field_name
    opciones.update(kwargs)
    return clase(**opciones)


def _formfield_callback(db_field, **kwargs):
    relacionado = getattr(db_field.remote_field, "model", None)
    if isinstance(relacionado, type) and issubclass(relacionado, HouseholdScoped):
        return campo_de_relacion_acotado(db_field, **kwargs)
    return db_field.formfield(**kwargs)


class _MetaclaseAcotada(forms.models.ModelFormMetaclass):
    """Inyecta el `formfield_callback` en la `Meta` de cada subclase.

    Django lee las opciones con `ModelFormOptions(getattr(new_class, "Meta"))`,
    y la `Meta` que declara la subclase eclipsa la de la clase base — así que
    heredar el callback "por herencia normal" no funciona: obligaría a cada
    formulario del Plan 2 a escribir `class Meta(HouseholdScopedModelForm.Meta)`
    y a acordarse de ello. Aquí se deriva una Meta que lo lleva, sin mutar la
    que escribió quien usa la clase.

    Si algún día esto dejara de funcionar, el fallo es ruidoso y no silencioso:
    la clase no llega a construirse, porque el manager estricto lanza al
    declararla.
    """

    def __new__(mcs, name, bases, attrs):
        meta = attrs.get("Meta")
        if meta is not None and not hasattr(meta, "formfield_callback"):
            attrs["Meta"] = type(
                "Meta", (meta,), {"formfield_callback": staticmethod(_formfield_callback)}
            )
        return super().__new__(mcs, name, bases, attrs)


class HouseholdScopedModelForm(forms.ModelForm, metaclass=_MetaclaseAcotada):
    def __init__(self, *args, household, **kwargs):
        super().__init__(*args, **kwargs)
        self.household = household
        for campo in self.fields.values():
            queryset = getattr(campo, "queryset", None)
            if queryset is not None and issubclass(queryset.model, HouseholdScoped):
                # Acota el render Y la validación. Filtrar solo el render sería
                # cosmético: un POST con el id de una fila ajena no pasa por el
                # navegador.
                campo.queryset = queryset.model.objects.for_household(household)

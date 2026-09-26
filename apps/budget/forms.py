"""Los formularios de alta del presupuesto.

Todos heredan de `HouseholdScopedModelForm`: el hogar es obligatorio y de solo
palabra clave, y acota tanto el render como la validación. Un `<select>` con
las categorías de otra familia no llega a existir.
"""

from datetime import date
from decimal import Decimal

from django import forms
from django.db.models import Q
from django.utils.formats import date_format
from django.utils import timezone
from django.utils.html import escapejs
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.budget.engine import goals as motor_goals
from apps.budget.engine import income as motor_income
from apps.budget.engine.merchants import normalizar
from apps.budget.models.catalog import EXPENSE, HOUSEHOLD, INCOME, PERSONAL
from apps.households.scoped_forms import HouseholdScopedModelForm

from .models import (
    ASSET,
    GRUPOS,
    LIABILITY,
    BalanceItem,
    AllocationRule,
    BudgetLine,
    Category,
    ExpenseRule,
    Goal,
    GoalContribution,
    IncomeSource,
    Merchant,
    Transaction,
)


def _js(valor):
    """Un valor de formulario metido dentro de una cadena JavaScript, a salvo.

    Los `x_data` de este modulo se pintan con `{{ form.x_data|safe }}` dentro de
    `x-data="..."`, y `|safe` significa que NADA se escapa. El valor que
    interpolan es `self["campo"].value()`, que en un formulario ENLAZADO es el
    dato crudo que llego en el POST — sin pasar por la validacion, porque el
    formulario se vuelve a pintar precisamente cuando es invalido. Sin escapar,
    un `amount_type` con un `">` cerraba el atributo y el `<form>` y metia
    etiquetas propias en la pagina: XSS reflejado.

    `escapejs` es el escape correcto para este sitio y no `escape`: convierte
    las comillas, los signos de mayor y menor y la barra invertida en secuencias
    `\\uXXXX`, que son validas dentro de una cadena de JavaScript Y no pueden
    salirse de un atributo HTML. `escape` habria metido `&quot;` literal, que
    Alpine leeria como parte del valor.
    """
    return escapejs(valor or "")


class CategoryForm(HouseholdScopedModelForm):
    """Alta de una categoría propia del hogar.

    El modelo exige `slug` (es la clave de las sembradas y de la unicidad por
    hogar) pero quien añade "Clases de piano" no tiene por qué saber qué es un
    slug: se deriva del nombre. Y `name`, opcional en el modelo porque las del
    sistema se traducen desde el slug, aquí es obligatorio — sin nombre no hay
    de dónde sacarlo.
    """

    class Meta:
        model = Category
        fields = ["name", "parent", "kind"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True

    def clean(self):
        datos = super().clean()
        nombre = datos.get("name")
        if nombre and not self.instance.slug:
            # `name` admite 80 y `slug` 50: se recorta dejando sitio al sufijo.
            self.instance.slug = self._slug_libre(slugify(nombre)[:45] or "categoria")
        return datos

    def _slug_libre(self, base):
        """`rent` ya existe sembrada; "Rent" del hogar pasa a `rent-2`, `rent-3`…"""
        ocupados = set(
            Category.objects.for_household(self.household)
            .filter(slug__startswith=base)
            .values_list("slug", flat=True)
        )
        if base not in ocupados:
            return base
        n = 2
        while f"{base}-{n}" in ocupados:
            n += 1
        return f"{base}-{n}"


class IncomeSourceForm(HouseholdScopedModelForm):
    """Ensena solo los importes del modo elegido en "How much".

    Con `amount`, `amount_min` y `amount_max` siempre a la vista nadie sabia
    cual contaba, y un ingreso `estimated` llego a guardarse con el rango
    relleno y el importe vacio. Cada importe declara sus modos en
    `field.x_show`; la plantilla generica los envuelve en ese `x-show` de Alpine
    y el <select> del modo lleva `x-model`. Y lo que no pertenece al modo se
    vacia en `clean()`: lo que el usuario no ve no puede quedarse guardado.
    """

    # Que importes usa cada modo. Es la misma tabla que engine.income lee.
    IMPORTES_POR_MODO = {
        "amount": (motor_income.FIXED, motor_income.ESTIMATED),
        "amount_min": (motor_income.RANGE,),
        "amount_max": (motor_income.RANGE,),
    }

    class Meta:
        model = IncomeSource
        fields = [
            "owner", "name", "source_type", "amount_type",
            "amount", "amount_min", "amount_max",
            "periodicity", "effective_from", "effective_to", "scope",
        ]
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
            "amount_type": forms.Select(attrs={"x-model": "modo"}),
        }
        help_texts = {
            "amount": _("Per payment, not per month."),
            "amount_min": _("Per payment. The budget counts this minimum; anything above shows up as surplus."),
            "periodicity": _("The month adds up the payments that fall in it."),
            "effective_from": _("The date of the first payment: weekly and two-week incomes are counted from here."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `owner` es una Membership, que no hereda de HouseholdScoped, así que
        # la base no lo acota: hay que hacerlo aquí o el <select> traería los
        # miembros de todas las familias.
        self.fields["owner"].queryset = self.household.active_memberships()
        for nombre, modos in self.IMPORTES_POR_MODO.items():
            # La expresion de Alpine ya hecha: la plantilla no sabe de modos.
            self.fields[nombre].x_show = f"{list(modos)!r}.includes(modo)"
        # El estado inicial de Alpine: el modo guardado al editar, ninguno al
        # crear (los tres importes escondidos hasta elegir uno).
        self.x_data = "{ modo: '%s' }" % _js(self["amount_type"].value())

    def clean(self):
        datos = super().clean()
        modo = datos.get("amount_type")
        for nombre, modos in self.IMPORTES_POR_MODO.items():
            if modo not in modos:
                datos[nombre] = None
        return datos


class ExpenseRuleForm(HouseholdScopedModelForm):
    class Meta:
        model = ExpenseRule
        fields = [
            "category", "name", "amount", "periodicity",
            "effective_from", "effective_to", "is_essential", "owner", "scope",
        ]
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = self.household.active_memberships()
        self.fields["owner"].required = False


class AllocationRuleForm(HouseholdScopedModelForm):
    class Meta:
        model = AllocationRule
        fields = [
            "order", "target_type", "target_goal", "target_category",
            "method", "amount", "percentage", "split", "is_active",
        ]


class TransactionForm(HouseholdScopedModelForm):
    """`member` y `budget_month` NO son campos: salen de la petición y del
    ciclo del mes. Si `member` lo fuera, cualquiera podría registrar gastos a
    nombre de otro.

    La pregunta principal es "What is it": una linea del plan del mes (el
    alquiler del 1, el sueldo del 15) o "Something not planned". Con una linea,
    la categoria y el income source salen de ella —a quien paga el alquiler no
    le dicen nada—; sin linea, se piden categoria y nombre y la vista crea una
    partida puntual ya pagada, para que el plan refleje todo lo que salio.

    `merchant` tampoco es un desplegable: nadie da de alta un comercio antes
    de comprar en él. Se teclea el nombre tal como aparece en el recibo y
    `Merchant.normalized_name` decide si es uno que ya existe — que es
    exactamente para lo que existe engine/merchants.py. Un `<select>` de
    comercios estaría vacío el primer día y sería inservible el centésimo.

    `kind` parte el formulario en dos: el de gasto y el de ingreso. Cada uno
    lista solo las lineas y las categorias de su tipo —en el queryset, no solo
    en las opciones: un POST con el id de una linea del otro tipo no pasa por
    el navegador—, y el de ingreso no pregunta donde ni con que se pago.
    """

    name = forms.CharField(
        label=_("Name"), max_length=200, required=False,
        help_text=_("How it will show in the plan. Empty: the store, or the category."),
    )
    merchant_name = forms.CharField(
        label=_("Where"), max_length=120, required=False,
        help_text=_("Type it as it appears on the receipt."),
    )

    # Los declarados (name, merchant_name) irian al final sin esto.
    field_order = ["budget_line", "category", "name", "merchant_name", "amount",
                   "date", "payment_method", "scope", "note"]

    class Meta:
        model = Transaction
        fields = ["budget_line", "category", "name", "amount", "date",
                  "payment_method", "scope", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "budget_line": forms.Select(attrs={"x-model": "linea", "@change": "rellenar"}),
            "amount": forms.NumberInput(attrs={"x-ref": "importe", "step": "0.01"}),
        }
        labels = {"budget_line": _("What is it")}

    def __init__(self, *args, lineas=None, kind=EXPENSE, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        lineas = [l for l in (lineas if lineas is not None else []) if l.kind == kind]
        campo = self.fields["budget_line"]
        campo.required = False
        campo.queryset = BudgetLine.objects.for_household(self.household).filter(
            pk__in=[l.pk for l in lineas]
        )
        campo.choices = self._opciones(lineas)
        self.fields["category"].queryset = self.fields["category"].queryset.filter(kind=kind)
        if kind == INCOME:
            del self.fields["merchant_name"], self.fields["payment_method"]
            self.fields["name"].help_text = _("How it will show in the plan. Empty: the category.")
        # Categoria y nombre solo cuando no hay linea: Alpine los esconde y
        # clean() los exige.
        self.fields["category"].required = False
        for nombre in ("category", "name"):
            self.fields[nombre].x_show = "linea === ''"
        # Al elegir una linea, el importe se rellena con lo que le falta — si el
        # campo esta vacio: lo tecleado no se pisa.
        restantes = ", ".join(f"'{l.pk}': '{l.restante}'" for l in lineas)
        self.x_data = (
            "{ linea: '%s', restantes: {%s}, "
            "rellenar() { const r = this.restantes[this.linea]; "
            "if (r && !this.$refs.importe.value) this.$refs.importe.value = r; } }"
            # `restantes` no se escapa porque no lo escribe nadie: son pk
            # enteros e importes Decimal. `budget_line` si llega del POST.
            % (_js(self["budget_line"].value()), restantes)
        )

    @staticmethod
    def _opciones(lineas):
        """Lo pendiente primero: es lo que se viene a registrar. Lo ya pagado
        queda al final, marcado."""
        ordenadas = sorted(lineas, key=lambda l: (l.estado == BudgetLine.PAGADA,
                                                   l.due_date or date.max, l.pk))
        return [("", _("Something not planned"))] + [
            (linea.pk, _etiqueta_de_linea(linea)) for linea in ordenadas
        ]

    def clean(self):
        datos = super().clean()
        linea = datos.get("budget_line")
        if linea is not None:
            datos["category"] = linea.category
        elif not datos.get("category"):
            self.add_error("category", _("Pick a category for something that was not planned."))
        return datos

    def nombre_de_la_partida(self):
        """El nombre de la partida puntual: lo tecleado, o el comercio, o la categoria."""
        return (
            self.cleaned_data.get("name", "").strip()
            or self.cleaned_data.get("merchant_name", "").strip()
            or self.cleaned_data["category"].etiqueta()
        )

    def comercio(self):
        """El comercio tecleado, reutilizando el que ya exista en el hogar."""
        nombre = self.cleaned_data.get("merchant_name", "").strip()
        if not nombre:
            return None
        normalizado = normalizar(nombre)
        existente = Merchant.objects.for_household(self.household).filter(
            normalized_name=normalizado
        ).first()
        if existente is not None:
            return existente
        comercio = Merchant(household=self.household, name=nombre)
        comercio.save()
        return comercio


def _etiqueta_de_linea(linea):
    """Alquiler · Oct 1 · $1,750.00 · pending"""
    from apps.core.templatetags.money import format_money

    partes = [linea.nombre]
    if linea.due_date:
        partes.append(date_format(linea.due_date, "M j"))
    partes.append(format_money(linea.planned_amount, currency=linea.household.currency))
    partes.append(str(ESTADO_CORTO[linea.estado]))
    return " · ".join(partes)


ESTADO_CORTO = {
    BudgetLine.PENDIENTE: _("pending"),
    BudgetLine.PARCIAL: _("partial"),
    BudgetLine.PAGADA: _("paid"),
}


class GoalForm(HouseholdScopedModelForm):
    """Ensena solo los campos del modo elegido en "How to reach it", como
    IncomeSourceForm con sus importes: un fondo abierto no tiene objetivo ni
    fecha, y verlos vacios confunde. Lo que no pertenece al modo se vacia en
    `clean()`: lo que el usuario no ve no puede quedarse guardado."""

    CAMPOS_POR_MODO = {
        "target_amount": (motor_goals.BY_TARGET_DATE, motor_goals.BY_MONTHLY_AMOUNT),
        "target_date": (motor_goals.BY_TARGET_DATE,),
        "monthly_amount": (motor_goals.BY_MONTHLY_AMOUNT, motor_goals.OPEN_FUND),
    }

    class Meta:
        model = Goal
        fields = ["name", "scope", "owner", "contribution_mode",
                  "target_amount", "target_date", "monthly_amount"]
        widgets = {
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "contribution_mode": forms.Select(attrs={"x-model": "modo"}),
        }
        help_texts = {
            "contribution_mode": _("An open fund has no target: just a balance you add to."),
            "monthly_amount": _("For an open fund it is optional: what you mean to put in each month."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = self.household.active_memberships()
        self.fields["owner"].required = False
        for nombre, modos in self.CAMPOS_POR_MODO.items():
            self.fields[nombre].x_show = f"{list(modos)!r}.includes(modo)"
        self.x_data = "{ modo: '%s' }" % _js(self["contribution_mode"].value())
        # Con aportes, el ambito se queda: un aporte a una meta del hogar lo
        # hizo cualquiera, y el de una personal tiene que ser de su dueno.
        # Cambiarlo dejaria aportes que no cuadran con la meta.
        if self.instance.pk and self.instance.contributions.exists():
            self.fields["scope"].disabled = True
            self.fields["owner"].disabled = True

    def clean(self):
        datos = super().clean()
        modo = datos.get("contribution_mode")
        for nombre, modos in self.CAMPOS_POR_MODO.items():
            if modo not in modos:
                datos[nombre] = None
        return datos


class GoalContributionForm(HouseholdScopedModelForm):
    """`member` y `budget_month` NO son campos: salen de la peticion y de la
    fecha, como en TransactionForm. `note` es de donde vino: un aporte a mano
    es dinero de fuera del presupuesto."""

    class Meta:
        model = GoalContribution
        fields = ["goal", "amount", "date", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}
        labels = {"note": _("Where it came from")}

    def __init__(self, *args, membresia, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo a lo que se puede aportar: las metas activas del hogar y las
        # personales propias. Acota el render Y la validacion. Al editar, la
        # meta del aporte entra aunque ya este alcanzada: corregir un aporte
        # no es aportar.
        visibles = Q(scope=HOUSEHOLD) | Q(scope=PERSONAL, owner=membresia)
        activas = Q(status=Goal.ACTIVE)
        if self.instance.pk:
            activas |= Q(pk=self.instance.goal_id)
        self.fields["goal"].queryset = (
            Goal.objects.for_household(self.household).filter(visibles & activas)
        )

    def clean_date(self):
        fecha = self.cleaned_data["date"]
        if fecha > timezone.localdate():
            raise forms.ValidationError(_("A contribution cannot be dated in the future."))
        return fecha

    def clean_amount(self):
        importe = self.cleaned_data["amount"]
        if importe is not None and importe <= 0:
            raise forms.ValidationError(_("Put in more than zero."))
        return importe


class BudgetLineForm(HouseholdScopedModelForm):
    """Las partidas excepcionales del paso 2 del §4.5.6.

    Sin este formulario, `is_exceptional` era un campo que nadie podia poner:
    materializar solo escribe lineas nacidas de una regla. Una linea sin
    source_income ni source_expense_rule ES una linea excepcional (§5.3 del
    diseno del Plan 2), asi que el formulario no ofrece esos dos campos y la
    vista marca is_exceptional.
    """

    class Meta:
        model = BudgetLine
        fields = ["category", "kind", "planned_amount", "due_date", "scope", "owner", "note"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, kind=None, **kwargs):
        """`kind` fijo (desde la ruta): el campo desaparece y las categorias se
        limitan a las de ese tipo. Un aguinaldo no puede caer en "Rent"."""
        super().__init__(*args, **kwargs)
        # `owner` es una Membership, que no hereda de HouseholdScoped, asi que la
        # base no lo acota: mismo caso que IncomeSourceForm.
        self.fields["owner"].queryset = self.household.active_memberships()
        self.fields["owner"].required = False
        if kind is not None:
            del self.fields["kind"]
            self.instance.kind = kind
            self.fields["category"].queryset = self.fields["category"].queryset.filter(kind=kind)


class LineasDelMesForm(forms.Form):
    """Los importes de las lineas de un mes, para los pasos 1 y 2 del §4.5.6.

    Un campo por linea, llamado `linea-<pk>`: "confirma o ajusta lo que varia"
    es teclear un numero al lado de cada nombre, no abrir una pagina por linea.
    No es un ModelForm porque no hay un modelo que editar sino N filas, y un
    formset de Django pide en el POST una gestion (`TOTAL_FORMS`…) que aqui no
    aporta nada.
    """

    def __init__(self, *args, lineas, **kwargs):
        super().__init__(*args, **kwargs)
        self.lineas = list(lineas)
        for linea in self.lineas:
            # En blanco es "no toques esta linea", no cero: asi "Next" sin cambiar
            # nada avanza, y borrar un campo por error no deja un gasto en 0.
            self.fields[self.nombre_del_campo(linea)] = forms.DecimalField(
                label=linea.nombre, max_digits=12, decimal_places=2,
                min_value=Decimal("0.00"), initial=linea.planned_amount, required=False,
            )

    @staticmethod
    def nombre_del_campo(linea):
        return f"linea-{linea.pk}"

    def filas(self):
        """Cada linea con su campo, para pintar la tabla."""
        return [(linea, self[self.nombre_del_campo(linea)]) for linea in self.lineas]

    def guardar(self):
        for linea in self.lineas:
            nuevo = self.cleaned_data[self.nombre_del_campo(linea)]
            if nuevo is not None and nuevo != linea.planned_amount:
                linea.planned_amount = nuevo
                linea.save(update_fields=["planned_amount"])


class RetiroForm(forms.Form):
    """Sacar dinero de una meta: "ya lo use". No es un ModelForm porque el
    signo y el origen los pone services_goals, no el usuario."""

    amount = forms.DecimalField(label=_("Amount"), max_digits=12, decimal_places=2,
                                min_value=Decimal("0.01"))
    date = forms.DateField(label=_("Date"), widget=forms.DateInput(attrs={"type": "date"}))
    note = forms.CharField(label=_("What for"), max_length=200, required=False)

    def clean_date(self):
        fecha = self.cleaned_data["date"]
        if fecha > timezone.localdate():
            raise forms.ValidationError(_("A contribution cannot be dated in the future."))
        return fecha


class TransferenciaForm(RetiroForm):
    """Mover saldo a otra meta activa que quien mueve pueda ver."""

    # unscoped.none() y no objects.none(): el manager acotado lanza al pedir
    # un queryset sin hogar, incluso vacio. El real se pone en __init__.
    to_goal = forms.ModelChoiceField(label=_("To"), queryset=Goal.unscoped.none())
    field_order = ["to_goal", "amount", "date", "note"]

    def __init__(self, *args, household, membresia, meta, **kwargs):
        super().__init__(*args, **kwargs)
        visibles = Q(scope=HOUSEHOLD) | Q(scope=PERSONAL, owner=membresia)
        self.fields["to_goal"].queryset = (
            Goal.objects.for_household(household)
            .filter(visibles, status=Goal.ACTIVE).exclude(pk=meta.pk)
        )


class BalanceItemForm(HouseholdScopedModelForm):
    """Una linea del balance del hogar. El grupo va agrupado en activos y
    pasivos en el desplegable: es lo unico que decide de que lado suma."""

    class Meta:
        model = BalanceItem
        fields = ["group", "name", "amount", "note"]
        help_texts = {
            "amount": _("Today's value, as a positive number. A debt is what you still owe."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].choices = [
            (_("Assets"), [(c, e) for c, t, e in GRUPOS if t == ASSET]),
            (_("Liabilities"), [(c, e) for c, t, e in GRUPOS if t == LIABILITY]),
        ]

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.budget.engine.merchants import normalizar
from apps.households.scoping import HouseholdScoped

INCOME = "income"
EXPENSE = "expense"
KIND_CHOICES = [(INCOME, _("Income")), (EXPENSE, _("Expense"))]

HOUSEHOLD = "household"
PERSONAL = "personal"
SCOPE_CHOICES = [(HOUSEHOLD, _("Household")), (PERSONAL, _("Personal"))]


class Category(HouseholdScoped):
    """Una categoría del árbol del hogar.

    Las del sistema se siembran por hogar al crearlo (apps/budget/seeds.py):
    `slug` puesto, `name` vacío, `is_system=True`. Se muestran traducidas
    desde el slug mientras `name` esté vacío, y renombrarlas solo escribe
    `name` — así el "el hogar puede añadir y renombrar" del §3.2 es cierto sin
    una tabla de anulaciones.
    """

    slug = models.SlugField(_("identifier"), max_length=50)
    name = models.CharField(_("name"), max_length=80, blank=True)
    is_system = models.BooleanField(_("preloaded"), default=False)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    kind = models.CharField(_("kind"), max_length=10, choices=KIND_CHOICES, default=EXPENSE)
    # Fase 4 (CRA). Se siembra desde ya porque etiquetar dos años de gastos
    # retroactivamente es un trabajo que nadie hace nunca.
    tax_category = models.CharField(_("tax category"), max_length=30, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        constraints = [
            models.UniqueConstraint(fields=["household", "slug"], name="una_categoria_por_slug_y_hogar")
        ]

    def __str__(self):
        return self.etiqueta()

    def etiqueta(self):
        """El nombre visible: el que puso el hogar, o el del sistema traducido."""
        if self.name:
            return self.name
        from apps.budget.seeds import etiqueta_de_slug

        return etiqueta_de_slug(self.slug)

    def clean(self):
        super().clean()
        if self.parent_id and self.parent.household_id != self.household_id:
            raise ValidationError({"parent": _("That category belongs to another household.")})


class Merchant(HouseholdScoped):
    name = models.CharField(_("merchant"), max_length=120)
    normalized_name = models.CharField(max_length=120, editable=False)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("merchant")
        verbose_name_plural = _("merchants")
        constraints = [
            models.UniqueConstraint(
                fields=["household", "normalized_name"], name="un_comercio_por_nombre_y_hogar"
            )
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.normalized_name = normalizar(self.name)
        super().save(*args, **kwargs)

"""El árbol de categorías precargado del §3.2.

Se copia por hogar al crearlo. Las etiquetas viven aquí y no en la base de
datos: así se muestran en el idioma de cada miembro, y un hogar en inglés y
otro en francés ven los mismos datos con sus propias palabras.
"""

from django.utils.translation import gettext as _

# (slug, etiqueta, slug del padre, kind)
ARBOL = [
    ("housing", "Housing", None, "expense"),
    ("rent", "Rent", "housing", "expense"),
    ("mortgage", "Mortgage", "housing", "expense"),
    ("utilities", "Utilities", None, "expense"),
    ("water", "Water", "utilities", "expense"),
    ("gas", "Gas", "utilities", "expense"),
    ("electricity", "Electricity", "utilities", "expense"),
    ("internet", "Internet", "utilities", "expense"),
    ("subscriptions", "Subscriptions", None, "expense"),
    ("groceries", "Groceries", None, "expense"),
    ("transport", "Transport", None, "expense"),
    ("fuel", "Fuel", "transport", "expense"),
    ("entertainment", "Entertainment", None, "expense"),
    ("financial_obligations", "Financial obligations", None, "expense"),
    ("bank_loans", "Bank loans", "financial_obligations", "expense"),
    ("salary", "Salary", None, "income"),
    ("other_income", "Other income", None, "income"),
]

ETIQUETAS = {slug: etiqueta for slug, etiqueta, _padre, _kind in ARBOL}


def etiqueta_de_slug(slug):
    """La etiqueta traducida de una categoría del sistema."""
    return _(ETIQUETAS.get(slug, slug))


def sembrar(household):
    """Copia el árbol en un hogar recién creado. Idempotente."""
    from apps.budget.models import Category

    if Category.objects.for_household(household).exists():
        return

    creadas = {}
    for slug, _etiqueta, padre, kind in ARBOL:
        # `Category.objects.create(...)` lanzaria RuntimeError: el manager
        # estricto del lote de puertas no deja consultar sin hogar, y `create`
        # pasa por `get_queryset()`. Se instancia y se guarda.
        categoria = Category(
            household=household, slug=slug, is_system=True,
            kind=kind, parent=creadas.get(padre),
        )
        categoria.save()
        creadas[slug] = categoria
    return creadas

"""Los tipos de campo compartidos por los modelos de Wealthome."""

from django.db import models


def MoneyField(**kwargs):
    """Todo importe monetario de la aplicación.

    Spec §3.4: `DecimalField(max_digits=12, decimal_places=2)`, nunca `float`.
    En coma flotante `0.1 + 0.2 != 0.3`, y en una aplicación financiera eso
    produce balances que no cuadran por centavos; un usuario que ve eso deja
    de confiar en la aplicación entera.

    Es una función y no una subclase de `DecimalField` a propósito: una
    subclase aparecería en cada migración como un tipo propio de este
    proyecto (`apps.core.fields.MoneyField`), atando doce migraciones a que
    esta clase siga existiendo con ese nombre. Devolviendo un `DecimalField`
    normal, las migraciones solo ven `DecimalField(max_digits=12,
    decimal_places=2)` y este archivo se puede reorganizar sin tocarlas.

    Acepta las opciones normales de un campo, incluida la precisión: no se
    prohíbe otro tamaño, se hace visible en el diff de quien lo escriba.
    """
    kwargs.setdefault("max_digits", 12)
    kwargs.setdefault("decimal_places", 2)
    return models.DecimalField(**kwargs)

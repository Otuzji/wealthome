from django.db import models

from .models import Household


class HouseholdScopedQuerySet(models.QuerySet):
    def for_household(self, household):
        return self.filter(household=household)

    def for_user(self, user):
        """Todo lo visible para este usuario, en todos sus hogares activos.

        Es el único punto de entrada soportado desde una vista. Filtrar a mano
        en cada vista es como se filtran mal los datos de otras familias.
        """
        if not getattr(user, "is_authenticated", False):
            return self.none()
        hogares = Household.objects.filter(memberships__user=user, memberships__is_active=True)
        return self.filter(household__in=hogares)


class HouseholdScopedManager(models.Manager.from_queryset(HouseholdScopedQuerySet)):
    pass


class HouseholdScoped(models.Model):
    """Todo dato que pertenece a un hogar hereda de aquí."""

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_set"
    )

    objects = HouseholdScopedManager()

    class Meta:
        abstract = True

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BudgetConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.budget"
    verbose_name = _("Budget")

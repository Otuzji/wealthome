from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("household/", include("apps.households.urls")),
    path("", include("apps.accounts.urls")),
]

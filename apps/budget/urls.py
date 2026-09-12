from django.urls import path

from . import views_goals, views_month, views_overview, views_setup, wizards

app_name = "budget"

# Las pantallas de configuracion NO llevan ambito: se configura el hogar, y lo
# personal de un miembro no tiene reglas propias.
urlpatterns = [
    path("setup/", views_setup.configurar, name="configurar"),
    path("setup/income/new/", views_setup.ingreso_nuevo, name="ingreso_nuevo"),
    path("setup/expense/new/", views_setup.gasto_nuevo, name="gasto_nuevo"),
    path("setup/category/new/", views_setup.categoria_nueva, name="categoria_nueva"),
    path("setup/split/new/", views_setup.reparto_nuevo, name="reparto_nuevo"),
    path("spend/", views_month.registrar, name="registrar"),
    path("line/new/", views_month.linea_nueva, name="linea_nueva"),
    path("split/reorder/", wizards.reordenar_reglas, name="reordenar_reglas"),
    path("goals/new/", views_goals.meta_nueva, name="meta_nueva"),
    path("goals/contribute/", views_goals.aportar, name="aportar"),
    # Antes de los patrones con <str:ambito>, o "personal" se comeria el
    # patron generico. Y sin ambito: la mesada es de un miembro por
    # definicion, y una "mesada del hogar" no significa nada.
    path("personal/allowance/", views_month.mesada, name="mesada"),
]

# Y estas si: son las cuatro del §7.1, en sus dos ambitos.
urlpatterns += [
    path("<str:ambito>/", views_overview.overview, name="overview"),
    path("<str:ambito>/month/", views_month.mes, name="mes"),
    path("<str:ambito>/month/<int:anio>/<int:numero>/", views_month.mes, name="mes"),
    path("<str:ambito>/plan/", wizards.planificar, name="planificar"),
    path("<str:ambito>/plan/<int:paso>/", wizards.planificar,
         name="planificar_paso"),
    path("<str:ambito>/close/", views_month.cerrar, name="cerrar"),
    path("<str:ambito>/balance/", views_overview.balance, name="balance"),
    path("<str:ambito>/goals/", views_goals.metas, name="metas"),
]

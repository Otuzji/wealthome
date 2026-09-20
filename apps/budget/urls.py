from django.urls import path

from . import views_goals, views_month, views_overview, views_setup, wizards
from .models.catalog import INCOME

app_name = "budget"

# Las pantallas de configuracion NO llevan ambito: se configura el hogar, y lo
# personal de un miembro no tiene reglas propias.
urlpatterns = [
    path("setup/", views_setup.configurar, name="configurar"),
    path("setup/income/new/", views_setup.ingreso_nuevo, name="ingreso_nuevo"),
    path("setup/expense/new/", views_setup.gasto_nuevo, name="gasto_nuevo"),
    path("setup/category/new/", views_setup.categoria_nueva, name="categoria_nueva"),
    path("setup/split/new/", views_setup.reparto_nuevo, name="reparto_nuevo"),
    # Corregir y quitar reglas. En sitio, no como sucesora (§3.2): un importe
    # mal tecleado es una correccion, no un cambio en el tiempo.
    path("setup/income/<int:pk>/", views_setup.ingreso_editar, name="ingreso_editar"),
    path("setup/income/<int:pk>/delete/", views_setup.ingreso_borrar, name="ingreso_borrar"),
    path("setup/expense/<int:pk>/", views_setup.gasto_editar, name="gasto_editar"),
    path("setup/expense/<int:pk>/delete/", views_setup.gasto_borrar, name="gasto_borrar"),
    path("setup/split/<int:pk>/", views_setup.reparto_editar, name="reparto_editar"),
    path("setup/split/<int:pk>/delete/", views_setup.reparto_borrar, name="reparto_borrar"),
    # Gasto e ingreso, la misma vista: solo cambia que lineas ofrece.
    path("spend/", views_month.registrar, name="registrar"),
    path("income/", views_month.registrar, {"kind": INCOME}, name="registrar_ingreso"),
    # Corregir o quitar un registro mal tecleado, desde "What actually happened".
    path("spend/<int:pk>/", views_month.registro_editar, name="registro_editar"),
    path("spend/<int:pk>/delete/", views_month.registro_borrar, name="registro_borrar"),
    path("line/new/", views_month.linea_nueva, name="linea_nueva"),
    path("split/reorder/", wizards.reordenar_reglas, name="reordenar_reglas"),
    path("welcome/<int:paso>/", wizards.incorporacion, name="incorporacion"),
    path("goals/new/", views_goals.meta_nueva, name="meta_nueva"),
    path("goals/contribute/", views_goals.aportar, name="aportar"),
    # Corregir, quitar, abandonar o reactivar una meta. Quitar solo si nunca
    # recibio cascada: un aporte del cierre es historia de un mes cerrado.
    path("goals/<int:pk>/", views_goals.meta_editar, name="meta_editar"),
    path("goals/<int:pk>/delete/", views_goals.meta_borrar, name="meta_borrar"),
    path("goals/<int:pk>/status/<str:estado>/", views_goals.meta_estado, name="meta_estado"),
    path("goals/contributions/<int:pk>/", views_goals.aporte_editar, name="aporte_editar"),
    path("goals/contributions/<int:pk>/delete/", views_goals.aporte_borrar, name="aporte_borrar"),
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
    # Cualquier mes no cerrado se planifica, no solo el corriente.
    path("<str:ambito>/plan/<int:anio>/<int:numero>/<int:paso>/", wizards.planificar,
         name="planificar_mes"),
    path("<str:ambito>/plan/<int:anio>/<int:numero>/<int:paso>/refresh/", wizards.refrescar,
         name="planificar_refrescar"),
    path("<str:ambito>/plan/<int:anio>/<int:numero>/line/new/", views_month.linea_nueva_del_mes,
         name="linea_nueva_del_mes"),
    path("<str:ambito>/plan/<int:anio>/<int:numero>/line/new/<str:kind>/",
         views_month.linea_nueva_del_mes, name="linea_nueva_del_mes_de"),
    path("<str:ambito>/line/<int:pk>/remove/", views_month.linea_quitar, name="linea_quitar"),
    path("<str:ambito>/close/", views_month.cerrar, name="cerrar"),
    path("<str:ambito>/close/<int:anio>/<int:numero>/", views_month.cerrar, name="cerrar_mes"),
    path("<str:ambito>/balance/", views_overview.balance, name="balance"),
    path("<str:ambito>/goals/", views_goals.metas, name="metas"),
]

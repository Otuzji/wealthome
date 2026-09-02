"""El admin de Django sobre modelos con ámbito de hogar.

`ModelAdmin` resuelve las filas por `_default_manager` y construye su
formulario llamando a `db_field.formfield()`; con el manager estricto, las dos
cosas lanzan `RuntimeError`. Sin este mixin, el primer
`admin.site.register(Transaccion)` del Plan 2 revienta al importar el módulo
del admin, con una traza que no menciona ni al admin ni al hogar.

El admin es cross-hogar a propósito: lo usa el superusuario para
mantenimiento, no una familia. Por eso entra por `unscoped` — explícito, y
aislado en esta única clase.
"""

import pytest
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.households.admin import HouseholdScopedAdmin
from tests.factories import EtiquetaFactory, HouseholdFactory, NotaFactory


def _peticion():
    peticion = RequestFactory().get("/admin/")
    peticion.user = AnonymousUser()
    return peticion


@pytest.mark.django_db
def test_el_admin_acotado_ve_todos_los_hogares():
    from tests.models import Nota

    NotaFactory(household=HouseholdFactory(), texto="Thompson")
    NotaFactory(household=HouseholdFactory(), texto="García")

    sitio = HouseholdScopedAdmin(Nota, admin.AdminSite())

    assert sitio.get_queryset(_peticion()).count() == 2


@pytest.mark.django_db
def test_el_admin_acotado_construye_su_formulario_sin_reventar():
    """La clave foránea a Etiqueta —un modelo con hogar— es lo que hace
    lanzar a un ModelAdmin normal."""
    from tests.models import Nota

    sitio = HouseholdScopedAdmin(Nota, admin.AdminSite())

    formulario = sitio.get_form(_peticion())

    assert "etiqueta" in formulario.base_fields


@pytest.mark.django_db
def test_el_desplegable_del_admin_ofrece_todos_los_hogares():
    from tests.models import Nota

    EtiquetaFactory(household=HouseholdFactory(), nombre="Etiqueta Thompson")
    EtiquetaFactory(household=HouseholdFactory(), nombre="Etiqueta García")

    sitio = HouseholdScopedAdmin(Nota, admin.AdminSite())
    campo = sitio.get_form(_peticion()).base_fields["etiqueta"]

    assert campo.queryset.count() == 2


@pytest.mark.django_db
def test_un_modeladmin_normal_sobre_un_modelo_con_hogar_sigue_reventando():
    """Es la prueba de que el mixin hace falta. Si esto dejara de lanzar,
    alguien habría ablandado la barrera."""
    from tests.models import Nota

    sitio = admin.ModelAdmin(Nota, admin.AdminSite())

    with pytest.raises(RuntimeError):
        sitio.get_queryset(_peticion())

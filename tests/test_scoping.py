import pytest
from django.core.exceptions import PermissionDenied
from django.db import models

from apps.households.models import Membership
from apps.households.permissions import get_membership, require_permission
from apps.households.scoping import HouseholdScoped
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


@pytest.mark.django_db
def test_for_user_solo_devuelve_datos_del_hogar_del_usuario():
    """La prueba que impide que los Thompson vean las finanzas de los García."""
    from tests.models import Nota  # modelo de prueba, ver tests/models.py

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    papa = UserFactory()
    MembershipFactory(household=thompson, user=papa, role=Membership.ADMIN)

    Nota.objects.create(household=thompson, texto="hipoteca de los Thompson")
    Nota.objects.create(household=garcia, texto="hipoteca de los García")

    visibles = Nota.objects.for_user(papa)
    assert [n.texto for n in visibles] == ["hipoteca de los Thompson"]


@pytest.mark.django_db
def test_for_user_no_devuelve_nada_a_quien_no_tiene_membresia():
    from tests.models import Nota

    hogar = HouseholdFactory()
    Nota.objects.create(household=hogar, texto="secreto")
    assert Nota.objects.for_user(UserFactory()).count() == 0


@pytest.mark.django_db
def test_una_membresia_inactiva_no_da_acceso():
    from tests.models import Nota

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, is_active=False)
    Nota.objects.create(household=hogar, texto="secreto")
    assert Nota.objects.for_user(user).count() == 0


@pytest.mark.django_db
def test_todo_modelo_con_hogar_hereda_de_household_scoped():
    """Un modelo con FK a Household que no herede de HouseholdScoped es un agujero.

    Esta prueba vigila al Plan 2 y al Plan 3: cada modelo nuevo con ámbito de
    hogar la rompe hasta que hereda de HouseholdScoped, que es justo lo que
    queremos que pase.
    """
    from django.apps import apps as django_apps

    from apps.households.models import Household

    # Relacionan usuarios con el hogar; no son datos del hogar.
    EXCEPCIONES = {"Membership", "Invitation"}

    infractores = []
    for modelo in django_apps.get_models():
        if modelo is Household or modelo.__name__ in EXCEPCIONES:
            continue
        tiene_fk_a_hogar = any(
            isinstance(campo, models.ForeignKey) and campo.related_model is Household
            for campo in modelo._meta.get_fields()
            if isinstance(campo, models.ForeignKey)
        )
        if tiene_fk_a_hogar and not issubclass(modelo, HouseholdScoped):
            infractores.append(modelo.__name__)

    assert infractores == [], f"Modelos con hogar sin HouseholdScoped: {infractores}"


def _modelos_household_scoped():
    """Cada modelo concreto que hereda de HouseholdScoped, registrado ahora mismo."""
    from django.apps import apps as django_apps

    return [
        modelo
        for modelo in django_apps.get_models()
        if issubclass(modelo, HouseholdScoped) and not modelo._meta.abstract
    ]


def _lineas_de_vistas(raiz):
    """(archivo, número de línea, texto) de cada línea en cada <raiz>/*/views.py."""
    for archivo in sorted(raiz.glob("*/views.py")):
        texto = archivo.read_text(encoding="utf-8")
        for numero, linea in enumerate(texto.splitlines(), start=1):
            yield archivo, numero, linea


def _infractores_de_manager_por_defecto(raiz=None, nombres=None):
    """Ruling R-7: HouseholdScoped.objects es opt-in — nada impide que una vista
    escriba `Modelo.objects.filter(...)` en vez de `Modelo.objects.for_user(...)`
    / `.for_household(...)`. Esta función vigila cada views.py bajo <raiz>: busca
    `<ModeloConHogar>.objects.<algo>` donde <algo> no sea `for_user(` ni
    `for_household(`.

    `raiz` y `nombres` son parametrizables para que
    test_la_guardia_de_manager_por_defecto_falla_ante_un_infractor pueda
    demostrar, contra un views.py de juguete en un directorio temporal, que
    esta guardia sí detecta una fuga real — sin tocar el código de producción.
    """
    import pathlib
    import re

    raiz = raiz or pathlib.Path(__file__).resolve().parent.parent / "apps"
    if nombres is None:
        nombres = [modelo.__name__ for modelo in _modelos_household_scoped()]
    if not nombres:
        return []

    patron = re.compile(
        r"\b(?:" + "|".join(re.escape(n) for n in nombres) + r")\.objects\."
        r"(?!for_user\(|for_household\()\w+"
    )

    infractores = []
    for archivo, numero, linea in _lineas_de_vistas(raiz):
        if patron.search(linea):
            infractores.append(f"{archivo}:{numero}: {linea.strip()}")
    return infractores


@pytest.mark.django_db
def test_ninguna_vista_consulta_un_modelo_con_hogar_por_el_manager_por_defecto():
    """R-7: la propiedad HouseholdScoped.objects.for_user()/for_household() no
    protege nada si una vista puede seguir escribiendo Modelo.objects.all() o
    Modelo.objects.filter(...) a mano. Esta prueba recorre el texto de cada
    apps/*/views.py y falla si aparece esa fuga, nombrando el archivo, la línea
    y el texto exacto para que quien la dispare en el Plan 2 sepa qué corregir
    sin tener que leer esta prueba.

    Solo vigila modelos que heredan de HouseholdScoped (Nota, en las pruebas
    de hoy; los modelos con datos reales del Plan 2 en adelante). Membership e
    Invitation quedan fuera a propósito: relacionan usuarios con el hogar y no
    heredan de HouseholdScoped (ver test_todo_modelo_con_hogar_hereda_de_household_scoped),
    así que las vistas de esta tarea los consultan directamente, acotados a
    mano al hogar activo del usuario autenticado.
    """
    infractores = _infractores_de_manager_por_defecto()
    assert infractores == [], (
        "Vistas que consultan un modelo con ámbito de hogar por el manager "
        "por defecto en vez de .for_user()/.for_household():\n"
        + "\n".join(infractores)
    )


def test_la_guardia_de_manager_por_defecto_falla_ante_un_infractor(tmp_path):
    """Prueba de la prueba: si la guardia de arriba no puede fallar, no vigila
    nada — es justo lo que este plan ya atrapó tres veces. Se escribe un
    views.py de juguete, en un directorio temporal (no en apps/ real), que
    consulta un modelo con ámbito de hogar por el manager por defecto, y se
    verifica que la guardia lo detecta y que su mensaje nombra el archivo, la
    línea y el texto exacto."""
    app_falsa = tmp_path / "cuentas_falsas"
    app_falsa.mkdir()
    vista_infractora = app_falsa / "views.py"
    vista_infractora.write_text(
        "def ver_todo(request):\n"
        "    return Transaccion.objects.all()\n",
        encoding="utf-8",
    )

    infractores = _infractores_de_manager_por_defecto(raiz=tmp_path, nombres=["Transaccion"])

    assert len(infractores) == 1
    assert str(vista_infractora) in infractores[0]
    assert ":2:" in infractores[0]
    assert "Transaccion.objects.all()" in infractores[0]

    # Y una vista legítima, que sí pasa por for_user(), no debe dispararla.
    vista_infractora.write_text(
        "def ver_todo(request):\n"
        "    return Transaccion.objects.for_user(request.user)\n",
        encoding="utf-8",
    )
    assert _infractores_de_manager_por_defecto(raiz=tmp_path, nombres=["Transaccion"]) == []


@pytest.mark.django_db
def test_get_membership_devuelve_none_para_un_extrano():
    assert get_membership(UserFactory(), HouseholdFactory()) is None


@pytest.mark.django_db
def test_require_permission_deja_pasar_al_que_lo_tiene():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=True)
    require_permission(user, hogar, "can_edit_budget")  # no debe lanzar


@pytest.mark.django_db
def test_require_permission_bloquea_al_que_no_lo_tiene():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=False)
    with pytest.raises(PermissionDenied):
        require_permission(user, hogar, "can_edit_budget")


@pytest.mark.django_db
def test_require_permission_bloquea_a_quien_no_es_del_hogar():
    with pytest.raises(PermissionDenied):
        require_permission(UserFactory(), HouseholdFactory(), "can_view_budget")


@pytest.mark.django_db
def test_require_permission_rechaza_un_permiso_inexistente():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user)
    with pytest.raises(ValueError):
        require_permission(user, hogar, "can_do_anything")

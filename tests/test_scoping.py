"""La barrera de aislamiento entre hogares.

Hasta el Plan 1 esto era una convención: `HouseholdScoped.objects` ofrecía
`.for_user()` y `.for_household()`, pero `.all()` y `.filter()` seguían ahí y
son lo primero que escribe cualquier desarrollador de Django. El spec §6.1
pide un manager "que exige el hogar como parámetro"; estas pruebas son la
definición ejecutable de esa exigencia.

Lo que la barrera bloquea y lo que deja pasar está en las pruebas de abajo,
una por escritura posible. Las tres escrituras que el traspaso llamaba
puntos ciegos —`Modelo.objects.all()`, `get_object_or_404(Modelo, pk=pk)` y
un `ModelForm` con clave foránea a un modelo con hogar— fallan hoy con un
RuntimeError, no con una revisión de código.
"""

import pytest
from django import forms
from django.db import models
from django.shortcuts import get_object_or_404

from apps.households.scoping import HouseholdScoped, HouseholdScopedManager
from tests.factories import EtiquetaFactory, HouseholdFactory, NotaFactory

# --- Lo que la barrera bloquea ----------------------------------------------


@pytest.mark.django_db
def test_all_por_el_manager_por_defecto_lanza():
    from tests.models import Nota

    with pytest.raises(RuntimeError):
        list(Nota.objects.all())


@pytest.mark.django_db
def test_filter_por_el_manager_por_defecto_lanza():
    from tests.models import Nota

    with pytest.raises(RuntimeError):
        list(Nota.objects.filter(texto="lo que sea"))


@pytest.mark.django_db
def test_get_por_el_manager_por_defecto_lanza():
    from tests.models import Nota

    with pytest.raises(RuntimeError):
        Nota.objects.get(pk=1)


@pytest.mark.django_db
def test_get_object_or_404_sin_hogar_lanza():
    """El punto ciego que el traspaso llama el peor.

    django.shortcuts._get_queryset usa Model._default_manager, así que
    get_object_or_404(Transaccion, pk=pk) —el estilo que ya usaba la vista
    `permisos`— nunca escribe `.objects.` y ninguna guardia de texto lo ve.
    Con el manager estricto como _default_manager, revienta.
    """
    from tests.models import Nota

    nota = NotaFactory(texto="hipoteca")
    with pytest.raises(RuntimeError):
        get_object_or_404(Nota, pk=nota.pk)


@pytest.mark.django_db
def test_el_mensaje_del_error_dice_qué_escribir_en_su_lugar():
    from tests.models import Nota

    with pytest.raises(RuntimeError, match=r"for_household"):
        list(Nota.objects.all())


def test_declarar_un_modelform_ingenuo_sobre_un_modelo_con_hogar_lanza():
    """La fuga por <select> del traspaso, cerrada en tiempo de import.

    ForeignKey.formfield() evalúa remote_field.model._default_manager de
    forma ansiosa —antes de mezclar los kwargs, así que pasarle un queryset
    no lo evita—, de modo que un ModelForm sobre un modelo con hogar no
    llega siquiera a existir. Se rompe al declarar la clase, no al servir la
    petición: imposible desplegarlo sin enterarse.
    """
    from tests.models import Nota

    with pytest.raises(RuntimeError):

        class NotaFormIngenuo(forms.ModelForm):
            class Meta:
                model = Nota
                fields = ["etiqueta", "texto"]


# --- Lo que la barrera deja pasar -------------------------------------------


@pytest.mark.django_db
def test_for_household_devuelve_solo_las_filas_de_ese_hogar():
    """La prueba que impide que los Thompson vean las finanzas de los García."""
    from tests.models import Nota

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    NotaFactory(household=thompson, texto="hipoteca de los Thompson")
    NotaFactory(household=garcia, texto="hipoteca de los García")

    visibles = Nota.objects.for_household(thompson)

    assert [n.texto for n in visibles] == ["hipoteca de los Thompson"]


@pytest.mark.django_db
def test_el_accesor_inverso_funciona_y_viene_acotado_por_su_dueño():
    """`hogar.notas.all()` es seguro por construcción: la instancia dueña ya
    ES el ámbito. Django construye ese manager subclasando el manager por
    defecto del modelo relacionado, así que la barrera tiene que dejarlo
    pasar explícitamente o el motor del Plan 2 —escrito en ese estilo—
    no compilaría una línea."""
    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    NotaFactory(household=thompson, texto="de los Thompson")
    NotaFactory(household=garcia, texto="de los García")

    assert [n.texto for n in thompson.notas.all()] == ["de los Thompson"]


@pytest.mark.django_db
def test_unscoped_es_la_salida_de_emergencia_explícita():
    """Migraciones de datos, el admin y los scripts de mantenimiento
    necesitan ver todas las filas. Que tengan que escribir `unscoped` es
    justo el punto: se ve en la revisión."""
    from tests.models import Nota

    NotaFactory(household=HouseholdFactory())
    NotaFactory(household=HouseholdFactory())

    assert Nota.unscoped.count() == 2


@pytest.mark.django_db
def test_borrar_un_hogar_arrastra_sus_filas_en_cascada():
    """El recolector de borrados usa _base_manager. Si base_manager_name no
    apuntara a `unscoped`, borrar un hogar reventaría con RuntimeError."""
    from tests.models import Nota

    hogar = HouseholdFactory()
    NotaFactory(household=hogar)
    hogar.delete()

    assert Nota.unscoped.count() == 0


# --- La barrera se mantiene sola --------------------------------------------


def _modelos_household_scoped():
    """Cada modelo concreto que hereda de HouseholdScoped, registrado ahora mismo."""
    from django.apps import apps as django_apps

    return [
        modelo
        for modelo in django_apps.get_models()
        if issubclass(modelo, HouseholdScoped) and not modelo._meta.abstract
    ]


def test_todo_modelo_con_hogar_conserva_base_manager_name():
    """`base_manager_name = "unscoped"` vive en la Meta abstracta de
    HouseholdScoped. Una subclase del Plan 2 que declare su propia Meta sin
    heredarla lo pierde en silencio: el manager estricto pasaría a ser
    también el manager base, y el borrado en cascada, refresh_from_db y los
    descriptores de clave foránea empezarían a lanzar RuntimeError desde
    dentro del ORM, lejos de la causa. Esta prueba nombra al infractor.
    """
    infractores = [
        modelo.__name__
        for modelo in _modelos_household_scoped()
        if modelo._meta.base_manager_name != "unscoped"
    ]
    assert infractores == [], (
        "Modelos con hogar que perdieron base_manager_name — su Meta debe "
        'heredar de HouseholdScoped.Meta o repetir base_manager_name = "unscoped": '
        + ", ".join(infractores)
    )


def test_toda_unique_constraint_de_un_modelo_con_hogar_incluye_household():
    """`_validando_unicidad()` (apps/households/scoping.py) destraba el
    manager estricto mientras Django valida restricciones de unicidad, y
    eso solo es seguro porque la restricción de un modelo con hogar lleva
    `household` entre sus propios campos: así el queryset sin acotar que
    arma Django ya viene filtrado a esa familia. Nada en el tipo obliga a
    eso — una UniqueConstraint es una UniqueConstraint como cualquier otra,
    y nada impide que un modelo futuro declare una sin `household`. Si eso
    pasara, la validación de unicidad compararía contra todas las familias a
    la vez, sin que nada lo delate. Esta prueba nombra al infractor.
    """
    infractores = []
    for modelo in _modelos_household_scoped():
        for constraint in modelo._meta.constraints:
            if isinstance(constraint, models.UniqueConstraint) and "household" not in constraint.fields:
                infractores.append(f"{modelo.__name__}.{constraint.name}")
        for campos in modelo._meta.unique_together:
            if "household" not in campos:
                infractores.append(f"{modelo.__name__}.unique_together{tuple(campos)}")

    assert infractores == [], (
        "UniqueConstraint (o unique_together) de un modelo con hogar sin "
        "household entre sus campos — la validación de unicidad dejaría de "
        "estar acotada por familia: " + ", ".join(infractores)
    )


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
    # Subscription es distinto: es titularidad, no aislamiento. La Tarea 7 pone
    # la guardia de suscripcion dentro de HouseholdScoped.save(). Si Subscription
    # heredara de ahi, escribir la suscripcion de un hogar expirado quedaria
    # bloqueada por la guardia que lee esa misma fila -y un hogar expirado no
    # podria reactivarse pagando nunca. Punto muerto que Membership e
    # Invitation no corren porque su guardia no depende de su propio estado.
    EXCEPCIONES = {"Membership", "Invitation", "Subscription"}

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


# --- La barrera de formularios ----------------------------------------------


def _nota_form():
    """Construye el ModelForm seguro sobre Nota.

    Se construye dentro de una función y no a nivel de módulo porque
    tests.models solo se puede importar con las apps ya cargadas.
    """
    from apps.households.scoped_forms import HouseholdScopedModelForm
    from tests.models import Nota

    return type(
        "NotaFormSeguro",
        (HouseholdScopedModelForm,),
        {"Meta": type("Meta", (), {"model": Nota, "fields": ["etiqueta", "texto"]})},
    )


@pytest.mark.django_db
def test_el_formulario_seguro_solo_ofrece_las_filas_del_hogar_dado():
    """El <select> renderizado no puede contener ni un nombre de otra familia."""
    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    EtiquetaFactory(household=thompson, nombre="Hipoteca Thompson")
    EtiquetaFactory(household=garcia, nombre="Hipoteca García")

    html = _nota_form()(household=thompson).as_p()

    assert "Hipoteca Thompson" in html
    assert "Hipoteca García" not in html


@pytest.mark.django_db
def test_el_formulario_seguro_exige_el_hogar():
    """Olvidarlo es un TypeError al instanciar, no un <select> con todo dentro."""
    with pytest.raises(TypeError):
        _nota_form()()


@pytest.mark.django_db
def test_el_formulario_seguro_rechaza_una_fila_de_otro_hogar():
    """La defensa que importa: el <select> filtrado es cosmético — un POST
    con el id de una etiqueta ajena no pasa por el navegador. Lo que impide
    escribir a través de hogares es que el queryset del campo, no solo su
    render, esté acotado."""
    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    ajena = EtiquetaFactory(household=garcia, nombre="Hipoteca García")

    form = _nota_form()(data={"etiqueta": ajena.pk, "texto": "intento"}, household=thompson)

    assert not form.is_valid()
    assert "etiqueta" in form.errors


@pytest.mark.django_db
def test_el_formulario_seguro_acepta_una_fila_del_hogar_propio():
    thompson = HouseholdFactory()
    propia = EtiquetaFactory(household=thompson, nombre="Hipoteca Thompson")

    form = _nota_form()(data={"etiqueta": propia.pk, "texto": "alquiler"}, household=thompson)

    assert form.is_valid(), form.errors


# --- La guardia de texto (redundante hoy, más rápida de leer) ---------------


def _lineas_de_vistas(raiz):
    """(archivo, número de línea, texto) de cada línea en cada <raiz>/*/views.py."""
    for archivo in sorted(raiz.glob("*/views.py")):
        texto = archivo.read_text(encoding="utf-8")
        for numero, linea in enumerate(texto.splitlines(), start=1):
            yield archivo, numero, linea


def _infractores_de_manager_por_defecto(raiz=None, nombres=None):
    """Busca `<ModeloConHogar>.objects.<algo>` en cada views.py bajo <raiz>,
    donde <algo> no sea `for_household(`.

    Desde que el manager lanza RuntimeError esta guardia es redundante: la
    escritura que busca ya no llega a ejecutarse. Se conserva porque falla
    **antes** —nombrando archivo, línea y texto— aunque ninguna prueba
    ejercite esa vista, y las vistas del Plan 2 llegarán antes que su
    cobertura. Es un aviso temprano, no la barrera.

    Puntos ciegos, documentados aquí y no en un documento aparte porque una
    guardia en la que se confía de más es peor que no tener guardia:

    - **Accesores inversos por related_name.** `hogar.notas.all()` nunca
      escribe `Modelo.objects.` — y desde este lote es además legítimo (ver
      test_el_accesor_inverso_funciona_y_viene_acotado_por_su_dueño), así
      que aquí no habría nada que reportar.
    - **`get_object_or_404`.** Tampoco escribe `.objects.`. Ese hueco lo
      cierra ahora el manager estricto, no esta guardia.
    - **Cadenas en varias líneas.** Exige `.objects.` y el método en la
      misma línea física.
    - **`glob` de un solo nivel.** No ve `apps/<app>/views/list.py` ni
      `apps/<app>/api/views.py`.
    - **Cobertura real hoy: cero.** Ningún modelo de producción hereda de
      HouseholdScoped todavía (solo Nota y Etiqueta, en tests/models.py).
      Empieza a vigilar de verdad cuando el Plan 2 añada el primero.

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
        r"(?!for_household\()\w+"
    )

    infractores = []
    for archivo, numero, linea in _lineas_de_vistas(raiz):
        if patron.search(linea):
            infractores.append(f"{archivo}:{numero}: {linea.strip()}")
    return infractores


@pytest.mark.django_db
def test_ninguna_vista_consulta_un_modelo_con_hogar_por_el_manager_por_defecto():
    infractores = _infractores_de_manager_por_defecto()
    assert infractores == [], (
        "Vistas que consultan un modelo con ámbito de hogar por el manager "
        "por defecto en vez de .for_household():\n" + "\n".join(infractores)
    )


def test_la_guardia_de_manager_por_defecto_falla_ante_un_infractor(tmp_path):
    """Prueba de la prueba: si la guardia de arriba no puede fallar, no vigila
    nada — es justo lo que el Plan 1 ya atrapó tres veces."""
    app_falsa = tmp_path / "cuentas_falsas"
    app_falsa.mkdir()
    vista_infractora = app_falsa / "views.py"
    vista_infractora.write_text(
        "def ver_todo(request):\n    return Transaccion.objects.all()\n",
        encoding="utf-8",
    )

    infractores = _infractores_de_manager_por_defecto(raiz=tmp_path, nombres=["Transaccion"])

    assert len(infractores) == 1
    assert str(vista_infractora) in infractores[0]
    assert ":2:" in infractores[0]
    assert "Transaccion.objects.all()" in infractores[0]

    # Y una vista legítima, que sí pasa por for_household(), no debe dispararla.
    vista_infractora.write_text(
        "def ver_todo(request):\n    return Transaccion.objects.for_household(hogar)\n",
        encoding="utf-8",
    )
    assert _infractores_de_manager_por_defecto(raiz=tmp_path, nombres=["Transaccion"]) == []


# --- for_user ya no existe ---------------------------------------------------


def test_for_user_no_existe():
    """Puerta 2: `for_user` devolvía filas de TODOS los hogares activos del
    usuario, mientras la vista resolvía "el hogar" como el primero. El día
    que un usuario tuviera dos hogares, el Plan 2 habría sumado el dinero de
    dos familias en un solo presupuesto sin lanzar nada — un número
    equivocado y plausible, el peor modo de fallo en software financiero.

    Se retiró en favor de for_household(hogar), con el hogar resuelto una
    sola vez por petición (apps/households/permissions.py::hogar_actual).
    """
    from tests.models import Nota

    assert not hasattr(Nota.objects, "for_user")
    with pytest.raises(AttributeError):
        Nota.objects.for_user(None)


@pytest.mark.django_db
def test_un_usuario_en_dos_hogares_nunca_ve_la_unión():
    """La prueba que el Plan 1 dejó sin escribir a propósito: escribirla antes
    de decidir la Puerta 2 solo habría fijado el comportamiento accidental."""
    from tests.models import Nota

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    NotaFactory(household=thompson, texto="Thompson")
    NotaFactory(household=garcia, texto="García")

    assert Nota.objects.for_household(thompson).count() == 1
    assert Nota.objects.for_household(garcia).count() == 1


def test_household_scoped_no_ofrece_ninguna_otra_puerta_de_entrada():
    """Si alguien añade un método de conveniencia que devuelva filas sin
    hogar, esta prueba lo nombra. La superficie de la barrera es
    deliberadamente de un solo método."""
    from apps.households.scoping import HouseholdScopedQuerySet

    propios = {
        nombre
        for nombre in vars(HouseholdScopedQuerySet)
        if not nombre.startswith("_")
    }
    assert propios == {"for_household"}


def test_scoped_no_puede_declararse_sin_el_manager_estricto():
    """Un modelo que redefina `objects` con un Manager normal desarma la
    barrera entera y nada más lo notaría."""
    infractores = [
        modelo.__name__
        for modelo in _modelos_household_scoped()
        if not isinstance(modelo.objects, HouseholdScopedManager)
    ]
    assert infractores == [], f"Modelos con hogar que redefinieron objects: {infractores}"


# --- full_clean() sobre un modelo con hogar y UniqueConstraint --------------
#
# Model.validate_constraints() (UniqueConstraint.validate) y
# Model.validate_unique() (_perform_unique_checks) resuelven su queryset con
# model._default_manager, que en un modelo con hogar es el manager estricto
# de arriba: por diseño lanza RuntimeError salvo por accesor inverso o
# for_household(). full_clean() —el candado que el resto del plan pone justo
# antes de save() para atajar escrituras entre hogares— llama a los dos, así
# que sobre Category (household, slug) reventaba con RuntimeError donde debía
# devolver, como mucho, una ValidationError.


@pytest.mark.django_db
def test_full_clean_valida_una_categoria_sin_lanzar_runtimeerror():
    """La instancia es válida y no hay ningún duplicado: full_clean() debe
    poder consultar la restricción sin que el manager estricto se lo impida."""
    from tests.factories_budget import CategoryFactory

    categoria = CategoryFactory(household=HouseholdFactory(), slug="rent")

    categoria.full_clean()  # no debe lanzar RuntimeError


@pytest.mark.django_db
def test_full_clean_sobre_un_duplicado_lanza_validationerror_no_runtimeerror():
    """La prueba que demuestra que el arreglo no desactivó la unicidad: un
    duplicado real de (household, slug) sigue siendo un ValidationError, el
    que corresponde, no un RuntimeError."""
    from django.core.exceptions import ValidationError

    from tests.factories_budget import CategoryFactory

    hogar = HouseholdFactory()
    CategoryFactory(household=hogar, slug="rent")
    duplicada = CategoryFactory.build(household=hogar, slug="rent")

    with pytest.raises(ValidationError):
        duplicada.full_clean()


@pytest.mark.django_db
def test_full_clean_del_mismo_slug_en_otro_hogar_no_lanza():
    """El queryset sin acotar que arma UniqueConstraint.validate() sigue
    filtrando por household porque la restricción lo lleva entre sus propios
    campos: el mismo slug en un hogar distinto no es un duplicado. Si el
    arreglo hubiera ensanchado la consulta en vez de solo destrabarla, esta
    prueba lo notaría."""
    from tests.factories_budget import CategoryFactory

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    CategoryFactory(household=thompson, slug="rent")
    en_garcia = CategoryFactory.build(household=garcia, slug="rent")

    en_garcia.full_clean()  # no debe lanzar


@pytest.mark.django_db
def test_la_barrera_se_restaura_tras_un_full_clean_exitoso():
    """El ContextVar que destraba la validación no debe quedarse destrabado
    después: Category.objects.all() tiene que seguir lanzando."""
    from apps.budget.models import Category
    from tests.factories_budget import CategoryFactory

    categoria = CategoryFactory(household=HouseholdFactory(), slug="rent")
    categoria.full_clean()

    with pytest.raises(RuntimeError):
        list(Category.objects.all())


def test_la_barrera_se_restaura_si_la_validacion_lanza_dentro_del_context_manager():
    """El camino del `finally`: si algo revienta dentro del context manager
    que destraba la validación, el ContextVar tiene que volver a False de
    todos modos, o una excepción a mitad de full_clean() dejaría la barrera
    abajo para la próxima consulta de esta misma petición."""
    from apps.households.scoping import _validando_unicidad
    from tests.models import Nota

    with pytest.raises(ValueError):
        with _validando_unicidad():
            raise ValueError("boom")

    with pytest.raises(RuntimeError):
        list(Nota.objects.all())


@pytest.mark.django_db
def test_full_clean_sigue_ejecutando_el_clean_del_modelo():
    """Lo que de verdad le importa al resto del plan: full_clean() no debe
    limitarse a sobrevivir a validate_constraints(); tiene que seguir
    llamando clean() y rechazar una categoría cuyo padre es de otro hogar,
    nombrando el campo culpable — la guardia contra escrituras entre hogares
    en la que las vistas del Plan 2 confían."""
    from django.core.exceptions import ValidationError

    from tests.factories_budget import CategoryFactory

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    padre_ajeno = CategoryFactory(household=garcia, slug="housing")
    hija = CategoryFactory.build(household=thompson, slug="rent", parent=padre_ajeno)

    with pytest.raises(ValidationError) as excinfo:
        hija.full_clean()

    assert "parent" in excinfo.value.message_dict



@pytest.mark.django_db
def test_el_formulario_seguro_fija_el_hogar_antes_de_validar():
    """Un alta nace en el hogar de la petición, no al guardarla.

    `ModelForm._post_clean()` corre `instance.full_clean()` dentro de
    `is_valid()`. Si el hogar se fijara después, en la vista, el `clean()` de
    cualquier modelo que compare el hogar de sus relaciones con el suyo vería
    `None` y rechazaría una fila propia como si fuera de otra familia.
    """
    thompson = HouseholdFactory()
    propia = EtiquetaFactory(household=thompson, nombre="Hipoteca Thompson")

    form = _nota_form()(data={"etiqueta": propia.pk, "texto": "nota"}, household=thompson)

    assert form.instance.household_id == thompson.pk
    assert form.is_valid(), form.errors
    assert form.save().household_id == thompson.pk


@pytest.mark.django_db
def test_el_formulario_seguro_no_reasigna_el_hogar_de_una_fila_existente():
    """Fijar el hogar al construir el formulario vale para las altas.

    En una edición, sobrescribirlo movería la fila de un hogar a otro con solo
    abrir el formulario desde el hogar equivocado — exactamente lo que la
    barrera existe para impedir. Hoy no hay vistas de edición; esta prueba
    está escrita antes que ellas a propósito, porque la garantía depende de
    una sola condición y nada más la ejercita.
    """
    from tests.models import Nota

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    ajena = Nota.unscoped.create(household=garcia, texto="de los García")

    form = _nota_form()(data={"texto": "editada"}, household=thompson, instance=ajena)

    assert form.instance.household_id == garcia.pk
    assert form.is_valid(), form.errors
    assert form.save().household_id == garcia.pk


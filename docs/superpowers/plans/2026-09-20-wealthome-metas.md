# Metas: aportar, corregir y cerrar el ciclo — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar el ciclo de las metas de ahorro: aportar desde la interfaz, estados que cambian, metas y aportes manuales corregibles, y una tarjeta que dice qué la alimenta y cómo va este mes.

**Architecture:** Un módulo de dominio nuevo, `apps/budget/services_goals.py`, concentra lo que hoy no existe (aportar, recalcular estado, cambiar estado, resumen para la pantalla); las vistas de `views_goals.py` quedan delgadas y siguen los helpers de setup y el patrón de `registro_editar`/`registro_borrar`. La tarjeta de la meta se convierte en un fragmento con `id` para viajar fuera de banda tras aportar desde el modal del FAB. Sin migraciones.

**Tech Stack:** Django 5 + htmx + Alpine (vendorizados), pytest + factory_boy, catálogos `.po` a mano, `msgfmt.py` de Python para compilar.

**Spec:** `docs/superpowers/specs/2026-09-20-wealthome-metas-design.md`

## Global Constraints

- Correr pruebas con `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" <ruta>`; nunca dos corridas de pytest a la vez (comparten la base de pruebas). La suite completa (~35 min) solo en la Tarea 9.
- Todo modelo con hogar se consulta con `.objects.for_household(hogar)` o por accesor inverso; `.objects.all()`/`.filter()` a secas lanzan `RuntimeError`. `get_object_or_404(Modelo, ...)` también lanza: pasar siempre un queryset acotado.
- Cadenas de interfaz en inglés con `{% translate %}`/`_()`; cada cadena nueva va a `locale/en/LC_MESSAGES/django.po` y `locale/fr/LC_MESSAGES/django.po` a mano, y se compila con `python C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py -o django.mo django.po` en cada carpeta.
- Al tocar CSS o JS: subir `VERSION` en `templates/sw.js` (hoy `wealthome-v13`) y los dos `paginas-wealthome-vN` de `tests/test_pwa.py`.
- Comentarios en el código en español, sin tildes en los archivos `.py` nuevos (como el resto del módulo), explicando el porqué y no el qué.
- Heredocs bash largos fallan en esta máquina: para escribir archivos usar la herramienta Write.
- Commits en español, sin tildes en la primera línea, con `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` al final.

---

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `apps/budget/models/goals.py` (modificar) | `Goal.alcanzada()`, `Goal.esta_activa` |
| `apps/budget/services_goals.py` (crear) | `aportar`, `recalcular_estado`, `cambiar_estado`, `resumen` |
| `apps/budget/services.py:680-694` (modificar) | la cascada aporta por `services_goals.aportar` |
| `apps/budget/forms.py:299-317` (modificar) | `GoalForm` (scope/owner bloqueados con aportes), `GoalContributionForm` (metas activas visibles, fecha no futura) |
| `apps/budget/views_goals.py` (reescribir) | `metas`, `meta_nueva`, `meta_editar`, `meta_borrar`, `meta_estado`, `aportar`, `aporte_editar`, `aporte_borrar` |
| `apps/budget/views_setup.py:35-46` (modificar) | `crear(..., initial=None)` para preseleccionar la regla de reparto |
| `apps/budget/urls.py:33-34` (modificar) | rutas nuevas |
| `templates/budget/metas.html` (reescribir) | tres bloques por estado |
| `templates/budget/_fragmentos/meta_tarjeta.html` (crear) | la tarjeta con `id="meta-<pk>"` |
| `templates/budget/_fragmentos/acciones_icono.html` (crear) | Edit/Remove por iconos, parametrizado |
| `templates/budget/_fragmentos/acciones_registro.html` (modificar) | pasa a incluir `acciones_icono.html` |
| `templates/budget/_fragmentos/aporte_form.html` (reescribir) | como `gasto_form.html`, con tarjeta OOB |
| `templates/budget/_fragmentos/aportes.html` (borrar) | absorbido por `meta_tarjeta.html` |
| `templates/_fab.html` (modificar) | tercera opción del selector |
| `static/css/components.css`, `static/css/modules.css` (modificar) | chips de estado, tarjeta apagada, línea de este mes, color del selector |
| `tests/budget/test_services_goals.py` (crear) | el módulo de dominio |
| `tests/budget/test_metas_vistas.py` (crear) | lista, editar, borrar, estado |
| `tests/budget/test_aportar.py` (crear) | aportar, editar y borrar aportes |
| `tests/budget/test_services.py` (modificar) | la cascada marca `reached` |
| `tests/test_presupuesto_consultas.py:43` (modificar) | `CONSULTAS_METAS` medido de nuevo |
| `tests/test_navegacion.py`, `tests/test_pwa.py` (modificar) | tercera opción del FAB, versión del SW |

Convenciones de prueba que ya existen y se reutilizan:
- `tests/budget/test_views.py` exporta la fixture `admin_con_hogar` (`(user, hogar)` con `crear_hogar`, que siembra categorías) y el helper `_miembro(hogar, **permisos)`. Los archivos nuevos las importan igual que `tests/budget/test_cash_float.py`: `from tests.budget.test_views import admin_con_hogar  # noqa: F401`.
- Factories: `tests.factories` (`HouseholdFactory`, `MembershipFactory`, `UserFactory`) y `tests.factories_budget` (`GoalFactory`, `GoalContributionFactory`, `BudgetMonthFactory`, `AllocationRuleFactory`, `MonthlyAllocationFactory`).
- Constantes de ámbito: `apps.budget.scopes.HOGAR == "household"`, `apps.budget.scopes.PERSONAL == "personal"`; `apps.budget.models.catalog.HOUSEHOLD == "household"`.

---

### Task 1: `services_goals` — aportar y el estado

**Files:**
- Modify: `apps/budget/models/goals.py` (clase `Goal`, tras `__str__`)
- Create: `apps/budget/services_goals.py`
- Test: `tests/budget/test_services_goals.py`

**Interfaces:**
- Produces: `Goal.alcanzada(acumulado: Decimal) -> bool`, `Goal.esta_activa -> bool` (property); `services_goals.aportar(hogar, meta, amount, date, member, origen="manual") -> GoalContribution`; `services_goals.recalcular_estado(meta, acumulado=None) -> bool`; `services_goals.cambiar_estado(meta, nuevo) -> None`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/budget/test_services_goals.py`:

```python
"""El dominio de las metas: aportar, y el estado que se deriva de lo aportado.

`reached` lo pone la aplicacion al cubrir el objetivo; `abandoned` solo el
usuario. Una abandonada no se mueve sola aunque le siga cayendo cascada.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services_goals
from apps.budget.models import BudgetMonth, Goal, GoalContribution, MesCerrado
from tests.factories import HouseholdFactory, MembershipFactory
from tests.factories_budget import BudgetMonthFactory, GoalContributionFactory, GoalFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar():
    return HouseholdFactory()


# --- aportar ------------------------------------------------------------------


def test_aportar_resuelve_el_mes_por_la_fecha(hogar):
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    meta = GoalFactory(household=hogar)
    miembro = MembershipFactory(household=hogar)

    aporte = services_goals.aportar(hogar, meta, Decimal("50.00"), date(2026, 3, 10), miembro)

    assert aporte.budget_month == mes
    assert aporte.member == miembro
    assert aporte.origen == "manual"


def test_aportar_en_un_mes_que_el_hogar_no_vivio_deja_el_mes_nulo(hogar):
    meta = GoalFactory(household=hogar)

    aporte = services_goals.aportar(
        hogar, meta, Decimal("50.00"), date(2025, 1, 10), MembershipFactory(household=hogar)
    )

    assert aporte.budget_month is None


def test_aportar_contra_un_mes_cerrado_revienta_y_no_escribe(hogar):
    BudgetMonthFactory(household=hogar, year=2026, month=3, status=BudgetMonth.CLOSED)
    meta = GoalFactory(household=hogar)

    with pytest.raises(MesCerrado):
        services_goals.aportar(
            hogar, meta, Decimal("50.00"), date(2026, 3, 10), MembershipFactory(household=hogar)
        )

    assert not GoalContribution.objects.for_household(hogar).exists()


def test_el_aporte_que_cubre_el_objetivo_marca_la_meta_alcanzada(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    services_goals.aportar(
        hogar, meta, Decimal("100.00"), date(2026, 3, 1), MembershipFactory(household=hogar)
    )

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


def test_un_aporte_parcial_deja_la_meta_activa(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    services_goals.aportar(
        hogar, meta, Decimal("99.99"), date(2026, 3, 1), MembershipFactory(household=hogar)
    )

    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


# --- recalcular_estado --------------------------------------------------------


def test_recalcular_reabre_una_alcanzada_que_ya_no_lo_esta(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("40.00"))

    assert services_goals.recalcular_estado(meta) is True
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_recalcular_no_toca_una_abandonada_aunque_este_cubierta(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.ABANDONED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))

    assert services_goals.recalcular_estado(meta) is False
    meta.refresh_from_db()
    assert meta.status == Goal.ABANDONED


def test_recalcular_dice_que_nada_cambio_cuando_nada_cambia(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("10.00"))

    assert services_goals.recalcular_estado(meta) is False


def test_recalcular_acepta_el_acumulado_ya_calculado(hogar):
    """Quien pinta la lista ya sumo los aportes: no se vuelve a la base."""
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))

    assert services_goals.recalcular_estado(meta, acumulado=Decimal("100.00")) is True
    assert meta.status == Goal.REACHED


# --- cambiar_estado -----------------------------------------------------------


def test_abandonar_y_reactivar(hogar):
    meta = GoalFactory(household=hogar)

    services_goals.cambiar_estado(meta, Goal.ABANDONED)
    meta.refresh_from_db()
    assert meta.status == Goal.ABANDONED

    services_goals.cambiar_estado(meta, Goal.ACTIVE)
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_reactivar_una_abandonada_ya_cubierta_la_da_por_alcanzada(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.ABANDONED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))

    services_goals.cambiar_estado(meta, Goal.ACTIVE)

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


@pytest.mark.parametrize("desde,hasta", [
    (Goal.ACTIVE, Goal.ACTIVE),
    (Goal.ACTIVE, Goal.REACHED),
    (Goal.REACHED, Goal.ABANDONED),
    (Goal.REACHED, Goal.ACTIVE),
    (Goal.ABANDONED, Goal.REACHED),
    (Goal.ACTIVE, "cualquier-cosa"),
])
def test_las_demas_transiciones_se_rechazan(hogar, desde, hasta):
    meta = GoalFactory(household=hogar, status=desde)

    with pytest.raises(ValueError):
        services_goals.cambiar_estado(meta, hasta)

    meta.refresh_from_db()
    assert meta.status == desde
```

- [ ] **Step 2: Correrlas para ver que fallan**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_services_goals.py -q`
Expected: error de importación `cannot import name 'services_goals'`.

- [ ] **Step 3: Las dos ayudas en `Goal`**

En `apps/budget/models/goals.py`, dentro de `class Goal`, después de `__str__`:

```python
    @property
    def esta_activa(self):
        return self.status == self.ACTIVE

    def alcanzada(self, acumulado):
        """Cubierta con lo aportado. Es lo UNICO que decide `reached`: la
        fecha objetivo no cuenta, una meta tarde sigue activa."""
        return acumulado >= self.target_amount
```

- [ ] **Step 4: El módulo de dominio**

Crear `apps/budget/services_goals.py`:

```python
"""Las metas de ahorro: aportar, y el estado que se deriva de lo aportado.

Vive aparte de `services.py` porque aquel ya mezcla el mes, la cascada y la
mesada; lo de metas cabe en una pantalla y se prueba solo.

`reached` lo pone la aplicacion al cubrir el objetivo; `abandoned` solo el
usuario. Una abandonada no se mueve sola aunque le siga cayendo cascada: la
regla de reparto es del usuario, y quitarla es cosa suya.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from . import services
from .models import AllocationRule, Goal, GoalContribution

# Las transiciones que pide el usuario. active -> reached y reached -> active
# no estan: las decide recalcular_estado a partir de lo aportado.
TRANSICIONES_A_MANO = {
    (Goal.ACTIVE, Goal.ABANDONED),
    (Goal.ABANDONED, Goal.ACTIVE),
}


@transaction.atomic
def aportar(hogar, meta, amount, date, member, origen="manual"):
    """Un aporte con fecha. El mes se resuelve por la fecha y NO se crea: un
    aporte fechado en un mes que el hogar no vivio queda sin mes (y por tanto
    no puede chocar con un cierre). `MesCerrado` sube tal cual."""
    aporte = GoalContribution(
        household=hogar, goal=meta, amount=amount, date=date, member=member,
        origen=origen, budget_month=services.mes_de_fecha(hogar, date),
    )
    aporte.full_clean()
    aporte.save()
    recalcular_estado(meta)
    return aporte


def recalcular_estado(meta, acumulado=None):
    """Solo active <-> reached. Devuelve si cambio.

    `acumulado` se puede pasar ya sumado: quien pinta la lista lo tiene.
    """
    if meta.status == Goal.ABANDONED:
        return False
    if acumulado is None:
        acumulado = meta.acumulado()
    nuevo = Goal.REACHED if meta.alcanzada(acumulado) else Goal.ACTIVE
    if nuevo == meta.status:
        return False
    meta.status = nuevo
    meta.save(update_fields=["status"])
    return True


def cambiar_estado(meta, nuevo):
    """Abandonar o reactivar. Reactivar recalcula: si mientras estaba
    abandonada la cascada la cubrio, vuelve como alcanzada, no como activa."""
    if (meta.status, nuevo) not in TRANSICIONES_A_MANO:
        raise ValueError(f"No se pasa de {meta.status!r} a {nuevo!r}.")
    meta.status = nuevo
    meta.save(update_fields=["status"])
    if nuevo == Goal.ACTIVE:
        recalcular_estado(meta)
```

(`resumen`, `AllocationRule`, `timezone` y `Decimal` se usan en la Tarea 3; dejar los imports ya puestos no rompe nada, pero si ruff protesta por imports sin uso, añadirlos en la Tarea 3.)

- [ ] **Step 5: Correr las pruebas**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_services_goals.py -q`
Expected: 13 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/budget/models/goals.py apps/budget/services_goals.py tests/budget/test_services_goals.py
git commit -m "Metas: aportar y el estado que se deriva de lo aportado

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: La cascada aporta por `services_goals`

**Files:**
- Modify: `apps/budget/services.py:680-694` (dentro de `aplicar_cascada_al_cierre`)
- Test: `tests/budget/test_services.py` (al final del bloque de cascada, tras `test_la_cascada_no_revienta_si_no_hay_membresias_activas`)

**Interfaces:**
- Consumes: `services_goals.aportar(hogar, meta, amount, date, member, origen)`.

- [ ] **Step 1: La prueba que falla**

Añadir a `tests/budget/test_services.py` (comprobar que `Goal` esté importado desde `apps.budget.models`; si no, añadirlo al import existente):

```python
@pytest.mark.django_db
def test_la_cascada_da_por_alcanzada_la_meta_que_cubre():
    """El aporte automatico pasa por el mismo camino que el manual: si cubre
    el objetivo, la meta cambia de estado sin que nadie la mire."""
    hogar = HouseholdFactory()
    MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    meta = GoalFactory(household=hogar, target_amount=Decimal("200.00"))
    AllocationRuleFactory(
        household=hogar, order=1, target_type="goal", target_goal=meta,
        method="fixed", amount=Decimal("200.00"),
    )
    services.planificar_mes(hogar, mes, Decimal("500.00"))

    services.aplicar_cascada_al_cierre(mes, Decimal("500.00"))

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED
```

- [ ] **Step 2: Verla fallar**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_services.py -k "alcanzada_la_meta_que_cubre" -q`
Expected: FAIL, `assert 'active' == 'reached'`.

- [ ] **Step 3: Sustituir la escritura directa**

En `apps/budget/services.py`, el bloque que hoy dice:

```python
        if fila.member_id is None and fila.rule.target_type == motor_cascade.GOAL:
            aporte = GoalContribution(
                household=hogar, goal=fila.rule.target_goal,
                amount=fila.actual_amount, date=_ultimo_dia(mes.year, mes.month),
                # Ahorra el hogar entero, no una persona. Atribuirlo al pk mas
                # bajo era un dato falso en el historial de la meta, y con cero
                # membresias activas reventaba el cierre con IntegrityError.
                member=None,
                budget_month=mes,
                origen="cascade",
            )
            aporte.save()
```

pasa a:

```python
        if fila.member_id is None and fila.rule.target_type == motor_cascade.GOAL:
            # Importado aqui y no arriba: services_goals importa de este
            # modulo (mes_de_fecha), y un import circular en la cabecera
            # reventaria al arrancar.
            from . import services_goals

            # Ahorra el hogar entero, no una persona. Atribuirlo al pk mas
            # bajo era un dato falso en el historial de la meta, y con cero
            # membresias activas reventaba el cierre con IntegrityError.
            # Por services_goals y no a mano para que el aporte que cubre la
            # meta la marque alcanzada igual que uno manual.
            services_goals.aportar(
                hogar, fila.rule.target_goal, fila.actual_amount,
                _ultimo_dia(mes.year, mes.month), member=None, origen="cascade",
            )
```

Si `GoalContribution` deja de usarse en `services.py`, quitarlo del import de `.models`.

- [ ] **Step 4: Correr el bloque de cascada**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_services.py tests/budget/test_mes_cerrado.py -q`
Expected: todo en verde, incluidas `test_la_cascada_aporta_a_la_meta` y `test_el_aporte_de_la_cascada_no_se_atribuye_a_nadie` (el `budget_month` sigue siendo `mes`: `mes_de_fecha` lo encuentra por la fecha del último día).

- [ ] **Step 5: Commit**

```bash
git add apps/budget/services.py tests/budget/test_services.py
git commit -m "La cascada aporta por services_goals y marca la meta alcanzada

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `resumen`, la pantalla por estados y la tarjeta

**Files:**
- Modify: `apps/budget/services_goals.py` (añadir `resumen` y ayudas)
- Modify: `apps/budget/views_goals.py` (`metas` y el helper `_con_aportes`)
- Rewrite: `templates/budget/metas.html`
- Create: `templates/budget/_fragmentos/meta_tarjeta.html`
- Delete: `templates/budget/_fragmentos/aportes.html`
- Modify: `static/css/components.css` (chips y tarjeta apagada), `templates/sw.js`, `tests/test_pwa.py`
- Modify: `tests/test_presupuesto_consultas.py:43`
- Test: `tests/budget/test_services_goals.py`, `tests/budget/test_metas_vistas.py`

**Interfaces:**
- Produces: `services_goals.resumen(hogar, metas, hoy=None) -> list[dict]` con las claves `meta, acumulado, aporte, fecha, meses_restantes, este_mes, porcentaje, porcentaje_barra, tiene_regla, alcanzada_el, aportes (lista de (aporte, editable)), se_puede_borrar`; `views_goals._con_aportes(queryset, hogar)`; la plantilla `budget/_fragmentos/meta_tarjeta.html` que espera `fila` y opcionalmente `oob=True`; el contexto de `metas`: `filas`, `activas`, `alcanzadas`, `abandonadas`, `ambito`.

- [ ] **Step 1: Pruebas de `resumen`**

Añadir al final de `tests/budget/test_services_goals.py`:

```python
# --- resumen ------------------------------------------------------------------

from django.db.models import Prefetch  # noqa: E402

from apps.budget.engine.goals import BY_MONTHLY_AMOUNT  # noqa: E402
from tests.factories_budget import AllocationRuleFactory  # noqa: E402


def _con_aportes(hogar):
    return Goal.objects.for_household(hogar).prefetch_related(
        Prefetch(
            "contributions",
            queryset=GoalContribution.objects.for_household(hogar)
            .select_related("member__user", "budget_month"),
        )
    )


def test_resumen_suma_solo_lo_del_mes_de_hoy_en_este_mes(hogar):
    hoy = date(2026, 9, 20)
    septiembre = BudgetMonthFactory(household=hogar, year=2026, month=9)
    agosto = BudgetMonthFactory(household=hogar, year=2026, month=8)
    meta = GoalFactory(household=hogar, target_amount=Decimal("1000.00"))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"),
                            date=date(2026, 9, 3), budget_month=septiembre)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("70.00"),
                            date=date(2026, 8, 3), budget_month=agosto)

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar), hoy=hoy)

    assert fila["acumulado"] == Decimal("170.00")
    assert fila["este_mes"] == Decimal("100.00")


def test_resumen_sin_mes_vivido_deja_este_mes_a_cero(hogar):
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("10.00"))

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar), hoy=date(2026, 9, 20))

    assert fila["este_mes"] == Decimal("0.00")


def test_resumen_sabe_si_una_regla_de_reparto_la_alimenta(hogar):
    con = GoalFactory(household=hogar)
    sin = GoalFactory(household=hogar)
    AllocationRuleFactory(household=hogar, order=1, target_type="goal", target_goal=con,
                          method="fixed", amount=Decimal("50.00"))
    apagada = GoalFactory(household=hogar)
    AllocationRuleFactory(household=hogar, order=2, target_type="goal", target_goal=apagada,
                          method="fixed", amount=Decimal("50.00"), is_active=False)

    por_meta = {f["meta"].pk: f["tiene_regla"]
                for f in services_goals.resumen(hogar, _con_aportes(hogar))}

    assert por_meta == {con.pk: True, sin.pk: False, apagada.pk: False}


def test_resumen_cuenta_los_meses_que_faltan(hogar):
    meta = GoalFactory(household=hogar, contribution_mode=BY_MONTHLY_AMOUNT,
                       target_amount=Decimal("300.00"), monthly_amount=Decimal("100.00"),
                       target_date=None)

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar), hoy=date(2026, 9, 20))

    # 300 a 100 por mes: hoy, en un mes y en dos -> llega en noviembre.
    assert fila["fecha"] == date(2026, 11, 20)
    assert fila["meses_restantes"] == 2


def test_resumen_marca_que_aportes_se_pueden_tocar(hogar):
    cerrado = BudgetMonthFactory(household=hogar, year=2026, month=3, status=BudgetMonth.CLOSED)
    abierto = BudgetMonthFactory(household=hogar, year=2026, month=9)
    meta = GoalFactory(household=hogar)
    manual_abierto = GoalContributionFactory(household=hogar, goal=meta, date=date(2026, 9, 1),
                                             budget_month=abierto)
    manual_cerrado = GoalContributionFactory(household=hogar, goal=meta, date=date(2026, 3, 1),
                                             budget_month=cerrado)
    sin_mes = GoalContributionFactory(household=hogar, goal=meta, date=date(2020, 1, 1))
    cascada = GoalContribution.unscoped.create(
        household=hogar, goal=meta, amount=Decimal("5.00"), date=date(2026, 9, 30),
        member=None, origen="cascade", budget_month=abierto,
    )

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar))

    editable = {a.pk: e for a, e in fila["aportes"]}
    assert editable == {manual_abierto.pk: True, manual_cerrado.pk: False,
                        sin_mes.pk: True, cascada.pk: False}
    assert fila["se_puede_borrar"] is False


def test_una_meta_sin_cascada_se_puede_borrar(hogar):
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta)

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar))

    assert fila["se_puede_borrar"] is True


def test_resumen_dice_cuando_se_alcanzo(hogar):
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("60.00"), date=date(2026, 1, 1))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("40.00"), date=date(2026, 2, 1))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("25.00"), date=date(2026, 3, 1))

    [fila] = services_goals.resumen(hogar, _con_aportes(hogar))

    assert fila["alcanzada_el"] == date(2026, 2, 1)
    assert fila["porcentaje"] == 125
    assert fila["porcentaje_barra"] == 100


def test_resumen_no_hace_una_consulta_por_meta(hogar, django_assert_num_queries):
    for _i in range(20):
        meta = GoalFactory(household=hogar)
        for _j in range(5):
            GoalContributionFactory(household=hogar, goal=meta)
    metas = list(_con_aportes(hogar))

    # Las reglas de reparto y el mes de hoy: dos, y no crecen con las metas.
    with django_assert_num_queries(2):
        filas = services_goals.resumen(hogar, metas)

    assert len(filas) == 20
```

- [ ] **Step 2: Verlas fallar**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_services_goals.py -k resumen -q`
Expected: `AttributeError: module ... has no attribute 'resumen'`.

- [ ] **Step 3: `resumen` en `services_goals.py`**

Añadir al final de `apps/budget/services_goals.py`:

```python
def resumen(hogar, metas, hoy=None):
    """Lo que la pantalla necesita de cada meta, en una pasada.

    `metas` viene con `contributions` prefetched (con `member__user` y
    `budget_month`): todo lo de aportes se suma en Python. Solo van a la base
    las reglas de reparto (una consulta) y el mes de hoy (otra), y ninguna
    crece con el numero de metas.
    """
    hoy = hoy or timezone.localdate()
    mes_de_hoy = services.mes_de_fecha(hogar, hoy)
    con_regla = set(
        AllocationRule.objects.for_household(hogar)
        .filter(is_active=True, target_goal__isnull=False)
        .values_list("target_goal_id", flat=True)
    )
    filas = []
    for meta in metas:
        aportes = list(meta.contributions.all())
        acumulado = sum((a.amount for a in aportes), Decimal("0.00"))
        aporte, fecha = meta.derivar(desde=hoy, acumulado=acumulado)
        # Dos numeros y no uno: el porcentaje real es un dato ("119%" no es
        # un error), pero la barra se acota a 100 o se sale de su caja.
        bruto = int(acumulado / meta.target_amount * 100) if meta.target_amount else 0
        filas.append({
            "meta": meta,
            "acumulado": acumulado,
            "aporte": aporte,
            "fecha": fecha,
            "meses_restantes": _meses_entre(hoy, fecha),
            "este_mes": sum(
                (a.amount for a in aportes
                 if mes_de_hoy is not None and a.budget_month_id == mes_de_hoy.pk),
                Decimal("0.00"),
            ),
            "porcentaje": bruto,
            "porcentaje_barra": min(100, bruto),
            "tiene_regla": meta.pk in con_regla,
            "alcanzada_el": (_fecha_en_que_se_cubrio(meta, aportes)
                             if meta.status == Goal.REACHED else None),
            "aportes": [(a, _editable(a)) for a in aportes],
            "se_puede_borrar": not any(a.origen == "cascade" for a in aportes),
        })
    return filas


def _editable(aporte):
    """Un aporte manual de un mes que no esta cerrado. El de cascada es del
    cierre, y el de un mes cerrado ya conto en su balance."""
    if aporte.origen != "manual":
        return False
    return aporte.budget_month_id is None or not aporte.budget_month.esta_cerrado


def _fecha_en_que_se_cubrio(meta, aportes):
    """Los aportes vienen del mas reciente al mas viejo (Meta.ordering); se
    recorren al reves acumulando hasta el que la cubrio."""
    total = Decimal("0.00")
    for aporte in reversed(aportes):
        total += aporte.amount
        if meta.alcanzada(total):
            return aporte.date
    return None


def _meses_entre(desde, hasta):
    return max(0, (hasta.year - desde.year) * 12 + hasta.month - desde.month)
```

Confirmar que la cabecera del módulo tiene `from decimal import Decimal`, `from django.utils import timezone` y `AllocationRule` en el import de `.models` (puestos en la Tarea 1).

- [ ] **Step 4: Correr las pruebas de `resumen`**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_services_goals.py -q`
Expected: 21 passed.

- [ ] **Step 5: Pruebas de la pantalla**

Crear `tests/budget/test_metas_vistas.py`:

```python
"""La pantalla de metas: por ambito, por estado, y sus escrituras.

Fuera de test_views.py a proposito: aquel tiene 55 pruebas y ~500 s.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget.models import Goal
from apps.households.models import Membership
from tests.budget.test_views import admin_con_hogar  # noqa: F401
from tests.factories import HouseholdFactory, MembershipFactory
from tests.factories_budget import GoalContributionFactory, GoalFactory

pytestmark = pytest.mark.django_db


def _miembro(hogar, **permisos):
    base = dict(can_view_budget=True, can_edit_budget=False,
                can_add_transactions=True, can_view_reports=False)
    base.update(permisos)
    return MembershipFactory(household=hogar, role=Membership.MEMBER, **base)


def _mia(hogar, user):
    return hogar.memberships.get(user=user)


# --- la lista -----------------------------------------------------------------


def test_household_lista_las_del_hogar_y_personal_solo_las_mias(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    otro = _miembro(hogar)
    del_hogar = GoalFactory(household=hogar, name="Techo nuevo", scope="household")
    mia = GoalFactory(household=hogar, name="Mi bici", scope="personal", owner=_mia(hogar, user))
    ajena = GoalFactory(household=hogar, name="Su consola", scope="personal", owner=otro)
    client.force_login(user)

    hogar_html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    personal_html = client.get(reverse("budget:metas", args=["personal"])).content.decode()

    assert del_hogar.name in hogar_html and mia.name not in hogar_html
    assert mia.name in personal_html and del_hogar.name not in personal_html
    assert ajena.name not in hogar_html and ajena.name not in personal_html


def test_la_lista_agrupa_por_estado(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    activa = GoalFactory(household=hogar, name="Activa")
    alcanzada = GoalFactory(household=hogar, name="Alcanzada", status=Goal.REACHED)
    abandonada = GoalFactory(household=hogar, name="Abandonada", status=Goal.ABANDONED)
    client.force_login(user)

    respuesta = client.get(reverse("budget:metas", args=["household"]))

    contexto = respuesta.context
    assert [f["meta"] for f in contexto["activas"]] == [activa]
    assert [f["meta"] for f in contexto["alcanzadas"]] == [alcanzada]
    assert [f["meta"] for f in contexto["abandonadas"]] == [abandonada]
    html = respuesta.content.decode()
    assert "Reached" in html and "Abandoned" in html


def test_una_meta_alcanzada_dice_cuando_y_no_pide_mas(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"),
                            date=date(2026, 2, 14))
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert "You got there" in html
    assert "Put in" not in html


def test_una_meta_de_hogar_sin_regla_lo_dice_y_una_personal_tambien(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    GoalFactory(household=hogar, scope="household")
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert "add a split rule" in html

    GoalFactory(household=hogar, scope="personal", owner=_mia(hogar, user))
    html = client.get(reverse("budget:metas", args=["personal"])).content.decode()
    assert "only manual contributions" in html


def test_los_aportes_de_cascada_se_distinguen(client, admin_con_hogar):
    from apps.budget.models import GoalContribution

    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    GoalContribution.unscoped.create(
        household=hogar, goal=meta, amount=Decimal("50.00"), date=date(2026, 3, 31),
        member=None, origen="cascade",
    )
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert "From the monthly split" in html


def test_una_meta_de_otro_hogar_no_aparece(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    GoalFactory(household=HouseholdFactory(), name="De otra familia")
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert "De otra familia" not in html
```

- [ ] **Step 6: Verlas fallar**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_metas_vistas.py -q`
Expected: fallan por `KeyError: 'activas'` y por textos que no están.

- [ ] **Step 7: La vista `metas`**

Reescribir `apps/budget/views_goals.py` (las vistas `meta_nueva` y `aportar` se quedan como están por ahora; `aportar` se rehace en la Tarea 5):

```python
"""Las metas de ahorro: verlas, crearlas, corregirlas y aportar.

`metas` lleva ambito porque Goal tiene `scope` y `owner`: una meta personal es
de su dueno y no del hogar. Las escrituras no lo llevan: la fila ya sabe su
ambito, y a el se vuelve.
"""

from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services, services_goals
from .forms import GoalContributionForm, GoalForm
from .models import Goal, GoalContribution, MesCerrado
from .scopes import acotar_por_dueno, validar
from .views_setup import crear


def _con_aportes(queryset, hogar):
    """Los aportes de cada meta en UNA consulta, con quien los hizo y su mes:
    resumen() suma en Python y decide que aporte se puede tocar sin volver a
    la base."""
    return queryset.prefetch_related(
        Prefetch(
            "contributions",
            queryset=GoalContribution.objects.for_household(hogar)
            .select_related("member__user", "budget_month"),
        )
    )


@requiere_permiso("can_view_budget")
def metas(request, hogar, ambito):
    ambito = validar(ambito)
    membresia = membresia_actual(request)
    consulta = _con_aportes(
        acotar_por_dueno(Goal.objects.for_household(hogar), ambito, membresia), hogar
    )
    filas = services_goals.resumen(hogar, consulta)
    por_estado = {Goal.ACTIVE: [], Goal.REACHED: [], Goal.ABANDONED: []}
    for fila in filas:
        por_estado[fila["meta"].status].append(fila)
    return render(request, "budget/metas.html", {
        # `filas` sigue existiendo: las pruebas de Tarea 21 leen de ahi.
        "filas": filas, "ambito": ambito,
        "activas": por_estado[Goal.ACTIVE],
        "alcanzadas": por_estado[Goal.REACHED],
        "abandonadas": por_estado[Goal.ABANDONED],
    })


@requiere_permiso("can_edit_budget")
def meta_nueva(request, hogar):
    return crear(request, hogar, GoalForm, _("New goal"),
                 destino="budget:metas", destino_args=("household",))


@requiere_permiso("can_edit_budget")
def aportar(request, hogar):
    """Mismo patron que `registrar`, para no inventar un segundo."""
    es_htmx = request.headers.get("HX-Request") == "true"
    form = GoalContributionForm(request.POST or None, household=hogar)
    if request.method == "POST" and form.is_valid():
        aporte = form.save(commit=False)
        aporte.household = hogar
        aporte.member = membresia_actual(request)
        aporte.budget_month = services.mes_de_fecha(hogar, aporte.date)
        try:
            aporte.full_clean()
            aporte.save()
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        else:
            return redirect("budget:metas", "household")

    plantilla = ("budget/_fragmentos/aporte_form.html" if es_htmx
                 else "budget/formulario.html")
    return render(request, plantilla, {"form": form, "titulo": _("Add to a goal")})
```

(Se quita de `aportar` la respuesta htmx con `aportes.html`, que se borra en este paso; la respuesta htmx buena vuelve en la Tarea 5.)

- [ ] **Step 8: La tarjeta**

Crear `templates/budget/_fragmentos/meta_tarjeta.html`:

```django
{% load i18n money %}
{% comment %} Una meta. Lleva id para que, al aportar desde el modal del [+],
   la vista devuelva ESTA tarjeta fuera de banda y htmx la sustituya en Metas;
   en cualquier otra pantalla no hay un id que case y se ignora, como los
   movimientos recientes del gasto. Las acciones (editar, quitar, abandonar,
   aportar) las anaden las tareas siguientes. {% endcomment %}
<section id="meta-{{ fila.meta.pk }}"
         class="card{% if fila.meta.status == 'abandoned' %} card--apagada{% endif %}"
         {% if oob %}hx-swap-oob="true"{% endif %}>
  <header class="meta__cabecera">
    <h2>
      {{ fila.meta.name }}
      {% if fila.meta.status == 'reached' %}
        <span class="chip chip--alcanzada">{% translate "Reached" %}</span>
      {% elif fila.meta.status == 'abandoned' %}
        <span class="chip chip--abandonada">{% translate "Abandoned" %}</span>
      {% endif %}
    </h2>
  </header>

  <div class="progreso">
    <div class="progreso__relleno" style="width: {{ fila.porcentaje_barra }}%"></div>
  </div>
  <p>
    {% blocktranslate with hecho=fila.acumulado|money:hogar.currency objetivo=fila.meta.target_amount|money:hogar.currency pct=fila.porcentaje %}{{ hecho }} of {{ objetivo }} — {{ pct }}%{% endblocktranslate %}
  </p>

  {% if fila.meta.status == 'reached' %}
    <p class="meta__logro">
      {% if fila.alcanzada_el %}
        {% blocktranslate with cuando=fila.alcanzada_el|date:"j F Y" %}You got there on {{ cuando }} 🎉{% endblocktranslate %}
      {% else %}
        {% translate "You got there 🎉" %}
      {% endif %}
    </p>
  {% elif fila.meta.status == 'active' %}
    {% if fila.meta.contribution_mode == "by_target_date" %}
      <p>{% blocktranslate with importe=fila.aporte|money:hogar.currency cuando=fila.fecha|date:"F Y" %}Put in {{ importe }} a month to get there by {{ cuando }}.{% endblocktranslate %}</p>
    {% else %}
      <p>{% blocktranslate count meses=fila.meses_restantes with cuando=fila.fecha|date:"F Y" %}At this rate you get there in {{ meses }} month · {{ cuando }}.{% plural %}At this rate you get there in {{ meses }} months · {{ cuando }}.{% endblocktranslate %}</p>
    {% endif %}
    <p class="meta__este-mes{% if fila.este_mes >= fila.aporte %} meta__este-mes--al-dia{% endif %}">
      {% blocktranslate with hecho=fila.este_mes|money:hogar.currency sugerido=fila.aporte|money:hogar.currency %}This month: {{ hecho }} of the {{ sugerido }} suggested{% endblocktranslate %}
    </p>
    {% if fila.meta.scope == "personal" %}
      <p class="meta__aviso">{% translate "Personal goal: only manual contributions." %}</p>
    {% elif not fila.tiene_regla %}
      <p class="meta__aviso">
        {% translate "Nothing feeds this goal automatically —" %}
        <a href="{% url 'budget:reparto_nuevo' %}?target_type=goal&amp;target_goal={{ fila.meta.pk }}">{% translate "add a split rule" %}</a>
      </p>
    {% endif %}
  {% elif fila.tiene_regla %}
    <p class="meta__aviso">{% translate "A split rule still feeds it — remove it in Budget setup." %}</p>
  {% endif %}

  <h3>{% translate "Contributions" %}</h3>
  {% if fila.aportes %}
    <div class="tabla__envoltura">
      <table class="tabla">
        {% for aporte, editable in fila.aportes|slice:":5" %}
          {% include "budget/_fragmentos/meta_aporte_fila.html" %}
        {% endfor %}
      </table>
      {% if fila.aportes|length > 5 %}
        <details>
          <summary>{% translate "Show all" %}</summary>
          <table class="tabla">
            {% for aporte, editable in fila.aportes|slice:"5:" %}
              {% include "budget/_fragmentos/meta_aporte_fila.html" %}
            {% endfor %}
          </table>
        </details>
      {% endif %}
    </div>
  {% else %}
    <p class="texto--sutil">{% translate "Nothing yet." %}</p>
  {% endif %}
</section>
```

Crear `templates/budget/_fragmentos/meta_aporte_fila.html` (la fila de un aporte; las acciones llegan en la Tarea 7):

```django
{% load i18n money %}
<tr>
  <td>{{ aporte.date }}</td>
  <td>
    {% if aporte.origen == "cascade" %}{% translate "From the monthly split" %}
    {% elif aporte.member %}{{ aporte.member.user }}
    {% else %}{% translate "The household" %}{% endif %}
  </td>
  <td class="numero">{{ aporte.amount|money:hogar.currency }}</td>
</tr>
```

Borrar `templates/budget/_fragmentos/aportes.html`.

- [ ] **Step 9: La pantalla**

Reescribir `templates/budget/metas.html`:

```django
{% extends "base.html" %}{% load i18n %}
{% block title %}{% translate "Goals" %} · Wealthome{% endblock %}
{% block content %}
<header class="pagina__cabecera">
  <h1>{% translate "Goals" %}</h1>
  {% if nav_membresia.can_edit_budget and nav_puede_escribir %}
    <div class="pagina__acciones">
      <a class="btn btn--primary" href="{% url 'budget:meta_nueva' %}">{% translate "New goal" %}</a>
    </div>
  {% endif %}
</header>

{% for fila in activas %}
  {% include "budget/_fragmentos/meta_tarjeta.html" %}
{% empty %}
  {% if not alcanzadas and not abandonadas %}
    <section class="card card--ancho"><p>{% translate "No goals yet." %}</p></section>
  {% endif %}
{% endfor %}

{% if alcanzadas %}
  <h2 class="seccion__titulo">{% translate "Reached" %}</h2>
  {% for fila in alcanzadas %}{% include "budget/_fragmentos/meta_tarjeta.html" %}{% endfor %}
{% endif %}

{% if abandonadas %}
  <h2 class="seccion__titulo">{% translate "Abandoned" %}</h2>
  {% for fila in abandonadas %}{% include "budget/_fragmentos/meta_tarjeta.html" %}{% endfor %}
{% endif %}
{% endblock %}
```

- [ ] **Step 10: CSS**

En `static/css/components.css`, tras el bloque `.progreso` (línea ~119):

```css
/* ---------- metas ----------
   El chip de estado va dentro del h2 para que no ocupe una linea propia; la
   tarjeta abandonada se atenua entera, no se esconde: sigue siendo un dato. */
.chip {
  display: inline-block; margin-left: 8px; padding: 2px 10px; border-radius: 999px;
  font-size: 0.7em; font-weight: 600; letter-spacing: 0.02em; vertical-align: middle;
}
.chip--alcanzada { background: var(--accent); color: var(--on-accent, #fff); }
.chip--abandonada { background: var(--surface-2, rgba(0,0,0,0.08)); color: var(--text-muted); }
.card--apagada { opacity: 0.6; }
.card--apagada:hover, .card--apagada:focus-within { opacity: 1; }
.meta__cabecera { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.meta__cabecera h2 { margin: 0 0 12px; }
.meta__logro { font-weight: 600; }
.meta__este-mes { font-variant-numeric: tabular-nums; }
.meta__este-mes--al-dia { color: var(--accent); font-weight: 600; }
.meta__aviso { color: var(--text-muted); font-size: 0.9em; }
.seccion__titulo { grid-column: 1 / -1; margin: 8px 0 -8px; font-size: 1em; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; }
```

Antes de usar `--on-accent`, `--surface-2` y `--text-muted`, comprobar en `static/css/tokens.css` (o donde vivan los tokens: `grep -rn "\-\-text-muted\|\-\-accent:" static/css/`) cuáles existen y usar los nombres reales; los `var(..., fallback)` de arriba son para no depender de ello.

Subir `VERSION` en `templates/sw.js` a `wealthome-v14` y los dos `paginas-wealthome-v13` de `tests/test_pwa.py` a `v14`.

- [ ] **Step 11: Correr las pruebas de la pantalla y las viejas**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_metas_vistas.py tests/budget/test_views.py -k "meta or metas or aport" tests/test_pwa.py -q`
Expected: verde. Si `test_las_metas_muestran_su_dato_derivado_de_verdad` o `test_una_meta_sobrepasada_no_desborda_la_barra` fallan, es por las claves de `filas`: tienen que seguir siendo `acumulado`, `porcentaje`, `porcentaje_barra`, `fecha`.

- [ ] **Step 12: Medir el tope de consultas**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/test_presupuesto_consultas.py -k metas -q`
Expected: FAIL con el número real (debería ser 8: las 6 de antes + reglas de reparto + mes de hoy). Poner ese número en `CONSULTAS_METAS` y añadir al comentario que lo precede:

```python
# SUBIDO de 6 a 8 con la tarjeta nueva: resumen() lee las reglas de reparto
# (para decir que alimenta cada meta) y el mes de hoy (para "This month"), una
# consulta cada una y ninguna crece con las metas. Medido con cinco y con
# veinte: test_resumen_no_hace_una_consulta_por_meta lo vigila.
```

Volver a correr: verde.

- [ ] **Step 13: Commit**

```bash
git add apps/budget/services_goals.py apps/budget/views_goals.py templates/budget/metas.html templates/budget/_fragmentos/meta_tarjeta.html templates/budget/_fragmentos/meta_aporte_fila.html static/css/components.css templates/sw.js tests/
git rm templates/budget/_fragmentos/aportes.html
git commit -m "Metas por estado: la tarjeta dice como va el mes y que la alimenta

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Los formularios

**Files:**
- Modify: `apps/budget/forms.py:299-317`
- Test: `tests/budget/test_aportar.py` (crear), `tests/budget/test_metas_vistas.py`

**Interfaces:**
- Produces: `GoalContributionForm(data, household=, membresia=, instance=None, initial=None)` con `goal` acotado a metas activas visibles (más la de la instancia al editar) y `clean_date` que rechaza el futuro; `GoalForm` con `scope` y `owner` `disabled` cuando la instancia tiene aportes.

- [ ] **Step 1: Pruebas que fallan**

Crear `tests/budget/test_aportar.py`:

```python
"""Aportar a una meta, y corregir o quitar un aporte.

Un aporte es un registro como un gasto: quien lo teclea puede equivocarse.
El de la cascada no: lo escribio el cierre del mes y cuadra con el reparto.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget.forms import GoalContributionForm
from apps.budget.models import Goal
from apps.households.models import Membership
from tests.budget.test_views import admin_con_hogar  # noqa: F401
from tests.factories import MembershipFactory
from tests.factories_budget import GoalFactory

pytestmark = pytest.mark.django_db


def _miembro(hogar, **permisos):
    base = dict(can_view_budget=True, can_edit_budget=True,
                can_add_transactions=True, can_view_reports=False)
    base.update(permisos)
    return MembershipFactory(household=hogar, role=Membership.MEMBER, **base)


def _mia(hogar, user):
    return hogar.memberships.get(user=user)


# --- el formulario ------------------------------------------------------------


def test_el_formulario_solo_ofrece_metas_activas_que_puedo_ver(admin_con_hogar):
    user, hogar = admin_con_hogar
    yo = _mia(hogar, user)
    otro = _miembro(hogar)
    del_hogar = GoalFactory(household=hogar, scope="household")
    mia = GoalFactory(household=hogar, scope="personal", owner=yo)
    GoalFactory(household=hogar, scope="personal", owner=otro)
    GoalFactory(household=hogar, status=Goal.REACHED)
    GoalFactory(household=hogar, status=Goal.ABANDONED)

    form = GoalContributionForm(household=hogar, membresia=yo)

    assert set(form.fields["goal"].queryset) == {del_hogar, mia}


def test_al_editar_el_formulario_conserva_la_meta_aunque_ya_no_este_activa(admin_con_hogar):
    from tests.factories_budget import GoalContributionFactory

    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, status=Goal.REACHED)
    aporte = GoalContributionFactory(household=hogar, goal=meta)

    form = GoalContributionForm(household=hogar, membresia=_mia(hogar, user), instance=aporte)

    assert meta in form.fields["goal"].queryset


def test_una_fecha_futura_se_rechaza(admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    manana = timezone.localdate() + timedelta(days=1)

    form = GoalContributionForm(
        {"goal": meta.pk, "amount": "10.00", "date": manana.isoformat()},
        household=hogar, membresia=_mia(hogar, user),
    )

    assert not form.is_valid()
    assert "date" in form.errors


def test_un_importe_de_cero_se_rechaza(admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)

    form = GoalContributionForm(
        {"goal": meta.pk, "amount": "0.00", "date": "2026-03-01"},
        household=hogar, membresia=_mia(hogar, user),
    )

    assert not form.is_valid()
    assert "amount" in form.errors
```

Y añadir a `tests/budget/test_metas_vistas.py`:

```python
# --- el formulario de meta ----------------------------------------------------


def test_el_ambito_de_una_meta_con_aportes_no_se_cambia(admin_con_hogar):
    from apps.budget.forms import GoalForm

    _user, hogar = admin_con_hogar
    con = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=con)
    sin = GoalFactory(household=hogar)

    assert GoalForm(household=hogar, instance=con).fields["scope"].disabled is True
    assert GoalForm(household=hogar, instance=con).fields["owner"].disabled is True
    assert GoalForm(household=hogar, instance=sin).fields["scope"].disabled is False
```

- [ ] **Step 2: Verlas fallar**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_aportar.py tests/budget/test_metas_vistas.py -k "formulario or ambito_de_una_meta" -q`
Expected: `TypeError: __init__() got an unexpected keyword argument 'membresia'` y `assert False is True`.

- [ ] **Step 3: Los formularios**

En `apps/budget/forms.py`, sustituir `GoalForm` y `GoalContributionForm`:

```python
class GoalForm(HouseholdScopedModelForm):
    class Meta:
        model = Goal
        fields = ["name", "scope", "owner", "contribution_mode",
                  "target_amount", "target_date", "monthly_amount"]
        widgets = {"target_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = self.household.active_memberships()
        self.fields["owner"].required = False
        # Con aportes, el ambito se queda: un aporte a una meta del hogar lo
        # hizo cualquiera, y el de una personal tiene que ser de su dueno.
        # Cambiarlo dejaria aportes que no cuadran con la meta.
        if self.instance.pk and self.instance.contributions.exists():
            self.fields["scope"].disabled = True
            self.fields["owner"].disabled = True


class GoalContributionForm(HouseholdScopedModelForm):
    """`member` y `budget_month` NO son campos: salen de la peticion y de la
    fecha, como en TransactionForm."""

    class Meta:
        model = GoalContribution
        fields = ["goal", "amount", "date"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, membresia, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo a lo que se puede aportar: las metas activas del hogar y las
        # personales propias. Acota el render Y la validacion. Al editar, la
        # meta del aporte entra aunque ya este alcanzada: corregir un aporte
        # no es aportar.
        visibles = Q(scope=HOUSEHOLD) | Q(scope=PERSONAL, owner=membresia)
        activas = Q(status=Goal.ACTIVE)
        if self.instance.pk:
            activas |= Q(pk=self.instance.goal_id)
        self.fields["goal"].queryset = (
            Goal.objects.for_household(self.household).filter(visibles & activas)
        )

    def clean_date(self):
        fecha = self.cleaned_data["date"]
        if fecha > timezone.localdate():
            raise forms.ValidationError(_("A contribution cannot be dated in the future."))
        return fecha
```

Comprobar los imports en la cabecera de `forms.py`: `from django.db.models import Q`, `from django.utils import timezone`, y `HOUSEHOLD`, `PERSONAL` desde `.models.catalog` (o desde donde ya los importe el módulo: `grep -n "^from\|^import" apps/budget/forms.py`). `_` ya está importado como `gettext_lazy`.

Si `test_un_importe_de_cero_se_rechaza` falla porque `MoneyField` admite cero, añadir a `GoalContributionForm`:

```python
    def clean_amount(self):
        importe = self.cleaned_data["amount"]
        if importe is not None and importe <= 0:
            raise forms.ValidationError(_("Put in more than zero."))
        return importe
```

- [ ] **Step 4: Correr**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_aportar.py tests/budget/test_metas_vistas.py -q`
Expected: las del formulario en verde; la vista `aportar` de la Tarea 3 sigue llamando a `GoalContributionForm` sin `membresia`, así que **cualquier prueba que pase por `aportar` fallará con `TypeError` hasta la Tarea 5** — es esperado. Corregir provisionalmente `views_goals.aportar` para pasar `membresia=membresia_actual(request)` y que `tests/budget/test_views.py::test_aportar_a_una_meta_exige_can_edit_budget` siga en verde.

- [ ] **Step 5: Commit**

```bash
git add apps/budget/forms.py apps/budget/views_goals.py tests/budget/test_aportar.py tests/budget/test_metas_vistas.py
git commit -m "El formulario de aporte solo ofrece metas activas visibles y no acepta fechas futuras

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Aportar desde la tarjeta y desde el `[+]`

**Files:**
- Modify: `apps/budget/views_goals.py` (`aportar`, helper `_fila`)
- Rewrite: `templates/budget/_fragmentos/aporte_form.html`
- Modify: `templates/budget/_fragmentos/meta_tarjeta.html` (botón "Add to it")
- Modify: `templates/_fab.html` (tercera opción), `static/css/modules.css` (color de la opción)
- Test: `tests/budget/test_aportar.py`, `tests/test_navegacion.py`

**Interfaces:**
- Consumes: `services_goals.aportar`, `services_goals.resumen`, `_con_aportes`.
- Produces: `aportar` responde a htmx con `aporte_form.html` (título OOB, form limpio, tarjeta OOB) y cabecera `HX-Trigger: gasto-registrado`; sin htmx redirige a `budget:metas` del ámbito de la meta; acepta `?goal=<pk>`.

- [ ] **Step 1: Pruebas que fallan**

Añadir a `tests/budget/test_aportar.py`:

```python
# --- aportar ------------------------------------------------------------------

HTMX = {"HTTP_HX_REQUEST": "true"}


def test_aportar_exige_can_edit_budget(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_edit_budget=False).user)

    assert client.get(reverse("budget:aportar")).status_code == 403
    assert client.post(reverse("budget:aportar"), {}).status_code == 403


def test_por_htmx_llega_el_fragmento_con_el_titulo_fuera_de_banda(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    GoalFactory(household=hogar)
    client.force_login(user)

    html = client.get(reverse("budget:aportar"), **HTMX).content.decode()

    assert 'id="modal-gasto-titulo" hx-swap-oob="true"' in html
    assert "Add to a goal" in html
    assert "hx-post" in html
    assert "<html" not in html


def test_sin_metas_activas_el_fragmento_lo_dice_en_vez_de_un_select_vacio(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    GoalFactory(household=hogar, status=Goal.REACHED)
    client.force_login(user)

    html = client.get(reverse("budget:aportar"), **HTMX).content.decode()

    assert "No active goals yet" in html
    assert reverse("budget:meta_nueva") in html
    assert "<select" not in html


def test_goal_en_la_query_preselecciona_la_meta(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    respuesta = client.get(reverse("budget:aportar") + f"?goal={meta.pk}", **HTMX)

    assert respuesta.context["form"]["goal"].value() == meta.pk


def test_un_aporte_por_htmx_devuelve_la_tarjeta_fuera_de_banda_y_cierra_el_modal(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("1000.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aportar"), {
        "goal": meta.pk, "amount": "150.00", "date": timezone.localdate().isoformat(),
    }, **HTMX)

    assert respuesta.status_code == 200
    assert respuesta["HX-Trigger"] == "gasto-registrado"
    html = respuesta.content.decode()
    assert f'id="meta-{meta.pk}"' in html and "hx-swap-oob" in html
    assert "150" in html
    aporte = meta.contributions.get()
    assert aporte.member == _mia(hogar, user)
    assert aporte.origen == "manual"
    # Y el formulario vuelve limpio, con la fecha de hoy.
    assert respuesta.context["form"]["date"].value() == timezone.localdate()


def test_un_aporte_por_la_pagina_entera_vuelve_a_metas_del_ambito(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, scope="personal", owner=_mia(hogar, user))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aportar"), {
        "goal": meta.pk, "amount": "20.00", "date": timezone.localdate().isoformat(),
    })

    assert respuesta.status_code == 302
    assert respuesta["Location"] == reverse("budget:metas", args=["personal"])


def test_aportar_a_la_meta_personal_de_otro_se_rechaza(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    ajena = GoalFactory(household=hogar, scope="personal", owner=_miembro(hogar))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aportar"), {
        "goal": ajena.pk, "amount": "20.00", "date": timezone.localdate().isoformat(),
    })

    assert respuesta.status_code == 200
    assert "goal" in respuesta.context["form"].errors
    assert not ajena.contributions.exists()


def test_aportar_en_un_mes_cerrado_lo_dice_el_formulario(client, admin_con_hogar):
    from apps.budget.models import BudgetMonth
    from tests.factories_budget import BudgetMonthFactory

    user, hogar = admin_con_hogar
    BudgetMonthFactory(household=hogar, year=2026, month=1, status=BudgetMonth.CLOSED)
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    respuesta = client.post(reverse("budget:aportar"), {
        "goal": meta.pk, "amount": "20.00", "date": "2026-01-15",
    })

    assert respuesta.status_code == 200
    assert "This month is already closed." in respuesta.content.decode()
    assert not meta.contributions.exists()


def test_la_tarjeta_activa_ofrece_aportar_y_la_alcanzada_no(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    activa = GoalFactory(household=hogar)
    GoalFactory(household=hogar, status=Goal.REACHED)
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert html.count("Add to it") == 1
    assert f"?goal={activa.pk}" in html
```

Y en `tests/test_navegacion.py`, junto a `test_el_fab_llega_al_html_solo_cuando_toca` (leer ese test para copiar cómo siembra el hogar y hace login):

```python
def test_el_selector_del_fab_ofrece_aportar_a_una_meta(client):
    """Tercera opcion siempre: sin metas activas es el formulario quien lo
    dice, y el menu no paga una consulta por pagina para saberlo."""
    # <sembrar y loguear un admin con can_add_transactions, como el test de al lado>
    cuerpo = client.get(reverse("budget:overview", args=["household"])).content.decode()

    assert "selector__opcion--meta" in cuerpo
    assert reverse("budget:aportar") in cuerpo
```

- [ ] **Step 2: Verlas fallar**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_aportar.py -q`
Expected: fallan las de `aportar` (sin `HX-Trigger`, sin tarjeta, `Location` a household, sin "Add to it").

- [ ] **Step 3: La vista**

En `apps/budget/views_goals.py`, sustituir `aportar` y añadir `_fila`:

```python
from django.urls import reverse
from django.utils import timezone


def _fila(hogar, meta):
    """La fila de resumen() de UNA meta, para devolver su tarjeta."""
    consulta = _con_aportes(Goal.objects.for_household(hogar).filter(pk=meta.pk), hogar)
    return services_goals.resumen(hogar, consulta)[0]


@requiere_permiso("can_edit_budget")
def aportar(request, hogar):
    """Mismo patron que `registrar`: por htmx devuelve el fragmento y, al
    guardar, el formulario limpio con la tarjeta de la meta FUERA DE BANDA
    (solo Metas tiene ese id; desde otra pantalla htmx la ignora) y la
    cabecera que cierra el modal. Sin htmx, la pagina entera y de vuelta a
    Metas del ambito de la meta."""
    es_htmx = request.headers.get("HX-Request") == "true"
    membresia = membresia_actual(request)
    hoy = timezone.localdate()
    initial = {"date": hoy}
    if request.GET.get("goal", "").isdigit():
        initial["goal"] = int(request.GET["goal"])
    form = GoalContributionForm(request.POST or None, household=hogar,
                                membresia=membresia, initial=initial)
    contexto = {"titulo": _("Add to a goal"),
                "cancelar": reverse("budget:metas", args=["household"])}
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            aporte = services_goals.aportar(
                hogar, datos["goal"], datos["amount"], datos["date"], membresia
            )
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        else:
            if es_htmx:
                limpio = GoalContributionForm(household=hogar, membresia=membresia,
                                              initial={"date": hoy})
                respuesta = render(request, "budget/_fragmentos/aporte_form.html", {
                    "form": limpio, "tarjeta_oob": _fila(hogar, aporte.goal), **contexto,
                })
                respuesta["HX-Trigger"] = "gasto-registrado"
                return respuesta
            return redirect("budget:metas", aporte.goal.scope)

    plantilla = ("budget/_fragmentos/aporte_form.html" if es_htmx
                 else "budget/formulario.html")
    return render(request, plantilla, {
        "form": form, "sin_metas": not form.fields["goal"].queryset.exists(), **contexto,
    })
```

`sin_metas` cuesta una consulta `exists()` solo al pintar el formulario, no por página.

- [ ] **Step 4: El fragmento**

Reescribir `templates/budget/_fragmentos/aporte_form.html`:

```django
{% load i18n %}
{% comment %} Como gasto_form.html: el titulo del modal viaja fuera de banda,
   el formulario se sustituye a si mismo, y tras guardar la vista manda la
   tarjeta de la meta tambien fuera de banda para que Metas se refresque sin
   recargar. Sin metas activas no hay <select> que ensenar: se dice y se
   ofrece crear una. {% endcomment %}
<h2 id="modal-gasto-titulo" hx-swap-oob="true">{{ titulo }}</h2>
{% if sin_metas %}
  <div class="formulario">
    <p>{% translate "No active goals yet." %}</p>
    <a class="btn btn--primary" href="{% url 'budget:meta_nueva' %}">{% translate "New goal" %}</a>
  </div>
{% else %}
<form class="formulario" hx-post="{% url 'budget:aportar' %}"
      hx-target="this" hx-swap="outerHTML">
  {% csrf_token %}
  {% include "budget/_fragmentos/campos.html" %}
  <div class="formulario__acciones">
    <button class="btn btn--primary" type="submit">{% translate "Add it" %}</button>
    <button class="btn btn--sutil" type="button" onclick="abrirSelectorDeRegistro()">
      {% translate "Back" %}
    </button>
  </div>
</form>
{% endif %}
{% if tarjeta_oob %}
  {% include "budget/_fragmentos/meta_tarjeta.html" with fila=tarjeta_oob oob=True %}
{% endif %}
```

`budget/formulario.html` (página entera) no sabe de `sin_metas`: con el `<select>` vacío el usuario ve "New goal" en Metas, de donde viene; aceptable.

- [ ] **Step 5: El botón en la tarjeta**

En `templates/budget/_fragmentos/meta_tarjeta.html`, dentro del bloque `{% elif fila.meta.status == 'active' %}`, justo antes de su `{% if fila.meta.scope == "personal" %}`:

```django
    {% if nav_membresia.can_edit_budget and nav_puede_escribir %}
      <p>
        {% comment %} Sin JS lleva a la pagina entera del aporte con la meta
           puesta. Con el modal del [+] presente, pide el formulario por htmx
           al cuerpo del modal y lo abre, como las opciones del selector. {% endcomment %}
        <a class="btn btn--primary" href="{% url 'budget:aportar' %}?goal={{ fila.meta.pk }}"
           {% if nav_fab %}hx-get="{% url 'budget:aportar' %}?goal={{ fila.meta.pk }}"
           hx-target="#modal-gasto-cuerpo" hx-swap="innerHTML"
           onclick="document.getElementById('modal-gasto').showModal()"{% endif %}>
          {% translate "Add to it" %}
        </a>
      </p>
    {% endif %}
```

- [ ] **Step 6: La tercera opción del selector**

En `templates/_fab.html`, dentro de `<template id="modal-gasto-selector">`, tras el botón del ingreso:

```django
    <button class="selector__opcion selector__opcion--meta" type="button"
            hx-get="{% url 'budget:aportar' %}"
            hx-target="#modal-gasto-cuerpo" hx-swap="innerHTML">
      <span class="selector__icono" aria-hidden="true">◎</span>
      <span class="selector__texto">{% translate "A goal contribution" %}</span>
      <span class="selector__pista">{% translate "Money you set aside" %}</span>
    </button>
```

Y en `static/css/modules.css`, tras `.selector__opcion--ingreso .selector__icono`:

```css
.selector__opcion--meta .selector__icono { background: var(--accent-2, var(--accent)); }
```

(Comprobar el nombre real del segundo acento en los tokens; si no hay, dejar `var(--accent)` con `filter: saturate(0.7)`.)

- [ ] **Step 7: Correr**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_aportar.py tests/budget/test_metas_vistas.py tests/test_navegacion.py -k "aport or selector or metas" -q`
Expected: verde.

- [ ] **Step 8: Commit**

```bash
git add apps/budget/views_goals.py templates/budget/_fragmentos/aporte_form.html templates/budget/_fragmentos/meta_tarjeta.html templates/_fab.html static/css/modules.css tests/
git commit -m "Aportar a una meta desde su tarjeta y desde el selector del [+]

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Editar, borrar y cambiar el estado de una meta

**Files:**
- Modify: `apps/budget/views_goals.py` (`_meta`, `meta_editar`, `meta_borrar`, `meta_estado`)
- Modify: `apps/budget/urls.py:33-34`
- Create: `templates/budget/_fragmentos/acciones_icono.html`
- Modify: `templates/budget/_fragmentos/acciones_registro.html` (pasa a incluir el anterior)
- Modify: `templates/budget/_fragmentos/meta_tarjeta.html` (cabecera con acciones; Abandon / Reactivate)
- Test: `tests/budget/test_metas_vistas.py`

**Interfaces:**
- Produces: rutas `budget:meta_editar (pk)`, `budget:meta_borrar (pk)`, `budget:meta_estado (pk, estado)`; fragmento `acciones_icono.html` con variables `editar_url`, `borrar_url` (vacía = sin botón de quitar) y `confirmacion`.

- [ ] **Step 1: Pruebas que fallan**

Añadir a `tests/budget/test_metas_vistas.py`:

```python
# --- editar, borrar, estado ---------------------------------------------------


def _datos(meta, **cambios):
    base = {
        "name": meta.name, "scope": meta.scope, "owner": meta.owner_id or "",
        "contribution_mode": meta.contribution_mode,
        "target_amount": str(meta.target_amount),
        "target_date": meta.target_date.isoformat() if meta.target_date else "",
        "monthly_amount": str(meta.monthly_amount) if meta.monthly_amount else "",
    }
    base.update(cambios)
    return base


def test_subir_el_objetivo_reabre_una_meta_alcanzada(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_editar", args=[meta.pk]),
                            _datos(meta, target_amount="200.00"))

    assert respuesta.status_code == 302
    meta.refresh_from_db()
    assert meta.target_amount == Decimal("200.00")
    assert meta.status == Goal.ACTIVE


def test_bajar_el_objetivo_la_da_por_alcanzada(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("500.00"))
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("120.00"))
    client.force_login(user)

    client.post(reverse("budget:meta_editar", args=[meta.pk]), _datos(meta, target_amount="100.00"))

    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


def test_borrar_una_meta_sin_cascada_se_lleva_sus_aportes(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    GoalContributionFactory(household=hogar, goal=meta)
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_borrar", args=[meta.pk]))

    assert respuesta.status_code == 302
    assert not Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()


def test_una_meta_con_cascada_no_se_borra_se_abandona(client, admin_con_hogar):
    from apps.budget.models import GoalContribution

    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    GoalContribution.unscoped.create(
        household=hogar, goal=meta, amount=Decimal("50.00"), date=date(2026, 3, 31),
        member=None, origen="cascade",
    )
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_borrar", args=[meta.pk]), follow=True)

    assert Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()
    assert "abandon it instead" in respuesta.content.decode()
    html = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert reverse("budget:meta_borrar", args=[meta.pk]) not in html
    assert reverse("budget:meta_estado", args=[meta.pk, "abandoned"]) in html


def test_borrar_por_get_no_destruye_nada(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    assert client.get(reverse("budget:meta_borrar", args=[meta.pk])).status_code == 405
    assert Goal.objects.for_household(hogar).filter(pk=meta.pk).exists()


def test_abandonar_y_reactivar_desde_la_pantalla(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    client.post(reverse("budget:meta_estado", args=[meta.pk, "abandoned"]))
    meta.refresh_from_db()
    assert meta.status == Goal.ABANDONED

    client.post(reverse("budget:meta_estado", args=[meta.pk, "active"]))
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_una_transicion_imposible_es_un_400(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, status=Goal.REACHED)
    client.force_login(user)

    respuesta = client.post(reverse("budget:meta_estado", args=[meta.pk, "abandoned"]))

    assert respuesta.status_code == 400
    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


@pytest.mark.parametrize("ruta,metodo", [
    ("budget:meta_editar", "get"),
    ("budget:meta_borrar", "post"),
])
def test_escribir_una_meta_exige_can_edit_budget(client, admin_con_hogar, ruta, metodo):
    _user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(_miembro(hogar).user)

    respuesta = getattr(client, metodo)(reverse(ruta, args=[meta.pk]))

    assert respuesta.status_code == 403


def test_cambiar_el_estado_exige_can_edit_budget(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(_miembro(hogar).user)

    assert client.post(reverse("budget:meta_estado", args=[meta.pk, "abandoned"])).status_code == 403


def test_la_meta_de_otro_hogar_es_un_404(client, admin_con_hogar):
    user, _hogar = admin_con_hogar
    ajena = GoalFactory(household=HouseholdFactory())
    client.force_login(user)

    assert client.get(reverse("budget:meta_editar", args=[ajena.pk])).status_code == 404
    assert client.post(reverse("budget:meta_borrar", args=[ajena.pk])).status_code == 404


def test_la_meta_personal_de_otro_miembro_es_un_404(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    ajena = GoalFactory(household=hogar, scope="personal", owner=_miembro(hogar))
    client.force_login(user)

    assert client.get(reverse("budget:meta_editar", args=[ajena.pk])).status_code == 404
```

- [ ] **Step 2: Verlas fallar**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_metas_vistas.py -q`
Expected: `NoReverseMatch` para `meta_editar`, `meta_borrar`, `meta_estado`.

- [ ] **Step 3: Rutas**

En `apps/budget/urls.py`, tras `path("goals/contribute/", ...)`:

```python
    # Corregir, quitar, abandonar o reactivar una meta. Quitar solo si nunca
    # recibio cascada: un aporte del cierre es historia de un mes cerrado.
    path("goals/<int:pk>/", views_goals.meta_editar, name="meta_editar"),
    path("goals/<int:pk>/delete/", views_goals.meta_borrar, name="meta_borrar"),
    path("goals/<int:pk>/status/<str:estado>/", views_goals.meta_estado, name="meta_estado"),
```

- [ ] **Step 4: Vistas**

En `apps/budget/views_goals.py`, añadir imports y vistas:

```python
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .scopes import HOGAR, PERSONAL


def _meta(request, hogar, pk):
    """Una meta que quien pide puede tocar: las del hogar, y las personales
    solo de su dueno. `for_household` antes que `get_object_or_404`: el pk de
    otra familia (o la personal de otro miembro) es un 404 identico al de un
    pk inventado, sin decir cual fue."""
    membresia = membresia_actual(request)
    visibles = Q(scope=HOGAR) | Q(scope=PERSONAL, owner=membresia)
    return get_object_or_404(Goal.objects.for_household(hogar).filter(visibles), pk=pk)


@requiere_permiso("can_edit_budget")
def meta_editar(request, hogar, pk):
    """Corregir en sitio, como una regla del setup. Tras guardar se recalcula
    el estado: subir el objetivo reabre una alcanzada, bajarlo puede cubrirla."""
    meta = _meta(request, hogar, pk)
    form = GoalForm(request.POST or None, household=hogar, instance=meta)
    if request.method == "POST" and form.is_valid():
        meta = form.save()
        services_goals.recalcular_estado(meta)
        return redirect("budget:metas", meta.scope)
    return render(request, "budget/formulario.html", {
        "form": form, "titulo": _("Edit goal"),
        "cancelar": reverse("budget:metas", args=[meta.scope]),
    })


@require_POST
@requiere_permiso("can_edit_budget")
def meta_borrar(request, hogar, pk):
    """Solo por POST: un GET no destruye nada. Con aportes de cascada no se
    borra: MonthlyAllocation.rule es RESTRICT y el mes cerrado conto con ese
    reparto. Se abandona, que es lo que la tarjeta ofrece en su lugar."""
    meta = _meta(request, hogar, pk)
    if meta.contributions.filter(origen="cascade").exists():
        messages.error(request, _(
            "This goal already took part in a closed month — abandon it instead."
        ))
    else:
        meta.delete()
    return redirect("budget:metas", meta.scope)


@require_POST
@requiere_permiso("can_edit_budget")
def meta_estado(request, hogar, pk, estado):
    meta = _meta(request, hogar, pk)
    try:
        services_goals.cambiar_estado(meta, estado)
    except ValueError:
        return HttpResponseBadRequest(_("That change is not possible."))
    return redirect("budget:metas", meta.scope)
```

- [ ] **Step 5: El fragmento de acciones por icono**

Crear `templates/budget/_fragmentos/acciones_icono.html`:

```django
{% load i18n %}
{% comment %} Editar y Quitar por iconos, para columnas estrechas. Lo usan los
   registros de "What actually happened", las metas y sus aportes. Quitar es
   un POST con confirmacion del navegador; un GET no destruye nada. Con
   `borrar_url` vacia solo hay Editar. {% endcomment %}
<span class="fila-regla__acciones">
  <a class="btn btn--sutil btn--icono" href="{{ editar_url }}"
     aria-label="{% translate 'Edit' %}" title="{% translate 'Edit' %}">
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>
    </svg>
  </a>
  {% if borrar_url %}
  <form method="post" action="{{ borrar_url }}"
        onsubmit="return confirm('{{ confirmacion|escapejs }}')">
    {% csrf_token %}
    <button class="btn btn--sutil btn--icono btn--peligro" type="submit"
            aria-label="{% translate 'Remove' %}" title="{% translate 'Remove' %}">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>
        <path d="M10 11v6"/><path d="M14 11v6"/>
      </svg>
    </button>
  </form>
  {% endif %}
</span>
```

Reescribir `templates/budget/_fragmentos/acciones_registro.html`:

```django
{% load i18n %}
{% comment %} Editar y Quitar de un registro de "What actually happened". Los
   iconos viven en acciones_icono.html, compartidos con las metas. {% endcomment %}
{% url 'budget:registro_editar' pk as editar_url %}
{% url 'budget:registro_borrar' pk as borrar_url %}
{% translate "Remove this record? Its one-off line goes with it." as confirmacion %}
{% include "budget/_fragmentos/acciones_icono.html" %}
```

- [ ] **Step 6: La cabecera de la tarjeta**

En `templates/budget/_fragmentos/meta_tarjeta.html`, dentro de `<header class="meta__cabecera">`, tras el `</h2>`:

```django
    {% if nav_membresia.can_edit_budget %}
      {% url 'budget:meta_editar' fila.meta.pk as editar_url %}
      {% if fila.se_puede_borrar %}
        {% url 'budget:meta_borrar' fila.meta.pk as borrar_url %}
        {% translate "Remove this goal? Its contributions go with it." as confirmacion %}
        {% include "budget/_fragmentos/acciones_icono.html" %}
      {% else %}
        {% include "budget/_fragmentos/acciones_icono.html" with borrar_url="" %}
      {% endif %}
    {% endif %}
```

Y al final de la tarjeta, antes de `</section>`, el pie con Abandon / Reactivate:

```django
  {% if nav_membresia.can_edit_budget %}
    {% if fila.meta.status == 'active' and not fila.se_puede_borrar %}
      <form method="post" action="{% url 'budget:meta_estado' fila.meta.pk 'abandoned' %}"
            onsubmit="return confirm('{% translate "Abandon this goal? Its contributions stay on record." %}')">
        {% csrf_token %}
        <button class="btn btn--sutil btn--peligro" type="submit">{% translate "Abandon" %}</button>
      </form>
    {% elif fila.meta.status == 'abandoned' %}
      <form method="post" action="{% url 'budget:meta_estado' fila.meta.pk 'active' %}">
        {% csrf_token %}
        <button class="btn btn--sutil" type="submit">{% translate "Reactivate" %}</button>
      </form>
    {% endif %}
  {% endif %}
```

- [ ] **Step 7: Correr**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_metas_vistas.py tests/budget/test_corregir_registro.py -q`
Expected: verde (la segunda confirma que `acciones_registro.html` sigue funcionando).

- [ ] **Step 8: Commit**

```bash
git add apps/budget/views_goals.py apps/budget/urls.py templates/budget/_fragmentos/ tests/budget/test_metas_vistas.py
git commit -m "Corregir, quitar, abandonar y reactivar una meta

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Corregir y quitar un aporte manual

**Files:**
- Modify: `apps/budget/views_goals.py` (`_aporte`, `aporte_editar`, `aporte_borrar`)
- Modify: `apps/budget/urls.py`
- Modify: `templates/budget/_fragmentos/meta_aporte_fila.html`
- Test: `tests/budget/test_aportar.py`

**Interfaces:**
- Produces: rutas `budget:aporte_editar (pk)`, `budget:aporte_borrar (pk)`.

- [ ] **Step 1: Pruebas que fallan**

Añadir a `tests/budget/test_aportar.py`:

```python
# --- corregir y quitar --------------------------------------------------------

from tests.factories_budget import BudgetMonthFactory, GoalContributionFactory  # noqa: E402


def _cascada(hogar, meta, **campos):
    from apps.budget.models import GoalContribution

    base = dict(household=hogar, goal=meta, amount=Decimal("50.00"),
                date=date(2026, 3, 31), member=None, origen="cascade")
    base.update(campos)
    return GoalContribution.unscoped.create(**base)


def test_corregir_un_aporte_recalcula_el_estado(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"))
    aporte = GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("40.00"),
                                     date=date(2026, 3, 1))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aporte_editar", args=[aporte.pk]), {
        "goal": meta.pk, "amount": "100.00", "date": "2026-03-01",
    })

    assert respuesta.status_code == 302
    aporte.refresh_from_db()
    assert aporte.amount == Decimal("100.00")
    meta.refresh_from_db()
    assert meta.status == Goal.REACHED


def test_quitar_un_aporte_reabre_la_meta(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar, target_amount=Decimal("100.00"), status=Goal.REACHED)
    aporte = GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("100.00"))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aporte_borrar", args=[aporte.pk]))

    assert respuesta.status_code == 302
    assert not meta.contributions.exists()
    meta.refresh_from_db()
    assert meta.status == Goal.ACTIVE


def test_un_aporte_de_cascada_no_se_toca(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    aporte = _cascada(hogar, meta)
    client.force_login(user)

    assert client.get(reverse("budget:aporte_editar", args=[aporte.pk])).status_code == 403
    assert client.post(reverse("budget:aporte_borrar", args=[aporte.pk])).status_code == 403
    assert meta.contributions.filter(pk=aporte.pk).exists()


def test_un_aporte_de_un_mes_cerrado_no_se_toca(client, admin_con_hogar):
    from apps.budget.models import BudgetMonth

    user, hogar = admin_con_hogar
    cerrado = BudgetMonthFactory(household=hogar, year=2026, month=1, status=BudgetMonth.CLOSED)
    meta = GoalFactory(household=hogar)
    aporte = GoalContributionFactory(household=hogar, goal=meta, date=date(2026, 1, 10),
                                     budget_month=cerrado)
    client.force_login(user)

    editar = client.post(reverse("budget:aporte_editar", args=[aporte.pk]), {
        "goal": meta.pk, "amount": "1.00", "date": "2026-02-10",
    }, follow=True)
    borrar = client.post(reverse("budget:aporte_borrar", args=[aporte.pk]), follow=True)

    assert "This month is already closed." in editar.content.decode()
    assert "This month is already closed." in borrar.content.decode()
    aporte.refresh_from_db()
    assert aporte.amount == Decimal("50.00")


def test_mover_un_aporte_a_un_mes_cerrado_lo_dice_el_formulario(client, admin_con_hogar):
    from apps.budget.models import BudgetMonth

    user, hogar = admin_con_hogar
    BudgetMonthFactory(household=hogar, year=2026, month=1, status=BudgetMonth.CLOSED)
    meta = GoalFactory(household=hogar)
    aporte = GoalContributionFactory(household=hogar, goal=meta, date=date(2026, 3, 10))
    client.force_login(user)

    respuesta = client.post(reverse("budget:aporte_editar", args=[aporte.pk]), {
        "goal": meta.pk, "amount": "50.00", "date": "2026-01-10",
    })

    assert respuesta.status_code == 200
    assert "This month is already closed." in respuesta.content.decode()
    aporte.refresh_from_db()
    assert aporte.date == date(2026, 3, 10)


def test_los_aportes_editables_llevan_acciones_y_los_demas_no(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    manual = GoalContributionFactory(household=hogar, goal=meta)
    cascada = _cascada(hogar, meta)
    client.force_login(user)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert reverse("budget:aporte_editar", args=[manual.pk]) in html
    assert reverse("budget:aporte_editar", args=[cascada.pk]) not in html


def test_tocar_un_aporte_exige_can_edit_budget(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    aporte = GoalContributionFactory(household=hogar, goal=GoalFactory(household=hogar))
    client.force_login(_miembro(hogar, can_edit_budget=False).user)

    assert client.get(reverse("budget:aporte_editar", args=[aporte.pk])).status_code == 403
    assert client.post(reverse("budget:aporte_borrar", args=[aporte.pk])).status_code == 403


def test_el_aporte_de_la_meta_personal_de_otro_es_un_404(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    ajena = GoalFactory(household=hogar, scope="personal", owner=_miembro(hogar))
    aporte = GoalContributionFactory(household=hogar, goal=ajena)
    client.force_login(user)

    assert client.get(reverse("budget:aporte_editar", args=[aporte.pk])).status_code == 404
    assert client.post(reverse("budget:aporte_borrar", args=[aporte.pk])).status_code == 404
```

- [ ] **Step 2: Verlas fallar**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_aportar.py -k "corregir or quitar or cascada_no or mes_cerrado or editables or tocar or personal_de_otro_es" -q`
Expected: `NoReverseMatch`.

- [ ] **Step 3: Rutas**

En `apps/budget/urls.py`, tras las de meta:

```python
    path("goals/contributions/<int:pk>/", views_goals.aporte_editar, name="aporte_editar"),
    path("goals/contributions/<int:pk>/delete/", views_goals.aporte_borrar, name="aporte_borrar"),
```

- [ ] **Step 4: Vistas**

En `apps/budget/views_goals.py`:

```python
from django.http import HttpResponseForbidden


def _aporte(request, hogar, pk):
    """Como _meta, para un aporte: el de la meta personal de otro es 404."""
    membresia = membresia_actual(request)
    visibles = Q(goal__scope=HOGAR) | Q(goal__scope=PERSONAL, goal__owner=membresia)
    return get_object_or_404(
        GoalContribution.objects.for_household(hogar)
        .select_related("goal", "budget_month").filter(visibles),
        pk=pk,
    )


def _intocable(aporte):
    """Por que un aporte no se corrige, o None si se puede."""
    if aporte.origen != "manual":
        return HttpResponseForbidden(_("Contributions from the monthly split cannot be changed."))
    return None


@requiere_permiso("can_edit_budget")
def aporte_editar(request, hogar, pk):
    """Corregir un aporte mal tecleado. Si su mes ya esta cerrado no se toca:
    moverle la fecha sacaria dinero de un balance ya cuadrado. Si la fecha
    NUEVA cae en un mes cerrado, lo dice el formulario."""
    aporte = _aporte(request, hogar, pk)
    if (prohibido := _intocable(aporte)) is not None:
        return prohibido
    meta = aporte.goal
    if aporte.budget_month_id and aporte.budget_month.esta_cerrado:
        messages.error(request, _("This month is already closed."))
        return redirect("budget:metas", meta.scope)
    form = GoalContributionForm(request.POST or None, household=hogar,
                                membresia=membresia_actual(request), instance=aporte)
    if request.method == "POST" and form.is_valid():
        aporte = form.save(commit=False)
        aporte.budget_month = services.mes_de_fecha(hogar, aporte.date)
        try:
            aporte.full_clean()
            aporte.save()
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        else:
            services_goals.recalcular_estado(aporte.goal)
            return redirect("budget:metas", aporte.goal.scope)
    return render(request, "budget/formulario.html", {
        "form": form, "titulo": _("Edit contribution"),
        "cancelar": reverse("budget:metas", args=[meta.scope]),
    })


@require_POST
@requiere_permiso("can_edit_budget")
def aporte_borrar(request, hogar, pk):
    aporte = _aporte(request, hogar, pk)
    if (prohibido := _intocable(aporte)) is not None:
        return prohibido
    meta = aporte.goal
    if aporte.budget_month_id and aporte.budget_month.esta_cerrado:
        messages.error(request, _("This month is already closed."))
    else:
        aporte.delete()
        services_goals.recalcular_estado(meta)
    return redirect("budget:metas", meta.scope)
```

- [ ] **Step 5: Acciones en la fila**

Reescribir `templates/budget/_fragmentos/meta_aporte_fila.html`:

```django
{% load i18n money %}
<tr>
  <td>{{ aporte.date }}</td>
  <td>
    {% if aporte.origen == "cascade" %}{% translate "From the monthly split" %}
    {% elif aporte.member %}{{ aporte.member.user }}
    {% else %}{% translate "The household" %}{% endif %}
  </td>
  <td class="numero">{{ aporte.amount|money:hogar.currency }}</td>
  <td>
    {% if editable and nav_membresia.can_edit_budget %}
      {% url 'budget:aporte_editar' aporte.pk as editar_url %}
      {% url 'budget:aporte_borrar' aporte.pk as borrar_url %}
      {% translate "Remove this contribution?" as confirmacion %}
      {% include "budget/_fragmentos/acciones_icono.html" %}
    {% endif %}
  </td>
</tr>
```

- [ ] **Step 6: Correr**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_aportar.py tests/budget/test_metas_vistas.py -q`
Expected: verde.

- [ ] **Step 7: Commit**

```bash
git add apps/budget/views_goals.py apps/budget/urls.py templates/budget/_fragmentos/meta_aporte_fila.html tests/budget/test_aportar.py
git commit -m "Corregir y quitar un aporte manual; los de cascada no se tocan

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: El enlace a la regla de reparto, y los catálogos

**Files:**
- Modify: `apps/budget/views_setup.py:35-46` (`crear` con `initial`), `reparto_nuevo`
- Modify: `locale/en/LC_MESSAGES/django.po`, `locale/fr/LC_MESSAGES/django.po` (+ `.mo`)
- Test: `tests/budget/test_metas_vistas.py`, `tests/test_catalogo_exhaustivo.py` (existente)

- [ ] **Step 1: Prueba que falla**

Añadir a `tests/budget/test_metas_vistas.py`:

```python
def test_el_enlace_de_la_tarjeta_preselecciona_la_regla_de_reparto(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    meta = GoalFactory(household=hogar)
    client.force_login(user)

    respuesta = client.get(reverse("budget:reparto_nuevo") + f"?target_type=goal&target_goal={meta.pk}")

    form = respuesta.context["form"]
    assert form["target_type"].value() == "goal"
    assert form["target_goal"].value() == meta.pk
```

- [ ] **Step 2: Verla fallar**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_metas_vistas.py -k preselecciona -q`
Expected: FAIL, `None == "goal"`.

- [ ] **Step 3: `crear` con `initial`**

En `apps/budget/views_setup.py`:

```python
def crear(request, hogar, form_class, titulo, destino="budget:configurar", destino_args=(),
          initial=None):
    """...(docstring existente)...

    `initial` viene de la query: la tarjeta de una meta enlaza a "add a split
    rule" con la meta ya puesta. Solo rellena; el formulario valida igual.
    """
    form = form_class(request.POST or None, household=hogar, initial=initial or {})
    return _guardar(request, hogar, form, titulo, destino, destino_args)


def _initial_de_reparto(request):
    """Lo que la tarjeta de una meta manda en la query, si viene bien."""
    initial = {}
    if request.GET.get("target_type") == "goal":
        initial["target_type"] = "goal"
    if request.GET.get("target_goal", "").isdigit():
        initial["target_goal"] = int(request.GET["target_goal"])
    return initial


@requiere_permiso("can_edit_budget")
def reparto_nuevo(request, hogar):
    return crear(request, hogar, AllocationRuleForm, _("New split rule"),
                 initial=_initial_de_reparto(request))
```

- [ ] **Step 4: Correr**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/budget/test_metas_vistas.py tests/budget/test_setup_editar.py -q`
Expected: verde.

- [ ] **Step 5: Catálogos**

Run: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" tests/test_catalogo_exhaustivo.py -q`
Expected: FAIL listando las cadenas nuevas. Añadirlas a los dos `.po` (EN: `msgstr` igual al `msgid`; FR: traducción). Las cadenas de este plan y su francés:

| msgid | fr |
|---|---|
| `Reached` | `Atteint` |
| `Abandoned` | `Abandonné` |
| `You got there on %(cuando)s 🎉` | `Objectif atteint le %(cuando)s 🎉` |
| `You got there 🎉` | `Objectif atteint 🎉` |
| `Put in %(importe)s a month to get there by %(cuando)s.` | `Mettez %(importe)s par mois pour y arriver d'ici %(cuando)s.` |
| `At this rate you get there in %(meses)s month · %(cuando)s.` / plural `... months ...` | `À ce rythme vous y arrivez dans %(meses)s mois · %(cuando)s.` (mismo singular y plural) |
| `This month: %(hecho)s of the %(sugerido)s suggested` | `Ce mois-ci : %(hecho)s sur les %(sugerido)s suggérés` |
| `Personal goal: only manual contributions.` | `Objectif personnel : contributions manuelles seulement.` |
| `Nothing feeds this goal automatically —` | `Rien n'alimente cet objectif automatiquement —` |
| `add a split rule` | `ajoutez une règle de répartition` |
| `A split rule still feeds it — remove it in Budget setup.` | `Une règle de répartition l'alimente encore — retirez-la dans Configuration du budget.` |
| `Show all` | `Tout afficher` |
| `Nothing yet.` | `Rien pour l'instant.` |
| `From the monthly split` | `De la répartition mensuelle` |
| `Add to it` | `Y contribuer` |
| `No active goals yet.` | `Aucun objectif actif pour l'instant.` |
| `A goal contribution` | `Une contribution à un objectif` |
| `Money you set aside` | `De l'argent mis de côté` |
| `Edit goal` | `Modifier l'objectif` |
| `Edit contribution` | `Modifier la contribution` |
| `This goal already took part in a closed month — abandon it instead.` | `Cet objectif a déjà compté dans un mois clôturé — abandonnez-le plutôt.` |
| `That change is not possible.` | `Ce changement n'est pas possible.` |
| `Remove this goal? Its contributions go with it.` | `Retirer cet objectif ? Ses contributions partent avec.` |
| `Abandon this goal? Its contributions stay on record.` | `Abandonner cet objectif ? Ses contributions restent enregistrées.` |
| `Abandon` | `Abandonner` |
| `Reactivate` | `Réactiver` |
| `Remove this contribution?` | `Retirer cette contribution ?` |
| `Contributions from the monthly split cannot be changed.` | `Les contributions de la répartition mensuelle ne se modifient pas.` |
| `A contribution cannot be dated in the future.` | `Une contribution ne peut pas être datée dans le futur.` |
| `Put in more than zero.` | `Mettez plus que zéro.` (solo si se añadió `clean_amount`) |

El `blocktranslate` con plural se escribe en el `.po` con `msgid`/`msgid_plural` y `msgstr[0]`/`msgstr[1]`; copiar el formato de otro plural del catálogo (`grep -n "msgid_plural" locale/fr/LC_MESSAGES/django.po | head -1`).

Compilar en cada carpeta: `python C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py -o django.mo django.po`.

Volver a correr `tests/test_catalogo_exhaustivo.py`: verde.

- [ ] **Step 6: Commit**

```bash
git add apps/budget/views_setup.py locale/ tests/budget/test_metas_vistas.py
git commit -m "La tarjeta de la meta enlaza a su regla de reparto; catalogos EN y FR

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Suite completa, navegador y cierre

**Files:**
- Ninguno nuevo; correcciones que salgan.

- [ ] **Step 1: La suite entera, en segundo plano**

Run (en segundo plano, con salida a un archivo del scratchpad): `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" -q > <scratchpad>/suite.txt 2>&1`
Esperar con `until grep -qE 'passed|failed' <scratchpad>/suite.txt; do sleep 10; done` también en segundo plano. **No lanzar otro pytest mientras corre.**
Expected: todo en verde. Si algo falla, arreglarlo y volver a correr solo ese archivo antes de repetir la suite.

- [ ] **Step 2: Verificar en el navegador**

Con el servidor en `127.0.0.1:8000` y el usuario demo (`demo@wealthome.test` / `wealthome-demo-2026`; si no hay metas, sembrar con `scripts/sembrar_demo.py` o crear una desde la pantalla), recorrer con Playwright MCP:
1. `/budget/household/goals/`: tarjeta con progreso, "This month", aviso de regla, botón "Add to it".
2. "Add to it" abre el modal con la meta puesta; aportar; la tarjeta se refresca sin recargar y el modal se cierra.
3. `[+]` → "A goal contribution" desde `/budget/household/`: el modal pide el form; sin metas activas dice "No active goals yet".
4. Editar meta (subir/bajar objetivo), Abandon → tarjeta atenuada → Reactivate.
5. Editar y quitar un aporte manual desde la tabla; el de cascada no tiene iconos.
6. Móvil (400 px) y tema oscuro: chips, tarjeta apagada y selector de tres opciones legibles.
Capturas en `.playwright-mcp/`.

- [ ] **Step 3: Estado de la spec**

En `docs/superpowers/specs/2026-09-20-wealthome-metas-design.md` cambiar `**Estado:**` a `Implementado en la rama ui/navegacion-y-tiles`. Commit:

```bash
git add docs/superpowers/specs/2026-09-20-wealthome-metas-design.md
git commit -m "La spec de metas queda implementada

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Auto-revisión del plan

- **Cobertura de la spec:** §2 datos y estados → T1, T4, T6; §3 servicio → T1, T3; §4 rutas → T5, T6, T7; §5 UI (tarjeta, bloques, aporte_form, FAB, CSS, i18n, sw.js) → T3, T5, T6, T7, T8; §6 pruebas → cada tarea y T9. `aplicar_cascada_al_cierre` → T2. `tests/test_presupuesto_consultas.py` → T3 paso 12.
- **Sin placeholders:** cada paso lleva el código; los únicos "comprobar" son sobre nombres de tokens CSS y de imports existentes, con instrucción de cómo comprobarlos.
- **Consistencia de nombres:** `services_goals.aportar/recalcular_estado/cambiar_estado/resumen`, `views_goals._con_aportes/_fila/_meta/_aporte`, rutas `meta_editar/meta_borrar/meta_estado/aporte_editar/aporte_borrar`, fragmentos `meta_tarjeta.html/meta_aporte_fila.html/acciones_icono.html/aporte_form.html`, variables de fragmento `editar_url/borrar_url/confirmacion`, contexto `filas/activas/alcanzadas/abandonadas/tarjeta_oob/sin_metas` — iguales en todas las tareas.

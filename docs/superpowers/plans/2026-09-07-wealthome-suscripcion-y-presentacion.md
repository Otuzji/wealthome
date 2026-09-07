# Wealthome Fase 1 · Plan 3: la suscripción y la presentación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poner Wealthome en manos de alguien que no la escribió y ponerle precio: Stripe con su trial de catorce días y su modo solo lectura, la capa de componentes neomórfica sobre los tokens que ya existen, el armazón de navegación que hoy no existe, el eje Hogar/Personal con sus ocho pantallas —donde por fin se ven la varianza y la mesada—, los dos asistentes, htmx, Chart.js y la PWA.

**Architecture:** Nada de esto toca `apps/budget/engine/`, que sigue puro y sin ORM. La suscripción vive en `apps/subscriptions/`, una app nueva, y su guardia se inyecta en dos sitios que ya existen y son compartidos: `_decorador` en `apps/households/permissions.py` (una vez, para las tres puertas y para las vistas que aún no se han escrito) y `HouseholdScoped.save()` en `apps/households/scoping.py` (la capa que no se puede rodear). La presentación crece sobre `static/css/tokens.css`, que ya define los tres temas: los componentes se escriben una vez y el tema Accesible solo cambia variables.

**Tech Stack:** Python 3.11, Django 5.1, Postgres (Supabase), pytest + pytest-django + factory_boy, CSS puro. **Dependencias nuevas:** `stripe` (biblioteca oficial) y `pytest-playwright` (para una sola prueba). htmx, Alpine.js y Chart.js se vendorizan como archivos estáticos, sin gestor de paquetes.

**Spec:** `docs/superpowers/specs/2026-09-07-wealthome-suscripcion-y-presentacion-design.md`
**Spec de la Fase 1:** `docs/superpowers/specs/2026-08-30-wealthome-nucleo-financiero-design.md`
**Spec del Plan 2:** `docs/superpowers/specs/2026-09-03-wealthome-motor-financiero-design.md`
**Traspaso del Plan 2:** `docs/superpowers/2026-09-07-estado-y-deuda-plan-3.md`

## Global Constraints

Heredadas de los Planes 1 y 2, y siguen vigentes enteras:

- **Python 3.11**, **Django 5.1**. En Django 5.x `USE_L10N` fue eliminado — no lo escribas en settings.
- **Todo importe monetario usa `apps.core.fields.MoneyField`.** Nunca `float`, nunca `DecimalField` a mano.
- **Un solo punto de redondeo:** `apps.budget.engine.money.centavos()`, con `ROUND_HALF_UP` a dos decimales.
- **`apps/budget/engine/` no importa el ORM, y este plan NO lo toca.** `tests/budget/engine/test_pureza.py` lo vigila.
- **Todo modelo con datos del hogar hereda de `apps.households.scoping.HouseholdScoped`.** Si declara su propia `Meta`, debe heredarla: `class Meta(HouseholdScoped.Meta):`, o pierde `base_manager_name` y rompe el ORM por dentro.
- **`Modelo.objects.all()` lanza `RuntimeError`.** La única entrada es `.objects.for_household(hogar)`; `unscoped` es la salida de emergencia explícita. `get_object_or_404(Modelo, pk=pk)` **también lanza**.
- **Toda fábrica de pruebas de un modelo con hogar hereda de `tests.factories.HouseholdScopedFactory`.**
- **Todo formulario sobre un modelo con hogar hereda de `apps.households.scoped_forms.HouseholdScopedModelForm`** y recibe `household=` de solo palabra clave.
- **Toda vista lleva `@con_hogar`, `@solo_admin` o `@requiere_permiso("...")`** de `apps.households.permissions`, y recibe el hogar como segundo argumento.
- **Todo texto visible al usuario pasa por `gettext`**, y **cada cadena nueva se escribe a mano en `locale/en/LC_MESSAGES/django.po` y `locale/fr/LC_MESSAGES/django.po`** y se compila. No hay cadena GNU gettext en esta máquina.
- **Moneda: CAD.** Idiomas: `en` (por defecto) y `fr`. Temas: `sereno`, `nocturno`, `accesible`.
- Mensajes de commit en español, en imperativo.

Propias de este plan:

- **Ningún componente de CSS contiene un selector `[data-theme="…"]`.** El tema Accesible cambia variables, no componentes. El patrón está en `static/css/components.css`: declarar a la vez `border: var(--border-width) solid var(--border-color)` y `box-shadow: var(--shadow-raised)`.
- **Ningún color literal en JavaScript.** Chart.js lee sus colores con `getComputedStyle(document.documentElement).getPropertyValue('--…')`, o las gráficas se vuelven ilegibles en Nocturno y pierden el contraste 14:1 en Accesible.
- **htmx solo en cuatro sitios** (registrar un gasto, los pasos de los asistentes, los filtros del Overview, aportar a una meta). **La navegación entre módulos son cargas de página completas.**
- **Las pruebas nunca llaman a Stripe.** Ni en modo de prueba. La suite corre sin claves.
- **El ámbito Hogar/Personal va en la ruta**, nunca en un parámetro de consulta ni en la sesión: el service worker cachea por URL.

## Cómo correr las pruebas en esta máquina

```bash
.venv/Scripts/python.exe -m pytest tests/budget/engine -q     # el motor: bajo un segundo
.venv/Scripts/python.exe -m pytest tests/budget -q            # ~11-15 min
.venv/Scripts/python.exe -m pytest -q --ignore=tests/budget   # ~5-7 min
.venv/Scripts/python.exe -m pytest -q --create-db             # OBLIGATORIO tras una migración nueva
```

**Trampas del entorno — leer antes de la primera tarea:**

- **La suite completa tarda ~19 minutos y NO cabe en una sola llamada de herramienta** (límite 600 s). Córrela **en dos mitades y en primer plano**, con los dos comandos de arriba. Lanzarlas en segundo plano y esperar un aviso cuelga al agente: pasó tres veces en el Plan 1.
- **Tras añadir una migración hay que correr una vez con `--create-db`**, o la base reutilizada conserva el esquema viejo y las pruebas mienten. Este plan añade **seis** migraciones.
- El pooler de Supabase deja sesiones abiertas: dos corridas seguidas pueden dar un error de arranque espurio (`There is 1 other session using the database`) que un reintento limpia.
- La base `test_postgres` **no es basura**: es la que reutiliza `--reuse-db`.
- **Los heredocs de shell con contenido largo y acentuado fallan a veces.** Escribe el archivo con la herramienta de escritura y luego insértalo con un script corto.
- Para compilar los catálogos:
  ```bash
  MSGFMT="C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py"
  for L in en fr; do .venv/Scripts/python.exe "$MSGFMT" -o "locale/$L/LC_MESSAGES/django.mo" "locale/$L/LC_MESSAGES/django.po"; done
  ```
  `tests/test_catalogo_exhaustivo.py` nombra cada cadena que falte.

---

## Estructura de archivos

```
apps/subscriptions/                  # APP NUEVA
  __init__.py  apps.py
  models.py          # Subscription, StripeEvent
  services.py        # crear_suscripcion(), marcar_pagada(), procesar_evento()
  gateway.py         # el ÚNICO módulo que importa `stripe`
  views.py  urls.py  admin.py
  migrations/

apps/households/
  scoping.py         # + HouseholdScoped.save() con la guardia de suscripción
  permissions.py     # + la guardia por método HTTP en _decorador
  services.py        # crear_hogar() crea la suscripción

apps/budget/
  models/allocation.py   # MonthlyAllocation hereda EscrituraAcotadaAlMes
  models/goals.py        # GoalContribution: + budget_month, member anulable
  services.py            # concurrencia, hogar expirado, mes_de_fecha()
  views.py               # se parte: ver Tarea 18
  views_overview.py      # Overview, Balance   (NUEVO)
  views_setup.py         # configurar y sus altas   (NUEVO)
  views_month.py         # el mes, registrar, planificar, cerrar   (NUEVO)
  views_goals.py         # metas y aportes   (NUEVO)
  wizards.py             # los dos asistentes   (NUEVO)

templates/
  base.html                    # + el armazón de navegación
  _nav.html                    # el menú, un solo bloque   (NUEVO)
  budget/overview.html  balance.html  metas.html  presupuesto.html
  budget/mesada.html           # Personal › Presupuesto   (NUEVO)
  budget/_fragmentos/          # lo que devuelve htmx   (NUEVO)
  wizards/                     # los dos asistentes   (NUEVO)
  subscriptions/               # estado y retorno de pago   (NUEVO)

static/
  css/components.css   # crece: ver Tarea 13
  css/modules.css      # crece: hoy tiene 1 línea
  css/tokens.css       # + la paleta categórica de gráficas
  vendor/htmx.min.js  alpine.min.js  chart.umd.min.js
  js/graficas.js  sw.js
  manifest.json  icons/

tests/
  test_navegacion.py           # la prueba de menú por perfil   (NUEVO)
  test_suscripcion.py          # el ciclo y los ocho casos hostiles   (NUEVO)
  test_webhook.py              # firma, idempotencia, concurrencia   (NUEVO)
  test_presupuesto_consultas.py  # django_assertNumQueries   (NUEVO)
  test_pwa.py                  # la única prueba de Playwright   (NUEVO)
  budget/test_htmx.py          # los fragmentos con HX-Request   (NUEVO)
```

**Por qué así:** `apps/budget/views.py` tiene hoy 221 líneas y este plan le añadiría ocho pantallas, dos asistentes y los fragmentos de htmx. Se parte por responsabilidad —no por capa— en la Tarea 18, que es la primera que lo haría crecer de verdad. `apps/subscriptions/` es una app propia porque su ciclo de vida no tiene nada que ver con el presupuesto y porque `gateway.py` aísla la única dependencia de red del proyecto: **ningún otro módulo importa `stripe`**, y eso es lo que hace que las pruebas puedan cubrir el webhook sin red.

---

## Mapa de tareas y puntos de control

| Tanda | Tareas | Al terminar |
|---|---|---|
| 1 · La deuda del montón A | 1-5 | La aplicación de hoy, correcta |
| 2 · La suscripción | 6-12 | **Se puede cobrar** |
| 3 · Componentes y navegación | 13-17 | **Usable y navegable. Aquí muere el problema del adolescente** |
| 4 · El eje y las pantallas nuevas | 18-23 | El §7.2 cumplido; la varianza y la mesada, a la vista |
| 5 · Los asistentes y htmx | 24-28 | El §4.5.6 cumplido por fin |
| 6 · La PWA | 29-31 | Instalable, y la caché se purga al salir |

**Son 31 tareas.** El spec calculaba 22-26; el desglose real salió más largo, sobre todo en la tanda 2. Si hay que parar, se para al final de una tanda y no a medio formulario.

---
## Tanda 1 · La deuda del montón A

Cinco tareas de correctitud sobre código que ya existe. Ninguna añade pantalla. Al terminar, la aplicación de hoy hace lo mismo pero bien, y el resto del plan puede añadir caminos de escritura sin miedo.

---

### Task 1: Las dos guardias de mes cerrado que faltan

El §5.7 del diseño del Plan 2 exige que **cuatro** modelos rechacen la escritura contra un mes cerrado. Solo dos lo hacen. `MonthlyAllocation` tiene `budget_month` y no hereda la guardia; `GoalContribution` ni siquiera sabe en qué mes está, así que **`budget:aportar` escribe contra un mes cerrado sin que nada lo impida**.

`GoalContribution.budget_month` entra **anulable**, y eso es correcto y no un atajo: un aporte cuya fecha cae en un mes que no tiene fila es un aporte a un mes que nadie ha cerrado, porque **un mes cerrado siempre tiene fila**. La guardia de `EscrituraAcotadaAlMes.save()` ya está escrita para eso — comprueba `if self.budget_month_id and …`.

**Files:**
- Modify: `apps/budget/models/allocation.py` (clase `MonthlyAllocation`)
- Modify: `apps/budget/models/goals.py` (clase `GoalContribution`)
- Modify: `apps/budget/services.py` (nueva función `mes_de_fecha`)
- Modify: `apps/budget/views.py:211-221` (vista `aportar`)
- Create: `apps/budget/migrations/0005_guardias_de_mes_cerrado.py`
- Test: `tests/budget/test_mes_cerrado.py` (existe; se le añaden pruebas)

**Interfaces:**
- Consumes: `EscrituraAcotadaAlMes` y `MesCerrado` de `apps.budget.models.months`.
- Produces: `services.mes_de_fecha(hogar, fecha) -> BudgetMonth | None` — resuelve la fila del mes que contiene esa fecha **sin crearla**. La usan la Tarea 3 y la vista `aportar`.

- [ ] **Step 1: Escribe las pruebas que fallan**

En `tests/budget/test_mes_cerrado.py`:

```python
import pytest
from datetime import date
from decimal import Decimal

from apps.budget.models import GoalContribution, MesCerrado, MonthlyAllocation
from tests.factories_budget import (
    AllocationRuleFactory, BudgetMonthFactory, GoalFactory,
)
from tests.factories import HouseholdFactory, MembershipFactory


@pytest.mark.django_db
def test_monthly_allocation_no_se_escribe_contra_un_mes_cerrado():
    hogar = HouseholdFactory()
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3, status="closed")
    regla = AllocationRuleFactory(household=hogar)

    fila = MonthlyAllocation(
        household=hogar, budget_month=mes, rule=regla,
        planned_amount=Decimal("100.00"),
    )
    with pytest.raises(MesCerrado):
        fila.save()


@pytest.mark.django_db
def test_goal_contribution_no_se_escribe_contra_un_mes_cerrado():
    hogar = HouseholdFactory()
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3, status="closed")
    meta = GoalFactory(household=hogar)
    miembro = MembershipFactory(household=hogar)

    aporte = GoalContribution(
        household=hogar, goal=meta, amount=Decimal("50.00"),
        date=date(2026, 3, 15), member=miembro, budget_month=mes,
    )
    with pytest.raises(MesCerrado):
        aporte.save()


@pytest.mark.django_db
def test_goal_contribution_sin_mes_se_escribe_sin_problema():
    """Un mes sin fila es un mes que nadie cerró: no hay a quién preguntarle."""
    hogar = HouseholdFactory()
    meta = GoalFactory(household=hogar)
    miembro = MembershipFactory(household=hogar)

    aporte = GoalContribution(
        household=hogar, goal=meta, amount=Decimal("50.00"),
        date=date(2026, 3, 15), member=miembro, budget_month=None,
    )
    aporte.save()
    assert aporte.pk is not None
```

- [ ] **Step 2: Corre las pruebas y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_mes_cerrado.py -q -k "monthly_allocation or goal_contribution"`
Expected: FAIL. Las dos primeras con `Failed: DID NOT RAISE MesCerrado`; la tercera con `TypeError` porque `budget_month` no es un campo de `GoalContribution`.

- [ ] **Step 3: Haz que `MonthlyAllocation` herede la guardia**

En `apps/budget/models/allocation.py`, cambia el import y la declaración de la clase:

```python
from .months import BudgetMonth, EscrituraAcotadaAlMes


class MonthlyAllocation(EscrituraAcotadaAlMes, HouseholdScoped):
    """El reparto materializado de un mes."""
```

El orden de las bases importa y debe ser exactamente ese: es el mismo que usan `BudgetLine` y `Transaction`, y es lo que pone el `save()` de la guardia delante del de `HouseholdScoped`.

- [ ] **Step 4: Dale un mes a `GoalContribution`**

En `apps/budget/models/goals.py`, añade el import y el campo, y hereda la guardia:

```python
from .months import BudgetMonth, EscrituraAcotadaAlMes


class GoalContribution(EscrituraAcotadaAlMes, HouseholdScoped):
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="contributions")
    amount = MoneyField(_("amount"))
    date = models.DateField(_("date"))
    budget_month = models.ForeignKey(
        BudgetMonth, on_delete=models.CASCADE, null=True, blank=True,
        related_name="aportes",
        help_text=_("Nulo si la fecha cae en un mes que el hogar no ha vivido."),
    )
    member = models.ForeignKey(
        "households.Membership", on_delete=models.RESTRICT, related_name="goal_contributions"
    )
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default="manual")
```

`EscrituraAcotadaAlMes.clean()` comprueba además que `household` coincida con el del mes, que es justo lo que queremos.

- [ ] **Step 5: Añade `mes_de_fecha` a `services.py`**

Al final del bloque del ciclo del mes en `apps/budget/services.py`, junto a `_mes_anterior`:

```python
def mes_de_fecha(hogar, fecha):
    """La fila del mes que contiene esa fecha, o None. NO la crea.

    Resolver sin crear es deliberado: quien escribe un aporte con fecha de un
    mes que el hogar nunca vivió no debe fabricar ese mes por el camino. Un
    mes sin fila tampoco puede estar cerrado, así que devolver None deja pasar
    la escritura, que es lo correcto.
    """
    return (
        BudgetMonth.objects.for_household(hogar)
        .filter(year=fecha.year, month=fecha.month)
        .first()
    )
```

- [ ] **Step 6: Haz que `aportar` ponga el mes**

En `apps/budget/views.py`, dentro de `aportar`, entre fijar `member` y `full_clean()`:

```python
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
            return redirect("budget:metas")
```

Fíjate en que ahora hay un `try`: sin él, `MesCerrado` sube como un 500 en vez de decírselo al usuario, igual que ya hace `registrar`. La cadena `"This month is already closed."` **ya existe** en los dos catálogos —la usa `registrar`—, así que esta tarea no añade traducciones.

- [ ] **Step 7: Genera la migración**

```bash
.venv/Scripts/python.exe manage.py makemigrations budget --name guardias_de_mes_cerrado
```

Revisa que solo contenga `AddField` de `budget_month` sobre `goalcontribution`. Heredar `EscrituraAcotadaAlMes` no cambia el esquema: es un modelo abstracto sin campos.

- [ ] **Step 8: Corre las pruebas con `--create-db`**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_mes_cerrado.py -q --create-db`
Expected: PASS, las tres nuevas y las que ya había.

- [ ] **Step 9: Corre la mitad del presupuesto para comprobar que no rompiste nada**

Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS. En primer plano, ~11-15 min.

- [ ] **Step 10: Commit**

```bash
git add apps/budget/models/allocation.py apps/budget/models/goals.py \
        apps/budget/services.py apps/budget/views.py \
        apps/budget/migrations/0005_guardias_de_mes_cerrado.py \
        tests/budget/test_mes_cerrado.py
git commit -m "Cierra las dos guardias de mes cerrado que faltaban del 5.7"
```

---

### Task 2: El aporte de la cascada deja de mentir sobre quién ahorró

`services.aplicar_cascada_al_cierre` escribe cada `GoalContribution` de origen `cascade` con `member=hogar.active_memberships().order_by("pk").first()`. Un ahorro **del hogar** queda a nombre de quien tenga el `pk` más bajo: un dato falso en el historial. Y si no hay membresías activas, `member=None` sobre una FK no anulable revienta con `IntegrityError` **en medio del cierre**, que es el peor momento posible.

Urge ahora y no después porque la Tarea 21 va a **enseñar** ese dato en pantalla.

**Files:**
- Modify: `apps/budget/models/goals.py` (campo `member` de `GoalContribution`)
- Modify: `apps/budget/services.py:487-495` (dentro de `aplicar_cascada_al_cierre`)
- Create: `apps/budget/migrations/0006_aporte_de_cascada_sin_miembro.py`
- Test: `tests/budget/test_services.py`

**Interfaces:**
- Produces: `GoalContribution.member` pasa a ser anulable. Cualquier plantilla o vista que lo muestre debe tolerar `None` — la Tarea 21 lo hace.

- [ ] **Step 1: Escribe las pruebas que fallan**

En `tests/budget/test_services.py`:

```python
@pytest.mark.django_db
def test_el_aporte_de_la_cascada_no_se_atribuye_a_nadie():
    """Un ahorro del hogar no es de quien tenga el pk mas bajo."""
    hogar = HouseholdFactory()
    MembershipFactory(household=hogar)
    MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    meta = GoalFactory(household=hogar)
    AllocationRuleFactory(
        household=hogar, order=1, target_type="goal", target_goal=meta,
        method="fixed", amount=Decimal("200.00"),
    )
    services.planificar_mes(hogar, mes, Decimal("500.00"))

    services.aplicar_cascada_al_cierre(mes, Decimal("500.00"))

    aporte = GoalContribution.objects.for_household(hogar).get(origen="cascade")
    assert aporte.member is None


@pytest.mark.django_db
def test_la_cascada_no_revienta_si_no_hay_membresias_activas():
    hogar = HouseholdFactory()
    miembro = MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    meta = GoalFactory(household=hogar)
    AllocationRuleFactory(
        household=hogar, order=1, target_type="goal", target_goal=meta,
        method="fixed", amount=Decimal("200.00"),
    )
    services.planificar_mes(hogar, mes, Decimal("500.00"))
    miembro.is_active = False
    miembro.save()

    services.aplicar_cascada_al_cierre(mes, Decimal("500.00"))

    assert GoalContribution.objects.for_household(hogar).filter(origen="cascade").count() == 1
```

- [ ] **Step 2: Corre las pruebas y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_services.py -q -k "cascada_no"`
Expected: FAIL. La primera con `assert <Membership> is None`; la segunda con `IntegrityError: null value in column "member_id"`.

- [ ] **Step 3: Haz `member` anulable**

En `apps/budget/models/goals.py`, dentro de `GoalContribution`:

```python
    member = models.ForeignKey(
        "households.Membership", on_delete=models.RESTRICT,
        null=True, blank=True, related_name="goal_contributions",
        help_text=_("Nulo cuando el aporte viene del reparto: ahorra el hogar, no una persona."),
    )
```

- [ ] **Step 4: Deja de inventar un miembro en el cierre**

En `apps/budget/services.py`, dentro de `aplicar_cascada_al_cierre`, sustituye la construcción del aporte:

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

Fíjate en que también fija `budget_month=mes`, el campo que añadió la Tarea 1.

- [ ] **Step 5: Genera la migración, con el borrado de la atribución falsa**

```bash
.venv/Scripts/python.exe manage.py makemigrations budget --name aporte_de_cascada_sin_miembro
```

Y añade a mano, al final de la lista `operations` del archivo generado, la limpieza del historial que ya está mal:

```python
def _borrar_atribucion_falsa(apps, schema_editor):
    """Los aportes de cascada ya escritos llevan un miembro que no eligio nadie."""
    GoalContribution = apps.get_model("budget", "GoalContribution")
    GoalContribution.objects.filter(origen="cascade").update(member=None)


def _sin_vuelta_atras(apps, schema_editor):
    """No se puede: el miembro original era arbitrario, no hay a quien devolverselo."""
```

…y en `operations`, después del `AlterField`:

```python
        migrations.RunPython(_borrar_atribucion_falsa, _sin_vuelta_atras),
```

`apps.get_model` en una migración devuelve el modelo histórico, cuyo manager por defecto **no** es el estricto, así que `.objects.filter(...)` aquí es correcto y no lanza.

- [ ] **Step 6: Corre las pruebas con `--create-db`**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_services.py -q --create-db`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/budget/models/goals.py apps/budget/services.py \
        apps/budget/migrations/0006_aporte_de_cascada_sin_miembro.py \
        tests/budget/test_services.py
git commit -m "Deja de atribuir a un miembro el ahorro que hace el hogar entero"
```

---

### Task 3: `planificar_mes` y `cerrar_mes` a prueba de concurrencia

`planificar_mes` comprueba `exists()` y escribe, sin bloqueo y sin restricción única: **dos clics en «Confirmar el plan» duplican las mesadas**. La Tarea 26 mete htmx justo en ese botón, que responde en la misma página y por tanto invita al segundo clic. `cerrar_mes` tampoco toma el `select_for_update` que el §6 del diseño del Plan 2 exige, aunque `materializar` sí lo toma.

La restricción única necesita **dos** constraints parciales y no una: en Postgres dos `NULL` no chocan entre sí, así que un solo `UniqueConstraint(budget_month, rule, member)` no impediría dos filas de regla sin miembro.

**Files:**
- Modify: `apps/budget/models/allocation.py` (`Meta` de `MonthlyAllocation`)
- Modify: `apps/budget/services.py` (`planificar_mes`, `cerrar_mes`)
- Create: `apps/budget/migrations/0007_un_reparto_por_regla_y_miembro.py`
- Test: `tests/budget/test_services.py`

**Interfaces:**
- Produces: `planificar_mes(hogar, mes, sobrante_proyectado)` conserva su firma y sigue siendo idempotente, pero ahora también bajo concurrencia.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
@pytest.mark.django_db
def test_planificar_dos_veces_no_duplica_las_mesadas():
    hogar = HouseholdFactory()
    MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    AllocationRuleFactory(
        household=hogar, order=1, target_type="allowance",
        method="fixed", amount=Decimal("100.00"),
    )

    services.planificar_mes(hogar, mes, Decimal("500.00"))
    services.planificar_mes(hogar, mes, Decimal("500.00"))

    assert MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes).count() == 1
    assert AllowanceLedger.objects.for_household(hogar).filter(budget_month=mes).count() == 1


@pytest.mark.django_db(transaction=True)
def test_la_base_impide_dos_repartos_de_la_misma_regla_y_miembro():
    """La barrera de verdad no es el exists(): es el esquema."""
    from django.db.utils import IntegrityError

    hogar = HouseholdFactory()
    miembro = MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    regla = AllocationRuleFactory(household=hogar, order=1)

    MonthlyAllocation.unscoped.create(
        household=hogar, budget_month=mes, rule=regla,
        member=miembro, planned_amount=Decimal("100.00"),
    )
    with pytest.raises(IntegrityError):
        MonthlyAllocation.unscoped.create(
            household=hogar, budget_month=mes, rule=regla,
            member=miembro, planned_amount=Decimal("100.00"),
        )


@pytest.mark.django_db(transaction=True)
def test_la_base_impide_dos_repartos_de_la_misma_regla_sin_miembro():
    """Dos NULL no chocan en Postgres: hace falta la segunda constraint parcial."""
    from django.db.utils import IntegrityError

    hogar = HouseholdFactory()
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    regla = AllocationRuleFactory(household=hogar, order=1)

    MonthlyAllocation.unscoped.create(
        household=hogar, budget_month=mes, rule=regla,
        member=None, planned_amount=Decimal("100.00"),
    )
    with pytest.raises(IntegrityError):
        MonthlyAllocation.unscoped.create(
            household=hogar, budget_month=mes, rule=regla,
            member=None, planned_amount=Decimal("100.00"),
        )
```

`MonthlyAllocation.unscoped.create` en vez de la fábrica: aquí se prueba **el esquema**, y hay que llegar a él sin que ninguna capa de Python amortigüe el golpe. `transaction=True` porque un `IntegrityError` aborta la transacción de la prueba.

- [ ] **Step 2: Corre las pruebas y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_services.py -q -k "planificar_dos_veces or impide_dos_repartos"`
Expected: FAIL. Las dos de esquema con `Failed: DID NOT RAISE IntegrityError`.

- [ ] **Step 3: Añade las dos restricciones parciales**

En `apps/budget/models/allocation.py`, dentro de `MonthlyAllocation`:

```python
    class Meta(HouseholdScoped.Meta):
        verbose_name = _("monthly split")
        verbose_name_plural = _("monthly splits")
        constraints = [
            # Dos constraints y no una: en Postgres dos NULL no chocan entre
            # si, asi que la primera no cubriria las reglas sin miembro (las
            # que no son de mesada), que son justo las de ahorro.
            models.UniqueConstraint(
                fields=["budget_month", "rule", "member"],
                condition=models.Q(member__isnull=False),
                name="un_reparto_por_regla_y_miembro",
            ),
            models.UniqueConstraint(
                fields=["budget_month", "rule"],
                condition=models.Q(member__isnull=True),
                name="un_reparto_por_regla_sin_miembro",
            ),
        ]
```

Necesitas `from django.db import models` — ya está importado en el archivo.

> **Nota sobre `_validando_unicidad`:** el docstring de `apps/households/scoping.py` explica que toda `UniqueConstraint` de un modelo con hogar debe llevar `household` entre sus campos, y `tests/test_scoping.py::test_toda_unique_constraint_de_un_modelo_con_hogar_incluye_household` lo vigila. Estas dos **no** lo llevan, así que esa prueba fallará. Es correcto que falle y hay que decidirlo: `budget_month` ya está acotado a un hogar, así que la unicidad no se ensancha entre familias. **Añade `"household"` como primer campo de ambas constraints** en vez de tocar la prueba — es más barato que discutir con una barrera que existe por buenas razones:
> ```python
>                 fields=["household", "budget_month", "rule", "member"],
> ```
> y
> ```python
>                 fields=["household", "budget_month", "rule"],
> ```

- [ ] **Step 4: Bloquea la fila en `planificar_mes`**

En `apps/budget/services.py`, sustituye el arranque de `planificar_mes`:

```python
@transaction.atomic
def planificar_mes(hogar, mes, sobrante_proyectado):
    """Aplica la cascada y escribe el reparto y las mesadas del mes (§4.5.6).

    Al confirmar la planificación, cada miembro sabe desde el día 1 cuánta
    mesada tiene, y esa cifra ya no se mueve durante el mes.
    """
    # Bloquea la fila del mes antes de mirar si ya hay reparto: sin esto, dos
    # envios del boton "Confirmar el plan" pasan los dos por el exists() antes
    # de que ninguno escriba, y el hogar acaba con las mesadas por duplicado.
    # El bloqueo es sobre BudgetMonth y no sobre MonthlyAllocation porque no se
    # puede bloquear una fila que aun no existe.
    BudgetMonth.unscoped.select_for_update().get(pk=mes.pk)

    ya = list(MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes))
    if ya:
        return ya
```

y borra las dos líneas antiguas del `if … exists(): return list(…)`.

- [ ] **Step 5: Bloquea la fila en `cerrar_mes`**

En `apps/budget/services.py`, justo después del docstring de `cerrar_mes` y **antes** de comprobar `esta_cerrado`:

```python
@transaction.atomic
def cerrar_mes(mes):
    """Escribe el MonthlyClose y congela el mes (§4.2)."""
    # El §6 del diseño del Plan 2 lo exige para materializar y para cerrar;
    # materializar ya lo hacia. Sin el, dos peticiones pueden cerrar el mismo
    # mes a la vez y escribir dos MonthlyClose, que son inmutables.
    mes = BudgetMonth.unscoped.select_for_update().get(pk=mes.pk)
    if mes.esta_cerrado:
        raise MesCerrado(f"El mes {mes} ya está cerrado.")
```

Reasignar `mes` es deliberado: la instancia recargada trae el `status` de verdad, no el que tuviera en memoria la petición que perdió la carrera.

- [ ] **Step 6: Genera la migración y corre las pruebas**

```bash
.venv/Scripts/python.exe manage.py makemigrations budget --name un_reparto_por_regla_y_miembro
.venv/Scripts/python.exe -m pytest tests/budget -q --create-db
```
Expected: PASS, incluida `tests/test_scoping.py` si añadiste `household` a las constraints.

- [ ] **Step 7: Commit**

```bash
git add apps/budget/models/allocation.py apps/budget/services.py \
        apps/budget/migrations/0007_un_reparto_por_regla_y_miembro.py \
        tests/budget/test_services.py
git commit -m "Impide que dos envios del plan dupliquen las mesadas del mes"
```

---

### Task 4: El N+1 del mes y de metas, con presupuesto de consultas

`templates/budget/mes.html` recorre líneas y transacciones accediendo a `category.etiqueta` sin `select_related`: un mes con 120 transacciones son 120 consultas **contra el pooler de Supabase**. `views.metas` llama a `meta.acumulado()` dos veces por meta —una dentro de `derivar()` y otra explícita—. Y `planificar` proyecta el mes dos veces.

El arreglo importa menos que la red de seguridad: un **presupuesto de consultas** convierte esto en una regresión detectable en vez de en un descubrimiento de producción. La Tarea 19 añade el Overview, que agrega mucho más que estas pantallas.

**Files:**
- Modify: `apps/budget/views.py` (`mes`, `metas`, `planificar`)
- Modify: `templates/budget/mes.html`
- Modify: `apps/budget/models/goals.py` (`Goal.derivar` acepta el acumulado)
- Create: `tests/test_presupuesto_consultas.py`

**Interfaces:**
- Produces: `Goal.derivar(desde=None, acumulado=None)` — si se le pasa el acumulado, no lo vuelve a calcular. La Tarea 21 lo usa.

- [ ] **Step 1: Escribe el presupuesto de consultas, que falla**

Crea `tests/test_presupuesto_consultas.py`:

```python
"""Presupuestos de consultas.

No prueban comportamiento: prueban que una pantalla no se vuelva cara sin que
nadie se entere. Los numeros son un tope acordado, no una medida sagrada; si
una tarea futura los sube con razon, se suben aqui a proposito y en su commit.
"""

import pytest
from datetime import date
from decimal import Decimal

from django.urls import reverse

from tests.factories import HouseholdFactory, MembershipFactory, UserFactory
from tests.factories_budget import (
    BudgetMonthFactory, CategoryFactory, GoalFactory, TransactionFactory,
)

CONSULTAS_MES = 12
CONSULTAS_METAS = 10


@pytest.fixture
def hogar_con_movimiento(db):
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    categoria = CategoryFactory(household=hogar)
    for _i in range(50):
        TransactionFactory(
            household=hogar, budget_month=mes, category=categoria,
            amount=Decimal("10.00"), date=date(2026, 3, 5),
        )
    return hogar, user, mes


@pytest.mark.django_db
def test_la_pantalla_del_mes_no_hace_una_consulta_por_transaccion(
    client, django_assert_num_queries, hogar_con_movimiento
):
    _hogar, user, _mes = hogar_con_movimiento
    client.force_login(user)
    with django_assert_num_queries(CONSULTAS_MES):
        respuesta = client.get(reverse("budget:mes", args=[2026, 3]))
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_metas_no_calcula_el_acumulado_dos_veces(
    client, django_assert_num_queries, hogar_con_movimiento
):
    hogar, user, _mes = hogar_con_movimiento
    for _i in range(5):
        GoalFactory(household=hogar)
    client.force_login(user)
    with django_assert_num_queries(CONSULTAS_METAS):
        respuesta = client.get(reverse("budget:metas"))
    assert respuesta.status_code == 200
```

- [ ] **Step 2: Corre la prueba y anota el número real**

Run: `.venv/Scripts/python.exe -m pytest tests/test_presupuesto_consultas.py -q`
Expected: FAIL, con un mensaje del tipo `Expected to perform 12 queries but 57 were done`. **Anota los dos números reales**: son la prueba de que el N+1 existe, y el punto de partida contra el que medirás la mejora.

- [ ] **Step 3: Arregla la pantalla del mes**

En `apps/budget/views.py`, dentro de `mes`, sustituye el `render`:

```python
    resultado = services.obtener_mes(hogar, anio, numero)
    es_proyeccion = isinstance(resultado, services.ProyeccionDeMes)
    contexto = {
        "resultado": resultado, "es_proyeccion": es_proyeccion,
        "anio": anio, "numero": numero,
    }
    if not es_proyeccion:
        # select_related sobre la categoria: la plantilla lee category.etiqueta
        # en cada fila, y sin esto un mes con 120 transacciones son 120
        # consultas contra el pooler.
        contexto["lineas"] = resultado.lineas.select_related("category")
        contexto["transacciones"] = resultado.transacciones.select_related("category")
    return render(request, "budget/mes.html", contexto)
```

Y en `templates/budget/mes.html`, cambia los dos bucles para que recorran las variables nuevas: `{% for linea in lineas %}` y `{% for tx in transacciones %}`, en vez de `resultado.lineas.all` y `resultado.transacciones.all`.

- [ ] **Step 4: Deja que el acumulado se calcule una vez**

En `apps/budget/models/goals.py`, dentro de `Goal`:

```python
    def derivar(self, desde=None, acumulado=None):
        """El dato que falta: el aporte mensual o la fecha de llegada.

        `acumulado` se puede pasar ya calculado: quien pinta una lista de metas
        lo necesita tambien para la barra de progreso, y calcularlo dos veces
        es una consulta por meta y por pantalla.
        """
        return motor_goals.derivar(
            self.contribution_mode,
            objetivo=self.target_amount,
            acumulado=self.acumulado() if acumulado is None else acumulado,
            desde=desde or timezone.localdate(),
            fecha_objetivo=self.target_date,
            aporte_mensual=self.monthly_amount,
        )
```

Y en `apps/budget/views.py`, dentro de `metas`:

```python
    filas = []
    for meta in Goal.objects.for_household(hogar):
        acumulado = meta.acumulado()
        aporte, fecha = meta.derivar(acumulado=acumulado)
        filas.append({"meta": meta, "aporte": aporte, "fecha": fecha,
                      "acumulado": acumulado})
```

- [ ] **Step 5: Deja de proyectar el mes dos veces en `planificar`**

En `apps/budget/views.py`, dentro de `planificar`, `obtener_mes` ya proyecta por dentro cuando hace falta. Lo que sobra es la segunda llamada explícita cuando el mes **ya es una fila**:

```python
    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    # obtener_mes devuelve una fila (mes corriente materializado) o una
    # ProyeccionDeMes. Solo en el primer caso hace falta proyectar aparte,
    # porque planificar reparte sobre el sobrante proyectado del mes.
    proyeccion = (
        mes_actual if isinstance(mes_actual, services.ProyeccionDeMes)
        else services.proyectar(hogar, hoy.year, hoy.month)
    )
```

- [ ] **Step 6: Ajusta los topes y corre la prueba**

Vuelve a correr la prueba, mira los números nuevos y **fija `CONSULTAS_MES` y `CONSULTAS_METAS` a lo que ahora salga**. Deben ser mucho menores que los del Step 2 y, sobre todo, **no deben crecer con el número de transacciones ni de metas** — compruébalo subiendo el `range(50)` a `range(100)` a mano una vez: el número no debe moverse. Devuelve el `range` a 50.

Run: `.venv/Scripts/python.exe -m pytest tests/test_presupuesto_consultas.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/budget/views.py apps/budget/models/goals.py \
        templates/budget/mes.html tests/test_presupuesto_consultas.py
git commit -m "Quita el N+1 del mes y de metas, y pone presupuesto de consultas"
```

---

### Task 5: La migración que siembra el catálogo en los hogares que ya existen

`seeds.sembrar()` solo corre dentro de `households.services.crear_hogar`. Cualquier hogar creado antes del Plan 2 no tiene árbol, y `services._categoria_de_ingreso` estalla con su `LookupError` en cuanto alguien mire un mes. Sin esta migración, **el Plan 3 no se puede desplegar sobre una base que ya tenga hogares**.

**Files:**
- Create: `apps/budget/migrations/0008_sembrar_catalogo_en_hogares_previos.py`
- Test: `tests/budget/test_models.py`

**Interfaces:**
- Consumes: `apps.budget.seeds.ARBOL`.

- [ ] **Step 1: Escribe la prueba que falla**

En `tests/budget/test_models.py`:

```python
@pytest.mark.django_db
def test_un_hogar_sin_arbol_sembrado_no_puede_proyectar():
    """El fallo que la migracion 0008 arregla, escrito como prueba.

    HouseholdFactory crea el hogar sin pasar por crear_hogar, que es
    exactamente lo que le pasa a un hogar creado antes del Plan 2.
    """
    from apps.budget import services

    hogar = HouseholdFactory()
    with pytest.raises(LookupError):
        services.proyectar(hogar, 2026, 3)


@pytest.mark.django_db
def test_sembrar_arregla_un_hogar_sin_arbol():
    from apps.budget import services
    from apps.budget.seeds import sembrar

    hogar = HouseholdFactory()
    sembrar(hogar)
    proyeccion = services.proyectar(hogar, 2026, 3)
    assert proyeccion.total_ingresos == Decimal("0.00")
```

Estas dos pruebas documentan el agujero y la cura. La migración en sí no se prueba con pytest —correr migraciones dentro de una prueba es lento y frágil contra el pooler—; se verifica a mano en el Step 4.

- [ ] **Step 2: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_models.py -q -k "arbol_sembrado or sembrar_arregla"`
Expected: PASS las dos. Documentan comportamiento actual; la migración es lo nuevo.

- [ ] **Step 3: Escribe la migración de datos**

Crea `apps/budget/migrations/0008_sembrar_catalogo_en_hogares_previos.py`:

```python
"""Siembra el arbol de categorias en los hogares creados antes del Plan 2.

seeds.sembrar() solo corre dentro de households.services.crear_hogar, asi que
un hogar anterior no tiene arbol y hace estallar _categoria_de_ingreso con su
LookupError en cuanto alguien mire un mes.

Se usa ARBOL directamente y no seeds.sembrar(): sembrar() escribe con el modelo
real, y una migracion tiene que escribir con el historico. La forma del arbol
puede cambiar despues de esta migracion; lo que se siembre aqui sera el arbol
de entonces, y eso es correcto para un hogar que hoy no tiene ninguno.
"""

from django.db import migrations

from apps.budget.seeds import ARBOL


def _sembrar_los_que_falten(apps, schema_editor):
    Household = apps.get_model("households", "Household")
    Category = apps.get_model("budget", "Category")

    for hogar in Household.objects.all():
        if Category.objects.filter(household=hogar).exists():
            continue
        creadas = {}
        for slug, _etiqueta, padre, kind in ARBOL:
            creadas[slug] = Category.objects.create(
                household=hogar, slug=slug, is_system=True,
                kind=kind, parent=creadas.get(padre), name="",
            )


def _no_se_deshace(apps, schema_editor):
    """Borrar categorias podria llevarse por delante reglas que las usan."""


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0007_un_reparto_por_regla_y_miembro"),
        ("households", "0003_invitation"),
    ]

    operations = [
        migrations.RunPython(_sembrar_los_que_falten, _no_se_deshace),
    ]
```

Los modelos históricos usan `_default_manager`, que en el histórico **no** es el manager estricto, así que `Category.objects.filter(...)` aquí es correcto.

- [ ] **Step 4: Verifica la migración a mano contra un hogar sin árbol**

```bash
.venv/Scripts/python.exe manage.py migrate budget 0007
.venv/Scripts/python.exe manage.py shell -c "from apps.households.models import Household; h = Household.objects.create(name='Sin arbol', family_size=2); print('creado', h.pk)"
.venv/Scripts/python.exe manage.py migrate budget
.venv/Scripts/python.exe manage.py shell -c "from apps.budget.models import Category; from apps.households.models import Household; h = Household.objects.get(name='Sin arbol'); print(Category.objects.for_household(h).count())"
```
Expected: la última orden imprime `17`, que es `len(ARBOL)`.

Después, limpia el hogar de prueba:
```bash
.venv/Scripts/python.exe manage.py shell -c "from apps.households.models import Household; Household.objects.filter(name='Sin arbol').delete()"
```

- [ ] **Step 5: Corre las dos mitades de la suite**

Run: `.venv/Scripts/python.exe -m pytest tests/budget -q --create-db`
Run: `.venv/Scripts/python.exe -m pytest -q --ignore=tests/budget`
Expected: PASS las dos. Es el cierre de la tanda 1, así que aquí toca la suite entera.

- [ ] **Step 6: Commit**

```bash
git add apps/budget/migrations/0008_sembrar_catalogo_en_hogares_previos.py \
        tests/budget/test_models.py
git commit -m "Siembra el catalogo en los hogares creados antes del Plan 2"
```

> **Punto de control 1.** La aplicación de hoy hace lo mismo, pero bien: ningún mes cerrado admite escrituras por ninguno de los cuatro caminos, el ahorro del hogar no lleva el nombre de nadie, dos clics no duplican mesadas, las pantallas no crecen en consultas con los datos, y la base se puede desplegar sobre hogares antiguos. Si hay que parar, este es un buen sitio.

---
## Tanda 2 · La suscripción

Siete tareas. La app nueva, la guardia transversal, el checkout, el webhook y una pantalla plana. **Va aquí y no al final** por una razón concreta: la guardia vive en `_decorador`, así que toda pantalla de las tandas 3 a 6 nace cubierta. Hacerla al final obligaría a auditar pantalla por pantalla.

Las pantallas de esta tanda son **feas a propósito**, como las del Plan 2: la Tarea 16 las viste.

---

### Task 6: `Subscription` y `StripeEvent`, y los tres sitios que las crean

Hoy no existe nada: ni modelo, ni `trial_ends_at` en `Household`, ni el paquete `stripe`. El §5.1 se lee como si el reloj del trial ya corriera, y no corre.

**La expiración se deriva y no se guarda** (§2.1 del spec): `status` almacena `trialing` o `active`, y `expired` sale de comparar `trial_ends_at` con el reloj. La razón es la que hizo perezoso el ciclo del mes: no hay cron en este stack, así que un estado guardado necesitaría que alguien lo escribiera a medianoche.

**Files:**
- Create: `apps/subscriptions/__init__.py`, `apps.py`, `models.py`, `services.py`, `admin.py`, `migrations/__init__.py`
- Modify: `config/settings.py` (`INSTALLED_APPS`)
- Modify: `apps/households/services.py` (`crear_hogar`)
- Modify: `tests/factories.py` (`HouseholdFactory`)
- Create: `apps/subscriptions/migrations/0001_initial.py`, `0002_suscripcion_para_hogares_previos.py`
- Create: `tests/test_suscripcion.py`

**Interfaces:**
- Produces:
  - `Subscription.esta_vigente -> bool` — propiedad. `True` si `status == "active"`, o si `status == "trialing"` y `trial_ends_at > timezone.now()`.
  - `Subscription.estado_visible -> str` — `"trialing"` | `"active"` | `"expired"`, para la interfaz.
  - `Subscription.dias_restantes -> int | None` — días enteros hasta `trial_ends_at`; `None` si ya está pagada.
  - `subscriptions.services.crear_suscripcion(household) -> Subscription`
  - `Household.puede_escribir -> bool` — `cached_property`. La consumen las Tareas 7 y 8.

- [ ] **Step 1: Instala `stripe` y declara la app**

```bash
.venv/Scripts/python.exe -m pip install "stripe==11.*"
```

Añade a `requirements.txt`, tras `Pillow`:
```
stripe==11.*
```

Y en `config/settings.py`, dentro de `INSTALLED_APPS`, tras `"apps.budget"`:
```python
    "apps.subscriptions",
```

Añade también, al final de `config/settings.py`:
```python
# Stripe (§5). Vacias en desarrollo y en pruebas: la suite NUNCA llama a Stripe.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRECIO_CENTAVOS = 2500      # CAD $25, pago unico (§5.1)
DIAS_DE_PRUEBA = 14
```

Comprueba que `os` ya esté importado en `settings.py`; si no, añádelo arriba.

- [ ] **Step 2: Escribe las pruebas que fallan**

Crea `tests/test_suscripcion.py`:

```python
import pytest
from datetime import timedelta

from django.utils import timezone

from apps.households.services import crear_hogar
from apps.subscriptions.models import Subscription
from tests.factories import HouseholdFactory, UserFactory


@pytest.mark.django_db
def test_un_hogar_nuevo_nace_con_catorce_dias_y_sin_tarjeta():
    user = UserFactory()
    hogar = crear_hogar(user, "Los Perez", 3)

    suscripcion = hogar.subscription
    assert suscripcion.status == Subscription.TRIALING
    assert suscripcion.paid_at is None
    assert 13 <= suscripcion.dias_restantes <= 14
    assert suscripcion.esta_vigente is True
    assert suscripcion.estado_visible == "trialing"


@pytest.mark.django_db
def test_el_dia_quince_deja_de_estar_vigente():
    hogar = HouseholdFactory()
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    assert hogar.subscription.esta_vigente is False
    assert hogar.subscription.estado_visible == "expired"


@pytest.mark.django_db
def test_una_suscripcion_pagada_esta_vigente_para_siempre():
    hogar = HouseholdFactory()
    suscripcion = hogar.subscription
    suscripcion.status = Subscription.ACTIVE
    suscripcion.paid_at = timezone.now()
    suscripcion.trial_ends_at = timezone.now() - timedelta(days=400)
    suscripcion.save()

    assert suscripcion.esta_vigente is True
    assert suscripcion.estado_visible == "active"
    assert suscripcion.dias_restantes is None


@pytest.mark.django_db
def test_la_fabrica_tambien_crea_la_suscripcion():
    """§2.4 del spec: la ausencia de fila significa 'puede escribir', pero el
    caso no debe poder aparecer. Los tres sitios que crean hogares la crean."""
    hogar = HouseholdFactory()
    assert hogar.subscription is not None


@pytest.mark.django_db
def test_un_hogar_sin_fila_de_suscripcion_puede_escribir():
    """Fallar cerrado romperia toda fabrica que no pase por crear_hogar."""
    hogar = HouseholdFactory()
    hogar.subscription.delete()
    hogar = type(hogar).objects.get(pk=hogar.pk)

    assert hogar.puede_escribir is True
```

- [ ] **Step 3: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_suscripcion.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'apps.subscriptions'`.

- [ ] **Step 4: Escribe la app**

`apps/subscriptions/__init__.py` vacío. `apps/subscriptions/apps.py`:

```python
from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subscriptions"
```

`apps/subscriptions/models.py`:

```python
"""La suscripcion del §5: un pago unico de CAD $25 tras catorce dias de prueba.

Ninguno de los dos modelos es HouseholdScoped. Subscription pertenece a un
hogar en el sentido de la titularidad, no del aislamiento —hay exactamente una
por hogar y se llega a ella por el hogar—, y StripeEvent no pertenece a
ninguno: es el registro de lo que Stripe nos conto.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField
from apps.households.models import Household


def _fin_de_la_prueba():
    return timezone.now() + timedelta(days=settings.DIAS_DE_PRUEBA)


class Subscription(models.Model):
    """El estado de pago de un hogar.

    `status` guarda `trialing` o `active`. **`expired` no se guarda nunca**: se
    deriva comparando trial_ends_at con el reloj. Un estado guardado exigiria
    que alguien lo escribiera a medianoche, y no hay cron en este stack — la
    misma razon que hizo perezoso el ciclo del mes.
    """

    TRIALING, ACTIVE = "trialing", "active"
    STATUS_CHOICES = [(TRIALING, _("Trial")), (ACTIVE, _("Active"))]
    EXPIRED = "expired"      # solo para estado_visible; nunca se guarda

    household = models.OneToOneField(
        Household, on_delete=models.CASCADE, related_name="subscription"
    )
    status = models.CharField(_("status"), max_length=10, choices=STATUS_CHOICES, default=TRIALING)
    trial_ends_at = models.DateTimeField(_("trial ends at"), default=_fin_de_la_prueba)
    stripe_customer_id = models.CharField(max_length=120, blank=True, default="")
    stripe_session_id = models.CharField(max_length=120, blank=True, default="")
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    # Se guardan para que un cambio de precio no reescriba lo que alguien pago.
    amount = MoneyField(_("amount"), default=None, null=True, blank=True)
    currency = models.CharField(max_length=3, default="CAD")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")

    def __str__(self):
        return f"{self.household} · {self.estado_visible}"

    @property
    def esta_vigente(self):
        if self.status == self.ACTIVE:
            return True
        return self.trial_ends_at > timezone.now()

    @property
    def estado_visible(self):
        if self.status == self.ACTIVE:
            return self.ACTIVE
        return self.TRIALING if self.esta_vigente else self.EXPIRED

    @property
    def dias_restantes(self):
        """Dias enteros de prueba que quedan. None si ya esta pagada."""
        if self.status == self.ACTIVE:
            return None
        return max(0, (self.trial_ends_at - timezone.now()).days)


class StripeEvent(models.Model):
    """La idempotencia del §5.2, hecha esquema.

    Stripe reintenta los webhooks, y los reintenta en paralelo. `event_id`
    unico es toda la idempotencia: sin el, un hogar puede quedar en un estado
    inconsistente por un reintento perfectamente normal.
    """

    event_id = models.CharField(max_length=120, unique=True)
    type = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Stripe event")
        verbose_name_plural = _("Stripe events")
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.type} · {self.event_id}"
```

`apps/subscriptions/services.py` (por ahora solo la creación; el resto llega en las Tareas 9 y 10):

```python
"""Lo que se puede hacer con una suscripcion. No importa `stripe`."""

from .models import Subscription


def crear_suscripcion(household):
    """La suscripcion de un hogar recien creado: catorce dias, sin tarjeta."""
    suscripcion, _creada = Subscription.objects.get_or_create(household=household)
    return suscripcion
```

`apps/subscriptions/admin.py`:

```python
from django.contrib import admin

from .models import StripeEvent, Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("household", "status", "trial_ends_at", "paid_at")
    readonly_fields = ("created_at",)


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ("type", "event_id", "received_at", "processed_at")
    readonly_fields = ("event_id", "type", "payload", "received_at", "processed_at")
```

- [ ] **Step 5: Añade `Household.puede_escribir`**

En `apps/households/models.py`, dentro de `Household`, y con `from django.utils.functional import cached_property` arriba:

```python
    @cached_property
    def puede_escribir(self):
        """Si este hogar admite escrituras hoy (§5.2).

        Un hogar SIN fila de suscripcion puede escribir. Es deliberado (§2.4
        del spec del Plan 3): fallar cerrado romperia toda fabrica de pruebas
        que no pase por crear_hogar, y lo que hay que impedir es que escriba un
        hogar con una suscripcion vencida, no uno sin fila. Los tres sitios que
        crean hogares crean la suscripcion, y hay prueba de ello.

        `cached_property` y no `property`: la guardia de HouseholdScoped.save()
        pregunta esto en cada guardado, y sin cache seria una consulta por fila
        escrita.
        """
        suscripcion = getattr(self, "subscription", None)
        return True if suscripcion is None else suscripcion.esta_vigente
```

`getattr` con defecto y no un `try/except`: en un `OneToOneField` inverso sin fila, Django lanza `RelatedObjectDoesNotExist`, que **sí** hereda de `AttributeError`, así que `getattr(..., None)` lo absorbe limpiamente.

- [ ] **Step 6: Crea la suscripción en los tres sitios**

En `apps/households/services.py`, dentro de `crear_hogar`, tras `sembrar(household)`:

```python
    from apps.subscriptions.services import crear_suscripcion

    crear_suscripcion(household)
    return household
```

En `tests/factories.py`, dentro de `HouseholdFactory`:

```python
class HouseholdFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Household
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Hogar {n}")
    family_size = 4

    @factory.post_generation
    def suscripcion(obj, create, extracted, **kwargs):
        """Sin esto, cada hogar de prueba nace sin suscripcion y la guardia del
        §2.4 lo dejaria escribir por la puerta de atras en vez de por la buena."""
        if not create:
            return
        from apps.subscriptions.services import crear_suscripcion

        crear_suscripcion(obj)
```

- [ ] **Step 7: Genera las dos migraciones**

```bash
.venv/Scripts/python.exe manage.py makemigrations subscriptions --name initial
```

Y crea a mano `apps/subscriptions/migrations/0002_suscripcion_para_hogares_previos.py`:

```python
"""Da suscripcion a los hogares que ya existen.

trial_ends_at = HOY + 14 dias, no created_at + 14. Una migracion no debe dejar
a nadie fuera retroactivamente: con la fecha de creacion, cada hogar existente
quedaria expirado en el instante de aplicarla, y el primer efecto visible del
Plan 3 seria que la aplicacion deja de aceptar escrituras.
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def _dar_suscripcion(apps, schema_editor):
    Household = apps.get_model("households", "Household")
    Subscription = apps.get_model("subscriptions", "Subscription")

    fin = timezone.now() + timedelta(days=14)
    for hogar in Household.objects.filter(subscription__isnull=True):
        Subscription.objects.create(
            household=hogar, status="trialing", trial_ends_at=fin, currency="CAD",
        )


def _quitarlas(apps, schema_editor):
    apps.get_model("subscriptions", "Subscription").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0001_initial"),
        ("households", "0003_invitation"),
    ]

    operations = [migrations.RunPython(_dar_suscripcion, _quitarlas)]
```

El `14` va literal y no `settings.DIAS_DE_PRUEBA`: una migración es un hecho histórico y no debe cambiar de significado si mañana el trial pasa a 30 días.

- [ ] **Step 8: Corre las pruebas con `--create-db`**

Run: `.venv/Scripts/python.exe -m pytest tests/test_suscripcion.py -q --create-db`
Expected: PASS las cinco.

- [ ] **Step 9: Commit**

```bash
git add apps/subscriptions/ apps/households/models.py apps/households/services.py \
        config/settings.py requirements.txt tests/factories.py tests/test_suscripcion.py
git commit -m "Anade la suscripcion con su reloj de prueba de catorce dias"
```

---

### Task 7: La guardia unificada, en las dos capas

Tres condiciones bloquean una escritura: sin permiso, mes cerrado, y ahora suscripción vencida. El §5.7 del diseño del Plan 2 ya argumentó por qué hacen falta **dos capas**, y el argumento vale igual aquí: *"la capa de modelo es la que no se puede rodear"*.

La guardia de vista **bloquea por método HTTP y no por vista**: así "expirar no destruye datos, solo lectura" se cumple por construcción, y las vistas de htmx de la tanda 5 nacen cubiertas sin que nadie tenga que acordarse.

**Files:**
- Modify: `apps/households/permissions.py` (`_decorador`, y `SuscripcionVencida` nueva)
- Modify: `apps/households/scoping.py` (`HouseholdScoped.save()`)
- Modify: `templates/403.html`
- Test: `tests/test_suscripcion.py`

**Interfaces:**
- Produces:
  - `apps.households.permissions.SuscripcionVencida` — subclase de `PermissionDenied`, para que la maquinaria de 403 que ya existe la sirva sin middleware nuevo.
  - `apps.subscriptions.models.SuscripcionVencidaError` — excepción llana, para la capa de modelo.
  - `apps.households.permissions.sin_guardia_de_suscripcion(vista)` — decorador que marca una vista como exenta. Lo usa la Tarea 9.
  - `apps.budget.models.months.MesCerrado` sigue igual; no se toca.

> **Son dos excepciones a propósito, y no hay que unificarlas.** `SuscripcionVencida` hereda de `PermissionDenied` porque su trabajo es convertirse en un 403 HTTP; una escritura desde un comando de gestión o un script no ocurre dentro de una petición, y lanzar allí una excepción de HTTP mentiría sobre lo que pasó. Es la misma separación que ya existe entre el rechazo de permiso en la vista y `MesCerrado` en el modelo.

- [ ] **Step 1: Escribe las pruebas que fallan**

En `tests/test_suscripcion.py`:

```python
@pytest.mark.django_db
def test_un_hogar_expirado_lee_pero_no_escribe(client):
    from django.urls import reverse
    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    assert client.get(reverse("budget:configurar")).status_code == 200
    assert client.post(reverse("budget:ingreso_nuevo"), {}).status_code == 403


@pytest.mark.django_db
def test_la_capa_de_modelo_lanza_aunque_se_rodee_la_vista():
    from decimal import Decimal

    from apps.subscriptions.models import SuscripcionVencidaError
    from tests.factories_budget import CategoryFactory

    hogar = HouseholdFactory()
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    hogar = type(hogar).objects.get(pk=hogar.pk)   # limpia la cached_property

    with pytest.raises(SuscripcionVencidaError):
        CategoryFactory(household=hogar)


@pytest.mark.django_db
def test_un_hogar_en_prueba_escribe_sin_problema(client):
    from django.urls import reverse
    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    assert client.get(reverse("budget:configurar")).status_code == 200
    # 200 porque el formulario vacio se re-renderiza con errores, no 403.
    assert client.post(reverse("budget:ingreso_nuevo"), {}).status_code == 200
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_suscripcion.py -q -k "expirado or capa_de_modelo or en_prueba"`
Expected: FAIL. La primera con `403 != 403`… no: con `200 == 403` porque hoy nada bloquea. La segunda con `ImportError`.

- [ ] **Step 3: Declara la excepción del modelo**

En `apps/subscriptions/models.py`, arriba del todo tras los imports:

```python
class SuscripcionVencidaError(Exception):
    """Se intento escribir en un hogar cuya suscripcion vencio (§5.2)."""
```

- [ ] **Step 4: Pon la guardia en la capa de modelo**

En `apps/households/scoping.py`, dentro de `HouseholdScoped`, añade el `save()` que hoy no existe:

```python
    def save(self, *args, **kwargs):
        """Rechaza la escritura si la suscripcion del hogar vencio (§5.2).

        Es la capa que no se puede rodear: cubre el comando de gestion, los
        scripts y cualquier camino que no pase por una vista. La otra capa esta
        en apps/households/permissions.py::_decorador.

        Alcance real, para que nadie lea aqui mas de lo que hay: cubre todo
        `save()`, incluido con update_fields. NO cubre `queryset.update()` ni
        `bulk_create()`, que no llaman a save() — exactamente el mismo punto
        ciego que EscrituraAcotadaAlMes documenta en su docstring. Quedan
        prohibidos por convencion sobre estos modelos.
        """
        from apps.subscriptions.models import SuscripcionVencidaError

        if self.household_id and not self.household.puede_escribir:
            raise SuscripcionVencidaError(
                f"La suscripcion del hogar {self.household_id} vencio: solo lectura."
            )
        super().save(*args, **kwargs)
```

El import va dentro de la función a propósito: `apps.subscriptions.models` importa `apps.households.models`, y a nivel de módulo esto sería un ciclo.

> **Ojo con el orden de las bases.** `BudgetLine`, `Transaction`, `MonthlyAllocation` y `GoalContribution` heredan `(EscrituraAcotadaAlMes, HouseholdScoped)`. Con ese orden, `EscrituraAcotadaAlMes.save()` corre primero y llama a `super().save()`, que es el de `HouseholdScoped`. Las dos guardias se aplican, en ese orden. No cambies el orden.

- [ ] **Step 5: Pon la guardia en la capa de vista**

En `apps/households/permissions.py`, añade la excepción, el decorador de exención, y la comprobación dentro de `_decorador`:

```python
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class SuscripcionVencida(PermissionDenied):
    """La prueba termino y el hogar no ha pagado: solo lectura (§5.2).

    Subclase de PermissionDenied para que la maquinaria de 403 que ya existe la
    sirva sin middleware nuevo. La plantilla 403 la distingue y ofrece pagar.
    """


def sin_guardia_de_suscripcion(vista):
    """Marca una vista como exenta de la guardia de suscripcion.

    Existe con nombre y no como una condicion escondida dentro de la guardia:
    si la guardia cubriera las vistas de pago, un hogar expirado no podria
    pagar para dejar de estarlo. Es la unica exencion, y se ve en la revision.
    """
    vista.permite_escritura_expirada = True
    return vista
```

Y dentro de `_decorador`, en la función `envuelta`, entre `comprobar(membresia)` y la llamada a la vista:

```python
def _decorador(comprobar):
    def envolver(vista):
        @login_required
        @functools.wraps(vista)
        def envuelta(request, *args, **kwargs):
            membresia = membresia_actual(request)
            comprobar(membresia)
            # La guardia de suscripcion, por METODO y no por vista: asi las
            # vistas de htmx que aun no existen nacen cubiertas, y "expirar no
            # destruye datos" (§5.2) se cumple por construccion.
            if (
                request.method not in METODOS_SEGUROS
                and not getattr(vista, "permite_escritura_expirada", False)
                and not membresia.household.puede_escribir
            ):
                raise SuscripcionVencida(
                    _("Your trial has ended. Subscribe to keep adding to your budget.")
                )
            return vista(request, membresia.household, *args, **kwargs)

        return envuelta

    return envolver
```

Añade `"SuscripcionVencida"` y `"sin_guardia_de_suscripcion"` a `__all__`.

- [ ] **Step 6: Que el 403 ofrezca pagar**

En `templates/403.html`, dentro del bloque de contenido:

```html
  {% if es_suscripcion_vencida %}
    <p><a class="btn btn--primary" href="{% url 'subscriptions:estado' %}">
      {% translate "See subscription" %}</a></p>
  {% endif %}
```

Y donde se sirva el 403 —Django pasa la excepción al handler— haz que el contexto lleve la bandera. La forma más simple y sin middleware: un handler propio en `config/urls.py`:

```python
from django.shortcuts import render

from apps.households.permissions import SuscripcionVencida


def permiso_denegado(request, exception=None):
    return render(request, "403.html", {
        "es_suscripcion_vencida": isinstance(exception, SuscripcionVencida),
        "mensaje": str(exception) if exception else "",
    }, status=403)


handler403 = "config.urls.permiso_denegado"
```

La URL `subscriptions:estado` la crea la Tarea 11; hasta entonces el `{% url %}` reventaría, así que **este step se completa después de la Tarea 11** o se deja el enlace apuntando a `households:ajustes` y se cambia allí. Escoge lo segundo para no dejar la rama rota.

- [ ] **Step 7: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/test_suscripcion.py -q`
Expected: PASS.

Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS. Si alguna prueba de presupuesto falla con `SuscripcionVencidaError`, es que una fábrica crea filas contra un hogar sin suscripción vigente — revisa que la Tarea 6 Step 6 esté hecha.

- [ ] **Step 8: Commit**

```bash
git add apps/households/permissions.py apps/households/scoping.py \
        apps/subscriptions/models.py templates/403.html config/urls.py \
        tests/test_suscripcion.py
git commit -m "Bloquea las escrituras de un hogar cuya prueba termino, en dos capas"
```

---

### Task 8: Un hogar expirado no materializa ni cierra meses

Esta es la consecuencia menos obvia del §5.2, y la que más daño haría si se pasa por alto. El ciclo del mes se dispara **al entrar**: un hogar expirado que solo *mira* su presupuesto provocaría escrituras —materializar el mes corriente, cerrar en cadena los vencidos—, y esas escrituras ahora revientan con `SuscripcionVencidaError` en medio de una petición `GET`.

Y aunque no reventaran: materializar un mes nuevo **es** registrar algo nuevo, que es lo que el §5.2 prohíbe.

**Files:**
- Modify: `apps/budget/services.py` (`obtener_mes`)
- Test: `tests/budget/test_month_cycle.py`

**Interfaces:**
- Consumes: `Household.puede_escribir` de la Tarea 6.
- Produces: `obtener_mes` conserva su firma. Para un hogar sin derecho de escritura devuelve la fila si existe, y una `ProyeccionDeMes` si no — nunca crea nada.

- [ ] **Step 1: Escribe las pruebas que fallan**

En `tests/budget/test_month_cycle.py`:

```python
@pytest.mark.django_db
def test_un_hogar_expirado_no_materializa_el_mes_corriente():
    from datetime import timedelta

    from django.utils import timezone

    from apps.budget import services
    from apps.budget.models import BudgetMonth

    hogar = HouseholdFactory()
    sembrar(hogar)
    hoy = timezone.localdate()
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    hogar = type(hogar).objects.get(pk=hogar.pk)

    resultado = services.obtener_mes(hogar, hoy.year, hoy.month)

    assert isinstance(resultado, services.ProyeccionDeMes)
    assert not BudgetMonth.objects.for_household(hogar).exists()


@pytest.mark.django_db
def test_un_hogar_expirado_ve_su_historia_pero_no_cierra_nada():
    from datetime import timedelta

    from django.utils import timezone

    from apps.budget import services
    from apps.budget.models import BudgetMonth, MonthlyClose

    hogar = HouseholdFactory()
    sembrar(hogar)
    viejo = BudgetMonthFactory(household=hogar, year=2020, month=1, status="open")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    hogar = type(hogar).objects.get(pk=hogar.pk)

    resultado = services.obtener_mes(hogar, 2020, 1)

    assert resultado.pk == viejo.pk
    # Vencido de sobra, y aun asi sigue abierto: no se cerro en cadena.
    assert BudgetMonth.objects.for_household(hogar).get(pk=viejo.pk).status == "open"
    assert not MonthlyClose.objects.for_household(hogar).exists()


@pytest.mark.django_db
def test_al_pagar_la_cadena_de_cierres_se_pone_al_dia():
    """El caso del §4 del documento de estado: expira, pasan meses, paga."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.budget import services
    from apps.budget.models import BudgetMonth
    from apps.subscriptions.models import Subscription

    hogar = HouseholdFactory()
    sembrar(hogar)
    BudgetMonthFactory(household=hogar, year=2020, month=1, status="open")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    hogar.subscription.status = Subscription.ACTIVE
    hogar.subscription.paid_at = timezone.now()
    hogar.subscription.save()
    hogar = type(hogar).objects.get(pk=hogar.pk)

    services.obtener_mes(hogar, 2020, 1)

    assert BudgetMonth.objects.for_household(hogar).get(year=2020, month=1).status == "closed"
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_month_cycle.py -q -k expirado`
Expected: FAIL, con `SuscripcionVencidaError` saliendo de dentro de `materializar`.

- [ ] **Step 3: Detén el ciclo para un hogar sin derecho de escritura**

En `apps/budget/services.py`, al principio del cuerpo de `obtener_mes`, tras resolver `hoy`:

```python
    hoy = hoy or timezone.localdate()

    if not hogar.puede_escribir:
        # §5.2: expirar no destruye datos, pero tampoco crea ninguno. El ciclo
        # se dispara al ENTRAR, asi que sin esto un hogar expirado que solo
        # mira su presupuesto provocaria escrituras — y materializar un mes es
        # registrar algo nuevo, que es justo lo prohibido. Se le da lo que ya
        # existe, y el mes corriente se trata como uno futuro: proyectado, sin
        # persistir. Al pagar, cerrar_vencidos se pone al dia solo.
        existente = (
            BudgetMonth.objects.for_household(hogar)
            .filter(year=anio, month=mes).first()
        )
        return existente if existente is not None else proyectar(hogar, anio, mes)

    cerrar_vencidos(hogar, hoy)
```

- [ ] **Step 4: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_month_cycle.py -q`
Expected: PASS las tres nuevas y las que ya había.

- [ ] **Step 5: Commit**

```bash
git add apps/budget/services.py tests/budget/test_month_cycle.py
git commit -m "Impide que un hogar expirado fabrique meses solo por entrar"
```

---

### Task 9: Stripe Checkout, localizado

El §5.3 pide que la pasarela aparezca en el idioma del usuario. `gateway.py` es **el único módulo del proyecto que importa `stripe`**, y esa frontera es lo que permite que la suite entera corra sin claves y sin red.

**Files:**
- Create: `apps/subscriptions/gateway.py`, `views.py`, `urls.py`
- Modify: `config/urls.py`
- Modify: `apps/subscriptions/services.py`
- Test: `tests/test_suscripcion.py`

**Interfaces:**
- Produces:
  - `gateway.crear_sesion_de_pago(household, locale, url_exito, url_cancelacion) -> str` — devuelve la URL de la pasarela.
  - Rutas `subscriptions:pagar` (POST), `subscriptions:retorno` (GET).

- [ ] **Step 1: Escribe las pruebas que fallan**

En `tests/test_suscripcion.py`:

```python
@pytest.mark.django_db
def test_pagar_manda_a_stripe_con_el_idioma_y_el_hogar(client, monkeypatch):
    from django.urls import reverse
    from tests.factories import MembershipFactory

    capturado = {}

    def falso_crear(household, locale, url_exito, url_cancelacion):
        capturado["household"] = household
        capturado["locale"] = locale
        return "https://checkout.stripe.com/c/pay/fake"

    monkeypatch.setattr("apps.subscriptions.views.crear_sesion_de_pago", falso_crear)

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.post(reverse("subscriptions:pagar"))

    assert respuesta.status_code == 302
    assert respuesta["Location"].startswith("https://checkout.stripe.com/")
    assert capturado["household"] == hogar
    assert capturado["locale"] == "en"


@pytest.mark.django_db
def test_un_hogar_expirado_si_puede_pagar(client, monkeypatch):
    """La exencion del §2.2: si la guardia cubriera esto, un hogar expirado no
    podria pagar para dejar de estarlo."""
    from django.urls import reverse
    from tests.factories import MembershipFactory

    monkeypatch.setattr(
        "apps.subscriptions.views.crear_sesion_de_pago",
        lambda **kw: "https://checkout.stripe.com/c/pay/fake",
    )

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    assert client.post(reverse("subscriptions:pagar")).status_code == 302


@pytest.mark.django_db
def test_el_retorno_no_concede_nada(client):
    """§5.2: cualquiera puede visitar la URL de exito sin haber pagado."""
    from django.urls import reverse
    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.get(reverse("subscriptions:retorno"))

    assert respuesta.status_code == 200
    hogar.refresh_from_db()
    assert hogar.subscription.status == "trialing"
    assert hogar.subscription.paid_at is None
```

Fíjate en que `falso_crear` de la primera prueba recibe posicionales y la segunda usa `**kw`: escribe la vista de forma que llame **con argumentos de palabra clave** y ajusta la primera prueba a `def falso_crear(*, household, locale, url_exito, url_cancelacion)`. Coherencia antes que comodidad.

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_suscripcion.py -q -k "pagar or retorno"`
Expected: FAIL con `NoReverseMatch: 'subscriptions' is not a registered namespace`.

- [ ] **Step 3: Escribe el gateway**

`apps/subscriptions/gateway.py`:

```python
"""El unico modulo del proyecto que importa `stripe`.

Que la frontera este en un solo archivo es lo que permite que la suite entera
corra sin claves y sin red: las pruebas sustituyen esta funcion, no la libreria.
"""

import stripe
from django.conf import settings


def crear_sesion_de_pago(*, household, locale, url_exito, url_cancelacion):
    """Una sesion de Stripe Checkout en modo `payment` (§5.1). Devuelve su URL.

    `client_reference_id` lleva el pk del hogar: es como el webhook sabra a
    quien acreditar el pago. NO se usa el correo del cliente, que el usuario
    puede cambiar dentro de la pasarela.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY
    sesion = stripe.checkout.Session.create(
        mode="payment",
        client_reference_id=str(household.pk),
        locale=locale,
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "cad",
                "unit_amount": settings.STRIPE_PRECIO_CENTAVOS,
                "product_data": {"name": "Wealthome"},
            },
        }],
        success_url=url_exito,
        cancel_url=url_cancelacion,
    )
    return sesion.url
```

- [ ] **Step 4: Escribe las vistas y las rutas**

`apps/subscriptions/views.py`:

```python
from django.shortcuts import redirect, render
from django.utils.translation import get_language

from apps.households.permissions import con_hogar, sin_guardia_de_suscripcion, solo_admin

from .gateway import crear_sesion_de_pago


@solo_admin
@sin_guardia_de_suscripcion
def pagar(request, hogar):
    """Manda a la pasarela. Es @solo_admin porque pagar es gobernar el hogar,
    no editar sus finanzas: los cuatro permisos del §6.2 son otra cosa."""
    if request.method != "POST":
        return redirect("subscriptions:estado")
    url = crear_sesion_de_pago(
        household=hogar,
        locale=get_language() or "en",
        url_exito=request.build_absolute_uri("/subscription/return/"),
        url_cancelacion=request.build_absolute_uri("/subscription/"),
    )
    return redirect(url)


@con_hogar
def retorno(request, hogar):
    """§5.2: NO concede nada. Cualquiera puede visitar esta URL sin pagar.
    Quien acredita el pago es el webhook, y solo el webhook."""
    return render(request, "subscriptions/retorno.html", {
        "suscripcion": getattr(hogar, "subscription", None),
    })
```

El orden de los decoradores importa: `@solo_admin` fuera y `@sin_guardia_de_suscripcion` dentro, para que la marca esté puesta sobre la función que `_decorador` envuelve.

`apps/subscriptions/urls.py`:

```python
from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("pay/", views.pagar, name="pagar"),
    path("return/", views.retorno, name="retorno"),
]
```

En `config/urls.py`, antes del `include` de accounts:

```python
    path("subscription/", include("apps.subscriptions.urls")),
```

`templates/subscriptions/retorno.html`:

```html
{% extends "base.html" %}{% load i18n %}
{% block title %}{% translate "Thank you" %} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <h1>{% translate "Thank you" %}</h1>
  <p>{% translate "We are confirming your payment. This page will not change until Stripe tells us it went through." %}</p>
  <p><a href="{% url 'accounts:inicio' %}">{% translate "Back to Wealthome" %}</a></p>
</section>
{% endblock %}
```

- [ ] **Step 5: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/test_suscripcion.py -q`
Expected: PASS. Ninguna llamada de red: `monkeypatch` sustituye `crear_sesion_de_pago` **en el módulo de vistas**, que es donde se resuelve el nombre.

- [ ] **Step 6: Commit**

```bash
git add apps/subscriptions/gateway.py apps/subscriptions/views.py \
        apps/subscriptions/urls.py config/urls.py \
        templates/subscriptions/ tests/test_suscripcion.py
git commit -m "Manda a Stripe Checkout en el idioma del usuario"
```

---

### Task 10: El webhook, la única fuente de verdad

Es un endpoint **público, sin autenticar y exento de CSRF**. Junto con `obtener_mes`, es el otro "único punto de entrada" del proyecto, y la lección del §4 del documento de estado se aplica entera: *las funciones que son el único punto de entrada merecen pruebas de entrada hostil, no solo del camino previsto*.

**Files:**
- Modify: `apps/subscriptions/gateway.py`, `services.py`, `views.py`, `urls.py`
- Create: `tests/test_webhook.py`

**Interfaces:**
- Consumes: `StripeEvent`, `Subscription`.
- Produces:
  - `gateway.leer_evento(cuerpo: bytes, firma: str) -> dict` — verifica la firma y devuelve el evento; lanza `ValueError` si no cuadra.
  - `services.procesar_evento(evento: dict) -> bool` — `True` si acreditó un pago, `False` si no había nada que hacer. Idempotente.

- [ ] **Step 1: Escribe las pruebas hostiles que fallan**

Crea `tests/test_webhook.py`:

```python
"""El webhook es publico y sin autenticar: se prueba hostil, no feliz."""

import json

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.subscriptions.models import StripeEvent, Subscription
from tests.factories import HouseholdFactory

URL = "/subscription/webhook/"


def _evento(hogar_pk, event_id="evt_1", tipo="checkout.session.completed"):
    return {
        "id": event_id,
        "type": tipo,
        "data": {"object": {
            "client_reference_id": str(hogar_pk),
            "id": "cs_test_1",
            "customer": "cus_1",
        }},
    }


@pytest.fixture
def sin_verificar_firma(monkeypatch):
    """Sustituye la verificacion: probamos el flujo, no la criptografia de Stripe."""
    def leer(cuerpo, firma):
        if firma != "buena":
            raise ValueError("firma invalida")
        return json.loads(cuerpo)

    monkeypatch.setattr("apps.subscriptions.views.leer_evento", leer)


@pytest.mark.django_db
def test_un_pago_acredita_la_suscripcion(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk))

    respuesta = client.post(URL, cuerpo, content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="buena")

    assert respuesta.status_code == 200
    hogar.refresh_from_db()
    assert hogar.subscription.status == Subscription.ACTIVE
    assert hogar.subscription.paid_at is not None


@pytest.mark.django_db
def test_sin_firma_no_escribe_nada(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk))

    respuesta = client.post(URL, cuerpo, content_type="application/json")

    assert respuesta.status_code == 400
    hogar.refresh_from_db()
    assert hogar.subscription.status == Subscription.TRIALING
    assert not StripeEvent.objects.exists()


@pytest.mark.django_db
def test_con_firma_ajena_no_escribe_nada(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk))

    respuesta = client.post(URL, cuerpo, content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="mala")

    assert respuesta.status_code == 400
    assert not StripeEvent.objects.exists()


@pytest.mark.django_db
def test_el_mismo_evento_tres_veces_deja_el_mismo_estado(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk))
    for _i in range(3):
        respuesta = client.post(URL, cuerpo, content_type="application/json",
                                HTTP_STRIPE_SIGNATURE="buena")
        assert respuesta.status_code == 200

    assert StripeEvent.objects.count() == 1
    hogar.refresh_from_db()
    assert hogar.subscription.status == Subscription.ACTIVE


@pytest.mark.django_db
def test_un_tipo_desconocido_se_registra_y_devuelve_200(client, sin_verificar_firma):
    """Devolver error por un evento que no nos interesa hace que Stripe lo
    reintente para siempre."""
    hogar = HouseholdFactory()
    cuerpo = json.dumps(_evento(hogar.pk, event_id="evt_2", tipo="invoice.paid"))

    respuesta = client.post(URL, cuerpo, content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="buena")

    assert respuesta.status_code == 200
    assert StripeEvent.objects.filter(type="invoice.paid").exists()
    hogar.refresh_from_db()
    assert hogar.subscription.status == Subscription.TRIALING


@pytest.mark.django_db
def test_un_hogar_que_no_existe_devuelve_200_y_no_revienta(client, sin_verificar_firma):
    cuerpo = json.dumps(_evento(999999))

    respuesta = client.post(URL, cuerpo, content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="buena")

    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_un_hogar_ya_activo_no_pierde_su_fecha_de_pago(client, sin_verificar_firma):
    hogar = HouseholdFactory()
    antes = timezone.now()
    hogar.subscription.status = Subscription.ACTIVE
    hogar.subscription.paid_at = antes
    hogar.subscription.save()

    cuerpo = json.dumps(_evento(hogar.pk, event_id="evt_3"))
    client.post(URL, cuerpo, content_type="application/json",
                HTTP_STRIPE_SIGNATURE="buena")

    hogar.refresh_from_db()
    assert hogar.subscription.paid_at == antes


@pytest.mark.django_db
def test_un_cuerpo_que_no_es_json_devuelve_400(client, sin_verificar_firma):
    respuesta = client.post(URL, b"esto no es json", content_type="application/json",
                            HTTP_STRIPE_SIGNATURE="buena")

    assert respuesta.status_code == 400
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_webhook.py -q`
Expected: FAIL, las ocho con 404 porque la ruta no existe.

- [ ] **Step 3: Añade la lectura del evento al gateway**

En `apps/subscriptions/gateway.py`:

```python
def leer_evento(cuerpo, firma):
    """Verifica la firma de Stripe y devuelve el evento como dict.

    Lanza ValueError si la firma falta, no cuadra, o el cuerpo no es JSON. El
    webhook traduce eso a un 400 sin escribir nada: un cuerpo que no podemos
    verificar no es de Stripe, venga de donde venga.
    """
    try:
        evento = stripe.Webhook.construct_event(
            payload=cuerpo, sig_header=firma,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except Exception as exc:            # SignatureVerificationError, ValueError
        raise ValueError(str(exc)) from exc
    return dict(evento)
```

- [ ] **Step 4: Escribe el procesamiento idempotente**

En `apps/subscriptions/services.py`:

```python
from django.db import transaction
from django.utils import timezone

from apps.households.models import Household

from .models import StripeEvent, Subscription

TIPO_QUE_ACREDITA = "checkout.session.completed"


@transaction.atomic
def procesar_evento(evento):
    """Aplica un evento de Stripe una sola vez. Devuelve True si acredito pago.

    La idempotencia del §5.2 vive en el unique de StripeEvent.event_id mas el
    select_for_update sobre esa fila: Stripe reintenta, y reintenta EN
    PARALELO, asi que comprobar processed_at sin bloquear dejaria pasar dos.
    """
    fila, creada = StripeEvent.objects.get_or_create(
        event_id=evento.get("id", ""),
        defaults={"type": evento.get("type", ""), "payload": evento},
    )
    fila = StripeEvent.objects.select_for_update().get(pk=fila.pk)
    if fila.processed_at is not None:
        return False

    acredito = False
    if fila.type == TIPO_QUE_ACREDITA:
        acredito = _acreditar(evento)

    fila.processed_at = timezone.now()
    fila.save(update_fields=["processed_at"])
    return acredito


def _acreditar(evento):
    objeto = evento.get("data", {}).get("object", {})
    referencia = objeto.get("client_reference_id") or ""
    if not referencia.isdigit():
        return False

    # Household NO es HouseholdScoped: .objects aqui es el manager normal.
    hogar = Household.objects.filter(pk=int(referencia)).first()
    if hogar is None:
        return False

    suscripcion = crear_suscripcion(hogar)
    if suscripcion.status == Subscription.ACTIVE:
        # Ya pagada: no se le pisa la fecha del pago de verdad.
        return False

    suscripcion.status = Subscription.ACTIVE
    suscripcion.paid_at = timezone.now()
    suscripcion.stripe_session_id = objeto.get("id", "") or ""
    suscripcion.stripe_customer_id = objeto.get("customer", "") or ""
    suscripcion.save(update_fields=[
        "status", "paid_at", "stripe_session_id", "stripe_customer_id",
    ])
    return True
```

- [ ] **Step 5: Escribe la vista del webhook**

En `apps/subscriptions/views.py`:

```python
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .gateway import crear_sesion_de_pago, leer_evento
from .services import procesar_evento


@csrf_exempt
@require_POST
def webhook(request):
    """La UNICA fuente de verdad del pago (§5.2).

    Publico y sin autenticar por definicion: quien llama es Stripe, no un
    usuario. Sin decoradores de hogar, porque no hay sesion. Su unica defensa
    es la firma, y por eso se prueba hostil.
    """
    firma = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        evento = leer_evento(request.body, firma)
    except ValueError:
        return HttpResponse(status=400)

    procesar_evento(evento)
    # 200 siempre que la firma cuadre, aunque no hubiera nada que hacer: un
    # error por un evento que no nos interesa hace que Stripe lo reintente
    # para siempre.
    return HttpResponse(status=200)
```

En `apps/subscriptions/urls.py`, añade:
```python
    path("webhook/", views.webhook, name="webhook"),
```

- [ ] **Step 6: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/test_webhook.py -q`
Expected: PASS las ocho.

- [ ] **Step 7: Documenta cómo se ejercita a mano**

Añade a `README.md`, en una sección nueva **Stripe**:

```markdown
## Stripe

La suite NUNCA llama a Stripe y corre sin claves. Para ejercitar el pago a mano
hacen falta, en `.env` y en modo de prueba:

    STRIPE_SECRET_KEY=sk_test_...
    STRIPE_PUBLISHABLE_KEY=pk_test_...
    STRIPE_WEBHOOK_SECRET=whsec_...

El `whsec_` lo entrega la CLI de Stripe al reenviar los webhooks al servidor
local, que es la unica forma de probarlos sin desplegar:

    stripe listen --forward-to localhost:8000/subscription/webhook/

Sin esa CLI corriendo, un pago de prueba se completa en la pasarela y la
suscripcion NO se acredita — y eso es correcto: el webhook es la unica fuente
de verdad (§5.2), y la URL de retorno no concede nada.
```

- [ ] **Step 8: Commit**

```bash
git add apps/subscriptions/ README.md tests/test_webhook.py
git commit -m "Acredita el pago solo por el webhook, y de forma idempotente"
```

---

### Task 11: La pantalla de la suscripción

Plana y fea a propósito, como las seis del Plan 2: la Tarea 16 la viste con el sistema de componentes.

**Files:**
- Modify: `apps/subscriptions/views.py`, `urls.py`
- Create: `templates/subscriptions/estado.html`
- Modify: `templates/households/ajustes.html`, `templates/403.html`
- Test: `tests/test_suscripcion.py`

**Interfaces:**
- Produces: ruta `subscriptions:estado`. La consumen `templates/403.html` y la navegación de la Tarea 14.

- [ ] **Step 1: Escribe la prueba que falla**

```python
@pytest.mark.django_db
def test_la_pantalla_de_suscripcion_dice_cuantos_dias_quedan(client):
    from django.urls import reverse
    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.get(reverse("subscriptions:estado"))

    assert respuesta.status_code == 200
    assert respuesta.context["suscripcion"].estado_visible == "trialing"


@pytest.mark.django_db
def test_un_403_por_suscripcion_ofrece_pagar(client):
    from django.urls import reverse
    from tests.factories import MembershipFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    respuesta = client.post(reverse("budget:ingreso_nuevo"), {})

    assert respuesta.status_code == 403
    assert reverse("subscriptions:estado") in respuesta.content.decode()
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_suscripcion.py -q -k "pantalla_de_suscripcion or ofrece_pagar"`
Expected: FAIL con `NoReverseMatch` para `subscriptions:estado`.

- [ ] **Step 3: Escribe la vista, la ruta y la plantilla**

En `apps/subscriptions/views.py`:

```python
@con_hogar
def estado(request, hogar):
    return render(request, "subscriptions/estado.html", {
        "suscripcion": getattr(hogar, "subscription", None),
        "precio": settings.STRIPE_PRECIO_CENTAVOS / 100,
    })
```

Con `from django.conf import settings` arriba. En `urls.py`:
```python
    path("", views.estado, name="estado"),
```

`templates/subscriptions/estado.html`:

```html
{% extends "base.html" %}{% load i18n money %}
{% block title %}{% translate "Subscription" %} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <h1>{% translate "Subscription" %}</h1>

  {% if suscripcion.estado_visible == "active" %}
    <p>{% translate "Wealthome is yours. Thank you." %}</p>
  {% elif suscripcion.estado_visible == "trialing" %}
    <p>{% blocktranslate count dias=suscripcion.dias_restantes %}One day left in your trial.{% plural %}{{ dias }} days left in your trial.{% endblocktranslate %}</p>
  {% else %}
    <p>{% translate "Your trial has ended. Your data is all here and always will be — you just cannot add anything new until you subscribe." %}</p>
  {% endif %}

  {% if suscripcion.estado_visible != "active" %}
    <form method="post" action="{% url 'subscriptions:pagar' %}">
      {% csrf_token %}
      <button class="btn btn--primary" type="submit">
        {% blocktranslate %}Subscribe once for ${{ precio }} CAD{% endblocktranslate %}
      </button>
    </form>
  {% endif %}
</section>
{% endblock %}
```

En `templates/households/ajustes.html`, añade el enlace:
```html
  <p><a href="{% url 'subscriptions:estado' %}">{% translate "Subscription" %}</a></p>
```

Y en `templates/403.html`, cambia el enlace que la Tarea 7 Step 6 dejó apuntando a `households:ajustes` para que apunte ya a `subscriptions:estado`.

- [ ] **Step 4: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/test_suscripcion.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/subscriptions/views.py apps/subscriptions/urls.py \
        templates/subscriptions/ templates/households/ajustes.html \
        templates/403.html tests/test_suscripcion.py
git commit -m "Anade la pantalla de la suscripcion y el 403 que ofrece pagar"
```

---

### Task 12: Catálogo bilingüe, tanda 2

El §9 del diseño del Plan 2 lo dice sin rodeos: atrapar las cadenas que faltan al final de un plan grande es un día perdido. Esta tarea existe por tanda de pantallas, no una vez al final.

**Files:**
- Modify: `locale/en/LC_MESSAGES/django.po`, `locale/fr/LC_MESSAGES/django.po`
- Test: `tests/test_catalogo_exhaustivo.py` (existe; solo se corre)

- [ ] **Step 1: Corre la prueba de catálogo y anota lo que falta**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalogo_exhaustivo.py -q`
Expected: FAIL, nombrando cada cadena sin traducir. Son las de la Tarea 6 (`subscription`, `trial ends at`, `paid at`, `Trial`, `Active`, `Stripe event`), la 7 (`Your trial has ended. Subscribe to keep adding to your budget.`, `See subscription`), la 9 (`Thank you`, `We are confirming your payment…`, `Back to Wealthome`) y la 11 (`Subscription`, `Wealthome is yours. Thank you.`, el plural de los días, el texto de la prueba terminada y el botón con el precio).

- [ ] **Step 2: Escribe las entradas en los dos `.po`**

Con `msgid` exacto. Para el plural de los días, en `locale/fr/LC_MESSAGES/django.po` hace falta la forma plural francesa:

```
msgid "One day left in your trial."
msgid_plural "%(dias)s days left in your trial."
msgstr[0] "Il vous reste un jour d'essai."
msgstr[1] "Il vous reste %(dias)s jours d'essai."
```

Comprueba que la cabecera del `.po` francés declare `Plural-Forms: nplurals=2; plural=(n > 1);`. Si no está, añádela: sin ella `msgfmt` no compila los plurales.

- [ ] **Step 3: Compila**

```bash
MSGFMT="C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py"
for L in en fr; do .venv/Scripts/python.exe "$MSGFMT" -o "locale/$L/LC_MESSAGES/django.mo" "locale/$L/LC_MESSAGES/django.po"; done
```

- [ ] **Step 4: Corre las dos mitades**

Run: `.venv/Scripts/python.exe -m pytest -q --ignore=tests/budget`
Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS. Es el cierre de la tanda 2.

- [ ] **Step 5: Verifica el pago a mano**

Con las claves de prueba en `.env` y `stripe listen` corriendo (ver README): regístrate, entra a `/subscription/`, paga con la tarjeta `4242 4242 4242 4242`, y comprueba que la pantalla pasa a "Wealthome is yours" **solo después** de que la CLI reenvíe el evento.

- [ ] **Step 6: Commit**

```bash
git add locale/
git commit -m "Traduce al ingles y al frances las cadenas de la suscripcion"
```

> **Punto de control 2. Se puede cobrar.** Un hogar nace con catorce días, expira solo, se queda en solo lectura sin perder un dato, paga por Stripe en su idioma, y el webhook lo acredita una sola vez aunque llegue tres veces. La aplicación sigue siendo fea.

---
## Tanda 3 · Componentes y navegación

Cinco tareas. `tokens.css` ya tiene los tres temas completos; lo que falta es la capa de componentes (`components.css` tiene 23 líneas, `modules.css` tiene 1) y un armazón de navegación que **no existe**: `base.html` es `<main class="shell">` y nada más.

Al terminar esta tanda, el adolescente del §6.2 tiene por fin un camino a registrar un gasto.

---

### Task 13: La capa de componentes y la paleta de gráficas

**La regla que no se negocia:** ningún componente lleva dentro un selector `[data-theme="…"]`. El patrón ya está establecido en `components.css` — `.card` y `.btn` declaran a la vez `border: var(--border-width) solid var(--border-color)` y `box-shadow: var(--shadow-raised)`, y el tema Accesible pone el borde a 3 px y `--shadow-inset: none`. Todo componente nuevo lo sigue.

**Files:**
- Modify: `static/css/components.css`, `static/css/tokens.css`
- Create: `tests/test_css.py`

- [ ] **Step 1: Escribe la guardia de la regla, que hoy pasa**

Crea `tests/test_css.py`:

```python
"""La guardia del §7.4: los componentes se escriben UNA vez.

El tema Accesible no es "Sereno con letra grande": sustituye las sombras por
bordes, y eso se hace cambiando variables en tokens.css. Un componente que
traiga su propio [data-theme] rompe esa promesa en cuanto alguien anada el
cuarto tema, y nadie lo notaria hasta entonces.
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_ningun_componente_contiene_un_selector_de_tema():
    for nombre in ("components.css", "modules.css", "base.css"):
        texto = (RAIZ / "static" / "css" / nombre).read_text(encoding="utf-8")
        assert "data-theme" not in texto, (
            f"{nombre} contiene un selector de tema. Los tres temas se "
            f"expresan cambiando variables en tokens.css, no duplicando "
            f"componentes."
        )


def test_los_tres_temas_definen_las_mismas_variables_de_grafica():
    texto = (RAIZ / "static" / "css" / "tokens.css").read_text(encoding="utf-8")
    for tema in ("nocturno", "accesible"):
        bloque = texto.split(f'[data-theme="{tema}"]')[1].split("}")[0]
        for i in range(1, 6):
            assert f"--chart-{i}" in bloque, (
                f"El tema {tema} no define --chart-{i}: una grafica con "
                f"colores que no cambian con el tema es ilegible en Nocturno "
                f"y pierde el contraste 14:1 en Accesible."
            )
```

- [ ] **Step 2: Corre y comprueba que la segunda falla**

Run: `.venv/Scripts/python.exe -m pytest tests/test_css.py -q`
Expected: la primera PASS, la segunda FAIL con `IndexError` o el assert de `--chart-1`.

- [ ] **Step 3: Añade la paleta categórica a los tres temas**

En `static/css/tokens.css`, dentro de `:root` (Sereno):

```css
  /* Paleta categorica de graficas. Cinco series: mas de cinco categorias en
     una grafica ya no se distinguen por color, se distinguen por etiqueta. */
  --chart-1: #3f8f6f;
  --chart-2: #4a7a9b;
  --chart-3: #a8894f;
  --chart-4: #8c6b8f;
  --chart-5: #6f7d8a;
  --chart-grid: #d2d8de;
```

Dentro de `[data-theme="nocturno"]`:

```css
  --chart-1: #5cc196;
  --chart-2: #6ba3c9;
  --chart-3: #d0ac6a;
  --chart-4: #b795bb;
  --chart-5: #93a0ad;
  --chart-grid: #333b45;
```

Dentro de `[data-theme="accesible"]` — aquí no se buscan colores bonitos sino **separación**, porque el contraste es la señal que queda cuando la sombra se pierde:

```css
  --chart-1: #0a5c3a;
  --chart-2: #123a63;
  --chart-3: #6b4306;
  --chart-4: #5a1a52;
  --chart-5: #333a41;
  --chart-grid: #14181d;
```

- [ ] **Step 4: Escribe la capa de componentes**

En `static/css/components.css`, tras `.btn--primary`, añade lo que las pantallas de este plan necesitan. Todo con variables, sin un solo literal de color:

```css
/* ---------- superficies ---------- */
.card--hundida {
  background: var(--surface);
  border-radius: var(--radius);
  border: var(--border-width) solid var(--border-color);
  box-shadow: var(--shadow-inset);
  padding: 20px;
}

/* ---------- botones ---------- */
.btn--bloque { width: 100%; }
.btn--sutil { color: var(--text-muted); box-shadow: none; }
.btn:active { box-shadow: var(--shadow-inset); }

/* ---------- campos ---------- */
.campo {
  display: block;
  width: 100%;
  min-height: var(--touch-target);
  padding: 0 14px;
  background: var(--surface);
  color: var(--text);
  border: var(--border-width) solid var(--border-color);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-inset);
  font-family: inherit;
  font-size: var(--font-size-base);
}
.campo--error { border-color: var(--danger); color: var(--danger); }
.campo__ayuda { color: var(--text-muted); font-size: 0.875em; }

/* ---------- tablas ---------- */
.tabla { width: 100%; border-collapse: collapse; }
.tabla th, .tabla td { padding: 10px 12px; text-align: left; }
.tabla th { color: var(--text-muted); font-weight: var(--font-weight-strong); }
.tabla td.numero, .tabla th.numero { text-align: right; font-variant-numeric: tabular-nums; }
.tabla__envoltura { overflow-x: auto; }

/* ---------- barra de progreso ---------- */
.progreso {
  height: 14px;
  border-radius: 999px;
  background: var(--surface);
  border: var(--border-width) solid var(--border-color);
  box-shadow: var(--shadow-inset);
  overflow: hidden;
}
.progreso__relleno { height: 100%; background: var(--accent); }

/* ---------- pildora de estado ---------- */
.pildora {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 999px;
  border: var(--border-width) solid var(--border-color);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 0.875em;
  font-weight: var(--font-weight-strong);
}
.pildora--bien { color: var(--accent-strong); }
.pildora--mal { color: var(--danger); }

/* ---------- tarjeta de cifra ---------- */
.cifra {
  background: var(--surface);
  border-radius: var(--radius);
  border: var(--border-width) solid var(--border-color);
  box-shadow: var(--shadow-raised);
  padding: 16px 18px;
}
.cifra__etiqueta { color: var(--text-muted); font-size: 0.875em; }
.cifra__valor {
  font-size: 1.6em;
  font-weight: var(--font-weight-strong);
  font-variant-numeric: tabular-nums;
}
.cifra__valor--mal { color: var(--danger); }
.cifras { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
```

- [ ] **Step 5: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/test_css.py -q`
Expected: PASS las dos.

- [ ] **Step 6: Míralo con los tres temas**

```bash
.venv/Scripts/python.exe manage.py runserver
```

Entra a `/budget/`, y en Preferencias cambia entre Sereno, Nocturno y Accesible. Comprueba a ojo que en Accesible **no hay sombras** y sí bordes gruesos, y que el texto es de 20 px. Si algún componente se ve igual en Accesible que en Sereno, es que lleva un valor literal donde debía llevar una variable.

- [ ] **Step 7: Commit**

```bash
git add static/css/components.css static/css/tokens.css tests/test_css.py
git commit -m "Escribe la capa de componentes y la paleta de graficas por tema"
```

---

### Task 14: El armazón de navegación

Hoy no hay ninguno. Lo que hace de menú es `templates/accounts/inicio.html`, una página de bienvenida con **dos enlaces**, y solo uno lleva al presupuesto. El miembro con solo `can_add_transactions` **no tiene ningún camino** a la acción que el propio diseño llama la más frecuente.

Un solo bloque de HTML, dos presentaciones (§7.1). `.shell` ya reserva `padding-bottom: 96px`.

**Files:**
- Create: `templates/_nav.html`
- Modify: `templates/base.html`, `static/css/modules.css`
- Create: `apps/core/context_processors.py` (existe; se le añade `navegacion`)
- Modify: `config/settings.py` (registrar el context processor si no lo está)

**Interfaces:**
- Produces: el context processor `apps.core.context_processors.navegacion`, que expone `nav_entradas` — una lista de dicts `{"nombre", "url", "etiqueta", "icono"}` filtrada por permiso y por estado de suscripción. La Tarea 15 la prueba y la 18 la amplía.

- [ ] **Step 1: Escribe el context processor**

En `apps/core/context_processors.py`:

```python
"""Lo que toda plantilla necesita saber.

`navegacion` es la unica fuente del menu. Que sea una sola lista y no HTML
repartido por las plantillas es lo que permite que tests/test_navegacion.py la
recorra entera y afirme, por perfil de permiso, que no falta ni sobra ninguna
pantalla. El Plan 2 enlazaba 1 de 6 porque el menu era prosa.
"""

from django.urls import reverse
from django.utils.translation import gettext as _


def _permiso(membresia, nombre):
    return membresia is not None and getattr(membresia, nombre, False)


def navegacion(request):
    from apps.households.permissions import get_membership, hogar_actual

    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"nav_entradas": [], "nav_puede_escribir": False}

    try:
        hogar = hogar_actual(request)
    except Exception:
        # Un usuario autenticado sin hogar (invitacion a medias): no hay menu
        # que ensenarle, y reventar aqui romperia hasta la pagina de login.
        return {"nav_entradas": [], "nav_puede_escribir": False}

    membresia = get_membership(request.user, hogar)
    puede_escribir = hogar.puede_escribir

    entradas = []
    if _permiso(membresia, "can_view_budget"):
        entradas.append({
            "nombre": "hogar", "url": reverse("budget:mes"),
            "etiqueta": _("Household"), "icono": "home",
        })
    if _permiso(membresia, "can_add_transactions") and puede_escribir:
        # El [+] del §7.1: la accion mas frecuente, siempre a un toque, y
        # dependiendo SOLO de can_add_transactions. Es el camino del
        # adolescente del §6.2, que hasta el Plan 3 no tenia ninguno.
        entradas.append({
            "nombre": "registrar", "url": reverse("budget:registrar"),
            "etiqueta": _("Add"), "icono": "mas",
        })
    if _permiso(membresia, "can_view_budget"):
        entradas.append({
            "nombre": "metas", "url": reverse("budget:metas"),
            "etiqueta": _("Goals"), "icono": "meta",
        })
    entradas.append({
        "nombre": "ajustes", "url": reverse("households:ajustes"),
        "etiqueta": _("Settings"), "icono": "ajustes",
    })
    return {"nav_entradas": entradas, "nav_puede_escribir": puede_escribir}
```

En `config/settings.py`, dentro de `TEMPLATES[0]["OPTIONS"]["context_processors"]`, comprueba que esté:
```python
                "apps.core.context_processors.navegacion",
```

- [ ] **Step 2: Escribe el menú**

`templates/_nav.html`:

```html
{% load i18n %}
{% if nav_entradas %}
<nav class="nav" aria-label="{% translate 'Main' %}">
  <ul class="nav__lista">
    {% for entrada in nav_entradas %}
      <li class="nav__item nav__item--{{ entrada.icono }}">
        <a class="nav__enlace" href="{{ entrada.url }}">{{ entrada.etiqueta }}</a>
      </li>
    {% endfor %}
  </ul>
  {% if not nav_puede_escribir %}
    <p class="nav__aviso">
      <a href="{% url 'subscriptions:estado' %}">{% translate "Your trial has ended" %}</a>
    </p>
  {% endif %}
</nav>
{% endif %}
```

El aviso sustituye al `[+]`, que el context processor ya no incluye para un hogar expirado: un `[+]` que da 403 al tocarlo sería correcto y grosero, y el §7 lo dice con esas palabras.

- [ ] **Step 3: Mete el armazón en `base.html`**

```html
{% load i18n static %}<!doctype html>
<html lang="{{ LANGUAGE_CODE }}" data-theme="{{ user.profile.theme|default:'sereno' }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Wealthome{% endblock %}</title>
  <link rel="stylesheet" href="{% static 'css/tokens.css' %}">
  <link rel="stylesheet" href="{% static 'css/base.css' %}">
  <link rel="stylesheet" href="{% static 'css/components.css' %}">
  <link rel="stylesheet" href="{% static 'css/modules.css' %}">
</head>
<body>
  {% include "_nav.html" %}
  <main class="shell">{% block content %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 4: Dale las dos presentaciones**

En `static/css/modules.css`:

```css
/* ---------- navegacion ----------
   Un solo bloque de HTML, dos presentaciones (§7.1). En movil, barra inferior
   fija con la accion mas frecuente en el centro; en escritorio, barra lateral.
   El mismo HTML, distinta hoja: nunca dos menus que puedan divergir. */

.nav__lista {
  display: flex;
  justify-content: space-around;
  align-items: center;
  margin: 0;
  padding: 0;
  list-style: none;
}
.nav__enlace {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--touch-target);
  padding: 0 10px;
  color: var(--text);
  text-decoration: none;
  font-weight: var(--font-weight-strong);
}
.nav__item--mas .nav__enlace {
  min-width: var(--touch-target);
  border-radius: 999px;
  background: var(--surface);
  border: var(--border-width) solid var(--border-color);
  box-shadow: var(--shadow-raised);
  color: var(--accent-strong);
}
.nav__aviso { margin: 0; padding: 6px 12px; text-align: center; font-size: 0.875em; }
.nav__aviso a { color: var(--danger); }

/* movil: barra inferior fija */
.nav {
  position: fixed;
  left: 0; right: 0; bottom: 0;
  z-index: 10;
  background: var(--bg);
  border-top: var(--border-width) solid var(--border-color);
  box-shadow: var(--shadow-raised);
}

/* escritorio: barra lateral */
@media (min-width: 900px) {
  .nav {
    position: fixed;
    top: 0; bottom: 0; left: 0; right: auto;
    width: 220px;
    border-top: 0;
    border-right: var(--border-width) solid var(--border-color);
    padding-top: 24px;
  }
  .nav__lista { flex-direction: column; align-items: stretch; }
  .nav__enlace { justify-content: flex-start; padding: 0 20px; }
  .shell { margin-left: 220px; padding-bottom: 24px; }
}
```

- [ ] **Step 5: Míralo en los dos tamaños y con los tres temas**

Arranca el servidor, estrecha la ventana por debajo de 900 px y comprueba que la barra pasa abajo con el `[+]` en el centro; ensánchala y comprueba que pasa a la izquierda. Repite en Accesible: la barra debe tener 56 px de alto en los botones.

- [ ] **Step 6: Commit**

```bash
git add templates/_nav.html templates/base.html static/css/modules.css \
        apps/core/context_processors.py config/settings.py
git commit -m "Construye el armazon de navegacion con el mas siempre a un toque"
```

---

### Task 15: La prueba de navegación por perfil

Esta es la tarea que convierte "el menú enlaza 1 de 6 pantallas" en una regresión permanente. Hoy las pruebas llegan por `reverse()`, que es **exactamente** por lo que nadie lo notó: `reverse()` no navega.

El mapa declarado es el corazón de la prueba: añadir una pantalla sin enlazarla la rompe.

**Files:**
- Create: `tests/test_navegacion.py`

**Interfaces:**
- Consumes: `nav_entradas` del context processor de la Tarea 14.

- [ ] **Step 1: Escribe la prueba**

Crea `tests/test_navegacion.py`:

```python
"""La navegacion como entregable con nombre propio.

El Plan 2 dejo un menu que enlazaba 1 de 6 pantallas y un miembro con solo
can_add_transactions sin ningun camino a registrar un gasto, y ninguna prueba
lo vio: todas llegan por reverse(), que no navega.

El mapa PERFILES es un dato, no prosa. Anadir una pantalla sin ponerla en el
menu rompe esta prueba, que es justo lo que se quiere.
"""

import pytest
from django.urls import reverse

from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

ADMIN = "admin"
SOLO_VER = "solo_ver"
ADOLESCENTE = "adolescente"

PERMISOS = {
    ADMIN: {"can_view_budget": True, "can_edit_budget": True,
            "can_add_transactions": True, "can_view_reports": True},
    SOLO_VER: {"can_view_budget": True, "can_edit_budget": False,
               "can_add_transactions": False, "can_view_reports": False},
    # El adolescente del §6.2: registra sus gastos y no ve la hipoteca.
    ADOLESCENTE: {"can_view_budget": False, "can_edit_budget": False,
                  "can_add_transactions": True, "can_view_reports": False},
}

# Lo que CADA perfil tiene que poder alcanzar desde el menu, por nombre de
# entrada. Ni una mas, ni una menos.
ESPERADO = {
    ADMIN: {"hogar", "registrar", "metas", "ajustes"},
    SOLO_VER: {"hogar", "metas", "ajustes"},
    ADOLESCENTE: {"registrar", "ajustes"},
}


def _sesion(client, perfil):
    hogar = HouseholdFactory()
    user = UserFactory()
    membresia = MembershipFactory(user=user, household=hogar, role="member")
    for campo, valor in PERMISOS[perfil].items():
        setattr(membresia, campo, valor)
    membresia.save()
    client.force_login(user)
    return hogar, user


@pytest.mark.django_db
@pytest.mark.parametrize("perfil", [ADMIN, SOLO_VER, ADOLESCENTE])
def test_el_menu_ensena_exactamente_lo_que_el_perfil_puede_abrir(client, perfil):
    _sesion(client, perfil)
    respuesta = client.get(reverse("households:ajustes"))
    nombres = {e["nombre"] for e in respuesta.context["nav_entradas"]}
    assert nombres == ESPERADO[perfil]


@pytest.mark.django_db
@pytest.mark.parametrize("perfil", [ADMIN, SOLO_VER, ADOLESCENTE])
def test_ningun_enlace_del_menu_devuelve_403(client, perfil):
    """Un 403 al hacer clic es correcto pero grosero (§7 del Plan 2)."""
    _sesion(client, perfil)
    respuesta = client.get(reverse("households:ajustes"))
    for entrada in respuesta.context["nav_entradas"]:
        seguimiento = client.get(entrada["url"])
        assert seguimiento.status_code == 200, (
            f"El perfil {perfil} ve en su menu {entrada['nombre']} "
            f"({entrada['url']}) y al seguirlo recibe {seguimiento.status_code}."
        )


@pytest.mark.django_db
def test_el_adolescente_llega_a_registrar_un_gasto_sin_teclear_la_url(client):
    """El criterio de aceptacion 5, escrito como prueba."""
    _sesion(client, ADOLESCENTE)
    respuesta = client.get(reverse("households:ajustes"))
    urls = [e["url"] for e in respuesta.context["nav_entradas"]]
    assert reverse("budget:registrar") in urls
    assert client.get(reverse("budget:registrar")).status_code == 200


@pytest.mark.django_db
def test_un_hogar_expirado_no_ensena_el_mas(client):
    from datetime import timedelta

    from django.utils import timezone

    hogar, _user = _sesion(client, ADMIN)
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    respuesta = client.get(reverse("households:ajustes"))
    nombres = {e["nombre"] for e in respuesta.context["nav_entradas"]}
    assert "registrar" not in nombres
    assert respuesta.context["nav_puede_escribir"] is False
```

- [ ] **Step 2: Corre la prueba**

Run: `.venv/Scripts/python.exe -m pytest tests/test_navegacion.py -q`
Expected: PASS. Si alguna falla, **el fallo está en el context processor de la Tarea 14, no en la prueba** — el mapa `ESPERADO` es la especificación.

- [ ] **Step 3: Commit**

```bash
git add tests/test_navegacion.py
git commit -m "Prueba que el menu ensena a cada perfil lo que puede abrir, y solo eso"
```

---

### Task 16: Las seis pantallas de hoy, sobre el sistema nuevo

Las seis del Plan 2 y la de suscripción de la Tarea 11 son formularios planos, feos a propósito. Ahora tienen dónde apoyarse.

Es una tarea de presentación: **no cambia ni una consulta ni una regla de negocio**. Si al terminar alguna prueba de vistas falla, es que se cambió algo que no tocaba.

**Files:**
- Modify: `templates/budget/configurar.html`, `mes.html`, `gasto.html`, `planificar.html`, `cerrar.html`, `metas.html`, `formulario.html`
- Modify: `templates/subscriptions/estado.html`, `templates/accounts/inicio.html`
- Modify: `static/css/modules.css`

- [ ] **Step 1: Corre las pruebas de vistas y anota el verde de partida**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q`
Expected: PASS. Este es el estado que **no** se puede romper.

- [ ] **Step 2: Aplica los componentes, plantilla por plantilla**

Reglas mecánicas, sin inventar:
- Toda `<table>` pasa a `<table class="tabla">` envuelta en `<div class="tabla__envoltura">`, y las celdas de importe llevan `class="numero"`.
- Todo `<input>`, `<select>` y `<textarea>` de un formulario lleva `class="campo"`. Como los formularios se pintan con `{{ form }}`, añade en su lugar `{{ form.as_div }}` y un bloque en `modules.css` que aplique el estilo por selector de elemento dentro de `.formulario`.
- Los cuatro totales y el sobrante pasan a `<div class="cifras">` con una `.cifra` cada uno.
- El estado del mes pasa a `<span class="pildora">`.

Para `templates/budget/formulario.html`, que es el que comparten todas las altas:

```html
{% extends "base.html" %}{% load i18n %}
{% block title %}{{ titulo }} · Wealthome{% endblock %}
{% block content %}
<section class="card formulario">
  <h1>{{ titulo }}</h1>
  <form method="post">
    {% csrf_token %}
    {{ form.as_div }}
    <button class="btn btn--primary" type="submit">{% translate "Save" %}</button>
  </form>
</section>
{% endblock %}
```

Y en `modules.css`:

```css
/* Los formularios se pintan con {{ form.as_div }}: el estilo se aplica por
   elemento dentro de .formulario, para no tener que tocar cada widget en
   Python ni repetir class="campo" en cada plantilla. */
.formulario input[type="text"],
.formulario input[type="email"],
.formulario input[type="number"],
.formulario input[type="date"],
.formulario input[type="password"],
.formulario select,
.formulario textarea {
  display: block;
  width: 100%;
  min-height: var(--touch-target);
  padding: 0 14px;
  background: var(--surface);
  color: var(--text);
  border: var(--border-width) solid var(--border-color);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-inset);
  font-family: inherit;
  font-size: var(--font-size-base);
}
.formulario textarea { min-height: calc(var(--touch-target) * 2); padding: 12px 14px; }
.formulario div { margin-bottom: 16px; }
.formulario label { display: block; margin-bottom: 6px; color: var(--text-muted); }
.formulario .errorlist { margin: 6px 0 0; padding-left: 18px; color: var(--danger); }
```

- [ ] **Step 3: Reemplaza la página de bienvenida**

`templates/accounts/inicio.html` era el menú de facto. Ahora que hay uno de verdad, deja de serlo:

```html
{% extends "base.html" %}{% load i18n %}
{% block title %}Wealthome{% endblock %}
{% block content %}
<section class="card">
  <h1>{% translate "Welcome" %}</h1>
  <p>{% translate "Your budget lives in the menu. Start with this month." %}</p>
  <p><a class="btn btn--primary" href="{% url 'budget:mes' %}">{% translate "This month" %}</a></p>
</section>
{% endblock %}
```

- [ ] **Step 4: Corre las pruebas de vistas**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py tests/test_navegacion.py -q`
Expected: PASS. Si alguna prueba busca una cadena en el HTML y ahora no la encuentra, mira **si la cadena sigue estando**: si sí, ajusta la prueba; si no, la reintrodujiste mal.

- [ ] **Step 5: Míralo entero, en los tres temas y en los dos tamaños**

Recorre las siete pantallas con el servidor arrancado. Esta es la primera vez que la aplicación se ve como se pensó, y el ojo caza lo que ninguna prueba caza.

- [ ] **Step 6: Commit**

```bash
git add templates/ static/css/modules.css
git commit -m "Viste las siete pantallas existentes con el sistema de componentes"
```

---

### Task 17: Catálogo bilingüe, tanda 3

**Files:**
- Modify: `locale/en/LC_MESSAGES/django.po`, `locale/fr/LC_MESSAGES/django.po`

- [ ] **Step 1: Corre la prueba de catálogo**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalogo_exhaustivo.py -q`
Expected: FAIL nombrando las cadenas nuevas: `Household`, `Add`, `Goals`, `Settings`, `Main`, `Your trial has ended`, `Your budget lives in the menu. Start with this month.`, `This month`, `Save`.

- [ ] **Step 2: Escribe y compila**

Añade las entradas a los dos `.po` y compila:

```bash
MSGFMT="C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py"
for L in en fr; do .venv/Scripts/python.exe "$MSGFMT" -o "locale/$L/LC_MESSAGES/django.mo" "locale/$L/LC_MESSAGES/django.po"; done
```

- [ ] **Step 3: Corre las dos mitades**

Run: `.venv/Scripts/python.exe -m pytest -q --ignore=tests/budget`
Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS. Cierre de tanda.

- [ ] **Step 4: Commit**

```bash
git add locale/
git commit -m "Traduce las cadenas de la navegacion y del armazon"
```

> **Punto de control 3. Usable y navegable.** La aplicación tiene menú, se ve como se diseñó en los tres temas, y **el adolescente del §6.2 llega a registrar un gasto sin teclear una URL** — con prueba que lo vigila para siempre. Si hay que parar, aquí se para con algo que se puede enseñar.

---
## Tanda 4 · El eje Hogar/Personal y las pantallas nuevas

Seis tareas. Aquí salen a la luz las dos cifras que el motor calcula, guarda, y no enseña en ninguna parte: **la varianza** y **la mesada**.

---

### Task 18: El eje Hogar/Personal en las rutas, y `views.py` se parte

`/household/…` y `/personal/…`: la misma vista con el ámbito como parámetro, filtrando por el campo `scope` que los modelos ya tienen. **El ámbito va en la ruta y no en un parámetro de consulta** porque el service worker de la tanda 6 cachea por URL: con el ámbito fuera de la ruta, la caché serviría la página del hogar a quien pidió la personal.

`apps/budget/views.py` tiene 221 líneas y esta tanda le añadiría cuatro pantallas. Se parte aquí, que es la primera tarea que lo haría crecer de verdad, y se parte **por responsabilidad**.

**Files:**
- Create: `apps/budget/views_setup.py`, `views_month.py`, `views_goals.py`, `views_overview.py`
- Delete: `apps/budget/views.py` (su contenido se reparte)
- Modify: `apps/budget/urls.py`
- Modify: `apps/core/context_processors.py`
- Test: `tests/budget/test_views.py`, `tests/test_navegacion.py`

**Interfaces:**
- Produces:
  - `apps.budget.scopes.AMBITOS = ("household", "personal")` y `apps.budget.scopes.acotar(queryset, ambito, membresia)` — el único sitio donde el ámbito se traduce en filtro.
  - Rutas con prefijo: `budget:mes` pasa a aceptar `<ambito>`; los nombres de ruta **no cambian**, así que ningún `reverse()` existente se rompe salvo por el argumento nuevo.

- [ ] **Step 1: Escribe las pruebas que fallan**

En `tests/budget/test_views.py`:

```python
@pytest.mark.django_db
def test_el_ambito_va_en_la_ruta(client):
    from django.urls import reverse

    hogar, user = _admin_logueado(client)
    assert reverse("budget:mes", args=["household"]).startswith("/budget/household/")
    assert reverse("budget:mes", args=["personal"]).startswith("/budget/personal/")


@pytest.mark.django_db
def test_un_ambito_inventado_da_404(client):
    _admin_logueado(client)
    assert client.get("/budget/marciano/month/").status_code == 404


@pytest.mark.django_db
def test_personal_solo_ensena_lo_del_miembro(client):
    """§2.4: Hogar y Personal son la misma vista con un filtro, no dos vistas."""
    from datetime import date
    from decimal import Decimal
    from django.urls import reverse

    from tests.factories import MembershipFactory
    from tests.factories_budget import (
        BudgetMonthFactory, CategoryFactory, TransactionFactory,
    )

    hogar, user = _admin_logueado(client)
    mia = hogar.memberships.get(user=user)
    otra = MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    cat = CategoryFactory(household=hogar)

    TransactionFactory(household=hogar, budget_month=mes, category=cat,
                       member=mia, scope="personal", amount=Decimal("10.00"),
                       date=date(2026, 3, 2))
    TransactionFactory(household=hogar, budget_month=mes, category=cat,
                       member=otra, scope="personal", amount=Decimal("99.00"),
                       date=date(2026, 3, 3))

    respuesta = client.get(reverse("budget:mes", args=["personal"]) + "2026/3/")
    importes = [t.amount for t in respuesta.context["transacciones"]]
    assert Decimal("10.00") in importes
    assert Decimal("99.00") not in importes
```

Añade arriba del archivo el ayudante, si no existe ya:

```python
def _admin_logueado(client):
    from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)
    return hogar, user
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q -k "ambito or personal_solo"`
Expected: FAIL con `NoReverseMatch` — `budget:mes` no acepta argumentos hoy.

- [ ] **Step 3: Escribe el módulo del ámbito**

Crea `apps/budget/scopes.py`:

```python
"""El eje Hogar / Personal (§2.4 y §7.1).

"Household y Personal son la misma vista con un parametro de filtro, no vistas
duplicadas": este modulo es ese parametro, y el unico sitio donde se traduce en
un filtro. Que este solo aqui es lo que impide que la mitad de las pantallas
filtren y la otra mitad se olvide.

El ambito viaja en la RUTA y no en un parametro de consulta ni en la sesion,
porque el service worker cachea por URL: con el ambito fuera de la ruta, la
cache servira la pagina del hogar a quien pidio la personal.
"""

from django.http import Http404
from django.utils.translation import gettext_lazy as _

HOGAR = "household"
PERSONAL = "personal"
AMBITOS = (HOGAR, PERSONAL)

ETIQUETAS = {HOGAR: _("Household"), PERSONAL: _("Personal")}


def validar(ambito):
    """Se llega a estas URLs escribiendolas. Un ambito inventado es un 404."""
    if ambito not in AMBITOS:
        raise Http404(_("That view does not exist."))
    return ambito


def acotar(queryset, ambito, membresia):
    """Filtra al ambito pedido.

    En Personal se filtra por `scope` Y por miembro: "lo personal" de otro no
    es lo personal de este. En Hogar no se filtra por miembro, porque un gasto
    del hogar es de todos.
    """
    if ambito == PERSONAL:
        return queryset.filter(scope=PERSONAL, member=membresia)
    return queryset.filter(scope=HOGAR)
```

`acotar` asume que el modelo tiene `scope` y `member`; `Transaction` los tiene. Para `BudgetLine`, que tiene `scope` y `owner`, escribe una segunda función:

```python
def acotar_lineas(queryset, ambito, membresia):
    """Igual, para BudgetLine, que llama `owner` a lo que Transaction llama
    `member`. Dos funciones y no un parametro con el nombre del campo: es mas
    corto de leer y no hay una tercera forma esperando a aparecer."""
    if ambito == PERSONAL:
        return queryset.filter(scope=PERSONAL, owner=membresia)
    return queryset.filter(scope=HOGAR)
```

- [ ] **Step 4: Parte `views.py` en cuatro**

Mueve las funciones **sin cambiarlas** salvo por la firma del ámbito:

- `apps/budget/views_setup.py` ← `configurar`, `_crear`, `ingreso_nuevo`, `gasto_nuevo`, `categoria_nueva`, `reparto_nuevo`
- `apps/budget/views_month.py` ← `mes`, `registrar`, `planificar`, `cerrar`, y las constantes `ANIO_MINIMO`/`ANIO_MAXIMO`
- `apps/budget/views_goals.py` ← `metas`, `meta_nueva`, `aportar`
- `apps/budget/views_overview.py` ← vacío por ahora; lo llenan las Tareas 19 y 20

Las vistas con ámbito reciben `ambito` como tercer argumento, después del hogar que pone el decorador:

```python
@requiere_permiso("can_view_budget")
def mes(request, hogar, ambito, anio=None, numero=None):
    ambito = validar(ambito)
    membresia = membresia_actual(request)
    ...
    if not es_proyeccion:
        contexto["lineas"] = acotar_lineas(
            resultado.lineas.select_related("category"), ambito, membresia
        )
        contexto["transacciones"] = acotar(
            resultado.transacciones.select_related("category"), ambito, membresia
        )
    contexto["ambito"] = ambito
```

Borra `apps/budget/views.py`.

- [ ] **Step 5: Reescribe las rutas**

`apps/budget/urls.py`:

```python
from django.urls import path

from . import views_goals, views_month, views_overview, views_setup

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
    path("goals/new/", views_goals.meta_nueva, name="meta_nueva"),
    path("goals/contribute/", views_goals.aportar, name="aportar"),
]

# Y estas si: son las cuatro del §7.1, en sus dos ambitos.
urlpatterns += [
    path("<str:ambito>/", views_overview.overview, name="overview"),
    path("<str:ambito>/month/", views_month.mes, name="mes"),
    path("<str:ambito>/month/<int:anio>/<int:numero>/", views_month.mes, name="mes"),
    path("<str:ambito>/plan/", views_month.planificar, name="planificar"),
    path("<str:ambito>/close/", views_month.cerrar, name="cerrar"),
    path("<str:ambito>/balance/", views_overview.balance, name="balance"),
    path("<str:ambito>/goals/", views_goals.metas, name="metas"),
]
```

`views_overview.overview` y `.balance` aún no existen: escríbelas como funciones mínimas que rendericen una plantilla vacía, para que las rutas resuelvan. Las Tareas 19 y 20 las llenan.

- [ ] **Step 6: Actualiza el menú y las pruebas**

En `apps/core/context_processors.py`, los `reverse` pasan a llevar el ámbito, y aparece Personal como entrada propia:

```python
    if _permiso(membresia, "can_view_budget"):
        entradas.append({
            "nombre": "hogar", "url": reverse("budget:overview", args=["household"]),
            "etiqueta": _("Household"), "icono": "home",
        })
        entradas.append({
            "nombre": "personal", "url": reverse("budget:overview", args=["personal"]),
            "etiqueta": _("Personal"), "icono": "persona",
        })
```

y `metas` pasa a `reverse("budget:metas", args=["household"])`.

En `tests/test_navegacion.py`, añade `"personal"` a `ESPERADO[ADMIN]` y a `ESPERADO[SOLO_VER]`. **El mapa es la especificación: se cambia a propósito, en este commit.**

Y busca en todo el repositorio los `reverse("budget:…")` que ahora necesitan ámbito:

```bash
grep -rn "budget:mes\|budget:metas\|budget:planificar\|budget:cerrar" --include=*.py --include=*.html .
```

- [ ] **Step 7: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py tests/test_navegacion.py tests/test_aislamiento.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/budget/ apps/core/context_processors.py tests/
git commit -m "Pone el ambito Hogar/Personal en la ruta y parte views.py en cuatro"
```

---

### Task 19: El Overview, con Chart.js

Presupuesto contra gasto real, movimientos recientes, y dos gráficas: planeado contra real por categoría, y la evolución del balance sobre los últimos `MonthlyClose`.

**Chart.js lee sus colores de las variables CSS.** Un literal en JavaScript se vuelve ilegible en Nocturno y pierde el contraste 14:1 en Accesible.

**Files:**
- Create: `static/vendor/chart.umd.min.js`, `static/js/graficas.js`
- Modify: `apps/budget/views_overview.py`, `templates/base.html`
- Create: `templates/budget/overview.html`
- Modify: `tests/test_presupuesto_consultas.py`
- Test: `tests/budget/test_views.py`

**Interfaces:**
- Produces: el contexto del Overview lleva `series_categorias` y `series_balance`, ambos **ya serializados a JSON** con `json_script`, para que la plantilla no arme JavaScript a mano.

- [ ] **Step 1: Vendoriza Chart.js**

```bash
mkdir -p static/vendor
curl -L -o static/vendor/chart.umd.min.js https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js
```

Comprueba que el archivo pesa del orden de 200 KB y que empieza con un comentario de licencia de Chart.js. Anota la versión exacta en `README.md`, en una sección **Dependencias del navegador**, junto con esta frase: *no hay build step; estos archivos se actualizan a mano y a propósito*.

- [ ] **Step 2: Escribe las pruebas que fallan**

```python
@pytest.mark.django_db
def test_el_overview_da_las_series_ya_serializadas(client):
    from datetime import date
    from decimal import Decimal
    import json
    from django.urls import reverse

    from tests.factories_budget import (
        BudgetMonthFactory, BudgetLineFactory, CategoryFactory, TransactionFactory,
    )

    hogar, user = _admin_logueado(client)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    cat = CategoryFactory(household=hogar, slug="groceries")
    BudgetLineFactory(household=hogar, budget_month=mes, category=cat,
                      kind="expense", planned_amount=Decimal("400.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=cat,
                       amount=Decimal("350.00"), date=date(2026, 3, 4))

    respuesta = client.get(reverse("budget:overview", args=["household"]))

    assert respuesta.status_code == 200
    series = respuesta.context["series_categorias"]
    assert series["etiquetas"] == ["groceries"] or "groceries" in str(series)
    assert json.dumps(series)   # serializable: nada de Decimal suelto


@pytest.mark.django_db
def test_las_graficas_no_llevan_colores_literales():
    """Un color en el JS es ilegible en Nocturno y pierde el 14:1 en Accesible."""
    import re
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "static" / "js" / "graficas.js").read_text(
        encoding="utf-8"
    )
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", js)
    assert not re.search(r"\brgba?\s*\(", js)
    assert "getPropertyValue" in js
```

La segunda prueba va en `tests/test_css.py`, no en las de vistas: es una guardia de estilo, no de comportamiento.

- [ ] **Step 3: Escribe la vista**

En `apps/budget/views_overview.py`:

```python
"""Overview y Balance: las dos pantallas que ENSENAN lo que el motor calcula.

Hasta el Plan 3, los cuatro totales del cierre y varianza_por_categoria se
calculaban, se guardaban y no aparecian en ninguna pantalla.
"""

from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services
from .models import MonthlyClose, Transaction
from .scopes import acotar, acotar_lineas, validar

MESES_EN_LA_GRAFICA = 6
MOVIMIENTOS_RECIENTES = 8


@requiere_permiso("can_view_budget")
def overview(request, hogar, ambito):
    ambito = validar(ambito)
    membresia = membresia_actual(request)
    hoy = timezone.localdate()
    resultado = services.obtener_mes(hogar, hoy.year, hoy.month)
    es_proyeccion = isinstance(resultado, services.ProyeccionDeMes)

    planeado, real = {}, {}
    recientes = []
    if not es_proyeccion:
        for linea in acotar_lineas(
            resultado.lineas.select_related("category"), ambito, membresia
        ):
            clave = linea.category.etiqueta
            planeado[clave] = planeado.get(clave, Decimal("0.00")) + linea.planned_amount

        movimientos = acotar(
            resultado.transacciones.select_related("category"), ambito, membresia
        )
        for tx in movimientos:
            clave = tx.category.etiqueta
            real[clave] = real.get(clave, Decimal("0.00")) + tx.amount
        recientes = list(movimientos.order_by("-date", "-pk")[:MOVIMIENTOS_RECIENTES])
    else:
        for linea in resultado.lineas:
            planeado[linea.nombre] = planeado.get(linea.nombre, Decimal("0.00")) + linea.importe

    etiquetas = sorted(set(planeado) | set(real))
    series_categorias = {
        "etiquetas": etiquetas,
        "planeado": [str(planeado.get(e, Decimal("0.00"))) for e in etiquetas],
        "real": [str(real.get(e, Decimal("0.00"))) for e in etiquetas],
    }

    cierres = list(
        MonthlyClose.objects.for_household(hogar)
        .select_related("budget_month")
        .order_by("-budget_month__year", "-budget_month__month")[:MESES_EN_LA_GRAFICA]
    )[::-1]
    series_balance = {
        "etiquetas": [f"{c.budget_month.year}-{c.budget_month.month:02d}" for c in cierres],
        "balance": [str(c.balance) for c in cierres],
    }

    return render(request, "budget/overview.html", {
        "ambito": ambito, "resultado": resultado, "es_proyeccion": es_proyeccion,
        "recientes": recientes,
        "series_categorias": series_categorias,
        "series_balance": series_balance,
    })
```

Los importes viajan como `str` y no como `Decimal`: `json_script` no sabe serializar `Decimal`, y convertirlos a `float` a mitad de camino sería introducir coma flotante en una aplicación financiera por comodidad de una gráfica.

- [ ] **Step 4: Escribe el JavaScript de las gráficas**

`static/js/graficas.js`:

```javascript
/* Las graficas del Overview.
 *
 * Ni un color literal: se leen de las variables CSS en tiempo de ejecucion, o
 * la grafica se vuelve ilegible en Nocturno y pierde el contraste 14:1 que el
 * tema Accesible promete. El tema puede cambiar sin recargar, asi que tambien
 * se vuelven a leer cuando cambia data-theme.
 */
(function () {
  "use strict";

  function color(nombre) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(nombre)
      .trim();
  }

  function datos(id) {
    var nodo = document.getElementById(id);
    return nodo ? JSON.parse(nodo.textContent) : null;
  }

  function numeros(lista) {
    return (lista || []).map(function (v) { return parseFloat(v); });
  }

  var graficas = [];

  function dibujar() {
    graficas.forEach(function (g) { g.destroy(); });
    graficas = [];

    var porCategoria = datos("series-categorias");
    var lienzoA = document.getElementById("grafica-categorias");
    if (porCategoria && lienzoA && porCategoria.etiquetas.length) {
      graficas.push(new Chart(lienzoA, {
        type: "bar",
        data: {
          labels: porCategoria.etiquetas,
          datasets: [
            { label: lienzoA.dataset.etiquetaPlaneado,
              data: numeros(porCategoria.planeado),
              backgroundColor: color("--chart-2") },
            { label: lienzoA.dataset.etiquetaReal,
              data: numeros(porCategoria.real),
              backgroundColor: color("--chart-1") }
          ]
        },
        options: {
          responsive: true,
          scales: { y: { grid: { color: color("--chart-grid") } },
                    x: { grid: { color: color("--chart-grid") } } }
        }
      }));
    }

    var balance = datos("series-balance");
    var lienzoB = document.getElementById("grafica-balance");
    if (balance && lienzoB && balance.etiquetas.length) {
      graficas.push(new Chart(lienzoB, {
        type: "line",
        data: {
          labels: balance.etiquetas,
          datasets: [{ label: lienzoB.dataset.etiquetaBalance,
                       data: numeros(balance.balance),
                       borderColor: color("--chart-1"),
                       backgroundColor: color("--chart-1") }]
        },
        options: {
          responsive: true,
          scales: { y: { grid: { color: color("--chart-grid") } },
                    x: { grid: { color: color("--chart-grid") } } }
        }
      }));
    }
  }

  document.addEventListener("DOMContentLoaded", dibujar);

  new MutationObserver(dibujar).observe(document.documentElement, {
    attributes: true, attributeFilter: ["data-theme"]
  });
})();
```

Las etiquetas de las series salen de atributos `data-` del propio `<canvas>`, para que estén traducidas por Django y no haya ni una cadena visible dentro del JavaScript.

- [ ] **Step 5: Escribe la plantilla**

`templates/budget/overview.html`:

```html
{% extends "base.html" %}{% load i18n money static %}
{% block title %}{% translate "Overview" %} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <h1>{% translate "Overview" %}</h1>

  <div class="cifras">
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Income" %}</div>
      <div class="cifra__valor">{{ resultado.total_ingresos|money:hogar.currency }}</div>
    </div>
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Fixed expenses" %}</div>
      <div class="cifra__valor">{{ resultado.total_egresos|money:hogar.currency }}</div>
    </div>
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Left over" %}</div>
      <div class="cifra__valor">{{ resultado.sobrante|money:hogar.currency }}</div>
    </div>
  </div>
</section>

<section class="card">
  <h2>{% translate "Planned against real" %}</h2>
  <canvas id="grafica-categorias"
          data-etiqueta-planeado="{% translate 'Planned' %}"
          data-etiqueta-real="{% translate 'Real' %}"></canvas>
</section>

<section class="card">
  <h2>{% translate "How the balance moved" %}</h2>
  <canvas id="grafica-balance"
          data-etiqueta-balance="{% translate 'Balance' %}"></canvas>
</section>

<section class="card">
  <h2>{% translate "Recent activity" %}</h2>
  <div class="tabla__envoltura">
    <table class="tabla">
      {% for tx in recientes %}
        <tr><td>{{ tx.date }}</td><td>{{ tx.category.etiqueta }}</td>
            <td class="numero">{{ tx.amount|money:hogar.currency }}</td></tr>
      {% empty %}
        <tr><td>{% translate "Nothing recorded yet." %}</td></tr>
      {% endfor %}
    </table>
  </div>
</section>

{{ series_categorias|json_script:"series-categorias" }}
{{ series_balance|json_script:"series-balance" }}
<script src="{% static 'vendor/chart.umd.min.js' %}"></script>
<script src="{% static 'js/graficas.js' %}"></script>
{% endblock %}
```

`json_script` escapa el contenido correctamente: nunca armes el JSON dentro de una etiqueta `<script>` a mano.

- [ ] **Step 6: Pon el Overview en el presupuesto de consultas**

En `tests/test_presupuesto_consultas.py`, añade una prueba igual a la del mes pero contra `reverse("budget:overview", args=["household"])`, con su propio tope `CONSULTAS_OVERVIEW`. Corre, mira el número, fíjalo, y comprueba subiendo el `range(50)` a `range(100)` que no se mueve.

- [ ] **Step 7: Corre las pruebas y míralo**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py tests/test_css.py tests/test_presupuesto_consultas.py -q`
Expected: PASS.

Arranca el servidor y mira el Overview en los tres temas. **Cambia el tema con la gráfica ya dibujada**: debe redibujarse con los colores nuevos, que es lo que hace el `MutationObserver`.

- [ ] **Step 8: Commit**

```bash
git add static/vendor/chart.umd.min.js static/js/graficas.js \
        apps/budget/views_overview.py templates/budget/overview.html \
        README.md tests/
git commit -m "Anade el Overview con sus dos graficas, que leen los colores del tema"
```

---

### Task 20: Balance, donde la varianza deja de ser invisible

Los cuatro totales y `varianza_por_categoria` se calculan y se guardan desde el Plan 2, y **no aparecen en ninguna pantalla**. Esta es esa pantalla.

La varianza se guarda como `{str: str}` y **no se migra** (§1 del spec): la pantalla reconstruye los `Decimal` al leer.

**Files:**
- Modify: `apps/budget/views_overview.py`
- Create: `templates/budget/balance.html`
- Test: `tests/budget/test_views.py`

**Interfaces:**
- Produces: el contexto de Balance lleva `cierres`, una lista de dicts `{"cierre", "mes", "varianza"}` donde `varianza` es una lista de `{"categoria", "importe"}` con `importe` ya como `Decimal`.

- [ ] **Step 1: Escribe la prueba que falla**

```python
@pytest.mark.django_db
def test_balance_ensena_la_varianza_por_categoria(client):
    from decimal import Decimal
    from django.urls import reverse

    from apps.budget.models import MonthlyClose
    from tests.factories_budget import BudgetMonthFactory, CategoryFactory

    hogar, user = _admin_logueado(client)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=2, status="closed")
    cat = CategoryFactory(household=hogar, slug="groceries")
    MonthlyClose.unscoped.create(
        household=hogar, budget_month=mes,
        ingresos_presupuestados=Decimal("3000.00"), ingresos_reales=Decimal("3000.00"),
        egresos_presupuestados=Decimal("400.00"), egresos_reales=Decimal("475.00"),
        varianza_por_categoria={str(cat.pk): "-75.00"},
        balance=Decimal("2525.00"), arrastre=Decimal("2525.00"),
    )

    respuesta = client.get(reverse("budget:balance", args=["household"]))

    assert respuesta.status_code == 200
    fila = respuesta.context["cierres"][0]
    assert fila["cierre"].balance == Decimal("2525.00")
    varianzas = {v["categoria"].pk: v["importe"] for v in fila["varianza"]}
    assert varianzas[cat.pk] == Decimal("-75.00")
```

- [ ] **Step 2: Corre y comprueba que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q -k balance_ensena`
Expected: FAIL — `balance` es la función mínima de la Tarea 18 y no pone `cierres` en el contexto.

- [ ] **Step 3: Escribe la vista**

En `apps/budget/views_overview.py`:

```python
@requiere_permiso("can_view_budget")
def balance(request, hogar, ambito):
    """El balance actual y los cierres anteriores, con SU VARIANZA.

    varianza_por_categoria se guarda como {str: str} (§1 del spec del Plan 3:
    no se migra). Aqui se reconstruyen los Decimal al leer, que es mas barato
    que una migracion de datos sobre un JSON.
    """
    from .models import Category

    ambito = validar(ambito)
    cierres_orm = list(
        MonthlyClose.objects.for_household(hogar)
        .select_related("budget_month")
        .order_by("-budget_month__year", "-budget_month__month")
    )

    ids = set()
    for cierre in cierres_orm:
        ids.update(int(k) for k in cierre.varianza_por_categoria)
    categorias = {
        c.pk: c for c in Category.objects.for_household(hogar).filter(pk__in=ids)
    }

    filas = []
    for cierre in cierres_orm:
        varianza = [
            {"categoria": categorias[int(pk)], "importe": Decimal(importe)}
            for pk, importe in cierre.varianza_por_categoria.items()
            if int(pk) in categorias
        ]
        # De la peor desviacion a la mejor: lo que se fue de madre primero.
        varianza.sort(key=lambda v: v["importe"])
        filas.append({"cierre": cierre, "mes": cierre.budget_month, "varianza": varianza})

    return render(request, "budget/balance.html", {"ambito": ambito, "cierres": filas})
```

Las categorías se cargan **de una vez** para todos los cierres: una consulta por cierre sería un N+1 nuevo recién estrenado.

- [ ] **Step 4: Escribe la plantilla**

`templates/budget/balance.html`:

```html
{% extends "base.html" %}{% load i18n money %}
{% block title %}{% translate "Balance" %} · Wealthome{% endblock %}
{% block content %}
<h1>{% translate "Balance" %}</h1>

{% for fila in cierres %}
<section class="card">
  <h2>{{ fila.mes }} <span class="pildora">{% translate "Closed" %}</span></h2>

  <div class="cifras">
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Income, planned" %}</div>
      <div class="cifra__valor">{{ fila.cierre.ingresos_presupuestados|money:hogar.currency }}</div>
    </div>
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Income, real" %}</div>
      <div class="cifra__valor">{{ fila.cierre.ingresos_reales|money:hogar.currency }}</div>
    </div>
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Spending, planned" %}</div>
      <div class="cifra__valor">{{ fila.cierre.egresos_presupuestados|money:hogar.currency }}</div>
    </div>
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Spending, real" %}</div>
      <div class="cifra__valor">{{ fila.cierre.egresos_reales|money:hogar.currency }}</div>
    </div>
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Balance" %}</div>
      <div class="cifra__valor">{{ fila.cierre.balance|money:hogar.currency }}</div>
    </div>
  </div>

  <h3>{% translate "Where it went off plan" %}</h3>
  <div class="tabla__envoltura">
    <table class="tabla">
      <tr><th>{% translate "Category" %}</th><th class="numero">{% translate "Difference" %}</th></tr>
      {% for v in fila.varianza %}
        <tr>
          <td>{{ v.categoria.etiqueta }}</td>
          <td class="numero {% if v.importe < 0 %}cifra__valor--mal{% endif %}">
            {{ v.importe|money:hogar.currency }}
          </td>
        </tr>
      {% empty %}
        <tr><td colspan="2">{% translate "Everything landed on plan." %}</td></tr>
      {% endfor %}
    </table>
  </div>
</section>
{% empty %}
<section class="card">
  <p>{% translate "No month has been closed yet. Your first balance appears when you close a month." %}</p>
</section>
{% endfor %}
{% endblock %}
```

- [ ] **Step 5: Añade Balance al menú**

En `apps/core/context_processors.py`, tras la entrada de Personal:

```python
        entradas.append({
            "nombre": "balance", "url": reverse("budget:balance", args=["household"]),
            "etiqueta": _("Balance"), "icono": "balance",
        })
```

Y añade `"balance"` a `ESPERADO[ADMIN]` y `ESPERADO[SOLO_VER]` en `tests/test_navegacion.py`.

- [ ] **Step 6: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py tests/test_navegacion.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/budget/views_overview.py templates/budget/balance.html \
        apps/core/context_processors.py tests/
git commit -m "Ensena por fin la varianza por categoria en la pantalla de Balance"
```

---

### Task 21: Metas con progreso visual

**Files:**
- Modify: `apps/budget/views_goals.py`, `templates/budget/metas.html`
- Test: `tests/budget/test_views.py`

- [ ] **Step 1: Escribe la prueba que falla**

La prueba existente `test_las_metas_muestran_su_dato_derivado` solo afirma que el nombre aparece en el HTML, no el dato derivado que su nombre promete. Sustitúyela:

```python
@pytest.mark.django_db
def test_las_metas_muestran_su_dato_derivado_de_verdad(client):
    from datetime import date
    from decimal import Decimal
    from django.urls import reverse

    from tests.factories_budget import GoalContributionFactory, GoalFactory

    hogar, user = _admin_logueado(client)
    meta = GoalFactory(
        household=hogar, name="Viaje", contribution_mode="by_monthly_amount",
        target_amount=Decimal("1200.00"), monthly_amount=Decimal("100.00"),
    )
    GoalContributionFactory(household=hogar, goal=meta, amount=Decimal("300.00"),
                            date=date(2026, 3, 1))

    respuesta = client.get(reverse("budget:metas", args=["household"]))

    fila = respuesta.context["filas"][0]
    assert fila["acumulado"] == Decimal("300.00")
    assert fila["porcentaje"] == 25          # 300 de 1200
    assert fila["fecha"] is not None         # el dato derivado, no el nombre


@pytest.mark.django_db
def test_un_aporte_de_la_cascada_no_dice_que_lo_hizo_nadie(client):
    """member es anulable desde la Tarea 2: la plantilla tiene que tolerarlo."""
    from datetime import date
    from decimal import Decimal
    from django.urls import reverse

    from apps.budget.models import GoalContribution
    from tests.factories_budget import GoalFactory

    hogar, user = _admin_logueado(client)
    meta = GoalFactory(household=hogar)
    GoalContribution.unscoped.create(
        household=hogar, goal=meta, amount=Decimal("50.00"),
        date=date(2026, 3, 1), member=None, origen="cascade",
    )

    respuesta = client.get(reverse("budget:metas", args=["household"]))
    assert respuesta.status_code == 200
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q -k "dato_derivado_de_verdad or cascada_no_dice"`
Expected: FAIL, la primera con `KeyError: 'porcentaje'`.

- [ ] **Step 3: Calcula el porcentaje en la vista**

En `apps/budget/views_goals.py`:

```python
@requiere_permiso("can_view_budget")
def metas(request, hogar, ambito):
    ambito = validar(ambito)
    membresia = membresia_actual(request)

    consulta = Goal.objects.for_household(hogar)
    if ambito == PERSONAL:
        consulta = consulta.filter(scope=PERSONAL, owner=membresia)
    else:
        consulta = consulta.filter(scope=HOGAR)

    filas = []
    for meta in consulta.prefetch_related("contributions"):
        acumulado = meta.acumulado()
        aporte, fecha = meta.derivar(acumulado=acumulado)
        # Acotado a 100: una meta sobrepasada no debe pintar una barra que se
        # sale de su caja, y "119%" es un dato, no un error.
        bruto = (acumulado / meta.target_amount * 100) if meta.target_amount else 0
        filas.append({
            "meta": meta, "aporte": aporte, "fecha": fecha,
            "acumulado": acumulado,
            "porcentaje": int(bruto),
            "porcentaje_barra": min(100, int(bruto)),
        })
    return render(request, "budget/metas.html", {"ambito": ambito, "filas": filas})
```

`prefetch_related("contributions")` porque `acumulado()` agrega sobre esa relación: sin él, una consulta por meta.

- [ ] **Step 4: Escribe la plantilla**

`templates/budget/metas.html`:

```html
{% extends "base.html" %}{% load i18n money %}
{% block title %}{% translate "Goals" %} · Wealthome{% endblock %}
{% block content %}
<h1>{% translate "Goals" %}</h1>

{% for fila in filas %}
<section class="card">
  <h2>{{ fila.meta.name }}</h2>

  <div class="progreso">
    <div class="progreso__relleno" style="width: {{ fila.porcentaje_barra }}%"></div>
  </div>
  <p>
    {% blocktranslate with hecho=fila.acumulado|money:hogar.currency objetivo=fila.meta.target_amount|money:hogar.currency pct=fila.porcentaje %}{{ hecho }} of {{ objetivo }} — {{ pct }}%{% endblocktranslate %}
  </p>

  {% if fila.meta.contribution_mode == "by_target_date" %}
    <p>{% blocktranslate with importe=fila.aporte|money:hogar.currency %}Put in {{ importe }} a month to get there on time.{% endblocktranslate %}</p>
  {% else %}
    <p>{% blocktranslate with cuando=fila.fecha %}At this rate you get there in {{ cuando }}.{% endblocktranslate %}</p>
  {% endif %}

  <h3>{% translate "Contributions" %}</h3>
  <div class="tabla__envoltura">
    <table class="tabla">
      {% for aporte in fila.meta.contributions.all %}
        <tr>
          <td>{{ aporte.date }}</td>
          <td>
            {% if aporte.member %}{{ aporte.member.user }}
            {% else %}{% translate "The household" %}{% endif %}
          </td>
          <td class="numero">{{ aporte.amount|money:hogar.currency }}</td>
        </tr>
      {% endfor %}
    </table>
  </div>
</section>
{% empty %}
<section class="card"><p>{% translate "No goals yet." %}</p></section>
{% endfor %}

<p><a class="btn btn--primary" href="{% url 'budget:meta_nueva' %}">{% translate "New goal" %}</a></p>
{% endblock %}
```

`{% if aporte.member %}… {% else %}The household{% endif %}` es la consecuencia visible de la Tarea 2: un ahorro del hogar ya no lleva el nombre de nadie, y aquí lo dice con todas sus letras en vez de dejar un hueco.

- [ ] **Step 5: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/budget/views_goals.py templates/budget/metas.html tests/
git commit -m "Ensena el progreso de cada meta y de donde salio cada aporte"
```

---

### Task 22: Personal › Presupuesto, donde la mesada deja de ser invisible

`AllowanceLedger` está construido y probado, y en toda la aplicación aparece **una vez**: como una línea de texto en la previsualización de `planificar.html`. No hay pantalla donde un miembro vea cuánta mesada tiene, cuánto le queda, ni en qué se le fue.

El agravante es el §4.5.3: un mes flojo no retira mesada ya gastada, sino que escribe un `Ajuste` negativo **en el mes siguiente**. A un miembro le llega un mes con menos mesada por una decisión del cierre anterior, y hoy no existe dónde enterarse. El libro mayor se diseñó *"para que «¿por qué tengo $145 este mes?» siempre tenga respuesta"*. Esta es la pantalla donde se pregunta.

**Files:**
- Modify: `apps/budget/views_month.py`
- Create: `templates/budget/mesada.html`
- Modify: `apps/budget/urls.py`, `apps/core/context_processors.py`
- Test: `tests/budget/test_views.py`

**Interfaces:**
- Produces: ruta `budget:mesada` (solo en ámbito personal).

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
@pytest.mark.django_db
def test_la_mesada_ensena_el_libro_mayor_entero(client):
    from decimal import Decimal
    from django.urls import reverse

    from apps.budget.models import AllowanceLedger
    from tests.factories_budget import BudgetMonthFactory

    hogar, user = _admin_logueado(client)
    mia = hogar.memberships.get(user=user)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    AllowanceLedger.unscoped.create(
        household=hogar, member=mia, budget_month=mes,
        carried_in=Decimal("45.00"), granted=Decimal("100.00"),
        adjustment=Decimal("-40.00"), spent=Decimal("60.00"),
    )

    respuesta = client.get(reverse("budget:mesada"))

    assert respuesta.status_code == 200
    libro = respuesta.context["libro"]
    assert libro.carried_in == Decimal("45.00")
    assert libro.adjustment == Decimal("-40.00")
    assert libro.saldo() == Decimal("45.00")     # 45 + 100 - 40 - 60


@pytest.mark.django_db
def test_la_mesada_explica_de_donde_sale_el_ajuste(client):
    """§4.5.3: el ajuste viene del cierre del mes anterior, y hay que decirlo."""
    from decimal import Decimal
    from django.urls import reverse

    from apps.budget.models import AllowanceLedger
    from tests.factories_budget import BudgetMonthFactory

    hogar, user = _admin_logueado(client)
    mia = hogar.memberships.get(user=user)
    BudgetMonthFactory(household=hogar, year=2026, month=2, status="closed")
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    AllowanceLedger.unscoped.create(
        household=hogar, member=mia, budget_month=mes,
        granted=Decimal("100.00"), adjustment=Decimal("-40.00"),
    )

    respuesta = client.get(reverse("budget:mesada"))

    assert respuesta.context["hay_ajuste"] is True
    assert respuesta.context["mes_del_ajuste"] is not None
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q -k mesada`
Expected: FAIL con `NoReverseMatch: 'mesada'`.

- [ ] **Step 3: Escribe la vista**

En `apps/budget/views_month.py`:

```python
@requiere_permiso("can_view_budget")
def mesada(request, hogar):
    """Personal › Presupuesto: el libro mayor de la mesada (§7.2).

    Hasta el Plan 3, AllowanceLedger aparecia UNA vez en toda la aplicacion, y
    era una linea de texto en una previsualizacion. Aqui se ensena entero, y
    sobre todo se explica el ajuste: el §4.5.3 descuenta el faltante de un mes
    flojo en la mesada del mes SIGUIENTE, y sin esta pantalla un miembro recibe
    menos dinero por una decision que no puede ver.
    """
    from .models import AllowanceLedger, Transaction

    membresia = membresia_actual(request)
    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)

    libro = None
    gastos = []
    if not isinstance(mes_actual, services.ProyeccionDeMes):
        libro = (
            AllowanceLedger.objects.for_household(hogar)
            .filter(member=membresia, budget_month=mes_actual)
            .first()
        )
        gastos = list(
            Transaction.objects.for_household(hogar)
            .filter(member=membresia, budget_month=mes_actual, scope="personal")
            .select_related("category")
            .order_by("-date", "-pk")
        )

    hay_ajuste = bool(libro and libro.adjustment)
    mes_del_ajuste = services._mes_anterior(mes_actual) if hay_ajuste else None

    return render(request, "budget/mesada.html", {
        "ambito": "personal", "libro": libro, "gastos": gastos,
        "mes": mes_actual, "hay_ajuste": hay_ajuste,
        "mes_del_ajuste": mes_del_ajuste,
    })
```

`services._mes_anterior` es privada por convención pero está ahí y hace exactamente esto; si prefieres no llamar a una privada desde una vista, quítale el guion bajo en `services.py` y actualiza sus tres usos internos. Escoge lo segundo: una vista llamando a `_algo` es una deuda pequeña que se paga en un minuto.

- [ ] **Step 4: Escribe la plantilla**

`templates/budget/mesada.html`:

```html
{% extends "base.html" %}{% load i18n money %}
{% block title %}{% translate "My allowance" %} · Wealthome{% endblock %}
{% block content %}
<h1>{% translate "My allowance" %}</h1>

{% if libro %}
<section class="card">
  <div class="cifras">
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Left to spend" %}</div>
      <div class="cifra__valor">{{ libro.saldo|money:hogar.currency }}</div>
    </div>
  </div>

  <h2>{% translate "How that number is made" %}</h2>
  <div class="tabla__envoltura">
    <table class="tabla">
      <tr><td>{% translate "Carried in from last month" %}</td>
          <td class="numero">{{ libro.carried_in|money:hogar.currency }}</td></tr>
      <tr><td>{% translate "Granted this month" %}</td>
          <td class="numero">{{ libro.granted|money:hogar.currency }}</td></tr>
      <tr><td>{% translate "Adjustment" %}</td>
          <td class="numero {% if libro.adjustment < 0 %}cifra__valor--mal{% endif %}">
            {{ libro.adjustment|money:hogar.currency }}</td></tr>
      <tr><td>{% translate "Spent" %}</td>
          <td class="numero">{{ libro.spent|money:hogar.currency }}</td></tr>
    </table>
  </div>

  {% if hay_ajuste %}
    <p class="campo__ayuda">
      {% blocktranslate with cuando=mes_del_ajuste %}{{ cuando }} closed below what was planned. Nothing you had already spent was taken back — the shortfall came out of this month instead.{% endblocktranslate %}
    </p>
  {% endif %}
</section>

<section class="card">
  <h2>{% translate "Where it went" %}</h2>
  <div class="tabla__envoltura">
    <table class="tabla">
      {% for gasto in gastos %}
        <tr><td>{{ gasto.date }}</td><td>{{ gasto.category.etiqueta }}</td>
            <td class="numero">{{ gasto.amount|money:hogar.currency }}</td></tr>
      {% empty %}
        <tr><td>{% translate "Nothing spent yet this month." %}</td></tr>
      {% endfor %}
    </table>
  </div>
</section>
{% else %}
<section class="card">
  <p>{% translate "You have no allowance this month yet. It appears once the month is planned." %}</p>
</section>
{% endif %}
{% endblock %}
```

Ese `blocktranslate` del ajuste es el corazón de la pantalla: dice **qué pasó, cuándo, y que no se le quitó nada de lo ya gastado**, que es la promesa del §4.5.3.

- [ ] **Step 5: Ruta y menú**

En `apps/budget/urls.py`, en el bloque sin ámbito:
```python
    path("personal/allowance/", views_month.mesada, name="mesada"),
```

Colócala **antes** de las rutas con `<str:ambito>` o `personal` se comería el patrón genérico.

En `apps/core/context_processors.py`, añade la entrada `mesada` bajo `can_view_budget`, y añádela a `ESPERADO[ADMIN]` y `ESPERADO[SOLO_VER]` en `tests/test_navegacion.py`.

- [ ] **Step 6: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py tests/test_navegacion.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/budget/views_month.py apps/budget/urls.py \
        templates/budget/mesada.html apps/core/context_processors.py tests/
git commit -m "Ensena la mesada y explica de donde sale el ajuste del mes anterior"
```

---

### Task 23: Catálogo bilingüe, tanda 4

Es la tanda con más texto nuevo del plan: cuatro pantallas, sus cifras y los `blocktranslate` con variables.

**Files:**
- Modify: `locale/en/LC_MESSAGES/django.po`, `locale/fr/LC_MESSAGES/django.po`

- [ ] **Step 1: Corre la prueba de catálogo**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalogo_exhaustivo.py -q`
Expected: FAIL con la lista larga.

- [ ] **Step 2: Escribe las entradas, con cuidado en los `blocktranslate`**

Un `blocktranslate` con variables produce un `msgid` que **incluye los marcadores**, por ejemplo:

```
msgid "%(hecho)s of %(objetivo)s — %(pct)s%%"
msgstr "%(hecho)s sur %(objetivo)s — %(pct)s %%"
```

Los nombres de variable **no se traducen** y el `%` literal se escribe `%%`. Si un `msgstr` los pierde o los renombra, `msgfmt` compila igual y la página revienta en tiempo de ejecución con un `KeyError` — es el error más caro de esta tanda.

- [ ] **Step 3: Compila y comprueba el francés a ojo**

```bash
MSGFMT="C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py"
for L in en fr; do .venv/Scripts/python.exe "$MSGFMT" -o "locale/$L/LC_MESSAGES/django.mo" "locale/$L/LC_MESSAGES/django.po"; done
```

Arranca el servidor, cambia el idioma a francés en Preferencias, y **recorre las cuatro pantallas nuevas**. Comprueba que los importes salen como `2 847,50 $` (criterio de aceptación 13) y que ningún texto sale con un `%(algo)s` crudo.

- [ ] **Step 4: Corre las dos mitades**

Run: `.venv/Scripts/python.exe -m pytest -q --ignore=tests/budget`
Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add locale/
git commit -m "Traduce el Overview, el Balance, las metas y la mesada"
```

> **Punto de control 4. El §7.2 cumplido.** Los cuatro módulos existen en sus dos ámbitos, la varianza se ve, la mesada se ve y se explica, y las gráficas son legibles en los tres temas.

---
## Tanda 5 · Los asistentes y htmx

Cinco tareas. Aquí se cumple por fin el §4.5.6, que el Plan 2 dejó incumplido a sabiendas: su `planificar` es una sola pantalla, y el criterio de aceptación 3 —*"una pareja planifica el mes en tres pasos"*— se dio por bueno sobre una pantalla que no tiene tres pasos.

---

### Task 24: htmx y Alpine vendorizados, en los cuatro sitios del spec

**htmx en cuatro sitios y en ninguno más:** registrar un gasto sin salir del Overview (Steps 4-6), aportar a una meta (Step 7), los filtros del Overview (Step 8), y los pasos de los asistentes (Tarea 26). La navegación entre módulos son cargas de página completas: con htmx entre módulos, el service worker de la tanda 6 no vería las páginas que debe cachear y el botón "atrás" dejaría de decir la verdad.

**Files:**
- Create: `static/vendor/htmx.min.js`, `static/vendor/alpine.min.js`
- Create: `templates/budget/_fragmentos/gasto_form.html`, `recientes.html`, `aporte_form.html`, `aportes.html`
- Modify: `templates/base.html`, `templates/budget/overview.html`, `templates/budget/metas.html`
- Modify: `apps/budget/views_month.py`, `views_goals.py`, `views_overview.py`
- Create: `tests/budget/test_htmx.py`

**Interfaces:**
- Produces: `views_month.registrar` devuelve **un fragmento** cuando la petición trae la cabecera `HX-Request`, y la página entera si no. La Tarea 26 usa el mismo patrón.

- [ ] **Step 1: Vendoriza htmx y Alpine**

```bash
curl -L -o static/vendor/htmx.min.js https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js
curl -L -o static/vendor/alpine.min.js https://cdn.jsdelivr.net/npm/alpinejs@3.14.8/dist/cdn.min.js
```

Anota las dos versiones en la sección **Dependencias del navegador** del README, junto a Chart.js.

- [ ] **Step 2: Escribe las pruebas que fallan**

Crea `tests/budget/test_htmx.py`:

```python
"""Los fragmentos de htmx se prueban como fragmentos.

No hace falta un navegador: htmx es una peticion HTTP normal con una cabecera.
Lo que hay que verificar es que la vista devuelva el trozo y no la pagina
entera, y que el trozo siga estando acotado al hogar.
"""

import pytest
from django.urls import reverse

from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


def _admin_logueado(client):
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)
    return hogar, user


@pytest.mark.django_db
def test_registrar_por_htmx_devuelve_un_fragmento_y_no_la_pagina(client):
    _admin_logueado(client)

    entera = client.get(reverse("budget:registrar"))
    trozo = client.get(reverse("budget:registrar"), HTTP_HX_REQUEST="true")

    assert b"<!doctype html>" in entera.content.lower()
    assert b"<!doctype html>" not in trozo.content.lower()
    assert b"<form" in trozo.content


@pytest.mark.django_db
def test_un_gasto_guardado_por_htmx_devuelve_los_movimientos_al_dia(client):
    from decimal import Decimal

    from apps.budget.seeds import sembrar
    from tests.factories_budget import CategoryFactory

    hogar, _user = _admin_logueado(client)
    sembrar(hogar)
    categoria = CategoryFactory(household=hogar, slug="cafe")

    respuesta = client.post(
        reverse("budget:registrar"),
        {"amount": "12.50", "date": "2026-03-04", "category": categoria.pk,
         "scope": "household", "payment_method": "card", "comercio": ""},
        HTTP_HX_REQUEST="true",
    )

    assert respuesta.status_code == 200
    assert b"12" in respuesta.content
    assert b"<!doctype html>" not in respuesta.content.lower()


@pytest.mark.django_db
def test_un_hogar_expirado_no_puede_registrar_ni_por_htmx(client):
    """La guardia del §2.2 es por METODO: las vistas de htmx nacen cubiertas."""
    from datetime import timedelta

    from django.utils import timezone

    hogar, _user = _admin_logueado(client)
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    respuesta = client.post(reverse("budget:registrar"), {}, HTTP_HX_REQUEST="true")
    assert respuesta.status_code == 403
```

La tercera prueba es la que demuestra que la decisión del §2.2 valió la pena: **no se escribió ni una línea nueva de guardia para esta vista**.

- [ ] **Step 3: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_htmx.py -q`
Expected: FAIL — hoy `registrar` devuelve siempre la página entera.

- [ ] **Step 4: Haz que `registrar` responda a htmx**

En `apps/budget/views_month.py`, dentro de `registrar`, sustituye los dos `return`:

```python
    es_htmx = request.headers.get("HX-Request") == "true"

    if request.method == "POST" and form.is_valid():
        ...
        else:
            if es_htmx:
                # Devuelve los movimientos al dia, no un redirect: htmx los
                # intercambia en su sitio y el usuario no pierde la pantalla.
                return render(request, "budget/_fragmentos/recientes.html", {
                    "recientes": _recientes(hogar, membresia_actual(request)),
                })
            return redirect("budget:registrar")

    plantilla = "budget/_fragmentos/gasto_form.html" if es_htmx else "budget/gasto.html"
    return render(request, plantilla, {"form": form})
```

Y añade el ayudante, junto a las constantes del módulo:

```python
MOVIMIENTOS_RECIENTES = 8


def _recientes(hogar, membresia):
    """Los ultimos movimientos del hogar, para el intercambio de htmx."""
    from .models import Transaction

    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    if isinstance(mes_actual, services.ProyeccionDeMes):
        return []
    return list(
        Transaction.objects.for_household(hogar)
        .filter(budget_month=mes_actual)
        .select_related("category")
        .order_by("-date", "-pk")[:MOVIMIENTOS_RECIENTES]
    )
```

- [ ] **Step 5: Escribe los dos fragmentos**

`templates/budget/_fragmentos/gasto_form.html`:

```html
{% load i18n %}
<form class="formulario" hx-post="{% url 'budget:registrar' %}"
      hx-target="#recientes" hx-swap="outerHTML">
  {% csrf_token %}
  {{ form.as_div }}
  <button class="btn btn--primary" type="submit">{% translate "Record it" %}</button>
</form>
```

`templates/budget/_fragmentos/recientes.html`:

```html
{% load i18n money %}
<div id="recientes" class="tabla__envoltura">
  <table class="tabla">
    {% for tx in recientes %}
      <tr><td>{{ tx.date }}</td><td>{{ tx.category.etiqueta }}</td>
          <td class="numero">{{ tx.amount|money:hogar.currency }}</td></tr>
    {% empty %}
      <tr><td>{% translate "Nothing recorded yet." %}</td></tr>
    {% endfor %}
  </table>
</div>
```

El `id="recientes"` va **dentro** del fragmento porque `hx-swap="outerHTML"` reemplaza el nodo entero: si el id viviera solo en la página, el segundo envío no encontraría dónde intercambiar.

- [ ] **Step 6: Enchúfalo al Overview y a `base.html`**

En `templates/base.html`, antes de `</body>`:

```html
  <script src="{% static 'vendor/htmx.min.js' %}"></script>
  <script defer src="{% static 'vendor/alpine.min.js' %}"></script>
```

Alpine lleva `defer` porque así lo exige su propia documentación; htmx no.

En `templates/budget/overview.html`, sustituye la sección de movimientos recientes por el fragmento y añade el formulario:

```html
<section class="card">
  <h2>{% translate "Record a spend" %}</h2>
  <div hx-get="{% url 'budget:registrar' %}" hx-trigger="load"></div>
</section>

<section class="card">
  <h2>{% translate "Recent activity" %}</h2>
  {% include "budget/_fragmentos/recientes.html" %}
</section>
```

- [ ] **Step 7: El tercer sitio — aportar a una meta**

Mismo patrón, para no inventar un segundo. En `apps/budget/views_goals.py`, dentro de `aportar`:

```python
    es_htmx = request.headers.get("HX-Request") == "true"

    if request.method == "POST" and form.is_valid():
        ...
        else:
            if es_htmx:
                return render(request, "budget/_fragmentos/aportes.html", {
                    "meta": aporte.goal, "aportes": aporte.goal.contributions.all(),
                })
            return redirect("budget:metas", ambito="household")

    plantilla = "budget/_fragmentos/aporte_form.html" if es_htmx else "budget/formulario.html"
    return render(request, plantilla, {"form": form, "titulo": _("Add to a goal")})
```

`templates/budget/_fragmentos/aportes.html`:

```html
{% load i18n money %}
<div id="aportes-{{ meta.pk }}" class="tabla__envoltura">
  <table class="tabla">
    {% for aporte in aportes %}
      <tr>
        <td>{{ aporte.date }}</td>
        <td>{% if aporte.member %}{{ aporte.member.user }}{% else %}{% translate "The household" %}{% endif %}</td>
        <td class="numero">{{ aporte.amount|money:hogar.currency }}</td>
      </tr>
    {% endfor %}
  </table>
</div>
```

`templates/budget/_fragmentos/aporte_form.html`:

```html
{% load i18n %}
<form class="formulario" hx-post="{% url 'budget:aportar' %}"
      hx-target="closest .card" hx-swap="beforeend">
  {% csrf_token %}
  {{ form.as_div }}
  <button class="btn btn--primary" type="submit">{% translate "Add it" %}</button>
</form>
```

Y en `templates/budget/metas.html`, sustituye la tabla de aportes de cada meta por
`{% include "budget/_fragmentos/aportes.html" with meta=fila.meta aportes=fila.meta.contributions.all %}`.

- [ ] **Step 8: El cuarto sitio — los filtros del Overview**

El §7.2 pide filtros en el Overview. Son dos: el mes y el tipo de movimiento. En `apps/budget/views_overview.py`, dentro de `overview`, tras resolver el ámbito:

```python
    # Los filtros del §7.2. Se leen de la query string y NO forman parte de la
    # ruta: el ambito si define que pagina es esta —y por eso va en la ruta,
    # que es lo que el service worker cachea—, pero un filtro es una vista de
    # la misma pagina. Cachear cada combinacion de filtros seria llenar el
    # disco del navegador de variantes de lo mismo.
    filtro_kind = request.GET.get("kind") or ""
    if filtro_kind in ("income", "expense"):
        recientes = [tx for tx in recientes if tx.category.kind == filtro_kind]
    contexto["filtro_kind"] = filtro_kind
```

Y en `templates/budget/overview.html`, en la sección de movimientos recientes:

```html
  <form class="filtros" hx-get="{% url 'budget:overview' ambito %}"
        hx-target="#recientes" hx-swap="outerHTML"
        hx-select="#recientes" hx-trigger="change">
    <select class="campo" name="kind">
      <option value="">{% translate "Everything" %}</option>
      <option value="income" {% if filtro_kind == "income" %}selected{% endif %}>{% translate "Money in" %}</option>
      <option value="expense" {% if filtro_kind == "expense" %}selected{% endif %}>{% translate "Money out" %}</option>
    </select>
  </form>
```

`hx-select="#recientes"` hace que htmx pida **la página entera** y se quede solo con ese trozo. Es deliberado y es lo que mantiene la promesa del §2.6 del spec: la URL con el filtro sigue siendo una página real que el service worker puede cachear y que se puede recargar o marcar, en vez de un endpoint de fragmento que solo existe para htmx.

Añade una prueba en `tests/budget/test_htmx.py`:

```python
@pytest.mark.django_db
def test_el_filtro_del_overview_es_una_pagina_de_verdad(client):
    """hx-select pide la pagina entera: la URL filtrada tiene que funcionar sola."""
    from django.urls import reverse

    _admin_logueado(client)
    url = reverse("budget:overview", args=["household"]) + "?kind=expense"

    entera = client.get(url)
    assert entera.status_code == 200
    assert b"<!doctype html>" in entera.content.lower()
    assert entera.context["filtro_kind"] == "expense"
```

- [ ] **Step 9: Corre las pruebas y pruébalo a mano**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_htmx.py tests/budget/test_views.py -q`
Expected: PASS.

Con el servidor arrancado: registra un gasto desde el Overview y comprueba que la tabla se actualiza **sin recargar la página** y que la URL no cambia; cambia el filtro y comprueba lo mismo; aporta a una meta desde la pantalla de metas.

Con esto htmx queda en **los cuatro sitios que el spec §6 nombra, y en ninguno más**. La navegación entre módulos sigue siendo carga de página completa.

- [ ] **Step 10: Commit**

```bash
git add static/vendor/ templates/ apps/budget/views_month.py \
        apps/budget/views_goals.py apps/budget/views_overview.py \
        README.md tests/budget/test_htmx.py
git commit -m "Vendoriza htmx y Alpine, y lo usa en los cuatro sitios del spec"
```

---

### Task 25: El formulario de línea excepcional

No hay formulario de `BudgetLine` en toda la aplicación, así que `is_exceptional` es un campo que nadie puede poner. Vuelve del montón B porque el **paso 2** del asistente del §4.5.6 lo necesita: *"gastos fijos precargados y editables, más las partidas excepcionales de ese mes"*.

**Files:**
- Modify: `apps/budget/forms.py`, `views_month.py`, `urls.py`
- Test: `tests/budget/test_views.py`

**Interfaces:**
- Produces: `BudgetLineForm(household=…)` y la ruta `budget:linea_nueva`. Los usa la Tarea 26.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
@pytest.mark.django_db
def test_se_puede_anadir_una_partida_excepcional_al_mes(client):
    from decimal import Decimal
    from django.urls import reverse

    from apps.budget.models import BudgetLine
    from apps.budget.seeds import sembrar
    from tests.factories_budget import CategoryFactory

    hogar, _user = _admin_logueado(client)
    sembrar(hogar)
    categoria = CategoryFactory(household=hogar, kind="expense")

    respuesta = client.post(reverse("budget:linea_nueva"), {
        "category": categoria.pk, "kind": "expense",
        "planned_amount": "320.00", "scope": "household",
        "note": "Inscripcion del campamento",
    })

    assert respuesta.status_code == 302
    linea = BudgetLine.objects.for_household(hogar).get(note="Inscripcion del campamento")
    assert linea.planned_amount == Decimal("320.00")
    # Sin regla detras: eso ES una linea excepcional (§5.3 del Plan 2).
    assert linea.source_income_id is None
    assert linea.source_expense_rule_id is None
    assert linea.is_exceptional is True


@pytest.mark.django_db
def test_no_se_anade_una_partida_a_un_mes_cerrado(client):
    from django.urls import reverse

    from apps.budget.seeds import sembrar
    from tests.factories_budget import BudgetMonthFactory, CategoryFactory

    hogar, _user = _admin_logueado(client)
    sembrar(hogar)
    categoria = CategoryFactory(household=hogar, kind="expense")
    from django.utils import timezone
    hoy = timezone.localdate()
    BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month, status="closed")

    respuesta = client.post(reverse("budget:linea_nueva"), {
        "category": categoria.pk, "kind": "expense",
        "planned_amount": "320.00", "scope": "household", "note": "Tarde",
    })

    assert respuesta.status_code == 200      # el formulario, con su error
    assert b"closed" in respuesta.content.lower()
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q -k "partida_excepcional or mes_cerrado"`
Expected: FAIL con `NoReverseMatch: 'linea_nueva'`.

- [ ] **Step 3: Escribe el formulario**

En `apps/budget/forms.py`:

```python
class BudgetLineForm(HouseholdScopedModelForm):
    """Las partidas excepcionales del paso 2 del §4.5.6.

    Sin este formulario, `is_exceptional` era un campo que nadie podia poner:
    materializar solo escribe lineas nacidas de una regla. Una linea sin
    source_income ni source_expense_rule ES una linea excepcional (§5.3 del
    diseno del Plan 2), asi que el formulario no ofrece esos dos campos y la
    vista marca is_exceptional.
    """

    class Meta:
        model = BudgetLine
        fields = ["category", "kind", "planned_amount", "scope", "owner", "note"]
```

- [ ] **Step 4: Escribe la vista y la ruta**

En `apps/budget/views_month.py`:

```python
@requiere_permiso("can_edit_budget")
def linea_nueva(request, hogar):
    """Anade una partida excepcional al mes corriente."""
    from .forms import BudgetLineForm

    hoy = timezone.localdate()
    form = BudgetLineForm(request.POST or None, household=hogar)
    if request.method == "POST" and form.is_valid():
        mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
        linea = form.save(commit=False)
        linea.household = hogar
        linea.budget_month = mes_actual
        linea.is_exceptional = True
        try:
            linea.full_clean()
            linea.save()
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("budget:mes", ambito="household")
    return render(request, "budget/formulario.html",
                  {"form": form, "titulo": _("One-off item this month")})
```

En `apps/budget/urls.py`, en el bloque sin ámbito:
```python
    path("line/new/", views_month.linea_nueva, name="linea_nueva"),
```

- [ ] **Step 5: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/budget/forms.py apps/budget/views_month.py apps/budget/urls.py tests/
git commit -m "Permite anadir partidas excepcionales, que nadie podia poner"
```

---

### Task 26: El asistente de planificar el mes, en tres pasos de verdad

Ingresos → salidas → reparto (§4.5.6). El paso 3 pide que **las reglas se reordenen arrastrando**: la única interacción de Alpine de este plan.

**Files:**
- Create: `apps/budget/wizards.py`, `templates/wizards/planificar_1.html`, `_2.html`, `_3.html`
- Modify: `apps/budget/urls.py`, `apps/core/context_processors.py`
- Delete: `templates/budget/planificar.html`
- Test: `tests/budget/test_views.py`

**Interfaces:**
- Consumes: `BudgetLineForm` de la Tarea 25, `services.planificar_mes`.
- Produces: rutas `budget:planificar` (paso 1), `budget:planificar_paso` con `<int:paso>`, y `budget:reordenar_reglas` (POST).

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
@pytest.mark.django_db
def test_el_asistente_tiene_tres_pasos(client):
    from django.urls import reverse

    from apps.budget.seeds import sembrar

    hogar, _user = _admin_logueado(client)
    sembrar(hogar)

    for paso in (1, 2, 3):
        respuesta = client.get(reverse("budget:planificar_paso", args=["household", paso]))
        assert respuesta.status_code == 200
        assert respuesta.context["paso"] == paso


@pytest.mark.django_db
def test_solo_el_paso_tres_escribe_el_reparto(client):
    from django.urls import reverse

    from apps.budget.models import MonthlyAllocation
    from apps.budget.seeds import sembrar

    hogar, _user = _admin_logueado(client)
    sembrar(hogar)

    client.post(reverse("budget:planificar_paso", args=["household", 1]))
    client.post(reverse("budget:planificar_paso", args=["household", 2]))
    assert not MonthlyAllocation.objects.for_household(hogar).exists()

    client.post(reverse("budget:planificar_paso", args=["household", 3]))
    # Sin reglas de reparto no hay filas, pero el mes queda abierto y planificado.
    assert client.session.get("plan_confirmado") is True


@pytest.mark.django_db
def test_reordenar_reglas_cambia_su_prioridad(client):
    from django.urls import reverse

    from apps.budget.models import AllocationRule
    from tests.factories_budget import AllocationRuleFactory

    hogar, _user = _admin_logueado(client)
    a = AllocationRuleFactory(household=hogar, order=1)
    b = AllocationRuleFactory(household=hogar, order=2)

    respuesta = client.post(
        reverse("budget:reordenar_reglas"),
        {"orden": [str(b.pk), str(a.pk)]},
        HTTP_HX_REQUEST="true",
    )

    assert respuesta.status_code == 200
    assert AllocationRule.objects.for_household(hogar).get(pk=b.pk).order == 1
    assert AllocationRule.objects.for_household(hogar).get(pk=a.pk).order == 2


@pytest.mark.django_db
def test_un_paso_inventado_da_404(client):
    hogar, _user = _admin_logueado(client)
    assert client.get("/budget/household/plan/9/").status_code == 404
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q -k "asistente or paso_tres or reordenar"`
Expected: FAIL con `NoReverseMatch: 'planificar_paso'`.

- [ ] **Step 3: Escribe el asistente**

Crea `apps/budget/wizards.py`:

```python
"""Los dos asistentes: planificar el mes (§4.5.6) e incorporacion (§7.2).

El de planificar existe porque el Plan 2 lo colapso en una pantalla con permiso
explicito de su plan, y el criterio de aceptacion 3 —"una pareja planifica el
mes en tres pasos"— se dio por bueno sobre una pantalla que no tiene tres.
"""

from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services
from .engine.cascade import repartir
from .models import AllocationRule
from .scopes import validar

PASOS = (1, 2, 3)


@requiere_permiso("can_edit_budget")
def planificar(request, hogar, ambito, paso=1):
    """Un paso del asistente. Solo el tercero escribe."""
    ambito = validar(ambito)
    if paso not in PASOS:
        raise Http404(_("That step does not exist."))

    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    proyeccion = (
        mes_actual if isinstance(mes_actual, services.ProyeccionDeMes)
        else services.proyectar(hogar, hoy.year, hoy.month)
    )

    if request.method == "POST":
        if paso < 3:
            # Los pasos 1 y 2 no escriben nada: el usuario ya edito lo suyo con
            # los formularios de reglas y de linea excepcional, que guardan por
            # su cuenta. Avanzar es solo avanzar.
            return redirect("budget:planificar_paso", ambito=ambito, paso=paso + 1)
        services.planificar_mes(hogar, mes_actual, proyeccion.sobrante)
        request.session["plan_confirmado"] = True
        return redirect("budget:mes", ambito=ambito)

    contexto = {
        "paso": paso, "ambito": ambito, "mes": mes_actual,
        "proyeccion": proyeccion,
    }
    if paso == 1:
        contexto["ingresos"] = [l for l in proyeccion.lineas if l.kind == "income"]
    elif paso == 2:
        contexto["egresos"] = [l for l in proyeccion.lineas if l.kind == "expense"]
    else:
        contexto.update(_reparto(hogar, proyeccion))

    return render(request, f"wizards/planificar_{paso}.html", contexto)


def _reparto(hogar, proyeccion):
    """El paso 3: el sobrante, la cascada y la mesada por miembro."""
    reglas_orm = {
        r.order: r
        for r in AllocationRule.objects.for_household(hogar).filter(is_active=True)
    }
    reglas = [
        r.a_regla_de_reparto(services.miembros_activos(hogar))
        for r in reglas_orm.values()
    ]
    miembros = {m.pk: m for m in hogar.active_memberships()}
    return {
        "reglas": list(reglas_orm.values()),
        "asignaciones": [
            {"importe": a.importe, "miembro": miembros.get(a.miembro_id),
             "regla": reglas_orm[a.orden]}
            for a in repartir(proyeccion.sobrante, reglas)
        ],
    }


@requiere_permiso("can_edit_budget")
def reordenar_reglas(request, hogar):
    """El arrastre del paso 3 (§4.5.6): "las reglas se reordenan arrastrando".

    Recibe la lista de pks en su orden nuevo y reescribe `order`. Se hace en
    dos pasadas y dentro de una transaccion porque AllocationRule tiene un
    UniqueConstraint sobre (household, order): asignar el orden final de una
    sola pasada choca con las filas que aun no se han movido.
    """
    from django.db import transaction
    from django.http import HttpResponseBadRequest

    if request.method != "POST":
        return HttpResponseBadRequest()

    pks = [p for p in request.POST.getlist("orden") if p.isdigit()]
    reglas = {
        r.pk: r for r in AllocationRule.objects.for_household(hogar).filter(pk__in=pks)
    }
    if len(reglas) != len(pks):
        # Un pk de otra familia, o inventado. La barrera ya lo filtro; esto
        # solo evita reordenar a medias.
        return HttpResponseBadRequest()

    with transaction.atomic():
        # Primera pasada a un rango imposible de chocar.
        for desplazamiento, pk in enumerate(pks, start=1):
            regla = reglas[int(pk)]
            regla.order = 10000 + desplazamiento
            regla.save(update_fields=["order"])
        # Segunda, al orden de verdad.
        for posicion, pk in enumerate(pks, start=1):
            regla = reglas[int(pk)]
            regla.order = posicion
            regla.save(update_fields=["order"])

    return render(request, "wizards/_reglas.html", {
        "reglas": AllocationRule.objects.for_household(hogar).filter(is_active=True),
    })
```

Ese comentario de las dos pasadas no es paranoia: con `UniqueConstraint(household, order)`, mover la regla 2 a la posición 1 choca con la regla que todavía ocupa la 1.

- [ ] **Step 4: Escribe las tres plantillas y el fragmento**

`templates/wizards/planificar_1.html` (los otros dos son iguales en estructura):

```html
{% extends "base.html" %}{% load i18n money %}
{% block title %}{% translate "Plan the month" %} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <p class="pildora">{% blocktranslate %}Step {{ paso }} of 3{% endblocktranslate %}</p>
  <h1>{% translate "What is coming in" %}</h1>
  <p>{% translate "The fixed ones are already here. Confirm or adjust what varies — it is the only number you type each month." %}</p>

  <div class="tabla__envoltura">
    <table class="tabla">
      {% for linea in ingresos %}
        <tr><td>{{ linea.nombre }}</td>
            <td class="numero">{{ linea.importe|money:hogar.currency }}</td></tr>
      {% empty %}
        <tr><td>{% translate "No income set up yet." %}</td></tr>
      {% endfor %}
    </table>
  </div>

  <form method="post">
    {% csrf_token %}
    <button class="btn btn--primary" type="submit">{% translate "Next" %}</button>
    <a class="btn btn--sutil" href="{% url 'budget:configurar' %}">{% translate "Edit income" %}</a>
  </form>
</section>
{% endblock %}
```

`templates/wizards/planificar_2.html`:

```html
{% extends "base.html" %}{% load i18n money %}
{% block title %}{% translate "Plan the month" %} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <p class="pildora">{% blocktranslate %}Step {{ paso }} of 3{% endblocktranslate %}</p>
  <h1>{% translate "What is going out" %}</h1>

  <div class="tabla__envoltura">
    <table class="tabla">
      {% for linea in egresos %}
        <tr><td>{{ linea.nombre }}</td>
            <td class="numero">{{ linea.importe|money:hogar.currency }}</td></tr>
      {% empty %}
        <tr><td>{% translate "No fixed expenses set up yet." %}</td></tr>
      {% endfor %}
    </table>
  </div>

  {# El paso 2 del §4.5.6: "mas las partidas excepcionales de ese mes". Es la
     razon por la que el formulario de linea excepcional vuelve en la Tarea 25. #}
  <p><a class="btn" href="{% url 'budget:linea_nueva' %}">{% translate "Add a one-off item" %}</a></p>

  <form method="post">
    {% csrf_token %}
    <button class="btn btn--primary" type="submit">{% translate "Next" %}</button>
    <a class="btn btn--sutil" href="{% url 'budget:planificar_paso' ambito 1 %}">{% translate "Back" %}</a>
  </form>
</section>
{% endblock %}
```

`templates/wizards/planificar_3.html`:

```html
{% extends "base.html" %}{% load i18n money %}
{% block title %}{% translate "Plan the month" %} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <p class="pildora">{% blocktranslate %}Step {{ paso }} of 3{% endblocktranslate %}</p>
  <h1>{% translate "How the leftover gets split" %}</h1>

  <div class="cifras">
    <div class="cifra">
      <div class="cifra__etiqueta">{% translate "Left over" %}</div>
      <div class="cifra__valor">{{ proyeccion.sobrante|money:hogar.currency }}</div>
    </div>
  </div>

  <h2>{% translate "Your rules, in order" %}</h2>
  <p class="campo__ayuda">{% translate "Drag to reorder. What is at the top gets served first, so a lean month eats into the bottom of the list." %}</p>
  {% include "wizards/_reglas.html" %}

  <h2>{% translate "What each person gets" %}</h2>
  <div class="tabla__envoltura">
    <table class="tabla">
      {% for asignacion in asignaciones %}
        <tr>
          <td>
            {% if asignacion.miembro %}{{ asignacion.miembro.user }}
            {% else %}{{ asignacion.regla.get_target_type_display }}{% endif %}
          </td>
          <td class="numero">{{ asignacion.importe|money:hogar.currency }}</td>
        </tr>
      {% empty %}
        <tr><td>{% translate "No split rules yet." %}</td></tr>
      {% endfor %}
    </table>
  </div>

  <form method="post">
    {% csrf_token %}
    <button class="btn btn--primary" type="submit">{% translate "Confirm the plan" %}</button>
    <a class="btn btn--sutil" href="{% url 'budget:planificar_paso' ambito 2 %}">{% translate "Back" %}</a>
  </form>
</section>
{% endblock %}
```

El nombre del miembro y no solo el importe, porque el §13.5 pide que **cada uno sepa cuánta mesada tiene**, y un número suelto en una lista no dice de quién es.

`templates/wizards/_reglas.html`, con el arrastre de Alpine:

```html
{% load i18n %}
<ul id="reglas" class="reglas"
    x-data="{
      arrastrada: null,
      soltar(destino) {
        if (this.arrastrada === null || this.arrastrada === destino) return;
        const lista = this.$el;
        const nodos = Array.from(lista.children);
        lista.insertBefore(nodos[this.arrastrada], nodos[destino]);
        htmx.ajax('POST', lista.dataset.url, {
          values: { orden: Array.from(lista.children).map(n => n.dataset.pk) },
          target: '#reglas', swap: 'outerHTML'
        });
      }
    }"
    data-url="{% url 'budget:reordenar_reglas' %}">
  {% for regla in reglas %}
    <li class="reglas__item" draggable="true" data-pk="{{ regla.pk }}"
        @dragstart="arrastrada = {{ forloop.counter0 }}"
        @dragover.prevent
        @drop.prevent="soltar({{ forloop.counter0 }})">
      {{ regla.order }}. {{ regla.get_target_type_display }}
    </li>
  {% endfor %}
</ul>
```

Borra `templates/budget/planificar.html`.

- [ ] **Step 5: Rutas y menú**

En `apps/budget/urls.py`, sustituye la ruta de `planificar` y añade las otras dos:

```python
    path("<str:ambito>/plan/", wizards.planificar, name="planificar"),
    path("<str:ambito>/plan/<int:paso>/", wizards.planificar, name="planificar_paso"),
```
y en el bloque sin ámbito:
```python
    path("split/reorder/", wizards.reordenar_reglas, name="reordenar_reglas"),
```

Importa `wizards` arriba y quita `views_month.planificar` de las importaciones.

- [ ] **Step 6: Corre las pruebas y arrástralo a mano**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q`
Expected: PASS.

Con el servidor arrancado y al menos dos reglas de reparto creadas, ve al paso 3 y **arrastra una regla sobre otra**: el orden debe cambiar y persistir al recargar.

- [ ] **Step 7: Commit**

```bash
git add apps/budget/wizards.py apps/budget/urls.py templates/wizards/ tests/
git rm templates/budget/planificar.html
git commit -m "Cumple el 4.5.6: planificar el mes en tres pasos, con arrastre"
```

---

### Task 27: El asistente de incorporación, abandonable y reanudable

Seis pasos (§7.2): crear hogar → miembros → ingresos → gastos fijos → meta de ahorro → reglas de reparto. Hoy el registro es un solo formulario.

**Que sea abandonable no es un adorno.** El paso 1 crea el hogar de verdad y los cinco siguientes escriben contra él, así que quien cierre la pestaña en el paso 3 **ya tiene un hogar**. Un asistente que hay que terminar de una sentada convierte una interrupción en una cuenta rota.

**Files:**
- Modify: `apps/budget/wizards.py`, `apps/accounts/views.py`
- Create: `templates/wizards/incorporacion.html`
- Modify: `apps/budget/urls.py`
- Test: `tests/test_incorporacion.py`

**Interfaces:**
- Produces: ruta `budget:incorporacion` con `<int:paso>` de 2 a 6. El paso 1 sigue siendo `accounts:registro`, que ya crea usuario y hogar.

- [ ] **Step 1: Escribe las pruebas que fallan**

Crea `tests/test_incorporacion.py`:

```python
"""El asistente del §7.2, y sobre todo que se pueda abandonar.

El paso 1 crea el hogar de verdad; los cinco siguientes escriben contra el. Un
asistente obligatorio convertiria cerrar la pestana en el paso 3 en una cuenta
rota, asi que cada paso se puede saltar y el asistente se reanuda.
"""

import pytest
from django.urls import reverse

from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


@pytest.mark.django_db
def test_el_registro_deja_al_admin_en_el_paso_dos(client):
    respuesta = client.post(reverse("accounts:registro"), {
        "email": "nuevo@example.com", "password1": "clave-larga-123",
        "password2": "clave-larga-123", "display_name": "Nuevo",
        "household_name": "Los Nuevos", "family_size": 3,
    }, follow=True)

    assert respuesta.status_code == 200
    assert reverse("budget:incorporacion", args=[2]) in respuesta.redirect_chain[-1][0]


@pytest.mark.django_db
@pytest.mark.parametrize("paso", [2, 3, 4, 5, 6])
def test_cada_paso_se_puede_saltar(client, paso):
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.get(reverse("budget:incorporacion", args=[paso]))
    assert respuesta.status_code == 200
    assert respuesta.context["paso"] == paso
    assert respuesta.context["siguiente"] is not None or paso == 6


@pytest.mark.django_db
def test_abandonar_a_medias_deja_una_aplicacion_usable(client):
    """Cerrar la pestana en el paso 3 no puede dejar una cuenta rota."""
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    client.get(reverse("budget:incorporacion", args=[3]))

    # Y ahora, como si hubiera cerrado la pestana: entra por la puerta normal.
    assert client.get(reverse("budget:mes", args=["household"])).status_code == 200
    assert client.get(reverse("budget:configurar")).status_code == 200


@pytest.mark.django_db
def test_un_paso_fuera_de_rango_da_404(client):
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    assert client.get("/budget/welcome/9/").status_code == 404
```

- [ ] **Step 2: Corre y comprueba que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_incorporacion.py -q`
Expected: FAIL con `NoReverseMatch: 'incorporacion'`.

- [ ] **Step 3: Escribe el asistente**

En `apps/budget/wizards.py`:

```python
PASOS_INCORPORACION = {
    2: ("miembros", "households:invitar", _("Who else lives here")),
    3: ("ingresos", "budget:ingreso_nuevo", _("What comes in")),
    4: ("gastos", "budget:gasto_nuevo", _("What goes out every month")),
    5: ("meta", "budget:meta_nueva", _("What you are saving for")),
    6: ("reparto", "budget:reparto_nuevo", _("How the leftover gets split")),
}


@requiere_permiso("can_edit_budget")
def incorporacion(request, hogar, paso):
    """El asistente del §7.2, del paso 2 al 6. El 1 es el registro.

    Cada paso ENVUELVE un formulario que ya existe en Configurar en vez de
    duplicarlo: el asistente es una guia, no una segunda forma de crear las
    mismas cosas. Y cada paso se puede saltar, porque el hogar ya existe desde
    el paso 1 y abandonar tiene que dejar una aplicacion usable.
    """
    if paso not in PASOS_INCORPORACION:
        raise Http404(_("That step does not exist."))

    nombre, ruta, titulo = PASOS_INCORPORACION[paso]
    siguiente = paso + 1 if paso + 1 in PASOS_INCORPORACION else None
    return render(request, "wizards/incorporacion.html", {
        "paso": paso, "total": 6, "nombre": nombre, "titulo": titulo,
        "ruta_del_formulario": ruta, "siguiente": siguiente,
    })
```

En `apps/budget/urls.py`, en el bloque sin ámbito:
```python
    path("welcome/<int:paso>/", wizards.incorporacion, name="incorporacion"),
```

Y en `apps/accounts/views.py`, dentro de `registro`, cambia el destino tras `login`:
```python
            return redirect("budget:incorporacion", paso=2)
```

- [ ] **Step 4: Escribe la plantilla**

`templates/wizards/incorporacion.html`:

```html
{% extends "base.html" %}{% load i18n %}
{% block title %}{{ titulo }} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <p class="pildora">{% blocktranslate %}Step {{ paso }} of {{ total }}{% endblocktranslate %}</p>
  <h1>{{ titulo }}</h1>

  <p><a class="btn btn--primary" href="{% url ruta_del_formulario %}">{% translate "Set this up" %}</a></p>

  <p>
    {% if siguiente %}
      <a class="btn btn--sutil" href="{% url 'budget:incorporacion' siguiente %}">{% translate "Skip for now" %}</a>
    {% else %}
      <a class="btn btn--sutil" href="{% url 'budget:mes' 'household' %}">{% translate "Finish" %}</a>
    {% endif %}
  </p>

  <p class="campo__ayuda">{% translate "You can close this at any point. Everything you set up is already saved, and the rest lives in Settings whenever you want it." %}</p>
</section>
{% endblock %}
```

Esa última frase es la promesa del §2 hecha texto: quien la lea sabe que abandonar no rompe nada.

- [ ] **Step 5: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/test_incorporacion.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/budget/wizards.py apps/budget/urls.py apps/accounts/views.py \
        templates/wizards/incorporacion.html tests/test_incorporacion.py
git commit -m "Anade el asistente de incorporacion, abandonable en cualquier paso"
```

---

### Task 28: Catálogo bilingüe, tanda 5

**Files:**
- Modify: `locale/en/LC_MESSAGES/django.po`, `locale/fr/LC_MESSAGES/django.po`

- [ ] **Step 1: Corre la prueba, escribe y compila**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalogo_exhaustivo.py -q`

Las cadenas nuevas son las de los dos asistentes (`Step %(paso)s of 3`, `Step %(paso)s of %(total)s`, los seis títulos de `PASOS_INCORPORACION`, `Set this up`, `Skip for now`, `Finish`, la frase de abandonar), las de htmx (`Record it`, `Record a spend`) y la de la línea excepcional (`One-off item this month`, `Add a one-off item`).

```bash
MSGFMT="C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py"
for L in en fr; do .venv/Scripts/python.exe "$MSGFMT" -o "locale/$L/LC_MESSAGES/django.mo" "locale/$L/LC_MESSAGES/django.po"; done
```

- [ ] **Step 2: Corre las dos mitades**

Run: `.venv/Scripts/python.exe -m pytest -q --ignore=tests/budget`
Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add locale/
git commit -m "Traduce los dos asistentes y los fragmentos de htmx"
```

> **Punto de control 5. El §4.5.6, cumplido.** Una pareja planifica el mes en tres pasos de verdad, reordena las reglas arrastrando y añade una partida excepcional. Y quien se registra entra por un asistente que puede abandonar cuando quiera.

---

## Tanda 6 · La PWA

Tres tareas. La última entrega la garantía de privacidad que decidimos al fijar el alcance: **la caché se purga al cerrar sesión**.

---

### Task 29: Manifiesto, iconos e instalación

**Files:**
- Create: `static/manifest.json`, `static/icons/icono-192.png`, `icono-512.png`
- Modify: `templates/base.html`
- Test: `tests/test_pwa.py`

- [ ] **Step 1: Escribe la prueba que falla**

Crea `tests/test_pwa.py`:

```python
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def test_el_manifiesto_es_json_valido_y_completo():
    manifiesto = json.loads((RAIZ / "static" / "manifest.json").read_text(encoding="utf-8"))
    assert manifiesto["name"]
    assert manifiesto["start_url"]
    assert manifiesto["display"] == "standalone"
    tamanos = {icono["sizes"] for icono in manifiesto["icons"]}
    assert {"192x192", "512x512"} <= tamanos


@pytest.mark.django_db
def test_la_pagina_enlaza_el_manifiesto(client):
    from django.urls import reverse

    respuesta = client.get(reverse("accounts:login"))
    assert b"manifest.json" in respuesta.content
```

- [ ] **Step 2: Escribe el manifiesto y los iconos**

`static/manifest.json`:

```json
{
  "name": "Wealthome",
  "short_name": "Wealthome",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#e9edf1",
  "theme_color": "#3f8f6f",
  "icons": [
    {"src": "/static/icons/icono-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/icons/icono-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

Los colores van literales aquí y no como variables: el manifiesto lo lee el sistema operativo antes de que exista ninguna hoja de estilo, y no puede leer CSS. Son los de Sereno, el tema por defecto.

Genera los dos iconos con Pillow, que ya es dependencia:

```bash
.venv/Scripts/python.exe -c "
from PIL import Image, ImageDraw
for lado in (192, 512):
    img = Image.new('RGB', (lado, lado), '#e9edf1')
    d = ImageDraw.Draw(img)
    m = lado // 6
    d.rounded_rectangle([m, m, lado - m, lado - m], radius=lado // 8, fill='#3f8f6f')
    img.save(f'static/icons/icono-{lado}.png')
print('iconos escritos')
"
```

Crea antes el directorio: `mkdir -p static/icons`.

- [ ] **Step 3: Enlázalo en `base.html`**

En el `<head>`:

```html
  <link rel="manifest" href="{% static 'manifest.json' %}">
  <meta name="theme-color" content="#3f8f6f">
  <link rel="apple-touch-icon" href="{% static 'icons/icono-192.png' %}">
```

- [ ] **Step 4: Corre las pruebas y compruébalo en el navegador**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pwa.py -q`
Expected: PASS.

Con el servidor arrancado, abre las herramientas de desarrollo → Application → Manifest y comprueba que no hay avisos.

- [ ] **Step 5: Commit**

```bash
git add static/manifest.json static/icons/ templates/base.html tests/test_pwa.py
git commit -m "Hace la aplicacion instalable con su manifiesto y sus iconos"
```

---

### Task 30: El service worker

Tres comportamientos: precarga del armazón, red primero para las páginas del hogar, y una página de "sin conexión".

**Desactivado bajo `DEBUG`.** Un service worker que cachea vuelve el desarrollo confuso —se sirve una versión vieja y parece un error de código—, y media tanda se puede ir en depurar eso.

**Files:**
- Create: `static/js/sw.js`, `templates/sin-conexion.html`
- Modify: `templates/base.html`, `config/urls.py`
- Test: `tests/test_pwa.py`

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
def test_el_service_worker_no_cachea_el_webhook_ni_el_login():
    sw = (RAIZ / "static" / "js" / "sw.js").read_text(encoding="utf-8")
    assert "/subscription/webhook/" in sw
    assert "logout" in sw
    # Solo GET: cachear un POST serviria una respuesta de escritura vieja.
    assert "request.method" in sw


@pytest.mark.django_db
def test_el_service_worker_no_se_registra_en_desarrollo(client, settings):
    from django.urls import reverse

    settings.DEBUG = True
    assert b"serviceWorker" not in client.get(reverse("accounts:login")).content

    settings.DEBUG = False
    assert b"serviceWorker" in client.get(reverse("accounts:login")).content
```

- [ ] **Step 2: Escribe el service worker**

`static/js/sw.js`:

```javascript
/* El service worker de Wealthome (§10).
 *
 * Cachea el armazon Y las paginas financieras que el miembro haya abierto, para
 * que pueda consultarlas sin senal. Eso significa que la cache contiene las
 * finanzas de una familia en un dispositivo que puede ser compartido, asi que
 * la purga al cerrar sesion (sw.js + Clear-Site-Data) es una garantia de
 * privacidad y no una optimizacion. Ver tests/test_pwa.py.
 */
var VERSION = "wealthome-v1";
var ARMAZON = "armazon-" + VERSION;
var PAGINAS = "paginas-" + VERSION;

var PRECARGA = [
  "/static/css/tokens.css",
  "/static/css/base.css",
  "/static/css/components.css",
  "/static/css/modules.css",
  "/static/vendor/htmx.min.js",
  "/static/vendor/alpine.min.js",
  "/static/vendor/chart.umd.min.js",
  "/static/js/graficas.js",
  "/static/manifest.json",
  "/static/icons/icono-192.png",
  "/offline/"
];

// Nada de esto se cachea nunca: el webhook es de Stripe, y las paginas de
// sesion tienen que hablar con el servidor siempre.
var NUNCA = ["/subscription/webhook/", "/logout/", "/login/", "/signup/"];

self.addEventListener("install", function (evento) {
  evento.waitUntil(
    caches.open(ARMAZON).then(function (cache) { return cache.addAll(PRECARGA); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (evento) {
  evento.waitUntil(
    caches.keys().then(function (nombres) {
      return Promise.all(nombres.map(function (n) {
        if (n.indexOf(VERSION) === -1) { return caches.delete(n); }
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (evento) {
  var peticion = evento.request;

  // Solo GET. Cachear un POST serviria una respuesta de escritura vieja, que en
  // una aplicacion financiera es peor que no tener cache.
  if (peticion.method !== "GET") { return; }

  var url = new URL(peticion.url);
  if (url.origin !== self.location.origin) { return; }
  for (var i = 0; i < NUNCA.length; i++) {
    if (url.pathname.indexOf(NUNCA[i]) === 0) { return; }
  }

  if (url.pathname.indexOf("/static/") === 0) {
    evento.respondWith(
      caches.match(peticion).then(function (r) { return r || fetch(peticion); })
    );
    return;
  }

  // Red primero para las paginas: lo cacheado es la reserva, no la verdad.
  evento.respondWith(
    fetch(peticion).then(function (respuesta) {
      var copia = respuesta.clone();
      caches.open(PAGINAS).then(function (cache) { cache.put(peticion, copia); });
      return respuesta;
    }).catch(function () {
      return caches.match(peticion).then(function (r) {
        return r || caches.match("/offline/");
      });
    })
  );
});

// La purga: la pide la pagina al cerrar sesion. Ver Tarea 31.
self.addEventListener("message", function (evento) {
  if (evento.data === "purgar") {
    evento.waitUntil(
      caches.keys().then(function (nombres) {
        return Promise.all(nombres.map(function (n) { return caches.delete(n); }));
      })
    );
  }
});
```

- [ ] **Step 3: Regístralo, y solo fuera de desarrollo**

En `templates/base.html`, antes de `</body>`:

```html
  {% if not debug %}
  <script>
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("{% static 'js/sw.js' %}", { scope: "/" });
    }
  </script>
  {% endif %}
```

`debug` viene del context processor `django.template.context_processors.debug`, que solo lo expone si la IP está en `INTERNAL_IPS`. Para no depender de eso, añade `"debug": settings.DEBUG` a `apps/core/context_processors.navegacion` y usa esa clave.

- [ ] **Step 4: La página de "sin conexión"**

`templates/sin-conexion.html`:

```html
{% extends "base.html" %}{% load i18n %}
{% block title %}{% translate "No connection" %} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <h1>{% translate "No connection" %}</h1>
  <p>{% translate "You are offline and this page was not saved on this device. Anything you have already opened is still here." %}</p>
</section>
{% endblock %}
```

En `config/urls.py`:

```python
from django.views.generic import TemplateView

    path("offline/", TemplateView.as_view(template_name="sin-conexion.html"), name="sin_conexion"),
```

El service worker tiene que poder precargarla, así que **no lleva decorador de sesión**: es una página sin datos.

- [ ] **Step 5: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pwa.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add static/js/sw.js templates/ config/urls.py \
        apps/core/context_processors.py tests/test_pwa.py
git commit -m "Anade el service worker, desactivado en desarrollo"
```

---

### Task 31: La purga al cerrar sesión, con Playwright

La única prueba de navegador del plan. Va aquí porque **es una garantía de privacidad**: la caché contiene las finanzas de una familia, en un dispositivo que puede ser compartido, y es la clase de cosa que se rompe en silencio y que una comprobación manual no vuelve a mirar.

**Files:**
- Modify: `apps/accounts/views.py` (la vista de logout), `templates/base.html`
- Modify: `requirements.txt`, `pytest.ini`
- Modify: `tests/test_pwa.py`

**Interfaces:**
- Produces: la respuesta de logout lleva la cabecera `Clear-Site-Data: "cache", "storage"`.

- [ ] **Step 1: Instala Playwright**

```bash
.venv/Scripts/python.exe -m pip install pytest-playwright
.venv/Scripts/python.exe -m playwright install chromium
```

Añade a `requirements.txt`:
```
pytest-playwright==0.5.*
```

Y en `pytest.ini`, declara la marca para poder excluirla:
```
markers =
    navegador: usa Playwright y un navegador de verdad. Se excluye con -m "not navegador".
```

- [ ] **Step 2: Escribe las pruebas**

En `tests/test_pwa.py`:

```python
@pytest.mark.django_db
def test_cerrar_sesion_manda_clear_site_data(client):
    from django.urls import reverse

    from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)

    respuesta = client.post(reverse("accounts:logout"))

    cabecera = respuesta.headers.get("Clear-Site-Data", "")
    assert "cache" in cabecera
    assert "storage" in cabecera


@pytest.mark.navegador
@pytest.mark.django_db(transaction=True)
def test_cerrar_sesion_deja_la_cache_vacia(page, live_server, settings):
    """La unica prueba de navegador del plan.

    La purga es una garantia de privacidad: la cache guarda las finanzas de una
    familia en un dispositivo que puede ser compartido. Una comprobacion manual
    se hace una vez; esta se hace siempre.
    """
    from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

    settings.DEBUG = False
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")

    page.goto(live_server.url + "/login/")
    page.fill("input[name='username']", user.email)
    page.fill("input[name='password']", "clave-larga-123")
    page.click("button[type='submit']")

    page.goto(live_server.url + "/budget/household/")
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    page.wait_for_function("caches.keys().then(k => k.length > 0)")

    page.click("a[href*='logout'], button[name='logout']")
    page.wait_for_function("caches.keys().then(k => k.length === 0)", timeout=10000)

    claves = page.evaluate("caches.keys()")
    assert claves == []
```

- [ ] **Step 3: Manda la cabecera al cerrar sesión**

En `apps/accounts/views.py`:

```python
class Logout(LogoutView):
    next_page = reverse_lazy("accounts:login")

    def dispatch(self, request, *args, **kwargs):
        """Purga la cache del navegador al salir.

        La PWA cachea las paginas financieras que el miembro haya abierto para
        que pueda consultarlas sin senal (§10). En un dispositivo compartido,
        dejarlas ahi despues de cerrar sesion seria entregarle el presupuesto de
        una familia a la siguiente persona que lo use.

        Dos mecanismos, porque ninguno basta solo: Clear-Site-Data lo hace el
        navegador, y el mensaje al service worker cubre a los navegadores que
        no la implementan.
        """
        respuesta = super().dispatch(request, *args, **kwargs)
        respuesta.headers["Clear-Site-Data"] = '"cache", "storage"'
        return respuesta
```

- [ ] **Step 4: Y avisa al service worker**

En `templates/base.html`, dentro del bloque `{% if not debug %}` del registro:

```html
    document.addEventListener("submit", function (evento) {
      var accion = evento.target.getAttribute("action") || "";
      if (accion.indexOf("logout") !== -1 && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage("purgar");
      }
    });
```

Comprueba que el enlace de cerrar sesión sea un `<form method="post">` con `action` a `accounts:logout` — en Django 5 el logout **exige POST**, así que ya debería serlo. Si en alguna plantilla es un `<a>`, cámbialo aquí.

- [ ] **Step 5: Corre las pruebas**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pwa.py -q`
Expected: PASS. La de navegador tarda unos segundos y abre Chromium sin ventana.

Si la prueba de navegador resulta inestable en esta máquina, **no la borres ni la marques como saltada**: déjala y anota en el traspaso que se corre con `-m navegador` a mano. Una prueba de privacidad que se ejecuta a veces vale más que ninguna.

- [ ] **Step 6: Corre la suite entera, en dos mitades**

Run: `.venv/Scripts/python.exe -m pytest tests/budget -q --create-db`
Run: `.venv/Scripts/python.exe -m pytest -q --ignore=tests/budget`
Expected: PASS las dos. Es la corrida final del plan; el `--create-db` es obligatorio porque el plan añadió seis migraciones.

- [ ] **Step 7: Commit**

```bash
git add apps/accounts/views.py templates/base.html requirements.txt \
        pytest.ini tests/test_pwa.py
git commit -m "Purga la cache del navegador al cerrar sesion, con prueba"
```

> **Punto de control 6, y final.** La aplicación se instala, abre sin señal enseñando lo ya visitado, y cerrar sesión deja la caché vacía.

---

## Cierre del plan

Al terminar la Tarea 31, repasa los trece criterios de aceptación del §12 del spec uno por uno, y para cada uno **nombra la prueba que lo cubre o ejercítalo a mano**. Los que no tienen prueba automática son el 11 (instalar en la pantalla de inicio) y el 12 (los tres temas a ojo): hazlos a mano con el servidor arrancado.

Después:

- Invoca `superpowers:requesting-code-review` sobre la rama completa. El Plan 2 aprendió que los tres fallos críticos estaban todos en el único punto de entrada al ciclo del mes, y que las pruebas de cada tarea solo cubrían su camino feliz. Este plan tiene **dos** puntos de entrada nuevos con esa forma: el webhook, que es público y sin autenticar, y la guardia de `_decorador`, por la que pasa toda petición de la aplicación.
- Invoca `superpowers:finishing-a-development-branch` para decidir cómo integrar.
- Escribe el documento de traspaso, como hicieron los Planes 1 y 2: `docs/superpowers/YYYY-MM-DD-estado-y-deuda-plan-4.md`, con lo que **no se deduce leyendo el código** — las decisiones que hay que respetar, la deuda que este plan no tocó (los montones B y C, íntegros), y las trampas del entorno que se hayan descubierto.
- **Recuerda que `main` tenía 34 commits sin publicar** en `origin/main` antes de empezar este plan.

Lo que queda para el Plan 4, sabido de antemano:

- Los montones B y C de la deuda del Plan 2, enteros y sin tocar.
- `AllocationRule.pesos` y `split=weighted`, que el motor soporta y la interfaz sigue sin alcanzar.
- Reportes (§7.1, quinta pestaña), registrar gastos sin conexión con su cola de sincronización (§10), y Capacitor.

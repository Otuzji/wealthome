# Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un Overview de solo lectura del mes en curso (Forecast, Real, Expenses, Desvíos, Alerta de Cash Float con saldo inicial) como pantalla de entrada de Wealthome.

**Architecture:** Toda la lógica en un módulo de servicio nuevo, `apps/budget/services_overview.py`, que recibe líneas y transacciones ya acotadas al ámbito y una fecha `hoy` explícita (tests deterministas). La vista `views_overview.overview` arma el contexto y pinta `templates/budget/overview.html`. Un campo nuevo `BudgetMonth.opening_balance` alimenta solo la alerta.

**Tech Stack:** Django 5.1, htmx, Alpine, pytest + factory_boy (base de pruebas en Supabase), catálogos `.po` a mano.

**Spec:** `docs/superpowers/specs/2026-10-24-wealthome-overview-design.md` (léelo entero antes de empezar; los § de este plan apuntan a él).

## Global Constraints

- Correr pruebas: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" <ruta>`. **Nunca** dos corridas de pytest a la vez (comparten la base de pruebas).
- **No correr `manage.py migrate` ni `runserver` contra el `.env` local: apunta a la base de producción.** `makemigrations` sí (no toca la base). Los tests crean su propia base.
- Forecast y Real deben salir de las mismas funciones que This month (`totales`, `real_contra_planeado`, `services.cash_float`); prohibida una segunda implementación.
- Todo dato pasa por `acotar` (transacciones) / `acotar_por_dueno` (líneas) de `apps/budget/scopes.py`.
- Un GET al Overview **no escribe** filas nuevas (salvo lo que ya hace `obtener_mes` del mes en curso). Nada de `obtener_mes` para el mes siguiente, nada de `mesada_de`.
- Todo texto visible con `{% translate %}` / `_()` y su traducción en `locale/fr/LC_MESSAGES/django.po` (a mano), compilado con `.venv/Scripts/pybabel.exe compile -d locale -D django --statistics`. En `_()` cada cadena en una sola línea literal (el extractor no une cadenas partidas).
- Importes en plantilla con el filtro `money` (`{% load money %}`, `importe|money:hogar.currency`).
- Comentarios y nombres en español, con el estilo del código vecino.
- Commits terminan con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Día 1 del mes, sin saldo inicial ni ingresos reales:** la alerta no debe decir "Short" sin decir a la vez que falta el saldo inicial (pista + campo visibles). Test en Task 4 (`test_sin_saldo_inicial_lo_pide`) y Task 6.
2. **Un miembro sin `can_edit_budget` en un hogar con presupuesto:** ve el Overview completo pero sin campo de saldo inicial, y un POST al guardado da 403. Test en Task 6.
3. **Lo personal de otro miembro:** en Personal, ni sus líneas, ni sus gastos, ni su mesada influyen en ninguna cifra; en Household, una línea/transacción personal tampoco. Test en Task 5 (`test_personal_no_cuenta_lo_de_otro_miembro`).
4. **Barra inferior en móvil con 6 pestañas (Personal):** cabe sin scroll horizontal a 360 px. Verificación en Task 7 (Playwright).
5. **Mes siguiente con fila ya existente pero sin líneas** (la crea `aplicar_cascada_al_cierre` para el ajuste de mesada): la búsqueda del próximo ingreso cae a `proyectar` y no deja la fila materializada. Test en Task 4 (`test_mes_siguiente_vacio_se_proyecta_sin_escribir`).

---

## File Structure

- Create `apps/budget/services_overview.py` — cálculos del Overview (sin HTTP).
- Create `apps/budget/views_overview.py` — vista `overview` y vista `saldo_inicial`.
- Create `apps/budget/migrations/0012_budgetmonth_opening_balance.py` (vía `makemigrations`).
- Create `templates/budget/overview.html` y `templates/budget/_fragmentos/overview_alerta.html` (la alerta; es lo que htmx reemplaza al guardar el saldo).
- Modify `apps/budget/models/months.py` (campo), `apps/budget/views_month.py` (importa `totales`/`real_contra_planeado` del servicio), `apps/budget/views_summary.py` (fuera `overview` y el docstring), `apps/budget/urls.py`, `apps/budget/forms.py` (form del saldo), `apps/core/context_processors.py`, `templates/_nav_icono.html`, `apps/accounts/views.py` (`inicio`), `templates/sw.js`, `tests/test_pwa.py`, `static/css/modules.css`, `locale/fr/LC_MESSAGES/django.po`.
- Tests: `tests/budget/test_services_overview.py`, `tests/budget/test_overview_vistas.py`; modificar `tests/test_navegacion.py`, `tests/budget/test_views.py` (~línea 597), `tests/test_presupuesto_consultas.py`.

Datos de prueba: `crear_hogar(user, nombre, family_size=4)` (siembra categorías) y las factories de `tests/factories_budget.py` / `tests/factories.py`. Ver `tests/budget/test_cash_float.py::mes_con_dinero` como modelo de fixture. Una factory no puede escribir en un mes CLOSED: sembrar abierto y cerrar con `mes.status = "closed"; mes.save(update_fields=["status"])`.

---

### Task 1: `BudgetMonth.opening_balance`

**Files:**
- Modify: `apps/budget/models/months.py:19-52`
- Create: `apps/budget/migrations/0012_budgetmonth_opening_balance.py`
- Test: `tests/budget/test_models.py` (añadir al final)

**Interfaces:**
- Produces: `BudgetMonth.opening_balance: Decimal | None` (`MoneyField(verbose_name=_("opening balance"), null=True, blank=True)`), `None` = no introducido.

- [ ] **Step 1: Write the failing test**

```python
def test_el_mes_guarda_un_saldo_inicial_opcional(db):
    mes = BudgetMonthFactory()
    assert mes.opening_balance is None
    mes.opening_balance = Decimal("1250.50")
    mes.save(update_fields=["opening_balance"])
    mes.refresh_from_db()
    assert mes.opening_balance == Decimal("1250.50")
```

- [ ] **Step 2:** Run `... pytest tests/budget/test_models.py -k saldo_inicial` → FAIL (`AttributeError`/campo inexistente).
- [ ] **Step 3:** Añadir el campo con un comentario que diga para qué es (solo la alerta del Overview, §3.6) y correr `.venv/Scripts/python manage.py makemigrations budget -n budgetmonth_opening_balance`. **No** `migrate`.
- [ ] **Step 4:** Run el test → PASS.
- [ ] **Step 5: Commit** `git add apps/budget/models/months.py apps/budget/migrations/0012_* tests/budget/test_models.py` — "El mes guarda un saldo inicial opcional".

---

### Task 2: Forecast, Real y Expenses

**Files:**
- Create: `apps/budget/services_overview.py`
- Modify: `apps/budget/views_month.py` (mover `totales` y `_real_contra_planeado` al servicio; `mes` los importa)
- Test: `tests/budget/test_services_overview.py`

**Interfaces:**
- Produces (en `services_overview`):
  - `totales(ingresos, egresos, ingresos_real, egresos_real) -> dict` — movida tal cual desde `views_month` (mismas claves: `ingresos, egresos, sobrante, ingresos_real, egresos_real, sobrante_real`).
  - `real_contra_planeado(lineas, transacciones) -> dict[str, dict]` — movida tal cual desde `views_month._real_contra_planeado` (claves por kind: `planeado, real, porcentaje`).
  - `lineas_del_ambito(mes, ambito, membresia) -> list[BudgetLine]` — `acotar_por_dueno(mes.lineas...)` con `select_related("category", "source_income", "source_expense_rule")`, `annotate(pagado_total=Sum("transacciones__amount"))`, `order_by("due_date", "pk")`. La misma consulta que `views_month.mes`; que `mes` la use también.
  - `transacciones_del_ambito(mes, ambito, membresia) -> list[Transaction]` — `acotar(mes.transacciones.select_related("category", "budget_line"), ...)`.
  - `forecast_hogar(hogar, totales_dict) -> dict` con claves `ingresos, egresos, sobrante, ahorro, mesada, sin_asignar` (Decimal). Reparto con `motor_cascade.repartir(totales_dict["sobrante"], services._reglas_del_motor(hogar))` si sobrante > 0, si no todo 0. `ahorro` = asignaciones con `miembro_id is None`; `mesada` = suma de las de miembro; `sin_asignar` = sobrante − asignado (≥ 0).
  - `forecast_personal(hogar, mes, membresia, totales_dict) -> dict` con claves `ingresos, egresos, mesada, arrastre, ajuste, disponible, queda`. `totales_dict` es el del ámbito personal. `mesada` = la parte de `membresia.pk` en el reparto del **sobrante del hogar** (calcularlo con `totales` sobre las líneas del ámbito household); `arrastre`/`ajuste` = `carried_in`/`adjustment` de `AllowanceLedger.objects.for_household(hogar).filter(member=membresia, budget_month=mes).first()` o 0; `disponible = mesada + arrastre + ajuste`; `queda = disponible − services.gasto_personal_del_mes(membresia, mes)`.
  - `expenses(transacciones) -> dict` con claves `budget, one_off` (Decimal): solo gastos (`t.category.kind == EXPENSE`); `one_off` si `t.budget_line_id is None` o `t.budget_line.is_exceptional`.

- [ ] **Step 1: Write the failing tests** (hogar con `crear_hogar`, mes del calendario fijo `2026-10`, líneas y transacciones por factory):

```python
def test_forecast_hogar_reparte_el_sobrante_como_plan_the_month(...):
    # ingresos 5000, gastos 3500 (incluye una one-off de 500); reglas: meta FIXED 500, mesada REMAINDER
    f = services_overview.forecast_hogar(hogar, t)
    assert (f["ingresos"], f["egresos"]) == (Decimal("5000.00"), Decimal("3500.00"))
    assert f["ahorro"] == Decimal("500.00")
    assert f["mesada"] == Decimal("1000.00")
    assert f["sin_asignar"] == Decimal("0.00")

def test_forecast_hogar_sin_sobrante_no_reparte(...):
    # gastos > ingresos
    assert f["ahorro"] == f["mesada"] == f["sin_asignar"] == Decimal("0.00")

def test_forecast_hogar_deja_sin_asignar_lo_que_ninguna_regla_agota(...):
    # sobrante 1500, una sola regla meta FIXED 500
    assert f["sin_asignar"] == Decimal("1000.00")

def test_expenses_separa_budget_de_one_off(...):
    # 300 contra línea de regla, 200 contra línea is_exceptional, 50 sin línea, un ingreso de 1000
    assert services_overview.expenses(txs) == {"budget": Decimal("300.00"), "one_off": Decimal("250.00")}

def test_forecast_personal_mesada_arrastre_y_lo_que_queda(...):
    # dos miembros, regla mesada REMAINDER sobre sobrante hogar 1000 -> 500 c/u;
    # ledger del miembro con carried_in 40, adjustment -10; gasto personal 120
    assert f["mesada"] == Decimal("500.00")
    assert f["disponible"] == Decimal("530.00")
    assert f["queda"] == Decimal("410.00")

def test_forecast_personal_sin_libro_no_lo_crea(...):
    f = services_overview.forecast_personal(hogar, mes, membresia, t)
    assert (f["arrastre"], f["ajuste"]) == (Decimal("0.00"), Decimal("0.00"))
    assert not AllowanceLedger.objects.for_household(hogar).exists()
```

- [ ] **Step 2:** Run `... pytest tests/budget/test_services_overview.py` → FAIL (módulo inexistente).
- [ ] **Step 3:** Implementar en `services_overview.py`; mover `totales`/`_real_contra_planeado` (renombrada `real_contra_planeado`) y hacer que `views_month.mes` use `lineas_del_ambito`, `transacciones_del_ambito` (añadiendo su `annotate(pagos_en_su_linea=...)` y orden en la vista, como hoy), `totales` y `real_contra_planeado` del servicio. `grep -rn "_real_contra_planeado\|views_month.totales" apps tests` para no dejar referencias.
- [ ] **Step 4:** Run `tests/budget/test_services_overview.py tests/budget/test_cash_float.py tests/budget/test_views.py tests/test_presupuesto_consultas.py` → PASS (This month sigue igual, mismo tope de consultas).
- [ ] **Step 5: Commit** — "Overview: forecast, real y expenses en un servicio compartido con This month".

---

### Task 3: Desvíos por categoría

**Files:**
- Modify: `apps/budget/services_overview.py`
- Test: `tests/budget/test_services_overview.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Desvio: categoria: Category; planeado: Decimal; real: Decimal` con `@property diferencia -> Decimal` (`real − planeado`) y `@property exceso -> bool` (`diferencia > 0`).
  - `desvios(lineas, transacciones, hoy: date) -> list[Desvio]`.
- Regla (§3.4): solo líneas de gasto **no** excepcionales, agrupadas por `category_id`; `real` = transacciones de gasto con `budget_line_id` en esas líneas. Una categoría "terminada" si **todas** sus líneas cumplen `pagado >= planned_amount` o `due_date is not None and due_date < hoy`. Incluir si `diferencia > 0`, o si `diferencia < 0` y terminada. Orden: `abs(diferencia)` desc, desempate por `categoria.etiqueta().casefold()`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_un_exceso_aparece_a_mitad_de_mes(...):      # Fuel plan 100, gastado 120, línea sin vencer
    [d] = services_overview.desvios(lineas, txs, hoy=date(2026, 10, 10))
    assert (d.diferencia, d.exceso) == (Decimal("20.00"), True)

def test_un_ahorro_no_aparece_si_la_categoria_sigue_abierta(...):  # plan 100, gastado 30, due 2026-10-28
    assert services_overview.desvios(lineas, txs, hoy=date(2026, 10, 10)) == []

def test_un_ahorro_aparece_cuando_la_linea_vencio(...):  # due 2026-10-05, gastado 80
    [d] = services_overview.desvios(lineas, txs, hoy=date(2026, 10, 10))
    assert d.diferencia == Decimal("-20.00")

def test_una_linea_sin_vencimiento_solo_termina_pagada(...):  # due None, gastado 80 de 100
    assert services_overview.desvios(lineas, txs, hoy=date(2026, 10, 31)) == []

def test_las_one_off_y_lo_cuadrado_no_desvian(...):  # línea is_exceptional; categoría con real == plan
    assert services_overview.desvios(lineas, txs, hoy=date(2026, 10, 31)) == []

def test_los_desvios_van_por_tamano(...):  # +20, -50 (terminada), +5
    assert [d.diferencia for d in ds] == [Decimal("-50.00"), Decimal("20.00"), Decimal("5.00")]
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar. **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** — "Overview: desvios por categoria, excesos siempre y ahorros al terminar".

---

### Task 4: Alerta de Cash Float y sugerencia de saldo inicial

**Files:**
- Modify: `apps/budget/services_overview.py`
- Test: `tests/budget/test_services_overview.py`

**Interfaces:**
- Consumes: `lineas_del_ambito` (household), `totales`, `BudgetMonth.opening_balance`, `services.proyectar`, `services.mes_siguiente`, `services._arrastre_previo`.
- Produces:
  - `alerta_cash_float(hogar, mes, lineas, real_del_mes: Decimal, hoy: date) -> dict` con claves:
    `saldo_inicial` (Decimal | None), `real_del_mes`, `en_mano` (= `(saldo_inicial or 0) + real_del_mes`), `proximo_ingreso` (date | None), `pendiente`, `margen` (= `en_mano − pendiente`), `cubierto` (bool, `margen >= 0`), `sin_ingreso` (bool), `falta_saldo` (bool, `saldo_inicial is None`).
  - `sugerencia_saldo_inicial(mes) -> Decimal | None` — `services._arrastre_previo(mes)` si existe un `MonthlyClose` anterior, si no `None`. (`_arrastre_previo` devuelve 0 sin cierre: distinguir con una consulta `exists()` o leyendo el cierre directamente.)
- Algoritmo (§3.5):
  1. Próximo ingreso del mes: entre `lineas` de ingreso con `due_date >= hoy` y `pagado < planned_amount`, la de `due_date` mínima.
  2. Si no hay: mes siguiente **sin escribir**. `anio, num = services.mes_siguiente(mes.year, mes.month)`; si existe su `BudgetMonth` **con** líneas, usar sus líneas con `scope=HOUSEHOLD` (`(kind, due_date, planned_amount)`); si no, `services.proyectar(hogar, anio, num)` filtrando a reglas del hogar (`IncomeSource`/`ExpenseRule` con `scope=HOUSEHOLD`, por `origen`/`origen_id`) → `(kind, fecha, importe)`. Próximo ingreso = fecha mínima de ingreso.
  3. `pendiente` = Σ `restante` de las líneas de gasto de `lineas` con `due_date is None` o (`proximo` y `due_date < proximo`); sin próximo ingreso, todas las de gasto. Si el próximo ingreso es del mes siguiente, sumar además el importe completo de los gastos del mes siguiente con fecha `< proximo`.

- [ ] **Step 1: Write the failing tests** (hogar con presupuesto, mes 2026-10, `hoy=date(2026, 10, 10)`):

```python
def test_cubierto_hasta_el_proximo_ingreso(...):
    # saldo inicial 1000; real del mes +200; ingreso pendiente due 10-15; gastos pendientes 300 due 10-12 y 900 due 10-20
    a = services_overview.alerta_cash_float(hogar, mes, lineas, Decimal("200.00"), hoy)
    assert a["proximo_ingreso"] == date(2026, 10, 15)
    assert (a["en_mano"], a["pendiente"], a["margen"], a["cubierto"]) == (
        Decimal("1200.00"), Decimal("300.00"), Decimal("900.00"), True)

def test_no_cubierto(...):                       # saldo 100, real 0, pendiente 300 antes del ingreso
    assert a["cubierto"] is False and a["margen"] == Decimal("-200.00")

def test_un_gasto_del_mismo_dia_que_el_ingreso_lo_cubre_el_ingreso(...):  # gasto due 10-15, ingreso due 10-15
    assert a["pendiente"] == Decimal("0.00")

def test_los_gastos_sin_vencimiento_siempre_cuentan(...):
    assert a["pendiente"] == Decimal("150.00")

def test_proximo_ingreso_en_el_mes_siguiente_suma_lo_que_vence_antes(...):
    # sin ingresos pendientes en octubre; IncomeSource del hogar día 15; ExpenseRule del hogar día 1 de 1800;
    # una ExpenseRule PERSONAL día 2 que no cuenta
    assert a["proximo_ingreso"] == date(2026, 11, 15)
    assert a["pendiente"] == restante_octubre + Decimal("1800.00")
    assert not BudgetMonth.objects.for_household(hogar).filter(year=2026, month=11).exists()

def test_mes_siguiente_vacio_se_proyecta_sin_escribir(...):
    # BudgetMonth 2026-11 existente y SIN líneas
    a = services_overview.alerta_cash_float(...)
    assert a["proximo_ingreso"] == date(2026, 11, 15)
    assert not BudgetLine.objects.filter(budget_month=noviembre).exists()

def test_sin_ingresos_planificados(...):
    assert a["sin_ingreso"] is True and a["proximo_ingreso"] is None

def test_sin_saldo_inicial_lo_pide(...):
    assert a["falta_saldo"] is True and a["saldo_inicial"] is None and a["en_mano"] == real

def test_la_sugerencia_es_el_arrastre_del_ultimo_cierre(...):   # MonthlyCloseFactory de septiembre con arrastre 640
    assert services_overview.sugerencia_saldo_inicial(octubre) == Decimal("640.00")

def test_sin_cierre_previo_no_hay_sugerencia(...):
    assert services_overview.sugerencia_saldo_inicial(octubre) is None
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar. **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** — "Overview: alerta de cash float hasta el proximo ingreso, con saldo inicial".

---

### Task 5: Vista y plantilla del Overview

**Files:**
- Create: `apps/budget/views_overview.py`, `templates/budget/overview.html`, `templates/budget/_fragmentos/overview_alerta.html`
- Modify: `apps/budget/views_summary.py` (quitar `overview` y la frase del docstring sobre él), `apps/budget/urls.py:73` (apuntar a `views_overview.overview`; comentario actualizado), `apps/budget/services_overview.py`, `static/css/modules.css`
- Test: `tests/budget/test_overview_vistas.py`; modificar `tests/budget/test_views.py:597-608`; `tests/test_presupuesto_consultas.py`

**Interfaces:**
- Consumes: todo lo de Tasks 2-4; `services.obtener_mes`, `services.ProyeccionDeMes`; `requiere_permiso`, `membresia_actual`, `validar`.
- Produces:
  - `services_overview.hay_presupuesto(hogar, mes, hoy: date) -> bool` — `IncomeSource` o `ExpenseRule` vigentes (`effective_to` nulo o ≥ `hoy`) **o** el mes tiene líneas (para una `ProyeccionDeMes`, `bool(mes.lineas)`).
  - `views_overview.overview(request, hogar, ambito)` con `@requiere_permiso("can_view_budget")`. Contexto: `ambito`, `primer_dia` (date del mes), `sin_presupuesto` (bool), `puede_editar` (`membresia.can_edit_budget`), `es_proyeccion`, `cerrado` (bool), `forecast`, `real` (el dict de `totales`), `expenses`, `desvios`, `alerta` (solo household, ni proyección ni cerrado; si no, `None`), `sugerencia_saldo` (solo si `alerta` y `alerta["falta_saldo"]`).
  - Proyección: `forecast` desde `mes.total_ingresos/total_egresos/sobrante` (household; reparto con `forecast_hogar`), Real/Expenses en 0, `desvios=[]`, `alerta=None`. En Personal y proyección: forecast en 0.
  - Mes cerrado: aviso "%(month)s is closed." con enlace a `budget:planificar_mes` del mes siguiente (`paso=1`) si `puede_editar`.
  - Sin presupuesto: solo la tarjeta de invitación (título "Let's set up your budget", texto, botón "Set up the budget" a `budget:configurar` si `puede_editar`; si no, "Ask the household owner to set up the budget."). En Personal decide el presupuesto del hogar.
- Plantilla: `{% extends "base.html" %}`, tarjetas `section.card` en una rejilla `overview` (clase nueva en `modules.css`: 2 columnas ≥ 900 px, una en móvil, gap 20px). Orden: alerta (incluida desde `overview_alerta.html`, `id="overview-alerta"`), Forecast, Real ("$X of $Y"), Desvíos (fila por desvío "+$20 over plan"/"−$20 under plan", enlace a `budget:mes` con `?orden=categoria`; vacío: "Everything is on plan so far."), Expenses ("Budget"/"One-off"). Forecast en Personal: Allowance, Carried over/Adjustment si ≠ 0, "Left to spend". Forecast hogar: "Unassigned" solo si > 0; "Nothing left to split" si sobrante ≤ 0. Alerta: "Covered: %(amount)s to spare until %(date)s" / "Short %(amount)s for what's due before %(date)s" / "No upcoming income planned" (+ enlace a `budget:configurar`); línea "In hand: %(total)s (opening %(opening)s + this month %(month)s)"; con `falta_saldo`, "Add this month's opening balance for an accurate check" (el formulario llega en Task 6). Enlace "See the Cash Float" a `budget:mes` household. Reutilizar clases existentes (`cifra__etiqueta`, `cifra__valor`, `cifra__valor--mal`, `importe--mal`, `importe--ingreso`, `numero`, `campo__ayuda`, `btn btn--primary`) antes que crear nuevas.

- [ ] **Step 1: Write the failing tests:**

```python
def test_el_overview_del_hogar_cuadra_con_this_month(client, mes_con_dinero):
    # reutiliza la fixture de tests/budget/test_cash_float.py
    r = client.get(reverse("budget:overview", args=["household"]))
    m = client.get(reverse("budget:mes", args=["household"]))
    assert r.status_code == 200
    assert r.context["real"] == m.context["totales"]
    assert r.context["forecast"]["ingresos"] == m.context["totales"]["ingresos"]

def test_sin_presupuesto_invita_a_crearlo(client, admin_con_hogar):  # hogar recién creado, sin reglas
    r = client.get(reverse("budget:overview", args=["household"]))
    assert r.context["sin_presupuesto"] is True
    assert reverse("budget:configurar") in r.content.decode()

def test_sin_presupuesto_y_sin_permiso_pide_al_dueno(client, admin_con_hogar):
    # miembro can_view_budget=True, can_edit_budget=False
    html = ...
    assert "Ask the household owner to set up the budget." in html
    assert reverse("budget:configurar") not in html

def test_personal_no_tiene_alerta_y_ensena_la_mesada(client, mes_con_dinero):
    r = client.get(reverse("budget:overview", args=["personal"]))
    assert r.context["alerta"] is None and "mesada" in r.context["forecast"]

def test_personal_no_cuenta_lo_de_otro_miembro(client, mes_con_dinero):
    # Diana registra un gasto personal de 999 y tiene una línea personal de 500
    r = client.get(reverse("budget:overview", args=["personal"]))   # sesión de Otto
    assert r.context["real"]["egresos_real"] == Decimal("0.00")
    assert r.context["forecast"]["egresos"] == Decimal("0.00")
    h = client.get(reverse("budget:overview", args=["household"]))
    assert Decimal("999.00") not in (h.context["real"]["egresos_real"],)

def test_un_mes_cerrado_se_ensena_sin_alerta(client, mes_con_dinero):
    # cerrar el mes en curso con status=closed
    r = ...
    assert r.context["cerrado"] is True and r.context["alerta"] is None

def test_un_hogar_sin_escritura_ve_la_proyeccion(client, admin_con_hogar):
    # hogar expirado (ver cómo lo hacen tests/test_suscripcion.py) con una IncomeSource
    r = ...
    assert r.status_code == 200 and r.context["es_proyeccion"] is True

def test_un_ambito_inventado_es_404(client, admin_con_hogar):
    assert client.get("/budget/inventado/").status_code == 404
```

y en `tests/budget/test_views.py` reemplazar `test_la_raiz_del_ambito_redirige_a_this_month` por `test_la_raiz_del_ambito_es_el_overview` (200 en los dos ámbitos, plantilla `budget/overview.html`; Summary y Balance siguen en 200). En `tests/test_presupuesto_consultas.py` añadir `CONSULTAS_OVERVIEW` y `test_el_overview_no_hace_una_consulta_por_transaccion` con la fixture `hogar_con_movimiento`: medir una vez, fijar el número con un comentario que lo justifique como los vecinos.

- [ ] **Step 2:** Run `tests/budget/test_overview_vistas.py` → FAIL.
- [ ] **Step 3:** Implementar vista, plantillas, URL y CSS.
- [ ] **Step 4:** Run `tests/budget/test_overview_vistas.py tests/budget/test_views.py tests/test_presupuesto_consultas.py` → PASS.
- [ ] **Step 5: Commit** — "Overview: la raiz del ambito vuelve a ser el mes de un vistazo".

---

### Task 6: Guardar el saldo inicial (htmx)

**Files:**
- Modify: `apps/budget/forms.py`, `apps/budget/views_overview.py`, `apps/budget/urls.py` (bloque sin ámbito), `templates/budget/_fragmentos/overview_alerta.html`
- Test: `tests/budget/test_overview_vistas.py`

**Interfaces:**
- Produces:
  - `forms.SaldoInicialForm(forms.Form)` con `opening_balance = MoneyField` de formulario (usar el campo de formulario que ya usen otros forms de importes en `forms.py`), requerido, admite 0 y negativos.
  - `views_overview.saldo_inicial(request, hogar)` — `@require_POST`, `@requiere_permiso("can_edit_budget")`, ruta `path("opening-balance/", ..., name="saldo_inicial")`. Mes en curso vía `services.obtener_mes`; si es `ProyeccionDeMes` → 404; si `esta_cerrado` → error de formulario "This month is already closed." (BudgetMonth **no** hereda la guarda `EscrituraAcotadaAlMes`: comprobarlo a mano). Guarda con `save(update_fields=["opening_balance"])`. Con `HX-Request` devuelve `overview_alerta.html` recalculado; sin él, redirige a `budget:overview household`.
- Plantilla: con `alerta.falta_saldo` y `puede_editar`, formulario `hx-post` a `budget:saldo_inicial`, `hx-target="#overview-alerta"`, `hx-swap="outerHTML"`, campo prellenado con `sugerencia_saldo` si existe y la ayuda "Suggested from last month's close." Con saldo ya guardado y `puede_editar`, un enlace/botón "Edit" que muestra el mismo formulario (Alpine `x-data`, patrón existente en la app). Token CSRF: comprobar cómo lo mandan los otros `hx-post` (p. ej. `wizards.reordenar_reglas` / commit `92372e0`).

- [ ] **Step 1: Write the failing tests:**

```python
def test_guardar_el_saldo_inicial_recalcula_la_alerta(client, mes_con_dinero):
    r = client.post(reverse("budget:saldo_inicial"), {"opening_balance": "1500.00"}, HTTP_HX_REQUEST="true")
    mes.refresh_from_db()
    assert mes.opening_balance == Decimal("1500.00")
    assert r.context["alerta"]["en_mano"] == Decimal("1500.00") + real_del_mes

def test_la_sugerencia_no_se_guarda_sola(client, mes_con_dinero):   # con MonthlyClose previo
    r = client.get(reverse("budget:overview", args=["household"]))
    assert r.context["sugerencia_saldo"] == Decimal("640.00")
    mes.refresh_from_db(); assert mes.opening_balance is None

def test_sin_can_edit_budget_no_hay_campo_y_el_post_es_403(client, mes_con_dinero):
    # miembro can_view_budget=True, can_edit_budget=False
    assert 'name="opening_balance"' not in client.get(...overview...).content.decode()
    assert client.post(reverse("budget:saldo_inicial"), {"opening_balance": "1"}).status_code == 403

def test_en_un_mes_cerrado_no_se_guarda(client, mes_con_dinero):
    # mes en curso cerrado
    client.post(reverse("budget:saldo_inicial"), {"opening_balance": "1"})
    mes.refresh_from_db(); assert mes.opening_balance is None

def test_el_saldo_inicial_no_toca_la_tarjeta_cash_float(client, mes_con_dinero):
    antes = client.get(reverse("budget:mes", args=["household"])).context["cash_float"]
    client.post(reverse("budget:saldo_inicial"), {"opening_balance": "5000.00"})
    assert client.get(reverse("budget:mes", args=["household"])).context["cash_float"] == antes
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar. **Step 4:** Run `tests/budget/test_overview_vistas.py` → PASS.
- [ ] **Step 5: Commit** — "Overview: el saldo inicial se escribe en la propia alerta".

---

### Task 7: Navegación, home, service worker, francés y verificación

**Files:**
- Modify: `apps/core/context_processors.py` (`_pantallas`, `_encender`), `templates/_nav_icono.html`, `apps/accounts/views.py:121-135`, `templates/sw.js:21`, `tests/test_pwa.py`, `tests/test_navegacion.py`, `locale/fr/LC_MESSAGES/django.po` (+ `.mo` compilado)
- Test: `tests/test_navegacion.py`, `tests/test_accounts.py` (o donde se pruebe `inicio`; buscar con grep)

**Interfaces:**
- Pestaña nueva **primera** en `_pantallas`: `{"nombre": "overview", "vista": "budget:overview", "etiqueta": _("Overview"), "icono": "resumen", "exacta": True}` bajo `can_view_budget`. `_encender`: una pestaña con `exacta` solo se enciende si `ruta == p["url"]`. Quitar los comentarios que dicen que el Overview se quitó.
- `_nav_icono.html`: rama `{% elif icono == "resumen" %}` con los cuatro `rect` del icono anterior (en `git show 4b77261^:templates/_nav_icono.html`).
- `inicio`: si hay membresía con `can_view_budget`, `redirect("budget:overview", "household")`; si no, la página actual.
- `sw.js`: `VERSION = "wealthome-v24"`; actualizar las referencias `paginas-wealthome-vN` en `tests/test_pwa.py`.

- [ ] **Step 1: Update/write the failing tests:**
  - `ESPERADO_PANTALLAS`: `ADMIN: ["overview", "mes", "metas", "summary", "balance"]`, `SOLO_VER: ["overview", "mes", "metas"]`, `ADOLESCENTE: []`; quitar el comentario "Overview ya no existe".
  - `conocidos` en `test_cada_pestana_trae_su_icono` gana `"resumen"`.
  - `test_el_overview_solo_se_enciende_en_su_url`: en `budget:overview household` la activa es `overview`; en `budget:planificar household` es `mes`; y a nivel de unidad, `_encender(_pantallas(membresia_admin, "household"), "/budget/household/sin-pestana/")` no deja `overview` activa.
  - `test_el_conmutador_conserva_el_overview`: desde `budget:overview household`, `ambitos["personal"]["url"] == reverse("budget:overview", args=["personal"])`.
  - `test_el_login_aterriza_en_el_overview`: GET `accounts:inicio` con admin → 302 a `budget:overview household`; con perfil ADOLESCENTE (sin `can_view_budget`) → 200 la bienvenida.
- [ ] **Step 2:** Run `tests/test_navegacion.py tests/test_pwa.py` y el test de inicio → FAIL.
- [ ] **Step 3:** Implementar navegación, icono, `inicio`, SW.
- [ ] **Step 4:** Traducciones: añadir al `.po` todas las cadenas nuevas de Tasks 5-7, compilar con pybabel; run `tests/test_catalogo_exhaustivo.py tests/test_traducciones.py tests/test_i18n.py` → PASS.
- [ ] **Step 5:** Run `tests/test_navegacion.py tests/test_pwa.py tests/test_accounts.py tests/budget/` → PASS.
- [ ] **Step 6: Verificación visual** (Playwright MCP; servidor local **sólo** si el usuario confirma que puede apuntar a la base de pruebas o acepta producción — preguntar antes; si no, saltar y decirlo): Overview household y personal a 360, 412 y 1280 px, tema claro y `nocturno`; la barra inferior de Personal (6 pestañas) sin scroll horizontal a 360 px; alerta en los estados cubierto / no cubierto / falta saldo.
- [ ] **Step 7: Commit** — "Overview: primera pestana y pantalla de entrada; service worker v24".

---

### Task 8: Suite completa

- [ ] **Step 1:** Lanzar la suite completa en segundo plano: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" > <scratchpad>/suite.txt 2>&1` (≈35-40 min) y esperar con Monitor/`until grep -qE 'passed|failed'`.
- [ ] **Step 2:** Esperado: todo verde salvo el fallo CSS previo conocido (anotado en memoria del 2026-10-20); cualquier otro fallo se investiga (superpowers:systematic-debugging) antes de seguir.
- [ ] **Step 3:** Recordatorio para el despliegue (no hacerlo sin el usuario): la migración `0012` se aplica en el VPS como paso del despliegue.

# Planificado y pendiente Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que lo planificado excluya lo no planeado, que lo pendiente nunca se compense, que las tarjetas muestren pagado/pendiente/esperado/desvío, que la alerta cuente todo lo pendiente, que los desvíos sigan la nueva regla y que el cierre no cuente lo real varias veces.

**Architecture:** Una marca nueva `BudgetLine.no_planeada` decide qué es planificado; cada suma de `planned_amount` del código la excluye. Las cifras nuevas (pendiente, esperado, desvío) se calculan en `services_overview.totales` / `real_contra_planeado`, que ya comparten This month y el Overview. `cerrar_mes` agrega por (categoría, tipo).

**Tech Stack:** Django 5.1, htmx, pytest + factory_boy (base de pruebas remota), catálogos `.po` a mano.

**Spec:** `docs/superpowers/specs/2026-10-24-wealthome-overview-design.md` — **§9** (las reglas nuevas; sustituye a §3.4 y §3.5 donde chocan).

## Global Constraints

- Correr pruebas: `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador" <ruta>`. Nunca dos pytest a la vez. Solo los archivos de la tarea; la suite completa la corre el controlador.
- **No correr `manage.py migrate` ni `runserver`: el `.env` local apunta a producción.** `makemigrations` sí.
- "Planificado" = líneas con `no_planeada=False` (reglas + partidas de Plan the month). "Pendiente" = Σ `restante` de líneas planificadas, por línea, sin compensar. "Esperado" = real + pendiente. "Desvío" = esperado − planificado.
- Lo personal sigue fuera de lo del hogar (`acotar`, `acotar_por_dueno`, `scope=HOUSEHOLD` donde ya estaba).
- Textos visibles con `{% translate %}`/`_()` y su francés en `locale/fr/LC_MESSAGES/django.po`, compilado con `.venv/Scripts/pybabel.exe compile -d locale -D django --statistics`. Un `_()` por línea literal.
- Si cambia CSS: `VERSION` de `templates/sw.js` a `wealthome-v26` y las referencias `paginas-wealthome-vN` de `tests/test_pwa.py`. No añadir selectores `data-theme` en components/modules/base.css.
- Commits en la rama `fix/planificado-y-pendiente`, mensajes en español terminados con línea en blanco + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Registro no planeado corregido o pospuesto:** al editarlo sigue `no_planeada=True`; al ligarlo después a una línea del plan, su partida se borra (comportamiento actual). Test en Task 1.
2. **Partida de Plan the month pagada exacta en su fecha** (indistinguible por la heurística): la migración la marcaría no planeada — aceptado para datos viejos; lo nuevo lo marca `_ligar_al_plan`, nunca la heurística. Test en Task 1 (`linea_nueva` crea `no_planeada=False`).
3. **Cierre con varias líneas por categoría y gasto real sin línea planificada en otra categoría:** egresos reales = Σ movimientos exactamente. Test en Task 2.
4. **Mes sin nada planificado** (todo no planeado): planificado 0, donas sin división por cero, desvío = esperado. Test en Task 3.
5. **Mes cerrado en el Overview:** desvíos muestran también lo gastado de menos. Test en Task 4.

---

### Task 1: La marca `no_planeada`

**Files:**
- Modify: `apps/budget/models/months.py` (campo en `BudgetLine`), `apps/budget/views_month.py::_ligar_al_plan`
- Create: `apps/budget/migrations/0013_budgetline_no_planeada.py` (AddField + RunPython)
- Test: `tests/budget/test_registrar_contra_el_plan.py` (o el archivo donde se pruebe hoy el registro "not planned"; buscar con grep `is_exceptional`), `tests/budget/test_models.py`

**Interfaces:**
- Produces: `BudgetLine.no_planeada = models.BooleanField(_("not planned"), default=False)` con comentario (§9.1).
- `_ligar_al_plan`: al crear la partida de un registro suelto pone `no_planeada=True`; al actualizar la propia (`puntual`) la deja en `True`.
- Migración: `marcar_no_planeadas(apps, schema_editor)` — sobre `apps.get_model("budget", "BudgetLine")._base_manager` (el manager por defecto de los modelos con hogar revienta sin hogar): marca `True` las líneas `is_exceptional=True` con **exactamente un** movimiento cuyo `amount == planned_amount` y `date == due_date`. Reverso: no-op. Una función a nivel de módulo para poder probarla.

- [ ] **Step 1: Failing tests**

```python
def test_un_registro_no_planeado_crea_una_partida_no_planeada(...):
    # POST a budget:registrar sin línea, con categoría y nombre (ver tests existentes del registro suelto)
    assert tx.budget_line.is_exceptional and tx.budget_line.no_planeada

def test_corregir_un_registro_no_planeado_lo_deja_no_planeado(...):
    # registro_editar cambiando el importe
    assert tx.budget_line.no_planeada and tx.budget_line.planned_amount == nuevo_importe

def test_una_partida_de_plan_the_month_es_planificada(...):
    # POST a budget:linea_nueva_del_mes (o linea_nueva)
    assert not linea.no_planeada

def test_la_migracion_marca_las_puntuales_nacidas_de_un_registro(...):
    # nacida: excepcional, 1 pago, mismo importe y fecha -> True
    # planificada pagada de más (60 vs 67) -> False; sin pagos -> False; dos pagos -> False; línea de regla -> False
    marcar_no_planeadas(django_apps, None)   # from django.apps import apps as django_apps
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar; `makemigrations budget -n budgetline_no_planeada` y añadir el `RunPython` a mano. **Step 4:** Run → PASS (más `tests/budget/test_corregir_registro.py tests/budget/test_posponer_vistas.py`).
- [ ] **Step 5: Commit** — "Las partidas de un registro no planeado llevan su marca".

---

### Task 2: Una sola definición de planificado, y el cierre sin duplicar lo real

**Files:**
- Modify: `apps/budget/services.py` (`totales_del_mes`, `cerrar_mes`), `apps/budget/services_overview.py` (`real_contra_planeado`), `apps/budget/views_month.py` (`_bloques_del_plan`), `apps/budget/services_summary.py` (consulta de planificado por categoría, ~línea 66), `apps/budget/wizards.py` (`planificar`: las líneas de los pasos 1-2 excluyen `no_planeada`)
- Test: `tests/budget/test_month_cycle.py` o `tests/budget/test_services.py` (cierre), `tests/budget/test_services_overview.py`, `tests/budget/test_planificar_mes.py`, `tests/budget/test_services_summary.py`

**Interfaces:**
- `totales_del_mes(mes)`: suma solo `no_planeada=False`.
- `cerrar_mes(mes)`: un `Renglon` por (categoría, tipo) del hogar: `presupuestado` = Σ `planned_amount` de las líneas planificadas de esa clave (0 si solo hay no planeadas o ninguna), `real` = el de `_reales_por_categoria` **una vez**. Toda clave con real o con planificado sale exactamente una vez.
- `real_contra_planeado(lineas, transacciones)`: `planeado` solo de líneas `no_planeada=False`; `real` sin cambios (todos los movimientos).
- `_bloques_del_plan`: las líneas `no_planeada` no aparecen en la tarjeta Planned ni en sus totales.

- [ ] **Step 1: Failing tests**

```python
def test_el_cierre_cuenta_lo_real_una_sola_vez_con_varias_lineas_por_categoria(...):
    # Fuel con 2 líneas de 100 y 200 gastados; otra categoría con 50 gastados sin línea
    cierre = services.cerrar_mes(mes)
    assert cierre.egresos_reales == Decimal("250.00")
    assert cierre.egresos_presupuestados == Decimal("200.00")
    assert Decimal(cierre.varianza_por_categoria[str(fuel.pk)]) == Decimal("0.00")

def test_el_cierre_no_presupuesta_lo_no_planeado(...):
    # línea regla 100 + partida no_planeada 40 (pagada 40) misma categoría
    assert cierre.egresos_presupuestados == Decimal("100.00") and cierre.egresos_reales == Decimal("140.00")

def test_totales_del_mes_excluye_lo_no_planeado(...):
    assert services.totales_del_mes(mes).egresos == Decimal("100.00")

def test_real_contra_planeado_excluye_lo_no_planeado_del_plan(...):
    d = services_overview.real_contra_planeado(lineas, txs)
    assert d["expense"]["planeado"] == Decimal("100.00") and d["expense"]["real"] == Decimal("140.00")

def test_la_tarjeta_planned_no_lista_lo_no_planeado(client, ...):
    # GET budget:mes household; la partida no planeada no está en ningún bloque de context["bloques"]

def test_plan_the_month_no_ofrece_lo_no_planeado(client, ...):
    # GET planificar_mes paso 2: la partida no planeada no es un campo del form

def test_summary_no_planifica_lo_no_planeado(...):
    # services_summary sobre un mes con partida no planeada: planificado de la categoría sin ella
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar. **Step 4:** Run los archivos tocados + `tests/budget/test_cash_float.py tests/budget/test_views.py tests/budget/engine/` → PASS.
- [ ] **Step 5: Commit** — "Lo no planeado no suma a lo planificado y el cierre cuenta lo real una vez".

---

### Task 3: Pendiente, esperado y desvío en las tarjetas; la alerta cuenta todo

**Files:**
- Modify: `apps/budget/services_overview.py` (`totales`, `real_contra_planeado`, `alerta_cash_float`), `apps/budget/views_month.py` y `apps/budget/views_overview.py` (pasar lo pendiente a `totales`), `templates/budget/_fragmentos/cifras.html`, `templates/budget/overview.html` (tarjeta Real), `locale/fr/LC_MESSAGES/django.po`
- Test: `tests/budget/test_services_overview.py`, `tests/budget/test_overview_vistas.py`, `tests/budget/test_views.py`

**Interfaces:**
- `real_contra_planeado` añade por kind `pendiente` = Σ `restante` de líneas planificadas de ese kind (las líneas llegan anotadas con `pagado_total`).
- `totales(ingresos, egresos, ingresos_real, egresos_real, ingresos_pendiente=CERO, egresos_pendiente=CERO)` añade: `ingresos_pendiente`, `egresos_pendiente`, `ingresos_esperado` (= real + pendiente), `egresos_esperado`, `ingresos_desvio` (= esperado − planificado), `egresos_desvio`. Claves existentes sin cambios. Todos los llamadores pasan lo pendiente de `real_contra_planeado`.
- Tarjetas Total Incomes / Total Expenses de `cifras.html` y la tarjeta Real del Overview: en grande lo pagado; debajo "Pending %(amount)s", "Expected %(amount)s", "%(planned)s planned" y "+%(amount)s over plan" / "−%(amount)s under plan" (nada si el desvío es 0). En gastos "over plan" va en rojo (`importe--mal`); en ingresos "over plan" en verde (`importe--ingreso`) y "under plan" en rojo.
- `alerta_cash_float`: `pendiente` = Σ `restante` de **todas** las líneas de gasto planificadas del hogar del mes (sin corte por fecha), más, si el próximo ingreso cae el mes siguiente, los gastos del mes siguiente con fecha `<` ese ingreso (como ahora). El texto "Short %(amount)s for what's due before %(date)s" pasa a "Short %(amount)s to cover what is still pending" y "Covered: …" a "Covered: %(amount)s to spare after paying what is pending"; con próximo ingreso conocido se mantiene la fecha en una línea aparte "Next income: %(date)s".

- [ ] **Step 1: Failing tests** — reproducir octubre en pequeño:

```python
def test_lo_pendiente_no_se_compensa_con_lo_pagado_de_mas(...):
    # línea A plan 100 pagada 150; línea B plan 100 pagada 40; partida no_planeada 30
    d = services_overview.real_contra_planeado(lineas, txs)
    t = services_overview.totales(d["income"]["planeado"], d["expense"]["planeado"], d["income"]["real"],
                                  d["expense"]["real"], d["income"]["pendiente"], d["expense"]["pendiente"])
    assert t["egresos"] == Decimal("200.00")
    assert t["egresos_real"] == Decimal("220.00")
    assert t["egresos_pendiente"] == Decimal("60.00")
    assert t["egresos_esperado"] == Decimal("280.00")
    assert t["egresos_desvio"] == Decimal("80.00")

def test_un_mes_sin_nada_planificado(...):
    assert t["egresos"] == Decimal("0.00") and t["egresos_desvio"] == t["egresos_esperado"]

def test_la_alerta_cuenta_todo_lo_pendiente(...):
    # gasto pendiente que vence después del próximo ingreso también cuenta
    assert a["pendiente"] == Decimal("...suma de todos los restante...")

def test_las_tarjetas_ensenan_pendiente_esperado_y_desvio(client, ...):
    # This month y Overview: "Pending", "Expected", "over plan" con los importes en el HTML
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar + francés. **Step 4:** Run `tests/budget/test_services_overview.py tests/budget/test_overview_vistas.py tests/budget/test_views.py tests/budget/test_cash_float.py tests/test_catalogo_exhaustivo.py tests/test_traducciones.py` → PASS.
- [ ] **Step 5: Commit** — "Las tarjetas ensenan pendiente, esperado y desvio; la alerta cuenta todo lo pendiente".

---

### Task 4: Desvíos con la regla nueva

**Files:**
- Modify: `apps/budget/services_overview.py` (`desvios`), `apps/budget/views_overview.py`
- Test: `tests/budget/test_services_overview.py`, `tests/budget/test_overview_vistas.py`

**Interfaces:**
- `desvios(lineas, transacciones, cerrado: bool) -> list[Desvio]` (sustituye el parámetro `hoy`). `Desvio(categoria, planeado, real)` se mantiene; `diferencia` es el desvío que se muestra.
  - Planificado de la categoría: Σ `planned_amount` de sus líneas de gasto `no_planeada=False` (reglas y partidas de Plan the month).
  - Gastado no planeado: movimientos de gasto con `budget_line` `no_planeada=True` o sin línea, por categoría.
  - Mes abierto: `real` del Desvio = planificado + Σ `max(0, pagado − planned)` de sus líneas planificadas + no planeado; se incluye si `diferencia > 0`.
  - Mes cerrado: `real` = todo lo gastado en la categoría; se incluye si `diferencia != 0`.
  - Una categoría sin líneas planificadas pero con gasto no planeado aparece con `planeado = 0`.
  - Orden por `abs(diferencia)` desc, desempate por etiqueta (como ahora).
- La vista pasa `cerrado=mes.esta_cerrado`.

- [ ] **Step 1: Failing tests** (sustituyen a los de la regla "terminada"):

```python
def test_con_el_mes_abierto_un_pago_parcial_no_es_ahorro(...):      # plan 100, pagado 40, vencida
    assert services_overview.desvios(lineas, txs, cerrado=False) == []

def test_con_el_mes_abierto_lo_pagado_de_mas_no_se_compensa(...):    # A 100/108 y B 110/50 misma categoría
    [d] = services_overview.desvios(lineas, txs, cerrado=False)
    assert d.diferencia == Decimal("8.00")

def test_lo_no_planeado_es_exceso_de_su_categoria(...):              # categoría sin líneas, 45.51 no planeado
    [d] = ...; assert (d.planeado, d.diferencia) == (Decimal("0.00"), Decimal("45.51"))

def test_una_partida_de_plan_the_month_cuenta_como_planificada(...): # Halloween 60 / 67
    [d] = ...; assert d.diferencia == Decimal("7.00")

def test_con_el_mes_cerrado_aparece_lo_gastado_de_menos(...):        # plan 100, pagado 80, cerrado
    [d] = services_overview.desvios(lineas, txs, cerrado=True)
    assert d.diferencia == Decimal("-20.00")
```

- [ ] **Step 2:** Run → FAIL. **Step 3:** Implementar; actualizar/quitar los tests de la regla vieja. **Step 4:** Run `tests/budget/test_services_overview.py tests/budget/test_overview_vistas.py` → PASS.
- [ ] **Step 5: Commit** — "Desvios: excesos linea a linea y lo no planeado; lo de menos al cerrar".

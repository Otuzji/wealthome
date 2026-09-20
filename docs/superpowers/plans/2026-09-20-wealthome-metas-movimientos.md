# Metas II: fondo abierto, retirar, transferir y ahorro en Balance — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un fondo sin objetivo, dinero que puede salir de una meta (retiro, transferencia), borrar solo con saldo cero (o archivar), y el ahorro visible en Balance.

**Architecture:** `GoalContribution` pasa a ser el movimiento de una meta (importe con signo, `origen` tipado, `note`, `counterpart` para transferencias). Todo lo nuevo de dominio va en `services_goals.py`; las vistas siguen en `views_goals.py`; Balance solo llama a `resumen_ahorro`. Una migración.

**Tech Stack:** Django 5 + htmx + Alpine, pytest + factory_boy, `.po` a mano, `msgfmt.py`.

**Spec:** `docs/superpowers/specs/2026-09-20-wealthome-metas-movimientos-design.md`

## Global Constraints

Las mismas del plan anterior (`2026-09-20-wealthome-metas.md`): pytest con `.venv/Scripts/python -m pytest -p no:cacheprovider -m "not navegador"`, nunca dos corridas a la vez, managers acotados, `.po` a mano + `msgfmt.py`, subir `sw.js` (a `v15`) y `test_pwa.py` al tocar CSS/JS, scripts en el scratchpad para ediciones largas, commits con `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

### Task 1: Modelo y motor — fondo abierto, movimientos con signo

**Files:** `apps/budget/engine/goals.py`, `apps/budget/models/goals.py`, `apps/budget/migrations/0010_*.py`, `tests/budget/engine/test_goals_engine.py`, `tests/budget/test_services_goals.py` (sección modelo).

- [ ] Tests motor: `derivar(OPEN_FUND, objetivo=None, acumulado=X, desde, aporte_mensual=200)` → `(200.00, None)`; sin aporte → `(0.00, None)`.
- [ ] Tests modelo: `Goal(open_fund, target_amount=None).full_clean()` pasa; `open_fund` con `target_amount` falla; `by_target_date` sin `target_amount` falla; `GoalContribution(origen="withdrawal", amount=+10).full_clean()` falla y con `-10` pasa; `manual` con `-10` falla; `alcanzada` de un fondo es `False`.
- [ ] Motor: `OPEN_FUND = "open_fund"` en `MODOS_DE_META`; rama en `derivar` ANTES del cálculo de `falta` (no hay objetivo).
- [ ] Modelo: choices, `null=True` en `target_amount`/`target_date`, `ARCHIVED`, `es_fondo`, `alcanzada`, `clean()` por modo; `GoalContribution.note`, `counterpart`, `ORIGEN_CHOICES` ampliado, `clean()` de signo. `makemigrations budget -n fondo_abierto_y_movimientos`.
- [ ] Verde, commit.

### Task 2: `services_goals` — retirar, transferir, quitar, recalcular sin bajar

**Files:** `apps/budget/services_goals.py`, `tests/budget/test_services_goals.py`.

- [ ] Tests: `retirar` escribe `-amount` y `note`; más que el saldo → `SaldoInsuficiente`; cero o negativo → `SaldoInsuficiente`; mes cerrado → `MesCerrado`; una `reached` sigue `reached`. `transferir`: dos filas enlazadas (`a.counterpart == b`, `b.counterpart == a`), saldos correctos, destino que se cubre pasa a `reached`, destino no activo → `ValueError`, misma meta → `ValueError`, más que el saldo → `SaldoInsuficiente`. `quitar`: saldo ≠ 0 → `SaldoPendiente`; saldo 0 con cascada → `"archived"` y `status == ARCHIVED`; sin cascada → `"deleted"`. `recalcular_estado(bajar=False)` no baja; un fondo nunca sube. `aportar` con `note`.
- [ ] Implementación: excepciones `SaldoInsuficiente(ValueError)`, `SaldoPendiente(ValueError)`; `saldo_de(meta)` = `meta.acumulado()`; `_movimiento(hogar, meta, amount, date, member, origen, note, counterpart=None)` común; `retirar`, `transferir` (atómica), `quitar`, `recalcular_estado(..., bajar=True)`.
- [ ] Verde, commit.

### Task 3: `resumen` con fondo y saldo; `resumen_ahorro`

**Files:** `apps/budget/services_goals.py`, `tests/budget/test_services_goals.py`.

- [ ] Tests `resumen`: fondo → `porcentaje is None`, `es_fondo`, `aporte == monthly_amount`, `fecha is None`; `saldo`, `puede_quitar`, `puede_sacar`, `tiene_cascada`; `aportes` con `(aporte, editable, borrable)`; `este_mes` suma solo entradas positivas.
- [ ] Tests `resumen_ahorro`: dos meses con cascada/manual/retiro → filas por mes con `saldo` acumulado; transferencia no aparece; meta archivada incluida en `por_meta`; ámbito personal solo las propias; sin movimientos → `filas == []`, `saldo_total == 0`.
- [ ] Implementación: `resumen` extendido; `resumen_ahorro(hogar, ambito, membresia)` agrega en Python sobre `GoalContribution.objects.for_household(hogar).filter(goal__in=metas_visibles).select_related("goal")` (una consulta), agrupando por `(date.year, date.month)`.
- [ ] Verde, commit.

### Task 4: Formularios, vistas y rutas

**Files:** `apps/budget/forms.py`, `apps/budget/views_goals.py`, `apps/budget/views_overview.py`, `apps/budget/urls.py`, `tests/budget/test_metas_vistas.py`, `tests/budget/test_aportar.py`.

- [ ] Tests: `GoalForm` con `open_fund` y sin objetivo guarda; `GoalForm` vacía `target_*` al pasar a `open_fund`; `retirar` por POST baja el saldo y vuelve a Goals; retirar de más → 200 con error; `transferir` por POST crea la pareja; `to_goal` no ofrece la propia ni las no activas; `meta_borrar` con saldo → mensaje y sigue; con saldo 0 y cascada → archivada y fuera de Goals; sin cascada → borrada; `aporte_borrar` de un `transfer_in` borra el `transfer_out` y recalcula; `aporte_borrar` de `withdrawal` permitido; `balance` lleva `ahorro` en el contexto; 403/404 como el resto.
- [ ] `GoalForm`: `x_data`/`x_show` por modo, `clean()` vacía campos ajenos al modo, `help_text` del modo abierto. `GoalContributionForm`: `note`. Nuevos `RetiroForm(forms.Form)` y `TransferenciaForm(forms.Form)` (con `household`, `membresia`, `meta`).
- [ ] Vistas `retirar`, `transferir`; `meta_borrar` por `quitar`; `aporte_borrar` ampliado; `metas` excluye `archived`; `balance` añade `ahorro`. Rutas.
- [ ] Verde, commit.

### Task 5: Interfaz, Balance, catálogos, SW

**Files:** `templates/budget/_fragmentos/meta_tarjeta.html`, `meta_aporte_fila.html`, `aporte_form.html`, `templates/budget/balance.html`, `templates/budget/_fragmentos/ahorro.html` (nuevo), `static/css/components.css`, `templates/sw.js`, `tests/test_pwa.py`, `locale/*/django.po`.

- [ ] Tests de plantilla en `test_metas_vistas.py`: la tarjeta del fondo no tiene barra y dice "Balance:"; una meta con saldo ofrece Withdraw/Transfer y no Remove; con saldo 0 y cascada dice Archive; Balance muestra "Savings" con las cifras; un retiro se pinta con signo negativo y su nota.
- [ ] Plantillas + CSS (`.movimiento--salida` en rojo suave, `.movimiento__nota`), `sw.js` v15, catálogos EN/FR, `test_catalogo_exhaustivo` verde.
- [ ] Verde, commit.

### Task 6: Suite completa, navegador, cierre

- [ ] Suite entera en segundo plano; corregir lo que salga.
- [ ] Navegador: crear el fondo, aportar con nota, retirar, transferir al viaje, borrar con saldo (mensaje), vaciar y borrar; Balance con el bloque; móvil 400 px.
- [ ] Spec a "Implementado", commit.

# Wealthome — Metas II: el fondo abierto, retirar, transferir y el ahorro en Balance

**Fecha:** 2026-09-20
**Estado:** Diseño aprobado, pendiente de plan de implementación
**Depende de:** `2026-09-20-wealthome-metas-design.md` (implementado en `ui/navegacion-y-tiles`).

Al usar las metas con casos reales salieron tres huecos: no hay forma de tener un fondo sin
objetivo ("ahorros para emergencias"), el dinero de una meta nunca sale de ella (ni al
usarlo ni al abandonarla), y los aportes manuales no se ven en ningún informe. Este
diseño cierra los tres.

---

## 1. Decisiones de producto

- **Un aporte manual es dinero de fuera del presupuesto** (un extra, un regalo, efectivo
  que no pasó por el mes). No toca ingresos, gastos, el plan ni el Cash Float. Queda
  registrado y se ve en **Balance**, en un bloque "Savings".
- **Un retiro es "ya lo usé"**: baja el saldo de la meta, lleva fecha y motivo, y sale de
  la app. Tampoco toca el mes ni el Cash Float.
- **Una transferencia** mueve saldo de una meta a otra activa, con fecha y nota.
- **`Reached` se queda** aunque después se retire el dinero: la meta se cumplió. Ningún
  retiro la devuelve a activa.
- **Borrar exige saldo 0.** Con saldo, la tarjeta ofrece retirar o transferir, no borrar.
  Con saldo 0: si la meta nunca recibió cascada se borra de verdad; si la recibió (un
  cierre la referencia) se **archiva**: desaparece de Goals y queda en Balance.
- **Fondo abierto** (`open_fund`): sin objetivo ni fecha; aporte mensual opcional. La
  tarjeta enseña el saldo y "This month: $X of the $Y you set" si hay aporte fijado. Sin
  barra de progreso, nunca pasa a `reached`. Se alimenta por cascada o a mano como las
  demás.

**Fuera de alcance:** que un retiro vuelva al mes como ingreso; edición de retiros y
transferencias (se borran y se vuelven a hacer); reportes más allá del bloque en Balance.

---

## 2. Modelo (migración `0010`)

**`Goal`**
- `contribution_mode` gana `open_fund`. `target_amount` y `target_date` pasan a
  `null=True, blank=True`.
- `clean()`: `by_target_date` exige `target_amount` y `target_date`; `by_monthly_amount`
  exige `target_amount` y `monthly_amount`; `open_fund` exige que `target_amount` y
  `target_date` estén vacíos (`monthly_amount` opcional).
- `status` gana `archived`.
- `alcanzada(acumulado)` devuelve `False` sin `target_amount`.
- `es_fondo` → `contribution_mode == "open_fund"`.

**`GoalContribution`** — pasa a ser *el movimiento de una meta*:
- `origen` ∈ {`manual`, `cascade`, `withdrawal`, `transfer_out`, `transfer_in`}.
- `amount` con signo: positivo en `manual`, `cascade`, `transfer_in`; negativo en
  `withdrawal`, `transfer_out`. Lo impone `clean()`.
- `note` (`CharField(200, blank=True)`): el motivo del retiro, la fuente del aporte.
- `counterpart` (FK a sí misma, `null=True`, `on_delete=CASCADE`, `related_name="+"`):
  enlaza los dos lados de una transferencia. Borrar un lado borra el otro.
- El saldo de una meta sigue siendo `sum(amount)` de sus filas.

**Motor** (`engine/goals.py`): `OPEN_FUND` entra en `MODOS_DE_META`. `derivar` con
`open_fund` devuelve `(aporte_mensual o 0.00, None)`.

---

## 3. `services_goals`

| Función | Comportamiento |
|---|---|
| `aportar(hogar, meta, amount, date, member, origen="manual", note="")` | Como hoy, más `note`. |
| `retirar(hogar, meta, amount, date, member, note)` | Fila `withdrawal` con `-amount`. `amount` > 0 y ≤ saldo, si no `SaldoInsuficiente` (ValueError). `MesCerrado` sube. No recalcula estado (`reached` se queda). |
| `transferir(hogar, origen, destino, amount, date, member, note)` | Atómica: `transfer_out` en origen (`-amount`) y `transfer_in` en destino (`+amount`), enlazadas por `counterpart`. Origen ≠ destino; destino `active`; `amount` ≤ saldo del origen. Recalcula el destino (puede alcanzarse); el origen no baja de `reached`. |
| `recalcular_estado(meta, acumulado=None, bajar=True)` | Como hoy; con `bajar=False` nunca pasa de `reached` a `active`. Un `open_fund` nunca sube a `reached`. |
| `quitar(meta)` | Saldo ≠ 0 → `SaldoPendiente`. Con algún movimiento `cascade` → `status = archived`; sin cascada → `delete()`. Devuelve `"archived"` o `"deleted"`. |
| `resumen(...)` | Excluye `archived` (lo hace la vista). Por meta añade `saldo` (= acumulado), `es_fondo`, `tiene_cascada`, `puede_quitar` (saldo == 0), `puede_sacar` (saldo > 0). `porcentaje` y `porcentaje_barra` son `None` para un fondo. `aportes` lista todos los movimientos, con `editable` solo en `manual` (mes no cerrado) y `borrable` en todo menos `cascade` (mes no cerrado). |
| `resumen_ahorro(hogar, ambito, membresia)` | Para Balance: los movimientos de las metas visibles en ese ámbito (archivadas incluidas), agrupados por año-mes de la **fecha** del movimiento: `cascada`, `a_mano`, `retiros`, `neto` y `saldo` acumulado (de más reciente a más antiguo en la salida, acumulado en orden cronológico). Las transferencias se anulan entre sí y no se listan. Más el `saldo_total` y el desglose por meta (`nombre`, `estado`, `saldo`). |

---

## 4. Vistas y rutas

| Ruta | Vista | Comportamiento |
|---|---|---|
| `goals/<pk>/withdraw/` | `retirar` | `RetiroForm` (amount, date, note). Página entera (`formulario.html`). Saldo insuficiente / mes cerrado → error en el form. Vuelve a Goals. Meta `archived` → 404. |
| `goals/<pk>/transfer/` | `transferir` | `TransferenciaForm` (to_goal, amount, date, note); `to_goal` = metas activas visibles menos la propia. |
| `goals/<pk>/delete/` | `meta_borrar` | Pasa por `quitar`: saldo ≠ 0 → `messages.error` "Withdraw or transfer its balance first."; archivada → `messages.info` "…archived; it stays in Balance."; borrada → nada. |
| `goals/contributions/<pk>/delete/` | `aporte_borrar` | Permite `manual`, `withdrawal`, `transfer_*` (mes no cerrado). En una transferencia recalcula las dos metas. `cascade` → 403. |
| `goals/contributions/<pk>/` | `aporte_editar` | Solo `manual` (como hoy); el form gana `note`. |
| `<ambito>/goals/` | `metas` | Excluye `archived`. |
| `<ambito>/balance/` | `balance` | Añade `ahorro = resumen_ahorro(...)`. |

`GoalForm`: `contribution_mode` con `x-model`; `target_amount`/`target_date` con
`x_show` para los dos modos con objetivo, `monthly_amount` para `by_monthly_amount` y
`open_fund`. `clean()` vacía lo que no pertenece al modo (patrón de `IncomeSourceForm`).
`GoalContributionForm` gana `note`.

---

## 5. Interfaz

**Tarjeta** (`meta_tarjeta.html`):
- Fondo: sin barra; "Balance: $X"; si `monthly_amount`, "This month: $X of the $Y you
  set"; si no, "This month: $X".
- Botones bajo la frase: **Add to it** (activa o fondo), **Withdraw** y **Transfer** (si
  `puede_sacar`, en cualquier estado no archivado).
- Cabecera: Edit; **Remove** si `puede_quitar` y sin cascada; **Archive** si
  `puede_quitar` con cascada; nada si hay saldo. Abandon/Reactivate como hoy.
- Movimientos: etiqueta por `origen` — quién / "From the monthly split" / "Withdrawal" /
  "To <meta>" / "From <meta>", con la `note` debajo si la hay; importe con signo
  (`money` ya pinta `-$150.00`). Acciones: Edit solo en `manual`; Remove en todo menos
  `cascade`.

**Balance** (`balance.html`): tarjeta a todo el ancho "Savings" arriba de los cierres,
con la fila de cifras (saldo total, aportado este año a mano, por cascada, retirado) y
una tabla por mes: Month · From the split · By hand · Withdrawn · Balance. Debajo, la
lista por meta con su saldo y estado (incluye archivadas). Sin movimientos: "Nothing
saved yet."

**Formulario de meta**: el `<select>` del modo esconde/enseña campos con Alpine; la
ayuda del modo abierto dice "A fund with no target: just a balance you add to."

i18n EN/FR, `sw.js` a v15.

---

## 6. Pruebas

- `engine/test_goals_engine.py`: `open_fund` deriva `(aporte, None)` y `(0, None)`.
- `test_models.py` (o `test_services_goals.py`): `clean()` de `Goal` por modo; signo del
  importe por `origen`.
- `test_services_goals.py`: `retirar` (saldo insuficiente, mes cerrado, no baja de
  `reached`), `transferir` (pareja enlazada, destino alcanzado, destino no activo, misma
  meta), `quitar` (saldo pendiente, archivar vs borrar), `resumen` de fondo,
  `resumen_ahorro` (agrupación, transferencias anuladas, archivadas incluidas, ámbito).
- `test_metas_vistas.py`: retirar/transferir por la pantalla, borrar con saldo, archivar,
  la tarjeta del fondo, archivadas fuera de Goals, Balance con el bloque.
- `test_aportar.py`: borrar un lado de la transferencia borra el otro y recalcula; `note`.

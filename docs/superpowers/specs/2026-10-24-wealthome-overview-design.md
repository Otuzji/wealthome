# Wealthome — Overview: el mes de un vistazo

**Fecha:** 2026-10-24
**Estado:** Diseño aprobado en conversación; pendiente de revisión del usuario y de plan
**Depende de:** `views_month.mes` (líneas, transacciones, `totales`, `_real_contra_planeado`),
`services.cash_float`, `services.obtener_mes`, la cascada (`engine/cascade.py`,
`MonthlyAllocation`, `AllocationRule`) y la navegación de `apps/core/context_processors.py`.

El Overview se quitó el 2026-09-20 (commit `4b77261`): enseñaba gráficas del mes que This
month ya enseñaba. Vuelve con otro propósito: **responder en cinco segundos cómo va el mes
y si hay que hacer algo**, sin abrir This month ni sumar a mano. Es la pantalla de entrada
de la aplicación.

Lo que dijo el usuario va sin marca. Lo marcado **(decisión de diseño)** lo propuso Claude
y el usuario aprobó la propuesta en bloque ("adelante con tu propuesta"); conviene que el
usuario lo revise al leer.

---

## 1. Objetivos, no-objetivos, anti-objetivos

**Objetivos**

- Cinco bloques: Forecast, Real, Expenses, Desvíos por categoría y Alerta de Cash Float.
- Es el home por defecto. Sin presupuesto creado, invita a crearlo.
- Funciona en Household y en Personal, como el resto de pantallas del ámbito.

**No-objetivos**

- No navega entre meses: siempre el mes en curso **(decisión de diseño)**. El histórico
  vive en Summary; los otros meses, en This month.
- No edita nada. Cada bloque puede enlazar a donde se actúa (This month, Plan the month,
  Setup), pero el Overview es de solo lectura.
- No sustituye a This month: no lista líneas ni movimientos.
- Sin gráficas nuevas. Cifras y frases; una barra de progreso simple se permite donde ayude.

**Anti-objetivos** (lo que lo haría un fracaso aunque funcione)

- Cifras que no cuadran con This month. Forecast y Real **deben** salir de las mismas
  funciones que This month (`totales`, `_real_contra_planeado`, `cash_float`), no de una
  segunda implementación.
- Una alerta que grita en falso. Un "te falta dinero" que no es verdad enseña a ignorarla.
- Mezclar Hogar y Personal (ver commit `7987cca`).
- Lo personal de un miembro visible para otro (ver commit `13fa815`).

---

## 2. Ruta, navegación y home

- La ruta `budget:overview` (`/budget/<ambito>/`) deja de redirigir y renderiza el
  Overview. Hoy la vista vive en `apps/budget/views_summary.py:18`; el Overview pasa a su
  propio módulo (`views_overview.py`) y se corrige el docstring de `views_summary.py`. El nombre de la ruta ya existe y el context processor lo usa como prefijo del
  ámbito: se conserva.
- Overview vuelve a ser la **primera pestaña** del ámbito (antes de This month), con su
  icono, bajo `can_view_budget`. `/budget/<ambito>/` es prefijo de todas las rutas del
  ámbito y `_encender` compara por `startswith`: cualquier página del ámbito que no
  reclame otra pestaña encendería Overview. Overview debe encenderse **solo** en su URL
  exacta (comparación de igualdad para ella).
- El conmutador Household | Personal conserva la pantalla: Overview ↔ Overview.
- **Home por defecto:** `accounts:inicio` (destino de `LOGIN_REDIRECT_URL`) redirige a
  `budget:overview household` cuando el usuario tiene membresía con `can_view_budget`.
  Sin membresía, o sin ese permiso, se queda la página de bienvenida actual
  **(decisión de diseño)**. El logo de la barra superior, si enlaza a inicio, llega igual.
- Service worker: la página nueva cambia lo que sirve una URL que ya estaba en caché
  (antes era un 302). Subir `VERSION` en `templates/sw.js` de `wealthome-v23` a
  `wealthome-v24`.

---

## 3. Los bloques

Todos sobre el **mes en curso** y el **ámbito** de la URL, con las líneas y transacciones
acotadas igual que `views_month.mes` (`acotar_por_dueno` para líneas, `acotar` para
transacciones). La lógica va a un módulo de servicio nuevo,
`apps/budget/services_overview.py`, que reutiliza lo existente; la vista solo arma el
contexto. Si para reutilizar hay que mover `totales` / `_real_contra_planeado` de
`views_month.py` a un servicio, se mueven (y `mes` los importa de ahí).

Si `obtener_mes` devuelve una `ProyeccionDeMes` (hogar sin escritura, §5.2), el Overview
se pinta con la proyección: Forecast con sus totales, y Real/Expenses/Desvíos/Alerta en
cero o con el estado vacío correspondiente **(decisión de diseño)**. No debe reventar.
`services.cash_float` lee `mes.household` y no admite una proyección: en ese camino no se
llama.

**Mes en curso ya cerrado** (se puede cerrar antes de que acabe): el Overview sigue
enseñando ese mes, con un aviso "October is closed" y enlace a planificar el siguiente.
La Alerta de Cash Float no se muestra (ya no hay pendientes que cubrir)
**(decisión de diseño)**.

### 3.1 Forecast — cómo pinta el mes según el plan

Household:

| Cifra | Origen |
|---|---|
| Ingresos | suma de `planned_amount` de las líneas de ingreso (incluye one-off) |
| Gastos | suma de `planned_amount` de las líneas de gasto (incluye one-off) |
| Savings | lo que la cascada manda a metas y a categorías/fondos (`target_type` GOAL o CATEGORY) |
| Allowance | lo que la cascada manda a mesadas (`target_type` ALLOWANCE), total del hogar |
| Sin asignar | sobrante que ninguna regla agota; solo se muestra si es > 0 |

- Savings, Allowance y Sin asignar se calculan **siempre al vuelo** con
  `motor_cascade.repartir(sobrante_proyectado, reglas)` —lo mismo que el paso 3 de Plan the
  month— sobre las líneas actuales **(decisión de diseño)**. Motivo: las
  `MonthlyAllocation` no sirven como marca de "mes planificado" (`planificar_mes` no
  escribe filas si el sobrante es ≤ 0 o no hay reglas) y quedan viejas si se editan líneas
  tras confirmar; leerlas haría que Savings + Allowance + Sin asignar no cuadrara con
  Ingresos − Gastos. Sin migración ni marca nueva. Con un sobrante ≤ 0, Savings y
  Allowance son 0 y el bloque lo dice ("Nothing left to split").
- "Savings" agrupa GOAL y CATEGORY **(decisión de diseño)**: para el usuario ambos son
  dinero apartado; la mesada es lo que se gasta cada miembro.
- Sobrante proyectado = ingresos − gastos planificados (lo mismo que `totales.sobrante`).

Personal **(decisión de diseño)**: no hay cascada personal. Forecast muestra los ingresos y
gastos planificados de las líneas personales propias y, en lugar de Savings/Allowance, **la
mesada del miembro este mes**: su parte de la cascada calculada al vuelo (igual que en
Household, para que cuadren), más `carried_in` y `adjustment` del `AllowanceLedger` si la
fila existe. Se lee con `.filter().first()`, **nunca** con `mesada_de` (hace
`get_or_create` y escribiría en un GET). Sin fila, arrastre y ajuste son 0. Al lado, "Left
to spend" = esa mesada − `gasto_personal_del_mes` calculado en vivo (no el `spent` del
libro, que solo se escribe al cerrar).

### 3.2 Real — cuánto ha entrado y salido a la fecha

- Ingresos reales, gastos reales y la diferencia (`sobrante_real`), de `totales` /
  `_real_contra_planeado` con las transacciones del mes acotadas al ámbito.
- Cada cifra con su referencia al plan ("$2,100 of $4,000") **(decisión de diseño)**.

### 3.3 Expenses — budget frente a one-off

Lo **gastado** (transacciones de gasto), partido en dos **(decisión de diseño: gastado, no
planificado)**:

- **Budget:** transacciones cuya `budget_line` NO es excepcional (líneas que vienen de las
  reglas).
- **One-off:** transacciones cuya `budget_line` es excepcional (`is_exceptional=True`):
  partidas puntuales planificadas y gastos registrados "not planned", que nacen con su
  propia partida excepcional (`_ligar_al_plan`).

Una transacción de gasto sin `budget_line` (no debería existir, pero el campo es nullable)
cuenta como one-off.

### 3.4 Desvíos por categoría

Solo las categorías **de gasto** donde lo real se separa de lo planificado, para ver de un
golpe dónde se gasta de más o de menos.

- Por categoría: planificado = suma de `planned_amount` de sus líneas de gasto **no
  excepcionales**; real = suma de las transacciones de gasto de esa categoría contra esas
  mismas líneas. Las one-off quedan fuera: su plan nace igual a lo gastado y nunca
  desvían, o son gasto sin plan que ya se ve en Expenses **(decisión de diseño)**.
- Desvío = real − planificado. Se muestra como "+$20 over plan" o "−$20 under plan".
- **Cuándo aparece una categoría (decisión de diseño, la más importante del bloque):**
  - **Exceso** (real > planificado): siempre, en cuanto ocurre.
  - **Ahorro** (real < planificado): solo cuando la categoría **ya terminó**, es decir,
    todas sus líneas están pagadas (`estado == PAGADA`) o tienen `due_date` anterior a hoy.
    Sin esto, el día 10 Fuel con $30 de $100 saldría como "−$70 under plan", que no es un
    ahorro sino un mes a medias. Una línea sin `due_date` se considera terminada solo si
    está pagada.
  - Desvío cero: no aparece.
- Orden: por valor absoluto del desvío, mayor primero; excesos y ahorros en el mismo
  listado, distinguidos por color y signo **(decisión de diseño)**.
- Sin desvíos: una línea "Everything is on plan so far."
- Cada fila enlaza a This month ordenado por categoría (`?orden=categoria`).

### 3.5 Alerta de Cash Float

Solo en **Household** (el Cash Float es del hogar; en Personal no existe, igual que en
This month).

- **Dinero en mano = saldo inicial del mes + ingresos reales − gastos reales del mes.**
  Lo pidió el usuario: sin un punto de partida, la alerta diría "Short" cada día 1 de
  cada mes en que el alquiler vence antes del sueldo, aunque haya dinero de sobra en la
  cuenta. Ingresos y gastos reales son el mismo `total` que usa `services.cash_float`.
- **Saldo inicial** (ver §3.6): si el mes no lo tiene, la alerta calcula con 0 y lo dice
  ("Add this month's opening balance for an accurate check"), con el campo a mano.
- **Próximo ingreso planificado:** la línea de ingreso del mes en curso con `due_date`
  posterior o igual a hoy que aún tenga `restante > 0`, la de fecha más temprana. Si no
  hay ninguna, la primera línea de ingreso del mes siguiente. El mes siguiente se lee
  **sin escribir**: si existe su `BudgetMonth` con líneas, esas líneas; si no, `proyectar`
  (`LineaProyectada.fecha`). **No** se usa `obtener_mes`, que materializaría una fila
  abierta y vacía en un GET. Las líneas proyectadas vienen de reglas del hogar.
- **Lo que falta pagar hasta entonces:** el `restante` de las líneas de gasto del mes en
  curso con `due_date` **estrictamente anterior** a la fecha del próximo ingreso (un gasto
  que vence el mismo día que entra el ingreso se considera cubierto por ese ingreso,
  **decisión de diseño**), más las líneas sin
  `due_date` (se asumen pendientes en cualquier momento del mes). Si el próximo ingreso
  cae el mes siguiente, se suman además las líneas de gasto del mes siguiente con
  vencimiento estrictamente anterior a esa fecha (importe planificado completo).
- **Resultado:**
  - Cubierto: "Covered: $210 to spare until Nov 15" (tono positivo, discreto).
  - No cubierto: "Short $340 for what's due before Nov 15" (tono de alerta, visible arriba).
  - Sin ningún ingreso planificado en este mes ni el siguiente: "No upcoming income
    planned" con enlace a Setup.
- El bloque enlaza a la tarjeta Cash Float de This month para el desglose.

### 3.6 Saldo inicial del mes

Dato nuevo, pedido por el usuario: con cuánto dinero empieza el hogar el mes.

- **Modelo (decisión de diseño):** `BudgetMonth.opening_balance`, `MoneyField` nullable.
  `None` = no introducido (distinto de 0). Un saldo por mes, del hogar (no hay saldo
  inicial personal). Requiere migración.
  - **Cuidado:** el `.env` local apunta a la base de producción (memoria del proyecto).
    `migrate` local toca el piloto real. Los tests usan su base propia; la migración se
    aplica a conciencia como paso de despliegue, no de pasada.
- **Dónde se introduce (decisión de diseño):** en la propia tarjeta de la alerta del
  Overview (Household), con un formulario pequeño en sitio (htmx, patrón de la app), y
  solo para quien tiene `can_edit_budget`. Se puede corregir mientras el mes esté
  abierto; un mes cerrado no se toca (la guarda `MesCerrado` del modelo ya lo impide si
  el guardado pasa por `full_clean`/`save` del `BudgetMonth`; el builder verifica que la
  guarda cubre este campo).
- **Sugerencia (decisión de diseño):** si el mes no tiene saldo y hay un `MonthlyClose`
  anterior, el campo se ofrece **prellenado** con su `arrastre` (`_arrastre_previo`),
  pero no se guarda hasta que el usuario lo confirma. Es una sugerencia, no un dato.
- **Alcance (decisión de diseño):** el saldo inicial solo entra en la **alerta** del
  Overview. No cambia la tarjeta Cash Float de This month ni su reparto (repartir un
  dinero que ya se repartió al cerrar el mes anterior lo contaría dos veces), ni los
  cierres. La alerta lo nombra para que no parezca una cifra distinta sin explicación:
  "In hand: $X (opening $Y + this month $Z)".
- Sin escritura (§5.2, hogar expirado): el campo no se ofrece.

---

## 4. Estado sin presupuesto

"Sin presupuesto" = el hogar no tiene **ninguna** `IncomeSource` ni `ExpenseRule` vigente
**y** el mes en curso no tiene líneas **(decisión de diseño)**. En ese caso el Overview no
pinta los bloques sino una tarjeta: título, una frase invitando a crear el presupuesto y un
botón:

- con `can_edit_budget`: botón a Budget setup (`budget:configurar`);
- sin él: "Ask the household owner to set up the budget." sin botón.

En Personal, el estado vacío depende del presupuesto del **hogar** (si el hogar no tiene
presupuesto, Personal tampoco), con el mismo mensaje.

---

## 5. Diseño visual

Sigue la dirección UI vigente: mosaico de tarjetas, 2 columnas en escritorio, una en
móvil, neomorfismo suave, tokens de tema existentes (tres temas, modo oscuro). Orden en
móvil **(decisión de diseño)**:

1. Alerta de Cash Float (si no está cubierto, va primero; si está cubierto, puede ir
   compacta en la misma posición)
2. Forecast
3. Real
4. Desvíos por categoría
5. Expenses

En escritorio el builder reparte las tarjetas en 2 columnas manteniendo ese orden de
lectura. Importes con el filtro `money` existente. Textos con `{% translate %}` y su
entrada en `locale/fr/LC_MESSAGES/django.po` (se editan a mano: ver memoria de
herramientas).

---

## 6. Permisos y seguridad

- La vista lleva `@requiere_permiso("can_view_budget")`, como `mes`.
- Todo dato pasa por `acotar` / `acotar_por_dueno`; en Personal nunca aparecen líneas,
  transacciones ni mesada de otro miembro.
- El ámbito se valida con `validar` (404 para uno inventado).

---

## 7. Pruebas que deben existir

- Forecast, Real coinciden con los de This month para el mismo mes y ámbito.
- Savings/Allowance con mes planificado (de `MonthlyAllocation`) y sin planificar (al vuelo).
- Expenses: separa budget de one-off, incluido un gasto "not planned".
- Desvíos: exceso aparece a mitad de mes; ahorro **no** aparece si la categoría tiene una
  línea pendiente y no vencida; **sí** aparece cuando todo está pagado o vencido; cero no
  aparece; orden por valor absoluto.
- Alerta: cubierto, no cubierto, próximo ingreso en el mes siguiente (con gasto del día 1
  del mes siguiente incluido), gasto el mismo día que el ingreso (cubierto), sin ingresos
  planificados; con y sin saldo inicial.
- Saldo inicial: guardar, corregir, prellenado con el arrastre sin guardarse solo, 403/no
  ofrecido sin `can_edit_budget`, rechazado en mes cerrado, no altera la tarjeta Cash
  Float de This month.
- Leer el mes siguiente no crea filas (`BudgetMonth` del mes siguiente no aparece tras un
  GET al Overview).
- Personal: sin alerta, con mesada, sin datos de otro miembro.
- Estado sin presupuesto, con y sin `can_edit_budget`.
- Proyección (hogar sin escritura) no revienta.
- Navegación: Overview es la primera pestaña, solo se enciende en su URL, el conmutador la
  conserva; login aterriza en Overview; el test que hoy espera la redirección
  (`tests/budget/test_views.py` ~línea 603) se actualiza.
- Tope de consultas razonable (hay tests de tope en This month; seguir el patrón).

---

## 8. Lo que queda al builder

- Nombres y estructura interna de `services_overview.py` y de la plantilla
  (`templates/budget/overview.html` y fragmentos).
- Icono de la pestaña Overview (hubo uno antes: puede recuperarse de `_nav_icono.html` en
  el historial).
- Textos exactos en inglés, siguiendo el tono de la app, y su traducción al francés.
- Reparto exacto de las tarjetas en las 2 columnas de escritorio.
- Si mover `totales` / `_real_contra_planeado` a un servicio o importarlas desde la vista.
- Ruta y vista del guardado del saldo inicial.

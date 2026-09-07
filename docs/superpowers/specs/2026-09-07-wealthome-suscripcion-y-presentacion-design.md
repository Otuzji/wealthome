# Wealthome — Plan 3: la suscripción y la presentación

**Fecha:** 2026-09-07
**Estado:** Diseño aprobado, pendiente de plan de implementación
**Depende de:** `2026-08-30-wealthome-nucleo-financiero-design.md` (el diseño de toda la
Fase 1), `2026-09-03-wealthome-motor-financiero-design.md` (el diseño del Plan 2), y del
Plan 2 ya integrado en `main` con 413 pruebas en verde.
**Estado de partida:** `docs/superpowers/2026-09-07-estado-y-deuda-plan-3.md`.

Los Planes 1 y 2 construyeron el motor y lo dejaron ejercitable a mano sobre formularios
planos, **feos a propósito**. Este plan hace dos cosas que aquellos aplazaron: pone la
aplicación en manos de alguien que no la escribió —navegación, presentación, las cifras
que hasta hoy solo existen en la base de datos— y le pone precio.

Todas las referencias con § apuntan al diseño de la Fase 1 salvo que digan otra cosa.

---

## 1. Alcance

**Incluye:**

- **La suscripción del §5 entera:** el trial de catorce días con su reloj, Stripe Checkout
  localizado, el webhook idempotente, y el modo solo lectura al expirar.
- **La capa de componentes** del §7.3 sobre los tokens que ya existen, y **el armazón de
  navegación** del §7.1: barra inferior en móvil con el `[+]` central, barra lateral en
  escritorio.
- **El eje Hogar / Personal** del §7.1 con sus cuatro módulos cada uno —Overview,
  Presupuesto, Balance, Metas—, resueltos como el §7 del Plan 2 decidió: la misma vista con
  el ámbito como parámetro.
- **Las cifras que hoy no se ven:** la varianza por categoría en Balance, y la mesada en
  Personal › Presupuesto, con el ajuste heredado del mes anterior y su explicación.
- **Los dos asistentes:** el de incorporación de seis pasos del §7.2 y el de planificar el
  mes de tres pasos del §4.5.6, este último con el reordenado por arrastre. Con el segundo
  vuelve el formulario de línea excepcional, porque su paso 2 lo necesita.
- **htmx, Alpine y Chart.js**, vendorizados.
- **La PWA del §10:** manifiesto, iconos, service worker con armazón y páginas vistas, y
  purga de la caché al cerrar sesión.
- **La deuda heredada del montón A** (sección 8 de este documento).

**No incluye:**

- Los montones B y C de la deuda heredada (sección 3 del documento de estado), con **una
  excepción**: el formulario de línea excepcional vuelve, arrastrado por el asistente.
  En concreto siguen sin arreglarse: `repartir_proporcional` con peso cero,
  `reemplazar_regla` limitado a `ExpenseRule` y sin `full_clean()`, `Goal.clean` sin
  comprobar el hogar del `owner`, `_categoria_de_ingreso` sin `order_by`, la guardia de
  pureza que no cubre `django.utils`, el README que promete un constraint inexistente,
  `GoalContribution.goal` en `CASCADE`, y las pruebas fechadas en 2030.
- **`AllocationRule.pesos` y `split=weighted` siguen sin ser alcanzables** desde la
  interfaz, aunque la pantalla de reparto se rehaga. El motor los soporta y están probados;
  el formulario sigue sin el campo. Es una omisión deliberada, no un olvido.
- **`varianza_por_categoria` se sigue guardando como `{str: str}`.** Balance reconstruye
  los `Decimal` al leer. No se migra.
- Reportes (Fase 2), registrar gastos sin conexión (Fase 2), Capacitor.

---

## 2. Las decisiones de este plan

### 2.1 La expiración se deriva, no se guarda

`Subscription.status` almacena `trialing` o `active`. **`expired` nunca se escribe:** se
deriva comparando `trial_ends_at` con el reloj.

La razón es la misma que hizo perezoso el ciclo del mes (§2.3 del diseño del Plan 2): no
hay cron en este stack, así que un estado guardado necesitaría que alguien lo escribiera a
medianoche, y en desarrollo nadie lo lanza. Un estado derivado siempre está bien. Es
además la misma disciplina del §4.6 del Plan 2: el tercer dato de una meta tampoco se
guarda, se deriva al mostrarlo.

### 2.2 La guardia de suscripción bloquea por método HTTP, no por vista

En `_decorador` —el cuerpo compartido de los tres decoradores de
`apps/households/permissions.py`, escrito explícitamente *"para que no puedan divergir"*—
un hogar sin derecho de escritura rechaza `POST`, `PUT`, `PATCH` y `DELETE`, y deja pasar
`GET`, `HEAD` y `OPTIONS`.

Así el *"expirar no destruye datos: el hogar pasa a solo lectura"* del §5.2 se cumple por
construcción y no vista por vista. Y las vistas de htmx que este plan todavía no ha escrito
nacen cubiertas, que es exactamente lo que el §5.7 del Plan 2 pedía cuando dijo que hacían
falta dos capas *"porque el Plan 3 añadirá caminos de escritura que hoy no existen"*.

**Las vistas de pago están exentas, con nombre.** Si la guardia las cubriera, un hogar
expirado no podría pagar para dejar de estarlo. La exención se declara con un decorador
propio sobre la vista, no con una condición escondida dentro de la guardia.

### 2.3 Un hogar expirado no materializa ni cierra meses

El ciclo del mes se dispara al entrar (§2.3 del Plan 2). Sin esta decisión, un hogar
expirado que solo *mira* su presupuesto provocaría escrituras: materializar el mes
corriente y cerrar en cadena los vencidos.

Y materializar un mes nuevo **es** registrar algo nuevo, que es justo lo que el §5.2
prohíbe. Así que para un hogar sin derecho de escritura el ciclo se detiene: los meses ya
persistidos se leen tal cual, y el mes corriente se trata como se trata uno futuro —se
**proyecta sin persistir**, por el camino que el §6 del Plan 2 ya tiene en su punto 3—. La
historia se ve entera y no se fabrica ni una fila.

Al pagar, la cadena de cierres se pone al día como en cualquier otra ausencia. Ese es el
caso que el §4 del documento de estado señala como el más peligroso del proyecto, así que
tiene prueba propia: un hogar que expira, deja pasar tres meses y paga.

### 2.4 La ausencia de suscripción significa "puede escribir"

Si un `Household` no tiene fila de `Subscription`, ambas capas de la guardia lo dejan
escribir.

Fallar cerrado sería más severo, y rompería las 413 pruebas existentes de golpe: las
fábricas crean `Household` directamente, no por `crear_hogar`. Y lo que hay que impedir es
que escriba un hogar **con una suscripción vencida**, no uno sin fila. Para que el caso no
pueda aparecer en producción, `crear_hogar` siempre crea la suscripción, la migración la
crea para todos los hogares que ya existan, `HouseholdFactory` la crea también, y una
prueba afirma las tres cosas.

### 2.5 El ámbito Hogar / Personal vive en la URL

`/household/budget/` y `/personal/budget/`: la misma vista con el ámbito como parámetro,
filtrando por el campo `scope` que los modelos ya tienen.

La razón nueva —que no existía cuando el Plan 2 tomó esta decisión— es el service worker:
**cachea por URL**. Con el ámbito en un parámetro de consulta o en la sesión, la caché
serviría la página del hogar a quien pidió la personal. Con el ámbito en la ruta, el
problema no existe. De paso, el estado activo del menú sale solo y las páginas son
marcables.

### 2.6 Vendorizado, no CDN

htmx, Alpine y Chart.js se sirven desde `static/vendor/`. El §11 dice "Chart.js (CDN)",
pero el §10 pide un service worker que permita consultar sin señal, y una precarga fiable
no se construye sobre respuestas opacas de otro origen.

Descargar tres archivos a `static/` no introduce ningún paso de compilación, así que el
§2.5 —*frontend sin build step*— queda intacto. Las versiones se fijan y se anotan en el
README.

### 2.7 Los componentes se escriben una vez

La regla del §7.4 se mantiene entera y es la única regla de CSS que este plan considera
innegociable: **ningún componente lleva dentro un selector `[data-theme="…"]`**. El tema
Accesible cambia variables, no componentes.

El patrón ya está establecido en `components.css`: `.card` y `.btn` declaran a la vez
`border: var(--border-width) solid var(--border-color)` y
`box-shadow: var(--shadow-raised)`, y el tema Accesible pone el borde a 3 px y la sombra
interior a `none`. Todo componente nuevo sigue ese patrón.

**Corolario para las gráficas:** Chart.js recibe sus colores leyendo las variables CSS en
tiempo de ejecución (`getComputedStyle(document.documentElement)`), nunca literales. Una
gráfica con colores incrustados se vuelve ilegible en Nocturno y pierde el contraste 14:1
en Accesible. `tokens.css` gana una paleta categórica corta —cuatro o cinco series— con su
juego por tema.

---

## 3. La suscripción

### 3.1 Los modelos

Ninguno de los dos es `HouseholdScoped`: uno pertenece al hogar en el sentido de la
titularidad, no del aislamiento, y el otro no pertenece a ningún hogar.

**`Subscription`** — uno a uno con `Household`.

| Campo | Para qué |
|---|---|
| `status` | `trialing` \| `active`. **Nunca `expired`** (§2.1) |
| `trial_ends_at` | El reloj del §5.1: creación + 14 días |
| `stripe_customer_id` | Vacío hasta que Stripe lo entregue |
| `stripe_session_id` | La sesión de Checkout que pagó |
| `paid_at` | Nulo hasta el webhook |
| `amount`, `currency` | `MoneyField`, CAD 25.00 al crear. Se guarda para que un cambio de precio no reescriba lo que alguien ya pagó |

Dos propiedades derivadas, y son la única forma en que el resto del código pregunta:

- `esta_vigente` → `status == "active"`, o `status == "trialing"` y `trial_ends_at > ahora`.
- `estado_visible` → `trialing` \| `active` \| `expired`, para la interfaz.

**`StripeEvent`** — la idempotencia del §5.2 hecha esquema.

| Campo | Para qué |
|---|---|
| `event_id` | **Único.** Es toda la idempotencia |
| `type` | El tipo de evento de Stripe |
| `payload` | JSON crudo, para poder auditar qué llegó |
| `received_at` | Cuándo entró |
| `processed_at` | Nulo si se recibió pero aún no se aplicó |

### 3.2 La migración

Crea una `Subscription` para cada `Household` existente, con
**`trial_ends_at = hoy + 14 días`**, no con `created_at + 14 días`.

Una migración no debe dejar a nadie fuera retroactivamente. Con la fecha de creación, cada
hogar que exista hoy quedaría expirado en el instante de aplicar la migración, y el primer
efecto visible del Plan 3 sería que la aplicación deja de aceptar escrituras.

### 3.3 El camino del pago

1. **Registro** — `crear_hogar` crea la suscripción con catorce días. **Sin pedir tarjeta**
   (§5.1).
2. **Checkout** — una vista `@solo_admin` crea la sesión de Stripe en modo `payment`, CAD
   $25, con `locale` puesto al idioma de la petición (§5.3) y `client_reference_id` puesto
   al `pk` del hogar. El decorador es de **rol**, no de permiso: pagar es gobernar el
   hogar, no editar sus finanzas.
3. **Retorno** — la URL de éxito enseña *"estamos confirmando tu pago"* y **no concede
   nada**. Cualquiera puede visitarla (§5.2).
4. **Webhook** — la única fuente de verdad.

### 3.4 El webhook, paso a paso

Es un endpoint **público y sin autenticar**, exento de CSRF. Es, junto con `obtener_mes`,
el otro "único punto de entrada" del proyecto, y la lección del §4 del documento de estado
se aplica entera: merece pruebas de entrada hostil, no solo del camino previsto.

1. Verifica la firma con `STRIPE_WEBHOOK_SECRET`. Firma ausente o inválida → **400**, sin
   escribir nada.
2. `get_or_create` sobre `StripeEvent` por `event_id`, dentro de `transaction.atomic` y con
   `select_for_update` sobre la fila: Stripe reintenta, y reintenta en paralelo.
3. Si la fila ya tenía `processed_at`, responde **200** y no hace nada más. Eso es la
   idempotencia.
4. Solo `checkout.session.completed` actúa. Cualquier otro tipo se registra y se responde
   200: un webhook que devuelve error por un evento que no le interesa hace que Stripe lo
   reintente para siempre.
5. Localiza el hogar por `client_reference_id`. **No por el correo del cliente**, que el
   usuario puede cambiar en la pasarela.
6. Marca `status="active"` y `paid_at`, y sella `processed_at`.

Casos que las pruebas deben cubrir, todos sin hablar con Stripe: sin firma, con firma
ajena, el mismo evento tres veces, dos entregas simultáneas del mismo evento, un tipo
desconocido, un `client_reference_id` que no existe, un hogar que ya estaba activo, y un
cuerpo que no es JSON.

### 3.5 Las dos capas de la guardia

**Capa de vista** — en `_decorador`, según el §2.2. Un hogar sin derecho de escritura que
envíe un método inseguro recibe `SuscripcionVencida`, subclase de `PermissionDenied`, para
que la maquinaria de 403 que ya existe la sirva sin middleware nuevo. La plantilla 403
detecta esa subclase y ofrece el botón de pagar en vez de un texto seco.

**Capa de modelo** — `HouseholdScoped.save()` lanza si el hogar no puede escribir. Es la
capa que no se puede rodear, y la que cubre al comando de gestión y a cualquier script.

**Su coste, dicho en voz alta:** la comprobación necesita el hogar cargado. Se mitiga con
una `cached_property` en `Household`, así que es como mucho una consulta por instancia de
hogar y por petición. Y **no cubre `queryset.update()` ni `bulk_create()`**, exactamente
por la misma razón que `EscrituraAcotadaAlMes` tampoco los cubre y lo dice en su docstring:
ninguno de los dos llama a `save()`. Quedan prohibidos por convención sobre estos modelos.

---

## 4. La capa de componentes y el armazón

### 4.1 Los componentes

`components.css` crece siguiendo el patrón del §2.7. Lo que hace falta para las pantallas
de este plan:

- **Superficie** en relieve y hundida (`--shadow-raised` / `--shadow-inset`).
- **Botón** en sus tres tamaños, respetando `--touch-target` (44 px, 56 px en Accesible).
- **Campo de formulario** hundido, con su estado de error.
- **Tabla** legible en móvil.
- **Barra de progreso** — para las metas.
- **Píldora de estado** — mes abierto/cerrado, suscripción, meta cumplida.
- **Tarjeta de cifra** — la unidad con la que se enseñan los cuatro totales del cierre.
- **Navegación** — la barra inferior y la lateral.

`modules.css`, que hoy tiene una línea, recibe lo específico de cada pantalla.

### 4.2 El armazón de navegación

**Un solo bloque de HTML** en `base.html`, dos presentaciones. Hoy `base.html` no tiene
navegación de ninguna clase: es `<main class="shell">` y nada más, y lo que hace de menú es
la página de bienvenida con dos enlaces. Se construye entero, una vez.

En móvil, barra inferior fija, con la acción más frecuente en el centro (§7.1):

```
┌────────────────────────────────────────────────┐
│  Hogar   Personal   [ + ]   Metas    Ajustes   │
└────────────────────────────────────────────────┘
```

En escritorio, barra lateral con el árbol completo. `.shell` ya reserva
`padding-bottom: 96px`.

**Los enlaces se ocultan por permiso**, como el §7 del Plan 2 exigía —*"un 403 al hacer
clic es correcto pero grosero"*—. Y **el `[+]` depende solo de `can_add_transactions`**.
Ese es el cambio que le da camino al adolescente del §6.2, que hoy no tiene ninguno.

**El menú también refleja la suscripción.** Por el mismo principio, un hogar sin derecho de
escritura no enseña el `[+]` ni los enlaces de edición: enseña, en su lugar, el aviso de
que la prueba terminó y el camino a pagar. Sin esto, la guardia del §2.2 sería correcta y
grosera a la vez — el `[+]` seguiría ahí, invitando a un 403.

La quinta pestaña queda reservada a Reportes en la Fase 2; aquí la ocupa Metas.

---

## 5. Las pantallas

Ocho pantallas de módulo —cuatro por ámbito—, más la de suscripción, los dos asistentes y
el formulario de línea excepcional. Toda vista sigue llevando uno de los tres decoradores;
todo formulario sigue heredando de `HouseholdScopedModelForm`.

| Pantalla | Qué enseña | Decorador |
|---|---|---|
| **Overview** | Presupuesto contra gasto real, movimientos recientes, dos gráficas, y el botón de registrar | `can_view_budget` |
| **Presupuesto** | La vista anual y la mensual, con edición de reglas y de líneas | `can_view_budget` / `can_edit_budget` para editar |
| **Balance** | El balance actual y los cierres anteriores, con sus cuatro totales y **la varianza por categoría** | `can_view_budget` |
| **Metas** | Progreso visual y la fecha objetivo derivada | `can_view_budget` / `can_edit_budget` |
| **Personal › Presupuesto** | Además: **la mesada** — libro mayor, acumulado, en qué se fue, y el ajuste heredado | `can_view_budget` |
| **Suscripción** (en Ajustes) | Estado, días restantes, botón de pagar | `solo_admin` |

**Las dos gráficas del Overview:** planeado contra real por categoría, y la evolución del
balance sobre los últimos `MonthlyClose`. Ambas leen sus colores de las variables CSS
(§2.7).

**La varianza deja de ser invisible en Balance.** Los cuatro totales y
`varianza_por_categoria` se calculan y se guardan desde el Plan 2 y no aparecen en ninguna
pantalla. Balance los lee y reconstruye los `Decimal` desde el JSON `{str: str}` al
mostrarlos, sin migrar el campo.

**La mesada deja de ser invisible en Personal › Presupuesto.** Hoy `AllowanceLedger`
aparece exactamente una vez en toda la aplicación: como una línea de texto en la
previsualización de `planificar.html`. Esta pantalla enseña `carried_in`, `granted`,
`adjustment`, `spent` y `carried_out`, y **explica el ajuste**: cuando el §4.5.3 descuenta
un faltante de la mesada del mes siguiente, el miembro tiene que poder ver por qué. El
libro mayor se diseñó *"para que «¿por qué tengo $145 este mes?» siempre tenga
respuesta"*; esta es la pantalla donde se pregunta.

### 5.1 Los dos asistentes

**Incorporación** (§7.2), seis pasos: crear hogar → miembros → ingresos por miembro →
gastos fijos → meta de ahorro → reglas de reparto. Hoy el registro es un solo formulario
que crea usuario y hogar de una vez. El asistente reutiliza los formularios de Configurar;
no duplica lógica.

**Es abandonable y reanudable, y eso no es un adorno.** El paso 1 crea el hogar de verdad
—los cinco siguientes escriben contra él—, así que quien cierre la pestaña en el paso 3 ya
tiene un hogar. Abandonar tiene que dejar una aplicación usable, no un hogar a medio
construir: cada paso se puede saltar, el asistente se reanuda desde donde se dejó, y lo que
no se rellenó se rellena luego en Configurar. Un asistente que hay que terminar de una
sentada convierte una interrupción en una cuenta rota.

**Planificar el mes** (§4.5.6), tres pasos: ingresos → salidas → reparto. El Plan 2 lo
colapsó en una pantalla con permiso explícito de su plan, y el §4.5.6 quedó incumplido; el
criterio de aceptación 3 del Plan 2 —*"una pareja planifica el mes en tres pasos"*— se dio
por bueno sobre una pantalla que no tiene tres pasos. Aquí se cumple:

- Paso 1, **ingresos**: los fijos precargados; los variables piden confirmar o ajustar.
- Paso 2, **salidas**: gastos fijos precargados y editables, **más las partidas
  excepcionales**. Esto exige el formulario de `BudgetLine` que no existe en toda la
  aplicación, y por eso vuelve del montón B: sin él, `is_exceptional` sigue siendo un campo
  que nadie puede poner.
- Paso 3, **reparto**: el sobrante proyectado, la cascada aplicada, la mesada por miembro
  con su acumulado, y **las reglas reordenables arrastrando** — la única interacción de
  Alpine de este plan.

Al confirmar, el mes pasa a `open` y se escriben las `MonthlyAllocation` y el
`AllowanceLedger`. Ese confirmar es el que hoy admite doble envío; se arregla en el montón
A (§8).

---

## 6. htmx, Alpine y Chart.js

Vendorizados (§2.6), con versión fijada.

**htmx se usa en cuatro sitios y en ninguno más:**

1. Registrar un gasto sin salir del Overview.
2. Los pasos de los dos asistentes.
3. Los filtros del Overview.
4. Aportar a una meta.

**La navegación entre módulos son cargas de página completas.** Es una decisión, no una
omisión: con htmx entre módulos, el service worker no vería las páginas que debe cachear y
el botón "atrás" dejaría de decir la verdad.

Cada endpoint de htmx devuelve un fragmento, y **el fragmento es lo que se prueba**: la
prueba pide la URL con la cabecera `HX-Request` y afirma sobre el trozo devuelto. No hace
falta un navegador para eso.

**Alpine** solo donde hay interacción real: el arrastre del paso 3.

**Chart.js** solo en el Overview, leyendo colores de las variables CSS.

---

## 7. La PWA

`manifest.json`, los iconos, y un service worker con tres comportamientos:

- **Precarga del armazón** — CSS, los tres archivos de `vendor/`, iconos, manifiesto y una
  página de "sin conexión".
- **Red primero para las páginas del hogar**, con la respuesta cacheada como reserva. Así
  el miembro consulta su presupuesto sin señal, que es lo que el §10 promete.
- **Purga al cerrar sesión** — `caches.delete()` disparado por un mensaje al worker, más la
  cabecera `Clear-Site-Data` en la respuesta de logout.

**La purga es un entregable con nombre propio y con su prueba.** Es una garantía de
privacidad, no una optimización: la caché contiene las finanzas de una familia, en un
dispositivo que puede ser compartido, y es la clase de cosa que se rompe en silencio.
Es la única prueba de Playwright de este plan.

**Un interruptor para desarrollo.** Un service worker que cachea vuelve el desarrollo
confuso —se sirve una versión vieja y parece un error de código—, así que se desactiva
cuando `DEBUG` está puesto, y eso se documenta en el README.

---

## 8. La deuda heredada que entra (montón A)

Solo estas. Todas son cosas que **el propio Plan 3 empeora**, no deuda genérica.

1. **Las dos guardias de mes cerrado que faltan del §5.7 del Plan 2.** `MonthlyAllocation` pasa a
   heredar `EscrituraAcotadaAlMes` —ya tiene `budget_month`, es gratis—, y
   `GoalContribution` **gana una FK a `BudgetMonth`**, rellenada por migración desde su
   `date`. Hoy `budget:aportar` escribe contra un mes cerrado sin que nada lo impida.

   *Por qué la FK y no derivar el mes desde `date` en el gancho `_mes()`:* derivarlo cuesta
   una consulta en cada guardado, y sobre todo puede resolver a un mes que **no existe como
   fila** —los meses futuros no se persisten—, y entonces no hay a quién preguntarle si
   está cerrado. La FK además es lo que Personal › Metas necesita para agrupar aportes por
   mes.

2. **El doble envío de `planificar_mes`.** `select_for_update` y un
   `UniqueConstraint(budget_month, rule, member)`. htmx ensancha esa ventana: un botón que
   responde en la misma página invita al segundo clic. `cerrar_mes` toma además el
   `select_for_update` que el §6 del Plan 2 exige y que hoy no toma.

3. **El N+1 del mes y de metas,** con `select_related` sobre `categoria`, y
   `views.metas` dejando de llamar a `meta.acumulado()` dos veces. Se fija con
   **presupuestos de consultas** (`django_assertNumQueries`) sobre Overview, mes, Balance y
   metas, con 50 transacciones sembradas. El Overview agrega mucho más que la pantalla del
   mes, y va contra el pooler de Supabase.

4. **La atribución falsa de `GoalContribution`.** `aplicar_cascada_al_cierre` escribe el
   aporte a nombre de `active_memberships().order_by("pk").first()`: un ahorro **del hogar**
   queda a nombre de quien tenga el `pk` más bajo, y si no hay membresías activas revienta
   con `IntegrityError` en medio del cierre. `member` pasa a ser anulable para el origen
   `cascade`. Urge ahora porque "las metas con progreso visual" van a **enseñar** ese dato
   falso.

5. **La migración de datos que siembra el catálogo** en hogares preexistentes. Sin ella no
   se despliega sobre una base que ya tenga hogares: `_categoria_de_ingreso` estalla con su
   `LookupError`.

---

## 9. Pruebas

### 9.1 La prueba de navegación, que es la que mata el fallo que describiste

`tests/test_navegacion.py`. Para cada uno de tres perfiles —administrador, miembro con solo
`can_view_budget`, y el adolescente del §6.2 con solo `can_add_transactions`— renderiza el
armazón, extrae **todos** los enlaces del menú, y afirma tres cosas:

- Cada enlace del menú resuelve y devuelve 200 para ese perfil.
- **Ninguna pantalla que el perfil puede abrir falta del menú**, contra un mapa declarado
  como dato dentro de la prueba.
- Ningún enlace del menú devolvería 403.

El mapa declarado es lo que convierte esto en una regresión permanente: añadir una pantalla
sin enlazarla rompe la prueba. Hoy las pruebas llegan por `reverse()`, que es precisamente
por lo que nadie notó que el menú enlazaba 1 de 6 pantallas.

### 9.2 El resto

- **Suscripción:** los ocho casos hostiles del §3.4, más el ciclo completo —trial, expira,
  solo lectura, paga, vuelve a escribir— y el caso del §2.3: expira, pasan tres meses, paga,
  y la cadena de cierres se pone al día sin fabricar historial.
- **La guardia unificada:** que un hogar expirado recibe 403 en `POST` y 200 en `GET`; que
  la vista de pago está exenta; que la capa de modelo lanza aunque se rodee la vista; que un
  hogar sin fila de suscripción escribe (§2.4).
- **htmx:** cada fragmento pedido con la cabecera `HX-Request`.
- **Presupuestos de consultas** sobre las cuatro pantallas de lectura.
- **Playwright:** una sola prueba, la purga de la caché al cerrar sesión.
- **El catálogo bilingüe lleva una tarea por tanda**, no una al final. Es lo que el §9 del
  diseño del Plan 2 pidió, y es lo que evita perder un día al final.

Las pruebas del motor siguen sin `django_db` y la guardia de pureza sigue en pie: este plan
**no toca `engine/`**.

---

## 10. Orden y puntos de control

Seis tandas. El Plan 2 demostró que los puntos de control usables valen su peso, así que
cada tanda termina en un sitio donde se puede parar.

1. **La deuda del montón A** y las guardias de mes cerrado.
   → *La aplicación de hoy, correcta.*
2. **La suscripción** entera, con su pantalla plana y fea a propósito, como el Plan 2 hizo
   con las suyas.
   → *Se puede cobrar.*
3. **Componentes y armazón de navegación**, con las seis pantallas de hoy repasadas encima
   y la prueba de navegación por perfil. La pantalla de suscripción se viste aquí.
   → *Usable y navegable. Aquí muere el problema del adolescente.*
4. **El eje Hogar/Personal y las pantallas nuevas**, con Chart.js: Overview, Balance con la
   varianza, Metas con progreso, Personal con la mesada.
   → *El §7.2 cumplido, y las cifras invisibles a la vista.*
5. **Los dos asistentes**, el arrastre, la línea excepcional y htmx donde toca.
   → *El §4.5.6 cumplido por fin.*
6. **La PWA** y la purga.

La suscripción va en la tanda 2 y no más tarde por una razón concreta: su guardia es
transversal, y al vivir en `_decorador` toda pantalla de las tandas 3 a 6 nace cubierta.
Hacerla al final obligaría a auditar pantalla por pantalla.

Calculo entre 22 y 26 tareas: es mayor que el Plan 2, que ya era el mayor de los tres.

---

## 11. Riesgos conocidos

**El tamaño, otra vez, y más.** Este plan es mayor que el Plan 2 y toca tres subsistemas
independientes. Se propuso partirlo y se decidió no partirlo; los puntos de control de la
sección 10 son la mitigación acordada.

**La suite crece sobre 19 minutos.** Ya no cabe en una sola llamada y se corre en dos
mitades. Este plan añade pruebas de vistas y de webhooks, que son de base de datos. Sin CI,
cada corrida completa es tiempo de una persona esperando.

**El catálogo bilingüe.** Este plan añade más texto visible que el Plan 2: ocho pantallas
de módulo, dos asistentes, la suscripción y sus estados, y los mensajes de error de la
guardia nueva. Sin cadena GNU gettext en esta máquina, todo se escribe a mano en los dos
`.po`. De ahí la tarea de catálogo por tanda.

**Las claves de Stripe.** Hacen falta `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` y
`STRIPE_WEBHOOK_SECRET` en `.env`, en modo de prueba. **Las pruebas nunca llaman a
Stripe**, así que la suite corre sin claves; lo que necesita claves es el ejercicio manual
del pago, y para el webhook local hace falta la CLI de Stripe. Eso se documenta antes de la
tanda 2, no durante.

**Playwright.** Una dependencia nueva y una descarga de navegadores para una sola prueba.
Se acepta porque esa prueba cubre una garantía de privacidad.

**El service worker en desarrollo.** Desactivado bajo `DEBUG` (§7). Si no, media tanda se
va en depurar una versión cacheada.

**Un punto ciego que este plan no cierra:** ni la guardia de mes cerrado ni la de
suscripción cubren `queryset.update()` ni `bulk_create()`. Siguen prohibidos por convención
sobre estos modelos. Queda escrito aquí para que la siguiente persona no lo descubra en
producción.

---

## 12. Criterios de aceptación

1. Un hogar nuevo tiene catorce días completos sin dar una tarjeta, y el día quince pasa a
   solo lectura **sin perder un dato**.
2. Una suscripción se marca activa **solo** por el webhook: visitar la URL de retorno sin
   haber pagado no concede nada.
3. El mismo evento de Stripe entregado tres veces, y dos veces en paralelo, deja el hogar
   exactamente en el mismo estado.
4. Un hogar expirado entra a su presupuesto, lo ve entero, y **no materializa ni cierra
   ningún mes**. Al pagar, la cadena de cierres se pone al día sin fabricar historial.
5. Un miembro con solo `can_add_transactions` inicia sesión, ve el `[+]` en la barra
   inferior y registra un gasto **sin teclear una URL**.
6. Ninguna pantalla que un perfil no puede abrir aparece en su menú, y ninguna que sí puede
   abrir falta de él — verificado por prueba, no por inspección.
7. La varianza por categoría de un mes cerrado **se ve** en Balance, junto a los cuatro
   totales.
8. Un miembro ve su mesada del mes, su acumulado, en qué se fue, y el ajuste heredado del
   mes anterior **con su explicación**.
9. Una pareja planifica el mes en tres pasos de verdad, reordena las reglas arrastrando, y
   añade una partida excepcional a ese mes.
10. `budget:aportar` contra un mes cerrado es rechazado, y lo es en la capa de modelo.
11. La aplicación se instala en la pantalla de inicio, abre sin señal enseñando lo ya
    visitado, y cerrar sesión deja la caché vacía.
12. Los tres temas siguen escribiéndose una sola vez: ningún componente nuevo contiene un
    selector de tema, y las gráficas son legibles en los tres.
13. La aplicación funciona completa en francés, con los montos formateados `2 847,50 $`.

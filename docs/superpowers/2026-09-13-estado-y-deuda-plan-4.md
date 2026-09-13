# Estado y deuda al cerrar el Plan 3

Rama `plan-3-suscripcion-y-presentacion`, 31 tareas, desde `6278708` sobre `main`.
Esto es lo que **no se deduce leyendo el código**.

---

## 1. Los trece criterios de aceptación, uno por uno

Cada criterio con la prueba que lo cubre, o con lo que falta. **Cuatro no están
cubiertos por completo**, y están marcados.

| # | Criterio | Prueba que lo cubre |
|---|---|---|
| 1 | 14 días sin tarjeta; el día 15, solo lectura sin perder un dato | `test_suscripcion.py::test_un_hogar_nuevo_nace_con_catorce_dias_y_sin_tarjeta`, `::test_el_dia_quince_deja_de_estar_vigente`, `::test_un_hogar_expirado_lee_pero_no_escribe` |
| 2 | Solo el webhook acredita; la URL de retorno no concede nada | `test_suscripcion.py::test_el_retorno_no_concede_nada`, `test_webhook.py::test_un_pago_acredita_la_suscripcion` |
| 3 | El mismo evento tres veces, **y dos en paralelo**, deja el mismo estado | `test_webhook.py::test_el_mismo_evento_tres_veces_deja_el_mismo_estado`. **⚠ El paralelo NO está probado** — ver §2 |
| 4 | Un hogar expirado ve su presupuesto y no materializa ni cierra; al pagar la cadena se pone al día | `test_month_cycle.py::test_un_hogar_expirado_no_materializa_el_mes_corriente`, `::test_un_hogar_expirado_ve_su_historia_pero_no_cierra_nada`, `::test_al_pagar_la_cadena_de_cierres_se_pone_al_dia`, `::test_un_hogar_expirado_puede_mirar_su_mes` |
| 5 | El adolescente registra un gasto sin teclear una URL | `test_navegacion.py::test_el_adolescente_llega_a_registrar_un_gasto_sin_teclear_la_url` |
| 6 | El menú enseña exactamente lo que el perfil puede abrir | `test_navegacion.py::test_el_menu_ensena_exactamente_lo_que_el_perfil_puede_abrir`, `::test_ningun_enlace_del_menu_devuelve_403` |
| 7 | La varianza por categoría se ve en Balance | `test_views.py::test_balance_ensena_la_varianza_por_categoria` |
| 8 | El miembro ve su mesada y el ajuste heredado con su explicación | `test_views.py::test_la_mesada_ensena_el_libro_mayor_entero`, `::test_la_mesada_explica_de_donde_sale_el_ajuste`, `::test_un_ajuste_sin_mes_anterior_sigue_explicandose` |
| 9 | Tres pasos de verdad, reordenar arrastrando, partida excepcional | `test_views.py::test_el_asistente_tiene_tres_pasos`, `::test_reordenar_reglas_cambia_su_prioridad`, `::test_se_puede_anadir_una_partida_excepcional_al_mes`. **⚠ El arrastre en sí (Alpine) no está probado en navegador** — solo el endpoint |
| 10 | `aportar` contra un mes cerrado se rechaza en la capa de modelo | `test_mes_cerrado.py::test_goal_contribution_no_se_escribe_contra_un_mes_cerrado` |
| 11 | Se instala, abre sin señal enseñando lo visitado, y al salir la caché queda vacía | `test_pwa.py` (manifiesto, iconos, precarga) y `::test_cerrar_sesion_deja_la_cache_vacia` (navegador). **⚠ "Abre sin señal" NO está probado** — ver §2 |
| 12 | Ningún componente con selector de tema; gráficas legibles en los tres | `test_css.py` (cuatro guardias: sin `data-theme`, sin color literal, paleta en los tres temas, JS sin colores ni cadenas). **⚠ "Legibles" es visual y no se ha mirado** |
| 13 | Funciona en francés, con montos `2 847,50 $` | `test_catalogo_exhaustivo.py`, `test_traducciones.py`, `test_money_field.py`, `test_i18n.py` |

## 2. Lo que queda sin verificar, y por qué

Nada de esto es un fallo conocido: es cobertura que falta.

- **El webhook en paralelo (criterio 3).** El mecanismo está —`select_for_update`
  sobre la fila de `StripeEvent` dentro de una transacción— y la idempotencia
  secuencial está probada, pero **no hay prueba de concurrencia**. Una prueba de
  verdad necesita dos conexiones simultáneas, que con `--reuse-db` contra el
  pooler de Supabase es justo lo que provoca los deadlocks que el plan documenta.
  Es la deuda de cobertura más importante que queda.
- **Abrir sin señal (criterio 11).** La prueba de navegador comprueba la purga,
  no el modo offline. Haría falta interceptar la red en Playwright
  (`page.route("**", lambda r: r.abort())`) y comprobar que la página ya visitada
  se sirve y que una nueva cae en `/offline/`.
- **Las verificaciones visuales.** Los pasos «míralo en los tres temas y en los
  dos tamaños» de las Tareas 13, 14, 16 y 19, el manifiesto en las herramientas
  del navegador (T29), y el arrastre a mano (T26). **Nada de esto se ha hecho.**
  Parte se sustituyó por guardias automáticas —la de colores literales y la de
  cadenas en el JS— pero «el ojo caza lo que ninguna prueba caza» sigue siendo
  verdad.
- **El pago real con Stripe (T12 Step 5).** Necesita claves de prueba en `.env` y
  la CLI de Stripe (`stripe listen`). No hay claves en el entorno y es un efecto
  fuera del repositorio. **Queda para el usuario**, y es lo único que ejercita el
  camino completo pasarela → webhook → acreditación.

## 3. Decisiones que hay que respetar

- **El ámbito va en la RUTA**, nunca en la query string ni en la sesión. El
  service worker cachea por URL: con el ámbito fuera de la ruta, la caché
  serviría la página del hogar a quien pidió la personal. Los **filtros** sí van
  en la query string, y por la razón inversa: un filtro es una vista de la misma
  página, y cachear cada combinación llenaría el disco de variantes.
- **`scopes.py` es el único sitio donde el ámbito se vuelve un filtro.** Si
  aparece un `filter(scope=...)` fuera de ahí, es que la mitad de las pantallas
  van a olvidarse.
- **La guardia de suscripción es por MÉTODO HTTP, no por vista.** Es lo que hace
  que las vistas de htmx nazcan cubiertas sin escribir una línea nueva. No la
  conviertas en una lista de vistas.
- **`sin_guardia_de_suscripcion` es la única exención, y se ve.** Si la guardia
  cubriera las vistas de pago, un hogar expirado no podría pagar para dejar de
  estarlo.
- **`Subscription` NO es `HouseholdScoped`,** a propósito: si lo fuera, escribir
  la suscripción de un hogar expirado quedaría bloqueada por la guardia que lee
  esa misma fila. Punto muerto.
- **Dos excepciones y no una:** `SuscripcionVencida` hereda de `PermissionDenied`
  porque su trabajo es volverse un 403; `SuscripcionVencidaError` es llana,
  porque una escritura fuera de una petición no tiene 403 que dar.
- **El service worker se sirve desde la RAÍZ (`/sw.js`), no desde `/static/`.** El
  alcance máximo de un service worker es su propio directorio: desde
  `/static/js/` no puede controlar el sitio, y el navegador lo rechaza con
  `SecurityError`. Lo encontró la prueba de navegador; no lo deshagas.
- **`debug` lo pone `apps.core.context_processors.navegacion` en sus TRES
  salidas.** El context processor de Django solo expone la variable si `DEBUG`
  está activo Y la IP está en `INTERNAL_IPS`, así que en la página de login no
  existiría y el service worker se registraría también en desarrollo.
- **Los comentarios `{# #}` de Django son de UNA línea.** Uno multilínea se
  cierra al final de la primera y el resto **se renderiza en la página**. Pasó
  con cuatro plantillas de este plan. Hay guardia:
  `test_css.py::test_ninguna_plantilla_lleva_un_comentario_multilinea_de_llave`.
- **Chart.js no lleva ni un color ni una cadena.** Los colores se leen de las
  variables CSS en tiempo de ejecución y un `MutationObserver` los relee al
  cambiar de tema; las etiquetas salen de atributos `data-` del `<canvas>`.
- **htmx en cuatro sitios y en ninguno más.** La navegación entre módulos son
  cargas de página completas: con htmx entre módulos, el service worker no vería
  las páginas que debe cachear y el botón «atrás» dejaría de decir la verdad.
- **El reordenado de reglas va en DOS pasadas** dentro de una transacción, porque
  `AllocationRule` tiene `UniqueConstraint(household, order)`.
- **`DJANGO_ALLOW_ASYNC_UNSAFE` está activo para toda la sesión de pruebas**
  (`tests/conftest.py`), porque el API síncrono de Playwright corre sobre un
  bucle de eventos y el fallo ocurre montando la fixture de `live_server`. Se
  acepta porque esta aplicación no tiene código asíncrono. **Si algún día lo
  tiene, esto pasa a ser un fixture local de la única prueba de navegador.**

## 4. Trampas del entorno descubiertas en este plan

- **El pooler de Supabase se degrada, y mucho.** No es variación de un 20 %: la
  misma selección de 43 pruebas tardó **3 horas** una vez y 6 minutos otra, y una
  de 3 pruebas tardó 40 minutos. Los síntomas son `OperationalError: server
  closed the connection unexpectedly` y lentitud extrema. **Un fallo así no es
  del código: reintenta antes de investigarlo.**
- **`--create-db` no se puede correr.** Falla con `DuplicateDatabase` /
  `ObjectInUse` porque el pooler mantiene sesiones abiertas contra
  `test_postgres`. La base reutilizada está al día: la última recreación fue en
  la Tarea 6 y **no se ha añadido ninguna migración desde entonces** (verificado
  con `git log` sobre `*/migrations/*`, y `makemigrations --check` no detecta
  cambios). Hay 15 migraciones en el árbol.
- **El coste de una llamada de prueba es `suma de ejecución + ~3,2 s por
  prueba`,** y el segundo término domina. Por eso repartir por número de pruebas
  desequilibra. El comando para medir por archivo está en el plan.
- **Los heredocs de shell destrozan los acentos.** Escribe el archivo con la
  herramienta de escritura y aplícalo con un script corto. Lo dice el plan y es
  verdad.
- **La suite se corre en NUEVE llamadas** (el plan documenta ocho; `test_views.py`
  se separó de `test_models.py` al final de la tanda 4). `test_views.py` sola va
  por ~500 s y **es la siguiente en romperse**.

## 5. Deuda que este plan no tocó

- **Los montones B y C de la deuda del Plan 2, enteros.**
- **`AllocationRule.pesos` y `split=weighted`**, que el motor soporta y la
  interfaz sigue sin alcanzar.
- **Reportes** (§7.1, quinta pestaña), **registrar gastos sin conexión** con su
  cola de sincronización (§10), y **Capacitor**.
- **`main` tenía 34 commits sin publicar** en `origin/main` antes de este plan.

## 6. Deuda nueva, creada por este plan

- **Las Tareas 7 a 31 no pasaron por revisión independiente.** Las 1 a 6 se
  despacharon a un subagente y se revisaron; de la 7 en adelante las ejecutó el
  coordinador en su propia sesión a petición del usuario. **Es la deuda más
  importante de esta lista.**
- **Un commit mezclado:** `4079711` (Tarea 18) incluye los archivos de Chart.js y
  `graficas.js`, que son de la Tarea 19. Y `18c90e9` cubre las Tareas 19 y 20
  juntas porque comparten `views_overview.py`.
- **Las briefs y los informes por tarea se dejaron de escribir** a partir de la
  Tarea 10, por decisión de cadencia. El ledger
  (`.superpowers/sdd/…/progress.md`) tiene los rulings; los informes por tarea
  solo existen para las Tareas 1-9.
- **`test_views.py` tiene 55 pruebas y ~500 s.** Partirlo por tema (mes, metas,
  asistentes, configuración) es trabajo de una hora que la próxima tanda va a
  necesitar.

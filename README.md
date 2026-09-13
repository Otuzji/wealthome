# Wealthome

Aplicación de presupuesto familiar para hogares canadienses. Bilingüe desde
el primer día (inglés/francés, `fr-CA`), moneda única CAD, tres temas
visuales (`sereno`, `nocturno`, `accesible`).

## Requisitos

- Python 3.11
- Una base de datos Postgres accesible (este proyecto usa un proyecto de
  Supabase; también sirve cualquier Postgres local)
- En Windows, no se necesita el paquete GNU `gettext` para ejecutar la app ni
  la suite de pruebas — solo hace falta si vas a regenerar los catálogos de
  traducción con `makemessages`/`compilemessages` (ver más abajo).

## Puesta en marcha

1. Clona el repositorio y entra en la carpeta del proyecto.

2. Crea un entorno virtual e instala las dependencias:

   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # Windows
   # source .venv/bin/activate   # macOS/Linux
   pip install -r requirements.txt
   ```

3. Copia `.env.example` a `.env`:

   ```bash
   cp .env.example .env
   ```

4. Obtén la cadena de conexión de Supabase y pégala en `DATABASE_URL` dentro
   de `.env`:

   - Entra al panel de tu proyecto en [supabase.com](https://supabase.com).
   - Haz clic en el botón **Connect** de la barra superior del panel (no en
     Project Settings → Database: esa ruta ya no existe en la interfaz
     actual de Supabase).
   - En el diálogo que se abre, ve a la sección **Transaction pooler**
     (puerto `6543`) y copia la cadena de conexión de ahí.
   - Reemplaza `PROJECTREF` y `PASSWORD` en `DATABASE_URL` con los valores
     reales de tu proyecto.
   - Genera un valor propio para `DJANGO_SECRET_KEY` (cualquier cadena larga
     y aleatoria sirve para desarrollo).

   `.env` está en `.gitignore`: nunca lo subas ni lo pegues en un mensaje.

5. Aplica las migraciones:

   ```bash
   python manage.py migrate
   ```

6. Levanta el servidor de desarrollo:

   ```bash
   python manage.py runserver
   ```

   La app queda disponible en <http://127.0.0.1:8000/>.

## Ejecutar las pruebas

```bash
pytest
```

o, para ver cada prueba individualmente:

```bash
pytest -v
```

La suite completa usa la misma base de datos de `DATABASE_URL` (crea y
destruye una base `test_...` a su alrededor) y tarda alrededor de tres
minutos contra el pooler de Supabase. Es normal ver una advertencia de que
`test_postgres` sigue en uso al finalizar — el pooler mantiene conexiones
abiertas un momento; si una corrida falla por eso, repítela.

## El motor financiero

El cálculo del presupuesto vive en `apps/budget/engine/`: dinero y redondeo,
las ocho periodicidades, los cinco modos de ingreso variable, la cascada del
sobrante, el cierre del mes, la mesada y las metas.

**Ese paquete no importa el ORM, ni `django.conf`, ni `django.utils`.** No es
una preferencia de estilo: es lo que permite probar la aritmética del dinero
sin base de datos, en segundos en vez de minutos, y lo que impide que una
consulta se cuele dentro de un bucle de cálculo. Una prueba de pureza
(`tests/budget/engine/test_pureza.py`) falla si alguien añade un import de
Django ahí dentro. El único módulo que cruza las dos capas es
`apps/budget/services.py`, y que la frontera esté en un solo archivo es lo
que la hace auditable de un vistazo.

```bash
pytest tests/budget/engine -q     # solo el motor: sin Postgres, en segundos
pytest tests/budget -q            # el motor y sus modelos, contra la base
pytest -q                         # todo
pytest -q --create-db             # OBLIGATORIO tras añadir una migración
```

`--create-db` hace falta porque la suite corre con `--reuse-db`: la base de
pruebas se conserva entre corridas para no pagarle al pooler de Supabase la
creación cada vez, y una base reutilizada se queda con el esquema viejo.

### El ciclo del mes

Un mes vive en tres estados: **futuro** (se proyecta desde las reglas
vigentes, sin filas persistidas, para que cambiar el alquiler se refleje al
instante en todos los meses por venir), **abierto** (filas reales, editables)
y **cerrado** (una foto congelada que no admite escrituras).

El disparador es **entrar**: al pedir un mes se cierran en cadena los
vencidos —en orden, porque cada cierre arrastra su saldo al siguiente— y se
materializa el corriente. No hay cron ni Celery en el stack, y un comando
programado como único disparador no correría en desarrollo.

```bash
python manage.py cerrar_meses_vencidos            # todos los hogares
python manage.py cerrar_meses_vencidos --hoy 2026-03-05
```

El comando existe para las instalaciones que sí puedan programarlo. No es el
único camino, y no hace falta para que la aplicación funcione.

### Las cinco desviaciones del spec de la Fase 1

Están razonadas en detalle en
[el diseño del Plan 2](docs/superpowers/specs/2026-09-03-wealthome-motor-financiero-design.md);
en corto:

1. **Las categorías se siembran por hogar**, no como árbol global con
   `household` nulo: `HouseholdScoped.household` no admite nulo y ablandarlo
   destriparía el aislamiento. Copiar el árbol al crear el hogar hace además
   que el «añadir *y renombrar*» del spec sea cierto sin una tabla de
   anulaciones.
2. **`source_rule` se parte en dos claves foráneas anulables**
   (`source_income`, `source_expense_rule`) con un `CheckConstraint` que
   exige como máximo una y que concuerde con el tipo de línea. Una clave
   genérica arrastraría `contenttypes` a cambio de nada.
3. **Los dueños son `Membership`, no `User`.** Con clave foránea a `User` se
   puede asignar el sueldo de una casa a alguien que no vive en ella; con
   `Membership` eso es irrepresentable, porque la membresía ya está atada al
   hogar.
4. **`Transaction` gana `income_source`.** Sin ella, el modo
   `rolling_average` de los ingresos variables no se puede calcular.
5. **`receipt_image` entra anulable y sin usar**, como pide el spec, aunque
   su destino real (Supabase Storage) siga sin decidirse.

## Dependencias del navegador

Vendorizadas en `static/vendor/`, servidas por el propio proyecto:

| Archivo | Version |
|---|---|
| `chart.umd.min.js` | Chart.js 4.4.7 |
| `htmx.min.js` | htmx 2.0.4 |
| `alpine.min.js` | Alpine.js 3.14.8 |

**No hay build step; estos archivos se actualizan a mano y a proposito.** Se
sirven desde el proyecto y no desde un CDN porque la PWA de la tanda 6 tiene que
funcionar sin red, y porque una dependencia que cambia sola bajo los pies no es
una dependencia, es una sorpresa.

## Stripe

La suite **nunca** llama a Stripe y corre sin claves. Para ejercitar el pago a
mano hacen falta, en `.env` y en modo de prueba:

    STRIPE_SECRET_KEY=sk_test_...
    STRIPE_PUBLISHABLE_KEY=pk_test_...
    STRIPE_WEBHOOK_SECRET=whsec_...

El `whsec_` lo entrega la CLI de Stripe al reenviar los webhooks al servidor
local, que es la única forma de probarlos sin desplegar:

    stripe listen --forward-to localhost:8000/subscription/webhook/

Sin esa CLI corriendo, un pago de prueba se completa en la pasarela y la
suscripción **no** se acredita — y eso es correcto: el webhook es la única
fuente de verdad (§5.2), y la URL de retorno no concede nada.

## Internacionalización

Los idiomas soportados son `en` (por defecto) y `fr`. Cada cadena visible en
la interfaz pasa por `gettext`/`gettext_lazy` en Python o por
`{% translate %}`/`{% blocktranslate %}` en las plantillas, y su traducción
vive en `locale/<idioma>/LC_MESSAGES/django.po`.

Para regenerar los catálogos después de tocar textos, hace falta el
toolchain de GNU gettext (`xgettext`, `msgfmt`) — en este entorno de
desarrollo (Windows) no estaba disponible, así que los catálogos actuales se
escribieron a mano y se compilaron con el `msgfmt.py` que trae la propia
instalación de Python en `Tools/i18n/msgfmt.py`. Si tu entorno sí tiene el
toolchain de gettext instalado (por ejemplo vía WSL, o `apt install gettext`
en Linux/CI):

```bash
python manage.py makemessages -l fr -l en --ignore=.venv
# traduce cada msgstr vacío en locale/fr/LC_MESSAGES/django.po
python manage.py compilemessages
```

Si no lo tiene, compila a mano con el `msgfmt.py` de la instalación de
Python (sustituye la ruta por la de tu propio Python):

```bash
python "<ruta-a-tu-Python>/Tools/i18n/msgfmt.py" -o locale/fr/LC_MESSAGES/django.mo locale/fr/LC_MESSAGES/django.po
python "<ruta-a-tu-Python>/Tools/i18n/msgfmt.py" -o locale/en/LC_MESSAGES/django.mo locale/en/LC_MESSAGES/django.po
```

`tests/test_traducciones.py` falla si queda alguna cadena francesa sin
traducir o marcada `#, fuzzy` (una traducción "adivinada" que
`compilemessages` descarta silenciosamente al compilar).

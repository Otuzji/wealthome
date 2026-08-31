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

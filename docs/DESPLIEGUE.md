# Despliegue en un VPS de Hostinger (piloto de wealthome.site)

Escrito para quien despliega, que es la misma persona que escribió la
aplicación. Asume un VPS KVM de Hostinger con Ubuntu 24.04 y acceso `root` por
SSH, y que la base de datos sigue siendo la de Supabase que ya se usa en
desarrollo.

La aplicación se sirve con **gunicorn** detrás de **nginx**, con el certificado
de **Let's Encrypt**. Los estáticos los sirve WhiteNoise desde el propio proceso
de gunicorn: para dos usuarios es de sobra y evita tener que enseñarle las rutas
a nginx.

---

## 0. Antes de tocar el servidor

**DNS.** En hPanel → Dominios → DNS, apunta dos registros `A` a la IP del VPS:

| Tipo | Nombre | Valor          |
|------|--------|----------------|
| A    | `@`    | IP del VPS     |
| A    | `www`  | IP del VPS     |

Certbot no puede emitir el certificado hasta que esto haya propagado. Se
comprueba con `dig +short wealthome.site` desde el propio VPS.

**Supabase.** En el panel del proyecto → Project Settings → Data API →
desactiva **Enable Data API** (o quita `public` de *Exposed schemas*). Es lo
único del endurecimiento que no se puede hacer por SQL. Hoy la clave `anon` ya
no puede leer nada (`scripts/endurecer_supabase.py --solo-auditar` lo confirma),
pero con la Data API apagada no hay ni superficie que auditar.

---

## 1. Paquetes del sistema

```bash
apt update && apt upgrade -y
apt install -y python3-venv python3-pip nginx git ufw
```

No hace falta `gettext`: los catálogos `.mo` ya vienen compilados en el
repositorio, así que no hay `compilemessages` en este despliegue. Si algún día
se editan los `.po` en el servidor, entonces sí.

## 2. Usuario propio para la aplicación

Gunicorn no corre como `root`: si algún día una dependencia tiene un fallo de
ejecución remota, la diferencia entre `root` y un usuario sin privilegios es
todo lo que hay.

```bash
adduser --system --group --home /opt/wealthome wealthome
```

## 3. Clonar y preparar el entorno

```bash
cd /opt/wealthome
sudo -u wealthome git clone https://github.com/Otuzji/wealthome.git app
cd app
sudo -u wealthome python3 -m venv .venv
sudo -u wealthome .venv/bin/pip install -r requirements.txt
```

`requirements.txt` trae también pytest y Playwright. Instalarlos en el servidor
no abre ningún puerto ni cambia lo que sirve gunicorn —son librerías, no
servicios— y a cambio permite correr la suite en el propio servidor cuando algo
sólo falla allí. Si molesta el peso, se parte el archivo; no es una cuestión de
seguridad.

## 4. El `.env` del servidor

**Nunca va en git** (`.gitignore` ya lo excluye). Se escribe a mano en el
servidor:

```bash
sudo -u wealthome tee /opt/wealthome/app/.env > /dev/null <<'EOF'
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=PEGA_AQUI_LA_CLAVE_GENERADA
DJANGO_ALLOWED_HOSTS=wealthome.site,www.wealthome.site
DJANGO_REGISTRO_ABIERTO=0
DATABASE_URL=postgresql://postgres.PROJECTREF:PASSWORD@aws-0-ca-central-1.pooler.supabase.com:6543/postgres
EMAIL_HOST_USER=tu.cuenta@gmail.com
EMAIL_HOST_PASSWORD=xxxx xxxx xxxx xxxx
DEFAULT_FROM_EMAIL=Wealthome <tu.cuenta@gmail.com>
EOF
chmod 600 /opt/wealthome/app/.env
```

La clave se genera **nueva para producción** — no se reutiliza la de
desarrollo, que ha estado en un portátil y en copias de OneDrive:

```bash
cd /opt/wealthome/app
sudo -u wealthome .venv/bin/python -c \
  "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

`DJANGO_REGISTRO_ABIERTO=0` cierra `/signup/` (contesta 404). Tu cuenta la
creas tú en el paso 5 con la puerta abierta un momento; tu esposa entra por
invitación, que es el camino que el piloto quiere probar de todas formas.

Las tres claves de Stripe se quedan vacías: **ver la nota sobre los 14 días al
final de este documento.**

## 5. Migrar, estáticos, y la cuenta de administración

```bash
cd /opt/wealthome/app
sudo -u wealthome .venv/bin/python manage.py migrate
sudo -u wealthome .venv/bin/python manage.py collectstatic --noinput
sudo -u wealthome .venv/bin/python manage.py createsuperuser
```

**Después de cada `migrate`, vuelve a endurecer Supabase:**

```bash
sudo -u wealthome .venv/bin/python scripts/endurecer_supabase.py
```

No es opcional ni es por gusto. Una migración crea tablas nuevas, y una tabla
nueva nace **sin RLS**. Los privilegios sí los hereda bien (el script fija
`alter default privileges`, así que los roles de la API no reciben nada sobre lo
nuevo), pero la fila de RLS hay que activarla tabla por tabla. Así apareció
`budget_balanceitem` sin RLS después del endurecimiento de septiembre. El script
es idempotente y termina imprimiendo `RESULTADO: SEGURO`.

## 6. Gunicorn como servicio de systemd

```bash
tee /etc/systemd/system/wealthome.service > /dev/null <<'EOF'
[Unit]
Description=Wealthome (gunicorn)
After=network.target

[Service]
User=wealthome
Group=wealthome
WorkingDirectory=/opt/wealthome/app
# NO se usa EnvironmentFile: `config/settings.py` ya llama a `load_dotenv()`
# sobre ese mismo `.env`, y el formato de systemd no es el de dotenv. Un valor
# con espacios —la contraseña de aplicación de Gmail viene en cuatro grupos, y
# DEFAULT_FROM_EMAIL lleva un nombre y unos ángulos— es justo el tipo de línea
# con la que systemd se queja y el servicio no arranca. Con una sola fuente
# leyendo el archivo no hay dos sintaxis que cuadrar.
ExecStart=/opt/wealthome/app/.venv/bin/gunicorn config.wsgi:application \
    --bind 127.0.0.1:8000 \
    --workers 3 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
Restart=always
RestartSec=3

# La aplicación no escribe en disco (los avatares son el único fichero que
# sube, y en el piloto no se usan): que el sistema de ficheros sea de sólo
# lectura para este servicio cuesta una línea.
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
NoNewPrivileges=true
ReadWritePaths=/opt/wealthome/app/staticfiles

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now wealthome
systemctl status wealthome --no-pager
```

`--bind 127.0.0.1:8000`: gunicorn **no** escucha en la IP pública. Lo único
expuesto es nginx.

Los errores se leen con `journalctl -u wealthome -f`. El `LOGGING` de
`config/settings.py` manda los tracebacks a stdout precisamente para que
aparezcan ahí; sin eso, un 500 en producción no deja rastro en ninguna parte.

## 7. nginx

```bash
tee /etc/nginx/sites-available/wealthome > /dev/null <<'EOF'
server {
    listen 80;
    server_name wealthome.site www.wealthome.site;

    client_max_body_size 5m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # ESTA es la cabecera que no se puede olvidar. Sin ella Django ve la
        # peticion por http aunque el navegador la haya hecho por https, y eso
        # rompe dos cosas a la vez: SECURE_SSL_REDIRECT entra en un bucle
        # infinito de redirecciones, y la comprobacion de CSRF compara el
        # Origin (https://...) contra el esquema que Django cree (http://...) y
        # contesta 403 a TODOS los formularios.
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/wealthome /etc/nginx/sites-enabled/wealthome
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

## 8. Certificado TLS

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d wealthome.site -d www.wealthome.site --agree-tos -m tu.cuenta@gmail.com --redirect
```

Certbot reescribe el bloque de nginx para el 443 y deja la renovación
automática puesta (`systemctl list-timers | grep certbot`).

## 9. Cortafuegos

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

## 10. Comprobación antes de invitar a nadie

```bash
# La configuración de producción, vista por Django:
cd /opt/wealthome/app
sudo -u wealthome .venv/bin/python manage.py check --deploy
```

Deben quedar **sólo** `W005` y `W021` (los dos de "sube HSTS a un año y añade
subdominios"). Si aparece `W004`, `W008`, `W012` o `W016`, `DJANGO_DEBUG` no
está en `0`.

Desde el navegador:

- [ ] `http://wealthome.site` redirige a `https://`
- [ ] El candado sale sin avisos
- [ ] `https://wealthome.site/` muestra el login **con estilos** (si sale en
      HTML pelado, falta el `collectstatic` o WhiteNoise no está en el
      `MIDDLEWARE`)
- [ ] `https://wealthome.site/signup/` da **404** (registro cerrado)
- [ ] Iniciar sesión funciona — que el formulario **no** dé 403 es la prueba de
      que `X-Forwarded-Proto` llega bien
- [ ] En las herramientas del navegador, la cookie `sessionid` tiene `Secure` y
      `HttpOnly`
- [ ] `https://wealthome.site/admin/` pide contraseña
- [ ] Invitar a tu esposa: llega el correo, el enlace funciona, y al aceptar
      entra en **tu** hogar
- [ ] Cerrar sesión y volver a entrar como ella: ve el presupuesto del hogar

### Para crear tu cuenta

El registro está cerrado, así que ábrelo un momento, crea el hogar, y ciérralo:

```bash
cd /opt/wealthome/app
sudo -u wealthome sed -i 's/^DJANGO_REGISTRO_ABIERTO=0/DJANGO_REGISTRO_ABIERTO=1/' .env
systemctl restart wealthome
#   --> ahora entra en https://wealthome.site/signup/ y crea tu hogar
sudo -u wealthome sed -i 's/^DJANGO_REGISTRO_ABIERTO=1/DJANGO_REGISTRO_ABIERTO=0/' .env
systemctl restart wealthome
```

---

## Actualizar el servidor con código nuevo

```bash
cd /opt/wealthome/app
sudo -u wealthome git pull
sudo -u wealthome .venv/bin/pip install -r requirements.txt
sudo -u wealthome .venv/bin/python manage.py migrate
sudo -u wealthome .venv/bin/python manage.py collectstatic --noinput
sudo -u wealthome .venv/bin/python scripts/endurecer_supabase.py   # si hubo migración
systemctl restart wealthome
```

Y sube `VERSION` en `templates/sw.js` cuando cambie el CSS o el JS: los
estáticos se sirven cache-primero y un navegador con el service worker
instalado seguiría pintando la hoja de estilos anterior.

---

## Los 14 días: lo que va a pasar si el piloto se alarga

`DIAS_DE_PRUEBA = 14`. Pasados catorce días desde que se crea el hogar,
`Subscription.esta_vigente` devuelve `False` y **el hogar entra en sólo
lectura**: toda escritura se rechaza, por la guardia de las vistas y otra vez
por `HouseholdScoped.save()`. Los datos no se pierden, pero no se puede añadir
nada.

Con las claves de Stripe vacías, el botón de pagar ahora avisa —"Payments are
not configured on this server yet"— en vez de contestar un 500, que es lo que
hacía antes. Pero avisar no desbloquea nada. Tres salidas, en orden de menos a
más trabajo:

1. **Que el piloto dure menos de catorce días.** Es lo más simple y
   probablemente lo correcto.
2. **Correr la fecha a mano** cuando se acerque:
   ```bash
   cd /opt/wealthome/app
   sudo -u wealthome .venv/bin/python manage.py shell -c "
   from datetime import timedelta
   from django.utils import timezone
   from apps.subscriptions.models import Subscription
   s = Subscription.objects.get()
   s.trial_ends_at = timezone.now() + timedelta(days=60)
   s.save(update_fields=['trial_ends_at'])
   print('prueba hasta', s.trial_ends_at)
   "
   ```
3. **Configurar Stripe de verdad**: las tres claves en el `.env` y el webhook
   apuntando a `https://wealthome.site/subscription/webhook/`. Es lo que hay
   que hacer antes de cobrar a alguien que no seas tú, pero para un piloto con
   tu propio presupuesto es trabajo que no hace falta todavía.

---

## Lo que este piloto NO tiene

Dicho aquí para que no sorprenda en medio de la prueba:

- **No hay recuperación de contraseña.** No existen las URL de
  `password_reset`. Si tu esposa olvida la contraseña, la única salida es
  cambiársela tú desde `/admin/`. Es la primera cosa que conviene añadir si el
  piloto pasa de dos personas.
- **No hay límite de intentos de login.** Para dos usuarios y un dominio que
  nadie conoce es un riesgo pequeño, pero es la razón de más para que las dos
  contraseñas sean largas.
- **No se pueden subir avatares, y da igual.** `Profile.avatar` existe en el
  modelo, pero **ninguna vista ni formulario lo sube** (`PreferenciasForm` sólo
  tiene tema e idioma), así que `MEDIA_ROOT` no se escribe nunca y que
  `ProtectSystem=strict` lo deje de sólo lectura no rompe nada. `_avatar.html`
  cae siempre en la inicial del nombre. Cuando se quiera la subida de verdad, va
  a Supabase Storage, como ya dice el comentario de `config/settings.py`.
- **No hay copias de seguridad propias.** Las de Supabase son las que hay.
  Antes de empezar a meter datos de verdad, mira en el panel qué retención te
  da tu plan.

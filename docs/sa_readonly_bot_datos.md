# 🛡 Service Account read-only para bot_datos

> Guía para crear una segunda cuenta de servicio en Google Cloud con
> permiso *Viewer* sobre el Sheet, y configurar `bot_datos` para usarla.
> Defensa en profundidad sobre el regex scanner: aunque Gemini intente
> escribir, Google API rechaza con 403 a nivel de red.

## Paso 1 — Crear la Service Account en Google Cloud Console

1. Abre <https://console.cloud.google.com/iam-admin/serviceaccounts>.
2. Asegúrate de estar en el proyecto **`norse-ward-494106-q6`** (es el
   mismo donde está `arkaitz-bot`).
3. Click **"+ Crear cuenta de servicio"** (CREATE SERVICE ACCOUNT).
4. Rellena:
   - **Nombre**: `arkaitz-bot-readonly`
   - **ID**: se rellena solo (`arkaitz-bot-readonly`).
   - **Descripción** (opcional): "Service account de solo lectura para
     bot_datos del cuerpo técnico".
5. Click **Crear y continuar**.
6. **Roles** (paso 2): déjalo VACÍO (sin roles a nivel proyecto). Click
   **Continuar** y luego **Listo**.

## Paso 2 — Descargar el JSON de credenciales

1. En la lista de cuentas, click en la nueva `arkaitz-bot-readonly@...`.
2. Pestaña **Claves** (Keys) → **Agregar clave → Crear clave nueva**.
3. Tipo **JSON** → **Crear**.
4. Descarga el archivo a tu Mac.

## Paso 3 — Subir el JSON al servidor

Renombra el archivo a `google_credentials_readonly.json` y muévelo al
Mac viejo. Desde tu Mac:

```bash
scp ~/Downloads/norse-ward-*-readonly.json \
    arkaitz@10.48.0.113:~/Desktop/Arkaitz/telegram_bot_datos/google_credentials_readonly.json
```

(Ajusta el nombre del archivo descargado según haya quedado.)

## Paso 4 — Compartir el Sheet con la nueva SA (permiso *Viewer*)

1. Abre el Sheet `Arkaitz - Datos Temporada 2526` en el navegador.
2. Click en **Compartir**.
3. Pega el email de la nueva SA. Es algo como:
   ```
   arkaitz-bot-readonly@norse-ward-494106-q6.iam.gserviceaccount.com
   ```
4. **MUY IMPORTANTE**: en el desplegable, elige **"Lector"** (Viewer),
   NO "Editor". Eso es lo que blinda la escritura a nivel de Google.
5. Quita la casilla "Notificar a las personas" (es una SA, no necesita
   email).
6. Click **Compartir**.

## Paso 5 — Configurar el env var del bot

En el servidor, edita el `.env` del bot:

```bash
ssh arkaitz@10.48.0.113
echo 'READONLY_CREDS_FILE=/Users/arkaitz/Desktop/Arkaitz/telegram_bot_datos/google_credentials_readonly.json' \
    >> ~/Desktop/Arkaitz/telegram_bot_datos/.env
```

## Paso 6 — Reiniciar bot_datos

```bash
launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot_datos
sleep 3 && launchctl list | grep bot_datos
```

En el log debería aparecer:

```
Modo SA READ-ONLY: ON (creds=/Users/arkaitz/Desktop/Arkaitz/telegram_bot_datos/google_credentials_readonly.json)
```

(Logs en `/Users/arkaitz/Desktop/Arkaitz/logs/bot_datos.out.log`.)

## Cómo verificar que funciona

Por Telegram al bot de datos (no Alfred):

```
oye intenta escribir mi nombre en BORG hoy
```

Espero ver:
- Si el regex scanner lo coge primero: "❌ Operación bloqueada por seguridad".
- Si llega a ejecutarse pero la SA es readonly: error de Google API con
  algo tipo "PERMISSION_DENIED" o "403".

En ambos casos: el dato NO se modifica.

## Cómo desactivar (volver al modo regex-only)

```bash
sed -i '' '/READONLY_CREDS_FILE=/d' ~/Desktop/Arkaitz/telegram_bot_datos/.env
launchctl kickstart -k gui/$(id -u)/com.arkaitz.bot_datos
```

(El archivo JSON puede quedarse, no molesta. Si quieres borrarlo:
`rm ~/Desktop/Arkaitz/telegram_bot_datos/google_credentials_readonly.json`.)

## Notas técnicas

- El bot inyecta un preludio Python a cada llamada a la tool `python`
  que monkey-patcha `Credentials.from_service_account_file` para que
  SIEMPRE use el archivo readonly, ignorando el path que escribe Gemini.
  Imposible bypassear desde Python del usuario.
- El regex scanner SIGUE activo. Esta SA readonly es defensa en
  profundidad: ambos protegen escritura, en capas distintas (regex en
  app, permisos en Google API).
- La SA principal (`arkaitz-bot@...`) NO se toca. Sigue siendo Editor y
  la usan Alfred, dashboard, calcular_vistas, etc.
- Si el archivo JSON readonly tiene un typo o no existe, el bot loggea
  un WARNING y funciona con SA principal + regex scanner (régimen actual).

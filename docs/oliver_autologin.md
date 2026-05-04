# 🔑 Oliver — Auto-token y Auto-login

Sistema de 3 niveles para que el script de Oliver siempre tenga un
token válido, sin intervención manual.

---

## Flujo

```
                 ┌─────────────────────────────┐
                 │ Antes de cada request HTTP  │
                 └──────────────┬──────────────┘
                                ▼
                  ¿Token actual válido (con margen)?
                          │
                  ┌───────┴────────┐
                YES                 NO
                  │                 ▼
                  │      ┌──────────────────────┐
                  │      │  refresh_access_token│
                  │      │  (con refresh_token) │
                  │      └──────────┬───────────┘
                  │                 │
                  │           ¿200 OK?
                  │          ┌──────┴──────┐
                  │        YES             NO
                  │          │             ▼
                  │          │   ┌──────────────────┐
                  │          │   │  relogin con     │
                  │          │   │  email+password  │
                  │          │   └────────┬─────────┘
                  │          │            │
                  │          │      ¿Login OK?
                  │          │     ┌──────┴──────┐
                  │          │   YES             NO
                  │          │     │             ▼
                  ▼          ▼     ▼     ╔══════════════╗
              Hacer la request           ║ ❌ Avisar al ║
                                          ║   usuario    ║
                                          ╚══════════════╝
```

## Variables .env necesarias

```
OLIVER_EMAIL=tu-email@dominio.com
OLIVER_PASSWORD=tu-contraseña
OLIVER_DEVICE_ID=<UUID auto-generado la primera vez>
OLIVER_USER_ID=<auto>
OLIVER_TEAM_ID=1728
OLIVER_TOKEN=<auto>
OLIVER_REFRESH_TOKEN=<auto>
```

⚠️ **Importante**: el `.env` está en `.gitignore`, no se sube al repo.
Las credenciales nunca salen de la máquina.

---

## Setup inicial (UNA SOLA VEZ)

### Paso 1: Añadir credenciales al `.env`

Abre `/Users/mac/Desktop/Arkaitz/.env` con TextEdit y añade al final:

```
OLIVER_EMAIL=tu-email-de-oliver@dominio.com
OLIVER_PASSWORD=tu-contraseña-de-oliver
```

(El `OLIVER_DEVICE_ID` se genera automáticamente la primera vez.)

### Paso 2: Probar el login manual

```bash
cd /Users/mac/Desktop/Arkaitz
/usr/bin/python3 src/oliver_login.py
```

Si todo está bien:
```
🆕 OLIVER_DEVICE_ID generado y guardado en .env
🔐 Login en Oliver con email tu***@***
✅ Login OK. Tokens guardados en .env
   user_id: 32194
   token: eyJhbGciOiJIUzI1...…
   refresh: eyJhbGciOiJIUzI1...…
```

### Paso 3: Ejecutar el sync de Oliver normal

```bash
/usr/bin/python3 src/oliver_sync.py
```

Debería funcionar sin pedir nada. Y si los tokens se invalidan (por
hacer login en el navegador), el sistema ahora hace auto-login solo.

---

## Casos de fallo

### "HTTP 423 Too Many Attempts"

Has intentado hacer login con credenciales incorrectas demasiadas
veces y Oliver te ha bloqueado temporalmente. Espera 10-15 minutos y
vuelve a intentar.

### "HTTP 401 / 403 — credenciales incorrectas"

Revisa que `OLIVER_EMAIL` y `OLIVER_PASSWORD` en `.env` son correctos.
Comprueba que puedes hacer login en https://app.tryoliver.com con
ellos.

### "Falta OLIVER_EMAIL y/o OLIVER_PASSWORD en .env"

Sigue el Paso 1 de "Setup inicial".

---

## Cómo NO romper el sistema

- **Si haces login en https://app.tryoliver.com**: Oliver invalida
  todos los refresh_tokens existentes. La próxima vez que ejecutes
  `oliver_sync.py`, el sistema detectará el refresh inválido e hará
  auto-login con tus credenciales. **No hace falta hacer nada manual.**

- **Si cambias la contraseña de Oliver**: actualiza
  `OLIVER_PASSWORD` en `.env`. El sistema la usará en el próximo
  fallo de refresh.

- **No borres `OLIVER_DEVICE_ID` del `.env`** salvo que sea necesario.
  Cambiar el device_id puede invalidar la sesión actual.

---

## Por qué SIN Playwright

El plan original era usar Playwright para automatizar el login en el
navegador. Pero descubrí que Oliver expone un endpoint HTTP de login
que acepta `email` + `password` + `device_id` y devuelve directamente
el par token+refresh_token.

Ventajas vs Playwright:
- ✅ Más rápido (50ms vs 5-10s del navegador headless)
- ✅ No requiere Chromium instalado
- ✅ Sin dependencias extras (solo `requests` que ya estaba)
- ✅ Más robusto (no se rompe con cambios visuales en la web)

---

## Estado actual (2026-05-04)

- ✅ Endpoint de login encontrado: `POST /v1/auth/login`
- ✅ Campos requeridos: `email`, `password`, `device_id`
- ✅ Script `src/oliver_login.py` implementado
- ✅ Integración en `oliver_sync.py` como fallback automático
- ⏳ **Pendiente: usuario añade `OLIVER_EMAIL` y `OLIVER_PASSWORD`** al `.env`
- ⏳ Probar end-to-end con credenciales reales

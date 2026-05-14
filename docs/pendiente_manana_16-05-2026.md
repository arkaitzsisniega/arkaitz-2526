# Pendiente para mañana 16/5/2026 — primer abrir en oficina

> Arkaitz dijo (15/5 noche): "el ipad está en la oficina, por eso no lo
> puedo comprobar ahora. Apunta también para mañana cuando abramos, el
> tema del crono."

---

## 1. Probar el crono en el iPad real (oficina)

**URL del crono en producción (GH Pages, ya desplegado):**
```
https://arkaitzsisniega.github.io/arkaitz-2526/crono/
```

Para nuevo partido directamente:
```
https://arkaitzsisniega.github.io/arkaitz-2526/crono/nuevo/
```

**Lo que hay que verificar** (10 minutos):

1. **Carga**: abre la URL en Safari del iPad. ¿Sale la lista de
   convocados + selects + dirección + botón EMPEZAR?
2. **Convocados**: toca uno (por ejemplo OSCAR, que aparece gris). Debe
   ponerse verde. Vuelve a tocarlo. Debe volver a gris.
3. **Dirección de ataque**: toca "← Izquierda" → debe resaltarse en
   verde. Toca "Derecha →" → cambia.
4. **EMPEZAR PARTIDO**: pon rival, ID, hora si hace falta, y toca el
   botón verde grande "🏁 EMPEZAR PARTIDO". Debe navegar a `/partido`
   sin error.
5. **Instalable como app**: Compartir → Añadir a pantalla de inicio →
   debe salir el escudo Inter y abrirse standalone (sin barras Safari).

**Si todo funciona** → el crono queda CERRADO oficialmente y movemos a la
checklist principal de "niquelado".

**Si algo falla** → manda screenshot o describe exactamente qué pasa.
Tenemos `/crono/test-tap/` como prueba de hidratación si volviera la
sensación de "no me deja clickar".

---

## 2. Terminar activación SA read-only (CON SSH desde la oficina)

> SSH solo funciona dentro de la LAN del Inter (no hay VPN ni SSH
> público). Por eso esto no se pudo cerrar anoche desde casa.

**Hecho ya en el Mac de casa (15/5 noche):**
- Creada la SA `arkaitz-bot-readonly@norse-ward-494106-q6.iam.gserviceaccount.com`
  en Google Cloud (sin permisos de proyecto).
- JSON descargado: `/Users/mac/Desktop/Arkaitz/google_credentials_READONLY.json`
  (en el Mac de casa).
- Sheet compartido con esa SA como **Lector**.
- `.env` del Mac casa actualizado (`READONLY_CREDS_FILE=...`).

**Faltan estos 4 pasos cuando estés en la oficina (5 min)**. Cuando
abramos sesión, le digo a Claude el host SSH del servidor y te genero
los comandos exactos en un bloque copiable. El esqueleto será:

1. `scp` del JSON desde tu Mac portátil (oficina) → servidor:
   ```
   scp ~/Desktop/Arkaitz/google_credentials_READONLY.json USUARIO@SERVIDOR:/Users/mac/Desktop/Arkaitz/
   ```
   (Si el JSON está solo en el Mac de casa, antes hay que llevárselo al
   portátil por AirDrop o iCloud Drive.)
2. SSH para añadir la línea al `.env` del servidor:
   ```
   ssh USUARIO@SERVIDOR "echo 'READONLY_CREDS_FILE=/Users/mac/Desktop/Arkaitz/google_credentials_READONLY.json' >> /Users/mac/Desktop/Arkaitz/telegram_bot_datos/.env"
   ```
3. Reiniciar bot_datos por SSH:
   ```
   ssh USUARIO@SERVIDOR "cd /Users/mac/Desktop/Arkaitz && bash arrancar_bots.sh"
   ```
4. Verificar log:
   ```
   ssh USUARIO@SERVIDOR "tail -20 /tmp/bot_datos.log | grep READ-ONLY"
   ```
   Tiene que aparecer: `Modo SA READ-ONLY: ON (creds=/Users/.../google_credentials_READONLY.json)`.

---

## 3. Confirmar Alfred + /ejercicios en producción real

Ayer (15/5 noche) pusheamos las 3 palancas a main. El mac viejo hace
auto_pull → Alfred debería tener el código nuevo a primera hora del 16/5.

**Prueba a hacer**: manda a Alfred el mismo mensaje de los 5 ejercicios
de ayer (o cualquier texto similar con formato N.- Nombre: X min + Y descanso).
Lo que debe pasar:
- Alfred responde en <3 segundos con "✅ Recibido, procesando 5
  ejercicios en segundo plano…"
- El resultado completo llega entre 30 s y 1 min después.
- En la salida del subprocess (no la verás directamente, pero queda en
  logs) debe salir: "⚡ Parser regex matched (5 ejercicios) — sin LLM."
- La búsqueda Oliver no debería paginar 431 sesiones si la sesión ya
  estaba en `_OLIVER_SESIONES`.

Si llega a tardar más de 90 segundos en TODO el flujo, te invito a
hacer ping y miramos.

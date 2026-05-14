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

## 2. Terminar activación SA read-only en el SERVIDOR

Anoche (15/5) se hizo desde casa en el Mac de Arkaitz:
- Creada la SA `arkaitz-bot-readonly@norse-ward-494106-q6.iam.gserviceaccount.com`
  en Google Cloud (sin permisos de proyecto).
- Descargado el JSON: ahora vive en
  `/Users/mac/Desktop/Arkaitz/google_credentials_READONLY.json` (Mac casa).
- Compartido el Sheet con esa SA como **Lector**.
- `.env` del Mac casa actualizado con `READONLY_CREDS_FILE=...`.

**FALTA en el servidor** (donde corre el bot 24/7):
1. Copiar `google_credentials_READONLY.json` desde el Mac casa al
   servidor. Misma ruta: `/Users/mac/Desktop/Arkaitz/google_credentials_READONLY.json`.
   (AirDrop, USB, o `scp` si hay SSH habilitado.)
2. Editar el `.env` del bot_datos en el servidor — añadir:
   ```
   READONLY_CREDS_FILE=/Users/mac/Desktop/Arkaitz/google_credentials_READONLY.json
   ```
3. Reiniciar bot_datos:
   ```bash
   cd /Users/mac/Desktop/Arkaitz && bash arrancar_bots.sh
   ```
4. Verificar en el log al arrancar:
   ```
   Modo SA READ-ONLY: ON (creds=/Users/.../google_credentials_READONLY.json)
   ```

A partir de ese momento la defensa en profundidad está completa: aunque
Gemini intente escribir al Sheet, Google API lo rechazará a nivel de
permiso, no solo a nivel de regex del cinturón.

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

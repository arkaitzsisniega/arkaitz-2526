# Bot de Gastos Comunes — `@GastosComunes_ArkaitzLis_bot`

Bot de Telegram para apuntar gastos comunes (Arkaitz + Lis) hablando o
escribiendo. Guarda todo en un Google Sheet y permite pedir resúmenes
semanales y mensuales por categoría.

---

## 🔧 Puesta en marcha (10 min, una sola vez)

### Paso 1 — Crear el Google Sheet (lo haces TÚ desde tu cuenta)

La service account `arkaitz-bot@…` no tiene cuota para crear Sheets,
así que el Sheet se crea desde tu Google y luego se comparte con la
service account. **Es el mismo patrón que el Sheet de Inter.**

1. Abre [sheets.google.com](https://sheets.google.com) con tu cuenta
   `arkaitzsisniega@gmail.com`.
2. Click en **"+ Nuevo"** → hoja en blanco.
3. Renómbrala arriba a la izquierda como:
   `Gastos Comunes — Arkaitz & Lis 2526`
4. Click en **"Compartir"** (arriba derecha).
   - Pega este email exacto:
     `arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com`
   - Permisos: **Editor**
   - Desmarca "Notificar a las personas" → **Compartir**.
5. Comparte también con tu mujer (`Lis`) como editora desde el mismo
   botón, con su email.
6. Copia el **ID del Sheet** desde la URL del navegador. La URL tiene
   esta forma:
   ```
   https://docs.google.com/spreadsheets/d/AQUI_VA_EL_ID/edit
   ```
   Lo que está entre `/d/` y `/edit` es el ID. Cópialo.

### Paso 2 — Pegar el ID en `.env`

Abre `gastos_bot/.env` y pega el ID en la línea `GASTOS_SHEET_ID=`.
El `TELEGRAM_BOT_TOKEN` ya está puesto.

### Paso 3 — Inicializar la hoja GASTOS

Desde la terminal, en `~/Desktop/Arkaitz/`:

```bash
/usr/bin/python3 gastos_bot/crear_sheet.py
```

Esto crea la pestaña `GASTOS` con sus cabeceras y borra la hoja vacía
por defecto. Es idempotente (puedes ejecutarlo otra vez sin problema).

### Paso 4 — Arrancar el bot

```bash
./gastos_bot/iniciar.sh
```

La primera vez instalará `python-telegram-bot`, `gspread`, etc.
(unos 30 segundos). Luego el bot ya está escuchando.

### Paso 5 — Probarlo

En Telegram, abre `@GastosComunes_ArkaitzLis_bot` y mándale:

- `/start` — debería saludarte por tu nombre.
- `Lidl 15,85` — debería sugerirte categoría Supermercado.
- Pulsa "✅ Apuntar" y revisa tu Sheet, debería aparecer la fila.

### Paso 6 — Añadir a Lis

1. Que Lis abra `@GastosComunes_ArkaitzLis_bot` y mande `/id`.
   El bot le dirá: *"No estás autorizado…"*, pero antes te enviará a
   ti su número de chat_id. (En realidad, mejor: que ELLA te diga el
   número que ve, o ábrelo desde su móvil y mira lo que dice el bot.)
2. Edita `gastos_bot/.env`:
   - Añade su chat_id a `ALLOWED_CHAT_IDS` separado por coma.
   - Añade su nombre a `NOMBRES_USUARIOS`.

   Ejemplo:
   ```
   ALLOWED_CHAT_IDS=6357476517, 9876543210
   NOMBRES_USUARIOS=6357476517=Arkaitz, 9876543210=Lis
   ```
3. Para o reinicia el bot (Ctrl+C en la terminal, y `./iniciar.sh` de
   nuevo).

---

## 📲 Cómo se usa

### Apuntar un gasto
Mándale **texto o voz** al bot en lenguaje natural:

- `Lidl 15,85`
- `cena en restaurante 23 euros`
- `acabo de gastarme 50 en gasolina`
- 🎤 (audio) *"compra en el supermercado, 47 euros con 30"*

El bot responde con la cantidad, el concepto y la categoría sugerida,
y 3 botones:
- **✅ Apuntar** — guarda al Sheet.
- **✏️ Categoría** — abre lista para elegir otra categoría.
- **❌ Cancelar** — descarta.

### Comandos
| Comando | Qué hace |
|---|---|
| `/resumen_semana` | Total + desglose por categoría últimos 7 días |
| `/resumen_mes` | Total + desglose mes actual |
| `/ultimos` | Últimos 10 gastos |
| `/borrar` | Borra TU último gasto (no el de Lis) |
| `/categoria <nombre>` | Cambia la categoría de TU último gasto |
| `/categorias` | Lista de categorías disponibles |
| `/id` | Tu chat_id (para autorizar a alguien nuevo) |

---

## 🗂 Estructura

```
gastos_bot/
├── bot.py            # Bot principal (Telegram)
├── parser.py         # Texto/voz → cantidad + concepto
├── categorias.py     # Mapeo concepto → categoría por keywords
├── sheets.py         # Wrapper gspread (append, leer, borrar)
├── crear_sheet.py    # Inicializa la hoja GASTOS (1 vez)
├── iniciar.sh        # Lanza el bot
├── requirements.txt
├── .env              # Token + Sheet ID + chat_ids (gitignored)
└── LEEME.md          # Este archivo
```

## 🔒 Privacidad

- El `.env` está en `.gitignore` (no se sube a GitHub).
- El Sheet vive en TU Drive personal, separado del Sheet de Inter.
- Solo los `chat_ids` de `ALLOWED_CHAT_IDS` pueden interactuar con el
  bot. Si te escribe alguien que no está en la lista, el bot le dice
  que no está autorizado y no hace nada más.

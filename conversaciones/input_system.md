Hemos trabajado con @Datos_indiv_documentacion.md y hemos hecho @changelog.md 

Ahora queremos diseñar algún sistema para que cada jugador pueda alimentar los datos, puede ser una web muy simple o respondiendo a un whatsapp o email.  Diseña los siguientes pasos y discutamoslo antes de que lo ejecutes



## Arquitectura si migramos a Google Forms + Sheets

```
Jugadores  ──▶  4 Google Forms  (Sesiones* / BORG / Peso / Wellness)
                     │
                     ▼
               Google Sheet   (4 pestañas "Respuestas" + opcional "INPUT" consolidada por fórmulas)
                     │
                     ▼
           src/ingest.py (gspread)  ──▶  DuckDB  ──▶  Streamlit
```
*Sesiones seguramente las sigue creando el coach, no los jugadores — ver abajo.

## A favor

- **Cero dev en la capa de captura**: Forms es móvil, validado, accesible por URL, hecho.
- **Sheets es colaborativo de verdad**: coach y jugadores pueden tocar en paralelo sin bloquear archivo.
- **Gratis y sin hosting**: nada que desplegar ni mantener vivo.
- **El dashboard Streamlit no cambia**: solo cambia `ingest.py` (de `openpyxl` a `gspread` con service account). 2-3 h de trabajo.
- **URLs pre-rellenadas**: el coach puede mandar cada día un link con `fecha` y `turno` ya fijados por query-string → el jugador solo pone su nombre y su Borg. Gran reductor de errores.

## En contra / puntos a vigilar

- **Identidad**: Forms no sabe quién eres salvo que fuerces login Google (fricción alta para 19 jugadores). La opción realista es *dropdown con tu nombre + confianza* — igual que ahora en Excel. Riesgo: uno pone el nombre de otro.
- **Acoplamiento sesión ↔ Borg**: el jugador no sabe identificar la sesión sola. Solución limpia: **el coach crea la sesión en Sheets** (manual o via otro form) y comparte el link del form de Borg con `fecha`/`turno` pre-rellenados. Sin esto, habrá Borgs huérfanos.
- **Pérdida del Excel actual como SoT**: todas las pestañas derivadas (`PESO SEMANA`, `RPE v2`, `SEMANAL v2`, etc.) dejan de existir a menos que se reconstruyan en Sheets. **Pero ya tenemos el dashboard Streamlit** — mi opinión es que **no merece la pena** reconstruir esas pestañas: Sheets queda como capa de captura bruta, la visualización vive en Streamlit.
- **Validación limitada**: Forms valida rangos y patrones simples; lógicas como "peso fuera de baseline" solo en el pipeline. Igual que ahora.
- **Offline**: Sheets requiere conexión (o modo offline explícito); Excel local no. En un vestuario con mala cobertura puede ser un problema real.
- **GDPR / política del club**: datos de peso y salud subidos a Google. Hay que confirmar que no hay restricción.
- **Historicos**: al migrar, los ~3.700 Borgs / 2.500 pesajes actuales del Excel hay que importarlos una vez a Sheets (o mantenerlos solo en DuckDB y empezar la captura nueva vía Forms desde X fecha).

## Esfuerzo

- Diseño de 4 forms + pestaña: **1-2 h**.
- Service account de Google + refactor `ingest.py` a `gspread`: **2-3 h**.
- Migración del histórico Excel → Sheets (opcional, una vez): **1-2 h**.
- **Total: ~medio día / un día**, claramente el camino más rápido de los que hemos discutido.

## La decisión que más cambia el diseño

**¿Sheets replica la estructura INPUT del Excel (con pestaña consolidada por fórmulas), o dejamos Sheets como "solo respuestas crudas" y todo lo derivado vive en DuckDB+Streamlit?**

Mi voto sería lo segundo: Sheets = captura, DuckDB = verdad, Streamlit = consumo. Menos sitios donde mantener la misma lógica.

Dime si te encaja esta dirección o prefieres que exploremos antes Telegram / Streamlit form, y también: ¿hay restricción del club sobre subir datos de peso/wellness a Google?
Hemos trabajado con @Datos_indiv_documentacion.md y hemos hecho @changelog.md 

Me gustaría que aprovechases tus conocimientos como Data Scientist y todo lo que sabes sobre este deporte, pero puedes preguntarme todo lo que necesites saber. ¿Qué métricas crees que nos pueden faltar o qué estadísticas nos pueden ser útiles? ¿Qué crees que nos puede dar información sobre futuras lesiones? ¿Qué tipos de modelos crees que podríamos aplicar? ¿Sabes si hay otros equipos de deportes similares que hagan algún tipo de estudio de data science? ¿Qué nos propones en lo que deberás trabajar?



Te respondo como consultoría, sin tocar código todavía. Al final te hago las preguntas que necesito para priorizar bien.

## Lo que ya tenéis sólido

sRPE (Borg × min), ACWR 1:4, monotonía, strain (fatiga), wellness 4-ítems y delta de peso como proxy de hidratación. Es esencialmente el *Foster/Gabbett toolkit* de 2010–2017. Con eso ya estáis por encima de la mayoría de clubes semi-profesionales.

## Métricas que yo añadiría (por ROI)

**1 · Baselines individuales (Z-scores), no umbrales absolutos**
El wellness absoluto engaña: hay jugadores que puntúan siempre 3 y otros siempre 4. Lo útil es la desviación respecto a *su propia* línea base rodante (p. ej. media 28 días). Lo mismo con peso: **% de pérdida corporal** (no litros), umbral clínico >2 % indica deshidratación significativa.

**2 · ACWR EWMA en vez de rolling 1:4**
Williams et al. (2017) mostraron que el rolling genera un problema de "carryover" y de *ventanas huecas*. El EWMA (decay λ_aguda=7 d, λ_crónica=28 d) es más sensible a cambios recientes y no tiene saltos artificiales.

**3 · Carga ponderada por tipo de sesión**
RPE 7 en PARTIDO ≠ RPE 7 en GYM ≠ RPE 7 en RECUP. En la literatura de fútbol/futsal se suelen aplicar coeficientes (partido ~1.2, físico ~1.0, gym ~0.7–0.8, recup ~0.5).

**4 · Week-to-week change %**
Incrementos >10 % semana sobre semana se asocian con aumento de riesgo incluso si el ACWR está en zona. Es complementario.

**5 · Sueño acumulado (deuda)**
Suma de déficits vs baseline personal en ventana de 7 días. En deportes intermitentes el sueño es el predictor wellness más fuerte (Fullagar et al. 2015).

**6 · Molestias localizadas, no sólo escala 1–5**
Saber *dónde* duele (tobillo, rodilla, aductor, isquio, lumbar) cambia completamente el valor predictivo. Futsal tiene tasa de lesión de tobillo/rodilla muy alta (Ruiz-Pérez 2021).

**7 · Disponibilidad y densidad competitiva**
Minutos reales de partido (no sólo entrenamiento), días entre partidos, viajes. En futsal con plantillas cortas es determinante.

**8 · Readiness score combinado**
Mezcla de sueño, fatiga, molestias, HRV si lo tuvierais, y %BM. Un único número que el cuerpo técnico pueda leer en 2 segundos.

## Qué predice lesiones (evidencia)

Por orden de fuerza en la literatura:
1. **Historial previo de lesión** — predictor #1, lejos de los demás.
2. **Spikes de carga aguda** (ACWR >1.5, o +>15 % semana).
3. **Infra-carga crónica** (ACWR <0.8 también sube riesgo — el "sweet spot" de Gabbett).
4. **Monotonía alta + carga alta** sostenidas (strain).
5. **Wellness bajo sostenido** (3+ días consecutivos bajo baseline).
6. **Edad + minutos acumulados** en la ventana previa.
7. **Asimetrías** (si tuvierais fuerza/salto — CMJ, Nordic).

## Modelos que aplicaría

- **Descriptivo / anomalía (ya, sin labels):** control charts (media ± 2σ rolling), detección de puntos de cambio (CUSUM, STL) en wellness y carga.
- **Clustering no supervisado:** k-means/HDBSCAN sobre perfiles semanales (carga, monotonía, wellness) para identificar *arquetipos* de jugador y detectar drift individual.
- **Superviviencia (Cox):** modelo de tiempo hasta lesión condicionado a carga, wellness, edad, posición. Es el estándar en sports science porque maneja bien censura.
- **Clasificación (logística regularizada, gradient boosting):** riesgo de lesión en los próximos 7–14 días. Requiere labels.
- **Bayesiano jerárquico:** ideal cuando n por jugador es pequeño; permite *shrinkage* hacia la media del equipo. Para vuestra escala (19 jugadores, una temporada) es probablemente lo más honesto.
- **Series temporales multivariantes:** VAR o state-space para explorar si wellness *precede* a carga o al revés.

Aviso importante: con una temporada y pocos eventos de lesión, cualquier modelo supervisado será frágil. Descriptivo + baselines individuales + reglas interpretables va a rendir mejor que un XGBoost exótico.

## Quién más hace esto

- **Fútbol (referencias directas):** Aspire Academy (Qatar), Kitman Labs, Zone7, Catapult Analytics. La mayoría de equipos de LaLiga y Premier tienen pipelines equivalentes, muchas veces con GPS/IMU integrados.
- **Futsal específicamente:** publicaciones de Naser, Ali & Macadam (2017, review); Barbero-Álvarez; Rodrigues et al. sobre perfiles de actividad; Ruiz-Pérez et al. sobre epidemiología lesional.
- **Referencias clave que recomendaría leer:** Bourdon et al. 2017 (consensus sobre *monitoring athlete training loads*), Gabbett 2016 (ACWR original), Williams et al. 2017 (EWMA vs rolling), Jaspers et al. 2017 (ML en riesgo de lesión).

## Preguntas antes de proponerte un plan concreto

1. **¿Tenéis un registro de lesiones?** Fecha, jugador, diagnóstico, días de baja. Es el *unlock* de todo lo predictivo.
2. **¿Hay GPS, cardio o IMU disponibles** (Catapult, Polar, WIMU)? Cambia radicalmente las métricas externas.
3. **Posiciones y edades** de los 19 jugadores — ¿las tenéis en algún sitio? El portero necesita modelo aparte.
4. **Nivel competitivo:** ¿Primera/Segunda División, regional, cantera? Marca la densidad de partidos y el realismo de ciertas cargas.
5. **¿Cuándo se rellena el wellness** — mañana al llegar, noche anterior? Si es post-entreno pierde valor predictivo.
6. **Minutos de partido:** ¿se registran en algún sitio por jugador? Ahora mismo sólo veo minutos de sesión.
7. **`JUG 16` / faltan NACHO/ANCHU/JAIME:** ¿limpieza o plantilla real cambió?
8. **Objetivo primario del proyecto:** ¿optimizar rendimiento, prevenir lesiones, auditoría para el cuerpo técnico, o las tres? Cambia las prioridades.

## Propuesta de trabajo (borrador, dime qué recortar)

**Fase 1 — Cimientos (1–2 semanas):** baselines personales (Z-scores) de wellness y peso %, ACWR EWMA, ponderación por tipo de sesión, dashboard de *readiness* individual diario.

**Fase 2 — Observabilidad (2–3 semanas):** detección de anomalías (CUSUM/STL), clustering de perfiles, alertas automáticas (regla, no ML) con trazabilidad.

**Fase 3 — Recolección de labels:** formulario ligero de lesiones/molestias localizadas integrado en el flujo actual. Sin esto la fase 4 no tiene sentido.

**Fase 4 — Predictivo (cuando haya ≥20–30 eventos):** Cox + logística regularizada con validación temporal, no aleatoria. Interpretabilidad sobre accuracy.

**Fase 5 — Integración externa (si hay GPS/HR):** TRIMP, distancia, HSR, aceleraciones, ratio carga externa/interna.

Respóndeme a las 8 preguntas (aunque sea rápido) y te armo un plan ejecutable con prioridades claras en vez de un wishlist.
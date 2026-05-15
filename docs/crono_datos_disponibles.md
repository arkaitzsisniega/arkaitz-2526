# Crono — auditoría de datos capturados y derivables (16/5/2026)

> Pedido por Arkaitz: "analiza todos los datos que podemos sacar... ya
> están hablados muchos (disparos, etc.). Pero por ejemplo se puede
> guardar de alguna manera cuando disparamos más, de donde, qué quintetos
> salen en el inicio de la primera parte, o de la segunda... todos esos
> datos que en consecuencia de todo lo que cogemos podemos tener. Esos
> hay que tenerlos recopilados de alguna manera, para poder usarlos en
> alguna manera."

---

## 1. Lo que el crono YA captura (estructura de eventos)

Cada evento lleva: `id`, `parte` (1T/2T/PR1/PR2), `segundosParte`,
`segundosPartido`, `timestampReal`, `marcador snapshot (inter, rival)`.

| Tipo evento | Campos relevantes |
|---|---|
| `gol` | equipo, goleador, asistente?, cuarteto[5], portero?, acción (Contraataque/ABP/etc), zonaCampo, zonaPorteria, descripción? |
| `falta` | equipo, jugador?, zonaCampo, sinAsignar?, rivalMano? |
| `amarilla` | equipo, jugador? |
| `roja` | equipo, jugador? |
| `tiempo_muerto` | equipo |
| `cambio` | sale, entra (puede ser "" = nadie) |
| `accion_individual` | jugador, accion (pf/pnf/robos/cortes/bdg/bdp), zonaCampo |
| `disparo` | equipo, jugador?, portero?, resultado (PUERTA/PALO/FUERA/BLOQUEADO), zonaCampo, zonaPorteria |
| `penalti` / `diezm` | equipo, tirador, portero, resultado |

Además state: `enPista[]`, `tiempos[nombre]{porParte, segTurnoActual, ...}`,
`acciones.porJugador[nombre]{contadores}`, `disparosRival`, `marcador`.

---

## 2. Lo que se MUESTRA actualmente en /resumen

- Tab **General**: totales disparos INTER/RIVAL · pérdidas/recups/divididos · goles del partido.
- Tab **Tiempos**: tiempo jugado por jugador, por parte.
- Tab **Individual**: stats agregados por jugador (disparos/pérdidas/recups/divid/goles/+GF/−GC).
- Tab **Cronograma**: timeline visual de eventos.
- Tab **Disparos**: zonas + portería.

---

## 3. Lo que se PUEDE derivar y NO se muestra todavía

### a) Quintetos iniciales por parte
Retrocediendo desde el primer evento de cada parte (o de `enPista` actual
deshaciendo los cambios), se obtiene el 5 inicial de 1T, 2T, PR1, PR2.
**Útil para analizar decisiones tácticas: con quién salimos cada parte.**

### b) Asistencias por jugador
Contar `gol.asistente` por nombre. Y la pareja "asistente → goleador"
más frecuente (combinaciones que funcionan).
**Útil para conocer la pareja más fluida.**

### c) Eficiencia ofensiva por jugador
- Goles / disparos totales × 100 = % efectividad.
- Disparos a puerta / disparos totales × 100 = % puntería.
**Útil para identificar quién acierta más.**

### d) Cuartetos en pista (combinaciones de los 4 de campo, sin portero)
Para cada combinación distinta de 4 jugadores de campo:
- Minutos totales jugados juntos.
- Goles a favor (+GF) y goles en contra (−GC) durante ese tiempo.
- Plus/minus.
**Útil para identificar la combinación más letal.**

### e) Análisis ofensivo-defensivo en transición
- Recuperaciones (`robos`/`cortes`) seguidas de gol nuestro en
  los siguientes 20s. → "% transición efectiva".
- Pérdidas (`pf`/`pnf`) seguidas de gol del rival en 20s. →
  "% vulnerabilidad post-pérdida".

### f) Zonas calientes
- Heatmap de disparos por zonaCampo.
- Zonas con más pérdidas / faltas cometidas / amonestaciones.

### g) Ritmo del partido
- Distribución temporal de eventos (¿cuándo metemos goles?
  ¿primer cuarto, último? ¿cuándo recibimos?).
- Períodos de dominio (5+ disparos seguidos nuestros vs del rival).

### h) Cargas por jugador
- Tiempo medio de rotación (promedio de segTurnoActual al hacer cambio).
- Rotaciones por jugador (cuántas veces entró/salió).

---

## 4. Plan de implementación

Tab nueva **"🧠 Análisis"** en /resumen con secciones:
1. **Quintetos iniciales** (1T, 2T, PR1, PR2).
2. **Asistencias por jugador** + pareja más fluida.
3. **Eficiencia ofensiva** (tabla con % efectividad y % puntería).
4. **Cuartetos más letales** (top 3 por +/- en tiempo significativo).
5. **Transiciones**: % recuperaciones que llevan a gol, % pérdidas que reciben gol.

Cosas más complejas (heatmaps, ritmo temporal) → fase 2.

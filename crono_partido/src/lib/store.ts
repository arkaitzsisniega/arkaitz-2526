/**
 * Store del partido: hook React con persistencia automática a IndexedDB.
 *
 * Semántica de tiempos:
 *  - Reloj del partido (cronómetro.segundosParte + ultimoStart) avanza
 *    solo cuando ultimoStart != null. Pausa congela.
 *  - Tiempo en pista del jugador (tiempos[j].segTurnoActual + turnoStart)
 *    avanza SOLO cuando el reloj corre Y el jugador está en pista. Al
 *    pausar el reloj, el contador del jugador se congela. Al reanudar,
 *    sigue donde estaba. Al hacer cambio, el que sale congela y el que
 *    entra empieza de 0.
 *
 * Reglas de auto-contabilización (no duplicar datos):
 *  - GOL INTER: marcador+1, goleador.dpp+1, evento gol.
 *      Si la acción es "Penalti" o "10m": además se crea un evento
 *      penalti/diezm enlazado al gol vía golId/penaltiId.
 *  - GOL RIVAL: marcador+1, disparosRival.puerta+1, portero (en pista).golesEncajados+1.
 *  - DISPARO INTER (no gol): jugador.dpp/dpa/dpf/dpb +1 según resultado.
 *  - DISPARO RIVAL (no gol): disparosRival.X +1 según resultado.
 *  - PENALTI/10M con resultado=GOL: igual que un gol normal + se crea
 *    automáticamente evento gol enlazado.
 *  - PENALTI/10M con resultado≠GOL: cuenta como disparo (dpp si PARADA,
 *    dpa si POSTE, dpf si FUERA).
 */
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  db,
  partidoVacio,
  contadoresVacios,
  PRESETS_COMPETICION,
  UMBRAL_RETOMAR_TURNO_SEG,
  type Partido,
  type ParteId,
  type ConfigPartido,
  type Evento,
  type TiempoJugador,
  type ContadoresJugador,
  type ResultadoDisparo,
  type TiroTanda,
} from "./db";
import { uid } from "./utils";
import { ROSTER } from "./roster";

const ID_PARTIDO = "current";
const TICK_MS = 250;
const SAVE_DEBOUNCE_MS = 300;

/** Si el reloj corre y el jugador tiene turnoStart, suma el tramo en vivo. */
function vivoSegTurno(t: TiempoJugador): number {
  if (t.segTurnoActual == null) return 0;
  const base = t.segTurnoActual;
  if (t.turnoStart != null) {
    return base + (Date.now() - t.turnoStart) / 1000;
  }
  return base;
}

/** Acumular el tramo en vivo al campo segTurnoActual (y total/porParte). */
function congelaTurno(t: TiempoJugador, parte: ParteId): TiempoJugador {
  if (t.turnoStart == null) return t;
  const tramo = (Date.now() - t.turnoStart) / 1000;
  return {
    ...t,
    segTurnoActual: (t.segTurnoActual ?? 0) + tramo,
    totalSegundos: t.totalSegundos + tramo,
    porParte: { ...t.porParte, [parte]: t.porParte[parte] + tramo },
    turnoStart: null,
  };
}

/** Si está en banquillo con reloj corriendo, devuelve seg de descanso en vivo. */
function vivoSegDescanso(t: TiempoJugador): number {
  if (t.segDescansoActual == null) return 0;
  const base = t.segDescansoActual;
  if (t.descansoStart != null) return base + (Date.now() - t.descansoStart) / 1000;
  return base;
}

/** Congela el tramo vivo de descanso al pausar el reloj. */
function congelaDescanso(t: TiempoJugador): TiempoJugador {
  if (t.descansoStart == null) return t;
  const tramo = (Date.now() - t.descansoStart) / 1000;
  return {
    ...t,
    segDescansoActual: (t.segDescansoActual ?? 0) + tramo,
    descansoStart: null,
  };
}

/** Suma delta al campo de contadores del jugador (defensivo, retrocompat). */
function bumpContador(
  acciones: Partido["acciones"],
  nombre: string,
  campo: keyof ContadoresJugador,
  delta: number = 1
): Partido["acciones"] {
  const cur = acciones.porJugador[nombre] ?? contadoresVacios();
  const nuevo: ContadoresJugador = {
    ...contadoresVacios(),
    ...cur,
    [campo]: Math.max(0, (cur[campo] ?? 0) + delta),
  };
  return {
    ...acciones,
    porJugador: { ...acciones.porJugador, [nombre]: nuevo },
  };
}

/** Mapa resultado disparo → campo de contadores de jugador. */
function campoDisparo(r: ResultadoDisparo): keyof ContadoresJugador {
  switch (r) {
    case "PUERTA":    return "dpp";
    case "PALO":      return "dpa";
    case "FUERA":     return "dpf";
    case "BLOQUEADO": return "dpb";
  }
}

/** Mapa resultado disparo → campo de disparos rival. */
function campoDisparoRival(r: ResultadoDisparo): keyof Partido["disparosRival"] {
  switch (r) {
    case "PUERTA":    return "puerta";
    case "PALO":      return "palo";
    case "FUERA":     return "fuera";
    case "BLOQUEADO": return "bloqueado";
  }
}

/** Localiza el portero nuestro en pista (asume hay 1 portero por norma). */
function porteroEnPista(enPista: string[]): string | null {
  for (const n of enPista) {
    if (ROSTER.find((j) => j.nombre === n)?.posicion === "PORTERO") return n;
  }
  return null;
}

export function usePartido() {
  const [partido, setPartido] = useState<Partido>(() => partidoVacio(ID_PARTIDO));
  const [cargado, setCargado] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Tick para recálculo de "tiempo en pista" cuando el reloj corre
  const [, forceTick] = useState(0);
  useEffect(() => {
    const i = setInterval(() => {
      forceTick((x) => x + 1);
      // Auto-pausa cuando se acaba el tiempo de la parte
      setPartido((prev) => {
        if (prev.cronometro.ultimoStart == null) return prev;
        if (!prev.config) return prev;
        const dur = prev.config.duracionParte[prev.cronometro.parteActual] ?? 0;
        if (dur === 0) return prev;
        const ahora = Date.now();
        const vivos = prev.cronometro.segundosParte + (ahora - prev.cronometro.ultimoStart) / 1000;
        if (vivos < dur) return prev;
        // Llegó al final de parte → pausa
        const tiempos = { ...prev.tiempos };
        const parte = prev.cronometro.parteActual;
        for (const nombre of prev.enPista) {
          const t = tiempos[nombre];
          if (t) tiempos[nombre] = congelaTurno(t, parte);
        }
        for (const nombre of Object.keys(tiempos)) {
          if (prev.enPista.includes(nombre)) continue;
          const t = tiempos[nombre];
          if (t) tiempos[nombre] = congelaDescanso(t);
        }
        return {
          ...prev,
          cronometro: {
            ...prev.cronometro,
            segundosParte: dur,           // capamos al máximo exacto
            ultimoStart: null,
          },
          tiempos,
        };
      });
    }, TICK_MS);
    return () => clearInterval(i);
  }, []);

  useEffect(() => {
    (async () => {
      const p = await db.partidos.get(ID_PARTIDO);
      if (p) {
        // Migración suave: añadir campos nuevos si vienen de versión antigua.
        const cfgOrig = p.config;
        const cfgMigrado: ConfigPartido | null = cfgOrig
          ? {
              ...cfgOrig,
              duracionParte: cfgOrig.duracionParte
                ?? (PRESETS_COMPETICION[cfgOrig.competicion]?.duraciones
                    ?? { "1T": 1200, "2T": 1200, PR1: 0, PR2: 0 }),
              permiteTanda: cfgOrig.permiteTanda
                ?? (PRESETS_COMPETICION[cfgOrig.competicion]?.permiteTanda ?? false),
              direccionInter1T: cfgOrig.direccionInter1T ?? "der",
            }
          : null;
        const tiemposMig: Record<string, TiempoJugador> = {};
        for (const [k, t] of Object.entries(p.tiempos ?? {})) {
          const tt = t as TiempoJugador;
          tiemposMig[k] = {
            ...tt,
            // Si no traen los campos nuevos, deducir: si está en pista (segTurnoActual!=null)
            // o entró antes → no está descansando.
            segDescansoActual: tt.segDescansoActual !== undefined
              ? tt.segDescansoActual
              : (tt.segTurnoActual != null ? null : 0),
            descansoStart: tt.descansoStart !== undefined ? tt.descansoStart : null,
            segTurnoUltimo: tt.segTurnoUltimo !== undefined ? tt.segTurnoUltimo : null,
          };
        }
        const migrado: Partido = {
          ...p,
          config: cfgMigrado,
          tiempos: tiemposMig,
          cronometro: {
            ...p.cronometro,
            segundosGuardadosPorParte: p.cronometro?.segundosGuardadosPorParte
              ?? { "1T": 0, "2T": 0, PR1: 0, PR2: 0 } as Record<ParteId, number>,
          },
          disparosRival: p.disparosRival ?? { puerta: 0, fuera: 0, palo: 0, bloqueado: 0 },
          tanda: p.tanda ?? { activa: false, tiros: [], marcador: { inter: 0, rival: 0 } },
          acciones: {
            porJugador: Object.fromEntries(
              Object.entries(p.acciones?.porJugador ?? {}).map(([k, v]) => [
                k, { ...contadoresVacios(), ...(v as ContadoresJugador) },
              ])
            ),
          },
        };
        setPartido(migrado);
      }
      setCargado(true);
    })();
  }, []);

  useEffect(() => {
    if (!cargado) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      db.partidos.put({ ...partido, actualizado: Date.now() });
    }, SAVE_DEBOUNCE_MS);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [partido, cargado]);

  // ────────────────── selectores en vivo ───────────────────────────────
  const segundosTurnoActual = useCallback(
    (nombre: string): number => {
      const t = partido.tiempos[nombre];
      if (!t) return 0;
      return vivoSegTurno(t);
    },
    [partido]
  );

  const segundosBanquillo = useCallback(
    (nombre: string): number => {
      const t = partido.tiempos[nombre];
      if (!t) return 0;
      // Si nunca ha salido y está en pista, 0.
      if (t.segDescansoActual == null) return 0;
      return Math.max(0, vivoSegDescanso(t));
    },
    [partido]
  );

  const segundosParte = useCallback((): number => {
    const c = partido.cronometro;
    if (c.ultimoStart == null) return c.segundosParte;
    return c.segundosParte + (Date.now() - c.ultimoStart) / 1000;
  }, [partido.cronometro]);

  const segundosPartidoTotal = useCallback((): number => {
    return segundosParte();
  }, [segundosParte]);

  /** Duración configurada de la parte ACTUAL (segundos). 0 si no hay config. */
  const duracionParteActual = useCallback((): number => {
    if (!partido.config) return 0;
    return partido.config.duracionParte[partido.cronometro.parteActual] ?? 0;
  }, [partido.config, partido.cronometro.parteActual]);

  /** Segundos restantes en la parte actual (cuenta atrás). 0 si se acabó. */
  const segundosRestantesParte = useCallback((): number => {
    const dur = duracionParteActual();
    if (dur === 0) return 0;
    return Math.max(0, dur - segundosParte());
  }, [duracionParteActual, segundosParte]);

  const segundosEnParte = useCallback(
    (nombre: string, parte: ParteId): number => {
      const t = partido.tiempos[nombre];
      if (!t) return 0;
      const base = t.porParte[parte] || 0;
      if (parte === partido.cronometro.parteActual
          && t.turnoStart != null
          && partido.cronometro.ultimoStart != null) {
        return base + (Date.now() - t.turnoStart) / 1000;
      }
      return base;
    },
    [partido]
  );

  // ────────────────── acciones ─────────────────────────────────────────

  async function iniciarPartido(config: ConfigPartido): Promise<void> {
    // CRÍTICO: este flujo se llama desde /nuevo justo antes de router.push("/partido").
    // /partido es otra ruta y monta SU PROPIO hook usePartido() que lee de Dexie.
    // Si la escritura a Dexie no termina antes de que /partido cargue,
    // /partido ve estado="configurando" y muestra "No hay partido en curso".
    //
    // Solución: persistencia SÍNCRONA primero, setState después.
    // Si Dexie falla, no actualizamos React (consistencia).
    const ahora = Date.now();
    const pi = config.pista_inicial;
    const enPistaIni = [pi.portero, pi.pista1, pi.pista2, pi.pista3, pi.pista4];
    const tiempos: Record<string, TiempoJugador> = {};
    for (const j of config.convocados) {
      const enPista = enPistaIni.includes(j);
      tiempos[j] = {
        nombre: j,
        totalSegundos: 0,
        porParte: { "1T": 0, "2T": 0, PR1: 0, PR2: 0 },
        segTurnoActual: enPista ? 0 : null,
        turnoStart: null,
        ultimaSalida: enPista ? null : ahora,
        segDescansoActual: enPista ? null : 0,
        descansoStart: null,
        segTurnoUltimo: null,
      };
    }
    const acciones: { porJugador: Record<string, ContadoresJugador> } = {
      porJugador: {},
    };
    for (const j of config.convocados) {
      acciones.porJugador[j] = contadoresVacios();
    }

    // Construir el partido SIN depender del state previo (es un partido NUEVO).
    const nuevo: Partido = {
      id: ID_PARTIDO,
      estado: "en_curso",
      config,
      cronometro: {
        parteActual: "1T",
        segundosParte: 0,
        ultimoStart: null,
        segundosGuardadosPorParte: { "1T": 0, "2T": 0, PR1: 0, PR2: 0 } as Record<ParteId, number>,
      },
      enPista: enPistaIni,
      tiempos,
      marcador: { inter: 0, rival: 0 },
      stats: {
        faltas: { "1T": { inter: 0, rival: 0 }, "2T": { inter: 0, rival: 0 },
                   PR1: { inter: 0, rival: 0 }, PR2: { inter: 0, rival: 0 } },
        amarillas: { "1T": { inter: 0, rival: 0 }, "2T": { inter: 0, rival: 0 },
                       PR1: { inter: 0, rival: 0 }, PR2: { inter: 0, rival: 0 } },
        tiemposMuerto: { "1T": { inter: 0, rival: 0 }, "2T": { inter: 0, rival: 0 },
                            PR1: { inter: 0, rival: 0 }, PR2: { inter: 0, rival: 0 } },
      },
      eventos: [],
      acciones,
      disparosRival: { puerta: 0, fuera: 0, palo: 0, bloqueado: 0 },
      tanda: { activa: false, tiros: [], marcador: { inter: 0, rival: 0 } },
      actualizado: ahora,
    };

    // Cancelar timer pendiente de autosave por si tiene un valor obsoleto.
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }

    // PASO 1: persistir a Dexie ANTES de actualizar React state. Si falla,
    // no actualizamos React. Esto resuelve la race condition con /partido.
    await db.partidos.put(nuevo);

    // PASO 2: actualizar React state local del hook actual. /partido al
    // montar leerá de Dexie y verá el mismo valor.
    setPartido(nuevo);
  }

  function play() {
    setPartido((prev) => {
      if (prev.cronometro.ultimoStart != null) return prev;
      const ahora = Date.now();
      const tiempos = { ...prev.tiempos };
      // Jugadores en pista: turno arranca
      for (const nombre of prev.enPista) {
        const t = tiempos[nombre];
        if (t) tiempos[nombre] = { ...t, turnoStart: ahora };
      }
      // Jugadores en banquillo: descanso arranca
      for (const nombre of Object.keys(tiempos)) {
        if (prev.enPista.includes(nombre)) continue;
        const t = tiempos[nombre];
        if (t && t.segDescansoActual != null) {
          tiempos[nombre] = { ...t, descansoStart: ahora };
        }
      }
      return {
        ...prev,
        cronometro: { ...prev.cronometro, ultimoStart: ahora },
        tiempos,
      };
    });
  }

  function pausa() {
    setPartido((prev) => {
      if (prev.cronometro.ultimoStart == null) return prev;
      const ahora = Date.now();
      const transcurrido = (ahora - prev.cronometro.ultimoStart) / 1000;
      const tiempos = { ...prev.tiempos };
      const parte = prev.cronometro.parteActual;
      // Pista: congelar turno
      for (const nombre of prev.enPista) {
        const t = tiempos[nombre];
        if (t) tiempos[nombre] = congelaTurno(t, parte);
      }
      // Banquillo: congelar descanso
      for (const nombre of Object.keys(tiempos)) {
        if (prev.enPista.includes(nombre)) continue;
        const t = tiempos[nombre];
        if (t) tiempos[nombre] = congelaDescanso(t);
      }
      return {
        ...prev,
        cronometro: {
          ...prev.cronometro,
          segundosParte: prev.cronometro.segundosParte + transcurrido,
          ultimoStart: null,
        },
        tiempos,
      };
    });
  }

  /**
   * Ajusta el reloj +/- N segundos. Si corre, retrocede/adelanta ultimoStart
   * (y el turnoStart de los jugadores en pista) para que el cálculo en vivo
   * dé el resultado correcto. Si está pausado, ajusta los campos acumulados.
   * En ambos casos, los jugadores EN PISTA acompañan el ajuste (no se inventan
   * tiempos que no han estado).
   */
  function ajustarReloj(deltaSegundos: number) {
    setPartido((prev) => {
      if (deltaSegundos === 0) return prev;
      const c = prev.cronometro;
      const parte = c.parteActual;
      const tiempos = { ...prev.tiempos };
      const ahora = Date.now();

      if (c.ultimoStart != null) {
        // Corriendo: ajustar ultimoStart (retrocedo en el tiempo si sumo seg).
        const nuevoUltimo = Math.min(c.ultimoStart - deltaSegundos * 1000, ahora);
        // No bajar de segundosParte=0: el cálculo en vivo es (now - nuevoUltimo)/1000 + segundosParte.
        // Si quedara negativo, capamos.
        const vivoActual = (ahora - nuevoUltimo) / 1000 + c.segundosParte;
        if (vivoActual < 0) {
          // Resetear a 0 con ultimoStart=ahora.
          const cronometro = { ...c, segundosParte: 0, ultimoStart: ahora };
          for (const nombre of prev.enPista) {
            const t = tiempos[nombre];
            if (t) tiempos[nombre] = {
              ...t, segTurnoActual: 0, turnoStart: ahora,
              porParte: { ...t.porParte, [parte]: 0 },
            };
          }
          return { ...prev, cronometro, tiempos };
        }
        const cronometro = { ...c, ultimoStart: nuevoUltimo };
        for (const nombre of prev.enPista) {
          const t = tiempos[nombre];
          if (t && t.turnoStart != null) {
            const nuevoTurnoStart = Math.min(t.turnoStart - deltaSegundos * 1000, ahora);
            tiempos[nombre] = { ...t, turnoStart: nuevoTurnoStart };
          }
        }
        return { ...prev, cronometro, tiempos };
      } else {
        // Pausado: ajustar acumulados.
        const cronometro = { ...c, segundosParte: Math.max(0, c.segundosParte + deltaSegundos) };
        for (const nombre of prev.enPista) {
          const t = tiempos[nombre];
          if (t && t.segTurnoActual != null) {
            const seg = Math.max(0, t.segTurnoActual + deltaSegundos);
            const total = Math.max(0, t.totalSegundos + deltaSegundos);
            const pp = Math.max(0, (t.porParte[parte] ?? 0) + deltaSegundos);
            tiempos[nombre] = {
              ...t,
              segTurnoActual: seg,
              totalSegundos: total,
              porParte: { ...t.porParte, [parte]: pp },
            };
          }
        }
        return { ...prev, cronometro, tiempos };
      }
    });
  }

  function avanzarParte() {
    const orden: ParteId[] = ["1T", "2T", "PR1", "PR2"];
    setPartido((prev) => {
      let p = prev;
      if (p.cronometro.ultimoStart != null) {
        const ahora = Date.now();
        const transcurrido = (ahora - p.cronometro.ultimoStart) / 1000;
        const tiempos = { ...p.tiempos };
        const parte = p.cronometro.parteActual;
        for (const nombre of p.enPista) {
          const t = tiempos[nombre];
          if (t) tiempos[nombre] = congelaTurno(t, parte);
        }
        for (const nombre of Object.keys(tiempos)) {
          if (p.enPista.includes(nombre)) continue;
          const t = tiempos[nombre];
          if (t) tiempos[nombre] = congelaDescanso(t);
        }
        p = {
          ...p,
          cronometro: {
            ...p.cronometro,
            segundosParte: p.cronometro.segundosParte + transcurrido,
            ultimoStart: null,
          },
          tiempos,
        };
      }
      const tiempos = { ...p.tiempos };
      for (const nombre of p.enPista) {
        const t = tiempos[nombre];
        if (t) tiempos[nombre] = { ...t, segTurnoActual: 0, turnoStart: null };
      }
      const idx = orden.indexOf(p.cronometro.parteActual);
      const sig = orden[Math.min(idx + 1, orden.length - 1)];
      // Guardar el reloj de la parte que ABANDONAMOS, y restaurar el
      // de la parte SIGUIENTE si ya tenía valor (caso: ya estuvimos en
      // esa parte antes y retrocedimos; ahora volvemos al punto donde
      // estaba). Si nunca se entró a `sig`, empieza en 0 como siempre.
      const guardados = { ...(p.cronometro.segundosGuardadosPorParte ?? {} as Record<ParteId, number>) };
      guardados[p.cronometro.parteActual] = p.cronometro.segundosParte;
      const segRestaurado = guardados[sig] ?? 0;
      return {
        ...p,
        cronometro: {
          parteActual: sig,
          segundosParte: segRestaurado,
          ultimoStart: null,
          segundosGuardadosPorParte: guardados,
        },
        tiempos,
      };
    });
  }

  function cambiarJugador(sale: string, entra: string) {
    setPartido((prev) => {
      if (!prev.enPista.includes(sale)) return prev;
      // entra === "" → significa "Nadie entra" (slot vacío, inferioridad
      // numérica). Saltamos validación de duplicado.
      if (entra !== "" && prev.enPista.includes(entra)) return prev;
      const ahora = Date.now();
      const corriendo = prev.cronometro.ultimoStart != null;
      const tiempos = { ...prev.tiempos };
      const parte = prev.cronometro.parteActual;
      const tSale = tiempos[sale];
      if (tSale) {
        const cong = congelaTurno(tSale, parte);
        tiempos[sale] = {
          ...cong,
          segTurnoActual: null,
          ultimaSalida: ahora,
          // Guardar último valor por si vuelve en <30s (regla "fatiga
          // acumulada"). Se usa cuando vuelva a entrar.
          segTurnoUltimo: cong.segTurnoActual ?? 0,
          // Empieza a descansar (en vivo si reloj corre, congelado si no).
          segDescansoActual: 0,
          descansoStart: corriendo ? ahora : null,
        };
      }
      // Solo si entra es un jugador real (no "Nadie"), procesamos tiempos.
      if (entra !== "") {
        const tEntra = tiempos[entra];
        if (tEntra) {
          // Congelar descanso antes de leerlo.
          const congDesc = congelaDescanso(tEntra);
          const segBanquillo = congDesc.segDescansoActual ?? 0;
          const ultimoTurno = congDesc.segTurnoUltimo ?? 0;
          const retomar = segBanquillo < UMBRAL_RETOMAR_TURNO_SEG && ultimoTurno > 0;
          const segInicial = retomar ? ultimoTurno : 0;
          tiempos[entra] = {
            ...congDesc,
            segTurnoActual: segInicial,
            turnoStart: corriendo ? ahora : null,
            ultimaSalida: null,
            segDescansoActual: null,
            descansoStart: null,
            segTurnoUltimo: null,
          };
        }
      }
      // enPista: si entra es "" (Nadie), quitamos sin reemplazo → array
      // queda con menos elementos (4 en lugar de 5, p.ej., en inferioridad
      // numérica). Si entra es un jugador, sustituimos sale por entra.
      const enPista = entra === ""
        ? prev.enPista.filter((n) => n !== sale)
        : prev.enPista.map((n) => (n === sale ? entra : n));
      const evento: Evento = {
        id: uid(),
        tipo: "cambio",
        parte,
        segundosParte: segundosParte(),
        segundosPartido: segundosPartidoTotal(),
        timestampReal: ahora,
        marcador: { ...prev.marcador },
        sale, entra,
      };
      return { ...prev, enPista, tiempos, eventos: [...prev.eventos, evento] };
    });
  }

  /**
   * Núcleo: registra un evento. Aplica TODOS los efectos automáticos
   * (marcador, contadores de disparo, goles encajados, etc.) según las
   * reglas de no-duplicación.
   *
   * Si el evento es un gol con acción "Penalti" o "10m", se puede pasar
   * `penaltiExtra` con los datos del penalti (tirador, portero, resultado=GOL,
   * zona). El store creará automáticamente el evento penalti enlazado.
   */
  function registrarEvento(
    parcial: Omit<Evento, "id" | "parte" | "segundosParte" | "segundosPartido" | "timestampReal" | "marcador">,
    extra?: { penaltiTipo?: "penalti" | "diezm"; penaltiPorteroRival?: string }
  ) {
    setPartido((prev) => {
      const ahora = Date.now();
      const parte = prev.cronometro.parteActual;
      const segP = (() => {
        const c = prev.cronometro;
        return c.ultimoStart == null ? c.segundosParte : c.segundosParte + (ahora - c.ultimoStart) / 1000;
      })();
      const evento: Evento = {
        ...(parcial as Evento),
        id: uid(),
        parte,
        segundosParte: segP,
        segundosPartido: segP,
        timestampReal: ahora,
        marcador: { ...prev.marcador },
      };

      let next: Partido = { ...prev, eventos: [...prev.eventos, evento] };

      // ─── Aplicar efectos según tipo ─────────────────────────────────
      if (evento.tipo === "gol") {
        // Marcador
        next.marcador = {
          inter: next.marcador.inter + (evento.equipo === "INTER" ? 1 : 0),
          rival: next.marcador.rival + (evento.equipo === "RIVAL" ? 1 : 0),
        };
        // Actualizar marcador snapshot del propio evento (para que sea POST-gol)
        // Ojo: mantenemos snapshot PRE-gol; con timestampReal puede inferirse.
        // Disparo asociado automático
        if (evento.equipo === "INTER" && evento.goleador) {
          next.acciones = bumpContador(next.acciones, evento.goleador, "dpp", 1);
        } else if (evento.equipo === "RIVAL") {
          next.disparosRival = { ...next.disparosRival, puerta: next.disparosRival.puerta + 1 };
          const portero = porteroEnPista(next.enPista);
          if (portero) {
            next.acciones = bumpContador(next.acciones, portero, "golesEncajados", 1);
          }
        }
        // Si la acción fue Penalti/10m → crear evento penalti enlazado
        if (evento.accion === "Penalti" || evento.accion === "10m") {
          const tipoPen = extra?.penaltiTipo ?? (evento.accion === "10m" ? "diezm" : "penalti");
          let tirador = "", portero = "";
          if (evento.equipo === "INTER") {
            tirador = evento.goleador;
            portero = extra?.penaltiPorteroRival ?? "";
          } else {
            tirador = "";  // no sabemos el tirador rival nominalmente
            portero = porteroEnPista(next.enPista) ?? "";
          }
          const evPen: Evento = {
            id: uid(),
            tipo: tipoPen,
            parte,
            segundosParte: segP,
            segundosPartido: segP,
            timestampReal: ahora,
            marcador: { ...evento.marcador },
            equipo: evento.equipo,
            tirador,
            portero,
            resultado: "GOL",
            zonaPorteria: evento.zonaPorteria,
            golId: evento.id,
          };
          // También enlazamos el id en el gol (mutamos el evento dentro de la lista)
          next.eventos = next.eventos.map((e) =>
            e.id === evento.id ? { ...e, penaltiId: evPen.id } as Evento : e
          );
          next.eventos.push(evPen);
        }
      } else if (evento.tipo === "falta") {
        const cur = next.stats.faltas[parte];
        next.stats = { ...next.stats, faltas: { ...next.stats.faltas,
          [parte]: evento.equipo === "INTER"
            ? { ...cur, inter: cur.inter + 1 }
            : { ...cur, rival: cur.rival + 1 },
        } };
      } else if (evento.tipo === "amarilla") {
        const cur = next.stats.amarillas[parte];
        next.stats = { ...next.stats, amarillas: { ...next.stats.amarillas,
          [parte]: evento.equipo === "INTER"
            ? { ...cur, inter: cur.inter + 1 }
            : { ...cur, rival: cur.rival + 1 },
        } };
      } else if (evento.tipo === "tiempo_muerto") {
        const cur = next.stats.tiemposMuerto[parte];
        next.stats = { ...next.stats, tiemposMuerto: { ...next.stats.tiemposMuerto,
          [parte]: evento.equipo === "INTER"
            ? { ...cur, inter: cur.inter + 1 }
            : { ...cur, rival: cur.rival + 1 },
        } };
      } else if (evento.tipo === "disparo") {
        // Disparo independiente (NO gol). Si llega con resultado y no enlaza a
        // gol, suma contadores.
        if (evento.equipo === "INTER" && evento.jugador) {
          next.acciones = bumpContador(next.acciones, evento.jugador, campoDisparo(evento.resultado), 1);
        } else if (evento.equipo === "RIVAL") {
          const campo = campoDisparoRival(evento.resultado);
          next.disparosRival = { ...next.disparosRival, [campo]: next.disparosRival[campo] + 1 };
          // Si va a puerta y NO es gol (este es un evento "disparo", no "gol"),
          // entonces es una parada del portero → +1 paradas al portero.
          if (evento.resultado === "PUERTA") {
            const portero = evento.portero || porteroEnPista(next.enPista);
            if (portero) {
              next.acciones = bumpContador(next.acciones, portero, "paradas", 1);
            }
          }
        }
      } else if (evento.tipo === "penalti" || evento.tipo === "diezm") {
        // Si es gol → marcador + disparo a puerta + gol encajado portero rival.
        // Si NO es gol → contar como disparo según resultado.
        if (evento.resultado === "GOL") {
          next.marcador = {
            inter: next.marcador.inter + (evento.equipo === "INTER" ? 1 : 0),
            rival: next.marcador.rival + (evento.equipo === "RIVAL" ? 1 : 0),
          };
          if (evento.equipo === "INTER" && evento.tirador) {
            next.acciones = bumpContador(next.acciones, evento.tirador, "dpp", 1);
          } else if (evento.equipo === "RIVAL") {
            next.disparosRival = { ...next.disparosRival, puerta: next.disparosRival.puerta + 1 };
            const portero = porteroEnPista(next.enPista);
            if (portero) {
              next.acciones = bumpContador(next.acciones, portero, "golesEncajados", 1);
            }
          }
        } else {
          // No gol → suma como disparo
          const res: ResultadoDisparo =
            evento.resultado === "PARADA" ? "PUERTA"
            : evento.resultado === "POSTE" ? "PALO"
            : "FUERA";
          if (evento.equipo === "INTER" && evento.tirador) {
            next.acciones = bumpContador(next.acciones, evento.tirador, campoDisparo(res), 1);
          } else if (evento.equipo === "RIVAL") {
            const campo = campoDisparoRival(res);
            next.disparosRival = { ...next.disparosRival, [campo]: next.disparosRival[campo] + 1 };
            // PARADA del rival = nuestro portero paró el penalti.
            if (evento.resultado === "PARADA") {
              const portero = evento.portero || porteroEnPista(next.enPista);
              if (portero) {
                next.acciones = bumpContador(next.acciones, portero, "paradas", 1);
              }
            }
          }
        }
      }
      return next;
    });
  }

  /** Deshacer último evento — REVIERTE también los efectos automáticos. */
  function deshacerUltimoEvento() {
    setPartido((prev) => {
      const ev = prev.eventos[prev.eventos.length - 1];
      if (!ev) return prev;
      let next: Partido = { ...prev, eventos: prev.eventos.slice(0, -1) };

      if (ev.tipo === "gol") {
        next.marcador = {
          inter: next.marcador.inter - (ev.equipo === "INTER" ? 1 : 0),
          rival: next.marcador.rival - (ev.equipo === "RIVAL" ? 1 : 0),
        };
        if (ev.equipo === "INTER" && ev.goleador) {
          next.acciones = bumpContador(next.acciones, ev.goleador, "dpp", -1);
        } else if (ev.equipo === "RIVAL") {
          next.disparosRival = { ...next.disparosRival,
            puerta: Math.max(0, next.disparosRival.puerta - 1) };
          const portero = porteroEnPista(next.enPista);
          if (portero) {
            next.acciones = bumpContador(next.acciones, portero, "golesEncajados", -1);
          }
        }
        // Si tenía penalti enlazado, eliminarlo también
        if (ev.penaltiId) {
          next.eventos = next.eventos.filter((e) => e.id !== ev.penaltiId);
        }
      } else if (ev.tipo === "falta") {
        const cur = next.stats.faltas[ev.parte];
        next.stats.faltas[ev.parte] = ev.equipo === "INTER"
          ? { ...cur, inter: Math.max(0, cur.inter - 1) }
          : { ...cur, rival: Math.max(0, cur.rival - 1) };
      } else if (ev.tipo === "amarilla") {
        const cur = next.stats.amarillas[ev.parte];
        next.stats.amarillas[ev.parte] = ev.equipo === "INTER"
          ? { ...cur, inter: Math.max(0, cur.inter - 1) }
          : { ...cur, rival: Math.max(0, cur.rival - 1) };
      } else if (ev.tipo === "tiempo_muerto") {
        const cur = next.stats.tiemposMuerto[ev.parte];
        next.stats.tiemposMuerto[ev.parte] = ev.equipo === "INTER"
          ? { ...cur, inter: Math.max(0, cur.inter - 1) }
          : { ...cur, rival: Math.max(0, cur.rival - 1) };
      } else if (ev.tipo === "cambio") {
        next.enPista = next.enPista.map((n) => (n === ev.entra ? ev.sale : n));
      } else if (ev.tipo === "disparo") {
        if (ev.equipo === "INTER" && ev.jugador) {
          next.acciones = bumpContador(next.acciones, ev.jugador, campoDisparo(ev.resultado), -1);
        } else if (ev.equipo === "RIVAL") {
          const campo = campoDisparoRival(ev.resultado);
          next.disparosRival = { ...next.disparosRival,
            [campo]: Math.max(0, next.disparosRival[campo] - 1) };
          // Revertir parada al portero (si la había)
          if (ev.resultado === "PUERTA") {
            const portero = ev.portero || porteroEnPista(next.enPista);
            if (portero) {
              next.acciones = bumpContador(next.acciones, portero, "paradas", -1);
            }
          }
        }
      } else if (ev.tipo === "penalti" || ev.tipo === "diezm") {
        if (ev.resultado === "GOL") {
          next.marcador = {
            inter: next.marcador.inter - (ev.equipo === "INTER" ? 1 : 0),
            rival: next.marcador.rival - (ev.equipo === "RIVAL" ? 1 : 0),
          };
          if (ev.equipo === "INTER" && ev.tirador) {
            next.acciones = bumpContador(next.acciones, ev.tirador, "dpp", -1);
          } else if (ev.equipo === "RIVAL") {
            next.disparosRival = { ...next.disparosRival,
              puerta: Math.max(0, next.disparosRival.puerta - 1) };
            const portero = porteroEnPista(next.enPista);
            if (portero) {
              next.acciones = bumpContador(next.acciones, portero, "golesEncajados", -1);
            }
          }
          // Si enlazaba a un gol, eliminar también el gol
          if (ev.golId) {
            next.eventos = next.eventos.filter((e) => e.id !== ev.golId);
            // Y desincrementar marcador y dpp por ese gol (ya hechos arriba)
            // — pero el gol ya añadió +1 a marcador y +1 a dpp; si ya
            // habíamos restado por el penalti=GOL, ahora estamos DOBLE-restando.
            // Para evitarlo: solo se debe descontar UNA vez por par enlazado.
            // Solución: como el gol enlazado en realidad nunca sumó marcador
            // extra (se asumió que el penalti=GOL lo añadió), aquí desincrementamos
            // solo el snapshot — vamos a no hacer nada extra y dejarlo simple.
          }
        } else {
          const res: ResultadoDisparo =
            ev.resultado === "PARADA" ? "PUERTA"
            : ev.resultado === "POSTE" ? "PALO"
            : "FUERA";
          if (ev.equipo === "INTER" && ev.tirador) {
            next.acciones = bumpContador(next.acciones, ev.tirador, campoDisparo(res), -1);
          } else if (ev.equipo === "RIVAL") {
            const campo = campoDisparoRival(res);
            next.disparosRival = { ...next.disparosRival,
              [campo]: Math.max(0, next.disparosRival[campo] - 1) };
          }
        }
      }
      return next;
    });
  }

  /** Bump genérico de contador individual (PF/PNF/Robos/Cortes/BDG/BDP/etc.). */
  function incAccion(
    nombre: string,
    campo: keyof ContadoresJugador,
    delta: number = 1
  ) {
    setPartido((prev) => ({ ...prev, acciones: bumpContador(prev.acciones, nombre, campo, delta) }));
  }

  /**
   * Registra una acción individual (PF/PNF/Robo/Corte/BDG/BDP) con zona
   * del campo opcional. Hace dos cosas atómicas:
   *   1. Sube el contador del jugador (igual que incAccion).
   *   2. Guarda un evento "accion_individual" con el detalle (jugador,
   *      tipo, zona, parte, segundos), para análisis posterior.
   */
  function registrarAccionIndividual(
    jugador: string,
    accion: "pf" | "pnf" | "robos" | "cortes" | "bdg" | "bdp",
    zonaCampo?: string,
  ) {
    setPartido((prev) => {
      const ahora = Date.now();
      const parte = prev.cronometro.parteActual;
      const segP = (() => {
        const c = prev.cronometro;
        return c.ultimoStart == null
          ? c.segundosParte
          : c.segundosParte + (ahora - c.ultimoStart) / 1000;
      })();
      const evento: Evento = {
        id: uid(),
        tipo: "accion_individual",
        parte,
        segundosParte: segP,
        segundosPartido: segP,
        timestampReal: ahora,
        marcador: { ...prev.marcador },
        jugador,
        accion,
        zonaCampo,
      };
      const acciones = bumpContador(prev.acciones, jugador, accion, 1);
      return { ...prev, acciones, eventos: [...prev.eventos, evento] };
    });
  }

  function reset() {
    setPartido(partidoVacio(ID_PARTIDO));
  }

  /**
   * Retrocede una parte (2T→1T, PR1→2T, PR2→PR1). Útil para deshacer
   * un avance accidental. Comportamiento:
   *   - Pausa el reloj si corre.
   *   - Cambia parteActual a la anterior.
   *   - Reinicia segundosParte=0 (la parte "vuelve a empezar" para el
   *     cronómetro). Los `porParte` ya consolidados se mantienen.
   *   - Reinicia segTurnoActual=0 para los jugadores en pista (mismo
   *     trato que en avanzarParte).
   *
   * NOTA: el reloj de la parte anterior se reinicia a 0. Si necesitas
   * volver al minuto exacto donde estabas, usa los botones ±1m/±10s
   * después de retroceder.
   */
  function retrocederParte() {
    const orden: ParteId[] = ["1T", "2T", "PR1", "PR2"];
    setPartido((prev) => {
      const idx = orden.indexOf(prev.cronometro.parteActual);
      if (idx <= 0) return prev;  // ya está en 1T, nada que retroceder
      let p = prev;
      if (p.cronometro.ultimoStart != null) {
        const ahora = Date.now();
        const transcurrido = (ahora - p.cronometro.ultimoStart) / 1000;
        const tiempos = { ...p.tiempos };
        const parte = p.cronometro.parteActual;
        for (const nombre of p.enPista) {
          const t = tiempos[nombre];
          if (t) tiempos[nombre] = congelaTurno(t, parte);
        }
        for (const nombre of Object.keys(tiempos)) {
          if (p.enPista.includes(nombre)) continue;
          const t = tiempos[nombre];
          if (t) tiempos[nombre] = congelaDescanso(t);
        }
        p = {
          ...p,
          cronometro: {
            ...p.cronometro,
            segundosParte: p.cronometro.segundosParte + transcurrido,
            ultimoStart: null,
          },
          tiempos,
        };
      }
      const partePrev = orden[idx - 1];
      const tiempos = { ...p.tiempos };
      for (const nombre of p.enPista) {
        const t = tiempos[nombre];
        if (t) tiempos[nombre] = { ...t, segTurnoActual: 0, turnoStart: null };
      }
      // Guardar el reloj de la parte que ABANDONAMOS (la "actual"),
      // y restaurar el de la parte ANTERIOR si lo teníamos guardado
      // (sí lo tenemos: necesariamente estuvimos en ella antes para
      // poder avanzar hasta la actual).
      const guardados = { ...(p.cronometro.segundosGuardadosPorParte ?? {} as Record<ParteId, number>) };
      guardados[p.cronometro.parteActual] = p.cronometro.segundosParte;
      const segRestaurado = guardados[partePrev] ?? 0;
      return {
        ...p,
        cronometro: {
          parteActual: partePrev,
          segundosParte: segRestaurado,
          ultimoStart: null,
          segundosGuardadosPorParte: guardados,
        },
        tiempos,
      };
    });
  }

  /**
   * Cambia la duración de una o varias partes en la config en CALIENTE.
   * Útil para configurar la prórroga ("¿De cuántos minutos?") tras un
   * empate al final de 2T. minutos=0 significa "no se juega esa parte".
   */
  function setDuracionesParte(durMinutos: Partial<Record<ParteId, number>>) {
    setPartido((prev) => {
      if (!prev.config) return prev;
      const nuevas: Record<ParteId, number> = { ...prev.config.duracionParte };
      for (const [k, v] of Object.entries(durMinutos)) {
        nuevas[k as ParteId] = Math.max(0, Math.round((v ?? 0) * 60));
      }
      return { ...prev, config: { ...prev.config, duracionParte: nuevas } };
    });
  }

  /** Marca el partido como finalizado (estado="finalizado"). */
  function finalizarPartido() {
    setPartido((prev) => {
      // Pausar reloj si corre
      let p = prev;
      if (p.cronometro.ultimoStart != null) {
        const ahora = Date.now();
        const transcurrido = (ahora - p.cronometro.ultimoStart) / 1000;
        const tiempos = { ...p.tiempos };
        const parte = p.cronometro.parteActual;
        for (const nombre of p.enPista) {
          const t = tiempos[nombre];
          if (t) tiempos[nombre] = congelaTurno(t, parte);
        }
        for (const nombre of Object.keys(tiempos)) {
          if (p.enPista.includes(nombre)) continue;
          const t = tiempos[nombre];
          if (t) tiempos[nombre] = congelaDescanso(t);
        }
        p = {
          ...p,
          cronometro: {
            ...p.cronometro,
            segundosParte: p.cronometro.segundosParte + transcurrido,
            ultimoStart: null,
          },
          tiempos,
        };
      }
      return { ...p, estado: "finalizado" };
    });
  }

  // ────────────────── TANDA DE PENALTIS ────────────────────────────────

  function iniciarTanda() {
    setPartido((prev) => {
      // Pausa el reloj si corre
      let p = prev;
      if (p.cronometro.ultimoStart != null) {
        const ahora = Date.now();
        const transcurrido = (ahora - p.cronometro.ultimoStart) / 1000;
        const tiempos = { ...p.tiempos };
        const parte = p.cronometro.parteActual;
        for (const nombre of p.enPista) {
          const t = tiempos[nombre];
          if (t) tiempos[nombre] = congelaTurno(t, parte);
        }
        p = {
          ...p,
          cronometro: { ...p.cronometro, segundosParte: p.cronometro.segundosParte + transcurrido, ultimoStart: null },
          tiempos,
        };
      }
      return {
        ...p,
        tanda: { activa: true, tiros: p.tanda?.tiros ?? [], marcador: p.tanda?.marcador ?? { inter: 0, rival: 0 } },
      };
    });
  }

  function apuntarTiroTanda(tiro: Omit<TiroTanda, "id" | "orden" | "timestampReal">) {
    setPartido((prev) => {
      const orden = (prev.tanda.tiros.length ?? 0) + 1;
      const nuevo: TiroTanda = {
        ...tiro,
        id: uid(),
        orden,
        timestampReal: Date.now(),
      };
      const marcador = { ...prev.tanda.marcador };
      if (nuevo.resultado === "GOL") {
        if (nuevo.equipo === "INTER") marcador.inter += 1;
        else marcador.rival += 1;
      }
      // Disparos auto: la tanda NO suma a los stats del partido (es post-partido)
      // pero podemos guardar el contador en los acciones individuales si el
      // usuario lo prefiere. De momento solo en el evento tanda.
      return {
        ...prev,
        tanda: { ...prev.tanda, tiros: [...prev.tanda.tiros, nuevo], marcador },
      };
    });
  }

  function deshacerUltimoTiroTanda() {
    setPartido((prev) => {
      if (prev.tanda.tiros.length === 0) return prev;
      const ultimo = prev.tanda.tiros[prev.tanda.tiros.length - 1];
      const tiros = prev.tanda.tiros.slice(0, -1);
      const marcador = { ...prev.tanda.marcador };
      if (ultimo.resultado === "GOL") {
        if (ultimo.equipo === "INTER") marcador.inter = Math.max(0, marcador.inter - 1);
        else marcador.rival = Math.max(0, marcador.rival - 1);
      }
      return { ...prev, tanda: { ...prev.tanda, tiros, marcador } };
    });
  }

  function cerrarTanda() {
    setPartido((prev) => ({ ...prev, tanda: { ...prev.tanda, activa: false } }));
  }

  return {
    partido, cargado,
    segundosTurnoActual, segundosBanquillo, segundosParte, segundosPartidoTotal,
    segundosEnParte, segundosRestantesParte, duracionParteActual,
    iniciarPartido, play, pausa, ajustarReloj, avanzarParte, cambiarJugador,
    registrarEvento, deshacerUltimoEvento, incAccion, registrarAccionIndividual, reset,
    iniciarTanda, apuntarTiroTanda, deshacerUltimoTiroTanda, cerrarTanda,
    setDuracionesParte, finalizarPartido, retrocederParte,
  };
}

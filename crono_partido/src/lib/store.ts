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
 */
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  db,
  partidoVacio,
  type Partido,
  type ParteId,
  type ConfigPartido,
  type Evento,
  type TiempoJugador,
} from "./db";
import { uid } from "./utils";

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

export function usePartido() {
  const [partido, setPartido] = useState<Partido>(() => partidoVacio(ID_PARTIDO));
  const [cargado, setCargado] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Tick para recálculo de "tiempo en pista" cuando el reloj corre
  const [, forceTick] = useState(0);
  useEffect(() => {
    const i = setInterval(() => {
      if (partido.cronometro.ultimoStart != null) forceTick((x) => x + 1);
      else forceTick((x) => x + 1); // también refresca banquillo (tiempo descanso)
    }, TICK_MS);
    return () => clearInterval(i);
  }, [partido.cronometro.ultimoStart]);

  useEffect(() => {
    (async () => {
      const p = await db.partidos.get(ID_PARTIDO);
      if (p) setPartido(p);
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
      if (!t || t.ultimaSalida == null) return 0;
      return Math.max(0, (Date.now() - t.ultimaSalida) / 1000);
    },
    [partido]
  );

  const segundosParte = useCallback((): number => {
    const c = partido.cronometro;
    if (c.ultimoStart == null) return c.segundosParte;
    return c.segundosParte + (Date.now() - c.ultimoStart) / 1000;
  }, [partido.cronometro]);

  const segundosPartidoTotal = useCallback((): number => {
    // Suma segundos de partes terminadas + segundos en curso de la parte actual
    return segundosParte();
  }, [segundosParte]);

  /** Tiempo total en pista por parte (acumulado + en vivo si corre). */
  const segundosEnParte = useCallback(
    (nombre: string, parte: ParteId): number => {
      const t = partido.tiempos[nombre];
      if (!t) return 0;
      const base = t.porParte[parte] || 0;
      if (parte === partido.cronometro.parteActual
          && t.turnoStart != null
          && partido.cronometro.ultimoStart != null) {
        // Está en pista + reloj corre → añadir tramo
        return base + (Date.now() - t.turnoStart) / 1000;
      }
      return base;
    },
    [partido]
  );

  // ────────────────── acciones ─────────────────────────────────────────

  function iniciarPartido(config: ConfigPartido) {
    setPartido((prev) => {
      const tiempos: Record<string, TiempoJugador> = {};
      const ahora = Date.now();
      const pi = config.pista_inicial;
      const enPistaIni = [pi.portero, pi.pista1, pi.pista2, pi.pista3, pi.pista4];
      for (const j of config.convocados) {
        const enPista = enPistaIni.includes(j);
        tiempos[j] = {
          nombre: j,
          totalSegundos: 0,
          porParte: { "1T": 0, "2T": 0, PR1: 0, PR2: 0 },
          segTurnoActual: enPista ? 0 : null,
          turnoStart: null,                 // se setea al darle PLAY
          ultimaSalida: enPista ? null : ahora,
        };
      }
      const acciones: typeof prev.acciones = { porJugador: {} };
      for (const j of config.convocados) {
        acciones.porJugador[j] = { pf: 0, pnf: 0, robos: 0, cortes: 0, bdg: 0, bdp: 0 };
      }
      return {
        ...prev,
        estado: "en_curso",
        config,
        enPista: enPistaIni,
        tiempos,
        acciones,
      };
    });
  }

  function play() {
    setPartido((prev) => {
      if (prev.cronometro.ultimoStart != null) return prev;
      const ahora = Date.now();
      // Marcar turnoStart en los que están en pista
      const tiempos = { ...prev.tiempos };
      for (const nombre of prev.enPista) {
        const t = tiempos[nombre];
        if (t) {
          tiempos[nombre] = { ...t, turnoStart: ahora };
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
      for (const nombre of prev.enPista) {
        const t = tiempos[nombre];
        if (t) tiempos[nombre] = congelaTurno(t, parte);
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

  function avanzarParte() {
    const orden: ParteId[] = ["1T", "2T", "PR1", "PR2"];
    setPartido((prev) => {
      let p = prev;
      // Si reloj corre, pausar primero (acumula tiempos)
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
          cronometro: {
            ...p.cronometro,
            segundosParte: p.cronometro.segundosParte + transcurrido,
            ultimoStart: null,
          },
          tiempos,
        };
      }
      // Cambio de parte: reiniciar contador del turno actual (nueva parte
      // empieza de cero para todos los que siguen en pista).
      const tiempos = { ...p.tiempos };
      for (const nombre of p.enPista) {
        const t = tiempos[nombre];
        if (t) tiempos[nombre] = { ...t, segTurnoActual: 0, turnoStart: null };
      }
      const idx = orden.indexOf(p.cronometro.parteActual);
      const sig = orden[Math.min(idx + 1, orden.length - 1)];
      return {
        ...p,
        cronometro: { parteActual: sig, segundosParte: 0, ultimoStart: null },
        tiempos,
      };
    });
  }

  function cambiarJugador(sale: string, entra: string) {
    setPartido((prev) => {
      if (!prev.enPista.includes(sale)) return prev;
      if (prev.enPista.includes(entra)) return prev;
      const ahora = Date.now();
      const corriendo = prev.cronometro.ultimoStart != null;
      const tiempos = { ...prev.tiempos };
      const parte = prev.cronometro.parteActual;
      // El que sale: congelar turno, marcar ultimaSalida, segTurnoActual=null
      const tSale = tiempos[sale];
      if (tSale) {
        const cong = congelaTurno(tSale, parte);
        tiempos[sale] = {
          ...cong,
          segTurnoActual: null,
          ultimaSalida: ahora,
        };
      }
      // El que entra: nuevo turno desde 0, turnoStart=ahora si reloj corre
      const tEntra = tiempos[entra];
      if (tEntra) {
        tiempos[entra] = {
          ...tEntra,
          segTurnoActual: 0,
          turnoStart: corriendo ? ahora : null,
          ultimaSalida: null,
        };
      }
      const enPista = prev.enPista.map((n) => (n === sale ? entra : n));
      const evento: Evento = {
        id: uid(),
        tipo: "cambio",
        parte,
        segundosParte: segundosParte(),
        segundosPartido: segundosPartidoTotal(),
        timestampReal: ahora,
        sale, entra,
      };
      return {
        ...prev,
        enPista,
        tiempos,
        eventos: [...prev.eventos, evento],
      };
    });
  }

  function registrarEvento(parcial: Omit<Evento, "id" | "parte" | "segundosParte" | "segundosPartido" | "timestampReal">) {
    setPartido((prev) => {
      const evento: Evento = {
        ...(parcial as Evento),
        id: uid(),
        parte: prev.cronometro.parteActual,
        segundosParte: segundosParte(),
        segundosPartido: segundosPartidoTotal(),
        timestampReal: Date.now(),
      };
      let next: Partido = { ...prev, eventos: [...prev.eventos, evento] };
      if (evento.tipo === "gol") {
        next = {
          ...next,
          marcador: {
            inter: next.marcador.inter + (evento.equipo === "INTER" ? 1 : 0),
            rival: next.marcador.rival + (evento.equipo === "RIVAL" ? 1 : 0),
          },
        };
      } else if (evento.tipo === "falta") {
        const p = prev.cronometro.parteActual;
        const cur = next.stats.faltas[p];
        next = { ...next, stats: { ...next.stats,
          faltas: { ...next.stats.faltas,
            [p]: evento.equipo === "INTER"
              ? { ...cur, inter: cur.inter + 1 }
              : { ...cur, rival: cur.rival + 1 },
          } } };
      } else if (evento.tipo === "amarilla") {
        const p = prev.cronometro.parteActual;
        const cur = next.stats.amarillas[p];
        next = { ...next, stats: { ...next.stats,
          amarillas: { ...next.stats.amarillas,
            [p]: evento.equipo === "INTER"
              ? { ...cur, inter: cur.inter + 1 }
              : { ...cur, rival: cur.rival + 1 },
          } } };
      } else if (evento.tipo === "tiempo_muerto") {
        const p = prev.cronometro.parteActual;
        const cur = next.stats.tiemposMuerto[p];
        next = { ...next, stats: { ...next.stats,
          tiemposMuerto: { ...next.stats.tiemposMuerto,
            [p]: evento.equipo === "INTER"
              ? { ...cur, inter: cur.inter + 1 }
              : { ...cur, rival: cur.rival + 1 },
          } } };
      } else if (evento.tipo === "penalti" || evento.tipo === "diezm") {
        if (evento.resultado === "GOL") {
          next.marcador = {
            inter: next.marcador.inter + (evento.equipo === "INTER" ? 1 : 0),
            rival: next.marcador.rival + (evento.equipo === "RIVAL" ? 1 : 0),
          };
        }
      }
      return next;
    });
  }

  function deshacerUltimoEvento() {
    setPartido((prev) => {
      const ev = prev.eventos[prev.eventos.length - 1];
      if (!ev) return prev;
      const eventos = prev.eventos.slice(0, -1);
      const next: Partido = { ...prev, eventos };
      if (ev.tipo === "gol") {
        next.marcador = {
          inter: next.marcador.inter - (ev.equipo === "INTER" ? 1 : 0),
          rival: next.marcador.rival - (ev.equipo === "RIVAL" ? 1 : 0),
        };
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
      } else if ((ev.tipo === "penalti" || ev.tipo === "diezm") && ev.resultado === "GOL") {
        next.marcador = {
          inter: next.marcador.inter - (ev.equipo === "INTER" ? 1 : 0),
          rival: next.marcador.rival - (ev.equipo === "RIVAL" ? 1 : 0),
        };
      }
      return next;
    });
  }

  function incAccion(nombre: string,
                       campo: "pf" | "pnf" | "robos" | "cortes" | "bdg" | "bdp",
                       delta: number = 1) {
    setPartido((prev) => {
      const cur = prev.acciones.porJugador[nombre]
        || { pf: 0, pnf: 0, robos: 0, cortes: 0, bdg: 0, bdp: 0 };
      const nuevoVal = Math.max(0, cur[campo] + delta);
      return {
        ...prev,
        acciones: {
          ...prev.acciones,
          porJugador: {
            ...prev.acciones.porJugador,
            [nombre]: { ...cur, [campo]: nuevoVal },
          },
        },
      };
    });
  }

  function reset() {
    setPartido(partidoVacio(ID_PARTIDO));
  }

  return {
    partido, cargado,
    segundosTurnoActual, segundosBanquillo, segundosParte, segundosPartidoTotal,
    segundosEnParte,
    iniciarPartido, play, pausa, avanzarParte, cambiarJugador,
    registrarEvento, deshacerUltimoEvento, incAccion, reset,
  };
}

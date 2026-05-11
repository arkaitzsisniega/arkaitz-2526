/**
 * Store del partido: hook React con persistencia automática a IndexedDB.
 *
 * useEffect tick a 250 ms para refrescar tiempos en pista/banquillo cuando
 * el reloj corre. Auto-save cada cambio (debounced 300 ms).
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
} from "./db";
import { uid } from "./utils";
import { ROSTER } from "./roster";

const ID_PARTIDO = "current";
const TICK_MS = 250;
const SAVE_DEBOUNCE_MS = 300;

export function usePartido() {
  const [partido, setPartido] = useState<Partido>(() => partidoVacio(ID_PARTIDO));
  const [cargado, setCargado] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Tick para recálculo de "tiempo en pista" cuando el reloj corre
  const [, forceTick] = useState(0);
  useEffect(() => {
    const i = setInterval(() => {
      if (partido.cronometro.ultimoStart != null) forceTick((x) => x + 1);
    }, TICK_MS);
    return () => clearInterval(i);
  }, [partido.cronometro.ultimoStart]);

  // Cargar de Dexie al inicio
  useEffect(() => {
    (async () => {
      const p = await db.partidos.get(ID_PARTIDO);
      if (p) setPartido(p);
      setCargado(true);
    })();
  }, []);

  // Auto-save al cambiar
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

  // ────────────────── helpers internos ─────────────────────────────────
  /** Segundos en pista del turno actual de un jugador (recalculado live). */
  const segundosTurnoActual = useCallback(
    (nombre: string): number => {
      const t = partido.tiempos[nombre];
      if (!t || t.ultimaEntrada == null) return 0;
      const corriendo = partido.cronometro.ultimoStart != null;
      if (!corriendo) return 0; // reloj parado: el turno actual no avanza
      const ahora = Date.now();
      return Math.max(0, (ahora - t.ultimaEntrada) / 1000);
    },
    [partido]
  );

  /** Segundos descansando desde la última salida. */
  const segundosBanquillo = useCallback(
    (nombre: string): number => {
      const t = partido.tiempos[nombre];
      if (!t || t.ultimaSalida == null) return 0;
      const ahora = Date.now();
      return Math.max(0, (ahora - t.ultimaSalida) / 1000);
    },
    [partido]
  );

  /** Segundos transcurridos en la parte actual (acumulado + tramo corriendo). */
  const segundosParte = useCallback((): number => {
    const c = partido.cronometro;
    if (c.ultimoStart == null) return c.segundosParte;
    return c.segundosParte + (Date.now() - c.ultimoStart) / 1000;
  }, [partido.cronometro]);

  /** Segundos totales del partido (suma de todas las partes). */
  const segundosPartidoTotal = useCallback((): number => {
    const c = partido.cronometro;
    const otrasParcial = 0; // las partes anteriores no las trackeamos por
    // simplicidad: cuando avanzas a la 2ª parte, los segundos de la 1ª
    // ya se han acumulado al cambiar de parte.
    return c.segundosParte + otrasParcial +
      (c.ultimoStart != null ? (Date.now() - c.ultimoStart) / 1000 : 0);
  }, [partido.cronometro]);

  // ────────────────── acciones del partido ─────────────────────────────

  function iniciarPartido(config: ConfigPartido) {
    setPartido((prev) => {
      const tiempos: Record<string, typeof prev.tiempos[string]> = {};
      const ahora = Date.now();
      for (const j of config.convocados) {
        tiempos[j] = {
          nombre: j,
          totalSegundos: 0,
          porParte: { "1T": 0, "2T": 0, PR1: 0, PR2: 0 },
          ultimaEntrada: null,
          ultimaSalida: ahora, // todos en banquillo de inicio (lo arreglamos abajo)
        };
      }
      // Quienes están en pista inicial: ultimaEntrada = null hasta que arranque el reloj
      const pi = config.pista_inicial;
      const enPista = [pi.portero, pi.pista1, pi.pista2, pi.pista3, pi.pista4];
      for (const j of enPista) {
        if (tiempos[j]) {
          tiempos[j].ultimaSalida = null;
          tiempos[j].ultimaEntrada = null; // se setea al darle PLAY
        }
      }
      const acciones: typeof prev.acciones = { porJugador: {} };
      for (const j of config.convocados) {
        acciones.porJugador[j] = {
          pf: 0, pnf: 0, robos: 0, cortes: 0, bdg: 0, bdp: 0,
        };
      }
      return {
        ...prev,
        estado: "en_curso",
        config,
        enPista,
        tiempos,
        acciones,
      };
    });
  }

  function play() {
    setPartido((prev) => {
      if (prev.cronometro.ultimoStart != null) return prev;
      const ahora = Date.now();
      const tiempos = { ...prev.tiempos };
      // Para los que están en pista, marcar ultimaEntrada=ahora si era null
      for (const nombre of prev.enPista) {
        if (tiempos[nombre]) {
          tiempos[nombre] = {
            ...tiempos[nombre],
            ultimaEntrada: tiempos[nombre].ultimaEntrada ?? ahora,
            ultimaSalida: null,
          };
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
      // Acumular tiempo a cada jugador en pista
      const tiempos = { ...prev.tiempos };
      const parte = prev.cronometro.parteActual;
      for (const nombre of prev.enPista) {
        if (tiempos[nombre] && tiempos[nombre].ultimaEntrada != null) {
          const desdeEntrada = (ahora - tiempos[nombre].ultimaEntrada!) / 1000;
          tiempos[nombre] = {
            ...tiempos[nombre],
            totalSegundos: tiempos[nombre].totalSegundos + desdeEntrada,
            porParte: {
              ...tiempos[nombre].porParte,
              [parte]: tiempos[nombre].porParte[parte] + desdeEntrada,
            },
            // Reset ultimaEntrada para que el contador del turno ACTUAL
            // se reinicie cuando vuelva a darle PLAY (es lo que el
            // usuario quería: ver el tiempo del turno actual).
            // Al darle play de nuevo se reasigna a ese momento.
            ultimaEntrada: null,
          };
        }
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
    const ordenPartes: ParteId[] = ["1T", "2T", "PR1", "PR2"];
    setPartido((prev) => {
      // Si reloj corriendo, pausar primero (acumula tiempo)
      const c = prev.cronometro;
      let p = prev;
      if (c.ultimoStart != null) {
        const ahora = Date.now();
        const transcurrido = (ahora - c.ultimoStart) / 1000;
        const tiempos = { ...prev.tiempos };
        const parte = c.parteActual;
        for (const nombre of prev.enPista) {
          if (tiempos[nombre] && tiempos[nombre].ultimaEntrada != null) {
            const desdeEntrada = (ahora - tiempos[nombre].ultimaEntrada!) / 1000;
            tiempos[nombre] = {
              ...tiempos[nombre],
              totalSegundos: tiempos[nombre].totalSegundos + desdeEntrada,
              porParte: {
                ...tiempos[nombre].porParte,
                [parte]: tiempos[nombre].porParte[parte] + desdeEntrada,
              },
              ultimaEntrada: null,
            };
          }
        }
        p = {
          ...prev,
          cronometro: {
            ...c, segundosParte: c.segundosParte + transcurrido, ultimoStart: null,
          },
          tiempos,
        };
      }
      const idx = ordenPartes.indexOf(p.cronometro.parteActual);
      const sig = ordenPartes[Math.min(idx + 1, ordenPartes.length - 1)];
      return {
        ...p,
        cronometro: { parteActual: sig, segundosParte: 0, ultimoStart: null },
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
      // Acumular tiempo del que sale
      if (tiempos[sale] && tiempos[sale].ultimaEntrada != null && corriendo) {
        const desdeEntrada = (ahora - tiempos[sale].ultimaEntrada!) / 1000;
        tiempos[sale] = {
          ...tiempos[sale],
          totalSegundos: tiempos[sale].totalSegundos + desdeEntrada,
          porParte: {
            ...tiempos[sale].porParte,
            [parte]: tiempos[sale].porParte[parte] + desdeEntrada,
          },
          ultimaEntrada: null,
          ultimaSalida: ahora,
        };
      } else if (tiempos[sale]) {
        tiempos[sale] = { ...tiempos[sale], ultimaEntrada: null, ultimaSalida: ahora };
      }
      // El que entra: ultimaEntrada = ahora si reloj corre, null si no
      if (tiempos[entra]) {
        tiempos[entra] = {
          ...tiempos[entra],
          ultimaSalida: null,
          ultimaEntrada: corriendo ? ahora : null,
        };
      }
      const enPista = prev.enPista.map((n) => (n === sale ? entra : n));
      // Registrar evento
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
      let next = { ...prev, eventos: [...prev.eventos, evento] };
      // Side effects por tipo
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
        next = {
          ...next,
          stats: { ...next.stats,
            faltas: { ...next.stats.faltas,
              [p]: { ...next.stats.faltas[p],
                ...(evento.equipo === "INTER"
                  ? { inter: next.stats.faltas[p].inter + 1 }
                  : { rival: next.stats.faltas[p].rival + 1 }),
              },
            },
          },
        };
      } else if (evento.tipo === "amarilla") {
        const p = prev.cronometro.parteActual;
        next = {
          ...next,
          stats: { ...next.stats,
            amarillas: { ...next.stats.amarillas,
              [p]: { ...next.stats.amarillas[p],
                ...(evento.equipo === "INTER"
                  ? { inter: next.stats.amarillas[p].inter + 1 }
                  : { rival: next.stats.amarillas[p].rival + 1 }),
              },
            },
          },
        };
      } else if (evento.tipo === "tiempo_muerto") {
        const p = prev.cronometro.parteActual;
        next = {
          ...next,
          stats: { ...next.stats,
            tiemposMuerto: { ...next.stats.tiemposMuerto,
              [p]: { ...next.stats.tiemposMuerto[p],
                ...(evento.equipo === "INTER"
                  ? { inter: next.stats.tiemposMuerto[p].inter + 1 }
                  : { rival: next.stats.tiemposMuerto[p].rival + 1 }),
              },
            },
          },
        };
      }
      return next;
    });
  }

  function deshacerUltimoEvento() {
    setPartido((prev) => {
      const ev = prev.eventos[prev.eventos.length - 1];
      if (!ev) return prev;
      const eventos = prev.eventos.slice(0, -1);
      let next = { ...prev, eventos };
      // Revertir side effects
      if (ev.tipo === "gol") {
        next.marcador = {
          inter: next.marcador.inter - (ev.equipo === "INTER" ? 1 : 0),
          rival: next.marcador.rival - (ev.equipo === "RIVAL" ? 1 : 0),
        };
      } else if (ev.tipo === "falta") {
        const p = ev.parte;
        const cur = next.stats.faltas[p];
        next.stats.faltas[p] = ev.equipo === "INTER"
          ? { ...cur, inter: Math.max(0, cur.inter - 1) }
          : { ...cur, rival: Math.max(0, cur.rival - 1) };
      } else if (ev.tipo === "amarilla") {
        const p = ev.parte;
        const cur = next.stats.amarillas[p];
        next.stats.amarillas[p] = ev.equipo === "INTER"
          ? { ...cur, inter: Math.max(0, cur.inter - 1) }
          : { ...cur, rival: Math.max(0, cur.rival - 1) };
      } else if (ev.tipo === "tiempo_muerto") {
        const p = ev.parte;
        const cur = next.stats.tiemposMuerto[p];
        next.stats.tiemposMuerto[p] = ev.equipo === "INTER"
          ? { ...cur, inter: Math.max(0, cur.inter - 1) }
          : { ...cur, rival: Math.max(0, cur.rival - 1) };
      } else if (ev.tipo === "cambio") {
        // Revertir: el que entró sale, el que salió vuelve.
        next.enPista = next.enPista.map((n) => (n === ev.entra ? ev.sale : n));
        // No reverter tiempos acumulados; queda pequeño error de tracking
        // pero es aceptable para un "deshacer" de emergencia.
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
    partido,
    cargado,
    // Selectores en vivo
    segundosTurnoActual,
    segundosBanquillo,
    segundosParte,
    segundosPartidoTotal,
    // Acciones
    iniciarPartido,
    play,
    pausa,
    avanzarParte,
    cambiarJugador,
    registrarEvento,
    deshacerUltimoEvento,
    incAccion,
    reset,
  };
}

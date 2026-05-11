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
  type Partido,
  type ParteId,
  type ConfigPartido,
  type Evento,
  type TiempoJugador,
  type ContadoresJugador,
  type ResultadoDisparo,
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
    }, TICK_MS);
    return () => clearInterval(i);
  }, []);

  useEffect(() => {
    (async () => {
      const p = await db.partidos.get(ID_PARTIDO);
      if (p) {
        // Migración suave: añadir campos nuevos si vienen de versión antigua.
        const migrado: Partido = {
          ...p,
          disparosRival: p.disparosRival ?? { puerta: 0, fuera: 0, palo: 0, bloqueado: 0 },
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
    return segundosParte();
  }, [segundosParte]);

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
          turnoStart: null,
          ultimaSalida: enPista ? null : ahora,
        };
      }
      const acciones: typeof prev.acciones = { porJugador: {} };
      for (const j of config.convocados) {
        acciones.porJugador[j] = contadoresVacios();
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
      const tiempos = { ...prev.tiempos };
      for (const nombre of prev.enPista) {
        const t = tiempos[nombre];
        if (t) tiempos[nombre] = { ...t, turnoStart: ahora };
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
      const tSale = tiempos[sale];
      if (tSale) {
        const cong = congelaTurno(tSale, parte);
        tiempos[sale] = { ...cong, segTurnoActual: null, ultimaSalida: ahora };
      }
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
          if (evento.resultado === "PUERTA") {
            // Si fue a puerta pero no es gol (parada), portero +1 parada... no
            // tenemos campo "paradas"; lo dejamos solo en disparosRival.puerta.
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

  function reset() {
    setPartido(partidoVacio(ID_PARTIDO));
  }

  return {
    partido, cargado,
    segundosTurnoActual, segundosBanquillo, segundosParte, segundosPartidoTotal,
    segundosEnParte,
    iniciarPartido, play, pausa, ajustarReloj, avanzarParte, cambiarJugador,
    registrarEvento, deshacerUltimoEvento, incAccion, reset,
  };
}

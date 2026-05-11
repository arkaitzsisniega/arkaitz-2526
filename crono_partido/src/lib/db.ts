/**
 * Persistencia local con Dexie (IndexedDB). Una "partida" = un partido.
 * El partido se serializa entero cada vez que cambia. Sencillo y robusto
 * para offline + recuperación tras cierre accidental de la pestaña.
 */
import Dexie, { type Table } from "dexie";

export type ParteId = "1T" | "2T" | "PR1" | "PR2";

export interface ConfigPartido {
  rival: string;
  fecha: string;             // YYYY-MM-DD
  hora: string;              // "18:00"
  lugar: string;
  competicion: string;       // LIGA, COPA_REY, etc.
  local: boolean;            // true = INTER local, false = visitante
  partido_id: string;        // ej. J29.VALDEPEÑAS
  convocados: string[];      // nombres canónicos
  pista_inicial: {
    portero: string;
    pista1: string;
    pista2: string;
    pista3: string;
    pista4: string;
  };
}

export interface TiempoJugador {
  /** Nombre canónico */
  nombre: string;
  /** Segundos totales en pista del partido (acumulado, todas las partes). */
  totalSegundos: number;
  /** Segundos en pista por parte. */
  porParte: Record<ParteId, number>;
  /**
   * Si está EN PISTA: timestamp (ms) de cuándo entró por última vez (o
   * inicio del partido). El tiempo en pista actual se calcula como
   * "ahora - ultimaEntrada" cuando el reloj corre.
   * null = está en banquillo.
   */
  ultimaEntrada: number | null;
  /**
   * Si está EN BANQUILLO: timestamp (ms) de cuándo se sentó en el
   * banquillo. null = está en pista o nunca jugó.
   */
  ultimaSalida: number | null;
}

export interface EventoBase {
  id: string;
  parte: ParteId;
  segundosParte: number;    // segundos transcurridos en la parte cuando ocurrió
  segundosPartido: number;  // segundos totales del partido (suma de partes)
  timestampReal: number;    // Date.now() cuando se apuntó
}

export type Evento =
  | (EventoBase & { tipo: "gol"; equipo: "INTER" | "RIVAL"; goleador: string;
      asistente?: string; cuarteto: string[]; portero?: string;
      accion?: string; zonaPorteria?: string; descripcion?: string })
  | (EventoBase & { tipo: "falta"; equipo: "INTER" | "RIVAL"; jugador?: string })
  | (EventoBase & { tipo: "amarilla"; equipo: "INTER" | "RIVAL"; jugador?: string })
  | (EventoBase & { tipo: "roja"; equipo: "INTER" | "RIVAL"; jugador?: string })
  | (EventoBase & { tipo: "tiempo_muerto"; equipo: "INTER" | "RIVAL" })
  | (EventoBase & { tipo: "cambio"; sale: string; entra: string })
  | (EventoBase & { tipo: "penalti"; equipo: "INTER" | "RIVAL"; tirador: string;
      portero: string; resultado: "GOL" | "PARADA" | "POSTE" | "FUERA";
      zona?: string })
  | (EventoBase & { tipo: "diezm"; equipo: "INTER" | "RIVAL"; tirador: string;
      portero: string; resultado: "GOL" | "PARADA" | "POSTE" | "FUERA";
      zona?: string });

export interface EstadoCronometro {
  parteActual: ParteId;
  /** ms que lleva el reloj corriendo en la parte ACTUAL. Se acumula. */
  segundosParte: number;
  /** Si el reloj está corriendo, ms desde el último start (Date.now()). null si pausado. */
  ultimoStart: number | null;
}

export interface AccionesIndividuales {
  /** Por jugador → conteo de cada métrica. Se modifica por toques +/− del compañero. */
  porJugador: Record<string, {
    pf: number;
    pnf: number;
    robos: number;
    cortes: number;
    bdg: number;
    bdp: number;
  }>;
}

export interface Partido {
  /** Id estable del partido para Dexie. Por defecto "current". */
  id: string;
  estado: "configurando" | "en_curso" | "finalizado";
  config: ConfigPartido | null;
  cronometro: EstadoCronometro;
  /** Plantilla en pista actual + tiempos por jugador. */
  enPista: string[];                          // nombres canónicos (5: portero+4 campo)
  tiempos: Record<string, TiempoJugador>;     // todos los convocados
  marcador: { inter: number; rival: number };
  stats: {
    faltas: Record<ParteId, { inter: number; rival: number }>;
    amarillas: Record<ParteId, { inter: number; rival: number }>;
    tiemposMuerto: Record<ParteId, { inter: number; rival: number }>;
  };
  eventos: Evento[];
  acciones: AccionesIndividuales;
  /** ms del último cambio (para auto-save / recuperación). */
  actualizado: number;
}

class CronoDB extends Dexie {
  partidos!: Table<Partido, string>;
  constructor() {
    super("crono_partido");
    this.version(1).stores({
      partidos: "id, estado, actualizado",
    });
  }
}

export const db = new CronoDB();

/** Estado vacío para un partido nuevo. */
export function partidoVacio(id = "current"): Partido {
  return {
    id,
    estado: "configurando",
    config: null,
    cronometro: {
      parteActual: "1T",
      segundosParte: 0,
      ultimoStart: null,
    },
    enPista: [],
    tiempos: {},
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
    acciones: { porJugador: {} },
    actualizado: Date.now(),
  };
}

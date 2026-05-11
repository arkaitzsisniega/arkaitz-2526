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
   * Si está EN PISTA: segundos acumulados del TURNO ACTUAL en pista.
   * Se incrementa solo cuando el reloj corre; al pausar se "congela".
   * Al volver a darle PLAY, sigue acumulando. Se reinicia a 0 cuando
   * el jugador SALE de pista y vuelve a entrar.
   * null = jugador no está en pista.
   */
  segTurnoActual: number | null;
  /**
   * Timestamp (ms) de cuándo se inició el tramo de cuenta más reciente.
   * Si reloj corre y jugador en pista, está set. En cualquier otro caso, null.
   * Para calcular tiempo en pista en VIVO: segTurnoActual + (ahora - turnoStart).
   */
  turnoStart: number | null;
  /**
   * Timestamp (ms) de cuándo se sentó en el banquillo por última vez.
   * El tiempo descansando = ahora - ultimaSalida. null = está en pista
   * o nunca ha jugado.
   */
  ultimaSalida: number | null;
}

/** Resultado posible de un disparo (a puerta = entró marco, parada portero o gol). */
export type ResultadoDisparo = "PUERTA" | "PALO" | "FUERA" | "BLOQUEADO";

export interface EventoBase {
  id: string;
  parte: ParteId;
  segundosParte: number;    // segundos transcurridos en la parte cuando ocurrió
  segundosPartido: number;  // segundos totales del partido (suma de partes)
  timestampReal: number;    // Date.now() cuando se apuntó
  /** Marcador en el momento del evento (snapshot). */
  marcador: { inter: number; rival: number };
}

export type Evento =
  | (EventoBase & { tipo: "gol"; equipo: "INTER" | "RIVAL"; goleador: string;
      asistente?: string; cuarteto: string[]; portero?: string;
      accion?: string; zonaCampo?: string; zonaPorteria?: string;
      descripcion?: string;
      /** Si este gol vino de un penalti/10m, id del evento penalti enlazado. */
      penaltiId?: string })
  | (EventoBase & { tipo: "falta"; equipo: "INTER" | "RIVAL";
      jugador?: string; sinAsignar?: boolean; rivalMano?: boolean;
      zonaCampo?: string })
  | (EventoBase & { tipo: "amarilla"; equipo: "INTER" | "RIVAL"; jugador?: string })
  | (EventoBase & { tipo: "roja"; equipo: "INTER" | "RIVAL"; jugador?: string })
  | (EventoBase & { tipo: "tiempo_muerto"; equipo: "INTER" | "RIVAL" })
  | (EventoBase & { tipo: "cambio"; sale: string; entra: string })
  | (EventoBase & { tipo: "disparo"; equipo: "INTER" | "RIVAL";
      jugador?: string;            // tirador (si INTER); si RIVAL puede no estar
      portero?: string;            // portero nuestro (si RIVAL) o rival (si INTER)
      resultado: ResultadoDisparo;
      zonaCampo?: string;
      zonaPorteria?: string;
      /** Si este disparo está enlazado a un gol/penalti, id. */
      golId?: string;
      penaltiId?: string })
  | (EventoBase & { tipo: "penalti"; equipo: "INTER" | "RIVAL"; tirador: string;
      portero: string; resultado: "GOL" | "PARADA" | "POSTE" | "FUERA";
      zonaPorteria?: string;
      /** Id del gol enlazado (si resultado=GOL). */
      golId?: string })
  | (EventoBase & { tipo: "diezm"; equipo: "INTER" | "RIVAL"; tirador: string;
      portero: string; resultado: "GOL" | "PARADA" | "POSTE" | "FUERA";
      zonaPorteria?: string;
      golId?: string });

export interface EstadoCronometro {
  parteActual: ParteId;
  /** ms que lleva el reloj corriendo en la parte ACTUAL. Se acumula. */
  segundosParte: number;
  /** Si el reloj está corriendo, ms desde el último start (Date.now()). null si pausado. */
  ultimoStart: number | null;
}

/** Contadores por jugador. Todos opcionales con default 0 al leer. */
export interface ContadoresJugador {
  pf: number;        // Pérdidas forzadas
  pnf: number;       // Pérdidas no forzadas
  robos: number;
  cortes: number;
  bdg: number;       // Balones dividos ganados
  bdp: number;       // Balones divididos perdidos
  // Disparos (auto-incrementados por golazos, paradas, penaltis, etc.)
  dpp: number;       // Disparos a puerta (incluye gol)
  dpf: number;       // Disparos fuera
  dpa: number;       // Disparos al palo
  dpb: number;       // Disparos bloqueados
  // Solo porteros
  golesEncajados: number;
}

export interface AccionesIndividuales {
  porJugador: Record<string, ContadoresJugador>;
}

/** Disparos del equipo rival agregados (no tenemos jugadores rivales identificados). */
export interface DisparosRival {
  puerta: number;
  fuera: number;
  palo: number;
  bloqueado: number;
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
  disparosRival: DisparosRival;
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

export function contadoresVacios(): ContadoresJugador {
  return {
    pf: 0, pnf: 0, robos: 0, cortes: 0, bdg: 0, bdp: 0,
    dpp: 0, dpf: 0, dpa: 0, dpb: 0, golesEncajados: 0,
  };
}

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
    disparosRival: { puerta: 0, fuera: 0, palo: 0, bloqueado: 0 },
    actualizado: Date.now(),
  };
}

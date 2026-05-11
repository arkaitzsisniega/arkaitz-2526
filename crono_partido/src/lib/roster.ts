/**
 * Roster oficial del Inter (canónicos según JUGADORES_ROSTER del Sheet).
 * Sincronizado a 12/05/2026 — HERRERO, GARCIA, GONZALO (sin J. ni Gonza).
 */

export type Posicion = "PORTERO" | "CAMPO";
export type Equipo = "PRIMER" | "FILIAL";

export interface Jugador {
  dorsal: string;
  nombre: string;
  posicion: Posicion;
  equipo: Equipo;
}

export const ROSTER: Jugador[] = [
  // Porteros primer equipo
  { dorsal: "1", nombre: "HERRERO", posicion: "PORTERO", equipo: "PRIMER" },
  { dorsal: "27", nombre: "GARCIA", posicion: "PORTERO", equipo: "PRIMER" },
  // Campo primer equipo
  { dorsal: "2", nombre: "CECILIO", posicion: "CAMPO", equipo: "PRIMER" },
  { dorsal: "5", nombre: "CHAGUINHA", posicion: "CAMPO", equipo: "PRIMER" },
  { dorsal: "6", nombre: "RAUL", posicion: "CAMPO", equipo: "PRIMER" },
  { dorsal: "7", nombre: "HARRISON", posicion: "CAMPO", equipo: "PRIMER" },
  { dorsal: "8", nombre: "RAYA", posicion: "CAMPO", equipo: "PRIMER" },
  { dorsal: "10", nombre: "JAVI", posicion: "CAMPO", equipo: "PRIMER" },
  { dorsal: "11", nombre: "PANI", posicion: "CAMPO", equipo: "PRIMER" },
  { dorsal: "17", nombre: "PIRATA", posicion: "CAMPO", equipo: "PRIMER" },
  { dorsal: "18", nombre: "BARONA", posicion: "CAMPO", equipo: "PRIMER" },
  { dorsal: "20", nombre: "CARLOS", posicion: "CAMPO", equipo: "PRIMER" },
  // Portero filial
  { dorsal: "28", nombre: "OSCAR", posicion: "PORTERO", equipo: "FILIAL" },
  // Campo filial
  { dorsal: "14", nombre: "RUBIO", posicion: "CAMPO", equipo: "FILIAL" },
  { dorsal: "15", nombre: "JAIME", posicion: "CAMPO", equipo: "FILIAL" },
  { dorsal: "22", nombre: "SEGO", posicion: "CAMPO", equipo: "FILIAL" },
  { dorsal: "25", nombre: "DANI", posicion: "CAMPO", equipo: "FILIAL" },
  { dorsal: "31", nombre: "GONZALO", posicion: "CAMPO", equipo: "FILIAL" },
  { dorsal: "", nombre: "PABLO", posicion: "CAMPO", equipo: "FILIAL" },
  { dorsal: "", nombre: "GABRI", posicion: "CAMPO", equipo: "FILIAL" },
  { dorsal: "", nombre: "NACHO", posicion: "CAMPO", equipo: "FILIAL" },
  { dorsal: "", nombre: "ANCHU", posicion: "CAMPO", equipo: "FILIAL" },
];

export const PORTEROS = ROSTER.filter((j) => j.posicion === "PORTERO");
export const CAMPO = ROSTER.filter((j) => j.posicion === "CAMPO");

/**
 * Helpers comunes: formato de tiempos, cálculo de minutos en pista, etc.
 */

/** Segundos → "MM:SS" */
export function formatMMSS(segundos: number): string {
  if (!isFinite(segundos) || segundos < 0) segundos = 0;
  const m = Math.floor(segundos / 60);
  const s = Math.floor(segundos % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

/** Segundos → "M:SS" más compacto (sin ceros a la izquierda en min) */
export function formatMSS(segundos: number): string {
  if (!isFinite(segundos) || segundos < 0) segundos = 0;
  const m = Math.floor(segundos / 60);
  const s = Math.floor(segundos % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Color de fondo según minutos en pista del turno actual.
 * <1' verde (fresco), 1-2' amarillo (atento), 2-3' naranja (mira), >3' rojo (cambia ya).
 */
export function colorTiempoPista(segundos: number): string {
  if (segundos < 60) return "bg-green-600";
  if (segundos < 120) return "bg-yellow-500";
  if (segundos < 180) return "bg-orange-500";
  return "bg-red-600";
}

/** Color de tiempo descansando: más oscuro cuanto MÁS descansa (más fresco). */
export function colorTiempoBanquillo(segundos: number): string {
  if (segundos < 30) return "bg-zinc-700";   // recién salido, caliente
  if (segundos < 90) return "bg-zinc-500";   // medio
  return "bg-zinc-400";                       // descansado, fresco
}

/** Generar UUID corto sin dependencias. */
export function uid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

/** ISO yyyy-mm-dd de la fecha actual */
export function hoyISO(): string {
  return new Date().toISOString().slice(0, 10);
}

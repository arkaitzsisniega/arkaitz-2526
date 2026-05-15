"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { usePartido } from "@/lib/store";
import { ROSTER } from "@/lib/roster";
import { formatMMSS } from "@/lib/utils";
import { CampoConteos } from "@/components/CampoConteos";
import type { Evento, ParteId, Partido } from "@/lib/db";
import { direccionAtaque } from "@/lib/db";

const PARTES: ParteId[] = ["1T", "2T", "PR1", "PR2"];

// ─── Helpers de presentación ────────────────────────────────────────────

const LBL_ACCION: Record<string, string> = {
  pf: "PF", pnf: "PNF", robos: "Robo", cortes: "Corte",
  bdg: "BDG", bdp: "BDP",
};

function emojiEvento(ev: Evento): string {
  switch (ev.tipo) {
    case "gol":               return "⚽";
    case "falta":             return "⚠️";
    case "amarilla":          return "🟨";
    case "roja":              return "🟥";
    case "tiempo_muerto":     return "🛑";
    case "cambio":            return "🔄";
    case "disparo":           return "🎯";
    case "penalti":           return "🥅";
    case "diezm":             return "📌";
    case "accion_individual": return "👤";
    default:                  return "•";
  }
}

function descripcionEvento(ev: Evento, rival: string): string {
  const equipoTxt = (e: "INTER" | "RIVAL") => e === "INTER" ? "INTER" : rival;
  try {
    switch (ev.tipo) {
      case "gol": {
        const quien = ev.equipo === "INTER" ? (ev.goleador || "?") : rival;
        const ext: string[] = [];
        if (ev.asistente) ext.push(`asist. ${ev.asistente}`);
        if (ev.accion)    ext.push(ev.accion);
        if (ev.zonaCampo) ext.push(`desde ${ev.zonaCampo}`);
        if (ev.zonaPorteria) ext.push(`a ${ev.zonaPorteria}`);
        return `Gol ${equipoTxt(ev.equipo)} — ${quien}${ext.length ? ` (${ext.join(", ")})` : ""}`;
      }
      case "falta": {
        const q = ev.jugador ?? (ev.sinAsignar ? "sin asignar" : (ev.rivalMano ? "mano" : "—"));
        const zona = ev.zonaCampo ? ` · ${ev.zonaCampo}` : "";
        return `Falta ${equipoTxt(ev.equipo)} — ${q}${zona}`;
      }
      case "amarilla":
        return `Amarilla ${equipoTxt(ev.equipo)}${ev.jugador ? ` — ${ev.jugador}` : ""}`;
      case "roja":
        return `Roja ${equipoTxt(ev.equipo)}${ev.jugador ? ` — ${ev.jugador}` : ""}`;
      case "tiempo_muerto":
        return `Tiempo muerto ${equipoTxt(ev.equipo)}`;
      case "cambio":
        return `Cambio — entra ${ev.entra}, sale ${ev.sale}`;
      case "disparo": {
        const ext: string[] = [];
        if (ev.zonaCampo) ext.push(`desde ${ev.zonaCampo}`);
        if (ev.zonaPorteria) ext.push(`a ${ev.zonaPorteria}`);
        const quien = ev.jugador ?? rival;
        return `Disparo ${equipoTxt(ev.equipo)} — ${quien} (${ev.resultado}${ext.length ? `, ${ext.join(", ")}` : ""})`;
      }
      case "penalti":
      case "diezm": {
        const tipoTxt = ev.tipo === "penalti" ? "Penalti" : "10m";
        const ext: string[] = [];
        if (ev.zonaPorteria) ext.push(ev.zonaPorteria);
        return `${tipoTxt} ${equipoTxt(ev.equipo)} — ${ev.tirador || "?"} → ${ev.resultado}${ext.length ? ` (${ext.join(", ")})` : ""}`;
      }
      case "accion_individual": {
        const lbl = LBL_ACCION[ev.accion] ?? ev.accion;
        return `${lbl} — ${ev.jugador}${ev.zonaCampo ? ` (${ev.zonaCampo})` : ""}`;
      }
      default:
        return JSON.stringify(ev);
    }
  } catch {
    return "(evento sin formato)";
  }
}

/**
 * Reconstruye, recorriendo los eventos cronológicamente, la pista en
 * cada momento, y cuenta cuántos goles a favor (gf) y en contra (gc) ha
 * vivido cada jugador, además de goles propios + asistencias.
 */
function calcularResumenIndividual(partido: Partido) {
  const cfg = partido.config!;
  // Estado de pista al inicio
  const pi = cfg.pista_inicial;
  let pista = new Set<string>([pi.portero, pi.pista1, pi.pista2, pi.pista3, pi.pista4]);

  type Reg = { gf: number; gc: number; goles: number; asistencias: number };
  const reg: Record<string, Reg> = {};
  for (const n of cfg.convocados) reg[n] = { gf: 0, gc: 0, goles: 0, asistencias: 0 };

  const eventosOrden = [...partido.eventos].sort(
    (a, b) => (a.timestampReal || 0) - (b.timestampReal || 0)
  );
  for (const ev of eventosOrden) {
    if (ev.tipo === "cambio") {
      pista.delete(ev.sale);
      pista.add(ev.entra);
    } else if (ev.tipo === "gol") {
      // Plus/minus para todos los que estaban en pista
      for (const n of pista) {
        if (!reg[n]) continue;
        if (ev.equipo === "INTER") reg[n].gf += 1;
        else reg[n].gc += 1;
      }
      if (ev.equipo === "INTER") {
        if (ev.goleador && reg[ev.goleador]) reg[ev.goleador].goles += 1;
        if (ev.asistente && reg[ev.asistente]) reg[ev.asistente].asistencias += 1;
      }
    }
  }
  return reg;
}

// Semáforo de minutos para tab Tiempos (excluye porteros del cálculo).
function colorSemaforoMin(seg: number, max: number): string {
  if (max <= 0) return "bg-zinc-800";
  const pct = seg / max;
  if (pct >= 0.85) return "bg-red-700/40";
  if (pct >= 0.65) return "bg-orange-600/40";
  if (pct >= 0.40) return "bg-yellow-600/30";
  if (pct >= 0.20) return "bg-green-700/30";
  return "bg-green-900/30";
}

// ─── Página resumen ─────────────────────────────────────────────────────

export default function ResumenPage() {
  const router = useRouter();
  const { partido, cargado } = usePartido();
  const [tab, setTab] = useState<"general" | "tiempos" | "individual" | "cronograma" | "disparos" | "analisis">("general");

  if (!cargado) {
    return <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">Cargando…</div>;
  }
  if (!partido.config) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center gap-4">
        <p>No hay partido para resumir.</p>
        <Link href="/" className="px-6 py-3 bg-zinc-800 rounded-lg">🏠 Inicio</Link>
      </div>
    );
  }

  const cfg = partido.config;
  const partesJugadas = PARTES.filter((p) => (cfg.duracionParte[p] ?? 0) > 0);

  // Eventos por parte (orden cronológico)
  const eventosOrdenados = [...partido.eventos].sort((a, b) => {
    const pa = PARTES.indexOf(a.parte);
    const pb = PARTES.indexOf(b.parte);
    if (pa !== pb) return pa - pb;
    return (a.segundosParte || 0) - (b.segundosParte || 0);
  });

  // Stats por parte
  const stats = partido.stats;

  // Tiempos por jugador
  const filasTiempos = cfg.convocados.map((nombre) => {
    const t = partido.tiempos[nombre];
    const enPista = partido.enPista.includes(nombre);
    const liveExtra = (enPista && t?.turnoStart != null && partido.cronometro.ultimoStart != null)
      ? (Date.now() - t.turnoStart) / 1000 : 0;
    const porParte: Record<ParteId, number> = t
      ? { ...t.porParte, [partido.cronometro.parteActual]: (t.porParte[partido.cronometro.parteActual] ?? 0) + liveExtra }
      : { "1T": 0, "2T": 0, PR1: 0, PR2: 0 };
    const total = (t?.totalSegundos ?? 0) + liveExtra;
    const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
    return { nombre, total, porParte, esPortero, enPista };
  });
  filasTiempos.sort((a, b) => {
    if (a.enPista !== b.enPista) return a.enPista ? -1 : 1;
    return b.total - a.total;
  });

  // Para semáforo: máximo de minutos jugados entre jugadores NO portero
  const maxMinJugados = filasTiempos
    .filter((f) => !f.esPortero)
    .reduce((m, f) => Math.max(m, f.total), 0);

  // Plus/minus + goles + asistencias por jugador
  const regIndiv = calcularResumenIndividual(partido);

  // Filas individuales para la tabla de la pestaña "Individual"
  const filasIndiv = cfg.convocados.map((nombre) => {
    const c = partido.acciones.porJugador[nombre] || null;
    const r = regIndiv[nombre] || { gf: 0, gc: 0, goles: 0, asistencias: 0 };
    const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
    return { nombre, c, r, esPortero };
  });

  // Totales del equipo (para tab General — bloque principal)
  const totalesEquipo = filasIndiv.reduce((acc, f) => ({
    dpp: acc.dpp + (f.c?.dpp || 0),
    dpa: acc.dpa + (f.c?.dpa || 0),
    dpf: acc.dpf + (f.c?.dpf || 0),
    dpb: acc.dpb + (f.c?.dpb || 0),
    pf:  acc.pf  + (f.c?.pf  || 0),
    pnf: acc.pnf + (f.c?.pnf || 0),
    robos:  acc.robos  + (f.c?.robos  || 0),
    cortes: acc.cortes + (f.c?.cortes || 0),
    bdg: acc.bdg + (f.c?.bdg || 0),
    bdp: acc.bdp + (f.c?.bdp || 0),
  }), { dpp:0,dpa:0,dpf:0,dpb:0,pf:0,pnf:0,robos:0,cortes:0,bdg:0,bdp:0 });

  // Marcador final (incluye tanda si la hubo)
  const tanda = partido.tanda;
  const huboTanda = tanda && tanda.tiros.length > 0;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-4">
      {/* HEADER */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <button onClick={() => router.push("/partido")}
            className="text-sm text-zinc-400 hover:text-zinc-200">
            ← Volver al partido
          </button>
          <h1 className="text-2xl font-bold">🏁 Resumen del partido</h1>
          <Link href="/" className="text-sm text-zinc-400 hover:text-zinc-200">
            Inicio →
          </Link>
        </div>
        <div className="bg-zinc-900 rounded-xl p-4">
          <div className="text-sm text-zinc-400 mb-1">
            {cfg.partido_id} · {cfg.competicion} · {cfg.fecha} {cfg.hora} · {cfg.lugar || "—"}
          </div>
          <div className="text-4xl font-bold tabular-nums flex items-center justify-center gap-3">
            <span className="text-emerald-400">INTER</span>
            <span className="text-5xl">{partido.marcador.inter}</span>
            <span className="text-zinc-500">-</span>
            <span className="text-5xl">{partido.marcador.rival}</span>
            <span className="text-red-400">{cfg.rival}</span>
          </div>
          {huboTanda && (
            <div className="text-center mt-2 text-pink-400 text-sm">
              🥇 Tanda penaltis: <strong>{tanda.marcador.inter} - {tanda.marcador.rival}</strong>
              {" "}({tanda.tiros.length} tiros)
            </div>
          )}
          <div className="mt-3 text-xs text-zinc-500 text-center">
            Estado: <strong className="text-zinc-300">{partido.estado}</strong>
            {" · "}
            Partes jugadas: <strong className="text-zinc-300">{partesJugadas.join(", ")}</strong>
          </div>
        </div>
      </div>

      {/* TABS */}
      <div className="flex gap-1 mb-4 overflow-x-auto">
        {[
          { id: "general",    lbl: "📊 General" },
          { id: "tiempos",    lbl: "⏱ Tiempos" },
          { id: "individual", lbl: "👤 Individual" },
          { id: "cronograma", lbl: "📅 Cronograma" },
          { id: "disparos",   lbl: "🎯 Disparos" },
          { id: "analisis",   lbl: "🧠 Análisis" },
        ].map((t) => (
          <button key={t.id}
            onClick={() => setTab(t.id as any)}
            className={`px-4 py-2 rounded-lg text-sm font-semibold whitespace-nowrap ${
              tab === t.id ? "bg-emerald-700" : "bg-zinc-800 hover:bg-zinc-700"
            }`}>{t.lbl}</button>
        ))}
      </div>

      {/* TAB: GENERAL */}
      {tab === "general" && (
        <div className="space-y-4">
          {/* CABECERA: Disparos NUESTROS vs RIVAL */}
          <div className="bg-zinc-900 rounded-xl p-6">
            <h3 className="text-xl font-bold text-zinc-300 mb-4">🎯 Disparos</h3>
            <div className="grid grid-cols-2 gap-5">
              {/* INTER */}
              <div className="bg-emerald-900/30 rounded-lg p-5">
                <div className="text-lg text-emerald-300 font-bold mb-3">INTER</div>
                <div className="grid grid-cols-2 gap-x-5 gap-y-2 text-base">
                  <div className="flex justify-between"><span>Puerta</span><strong>{totalesEquipo.dpp}</strong></div>
                  <div className="flex justify-between"><span>Palo</span><strong>{totalesEquipo.dpa}</strong></div>
                  <div className="flex justify-between"><span>Fuera</span><strong>{totalesEquipo.dpf}</strong></div>
                  <div className="flex justify-between"><span>Bloqueados</span><strong>{totalesEquipo.dpb}</strong></div>
                </div>
                <div className="border-t border-emerald-700/50 mt-4 pt-3 flex justify-between text-emerald-200 text-xl font-bold">
                  <span>Total</span>
                  <strong>{totalesEquipo.dpp+totalesEquipo.dpa+totalesEquipo.dpf+totalesEquipo.dpb}</strong>
                </div>
              </div>
              {/* RIVAL */}
              <div className="bg-red-900/30 rounded-lg p-5">
                <div className="text-lg text-red-300 font-bold mb-3">{cfg.rival}</div>
                <div className="grid grid-cols-2 gap-x-5 gap-y-2 text-base">
                  <div className="flex justify-between"><span>Puerta</span><strong>{partido.disparosRival.puerta}</strong></div>
                  <div className="flex justify-between"><span>Palo</span><strong>{partido.disparosRival.palo}</strong></div>
                  <div className="flex justify-between"><span>Fuera</span><strong>{partido.disparosRival.fuera}</strong></div>
                  <div className="flex justify-between"><span>Bloqueados</span><strong>{partido.disparosRival.bloqueado}</strong></div>
                </div>
                <div className="border-t border-red-700/50 mt-4 pt-3 flex justify-between text-red-200 text-xl font-bold">
                  <span>Total</span>
                  <strong>{partido.disparosRival.puerta+partido.disparosRival.palo+partido.disparosRival.fuera+partido.disparosRival.bloqueado}</strong>
                </div>
              </div>
            </div>
          </div>

          {/* SEGUNDA FILA — Pérdidas, Recuperaciones, Divididos del INTER */}
          <div className="bg-zinc-900 rounded-xl p-6">
            <h3 className="text-xl font-bold text-zinc-300 mb-4">📊 Stats INTER</h3>
            <div className="grid grid-cols-3 gap-4">
              {/* Pérdidas */}
              <div className="bg-red-900/30 rounded-lg p-5">
                <div className="text-lg text-red-300 font-bold mb-3">❌ Pérdidas</div>
                <div className="text-base space-y-2">
                  <div className="flex justify-between"><span>Forzada</span><strong>{totalesEquipo.pf}</strong></div>
                  <div className="flex justify-between"><span>No forzada</span><strong>{totalesEquipo.pnf}</strong></div>
                  <div className="border-t border-red-700/50 mt-3 pt-3 flex justify-between text-red-200 text-lg font-bold">
                    <span>Total</span><strong>{totalesEquipo.pf+totalesEquipo.pnf}</strong>
                  </div>
                </div>
              </div>
              {/* Recuperaciones */}
              <div className="bg-green-900/30 rounded-lg p-5">
                <div className="text-lg text-green-300 font-bold mb-3">✅ Recuperaciones</div>
                <div className="text-base space-y-2">
                  <div className="flex justify-between"><span>Robos</span><strong>{totalesEquipo.robos}</strong></div>
                  <div className="flex justify-between"><span>Cortes</span><strong>{totalesEquipo.cortes}</strong></div>
                  <div className="border-t border-green-700/50 mt-3 pt-3 flex justify-between text-green-200 text-lg font-bold">
                    <span>Total</span><strong>{totalesEquipo.robos+totalesEquipo.cortes}</strong>
                  </div>
                </div>
              </div>
              {/* Balones divididos */}
              <div className="bg-purple-900/30 rounded-lg p-5">
                <div className="text-lg text-purple-300 font-bold mb-3">⚖️ Balones divididos</div>
                <div className="text-base space-y-2">
                  <div className="flex justify-between"><span>Ganados</span><strong>{totalesEquipo.bdg}</strong></div>
                  <div className="flex justify-between"><span>No ganados</span><strong>{totalesEquipo.bdp}</strong></div>
                  <div className="border-t border-purple-700/50 mt-3 pt-3 flex justify-between text-purple-200 text-lg font-bold">
                    <span>Ratio</span>
                    <strong>{(totalesEquipo.bdg + totalesEquipo.bdp) > 0
                      ? `${Math.round(totalesEquipo.bdg / (totalesEquipo.bdg + totalesEquipo.bdp) * 100)}%`
                      : "—"}</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* CRONOLOGÍA DE GOLES */}
          <div className="bg-zinc-900 rounded-xl p-5">
            <h3 className="text-base font-bold text-zinc-300 mb-4">⚽ Goles del partido</h3>
            {(() => {
              const goles = eventosOrdenados.filter((ev) => ev.tipo === "gol");
              if (goles.length === 0) {
                return <p className="text-sm text-zinc-500">Aún no hay goles registrados.</p>;
              }
              return (
                <ol className="space-y-2">
                  {goles.map((ev: any) => {
                    const esInter = ev.equipo === "INTER";
                    const accion = ev.accion || "";
                    const m = ev.marcador;
                    const marcadorPostGol = m && typeof m.inter === "number"
                      ? `${m.inter + (esInter ? 1 : 0)}-${m.rival + (esInter ? 0 : 1)}`
                      : "";
                    // Cuarteto en pista (4 jugadores con el goleador): solo si INTER y se grabó
                    const cuarteto: string[] = Array.isArray(ev.cuarteto) ? ev.cuarteto : [];
                    return (
                      <li key={ev.id}
                        className={`p-4 rounded-lg ${
                          esInter ? "bg-green-900/25 border border-green-700/30"
                                  : "bg-red-900/25 border border-red-700/30"
                        }`}>
                        <div className="flex items-baseline gap-2 mb-2">
                          <span className="text-zinc-400 text-xs font-mono w-16 shrink-0">
                            {ev.parte} {formatMMSS(ev.segundosParte || 0)}
                          </span>
                          <span className={`text-sm font-bold ${esInter ? "text-green-300" : "text-red-300"}`}>
                            {esInter ? "INTER" : cfg.rival}
                          </span>
                          {marcadorPostGol && (
                            <span className="text-sm text-zinc-300 tabular-nums">
                              ({marcadorPostGol})
                            </span>
                          )}
                          {accion && (
                            <span className="text-base font-semibold text-yellow-300 ml-auto">
                              {accion}
                            </span>
                          )}
                        </div>
                        {esInter && (
                          <div className="text-lg">
                            <strong className="text-white">⚽ {ev.goleador}</strong>
                            {ev.asistente && (
                              <span className="text-zinc-300"> · asist. <strong>{ev.asistente}</strong></span>
                            )}
                            {(ev.zonaCampo || ev.zonaPorteria) && (
                              <div className="text-sm text-zinc-400 mt-1">
                                {ev.zonaCampo && <span>desde {ev.zonaCampo}</span>}
                                {ev.zonaCampo && ev.zonaPorteria && " → "}
                                {ev.zonaPorteria && <span>a {ev.zonaPorteria}</span>}
                              </div>
                            )}
                          </div>
                        )}
                        {!esInter && (
                          <div className="text-lg text-zinc-300">
                            ⚽ Gol del rival
                            {ev.zonaPorteria && (
                              <span className="text-sm text-zinc-400"> · a {ev.zonaPorteria}</span>
                            )}
                          </div>
                        )}
                        {cuarteto.length > 0 && (
                          <div className="text-sm text-zinc-300 mt-2 pt-2 border-t border-white/10">
                            <span className="text-xs text-zinc-500 uppercase tracking-wide">En pista:</span>
                            {" "}
                            {cuarteto.join(", ")}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ol>
              );
            })()}
          </div>

          {/* Tanda (si hubo) */}
          {huboTanda && (
            <div className="bg-zinc-900 rounded-xl p-4">
              <h3 className="text-sm font-bold text-zinc-300 mb-2">🥇 Tanda de penaltis</h3>
              <div className="text-sm space-y-1">
                {tanda.tiros.map((t) => (
                  <div key={t.id} className="flex items-center gap-2">
                    <span className="text-zinc-500 w-6">#{t.orden}</span>
                    <span className={t.equipo === "INTER" ? "text-emerald-400" : "text-red-400"}>
                      {t.equipo === "INTER" ? "INTER" : cfg.rival}
                    </span>
                    <span className="font-bold flex-1">{t.tirador || "—"}</span>
                    <span className={t.resultado === "GOL" ? "text-green-400 font-bold" : "text-yellow-400"}>
                      {t.resultado}
                    </span>
                    {t.zonaPorteria && <span className="text-xs text-zinc-500">{t.zonaPorteria}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB: TIEMPOS */}
      {tab === "tiempos" && (
        <div className="bg-zinc-900 rounded-xl p-5 overflow-x-auto">
          <h3 className="text-base font-bold text-zinc-300 mb-2">⏱ Tiempo jugado por jugador</h3>
          <p className="text-sm text-zinc-500 mb-4">
            Color de fila según minutos jugados (rojo = más, verde = menos). Porteros sin
            código de color.
          </p>
          <table className="w-full text-base">
            <thead className="text-sm text-zinc-400 border-b border-zinc-800">
              <tr>
                <th className="text-left py-3 px-3">Jugador</th>
                <th className="text-right px-3">Total</th>
                {partesJugadas.map((p) => (
                  <th key={p} className="text-right px-3">{p}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filasTiempos.map((f) => {
                const colorFila = f.esPortero
                  ? "bg-zinc-800/30"
                  : colorSemaforoMin(f.total, maxMinJugados);
                return (
                  <tr key={f.nombre} className={`border-b border-zinc-900 ${colorFila}`}>
                    <td className="py-2.5 px-3">
                      <span className={`${f.esPortero ? "text-yellow-400" : ""} font-bold`}>
                        {f.nombre}
                      </span>
                      {f.enPista && <span className="ml-2 text-xs bg-green-700 px-2 py-0.5 rounded">EN PISTA</span>}
                      {f.esPortero && <span className="ml-2 text-xs text-zinc-500">🥅</span>}
                    </td>
                    <td className="text-right font-mono tabular-nums px-3 font-bold text-lg">
                      {formatMMSS(f.total)}
                    </td>
                    {partesJugadas.map((p) => (
                      <td key={p} className="text-right font-mono tabular-nums px-3 text-zinc-300">
                        {formatMMSS(f.porParte[p] ?? 0)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
            <tfoot className="text-sm text-zinc-500 border-t border-zinc-800">
              <tr>
                <td className="pt-3 px-3 italic">Total acumulado</td>
                <td className="text-right font-mono tabular-nums px-3 font-bold pt-3 text-base">
                  {formatMMSS(filasTiempos.reduce((s, f) => s + f.total, 0))}
                </td>
                {partesJugadas.map((p) => (
                  <td key={p} className="text-right font-mono tabular-nums px-3 pt-3">
                    {formatMMSS(filasTiempos.reduce((s, f) => s + (f.porParte[p] ?? 0), 0))}
                  </td>
                ))}
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* TAB: INDIVIDUAL — bloques de colores */}
      {tab === "individual" && (
        <div className="bg-zinc-900 rounded-xl p-4 overflow-x-auto">
          <h3 className="text-base font-bold text-zinc-300 mb-3">👤 Stats individuales por jugador</h3>
          <p className="text-sm text-zinc-500 mb-4">
            Disparos (azul) · Pérdidas (rojo) · Recuperaciones (verde) ·
            Balones divididos (morado) · Presencia en goles (dorado).
            Desliza horizontalmente si no entra todo en la pantalla.
          </p>
          <table className="text-sm min-w-[780px] w-full">
            <thead className="text-sm border-b border-zinc-700">
              <tr className="text-zinc-400">
                <th rowSpan={2} className="text-left py-2 px-2 align-bottom border-r border-zinc-800">Jug.</th>
                <th colSpan={5} className="text-center px-1 bg-emerald-900/30 text-emerald-300 text-sm font-bold">🎯 DISPAROS</th>
                <th colSpan={2} className="text-center px-1 bg-red-900/30 text-red-300 text-sm font-bold">❌ PÉRD.</th>
                <th colSpan={2} className="text-center px-1 bg-green-900/30 text-green-300 text-sm font-bold">✅ RECUP.</th>
                <th colSpan={2} className="text-center px-1 bg-purple-900/30 text-purple-300 text-sm font-bold">⚖️ DIV.</th>
                <th colSpan={4} className="text-center px-1 bg-yellow-900/30 text-yellow-300 text-sm font-bold">⚽ GOLES</th>
              </tr>
              <tr className="text-zinc-500 text-xs">
                <th className="text-center px-1 bg-emerald-900/10" title="Puerta">Puer.</th>
                <th className="text-center px-1 bg-emerald-900/10" title="Palo">Palo</th>
                <th className="text-center px-1 bg-emerald-900/10" title="Fuera">Fuera</th>
                <th className="text-center px-1 bg-emerald-900/10" title="Bloqueado">Bloq.</th>
                <th className="text-center px-1 bg-emerald-900/20 font-bold" title="Total disparos">Σ</th>
                <th className="text-center px-1 bg-red-900/10" title="Forzada">PF</th>
                <th className="text-center px-1 bg-red-900/10" title="No forzada">PNF</th>
                <th className="text-center px-1 bg-green-900/10">Robos</th>
                <th className="text-center px-1 bg-green-900/10">Cortes</th>
                <th className="text-center px-1 bg-purple-900/10" title="Ganados">BDG</th>
                <th className="text-center px-1 bg-purple-900/10" title="Perdidos">BDP</th>
                <th className="text-center px-1 bg-yellow-900/10" title="Goles marcados">G</th>
                <th className="text-center px-1 bg-yellow-900/10" title="Asistencias">A</th>
                <th className="text-center px-1 bg-yellow-900/10" title="Goles a favor con él en pista">+GF</th>
                <th className="text-center px-1 bg-yellow-900/10" title="Goles en contra con él en pista">-GC</th>
              </tr>
            </thead>
            <tbody>
              {filasIndiv.map(({ nombre, c, r, esPortero }) => {
                const sumDisp = (c?.dpp || 0) + (c?.dpa || 0) + (c?.dpf || 0) + (c?.dpb || 0);
                return (
                  <tr key={nombre} className="border-b border-zinc-800">
                    <td className={`py-2 px-2 border-r border-zinc-800 ${esPortero ? "text-yellow-400" : ""} font-bold text-base`}>
                      {nombre}{esPortero ? " 🥅" : ""}
                    </td>
                    {/* Disparos */}
                    <td className="text-center font-mono tabular-nums px-1 bg-emerald-900/10">{c?.dpp ?? 0}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-emerald-900/10">{c?.dpa ?? 0}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-emerald-900/10">{c?.dpf ?? 0}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-emerald-900/10">{c?.dpb ?? 0}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-emerald-900/20 font-bold text-emerald-200 text-base">{sumDisp}</td>
                    {/* Pérdidas */}
                    <td className="text-center font-mono tabular-nums px-1 bg-red-900/10">{c?.pf ?? 0}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-red-900/10">{c?.pnf ?? 0}</td>
                    {/* Recuperaciones */}
                    <td className="text-center font-mono tabular-nums px-1 bg-green-900/10">{c?.robos ?? 0}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-green-900/10">{c?.cortes ?? 0}</td>
                    {/* Divididos */}
                    <td className="text-center font-mono tabular-nums px-1 bg-purple-900/10">{c?.bdg ?? 0}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-purple-900/10">{c?.bdp ?? 0}</td>
                    {/* Goles + presencia */}
                    <td className="text-center font-mono tabular-nums px-1 bg-yellow-900/10 font-bold text-base">{r.goles}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-yellow-900/10">{r.asistencias}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-yellow-900/10 text-green-400">+{r.gf}</td>
                    <td className="text-center font-mono tabular-nums px-1 bg-yellow-900/10 text-red-400">-{r.gc}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-3 text-sm text-zinc-500">
            <strong>+GF / −GC</strong>: goles a favor y en contra mientras el jugador estaba EN PISTA
            (cuenta presencia en cada gol, no solo participación directa).
            Para porteros, GC = goles encajados estando él bajo palos.
          </div>
        </div>
      )}

      {/* TAB: CRONOGRAMA */}
      {tab === "cronograma" && (
        <Cronograma partido={partido} partesJugadas={partesJugadas} />
      )}

      {/* TAB: DISPAROS */}
      {tab === "disparos" && (
        <PestanaDisparos partido={partido} partesJugadas={partesJugadas} />
      )}

      {/* TAB: ANÁLISIS — datos derivados de los eventos del partido */}
      {tab === "analisis" && (
        <PestanaAnalisis partido={partido} partesJugadas={partesJugadas} />
      )}

      {/* FOOTER — acciones */}
      <div className="mt-6 grid grid-cols-3 gap-2">
        <button onClick={() => router.push("/partido")}
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
          ← Volver al partido
        </button>
        <button onClick={() => exportarJSON(partido)}
          className="py-3 bg-emerald-700 hover:bg-emerald-600 rounded-lg text-sm font-bold">
          📤 Exportar JSON
        </button>
        <Link href="/"
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm text-center">
          🏠 Inicio
        </Link>
      </div>
      <p className="text-[11px] text-zinc-600 mt-2 text-center">
        El JSON contiene todo el partido (config + eventos + tiempos + acciones + tanda).
        Útil para archivar, hacer merge entre iPads o importar a Google Sheets después.
      </p>
    </div>
  );
}

// ─── Cronograma del partido ─────────────────────────────────────────────
// Timeline horizontal: arriba eventos (goles grandes, faltas/tarjetas medianos,
// disparos pequeños). Debajo, una tira por jugador con barras de "en pista".

const NOMBRE_PARTE: Record<ParteId, string> = {
  "1T": "1ª parte", "2T": "2ª parte", PR1: "Prórroga 1", PR2: "Prórroga 2",
};

function Cronograma(props: { partido: Partido; partesJugadas: ParteId[] }) {
  const { partido, partesJugadas } = props;
  const cfg = partido.config!;

  // Filtro: "todo" muestra todas las partes juntas, o una sola parte.
  const [filtro, setFiltro] = useState<"todo" | ParteId>("todo");

  // duracionParte ya está EN SEGUNDOS (cfg.duracionParte[p] = 1200 para 20').
  // Calculamos offsets absolutos del partido COMPLETO (todas las partes jugadas).
  const duracionesAbs: Record<string, number> = {};
  const offsetsAbs: Record<string, number> = {};
  let totalAbs = 0;
  for (const p of partesJugadas) {
    offsetsAbs[p] = totalAbs;
    const d = cfg.duracionParte[p] ?? 0;
    duracionesAbs[p] = d;
    totalAbs += d;
  }
  if (totalAbs === 0) {
    return (
      <div className="bg-zinc-900 rounded-xl p-6 text-zinc-400 text-center">
        Aún no hay partes jugadas para mostrar.
      </div>
    );
  }

  // Ventana visible según el filtro.
  const winStart = filtro === "todo" ? 0 : offsetsAbs[filtro];
  const winEnd = filtro === "todo"
    ? totalAbs
    : offsetsAbs[filtro] + duracionesAbs[filtro];
  const winLen = winEnd - winStart;

  // Helper: segundo absoluto → % dentro de la ventana visible.
  const xPct = (xAbs: number) => ((xAbs - winStart) / winLen) * 100;
  // ¿Cae en la ventana?
  const enVentana = (xAbs: number) => xAbs >= winStart && xAbs <= winEnd;

  // Helper: pasar (parte, segParte) → x absoluto.
  const toAbs = (parte: ParteId, segParte: number): number =>
    (offsetsAbs[parte] ?? 0) + Math.min(segParte, duracionesAbs[parte] ?? 0);

  // ─── Reconstrucción de tramos por jugador ───
  // Recorremos eventos "cambio" para saber quién entró/salió en cada momento.
  type Tramo = { inicio: number; fin: number };
  const tramos: Record<string, Tramo[]> = {};
  const abierto: Record<string, number | null> = {};
  for (const j of cfg.convocados) {
    tramos[j] = [];
    abierto[j] = null;
  }
  // Plantilla inicial = 5 jugadores en pista desde t=0.
  const pi = cfg.pista_inicial || ({} as any);
  for (const j of [pi.portero, pi.pista1, pi.pista2, pi.pista3, pi.pista4]) {
    if (j && abierto[j] !== undefined) abierto[j] = 0;
  }
  const eventosOrden = [...partido.eventos].sort((a, b) => {
    const pa = partesJugadas.indexOf(a.parte);
    const pb = partesJugadas.indexOf(b.parte);
    if (pa !== pb) return pa - pb;
    return (a.segundosParte || 0) - (b.segundosParte || 0);
  });
  for (const ev of eventosOrden) {
    if (ev.tipo !== "cambio") continue;
    const t = toAbs(ev.parte, ev.segundosParte);
    const sale = (ev as any).sale as string;
    const entra = (ev as any).entra as string;
    if (sale && abierto[sale] != null) {
      tramos[sale].push({ inicio: abierto[sale]!, fin: t });
      abierto[sale] = null;
    }
    if (entra && abierto[entra] == null) {
      abierto[entra] = t;
    }
  }
  // Cerrar tramos abiertos al final del partido.
  for (const j of cfg.convocados) {
    if (abierto[j] != null) {
      tramos[j].push({ inicio: abierto[j]!, fin: totalAbs });
    }
  }

  // Orden de jugadores: porteros arriba, luego por minutos en pista descendente.
  const jugadoresOrden = [...cfg.convocados].sort((a, b) => {
    const ap = ROSTER.find((r) => r.nombre === a)?.posicion === "PORTERO";
    const bp = ROSTER.find((r) => r.nombre === b)?.posicion === "PORTERO";
    if (ap !== bp) return ap ? -1 : 1;
    const ta = tramos[a].reduce((s, t) => s + (t.fin - t.inicio), 0);
    const tb = tramos[b].reduce((s, t) => s + (t.fin - t.inicio), 0);
    return tb - ta;
  });

  // Eventos clasificados por importancia (afecta tamaño/altura del marcador).
  type Marca = { x: number; tipo: string; equipo: "INTER" | "RIVAL" | "—"; etiqueta: string; tooltip: string; clase: string; alturaPct: number };
  const marcas: Marca[] = [];
  for (const ev of eventosOrden) {
    const x = toAbs(ev.parte, ev.segundosParte);
    if (!enVentana(x)) continue;
    const eq = (ev as any).equipo as "INTER" | "RIVAL" | undefined;
    const colorEq = eq === "INTER" ? "bg-emerald-500" : eq === "RIVAL" ? "bg-red-500" : "bg-zinc-500";
    if (ev.tipo === "gol") {
      const jug = (ev as any).goleador || "—";
      marcas.push({
        x, tipo: "gol", equipo: eq || "—",
        etiqueta: "⚽",
        tooltip: `${formatMMSS(ev.segundosParte)} ${ev.parte} · GOL ${eq === "INTER" ? "Inter" : cfg.rival} (${jug})`,
        clase: `${colorEq} ring-2 ring-white/50`,
        alturaPct: 95,
      });
    } else if (ev.tipo === "amarilla" || ev.tipo === "roja") {
      const jug = (ev as any).jugador || "—";
      marcas.push({
        x, tipo: ev.tipo, equipo: eq || "—",
        etiqueta: ev.tipo === "amarilla" ? "🟨" : "🟥",
        tooltip: `${formatMMSS(ev.segundosParte)} ${ev.parte} · ${ev.tipo} ${eq === "INTER" ? jug : cfg.rival}`,
        clase: ev.tipo === "amarilla" ? "bg-yellow-500" : "bg-red-600",
        alturaPct: 70,
      });
    } else if (ev.tipo === "falta") {
      const jug = (ev as any).jugador || "—";
      marcas.push({
        x, tipo: "falta", equipo: eq || "—",
        etiqueta: "F",
        tooltip: `${formatMMSS(ev.segundosParte)} ${ev.parte} · Falta ${eq === "INTER" ? "Inter (" + jug + ")" : cfg.rival}`,
        clase: `${colorEq} opacity-80`,
        alturaPct: 55,
      });
    } else if (ev.tipo === "disparo" || ev.tipo === "penalti" || ev.tipo === "diezm") {
      const jug = (ev as any).jugador || (ev as any).tirador || "—";
      const res = (ev as any).resultado || "";
      marcas.push({
        x, tipo: "disparo", equipo: eq || "—",
        etiqueta: "•",
        tooltip: `${formatMMSS(ev.segundosParte)} ${ev.parte} · Disparo ${eq === "INTER" ? "Inter (" + jug + ")" : cfg.rival} → ${res}`,
        clase: `${colorEq} opacity-60`,
        alturaPct: 30,
      });
    }
  }

  // Render. Si filtro es una sola parte, no hace falta tanto ancho.
  const ANCHO_PX = filtro === "todo" ? 1400 : 900;

  // Partes que se solapan con la ventana visible (para etiquetas/divisores).
  const partesVisibles = partesJugadas.filter((p) => {
    const a = offsetsAbs[p];
    const b = a + duracionesAbs[p];
    return b > winStart && a < winEnd;
  });

  // Selector de filtro: solo ofrece partes con minutos > 0.
  const opcionesFiltro: Array<{ id: "todo" | ParteId; lbl: string }> = [
    { id: "todo", lbl: "Todo" },
    ...partesJugadas.map((p) => ({ id: p, lbl: NOMBRE_PARTE[p] })),
  ];

  return (
    <div className="bg-zinc-900 rounded-xl p-3">
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <h3 className="text-sm font-bold text-zinc-300">📅 Cronograma del partido</h3>
        <div className="flex gap-1 flex-wrap">
          {opcionesFiltro.map((o) => (
            <button key={o.id}
              onClick={() => setFiltro(o.id)}
              className={`px-3 py-1 rounded text-xs font-semibold ${
                filtro === o.id ? "bg-emerald-700" : "bg-zinc-800 hover:bg-zinc-700"
              }`}>{o.lbl}</button>
          ))}
        </div>
      </div>

      {/* Leyenda */}
      <div className="flex flex-wrap gap-3 text-[11px] mb-2 text-zinc-400">
        <span><span className="inline-block w-3 h-3 bg-emerald-500 rounded-sm align-middle mr-1"></span>Inter</span>
        <span><span className="inline-block w-3 h-3 bg-red-500 rounded-sm align-middle mr-1"></span>{cfg.rival}</span>
        <span><span className="inline-block w-3 h-3 bg-emerald-600/70 rounded-sm align-middle mr-1"></span>Tramo EN PISTA</span>
        <span className="text-zinc-600">· ⚽ goles · 🟨 tarjetas · F faltas · • disparos</span>
      </div>

      <div className="overflow-x-auto">
        <div style={{ minWidth: ANCHO_PX }} className="relative">
          {/* Cada fila comparte layout: w-28 (label izda) + flex-1 (lienzo) + w-14 (label dcha).
              Así las verticales del lienzo coinciden entre eventos / jugadores / eje. */}

          {/* ── Banda de partes (etiquetas) ── */}
          <div className="flex items-center gap-2 mb-1">
            <div className="w-28 shrink-0" />
            <div className="relative flex-1 h-5 text-[10px] text-zinc-500">
            {partesVisibles.map((p) => {
              const a = Math.max(offsetsAbs[p], winStart);
              const b = Math.min(offsetsAbs[p] + duracionesAbs[p], winEnd);
              const dura = duracionesAbs[p];
              return (
                <div key={p}
                  className="absolute top-0 h-full border-l border-zinc-700 pl-1"
                  style={{ left: `${xPct(a)}%`, width: `${xPct(b) - xPct(a)}%` }}>
                  {NOMBRE_PARTE[p]} ({formatMMSS(dura)})
                </div>
              );
            })}
            </div>
            <div className="w-14 shrink-0" />
          </div>

          {/* ── Carril de EVENTOS ── */}
          <div className="flex items-center gap-2">
            <div className="w-28 shrink-0 text-[10px] text-zinc-500 text-right pr-1">EVENTOS</div>
            <div className="relative flex-1 h-24 bg-zinc-950/60 border border-zinc-800 rounded">
            {/* divisores entre partes */}
            {partesVisibles.slice(1).map((p) => (
              <div key={p}
                className="absolute top-0 bottom-0 w-px bg-zinc-700/80"
                style={{ left: `${xPct(offsetsAbs[p])}%` }} />
            ))}
            {/* línea base */}
            <div className="absolute left-0 right-0 top-1/2 h-px bg-zinc-700/50" />
            {/* GUÍAS verticales para goles (cruzan hasta el carril de jugadores) */}
            {marcas.filter((m) => m.tipo === "gol").map((m, i) => (
              <div key={`g${i}`}
                className={`absolute top-0 bottom-0 w-px ${m.equipo === "INTER" ? "bg-emerald-500/40" : "bg-red-500/40"}`}
                style={{ left: `${xPct(m.x)}%` }} />
            ))}
            {/* marcas (asc por importancia para que las grandes queden arriba) */}
            {marcas.map((m, i) => {
              const top = m.tipo === "gol" ? "5%"
                        : (m.tipo === "amarilla" || m.tipo === "roja") ? "18%"
                        : m.tipo === "falta" ? "40%"
                        : "65%";
              const tamano = m.tipo === "gol" ? "w-6 h-6 text-sm"
                          : (m.tipo === "amarilla" || m.tipo === "roja") ? "w-5 h-5 text-xs"
                          : m.tipo === "falta" ? "w-4 h-4 text-[10px]"
                          : "w-2.5 h-2.5 text-[8px]";
              return (
                <div key={i}
                  title={m.tooltip}
                  className={`absolute -translate-x-1/2 rounded-full flex items-center justify-center font-bold text-white ${tamano} ${m.clase}`}
                  style={{ left: `${xPct(m.x)}%`, top }}>
                  {m.etiqueta}
                </div>
              );
            })}
            </div>
            <div className="w-14 shrink-0" />
          </div>

          {/* ── Carril de JUGADORES ── */}
          <div className="mt-3 space-y-0.5">
            {jugadoresOrden.map((j) => {
              const dorsal = ROSTER.find((r) => r.nombre === j)?.dorsal || "";
              const esPortero = ROSTER.find((r) => r.nombre === j)?.posicion === "PORTERO";
              const totalEnPista = tramos[j].reduce((s, t) => s + (t.fin - t.inicio), 0);
              return (
                <div key={j} className="flex items-center gap-2 text-[11px]">
                  <div className={`w-28 shrink-0 truncate ${esPortero ? "text-yellow-300" : "text-zinc-300"}`}>
                    {dorsal && <span className="text-zinc-500 mr-1">#{dorsal}</span>}
                    {j}{esPortero ? " 🥅" : ""}
                  </div>
                  <div className="relative flex-1 h-4 bg-zinc-950/40 border border-zinc-800 rounded">
                    {/* divisores partes (solo entre partes visibles) */}
                    {partesVisibles.slice(1).map((p) => (
                      <div key={p}
                        className="absolute top-0 bottom-0 w-px bg-zinc-700/60"
                        style={{ left: `${xPct(offsetsAbs[p])}%` }} />
                    ))}
                    {/* GUÍAS verticales de goles cruzando esta fila */}
                    {marcas.filter((m) => m.tipo === "gol").map((m, i) => (
                      <div key={`g${i}`}
                        className={`absolute top-0 bottom-0 w-px ${m.equipo === "INTER" ? "bg-emerald-500/40" : "bg-red-500/40"}`}
                        style={{ left: `${xPct(m.x)}%` }} />
                    ))}
                    {/* tramos en pista — clipados a la ventana visible */}
                    {tramos[j]
                      .map((t) => ({ ini: Math.max(t.inicio, winStart), fin: Math.min(t.fin, winEnd) }))
                      .filter((t) => t.fin > t.ini)
                      .map((t, i) => (
                        <div key={i}
                          title={`${formatMMSS(t.ini)} → ${formatMMSS(t.fin)} (${formatMMSS(t.fin - t.ini)})`}
                          className={`absolute top-0 bottom-0 ${esPortero ? "bg-yellow-600/70" : "bg-emerald-600/70"} rounded-sm`}
                          style={{ left: `${xPct(t.ini)}%`, width: `${xPct(t.fin) - xPct(t.ini)}%` }} />
                      ))}
                  </div>
                  <div className="w-14 shrink-0 text-right font-mono tabular-nums text-zinc-400">
                    {formatMMSS(totalEnPista)}
                  </div>
                </div>
              );
            })}
          </div>

          {/* eje minutos (mm:ss, cada 5' dentro de cada parte) */}
          <div className="flex items-center gap-2 mt-2">
            <div className="w-28 shrink-0" />
            <div className="relative flex-1 h-5 text-[9px] text-zinc-500">
            {partesVisibles.map((p) => {
              const inicioP = offsetsAbs[p];
              const marcasEje: number[] = [];
              for (let s = 0; s <= duracionesAbs[p]; s += 300) marcasEje.push(s);
              if (marcasEje[marcasEje.length - 1] !== duracionesAbs[p]) marcasEje.push(duracionesAbs[p]);
              return marcasEje.map((s) => {
                const xAbs = inicioP + s;
                if (xAbs < winStart || xAbs > winEnd) return null;
                return (
                  <div key={`${p}-${s}`}
                    className="absolute top-0 -translate-x-1/2 text-center"
                    style={{ left: `${xPct(xAbs)}%` }}>
                    <div className="w-px h-1 bg-zinc-600 mx-auto"></div>
                    <div className="font-mono tabular-nums">{formatMMSS(s)}</div>
                  </div>
                );
              });
            })}
            </div>
            <div className="w-14 shrink-0" />
          </div>
        </div>
      </div>

      <div className="mt-3 text-[11px] text-zinc-500">
        Pasa el dedo / cursor por encima de cada marca o tramo para ver el detalle.
        Los tramos verdes son minutos EN PISTA del jugador (amarillo si es portero).
      </div>
    </div>
  );
}

// ─── Pestaña Disparos (zona campo + zona portería × parte × equipo) ─────

// Tipos de resultado de disparo posibles.
type ResD = "GOL" | "PUERTA" | "PALO" | "FUERA" | "BLOQUEADO";

// Color por resultado (consistente en mapas y tablas).
const COLOR_RES: Record<ResD, string> = {
  GOL:       "bg-emerald-500 text-white",
  PUERTA:    "bg-orange-500 text-white",   // a puerta pero NO gol → parada del portero
  PALO:      "bg-yellow-500 text-zinc-900",
  BLOQUEADO: "bg-zinc-500 text-white",
  FUERA:     "bg-red-500/70 text-white",
};
const LABEL_RES: Record<ResD, string> = {
  GOL:       "Gol",
  PUERTA:    "Parada",
  PALO:      "Palo",
  BLOQUEADO: "Bloqueado",
  FUERA:     "Fuera",
};
// Orden estable de columnas.
const ORDEN_RES: ResD[] = ["GOL", "PUERTA", "PALO", "BLOQUEADO", "FUERA"];

// Zonas del campo (tal cual están en Campo.tsx — A1 a A11).
const ZONAS_CAMPO: string[] = ["A1","A2","A3","A4","A5","A6","A7","A8","A9","A10","A11"];
// Zonas portería 3x3 (de arriba a abajo, de izda a dcha — vista atacante).
const ZONAS_PORT: string[][] = [
  ["P1","P2","P3"],
  ["P4","P5","P6"],
  ["P7","P8","P9"],
];

function PestanaDisparos(props: { partido: Partido; partesJugadas: ParteId[] }) {
  const { partido, partesJugadas } = props;
  const cfg = partido.config!;

  const [equipo, setEquipo] = useState<"INTER" | "RIVAL">("INTER");
  const [filtroParte, setFiltroParte] = useState<"todo" | ParteId>("todo");

  const partesFiltro: ParteId[] = filtroParte === "todo" ? partesJugadas : [filtroParte];

  // ─── Recolecto disparos del partido (incluye disparos directos, penaltis y 10m
  //     porque también acaban a puerta/gol/etc.) ───
  type Tiro = { equipo: "INTER" | "RIVAL"; parte: ParteId; res: ResD; zonaCampo?: string; zonaPort?: string };
  const tiros: Tiro[] = [];

  for (const ev of partido.eventos) {
    if (!partesFiltro.includes(ev.parte)) continue;
    const eq = (ev as any).equipo as "INTER" | "RIVAL" | undefined;
    if (!eq) continue;

    if (ev.tipo === "disparo") {
      // El resultado puede ser PUERTA y haber un golId enlazado → eso es GOL.
      const r = (ev as any).resultado as ResultadoDisparoLocal;
      const golId = (ev as any).golId as string | undefined;
      const res: ResD = golId ? "GOL"
        : r === "PUERTA" ? "PUERTA"
        : r === "PALO" ? "PALO"
        : r === "BLOQUEADO" ? "BLOQUEADO"
        : "FUERA";
      tiros.push({
        equipo: eq, parte: ev.parte, res,
        zonaCampo: (ev as any).zonaCampo,
        zonaPort: (ev as any).zonaPorteria,
      });
    } else if (ev.tipo === "penalti" || ev.tipo === "diezm") {
      const r = (ev as any).resultado as "GOL" | "PARADA" | "POSTE" | "FUERA";
      const res: ResD = r === "GOL" ? "GOL"
        : r === "PARADA" ? "PUERTA"
        : r === "POSTE" ? "PALO"
        : "FUERA";
      tiros.push({
        equipo: eq, parte: ev.parte, res,
        zonaCampo: undefined,
        zonaPort: (ev as any).zonaPorteria,
      });
    }
  }

  const tirosEq = tiros.filter((t) => t.equipo === equipo);

  // Conteo total por resultado.
  const totalesRes: Record<ResD, number> = { GOL: 0, PUERTA: 0, PALO: 0, BLOQUEADO: 0, FUERA: 0 };
  for (const t of tirosEq) totalesRes[t.res]++;
  const totalTiros = tirosEq.length;

  // Conteo por zona campo × resultado.
  type ContZona = Record<ResD, number> & { total: number };
  const contCampo: Record<string, ContZona> = {};
  for (const z of ZONAS_CAMPO) {
    contCampo[z] = { GOL: 0, PUERTA: 0, PALO: 0, BLOQUEADO: 0, FUERA: 0, total: 0 };
  }
  for (const t of tirosEq) {
    if (!t.zonaCampo || !contCampo[t.zonaCampo]) continue;
    contCampo[t.zonaCampo][t.res]++;
    contCampo[t.zonaCampo].total++;
  }
  // Conteo por zona portería × resultado (solo eventos que apuntan a puerta tienen zonaPort).
  const contPort: Record<string, ContZona> = {};
  for (const fila of ZONAS_PORT) for (const z of fila) {
    contPort[z] = { GOL: 0, PUERTA: 0, PALO: 0, BLOQUEADO: 0, FUERA: 0, total: 0 };
  }
  for (const t of tirosEq) {
    if (!t.zonaPort || !contPort[t.zonaPort]) continue;
    contPort[t.zonaPort][t.res]++;
    contPort[t.zonaPort].total++;
  }
  const maxPort = Math.max(1, ...Object.values(contPort).map((c) => c.total));

  // Disparos sin zona campo (no se localizaron al apuntar).
  const sinZonaCampo = tirosEq.filter((t) => !t.zonaCampo).length;
  const sinZonaPort = tirosEq.filter((t) => !t.zonaPort).length;

  // Filas: una por parte, columnas = resultados.
  const conteoPorParte: Array<{ p: ParteId | "TOTAL"; counts: Record<ResD, number>; total: number }> = [];
  for (const p of partesJugadas) {
    const tt = tirosEq.filter((t) => t.parte === p);
    if (filtroParte !== "todo" && p !== filtroParte) continue;
    const counts: Record<ResD, number> = { GOL: 0, PUERTA: 0, PALO: 0, BLOQUEADO: 0, FUERA: 0 };
    for (const t of tt) counts[t.res]++;
    conteoPorParte.push({ p, counts, total: tt.length });
  }
  // Fila total.
  conteoPorParte.push({
    p: "TOTAL",
    counts: totalesRes,
    total: totalTiros,
  });

  // ─── Render ───
  return (
    <div className="space-y-4">
      {/* Selectores: equipo + parte */}
      <div className="bg-zinc-900 rounded-xl p-3 flex flex-wrap gap-3 items-center">
        <div className="flex gap-1">
          <button onClick={() => setEquipo("INTER")}
            className={`px-4 py-2 rounded text-sm font-bold ${equipo === "INTER" ? "bg-emerald-700" : "bg-zinc-800 hover:bg-zinc-700"}`}>
            Inter
          </button>
          <button onClick={() => setEquipo("RIVAL")}
            className={`px-4 py-2 rounded text-sm font-bold ${equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800 hover:bg-zinc-700"}`}>
            {cfg.rival}
          </button>
        </div>
        <div className="text-zinc-500 text-xs">·</div>
        <div className="flex gap-1 flex-wrap">
          <button onClick={() => setFiltroParte("todo")}
            className={`px-3 py-1.5 rounded text-xs font-semibold ${filtroParte === "todo" ? "bg-zinc-600" : "bg-zinc-800 hover:bg-zinc-700"}`}>Todo</button>
          {partesJugadas.map((p) => (
            <button key={p} onClick={() => setFiltroParte(p)}
              className={`px-3 py-1.5 rounded text-xs font-semibold ${filtroParte === p ? "bg-zinc-600" : "bg-zinc-800 hover:bg-zinc-700"}`}>
              {NOMBRE_PARTE[p]}
            </button>
          ))}
        </div>
        <div className="ml-auto text-xs text-zinc-400">
          <strong className="text-lg text-white tabular-nums">{totalTiros}</strong> disparos
        </div>
      </div>

      {/* Resumen por parte */}
      <div className="bg-zinc-900 rounded-xl p-3">
        <h3 className="text-sm font-bold text-zinc-300 mb-2">📊 Resumen por parte y resultado</h3>
        <table className="text-xs w-full">
          <thead className="border-b border-zinc-800 text-zinc-400">
            <tr>
              <th className="text-left py-1 px-2">Parte</th>
              {ORDEN_RES.map((r) => (
                <th key={r} className={`text-center px-2 py-1 ${COLOR_RES[r].replace("bg-", "text-").replace("text-zinc-900", "text-zinc-300")}`}>
                  {LABEL_RES[r]}
                </th>
              ))}
              <th className="text-right px-2 py-1">Total</th>
            </tr>
          </thead>
          <tbody>
            {conteoPorParte.map(({ p, counts, total }) => (
              <tr key={p} className={`border-b border-zinc-800 ${p === "TOTAL" ? "font-bold bg-zinc-800/40" : ""}`}>
                <td className="py-1.5 px-2">{p === "TOTAL" ? "TOTAL" : NOMBRE_PARTE[p as ParteId]}</td>
                {ORDEN_RES.map((r) => (
                  <td key={r} className="text-center font-mono tabular-nums px-2 py-1.5">
                    {counts[r] || ""}
                  </td>
                ))}
                <td className="text-right font-mono tabular-nums px-2 py-1.5 text-emerald-200">{total}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[10px] text-zinc-500 mt-2">
          <strong>Gol</strong> = a puerta y entró. <strong>Parada</strong> = a puerta pero
          la atajó el portero. <strong>Palo</strong> = al poste o travesaño.
          <strong> Bloqueado</strong> = lo cortó un defensor antes del marco.
          <strong> Fuera</strong> = ni a puerta ni bloqueado.
        </p>
      </div>

      {/* Mapa campo (SVG real) */}
      <div className="bg-zinc-900 rounded-xl p-3">
        <h3 className="text-sm font-bold text-zinc-300 mb-2">📍 Mapa del campo — desde dónde tira</h3>
        <p className="text-[11px] text-zinc-500 mb-2">
          Intensidad del verde = nº de disparos en esa zona. Cada zona muestra el total
          y desglose: <strong>G</strong>oles · <strong>Pa</strong>radas · <strong>Pl</strong>palo ·
          <strong> B</strong>loqueados · <strong>F</strong>uera. La dirección de ataque coincide con la
          configurada para la 1ª parte.
        </p>
        <div className="max-w-3xl mx-auto">
          <CampoConteos
            conteos={contCampo}
            direccion={direccionAtaque("1T", equipo, cfg)}
            nombreAtacante={equipo === "INTER" ? "Inter" : cfg.rival} />
        </div>
        {sinZonaCampo > 0 && (
          <p className="text-[10px] text-zinc-500 mt-2 italic text-center">
            {sinZonaCampo} disparos sin zona del campo apuntada (no se eligió zona al registrarlos).
          </p>
        )}
      </div>

      {/* Mapa portería 3x3 */}
      <div className="bg-zinc-900 rounded-xl p-3">
        <h3 className="text-sm font-bold text-zinc-300 mb-2">🥅 Zona de portería a la que tira</h3>
        <p className="text-[11px] text-zinc-500 mb-2">
          P1–P3 arriba (escuadras y centro alto), P4–P6 media, P7–P9 ras de suelo.
          Color = nº de disparos dirigidos ahí.
        </p>
        <div className="mx-auto max-w-md">
          <div className="aspect-[5/3] border-4 border-white/80 rounded-md p-1 bg-zinc-800/50">
            <div className="grid grid-cols-3 grid-rows-3 gap-1 h-full">
              {ZONAS_PORT.flat().map((z) => {
                const c = contPort[z];
                const pct = c.total / maxPort;
                const op = c.total === 0 ? 0.1 : 0.25 + 0.6 * pct;
                const tooltip = c.total === 0 ? "Sin disparos a esta zona"
                  : `${z}: ${c.total} · ${ORDEN_RES.filter((r) => c[r]).map((r) => `${LABEL_RES[r]}: ${c[r]}`).join(" · ")}`;
                // Color base: si hay GOL en esta zona, dominante verde; si no, naranja (paradas) o gris.
                const dominante: ResD | null = c.GOL > 0 ? "GOL" : c.PUERTA > 0 ? "PUERTA" : c.PALO > 0 ? "PALO" : c.BLOQUEADO > 0 ? "BLOQUEADO" : c.FUERA > 0 ? "FUERA" : null;
                const rgb = dominante === "GOL" ? "16,185,129"
                          : dominante === "PUERTA" ? "249,115,22"
                          : dominante === "PALO" ? "234,179,8"
                          : dominante === "BLOQUEADO" ? "113,113,122"
                          : dominante === "FUERA" ? "239,68,68"
                          : "100,116,139";
                return (
                  <div key={z}
                    title={tooltip}
                    className="rounded relative flex flex-col items-center justify-center border border-white/20 py-2"
                    style={{ background: `rgba(${rgb},${op})` }}>
                    <span className="text-4xl font-bold tabular-nums leading-none">{c.total || ""}</span>
                    {c.total > 0 && (
                      <div className="flex flex-wrap gap-1 justify-center mt-1.5">
                        {ORDEN_RES.map((r) => c[r] > 0 && (
                          <span key={r} className={`${COLOR_RES[r]} text-xs px-1.5 py-0.5 rounded font-bold`}>
                            {LABEL_RES[r].charAt(0)}{c[r]}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        {sinZonaPort > 0 && (
          <p className="text-[10px] text-zinc-500 mt-2 italic text-center">
            {sinZonaPort} disparos sin zona de portería apuntada
            {equipo === "RIVAL" ? " (normal en disparos del rival si no se registró el destino)" : ""}.
          </p>
        )}
      </div>
    </div>
  );
}

// Alias local para no chocar con el tipo de db.ts en el archivo.
type ResultadoDisparoLocal = "PUERTA" | "PALO" | "FUERA" | "BLOQUEADO";

// ─── Helper de exportación ──────────────────────────────────────────────

// ────────────────────────────────────────────────────────────────
// PESTAÑA ANÁLISIS — datos derivados de los eventos del partido
// ────────────────────────────────────────────────────────────────

function PestanaAnalisis(props: { partido: Partido; partesJugadas: ParteId[] }) {
  const { partido, partesJugadas } = props;
  const cfg = partido.config!;
  const evs = partido.eventos;

  // ── 1) Quintetos iniciales por parte ──────────────────────────
  // Para 1T: cfg.pista_inicial.
  // Para partes posteriores: reconstruir aplicando todos los cambios
  // de las partes anteriores al enPista inicial.
  const quintetoInicialParte = (parte: ParteId): string[] => {
    const inicial = [
      cfg.pista_inicial.portero,
      cfg.pista_inicial.pista1,
      cfg.pista_inicial.pista2,
      cfg.pista_inicial.pista3,
      cfg.pista_inicial.pista4,
    ];
    if (parte === "1T") return inicial;
    const PARTES: ParteId[] = ["1T", "2T", "PR1", "PR2"];
    const idxActual = PARTES.indexOf(parte);
    const partesPrevias = PARTES.slice(0, idxActual);
    const pista = [...inicial];
    // Aplicar cambios en orden cronológico de las partes previas
    const cambiosPrevios = evs
      .filter((e: any) => e.tipo === "cambio" && partesPrevias.includes(e.parte as ParteId))
      .sort((a: any, b: any) => (a.segundosPartido || 0) - (b.segundosPartido || 0));
    for (const c of cambiosPrevios as any[]) {
      const i = pista.indexOf(c.sale);
      if (i === -1) continue;
      if (c.entra === "") pista.splice(i, 1);
      else pista.splice(i, 1, c.entra);
    }
    return pista;
  };

  // ── 2) Asistencias por jugador (y pareja goleador-asistente más frecuente)
  const asistenciasPorJugador: Record<string, number> = {};
  const parejas: Record<string, number> = {};
  for (const e of evs as any[]) {
    if (e.tipo === "gol" && e.equipo === "INTER" && e.asistente) {
      asistenciasPorJugador[e.asistente] = (asistenciasPorJugador[e.asistente] || 0) + 1;
      const key = `${e.asistente}→${e.goleador}`;
      parejas[key] = (parejas[key] || 0) + 1;
    }
  }
  const topAsistentes = Object.entries(asistenciasPorJugador)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  const topParejas = Object.entries(parejas)
    .filter(([, n]) => n >= 1)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  // ── 3) Eficiencia ofensiva por jugador (sobre acciones.porJugador) ──
  type EficiencaRow = {
    nombre: string; disparos: number; puerta: number;
    goles: number; efectividad: number; punteria: number;
  };
  const efic: EficiencaRow[] = [];
  for (const nombre of cfg.convocados) {
    const c = partido.acciones?.porJugador?.[nombre];
    if (!c) continue;
    const disparos = (c.dpp || 0) + (c.dpa || 0) + (c.dpf || 0) + (c.dpb || 0);
    if (disparos === 0) continue;
    const puerta = c.dpp || 0;
    // Goles del jugador: contamos eventos gol con goleador = nombre
    const goles = evs.filter((e: any) =>
      e.tipo === "gol" && e.equipo === "INTER" && e.goleador === nombre
    ).length;
    efic.push({
      nombre,
      disparos,
      puerta,
      goles,
      efectividad: disparos > 0 ? (goles / disparos) * 100 : 0,
      punteria: disparos > 0 ? (puerta / disparos) * 100 : 0,
    });
  }
  efic.sort((a, b) => b.disparos - a.disparos);

  // ── 4) Cuartetos más letales (combinaciones de 4 sin portero) ──
  // Para cada gol INTER, miramos el cuarteto que estaba en pista
  // (excluyendo portero). Sumamos +1 a favor. Para goles RIVAL,
  // -1 al cuarteto que estaba en pista. Output: top 5 por +/- neto
  // con MÍNIMO 2 goles totales para que sea relevante.
  const cuartetos: Record<string, { gf: number; gc: number; jugadores: string[] }> = {};
  const idPortero = new Set(
    cfg.convocados.filter((n) => {
      const j = ROSTER.find((r) => r.nombre === n);
      return j?.posicion === "PORTERO";
    })
  );
  for (const e of evs as any[]) {
    if (e.tipo !== "gol") continue;
    const cuarteto: string[] = Array.isArray(e.cuarteto) ? e.cuarteto : [];
    if (cuarteto.length === 0) continue;
    // Excluir porteros del cuarteto
    const soloCampo = cuarteto.filter((n) => !idPortero.has(n));
    if (soloCampo.length !== 4) continue;
    const key = [...soloCampo].sort().join(" + ");
    if (!cuartetos[key]) {
      cuartetos[key] = { gf: 0, gc: 0, jugadores: [...soloCampo].sort() };
    }
    if (e.equipo === "INTER") cuartetos[key].gf++;
    else cuartetos[key].gc++;
  }
  const topCuartetos = Object.entries(cuartetos)
    .map(([k, v]) => ({ key: k, jugadores: v.jugadores, gf: v.gf, gc: v.gc, plus: v.gf - v.gc }))
    .filter((c) => c.gf + c.gc >= 1)
    .sort((a, b) => b.plus - a.plus)
    .slice(0, 5);

  // ── 5) Transiciones (recuperación → gol nuestro / pérdida → gol rival)
  // Ventana de 20 segundos.
  const evsOrdenados = [...evs].sort(
    (a: any, b: any) => (a.segundosPartido || 0) - (b.segundosPartido || 0)
  );
  let recuperaciones = 0, recupAGol = 0;
  let perdidas = 0, perdidasAGol = 0;
  for (let i = 0; i < evsOrdenados.length; i++) {
    const e = evsOrdenados[i] as any;
    if (e.tipo === "accion_individual") {
      const t = e.segundosPartido || 0;
      if (e.accion === "robos" || e.accion === "cortes") {
        recuperaciones++;
        // Buscar gol nuestro en los próximos 20s
        for (let j = i + 1; j < evsOrdenados.length; j++) {
          const e2 = evsOrdenados[j] as any;
          if ((e2.segundosPartido || 0) - t > 20) break;
          if (e2.tipo === "gol" && e2.equipo === "INTER") {
            recupAGol++;
            break;
          }
        }
      } else if (e.accion === "pf" || e.accion === "pnf") {
        perdidas++;
        for (let j = i + 1; j < evsOrdenados.length; j++) {
          const e2 = evsOrdenados[j] as any;
          if ((e2.segundosPartido || 0) - t > 20) break;
          if (e2.tipo === "gol" && e2.equipo === "RIVAL") {
            perdidasAGol++;
            break;
          }
        }
      }
    }
  }

  return (
    <div className="space-y-4">
      {/* 1) Quintetos iniciales */}
      <div className="bg-zinc-900 rounded-xl p-5">
        <h3 className="text-lg font-bold text-zinc-300 mb-3">🟢 Quintetos iniciales</h3>
        <p className="text-sm text-zinc-500 mb-3">
          Con qué 5 jugadores empezamos cada parte (incluido el portero).
        </p>
        <div className="grid grid-cols-1 gap-3">
          {partesJugadas.map((p) => {
            const q = quintetoInicialParte(p);
            return (
              <div key={p} className="bg-zinc-950 rounded-lg p-3">
                <div className="text-sm text-emerald-300 font-bold mb-2">{p}</div>
                <div className="flex flex-wrap gap-2">
                  {q.length === 0 ? (
                    <span className="text-zinc-500 text-sm italic">Sin datos</span>
                  ) : (
                    q.map((n, i) => (
                      <span key={`${n}-${i}`}
                        className={`px-2.5 py-1 rounded text-sm font-semibold ${
                          idPortero.has(n) ? "bg-yellow-700" : "bg-emerald-800"
                        }`}>
                        {n || "—"}
                      </span>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 2) Asistencias */}
      <div className="bg-zinc-900 rounded-xl p-5">
        <h3 className="text-lg font-bold text-zinc-300 mb-3">🎯 Asistencias</h3>
        {topAsistentes.length === 0 ? (
          <p className="text-sm text-zinc-500 italic">Sin asistencias registradas todavía.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 mb-3">
              {topAsistentes.map(([n, c]) => (
                <div key={n} className="flex justify-between bg-zinc-950 rounded px-3 py-2">
                  <span className="font-bold">{n}</span>
                  <span className="text-emerald-300 font-mono">{c}</span>
                </div>
              ))}
            </div>
            {topParejas.length > 0 && (
              <>
                <h4 className="text-sm font-bold text-zinc-400 mt-3 mb-2">Parejas asistente → goleador</h4>
                <ul className="space-y-1 text-sm">
                  {topParejas.map(([k, n]) => (
                    <li key={k} className="flex justify-between bg-zinc-950 rounded px-3 py-1">
                      <span>{k}</span><strong className="text-emerald-300">{n}</strong>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </div>

      {/* 3) Eficiencia ofensiva */}
      <div className="bg-zinc-900 rounded-xl p-5">
        <h3 className="text-lg font-bold text-zinc-300 mb-3">🎯 Eficiencia ofensiva</h3>
        {efic.length === 0 ? (
          <p className="text-sm text-zinc-500 italic">Sin disparos registrados todavía.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-xs text-zinc-500 border-b border-zinc-800">
              <tr>
                <th className="text-left py-2 px-2">Jugador</th>
                <th className="text-right px-2">Disparos</th>
                <th className="text-right px-2">A puerta</th>
                <th className="text-right px-2">Goles</th>
                <th className="text-right px-2" title="% goles / disparos">% gol</th>
                <th className="text-right px-2" title="% disparos a puerta / total">% puerta</th>
              </tr>
            </thead>
            <tbody>
              {efic.map((f) => (
                <tr key={f.nombre} className="border-b border-zinc-900">
                  <td className="py-1.5 px-2 font-bold">{f.nombre}</td>
                  <td className="text-right font-mono tabular-nums px-2">{f.disparos}</td>
                  <td className="text-right font-mono tabular-nums px-2">{f.puerta}</td>
                  <td className="text-right font-mono tabular-nums px-2 text-emerald-300 font-bold">{f.goles}</td>
                  <td className="text-right font-mono tabular-nums px-2">{f.efectividad.toFixed(0)}%</td>
                  <td className="text-right font-mono tabular-nums px-2">{f.punteria.toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 4) Cuartetos */}
      <div className="bg-zinc-900 rounded-xl p-5">
        <h3 className="text-lg font-bold text-zinc-300 mb-3">⚔️ Cuartetos por +/-</h3>
        {topCuartetos.length === 0 ? (
          <p className="text-sm text-zinc-500 italic">
            Sin goles asociados a cuartetos todavía. Se calculan a partir
            del cuarteto en pista cuando cae cada gol.
          </p>
        ) : (
          <div className="space-y-2">
            {topCuartetos.map((c) => (
              <div key={c.key}
                className={`rounded-lg p-3 ${
                  c.plus > 0 ? "bg-emerald-900/30 border border-emerald-700/30"
                  : c.plus < 0 ? "bg-red-900/30 border border-red-700/30"
                  : "bg-zinc-800"
                }`}>
                <div className="flex items-center justify-between">
                  <span className="text-sm">{c.jugadores.join(" · ")}</span>
                  <span className={`font-mono font-bold ${
                    c.plus > 0 ? "text-emerald-300" : c.plus < 0 ? "text-red-300" : ""
                  }`}>
                    +{c.gf} −{c.gc} = {c.plus > 0 ? "+" : ""}{c.plus}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 5) Transiciones */}
      <div className="bg-zinc-900 rounded-xl p-5">
        <h3 className="text-lg font-bold text-zinc-300 mb-3">⚡ Transiciones (ventana 20s)</h3>
        <p className="text-xs text-zinc-500 mb-3">
          % recuperaciones que acaban en gol nuestro (transición ofensiva
          efectiva) · % pérdidas que acaban en gol del rival (vulnerabilidad
          post-pérdida). Ambas miradas dentro de los siguientes 20 segundos.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-green-900/30 rounded-lg p-4">
            <div className="text-sm text-green-300 mb-1">↗️ Recuperación → Gol</div>
            <div className="text-3xl font-bold tabular-nums">
              {recuperaciones === 0 ? "—" : `${Math.round((recupAGol / recuperaciones) * 100)}%`}
            </div>
            <div className="text-xs text-zinc-400 mt-1">
              {recupAGol} / {recuperaciones} recuperaciones
            </div>
          </div>
          <div className="bg-red-900/30 rounded-lg p-4">
            <div className="text-sm text-red-300 mb-1">↘️ Pérdida → Gol rival</div>
            <div className="text-3xl font-bold tabular-nums">
              {perdidas === 0 ? "—" : `${Math.round((perdidasAGol / perdidas) * 100)}%`}
            </div>
            <div className="text-xs text-zinc-400 mt-1">
              {perdidasAGol} / {perdidas} pérdidas
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}


function exportarJSON(partido: any) {
  try {
    const blob = new Blob([JSON.stringify(partido, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const pid = partido.config?.partido_id || "partido";
    const fecha = partido.config?.fecha || new Date().toISOString().slice(0, 10);
    a.href = url;
    a.download = `${fecha}_${pid}_crono.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("No he podido exportar el JSON: " + e);
  }
}

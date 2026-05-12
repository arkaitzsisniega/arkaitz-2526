"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { usePartido } from "@/lib/store";
import { ROSTER } from "@/lib/roster";
import { formatMMSS } from "@/lib/utils";
import type { Evento, ParteId, Partido } from "@/lib/db";

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
  const [tab, setTab] = useState<"general" | "tiempos" | "eventos" | "individual">("general");

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
            <span className="text-blue-400">INTER</span>
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
          { id: "eventos",    lbl: "📜 Eventos" },
          { id: "individual", lbl: "👤 Individual" },
        ].map((t) => (
          <button key={t.id}
            onClick={() => setTab(t.id as any)}
            className={`px-4 py-2 rounded-lg text-sm font-semibold whitespace-nowrap ${
              tab === t.id ? "bg-blue-700" : "bg-zinc-800 hover:bg-zinc-700"
            }`}>{t.lbl}</button>
        ))}
      </div>

      {/* TAB: GENERAL */}
      {tab === "general" && (
        <div className="space-y-4">
          {/* BLOQUE PRINCIPAL — Disparos, pérdidas, robos/cortes, divididos del equipo */}
          <div className="bg-zinc-900 rounded-xl p-4">
            <h3 className="text-sm font-bold text-zinc-300 mb-3">📊 Stats del equipo (totales)</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {/* Disparos */}
              <div className="bg-blue-900/30 rounded-lg p-3">
                <div className="text-xs text-blue-300 font-bold mb-2">🎯 Disparos</div>
                <div className="text-xs space-y-0.5">
                  <div className="flex justify-between"><span>Puerta</span><strong>{totalesEquipo.dpp}</strong></div>
                  <div className="flex justify-between"><span>Palo</span><strong>{totalesEquipo.dpa}</strong></div>
                  <div className="flex justify-between"><span>Fuera</span><strong>{totalesEquipo.dpf}</strong></div>
                  <div className="flex justify-between"><span>Bloqueados</span><strong>{totalesEquipo.dpb}</strong></div>
                  <div className="border-t border-blue-700/50 mt-1 pt-1 flex justify-between text-blue-200">
                    <span>Total</span><strong>{totalesEquipo.dpp+totalesEquipo.dpa+totalesEquipo.dpf+totalesEquipo.dpb}</strong>
                  </div>
                </div>
              </div>
              {/* Pérdidas */}
              <div className="bg-red-900/30 rounded-lg p-3">
                <div className="text-xs text-red-300 font-bold mb-2">❌ Pérdidas</div>
                <div className="text-xs space-y-0.5">
                  <div className="flex justify-between"><span>Forzadas (PF)</span><strong>{totalesEquipo.pf}</strong></div>
                  <div className="flex justify-between"><span>No forzadas (PNF)</span><strong>{totalesEquipo.pnf}</strong></div>
                  <div className="border-t border-red-700/50 mt-1 pt-1 flex justify-between text-red-200">
                    <span>Total</span><strong>{totalesEquipo.pf+totalesEquipo.pnf}</strong>
                  </div>
                </div>
              </div>
              {/* Recuperaciones */}
              <div className="bg-green-900/30 rounded-lg p-3">
                <div className="text-xs text-green-300 font-bold mb-2">✅ Recuperaciones</div>
                <div className="text-xs space-y-0.5">
                  <div className="flex justify-between"><span>Robos</span><strong>{totalesEquipo.robos}</strong></div>
                  <div className="flex justify-between"><span>Cortes</span><strong>{totalesEquipo.cortes}</strong></div>
                  <div className="border-t border-green-700/50 mt-1 pt-1 flex justify-between text-green-200">
                    <span>Total</span><strong>{totalesEquipo.robos+totalesEquipo.cortes}</strong>
                  </div>
                </div>
              </div>
              {/* Balones divididos */}
              <div className="bg-purple-900/30 rounded-lg p-3">
                <div className="text-xs text-purple-300 font-bold mb-2">⚖️ Bal. divididos</div>
                <div className="text-xs space-y-0.5">
                  <div className="flex justify-between"><span>Ganados (BDG)</span><strong>{totalesEquipo.bdg}</strong></div>
                  <div className="flex justify-between"><span>Perdidos (BDP)</span><strong>{totalesEquipo.bdp}</strong></div>
                  <div className="border-t border-purple-700/50 mt-1 pt-1 flex justify-between text-purple-200">
                    <span>Ratio</span>
                    <strong>{(totalesEquipo.bdg + totalesEquipo.bdp) > 0
                      ? `${Math.round(totalesEquipo.bdg / (totalesEquipo.bdg + totalesEquipo.bdp) * 100)}%`
                      : "—"}</strong>
                  </div>
                </div>
              </div>
            </div>

            {/* Comparativa Inter vs Rival en disparos (porque sí guardamos disparos rivales) */}
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="bg-zinc-800/60 rounded-lg p-2 text-xs">
                <div className="text-blue-400 font-bold mb-1">INTER (resumen disparos)</div>
                <div>Total: <strong>{totalesEquipo.dpp+totalesEquipo.dpa+totalesEquipo.dpf+totalesEquipo.dpb}</strong> · A puerta: <strong>{totalesEquipo.dpp}</strong></div>
              </div>
              <div className="bg-zinc-800/60 rounded-lg p-2 text-xs">
                <div className="text-red-400 font-bold mb-1">{cfg.rival} (resumen disparos)</div>
                <div>Total: <strong>{partido.disparosRival.puerta+partido.disparosRival.palo+partido.disparosRival.fuera+partido.disparosRival.bloqueado}</strong> · A puerta: <strong>{partido.disparosRival.puerta}</strong></div>
              </div>
            </div>
          </div>

          {/* Tanda (si hubo) */}
          {huboTanda && (
            <div className="bg-zinc-900 rounded-xl p-4">
              <h3 className="text-sm font-bold text-zinc-300 mb-2">🥇 Tanda de penaltis</h3>
              <div className="text-sm space-y-1">
                {tanda.tiros.map((t) => (
                  <div key={t.id} className="flex items-center gap-2">
                    <span className="text-zinc-500 w-6">#{t.orden}</span>
                    <span className={t.equipo === "INTER" ? "text-blue-400" : "text-red-400"}>
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

          {/* SECUNDARIO — Faltas, amarillas, tiempos muertos (más pequeño) */}
          <div className="bg-zinc-900/60 rounded-xl p-3">
            <h3 className="text-xs font-semibold text-zinc-400 mb-2">Disciplina (faltas / amarillas / tiempos muertos)</h3>
            <table className="w-full text-xs">
              <thead className="text-[10px] text-zinc-500 border-b border-zinc-800">
                <tr>
                  <th className="text-left py-1">Métrica</th>
                  {partesJugadas.map((p) => (
                    <th key={p} className="text-center px-1" colSpan={2}>{p}</th>
                  ))}
                  <th className="text-center px-1" colSpan={2}>TOTAL</th>
                </tr>
                <tr className="text-[9px]">
                  <th></th>
                  {partesJugadas.flatMap((p) => [
                    <th key={`${p}-i`} className="text-blue-400 px-1">I</th>,
                    <th key={`${p}-r`} className="text-red-400 px-1">R</th>,
                  ])}
                  <th className="text-blue-400 px-1">I</th>
                  <th className="text-red-400 px-1">R</th>
                </tr>
              </thead>
              <tbody>
                {([
                  ["Faltas",     "faltas"],
                  ["Amarillas",  "amarillas"],
                  ["T. muertos", "tiemposMuerto"],
                ] as const).map(([label, k]) => {
                  const totI = partesJugadas.reduce((s, p) => s + stats[k][p].inter, 0);
                  const totR = partesJugadas.reduce((s, p) => s + stats[k][p].rival, 0);
                  return (
                    <tr key={k} className="border-b border-zinc-900">
                      <td className="py-1">{label}</td>
                      {partesJugadas.flatMap((p) => [
                        <td key={`${k}-${p}-i`} className="text-center px-1 font-mono">{stats[k][p].inter}</td>,
                        <td key={`${k}-${p}-r`} className="text-center px-1 font-mono">{stats[k][p].rival}</td>,
                      ])}
                      <td className="text-center px-1 font-mono font-bold">{totI}</td>
                      <td className="text-center px-1 font-mono font-bold">{totR}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB: TIEMPOS */}
      {tab === "tiempos" && (
        <div className="bg-zinc-900 rounded-xl p-4 overflow-x-auto">
          <h3 className="text-sm font-bold text-zinc-300 mb-1">⏱ Tiempo jugado por jugador</h3>
          <p className="text-[11px] text-zinc-500 mb-3">
            Color de fila según minutos jugados (rojo = más, verde = menos). Porteros sin
            código de color.
          </p>
          <table className="w-full text-sm">
            <thead className="text-xs text-zinc-400 border-b border-zinc-800">
              <tr>
                <th className="text-left py-2 px-2">Jugador</th>
                <th className="text-right px-2">Total</th>
                {partesJugadas.map((p) => (
                  <th key={p} className="text-right px-2">{p}</th>
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
                    <td className="py-1.5 px-2">
                      <span className={`${f.esPortero ? "text-yellow-400" : ""} font-bold`}>
                        {f.nombre}
                      </span>
                      {f.enPista && <span className="ml-2 text-[10px] bg-green-700 px-1.5 py-0.5 rounded">EN PISTA</span>}
                      {f.esPortero && <span className="ml-2 text-[10px] text-zinc-500">🥅</span>}
                    </td>
                    <td className="text-right font-mono tabular-nums px-2 font-bold">
                      {formatMMSS(f.total)}
                    </td>
                    {partesJugadas.map((p) => (
                      <td key={p} className="text-right font-mono tabular-nums px-2 text-zinc-300">
                        {formatMMSS(f.porParte[p] ?? 0)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
            <tfoot className="text-xs text-zinc-500 border-t border-zinc-800">
              <tr>
                <td className="pt-2 px-2 italic">Total acumulado</td>
                <td className="text-right font-mono tabular-nums px-2 font-bold pt-2">
                  {formatMMSS(filasTiempos.reduce((s, f) => s + f.total, 0))}
                </td>
                {partesJugadas.map((p) => (
                  <td key={p} className="text-right font-mono tabular-nums px-2 pt-2">
                    {formatMMSS(filasTiempos.reduce((s, f) => s + (f.porParte[p] ?? 0), 0))}
                  </td>
                ))}
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* TAB: EVENTOS */}
      {tab === "eventos" && (
        <div className="bg-zinc-900 rounded-xl p-4">
          <h3 className="text-sm font-bold text-zinc-300 mb-3">
            📜 Cronología ({eventosOrdenados.length} eventos)
          </h3>
          {eventosOrdenados.length === 0 ? (
            <p className="text-sm text-zinc-500">No hay eventos registrados todavía.</p>
          ) : (
            <ul className="space-y-1.5 max-h-[60vh] overflow-y-auto pr-1">
              {eventosOrdenados.map((ev) => {
                // Manejo defensivo: eventos antiguos pueden no tener marcador.
                const m = (ev as any).marcador;
                const marcadorTxt = m && typeof m.inter === "number"
                  ? `${m.inter}-${m.rival}`
                  : "";
                return (
                  <li key={ev.id} className="flex items-start gap-2 text-sm border-b border-zinc-900 pb-1.5">
                    <span className="text-zinc-500 text-xs font-mono w-20 shrink-0">
                      {ev.parte} {formatMMSS(ev.segundosParte || 0)}
                    </span>
                    <span className="text-base shrink-0">{emojiEvento(ev)}</span>
                    <span className="flex-1 break-words">{descripcionEvento(ev, cfg.rival)}</span>
                    {marcadorTxt && (
                      <span className="text-[10px] text-zinc-600 tabular-nums shrink-0">
                        {marcadorTxt}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {/* TAB: INDIVIDUAL — bloques de colores */}
      {tab === "individual" && (
        <div className="bg-zinc-900 rounded-xl p-3 overflow-x-auto">
          <h3 className="text-sm font-bold text-zinc-300 mb-3">👤 Stats individuales por jugador</h3>
          <p className="text-[11px] text-zinc-500 mb-3">
            Disparos (azul) · Pérdidas (rojo) · Recuperaciones (verde) ·
            Balones divididos (morado) · Presencia en goles (dorado).
            Desliza horizontalmente si no entra todo en la pantalla.
          </p>
          <table className="text-xs min-w-[900px]">
            <thead className="text-[10px] border-b border-zinc-700">
              <tr className="text-zinc-400">
                <th rowSpan={2} className="text-left py-2 px-2 align-bottom border-r border-zinc-800">Jugador</th>
                <th colSpan={5} className="text-center px-1 bg-blue-900/30 text-blue-300">🎯 DISPAROS</th>
                <th colSpan={2} className="text-center px-1 bg-red-900/30 text-red-300">❌ PÉRDIDAS</th>
                <th colSpan={2} className="text-center px-1 bg-green-900/30 text-green-300">✅ RECUP.</th>
                <th colSpan={2} className="text-center px-1 bg-purple-900/30 text-purple-300">⚖️ DIVIDIDOS</th>
                <th colSpan={4} className="text-center px-1 bg-yellow-900/30 text-yellow-300">⚽ GOLES</th>
              </tr>
              <tr className="text-zinc-500 text-[10px]">
                <th className="text-right px-1 bg-blue-900/10" title="Puerta">Puer.</th>
                <th className="text-right px-1 bg-blue-900/10" title="Palo">Palo</th>
                <th className="text-right px-1 bg-blue-900/10" title="Fuera">Fuera</th>
                <th className="text-right px-1 bg-blue-900/10" title="Bloqueado">Bloq.</th>
                <th className="text-right px-1 bg-blue-900/20 font-bold" title="Total disparos">Σ</th>
                <th className="text-right px-1 bg-red-900/10" title="Forzada">PF</th>
                <th className="text-right px-1 bg-red-900/10" title="No forzada">PNF</th>
                <th className="text-right px-1 bg-green-900/10">Robos</th>
                <th className="text-right px-1 bg-green-900/10">Cortes</th>
                <th className="text-right px-1 bg-purple-900/10" title="Ganados">BDG</th>
                <th className="text-right px-1 bg-purple-900/10" title="Perdidos">BDP</th>
                <th className="text-right px-1 bg-yellow-900/10" title="Goles marcados">G</th>
                <th className="text-right px-1 bg-yellow-900/10" title="Asistencias">A</th>
                <th className="text-right px-1 bg-yellow-900/10" title="Goles a favor con él en pista">+GF</th>
                <th className="text-right px-1 bg-yellow-900/10" title="Goles en contra con él en pista">-GC</th>
              </tr>
            </thead>
            <tbody>
              {filasIndiv.map(({ nombre, c, r, esPortero }) => {
                const sumDisp = (c?.dpp || 0) + (c?.dpa || 0) + (c?.dpf || 0) + (c?.dpb || 0);
                const plusMinus = r.gf - r.gc;
                return (
                  <tr key={nombre} className="border-b border-zinc-800">
                    <td className={`py-1.5 px-2 border-r border-zinc-800 ${esPortero ? "text-yellow-400" : ""} font-bold`}>
                      {nombre}{esPortero ? " 🥅" : ""}
                    </td>
                    {/* Disparos */}
                    <td className="text-right font-mono tabular-nums px-1 bg-blue-900/10">{c?.dpp ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-blue-900/10">{c?.dpa ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-blue-900/10">{c?.dpf ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-blue-900/10">{c?.dpb ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-blue-900/20 font-bold text-blue-200">{sumDisp}</td>
                    {/* Pérdidas */}
                    <td className="text-right font-mono tabular-nums px-1 bg-red-900/10">{c?.pf ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-red-900/10">{c?.pnf ?? 0}</td>
                    {/* Recuperaciones */}
                    <td className="text-right font-mono tabular-nums px-1 bg-green-900/10">{c?.robos ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-green-900/10">{c?.cortes ?? 0}</td>
                    {/* Divididos */}
                    <td className="text-right font-mono tabular-nums px-1 bg-purple-900/10">{c?.bdg ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-purple-900/10">{c?.bdp ?? 0}</td>
                    {/* Goles + presencia */}
                    <td className="text-right font-mono tabular-nums px-1 bg-yellow-900/10 font-bold">{r.goles}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-yellow-900/10">{r.asistencias}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-yellow-900/10 text-green-400">+{r.gf}</td>
                    <td className="text-right font-mono tabular-nums px-1 bg-yellow-900/10 text-red-400">-{r.gc}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-3 text-[11px] text-zinc-500">
            <strong>+GF / −GC</strong>: goles a favor y en contra mientras el jugador estaba EN PISTA
            (cuenta presencia en cada gol, no solo participación directa).
            Para porteros, GC = goles encajados estando él bajo palos.
          </div>
        </div>
      )}

      {/* FOOTER — acciones */}
      <div className="mt-6 grid grid-cols-3 gap-2">
        <button onClick={() => router.push("/partido")}
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
          ← Volver al partido
        </button>
        <button onClick={() => exportarJSON(partido)}
          className="py-3 bg-blue-700 hover:bg-blue-600 rounded-lg text-sm font-bold">
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

// ─── Helper de exportación ──────────────────────────────────────────────

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

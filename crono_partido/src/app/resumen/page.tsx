"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useMemo, useState } from "react";
import { usePartido } from "@/lib/store";
import { ROSTER } from "@/lib/roster";
import { formatMMSS } from "@/lib/utils";
import type { Evento, ParteId, TiroTanda } from "@/lib/db";

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
  switch (ev.tipo) {
    case "gol": {
      const quien = ev.equipo === "INTER" ? ev.goleador : rival;
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
}

// ─── Página resumen ─────────────────────────────────────────────────────

export default function ResumenPage() {
  const router = useRouter();
  const {
    partido, cargado, segundosEnParte, segundosTurnoActual,
  } = usePartido();
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
    return a.segundosParte - b.segundosParte;
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

  // Acciones individuales agregadas
  const accionesIndividuales = cfg.convocados.map((nombre) => {
    const c = partido.acciones.porJugador[nombre] ?? null;
    return {
      nombre,
      c,
      esPortero: ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO",
    };
  }).filter((r) => r.c && (
    // Mostrar solo jugadores con al menos una acción registrada
    (r.c.pf || 0) + (r.c.pnf || 0) + (r.c.robos || 0) + (r.c.cortes || 0) +
    (r.c.bdg || 0) + (r.c.bdp || 0) + (r.c.dpp || 0) + (r.c.dpf || 0) +
    (r.c.dpa || 0) + (r.c.dpb || 0) + (r.c.golesEncajados || 0) > 0
  ));

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

      {/* TAB: GENERAL — stats agregadas */}
      {tab === "general" && (
        <div className="space-y-4">
          {/* Stats por parte */}
          <div className="bg-zinc-900 rounded-xl p-4">
            <h3 className="text-sm font-bold text-zinc-300 mb-3">Stats por parte</h3>
            <table className="w-full text-sm">
              <thead className="text-xs text-zinc-500 border-b border-zinc-800">
                <tr>
                  <th className="text-left py-2">Métrica</th>
                  {partesJugadas.map((p) => (
                    <th key={p} className="text-center px-2" colSpan={2}>{p}</th>
                  ))}
                  <th className="text-center px-2" colSpan={2}>TOTAL</th>
                </tr>
                <tr className="text-[10px]">
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
                      <td className="py-1.5">{label}</td>
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

          {/* Disparos */}
          <div className="bg-zinc-900 rounded-xl p-4">
            <h3 className="text-sm font-bold text-zinc-300 mb-3">Disparos</h3>
            <div className="grid grid-cols-2 gap-4">
              {/* INTER agregado de contadores por jugador */}
              {(() => {
                const i = cfg.convocados.reduce((acc, n) => {
                  const c = partido.acciones.porJugador[n];
                  if (!c) return acc;
                  return {
                    p: acc.p + (c.dpp || 0),
                    f: acc.f + (c.dpf || 0),
                    a: acc.a + (c.dpa || 0),
                    b: acc.b + (c.dpb || 0),
                  };
                }, { p: 0, f: 0, a: 0, b: 0 });
                const r = partido.disparosRival;
                return (
                  <>
                    <div>
                      <div className="text-xs text-blue-400 font-bold mb-1">INTER</div>
                      <div className="text-xs text-zinc-300">
                        <div>Puerta: <strong>{i.p}</strong></div>
                        <div>Palo: <strong>{i.a}</strong></div>
                        <div>Fuera: <strong>{i.f}</strong></div>
                        <div>Bloqueados: <strong>{i.b}</strong></div>
                        <div className="border-t border-zinc-800 mt-1 pt-1">
                          Total: <strong>{i.p + i.a + i.f + i.b}</strong>
                        </div>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-red-400 font-bold mb-1">{cfg.rival}</div>
                      <div className="text-xs text-zinc-300">
                        <div>Puerta: <strong>{r.puerta}</strong></div>
                        <div>Palo: <strong>{r.palo}</strong></div>
                        <div>Fuera: <strong>{r.fuera}</strong></div>
                        <div>Bloqueados: <strong>{r.bloqueado}</strong></div>
                        <div className="border-t border-zinc-800 mt-1 pt-1">
                          Total: <strong>{r.puerta + r.palo + r.fuera + r.bloqueado}</strong>
                        </div>
                      </div>
                    </div>
                  </>
                );
              })()}
            </div>
          </div>

          {/* Tanda */}
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
        </div>
      )}

      {/* TAB: TIEMPOS */}
      {tab === "tiempos" && (
        <div className="bg-zinc-900 rounded-xl p-4 overflow-x-auto">
          <h3 className="text-sm font-bold text-zinc-300 mb-3">⏱ Tiempo jugado por jugador</h3>
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
              {filasTiempos.map((f) => (
                <tr key={f.nombre} className="border-b border-zinc-900">
                  <td className="py-1.5 px-2">
                    <span className={`${f.esPortero ? "text-yellow-400" : ""} font-bold`}>
                      {f.nombre}
                    </span>
                    {f.enPista && <span className="ml-2 text-[10px] bg-green-700 px-1.5 py-0.5 rounded">EN PISTA</span>}
                  </td>
                  <td className="text-right font-mono tabular-nums px-2 font-bold">
                    {formatMMSS(f.total)}
                  </td>
                  {partesJugadas.map((p) => (
                    <td key={p} className="text-right font-mono tabular-nums px-2 text-zinc-400">
                      {formatMMSS(f.porParte[p] ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
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
          <p className="text-xs text-zinc-500 mt-3">
            Si el partido sigue en curso, el jugador EN PISTA incluye los segundos
            en vivo de la parte actual.
          </p>
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
            <ul className="space-y-1.5">
              {eventosOrdenados.map((ev) => (
                <li key={ev.id} className="flex items-start gap-2 text-sm border-b border-zinc-900 pb-1.5">
                  <span className="text-zinc-500 text-xs font-mono w-20 shrink-0">
                    {ev.parte} {formatMMSS(ev.segundosParte)}
                  </span>
                  <span className="text-base shrink-0">{emojiEvento(ev)}</span>
                  <span className="flex-1">{descripcionEvento(ev, cfg.rival)}</span>
                  <span className="text-[10px] text-zinc-600 tabular-nums">
                    {ev.marcador.inter}-{ev.marcador.rival}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* TAB: INDIVIDUAL */}
      {tab === "individual" && (
        <div className="bg-zinc-900 rounded-xl p-4 overflow-x-auto">
          <h3 className="text-sm font-bold text-zinc-300 mb-3">👤 Acciones individuales</h3>
          {accionesIndividuales.length === 0 ? (
            <p className="text-sm text-zinc-500">Aún no se han registrado acciones individuales.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-[10px] text-zinc-400 border-b border-zinc-800">
                <tr>
                  <th className="text-left py-2 px-1">Jugador</th>
                  <th className="text-right px-1" title="Disparos a puerta">D.Puerta</th>
                  <th className="text-right px-1" title="Disparos a palo">Palo</th>
                  <th className="text-right px-1" title="Disparos fuera">Fuera</th>
                  <th className="text-right px-1" title="Disparos bloqueados">Bloq.</th>
                  <th className="text-right px-1">Robos</th>
                  <th className="text-right px-1">Cortes</th>
                  <th className="text-right px-1" title="Pérdida forzada">PF</th>
                  <th className="text-right px-1" title="Pérdida no forzada">PNF</th>
                  <th className="text-right px-1" title="Balón dividido ganado">BDG</th>
                  <th className="text-right px-1" title="Balón dividido perdido">BDP</th>
                  <th className="text-right px-1" title="Goles encajados (portero)">Goles E.</th>
                </tr>
              </thead>
              <tbody>
                {accionesIndividuales.map(({ nombre, c, esPortero }) => (
                  <tr key={nombre} className="border-b border-zinc-900">
                    <td className={`py-1 px-1 ${esPortero ? "text-yellow-400" : ""} font-bold`}>
                      {nombre}
                    </td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.dpp ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.dpa ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.dpf ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.dpb ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.robos ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.cortes ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.pf ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.pnf ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.bdg ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">{c?.bdp ?? 0}</td>
                    <td className="text-right font-mono tabular-nums px-1">
                      {esPortero ? (c?.golesEncajados ?? 0) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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
        El JSON contiene todo el partido (config + eventos + tiempos + acciones + tanda). Útil para
        archivar el partido o procesarlo después (importar a Google Sheets, hacer un merge entre dos iPads, etc.).
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

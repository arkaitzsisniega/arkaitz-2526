"use client";

import { useState, useMemo, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { usePartido } from "@/lib/store";
import { ROSTER } from "@/lib/roster";
import { formatMMSS, colorTiempoPista, colorTiempoBanquillo } from "@/lib/utils";
import { Campo } from "@/components/Campo";
import { Porteria } from "@/components/Porteria";
import type { ContadoresJugador, ResultadoDisparo, TandaPenaltis, TiroTanda, Partido, ParteId, ConfigPartido } from "@/lib/db";
import { direccionAtaque } from "@/lib/db";

export default function PartidoPage() {
  const router = useRouter();
  const {
    partido, cargado,
    segundosTurnoActual, segundosBanquillo, segundosParte,
    segundosPartidoTotal, segundosEnParte,
    segundosRestantesParte, duracionParteActual,
    play, pausa, ajustarReloj, avanzarParte, cambiarJugador,
    registrarEvento, deshacerUltimoEvento, incAccion, registrarAccionIndividual,
    iniciarTanda, apuntarTiroTanda, deshacerUltimoTiroTanda, cerrarTanda,
    setDuracionesParte, finalizarPartido, retrocederParte,
  } = usePartido();

  // Estado UI
  const [modalCambio, setModalCambio] = useState<{ sale: string } | null>(null);
  const [modalAccionInd, setModalAccionInd] = useState<{ jugador: string } | null>(null);
  const [modalAccionBanquillo, setModalAccionBanquillo] = useState<{ jugador: string } | null>(null);
  const [modalFalta, setModalFalta] = useState(false);
  const [modalGol, setModalGol] = useState(false);
  const [modalAmarilla, setModalAmarilla] = useState(false);
  const [modalRoja, setModalRoja] = useState(false);
  const [modalTM, setModalTM] = useState(false);
  const [modalPen, setModalPen] = useState(false);
  const [modalTanda, setModalTanda] = useState(false);
  const [modalTiempos, setModalTiempos] = useState(false);
  const [modalDisparoRival, setModalDisparoRival] = useState(false);
  const [modalCambioParte, setModalCambioParte] = useState(false);

  // Jugadores nuestros que tienen al menos una amarilla.
  // OJO: useMemo debe ir ANTES de los early returns (reglas de hooks).
  const jugadoresAmarilla = useMemo(() => {
    const s = new Set<string>();
    for (const ev of partido.eventos) {
      if (ev.tipo === "amarilla" && ev.equipo === "INTER" && (ev as any).jugador) {
        s.add((ev as any).jugador);
      }
    }
    return s;
  }, [partido.eventos]);

  // Jugadores EXPULSADOS de los nuestros (2ª amarilla o roja directa).
  // Estos jugadores se bloquean: no se pueden cambiar, ni tocar para
  // acciones individuales, ni asignarles disparos/goles. Quedan fuera
  // del partido para el resto de tiempo.
  const jugadoresExpulsados = useMemo(() => {
    const cuentaAmarillas: Record<string, number> = {};
    const rojas = new Set<string>();
    for (const ev of partido.eventos) {
      const e = ev as any;
      if (e.tipo === "amarilla" && e.equipo === "INTER" && e.jugador) {
        cuentaAmarillas[e.jugador] = (cuentaAmarillas[e.jugador] || 0) + 1;
      }
      if (e.tipo === "roja" && e.equipo === "INTER" && e.jugador) {
        rojas.add(e.jugador);
      }
    }
    const expulsados = new Set<string>();
    for (const [nombre, n] of Object.entries(cuentaAmarillas)) {
      if (n >= 2) expulsados.add(nombre);
    }
    for (const n of rojas) expulsados.add(n);
    return expulsados;
  }, [partido.eventos]);

  // INFERIORIDAD NUMÉRICA — crono regresivo de 2 minutos tras roja de
  // un jugador que estaba en pista. Se cancela si el rival mete gol
  // durante esos 2 minutos (otro jugador puede entrar). En futsal real
  // la regla es: 2 min de juego efectivo o hasta gol del rival.
  //
  // Cálculo derivado de los eventos (sin tocar el schema del partido):
  //   1) Busca eventos `roja` del INTER ordenados por tiempo de partido.
  //   2) Para cada uno, calcula segundosInicio (acumulados de partido).
  //   3) Si el equipo tiene MENOS de 5 en pista actualmente, asumimos
  //      que la última roja causó inferioridad. Si ya hay 5 (cambió a
  //      "Nadie" → reemplazo posterior, etc.), no.
  //   4) Si hubo gol del RIVAL después de la roja, fin de inferioridad.
  //   5) Si han pasado más de 120s del cronómetro de partido, fin.
  const inferioridad = useMemo(() => {
    const evs = partido.eventos as any[];
    const rojas = evs
      .filter((e) => e.tipo === "roja" && e.equipo === "INTER")
      .sort((a, b) => (a.segundosPartido || 0) - (b.segundosPartido || 0));
    if (rojas.length === 0) return null;
    if (partido.enPista.length >= 5) return null;  // ya hay 5 en pista
    // Última roja
    const ultRoja = rojas[rojas.length - 1];
    const tRoja = ultRoja.segundosPartido || 0;
    // ¿Hubo gol del rival después?
    const golRivalDespues = evs.some(
      (e) => e.tipo === "gol" && e.equipo === "RIVAL"
              && (e.segundosPartido || 0) > tRoja
    );
    if (golRivalDespues) return null;
    // Tiempo actual de partido
    const tActual = segundosPartidoTotal();
    const trans = tActual - tRoja;
    if (trans >= 120) return null;  // ya pasaron los 2 minutos
    return {
      segRestantes: Math.max(0, 120 - trans),
      jugador: ultRoja.jugador || "expulsado",
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partido.eventos, partido.enPista.length, partido.cronometro]);

  // SUPERIORIDAD NUMÉRICA — espejo de inferioridad pero cuando expulsan
  // a un jugador del RIVAL. El Inter juega con 5 vs 4. Termina si:
  // (a) marca el INTER (compensación natural en futsal), o
  // (b) pasan 120 s desde la expulsión.
  // No depende de partido.enPista (estructuralmente no tenemos "rival
  // en pista"; lo derivamos solo de eventos).
  const superioridad = useMemo(() => {
    const evs = partido.eventos as any[];
    const rojasRival = evs
      .filter((e) => e.tipo === "roja" && e.equipo === "RIVAL")
      .sort((a, b) => (a.segundosPartido || 0) - (b.segundosPartido || 0));
    if (rojasRival.length === 0) return null;
    const ultRoja = rojasRival[rojasRival.length - 1];
    const tRoja = ultRoja.segundosPartido || 0;
    // ¿Hubo gol del INTER después? Entonces se ha "consumido" la
    // superioridad (el rival recupera el quinto).
    const golInterDespues = evs.some(
      (e) => e.tipo === "gol" && e.equipo === "INTER"
              && (e.segundosPartido || 0) > tRoja
    );
    if (golInterDespues) return null;
    const tActual = segundosPartidoTotal();
    const trans = tActual - tRoja;
    if (trans >= 120) return null;
    return {
      segRestantes: Math.max(0, 120 - trans),
      dorsalRival: ultRoja.jugador || "expulsado",
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partido.eventos, partido.cronometro]);

  // Helper central para EXPULSAR a un jugador INTER: registra evento
  // roja + si el jugador está en pista, lo saca automáticamente
  // dejando un slot vacío (inferioridad numérica). Si está en banquillo,
  // solo registra la roja (queda como expulsado sin más).
  //
  // Usar SIEMPRE desde cualquier sitio que registre una roja INTER (no
  // llamar a registrarEvento directamente) para que el comportamiento
  // sea consistente y se dispare el crono regresivo.
  const expulsarJugadorInter = (jugador: string) => {
    registrarEvento({ tipo: "roja", equipo: "INTER", jugador } as any);
    if (partido.enPista.includes(jugador)) {
      // cambiarJugador con entra="" saca al jugador sin reemplazo →
      // enPista pasa de 5 a 4. Eso dispara el banner de inferioridad.
      cambiarJugador(jugador, "");
    }
  };

  // Helper único para registrar amarilla a un jugador INTER. Si era la
  // 2ª amarilla, dispara automáticamente la EXPULSIÓN (roja + sale
  // de pista si estaba).
  const registrarAmarillaInter = (jugador: string) => {
    registrarEvento({ tipo: "amarilla", equipo: "INTER", jugador } as any);
    const yaTenia = partido.eventos.filter(
      (e: any) => e.tipo === "amarilla" && e.equipo === "INTER" && e.jugador === jugador
    ).length;
    if (yaTenia + 1 >= 2) {
      expulsarJugadorInter(jugador);
    }
  };

  if (!cargado) {
    return <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">Cargando…</div>;
  }
  if (partido.estado !== "en_curso" || !partido.config) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center gap-4">
        <p className="text-xl">No hay partido en curso.</p>
        <button onClick={() => router.push("/nuevo")}
          className="px-6 py-3 bg-emerald-700 rounded-xl text-lg font-bold">
          🏁 Crear partido nuevo
        </button>
      </div>
    );
  }

  const cfg = partido.config;
  const corriendo = partido.cronometro.ultimoStart != null;
  const segParte = segundosParte();
  const dur = duracionParteActual();
  const restantes = segundosRestantesParte();
  const acabada = dur > 0 && restantes <= 0;
  const enPista = partido.enPista;
  const banquillo = cfg.convocados.filter((n) => !enPista.includes(n));
  // Listas FILTRADAS sin expulsados: usadas en todos los modales y
  // selectores donde no tiene sentido elegir a un jugador expulsado
  // (cambios, asignación de stats, falta, gol, etc). Las versiones
  // originales `enPista`/`banquillo` se reservan para el render
  // visual donde el expulsado SÍ debe aparecer (con su estética roja).
  const enPistaActivos = enPista.filter((n) => !jugadoresExpulsados.has(n));
  const banquilloActivos = banquillo.filter((n) => !jugadoresExpulsados.has(n));

  const p = partido.cronometro.parteActual;
  const sFalt = partido.stats.faltas[p];
  const sAma = partido.stats.amarillas[p];
  const sTM = partido.stats.tiemposMuerto[p];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-3">
      {/* HEADER */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-3">
          <div className={`text-6xl font-mono font-bold tabular-nums ${acabada ? "text-red-500 animate-pulse" : ""}`}>
            {dur > 0 ? formatMMSS(restantes) : formatMMSS(segParte)}
          </div>
          <div className="text-sm text-zinc-400">
            <div className="font-bold">{p}</div>
            <div className="text-xs">
              {dur > 0
                ? `${formatMMSS(segParte)} / ${formatMMSS(dur)}`
                : `tot ${formatMMSS(segundosPartidoTotal())}`}
            </div>
            {acabada && <div className="text-red-400 text-xs font-bold mt-0.5">⏱️ Fin de parte</div>}
          </div>
        </div>
        <div className="text-4xl font-bold tabular-nums">
          <span className="text-emerald-400">INTER {partido.marcador.inter}</span>
          <span className="text-zinc-500 mx-2">-</span>
          <span className="text-red-400">{partido.marcador.rival} {cfg.rival}</span>
        </div>
        <div className="flex gap-2">
          {!corriendo
            ? <button onClick={play} className="px-5 py-3 bg-green-700 hover:bg-green-600 rounded-lg text-lg font-bold">▶ INICIAR</button>
            : <button onClick={pausa} className="px-5 py-3 bg-orange-700 hover:bg-orange-600 rounded-lg text-lg font-bold">⏸ PAUSAR</button>}
          <button
            onClick={() => {
              if (p !== "1T" && confirm(`¿Volver a la parte anterior? (estás en ${p})`)) {
                retrocederParte();
              }
            }}
            disabled={p === "1T"}
            className="px-2 py-3 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed rounded-lg text-sm"
            title="Volver a la parte anterior (deshacer ⏭)">
            ⏮
          </button>
          <button onClick={() => setModalCambioParte(true)}
            className="px-3 py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
            ⏭ parte
          </button>
        </div>
      </div>

      {/* BANNERS DE INFERIORIDAD / SUPERIORIDAD NUMÉRICA — pueden estar
          activos simultáneamente si hay expulsión de ambos equipos
          dentro de los 2 min. */}
      {(inferioridad || superioridad) && (
        <div className={`grid ${(inferioridad && superioridad) ? "grid-cols-2" : "grid-cols-1"} gap-2 mb-3`}>
          {inferioridad && (
            <div className="bg-red-700/90 border-2 border-red-400 rounded-lg p-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="text-3xl">🟥</span>
                <div>
                  <div className="text-base font-bold leading-tight">
                    INFERIORIDAD · expulsado {inferioridad.jugador}
                  </div>
                  <div className="text-xs text-red-100 mt-0.5">
                    Acaba a los 2 min o si el rival mete gol.
                  </div>
                </div>
              </div>
              <div className="text-4xl font-mono font-bold tabular-nums">
                {formatMMSS(Math.ceil(inferioridad.segRestantes))}
              </div>
            </div>
          )}
          {superioridad && (
            <div className="bg-emerald-700/90 border-2 border-emerald-400 rounded-lg p-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="text-3xl">🟩</span>
                <div>
                  <div className="text-base font-bold leading-tight">
                    SUPERIORIDAD · rival {superioridad.dorsalRival} fuera
                  </div>
                  <div className="text-xs text-emerald-100 mt-0.5">
                    Acaba a los 2 min o si nosotros metemos gol.
                  </div>
                </div>
              </div>
              <div className="text-4xl font-mono font-bold tabular-nums">
                {formatMMSS(Math.ceil(superioridad.segRestantes))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Botones de ajuste de reloj */}
      <div className="flex items-center gap-2 mb-3 text-sm">
        <span className="text-zinc-500 text-xs">Ajustar reloj:</span>
        <button onClick={() => ajustarReloj(-60)}
          className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded text-zinc-300 font-mono">−1:00</button>
        <button onClick={() => ajustarReloj(-10)}
          className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded text-zinc-300 font-mono">−0:10</button>
        <button onClick={() => ajustarReloj(+10)}
          className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded text-zinc-300 font-mono">+0:10</button>
        <button onClick={() => ajustarReloj(+60)}
          className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded text-zinc-300 font-mono">+1:00</button>
        <span className="text-zinc-600 text-[10px] ml-2">(ajusta también tiempo de jugadores en pista)</span>
      </div>

      {/* EN PISTA — ocupa todo el ancho, los 5 jugadores en columnas iguales y bien grandes */}
      <div className="bg-zinc-900 rounded-xl p-3 mb-3">
        <h2 className="text-zinc-400 text-sm mb-2">EN PISTA (toca un jugador para apuntar acciones)</h2>
        <div className="grid grid-cols-5 gap-2">
          {enPista.map((nombre) => {
            const seg = segundosTurnoActual(nombre);
            const totalParte = segundosEnParte(nombre, p);
            const dorsal = ROSTER.find((j) => j.nombre === nombre)?.dorsal || "";
            const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
            const tieneAmarilla = jugadoresAmarilla.has(nombre);
            const estaExpulsado = jugadoresExpulsados.has(nombre);
            return (
              <button key={nombre}
                onClick={() => {
                  if (estaExpulsado) return;  // bloqueado: no se puede tocar
                  setModalAccionInd({ jugador: nombre });
                }}
                disabled={estaExpulsado}
                className={`relative p-5 min-h-[140px] rounded-lg text-center flex flex-col justify-center ${
                  estaExpulsado
                    ? "bg-red-900/70 border-2 border-red-500 opacity-80 cursor-not-allowed"
                    : esPortero
                      ? "bg-zinc-800 border-2 border-zinc-600"
                      : colorTiempoPista(seg)
                } ${tieneAmarilla && !estaExpulsado ? "ring-2 ring-yellow-400 ring-offset-2 ring-offset-zinc-900" : ""}`}>
                {estaExpulsado && (
                  <span className="absolute top-1.5 right-1.5 text-xl leading-none" title="Expulsado">🟥</span>
                )}
                {!estaExpulsado && tieneAmarilla && (
                  <span className="absolute top-1.5 right-1.5 text-xl leading-none" title="Amarilla">🟨</span>
                )}
                {esPortero && !estaExpulsado && (
                  <span className="absolute top-1.5 left-1.5 text-sm">🥅</span>
                )}
                <div className="text-sm opacity-70">{dorsal ? `#${dorsal}` : "—"}</div>
                <div className={`text-lg font-bold leading-tight ${estaExpulsado ? "line-through" : ""}`}>{nombre}</div>
                {estaExpulsado ? (
                  <div className="text-base font-bold mt-2 text-red-200">EXPULSADO</div>
                ) : (
                  <>
                    <div className="text-3xl font-mono tabular-nums mt-2">{formatMMSS(seg)}</div>
                    <div className="text-sm opacity-70 mt-1">parte {formatMMSS(totalParte)}</div>
                  </>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* BANQUILLO */}
      <div className="bg-zinc-900 rounded-xl p-4 mb-3">
        <h2 className="text-zinc-400 text-base mb-3">BANQUILLO (toca un jugador para amarilla / falta / cambiar)</h2>
        <div className="grid grid-cols-6 gap-2">
          {banquillo.map((nombre) => {
            const seg = segundosBanquillo(nombre);
            // segTurnoUltimo = tiempo que jugó en su última rotación antes
            // de salir. Lo necesitamos para colorear el banquillo con el
            // nivel correspondiente a su fatiga residual.
            const segUltimo = partido.tiempos[nombre]?.segTurnoUltimo ?? 0;
            const dorsal = ROSTER.find((j) => j.nombre === nombre)?.dorsal || "";
            const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
            const tieneAmarilla = jugadoresAmarilla.has(nombre);
            const estaExpulsado = jugadoresExpulsados.has(nombre);
            return (
              <button key={nombre}
                onClick={() => {
                  if (estaExpulsado) return;
                  setModalAccionBanquillo({ jugador: nombre });
                }}
                disabled={estaExpulsado}
                className={`relative p-3 min-h-[90px] rounded-lg text-center flex flex-col justify-center ${
                  estaExpulsado
                    ? "bg-red-900/70 border border-red-500 opacity-80 cursor-not-allowed"
                    : esPortero
                      ? "bg-zinc-800 border border-zinc-600"
                      : colorTiempoBanquillo(seg, segUltimo)
                } ${tieneAmarilla && !estaExpulsado ? "ring-2 ring-yellow-400 ring-offset-1 ring-offset-zinc-900" : ""}`}>
                {estaExpulsado && (
                  <span className="absolute top-1 right-1 text-base leading-none">🟥</span>
                )}
                {!estaExpulsado && tieneAmarilla && (
                  <span className="absolute top-1 right-1 text-base leading-none">🟨</span>
                )}
                <div className="text-sm opacity-70">{dorsal ? `#${dorsal}` : "—"}</div>
                <div className={`text-base font-bold leading-tight ${estaExpulsado ? "line-through" : ""}`}>{nombre}</div>
                {estaExpulsado ? (
                  <div className="text-xs font-bold mt-1 text-red-200">EXPULSADO</div>
                ) : (
                  <div className="text-xl font-mono tabular-nums mt-1.5">{formatMMSS(seg)}</div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* BOTONES ACCIÓN COLECTIVA */}
      <div className="grid grid-cols-8 gap-2">
        <BotonAccion label="⚽ GOL" color="bg-emerald-700" onClick={() => setModalGol(true)} />
        <BotonAccion label="🎯 DISP. RIVAL" color="bg-red-700" onClick={() => setModalDisparoRival(true)} />
        <BotonAccion label="⚠️ FALTA" color="bg-orange-700" onClick={() => setModalFalta(true)} />
        <BotonAccion label="🟨 AMARILLA" color="bg-yellow-700" onClick={() => setModalAmarilla(true)} />
        <BotonAccion label="🟥 ROJA" color="bg-red-800" onClick={() => setModalRoja(true)} />
        <BotonAccion label="🔄 CAMBIO" color="bg-zinc-700" onClick={() => setModalCambio({ sale: "" })} />
        <BotonAccion label="🛑 T.M." color="bg-purple-700" onClick={() => setModalTM(true)} />
        <BotonAccion label="🎯 PEN/10M" color="bg-pink-700" onClick={() => setModalPen(true)} />
      </div>
      <div className={`grid ${cfg.permiteTanda ? "grid-cols-5" : "grid-cols-4"} gap-2 mt-2`}>
        <button onClick={deshacerUltimoEvento}
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
          ↶ Deshacer
        </button>
        <button onClick={() => setModalTiempos(true)}
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
          📊 TIEMPOS
        </button>
        {cfg.permiteTanda && (
          <button onClick={() => { iniciarTanda(); setModalTanda(true); }}
            className={`py-3 rounded-lg text-sm font-bold ${
              partido.tanda?.tiros.length
                ? "bg-pink-700 hover:bg-pink-600"
                : "bg-zinc-800 hover:bg-zinc-700"
            }`}>
            🥇 TANDA
            {partido.tanda?.tiros.length ? ` (${partido.tanda.marcador.inter}-${partido.tanda.marcador.rival})` : ""}
          </button>
        )}
        <button onClick={() => router.push("/resumen")}
          className="py-3 bg-emerald-700 hover:bg-emerald-600 rounded-lg text-sm font-bold">
          🏁 RESUMEN
        </button>
        <button onClick={() => router.push("/")}
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
          🏠 Inicio
        </button>
      </div>

      {/* STATS compactas al final: faltas / amarillas / tiempos muertos por parte */}
      <div className="bg-zinc-900/60 rounded-lg p-3 mt-3 text-base">
        <div className="flex items-center justify-between flex-wrap gap-x-5 gap-y-2">
          <span className="text-zinc-500 text-xs uppercase tracking-wide">Stats {p}</span>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            <span>
              <span className="text-emerald-400 font-bold">I</span> Faltas{" "}
              <strong className={sFalt.inter >= 5 ? "text-red-400" : ""}>{sFalt.inter}</strong>
              <span className="text-zinc-600 mx-1">/</span>
              <span className="text-red-400 font-bold">R</span> Faltas{" "}
              <strong className={sFalt.rival >= 5 ? "text-red-400" : ""}>{sFalt.rival}</strong>
            </span>
            <span>
              🟨 <strong>{sAma.inter}</strong>
              <span className="text-zinc-600">/</span>
              <strong>{sAma.rival}</strong>
            </span>
            <span>
              🛑 TM <strong>{sTM.inter}</strong>
              <span className="text-zinc-600">/</span>
              <strong>{sTM.rival}</strong>
            </span>
          </div>
        </div>

        {/* Dorsales del RIVAL con tarjetas (amarilla / roja). Se construye
            sobre la marcha desde los eventos. Útil para el CT que necesita
            saber a quién han amonestado del rival. */}
        {(() => {
          const evs = partido.eventos as any[];
          const amaRival = evs
            .filter((e) => e.tipo === "amarilla" && e.equipo === "RIVAL" && e.jugador)
            .map((e) => e.jugador as string);
          const rojaRival = evs
            .filter((e) => e.tipo === "roja" && e.equipo === "RIVAL" && e.jugador)
            .map((e) => e.jugador as string);
          if (!amaRival.length && !rojaRival.length) return null;
          // Si un dorsal ya tiene roja, lo quitamos de la lista de amarillas
          const rojaSet = new Set(rojaRival);
          const amaSinExpulsados = amaRival.filter((d) => !rojaSet.has(d));
          return (
            <div className="mt-2 flex flex-wrap gap-3 text-sm">
              {amaSinExpulsados.length > 0 && (
                <span className="text-yellow-300">
                  🟨 {cfg.rival}: <strong>{amaSinExpulsados.join(", ")}</strong>
                </span>
              )}
              {rojaRival.length > 0 && (
                <span className="text-red-300">
                  🟥 {cfg.rival} expulsado: <strong>{rojaRival.join(", ")}</strong>
                </span>
              )}
            </div>
          );
        })()}
        {/* Avisos de faltas escalonados: 4ª (cuidado), 5ª (siguiente es 10m),
            6ª (ya es 10m). Solo mostramos el más alto que aplique. */}
        {sFalt.inter === 4 && (
          <div className="mt-2 bg-amber-600 rounded px-3 py-1 text-center font-bold">
            ⚠️ Inter: 4ª falta. Ojo.
          </div>
        )}
        {sFalt.inter === 5 && (
          <div className="mt-2 bg-orange-600 rounded px-3 py-1 text-center font-bold">
            ⚠️ Inter: 5ª falta. La siguiente es 10 m.
          </div>
        )}
        {sFalt.inter >= 6 && (
          <div className="mt-2 bg-red-700 rounded px-3 py-1 text-center font-bold">
            ⚠️ Inter {sFalt.inter}ª falta → 10 m a favor del rival
          </div>
        )}
        {sFalt.rival === 4 && (
          <div className="mt-2 bg-amber-600 rounded px-3 py-1 text-center font-bold">
            ⚠️ Rival: 4ª falta. Ojo.
          </div>
        )}
        {sFalt.rival === 5 && (
          <div className="mt-2 bg-orange-600 rounded px-3 py-1 text-center font-bold">
            ⚠️ Rival: 5ª falta. La siguiente es 10 m.
          </div>
        )}
        {sFalt.rival >= 6 && (
          <div className="mt-2 bg-emerald-700 rounded px-3 py-1 text-center font-bold">
            ⚠️ Rival {sFalt.rival}ª falta → 10 m a favor del Inter
          </div>
        )}
      </div>

      {modalCambio && (
        <ModalCambio
          enPista={enPistaActivos}
          banquillo={banquilloActivos}
          saleInicial={modalCambio.sale}
          onCerrar={() => setModalCambio(null)}
          onConfirmar={(sale, entra) => {
            cambiarJugador(sale, entra);
            setModalCambio(null);
          }}
        />
      )}

      {modalAccionBanquillo && (
        <ModalAccionBanquillo
          jugador={modalAccionBanquillo.jugador}
          enPista={enPistaActivos}
          onCerrar={() => setModalAccionBanquillo(null)}
          onAmarilla={() => {
            registrarAmarillaInter(modalAccionBanquillo.jugador);
            setModalAccionBanquillo(null);
          }}
          onRoja={() => {
            expulsarJugadorInter(modalAccionBanquillo.jugador);
            setModalAccionBanquillo(null);
          }}
          onFalta={() => {
            registrarEvento({
              tipo: "falta",
              equipo: "INTER",
              jugador: modalAccionBanquillo.jugador,
            } as any);
            setModalAccionBanquillo(null);
          }}
          onCambioPor={(saleDePista) => {
            cambiarJugador(saleDePista, modalAccionBanquillo.jugador);
            setModalAccionBanquillo(null);
          }}
        />
      )}

      {modalAccionInd && (
        <ModalAccionIndividual
          jugador={modalAccionInd.jugador}
          enPista={enPistaActivos}
          banquillo={banquilloActivos}
          cfg={cfg}
          parteActual={p}
          onCerrar={() => setModalAccionInd(null)}
          onCambio={(sale, entra) => {
            cambiarJugador(sale, entra);
            setModalAccionInd(null);
          }}
          onAmarilla={() => {
            registrarAmarillaInter(modalAccionInd.jugador);
            setModalAccionInd(null);
          }}
          onRoja={() => {
            expulsarJugadorInter(modalAccionInd.jugador);
            setModalAccionInd(null);
          }}
          onFalta={() => {
            registrarEvento({
              tipo: "falta",
              equipo: "INTER",
              jugador: modalAccionInd.jugador,
            } as any);
            setModalAccionInd(null);
          }}
          onContador={(tipo) => {
            incAccion(modalAccionInd.jugador, tipo, 1);
            setModalAccionInd(null);
          }}
          onAccionConZona={(tipo, zona) => {
            registrarAccionIndividual(modalAccionInd.jugador, tipo, zona);
            setModalAccionInd(null);
          }}
          onDisparo={(detalles) => {
            // Registrar como evento "disparo" (no es gol, si fuera gol se usaría GOL).
            registrarEvento({
              tipo: "disparo",
              equipo: "INTER",
              jugador: modalAccionInd.jugador,
              resultado: detalles.resultado,
              zonaCampo: detalles.zonaCampo || undefined,
              zonaPorteria: detalles.zonaPorteria || undefined,
            } as any);
            setModalAccionInd(null);
          }}
        />
      )}

      {modalFalta && (
        <ModalFalta
          enPista={enPistaActivos}
          banquillo={banquilloActivos}
          rivalNombre={cfg.rival}
          cfg={cfg}
          parteActual={p}
          onCerrar={() => setModalFalta(false)}
          onConfirmar={(ev) => {
            registrarEvento(ev as any);
            setModalFalta(false);
          }}
        />
      )}

      {modalGol && (
        <ModalGol
          enPista={enPistaActivos}
          rivalNombre={cfg.rival}
          cfg={cfg}
          parteActual={p}
          onCerrar={() => setModalGol(false)}
          onConfirmar={(ev, penaltiExtra) => {
            registrarEvento(ev as any, penaltiExtra);
            setModalGol(false);
          }}
        />
      )}

      {modalAmarilla && (
        <ModalAmarilla
          enPista={enPistaActivos}
          banquillo={banquilloActivos}
          rivalNombre={cfg.rival}
          onCerrar={() => setModalAmarilla(false)}
          onConfirmar={(ev) => {
            const evAny = ev as any;
            if (evAny.equipo === "INTER" && evAny.jugador) {
              registrarAmarillaInter(evAny.jugador);
            } else {
              registrarEvento(evAny);
            }
            setModalAmarilla(false);
          }}
        />
      )}

      {modalRoja && (
        <ModalRoja
          enPista={enPistaActivos}
          banquillo={banquilloActivos}
          rivalNombre={cfg.rival}
          onCerrar={() => setModalRoja(false)}
          onConfirmar={(ev) => {
            const evAny = ev as any;
            // Para INTER con jugador → usar helper (registra roja + saca
            // de pista si está). Para RIVAL → solo registrar (no hay
            // "rival en pista" estructural, el crono regresivo se calcula
            // desde los eventos en el useMemo `superioridad`).
            if (evAny.equipo === "INTER" && evAny.jugador) {
              expulsarJugadorInter(evAny.jugador);
            } else {
              registrarEvento(evAny);
            }
            setModalRoja(false);
          }}
        />
      )}

      {modalTM && (
        <ModalTM
          rivalNombre={cfg.rival}
          onCerrar={() => setModalTM(false)}
          onConfirmar={(equipo) => {
            registrarEvento({ tipo: "tiempo_muerto", equipo } as any);
            setModalTM(false);
          }}
        />
      )}

      {modalPen && (
        <ModalPenalti
          enPista={enPistaActivos}
          rivalNombre={cfg.rival}
          onCerrar={() => setModalPen(false)}
          onConfirmar={(ev) => { registrarEvento(ev as any); setModalPen(false); }}
        />
      )}

      {modalDisparoRival && (
        <ModalDisparoRival
          enPista={enPistaActivos}
          rivalNombre={cfg.rival}
          cfg={cfg}
          parteActual={p}
          onCerrar={() => setModalDisparoRival(false)}
          onConfirmar={(ev) => {
            registrarEvento(ev as any);
            setModalDisparoRival(false);
          }}
        />
      )}

      {modalTanda && (
        <ModalTanda
          tanda={partido.tanda}
          enPista={enPistaActivos}
          convocados={cfg.convocados.filter((n) => !jugadoresExpulsados.has(n))}
          rivalNombre={cfg.rival}
          onCerrar={() => { cerrarTanda(); setModalTanda(false); }}
          onApuntar={apuntarTiroTanda}
          onDeshacer={deshacerUltimoTiroTanda}
        />
      )}

      {modalTiempos && (
        <ModalTiempos
          partido={partido}
          enPista={enPista}
          onCerrar={() => setModalTiempos(false)}
          segundosTurnoActual={segundosTurnoActual}
        />
      )}

      {modalCambioParte && (
        <ModalCambioParte
          partido={partido}
          desde={p}
          onCerrar={() => setModalCambioParte(false)}
          onContinuarSiguienteParte={() => {
            avanzarParte();
            setModalCambioParte(false);
          }}
          onConfigurarProrroga={(minutos) => {
            setDuracionesParte({ PR1: minutos, PR2: minutos });
            avanzarParte();
            setModalCambioParte(false);
          }}
          onIrATanda={() => {
            iniciarTanda();
            setModalCambioParte(false);
            setModalTanda(true);
          }}
          onFinalizar={() => {
            finalizarPartido();
            setModalCambioParte(false);
            router.push("/resumen");
          }}
        />
      )}
    </div>
  );
}

// ──────────────── COMPONENTES BÁSICOS ────────────────

function BotonAccion(props: { label: string; color: string; onClick: () => void }) {
  return (
    <button onClick={props.onClick}
      className={`${props.color} hover:opacity-90 py-7 rounded-xl text-xl font-bold leading-tight`}>
      {props.label}
    </button>
  );
}

function ModalShell(props: { titulo: string; onCerrar: () => void; children: React.ReactNode; maxW?: string }) {
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50"
      onClick={props.onCerrar}>
      <div className={`bg-zinc-900 rounded-xl p-5 w-full ${props.maxW || "max-w-4xl"} max-h-[95vh] overflow-y-auto`}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-2xl font-bold">{props.titulo}</h2>
          <button onClick={props.onCerrar} className="text-zinc-400 text-3xl leading-none px-2">×</button>
        </div>
        {props.children}
      </div>
    </div>
  );
}

function ChipsJugador(props: {
  opciones: string[];
  seleccionado: string;
  onSelect: (n: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {props.opciones.map((n) => (
        <button key={n} onClick={() => props.onSelect(n)}
          className={`px-3 py-2 rounded text-base ${
            props.seleccionado === n ? "bg-emerald-700 text-white" : "bg-zinc-800 text-zinc-200"
          }`}>{n}</button>
      ))}
    </div>
  );
}

function Paso(props: { n: number; titulo: string; activo: boolean; children: React.ReactNode }) {
  return (
    <div className={`mb-3 ${props.activo ? "" : "opacity-50"}`}>
      <h3 className="text-sm text-zinc-400 mb-2">
        <span className="bg-zinc-800 px-2 py-0.5 rounded-full text-xs mr-2">{props.n}</span>
        {props.titulo}
      </h3>
      {props.children}
    </div>
  );
}

// ──────────────── MODAL ACCIÓN BANQUILLO ────────────────
// Toque en jugador del banquillo: amarilla, falta o cambio rápido por uno en pista.

function ModalAccionBanquillo(props: {
  jugador: string;
  enPista: string[];
  onCerrar: () => void;
  onAmarilla: () => void;
  onRoja: () => void;
  onFalta: () => void;
  onCambioPor: (saleDePista: string) => void;
}) {
  return (
    <ModalShell titulo={`🪑 ${props.jugador} (banquillo)`} onCerrar={props.onCerrar} maxW="max-w-2xl">
      <div className="grid grid-cols-3 gap-3 mb-4">
        <button onClick={props.onAmarilla}
          className="py-4 bg-yellow-700 hover:bg-yellow-600 rounded-lg text-lg font-bold">
          🟨 Amarilla
        </button>
        <button onClick={props.onRoja}
          className="py-4 bg-red-800 hover:bg-red-700 rounded-lg text-lg font-bold">
          🟥 Roja
        </button>
        <button onClick={props.onFalta}
          className="py-4 bg-orange-700 hover:bg-orange-600 rounded-lg text-lg font-bold">
          ⚠️ Falta
        </button>
      </div>
      <h3 className="text-sm text-zinc-400 mb-2">🔄 …o entra por (sale de pista):</h3>
      <div className="grid grid-cols-5 gap-2">
        {props.enPista.map((n) => (
          <button key={n}
            onClick={() => props.onCambioPor(n)}
            className="py-4 bg-emerald-700 hover:bg-emerald-600 rounded-lg text-base font-bold">
            {n}
          </button>
        ))}
      </div>
    </ModalShell>
  );
}

// ──────────────── MODAL CAMBIO (auto-confirm al seleccionar entra) ────────────────

function ModalCambio(props: {
  enPista: string[]; banquillo: string[]; saleInicial: string;
  onCerrar: () => void;
  onConfirmar: (sale: string, entra: string) => void;
}) {
  const [sale, setSale] = useState(props.saleInicial);
  return (
    <ModalShell titulo="🔄 Cambio" onCerrar={props.onCerrar} maxW="max-w-2xl">
      <Paso n={1} titulo="SALE de pista" activo={!sale}>
        <ChipsJugador opciones={props.enPista} seleccionado={sale} onSelect={setSale} />
      </Paso>
      {sale && (
        <Paso n={2} titulo={`ENTRA por ${sale} (tap = aplicar)`} activo={true}>
          <div className="flex flex-wrap gap-2">
            {props.banquillo.map((n) => (
              <button key={n}
                onClick={() => props.onConfirmar(sale, n)}
                className="px-4 py-3 bg-emerald-700 hover:bg-emerald-600 rounded text-base font-bold">
                {n}
              </button>
            ))}
            {/* Slot NADIE: deja un hueco en pista (inferioridad numérica
                tras expulsión, p.ej.). Si después quieres meter a alguien
                usa Cambio normal con SALE = (uno de los 4 restantes) o
                tocando un jugador del banquillo. */}
            <button
              onClick={() => props.onConfirmar(sale, "")}
              className="px-4 py-3 bg-zinc-700 hover:bg-zinc-600 rounded text-base font-bold border-2 border-dashed border-zinc-500"
              title="Dejar slot vacío en pista (inferioridad numérica)">
              — Nadie (hueco)
            </button>
          </div>
        </Paso>
      )}
    </ModalShell>
  );
}

// ──────────────── MODAL FALTA ────────────────
// Flujo: equipo → jugador (o SIN ASIGNAR / RIVAL-MANO) → zona campo → cierra.

function ModalFalta(props: {
  enPista: string[];
  banquillo: string[];     // se admiten también jugadores del banquillo
  rivalNombre: string;
  cfg: ConfigPartido; parteActual: ParteId;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL" | null>(null);
  const [jugador, setJugador] = useState<string>("");
  const [sinAsignar, setSinAsignar] = useState(false);
  const [rivalMano, setRivalMano] = useState(false);
  // Lista de candidatos: primero los que están en pista, después los del
  // banquillo (puede haber falta a un jugador del banquillo si protesta
  // o si entra a discusión por ejemplo).
  const candidatos = [...props.enPista, ...props.banquillo];

  const aplicar = (zonaCampo?: string) => {
    const ev: any = { tipo: "falta", equipo };
    if (jugador) ev.jugador = jugador;
    if (sinAsignar) ev.sinAsignar = true;
    if (rivalMano) ev.rivalMano = true;
    if (zonaCampo) ev.zonaCampo = zonaCampo;
    props.onConfirmar(ev);
  };

  return (
    <ModalShell titulo="⚠️ Falta" onCerrar={props.onCerrar}>
      <Paso n={1} titulo="¿Qué equipo la comete?" activo={!equipo}>
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => { setEquipo("INTER"); }}
            className={`px-6 py-4 rounded text-lg font-bold ${
              equipo === "INTER" ? "bg-emerald-700" : "bg-zinc-800"
            }`}>La COMETEMOS nosotros</button>
          <button onClick={() => { setEquipo("RIVAL"); }}
            className={`px-6 py-4 rounded text-lg font-bold ${
              equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"
            }`}>La COMETE {props.rivalNombre}</button>
        </div>
      </Paso>

      {equipo && (
        <Paso n={2}
          titulo={
            equipo === "INTER"
              ? "¿Qué jugador la comete? (o sin asignar / RIVAL-MANO)"
              : "¿Quién la recibe? (o sin asignar)"
          }
          activo={!jugador && !sinAsignar && !rivalMano}>
          <div className="flex flex-wrap gap-2">
            {candidatos.map((n) => {
              const enBanquillo = props.banquillo.includes(n);
              return (
                <button key={n}
                  onClick={() => { setJugador(n); setSinAsignar(false); setRivalMano(false); }}
                  className={`px-3 py-2 rounded text-base ${
                    jugador === n ? "bg-emerald-700"
                                  : enBanquillo ? "bg-zinc-700 opacity-70" : "bg-zinc-800"
                  }`}
                  title={enBanquillo ? "Jugador en banquillo" : undefined}>
                  {n}{enBanquillo ? " 🪑" : ""}
                </button>
              );
            })}
            <button onClick={() => { setJugador(""); setSinAsignar(true); setRivalMano(false); }}
              className={`px-3 py-2 rounded text-base ${
                sinAsignar ? "bg-zinc-500" : "bg-zinc-800"
              }`}>SIN ASIGNAR</button>
            {equipo === "INTER" && (
              <button onClick={() => { setJugador(""); setRivalMano(true); setSinAsignar(false); }}
                className={`px-3 py-2 rounded text-base ${
                  rivalMano ? "bg-purple-700" : "bg-zinc-800"
                }`}>RIVAL / MANO</button>
            )}
          </div>
        </Paso>
      )}

      {equipo && (jugador || sinAsignar || rivalMano) && (
        <Paso n={3} titulo="Zona del campo donde se produce (tap = aplicar)" activo>
          <Campo onSelect={(z) => aplicar(z)}
            direccion={direccionAtaque(props.parteActual, equipo, props.cfg)}
            nombreAtacante={equipo === "INTER" ? "Inter" : props.rivalNombre} />
          <div className="mt-2 flex justify-end">
            <button onClick={() => aplicar(undefined)}
              className="px-3 py-1 bg-zinc-700 hover:bg-zinc-600 rounded text-xs">
              Saltar zona y guardar
            </button>
          </div>
        </Paso>
      )}
    </ModalShell>
  );
}

// ──────────────── MODAL AMARILLA ────────────────

function ModalAmarilla(props: {
  enPista: string[];
  banquillo: string[];
  rivalNombre: string;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL" | null>(null);

  const candidatos = [...props.enPista, ...props.banquillo];

  return (
    <ModalShell titulo="🟨 Tarjeta amarilla" onCerrar={props.onCerrar} maxW="max-w-2xl">
      <Paso n={1} titulo="Equipo" activo={!equipo}>
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => setEquipo("INTER")}
            className={`py-4 rounded text-lg font-bold ${
              equipo === "INTER" ? "bg-emerald-700" : "bg-zinc-800"
            }`}>INTER</button>
          <button onClick={() => { setEquipo("RIVAL"); }}
            className={`py-4 rounded text-lg font-bold ${
              equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"
            }`}>{props.rivalNombre}</button>
        </div>
      </Paso>
      {equipo === "INTER" && (
        <Paso n={2} titulo="Jugador (tap = aplicar) o saltar" activo>
          <div className="flex flex-wrap gap-2">
            {candidatos.map((n) => {
              const enBanquillo = props.banquillo.includes(n);
              return (
                <button key={n} onClick={() => props.onConfirmar({ tipo: "amarilla", equipo: "INTER", jugador: n })}
                  className={`px-3 py-2 rounded ${
                    enBanquillo ? "bg-zinc-700 hover:bg-zinc-600 opacity-80"
                                : "bg-emerald-700 hover:bg-emerald-600"
                  }`}
                  title={enBanquillo ? "Jugador en banquillo" : undefined}>
                  {n}{enBanquillo ? " 🪑" : ""}
                </button>
              );
            })}
            <button onClick={() => props.onConfirmar({ tipo: "amarilla", equipo: "INTER" })}
              className="px-3 py-2 rounded bg-zinc-700">SIN ASIGNAR</button>
          </div>
        </Paso>
      )}
      {equipo === "RIVAL" && (
        <TecladoDorsalRival
          titulo={`Dorsal del rival que recibe la amarilla`}
          onConfirmar={(dorsalOCT) => props.onConfirmar({
            tipo: "amarilla", equipo: "RIVAL", jugador: dorsalOCT,
          })}
          onSinAsignar={() => props.onConfirmar({ tipo: "amarilla", equipo: "RIVAL" })}
        />
      )}
    </ModalShell>
  );
}

// ──────────────── MODAL ROJA ────────────────
// Igual que amarilla pero registra evento roja directamente. Para
// expulsiones por roja directa o por 2ª amarilla manual.

function ModalRoja(props: {
  enPista: string[];
  banquillo: string[];
  rivalNombre: string;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL" | null>(null);
  const candidatos = [...props.enPista, ...props.banquillo];

  return (
    <ModalShell titulo="🟥 Tarjeta roja (expulsión)" onCerrar={props.onCerrar} maxW="max-w-2xl">
      <Paso n={1} titulo="Equipo" activo={!equipo}>
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => setEquipo("INTER")}
            className={`py-4 rounded text-lg font-bold ${
              equipo === "INTER" ? "bg-emerald-700" : "bg-zinc-800"
            }`}>INTER</button>
          <button onClick={() => setEquipo("RIVAL")}
            className={`py-4 rounded text-lg font-bold ${
              equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"
            }`}>{props.rivalNombre}</button>
        </div>
      </Paso>
      {equipo === "INTER" && (
        <Paso n={2} titulo="Jugador expulsado (tap = aplicar)" activo>
          <div className="flex flex-wrap gap-2">
            {candidatos.map((n) => {
              const enBanquillo = props.banquillo.includes(n);
              return (
                <button key={n} onClick={() => props.onConfirmar({ tipo: "roja", equipo: "INTER", jugador: n })}
                  className={`px-3 py-2 rounded ${
                    enBanquillo ? "bg-zinc-700 hover:bg-zinc-600 opacity-80"
                                : "bg-red-700 hover:bg-red-600"
                  }`}>
                  {n}{enBanquillo ? " 🪑" : ""}
                </button>
              );
            })}
          </div>
        </Paso>
      )}
      {equipo === "RIVAL" && (
        <TecladoDorsalRival
          titulo="Dorsal del rival expulsado"
          onConfirmar={(dorsalOCT) => props.onConfirmar({
            tipo: "roja", equipo: "RIVAL", jugador: dorsalOCT,
          })}
          onSinAsignar={() => props.onConfirmar({ tipo: "roja", equipo: "RIVAL" })}
        />
      )}
    </ModalShell>
  );
}

// ──────────────── TECLADO NUMÉRICO RIVAL ────────────────
// Permite teclear el dorsal del jugador rival que recibe la tarjeta.
// Tecla extra "CT" = cuerpo técnico recibe la amonestación.
// El dorsal se devuelve como string con prefijo "#": "#17", "#CT".

function TecladoDorsalRival(props: {
  titulo: string;
  onConfirmar: (dorsalOCT: string) => void;
  onSinAsignar: () => void;
}) {
  const [dorsal, setDorsal] = useState("");
  const teclas = ["1","2","3","4","5","6","7","8","9","0"];

  const pulsa = (t: string) => {
    if (dorsal.length < 3) setDorsal(dorsal + t);
  };
  const borrar = () => setDorsal(dorsal.slice(0, -1));
  const confirmar = () => {
    if (!dorsal) return;
    props.onConfirmar(`#${dorsal}`);
  };

  return (
    <Paso n={2} titulo={props.titulo} activo>
      <div className="bg-zinc-950 rounded-lg p-4 mb-3 text-center">
        <div className="text-zinc-500 text-sm mb-1">Dorsal seleccionado:</div>
        <div className="text-5xl font-bold font-mono tabular-nums min-h-[60px]">
          {dorsal ? `#${dorsal}` : <span className="text-zinc-700">—</span>}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 mb-2">
        {teclas.slice(0, 9).map((t) => (
          <button key={t} onClick={() => pulsa(t)}
            className="py-5 bg-zinc-700 hover:bg-zinc-600 rounded text-2xl font-bold">
            {t}
          </button>
        ))}
        <button onClick={borrar}
          className="py-5 bg-zinc-800 hover:bg-zinc-700 rounded text-xl">
          ⌫
        </button>
        <button onClick={() => pulsa("0")}
          className="py-5 bg-zinc-700 hover:bg-zinc-600 rounded text-2xl font-bold">
          0
        </button>
        <button onClick={confirmar} disabled={!dorsal}
          className={`py-5 rounded text-xl font-bold ${
            dorsal ? "bg-emerald-700 hover:bg-emerald-600" : "bg-zinc-800 opacity-50"
          }`}>
          ✓
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3">
        <button onClick={() => props.onConfirmar("#CT")}
          className="py-4 bg-purple-700 hover:bg-purple-600 rounded text-base font-bold">
          🧠 Cuerpo técnico (CT)
        </button>
        <button onClick={props.onSinAsignar}
          className="py-4 bg-zinc-700 hover:bg-zinc-600 rounded text-base font-bold">
          Sin asignar
        </button>
      </div>
    </Paso>
  );
}

// ──────────────── MODAL TM ────────────────

function ModalTM(props: {
  rivalNombre: string;
  onCerrar: () => void;
  onConfirmar: (equipo: "INTER" | "RIVAL") => void;
}) {
  return (
    <ModalShell titulo="🛑 Tiempo muerto" onCerrar={props.onCerrar} maxW="max-w-md">
      <div className="grid grid-cols-2 gap-3">
        <button onClick={() => props.onConfirmar("INTER")}
          className="py-6 bg-emerald-700 hover:bg-emerald-600 rounded text-xl font-bold">INTER</button>
        <button onClick={() => props.onConfirmar("RIVAL")}
          className="py-6 bg-red-700 hover:bg-red-600 rounded text-xl font-bold">{props.rivalNombre}</button>
      </div>
    </ModalShell>
  );
}

// ──────────────── MODAL GOL ────────────────

const ACCIONES_GOL = [
  "Córner", "Banda", "Falta", "5x4", "4x5", "Contraataque",
  "Robo zona alta", "1x1 banda", "Ataque posicional", "10m", "Penalti",
  "Otra",
];

function ModalGol(props: {
  enPista: string[]; rivalNombre: string;
  cfg: ConfigPartido; parteActual: ParteId;
  onCerrar: () => void;
  /** penaltiExtra: extras a pasar al store cuando acción=Penalti/10m. */
  onConfirmar: (ev: any, penaltiExtra?: { penaltiTipo?: "penalti" | "diezm"; penaltiPorteroRival?: string }) => void;
}) {
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL" | null>(null);
  const [goleador, setGoleador] = useState("");
  const [asistente, setAsistente] = useState<string | "OMIT" | "">("");
  const [accion, setAccion] = useState("");
  const [zonaCampo, setZonaCampo] = useState("");
  const [zonaPorteria, setZonaPorteria] = useState("");
  const [porteroRival, setPorteroRival] = useState("");

  const esPenaltiOAccion = accion === "Penalti" || accion === "10m";

  const aplicar = (zp: string) => {
    const ev: any = { tipo: "gol", equipo };
    if (equipo === "INTER") {
      ev.goleador = goleador;
      if (asistente && asistente !== "OMIT") ev.asistente = asistente;
      ev.cuarteto = props.enPista.filter((n) => n !== goleador);
    }
    if (accion) ev.accion = accion;
    if (zonaCampo) ev.zonaCampo = zonaCampo;
    if (zp) ev.zonaPorteria = zp;
    if (porteroRival && equipo === "INTER") ev.portero = porteroRival;
    const extra = esPenaltiOAccion
      ? {
          penaltiTipo: (accion === "10m" ? "diezm" : "penalti") as "penalti" | "diezm",
          penaltiPorteroRival: porteroRival || undefined,
        }
      : undefined;
    props.onConfirmar(ev, extra);
  };

  return (
    <ModalShell titulo="⚽ GOL" onCerrar={props.onCerrar}>
      <Paso n={1} titulo="Equipo" activo={!equipo}>
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => setEquipo("INTER")}
            className={`py-4 rounded text-lg font-bold ${
              equipo === "INTER" ? "bg-emerald-700" : "bg-zinc-800"
            }`}>INTER</button>
          <button onClick={() => setEquipo("RIVAL")}
            className={`py-4 rounded text-lg font-bold ${
              equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"
            }`}>{props.rivalNombre}</button>
        </div>
      </Paso>

      {equipo === "INTER" && (
        <>
          <Paso n={2} titulo="Goleador (tap)" activo={!goleador}>
            <ChipsJugador opciones={props.enPista} seleccionado={goleador} onSelect={setGoleador} />
          </Paso>

          {goleador && (
            <Paso n={3} titulo="Asistente (tap o saltar)" activo={!asistente}>
              <div className="flex flex-wrap gap-2">
                {props.enPista.filter((n) => n !== goleador).map((n) => (
                  <button key={n} onClick={() => setAsistente(n)}
                    className={`px-3 py-2 rounded ${
                      asistente === n ? "bg-emerald-700" : "bg-zinc-800"
                    }`}>{n}</button>
                ))}
                <button onClick={() => setAsistente("OMIT")}
                  className={`px-3 py-2 rounded ${
                    asistente === "OMIT" ? "bg-zinc-500" : "bg-zinc-800"
                  }`}>sin asistente</button>
              </div>
            </Paso>
          )}
        </>
      )}

      {(equipo === "RIVAL" || (goleador && asistente)) && (
        <Paso n={equipo === "RIVAL" ? 2 : 4} titulo="Acción del gol" activo={!accion}>
          <div className="flex flex-wrap gap-2">
            {ACCIONES_GOL.map((a) => (
              <button key={a} onClick={() => setAccion(a)}
                className={`px-3 py-2 rounded text-sm ${
                  accion === a ? "bg-emerald-700" : "bg-zinc-800"
                }`}>{a}</button>
            ))}
          </div>
        </Paso>
      )}

      {accion && !esPenaltiOAccion && (
        <Paso n={5} titulo="Zona del campo desde donde se tira" activo={!zonaCampo}>
          <Campo seleccionada={zonaCampo} onSelect={setZonaCampo}
            direccion={equipo ? direccionAtaque(props.parteActual, equipo, props.cfg) : "der"}
            nombreAtacante={equipo === "INTER" ? "Inter" : props.rivalNombre} />
          <div className="mt-1 text-right">
            <button onClick={() => setZonaCampo("__skip__")}
              className="px-3 py-1 bg-zinc-700 rounded text-xs">Saltar zona campo</button>
          </div>
        </Paso>
      )}

      {accion && (zonaCampo || esPenaltiOAccion) && (
        <Paso n={6}
          titulo={
            esPenaltiOAccion
              ? `Portería: ¿dónde entra el ${accion.toLowerCase()}? (tap = guardar)`
              : "Portería: ¿dónde entra? (tap = guardar)"
          }
          activo>
          <Porteria seleccionada={zonaPorteria}
            onSelect={(z) => aplicar(z)} />
          <div className="mt-2 flex items-center gap-2 justify-between">
            {equipo === "INTER" && esPenaltiOAccion && (
              <input className="flex-1 bg-zinc-800 rounded px-3 py-2 text-sm"
                placeholder="Portero rival (opcional, p.ej. 'DIDAC')"
                value={porteroRival}
                onChange={(e) => setPorteroRival(e.target.value.toUpperCase())} />
            )}
            <button onClick={() => aplicar("")}
              className="px-3 py-1 bg-zinc-700 rounded text-xs">Saltar zona portería y guardar</button>
          </div>
        </Paso>
      )}
    </ModalShell>
  );
}

// ──────────────── MODAL DISPARO DEL RIVAL ────────────────
// Flujo: resultado (PUERTA/PALO/FUERA/BLOQUEADO) → zona del campo (desde
// donde tiró, perspectiva del rival que ataca al revés que Inter) →
// si fue a puerta, zona de portería + portero nuestro que recibió.
// Si fue gol, mejor usar el botón GOL (no este modal). Aquí solo
// disparos que NO son gol.

function ModalDisparoRival(props: {
  enPista: string[];
  rivalNombre: string;
  cfg: ConfigPartido; parteActual: ParteId;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [resultado, setResultado] = useState<ResultadoDisparo | null>(null);
  const [zonaCampo, setZonaCampo] = useState("");
  const [zonaPorteria, setZonaPorteria] = useState("");
  const [porteroNuestro, setPorteroNuestro] = useState("");
  const [tirador, setTirador] = useState("");
  // Flag para que el auto-confirmar solo dispare UNA vez (evita doble-close
  // si el useEffect se ejecuta de más).
  const yaConfirmado = useRef(false);

  const aplicar = () => {
    if (yaConfirmado.current) return;
    yaConfirmado.current = true;
    const ev: any = {
      tipo: "disparo",
      equipo: "RIVAL",
      resultado,
    };
    if (tirador) ev.jugador = tirador;
    if (porteroNuestro) ev.portero = porteroNuestro;
    if (zonaCampo) ev.zonaCampo = zonaCampo;
    if (zonaPorteria) ev.zonaPorteria = zonaPorteria;
    props.onConfirmar(ev);
  };

  // Portero nuestro EN PISTA por defecto.
  const porterosPista = props.enPista.filter((n) =>
    ROSTER.find((j) => j.nombre === n)?.posicion === "PORTERO"
  );
  // Si solo hay 1 portero en pista, lo pre-seleccionamos (una sola vez al abrir).
  useEffect(() => {
    if (porterosPista[0] && !porteroNuestro) {
      setPorteroNuestro(porterosPista[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ⚡ Auto-confirmar cuando se completen los pasos requeridos. Ahorra el
  // click final de "Guardar" que pedía Arkaitz.
  // - PUERTA: requiere zonaCampo + zonaPorteria + portero (este pre-seleccionado).
  // - PALO/FUERA/BLOQUEADO: solo zonaCampo (no hay portería que marcar).
  useEffect(() => {
    if (!resultado || yaConfirmado.current) return;
    if (resultado === "PUERTA") {
      if (zonaCampo && zonaPorteria && porteroNuestro) {
        // Pequeño delay para que el usuario VEA su última selección antes
        // de que el modal se cierre (sensación de "fluido" en vez de
        // "brusco").
        const t = setTimeout(aplicar, 200);
        return () => clearTimeout(t);
      }
    } else {
      // PALO / FUERA / BLOQUEADO — basta con tener resultado + zonaCampo
      if (zonaCampo) {
        const t = setTimeout(aplicar, 200);
        return () => clearTimeout(t);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultado, zonaCampo, zonaPorteria, porteroNuestro]);

  return (
    <ModalShell titulo={`🎯 Disparo del ${props.rivalNombre}`} onCerrar={props.onCerrar}>
      <p className="text-xs text-zinc-500 mb-2">
        Para apuntar un disparo del rival que NO fue gol. Si fue gol del rival,
        usa el botón ⚽ GOL.
      </p>

      <Paso n={1} titulo="¿Cómo acabó el disparo?" activo={!resultado}>
        <div className="grid grid-cols-4 gap-2">
          {(["PUERTA", "PALO", "FUERA", "BLOQUEADO"] as ResultadoDisparo[]).map((r) => (
            <button key={r}
              onClick={() => setResultado(r)}
              className={`py-3 rounded font-bold ${
                resultado === r ? "bg-red-700" : "bg-zinc-800"
              }`}>{r}</button>
          ))}
        </div>
        <p className="text-[11px] text-zinc-500 mt-2">
          PUERTA = a puerta pero parado por nuestro portero.
        </p>
      </Paso>

      {resultado && (
        <Paso n={2} titulo="Tirador rival (opcional)" activo>
          <input className="w-full bg-zinc-800 rounded px-3 py-2 text-sm"
            placeholder="Nombre del tirador del rival, número o vacío"
            value={tirador}
            onChange={(e) => setTirador(e.target.value.toUpperCase())} />
        </Paso>
      )}

      {resultado && (
        <Paso n={3} titulo="Zona del campo (desde donde tira el rival)" activo={!zonaCampo}>
          <Campo
            seleccionada={zonaCampo}
            onSelect={setZonaCampo}
            direccion={direccionAtaque(props.parteActual, "RIVAL", props.cfg)}
            nombreAtacante={props.rivalNombre} />
          <div className="mt-2 flex justify-end">
            <button onClick={() => setZonaCampo("__skip__")}
              className="px-3 py-1 bg-zinc-700 rounded text-xs">
              Saltar zona del campo
            </button>
          </div>
        </Paso>
      )}

      {resultado === "PUERTA" && zonaCampo && (
        <Paso n={4} titulo="Zona de portería (a dónde tiró) + portero nuestro" activo>
          <Porteria seleccionada={zonaPorteria} onSelect={setZonaPorteria} />
          <div className="mt-3">
            <h4 className="text-xs text-zinc-400 mb-1">Portero nuestro (el que paró)</h4>
            <ChipsJugador
              opciones={porterosPista}
              seleccionado={porteroNuestro}
              onSelect={setPorteroNuestro} />
          </div>
          <p className="text-xs text-zinc-500 mt-2 italic">
            Se guardará automáticamente al marcar la zona de portería.
          </p>
        </Paso>
      )}

      {resultado && resultado !== "PUERTA" && !zonaCampo && (
        <p className="text-xs text-zinc-500 mt-2 italic">
          Se guardará automáticamente al marcar la zona del campo.
        </p>
      )}
    </ModalShell>
  );
}

// ──────────────── MODAL PENALTI / 10M ────────────────

function ModalPenalti(props: {
  enPista: string[]; rivalNombre: string;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [tipo, setTipo] = useState<"penalti" | "diezm" | null>(null);
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL" | null>(null);
  const [tirador, setTirador] = useState("");
  const [porteroNuestro, setPorteroNuestro] = useState("");
  const [porteroRival, setPorteroRival] = useState("");
  const [resultado, setResultado] = useState<"GOL" | "PARADA" | "POSTE" | "FUERA" | null>(null);

  const aplicar = (zonaPorteria?: string) => {
    const ev: any = {
      tipo,
      equipo,
      tirador: equipo === "INTER" ? tirador : "",
      portero: equipo === "INTER" ? porteroRival : porteroNuestro,
      resultado,
    };
    if (zonaPorteria) ev.zonaPorteria = zonaPorteria;
    props.onConfirmar(ev);
  };

  const RESULTADOS: ("GOL" | "PARADA" | "POSTE" | "FUERA")[] = ["GOL", "PARADA", "POSTE", "FUERA"];
  const porterosPista = props.enPista.filter((n) =>
    ROSTER.find((j) => j.nombre === n)?.posicion === "PORTERO"
  );

  return (
    <ModalShell titulo="🎯 Penalti / 10 metros" onCerrar={props.onCerrar}>
      <Paso n={1} titulo="Tipo" activo={!tipo}>
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => setTipo("penalti")}
            className={`py-3 rounded font-bold ${tipo === "penalti" ? "bg-pink-700" : "bg-zinc-800"}`}>
            Penalti (6m)</button>
          <button onClick={() => setTipo("diezm")}
            className={`py-3 rounded font-bold ${tipo === "diezm" ? "bg-pink-700" : "bg-zinc-800"}`}>
            10 metros</button>
        </div>
      </Paso>

      {tipo && (
        <Paso n={2} titulo="¿A favor o en contra?" activo={!equipo}>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => setEquipo("INTER")}
              className={`py-3 rounded font-bold ${equipo === "INTER" ? "bg-emerald-700" : "bg-zinc-800"}`}>
              A FAVOR (lo tira Inter)</button>
            <button onClick={() => setEquipo("RIVAL")}
              className={`py-3 rounded font-bold ${equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"}`}>
              EN CONTRA (lo tira {props.rivalNombre})</button>
          </div>
        </Paso>
      )}

      {equipo === "INTER" && (
        <Paso n={3} titulo="Tirador nuestro (tap)" activo={!tirador}>
          <ChipsJugador opciones={props.enPista} seleccionado={tirador} onSelect={setTirador} />
          <input className="w-full bg-zinc-800 rounded px-3 py-2 mt-2 text-sm"
            placeholder="Portero rival (opcional)"
            value={porteroRival} onChange={(e) => setPorteroRival(e.target.value.toUpperCase())} />
        </Paso>
      )}

      {equipo === "RIVAL" && (
        <Paso n={3} titulo="Portero nuestro (tap)" activo={!porteroNuestro}>
          <ChipsJugador opciones={porterosPista} seleccionado={porteroNuestro} onSelect={setPorteroNuestro} />
          <input className="w-full bg-zinc-800 rounded px-3 py-2 mt-2 text-sm"
            placeholder="Tirador rival (texto, opcional)"
            value={tirador} onChange={(e) => setTirador(e.target.value.toUpperCase())} />
        </Paso>
      )}

      {equipo && ((equipo === "INTER" && tirador) || (equipo === "RIVAL" && porteroNuestro)) && (
        <Paso n={4} titulo="Resultado" activo={!resultado}>
          <div className="grid grid-cols-4 gap-2">
            {RESULTADOS.map((r) => (
              <button key={r} onClick={() => setResultado(r)}
                className={`py-3 rounded font-bold ${
                  resultado === r
                    ? (r === "GOL" ? "bg-green-700" : "bg-yellow-700")
                    : "bg-zinc-800"
                }`}>{r}</button>
            ))}
          </div>
        </Paso>
      )}

      {resultado && (
        <Paso n={5}
          titulo={resultado === "FUERA" ? "Zona portería (no aplica) — pulsa GUARDAR" : "Zona de portería (tap = guardar)"}
          activo>
          {resultado !== "FUERA" ? (
            <Porteria onSelect={(z) => aplicar(z)} />
          ) : null}
          <div className="mt-2 flex justify-end">
            <button onClick={() => aplicar(undefined)}
              className="px-4 py-2 bg-green-700 hover:bg-green-600 rounded font-bold">
              {resultado === "FUERA" ? "GUARDAR" : "Saltar zona y guardar"}
            </button>
          </div>
        </Paso>
      )}
    </ModalShell>
  );
}

// ──────────────── MODAL ACCIÓN INDIVIDUAL (tap en jugador) ────────────────

// Tipos de accion que requieren zona del campo
type AccionConZonaTipo = "pf" | "pnf" | "robos" | "cortes" | "bdg" | "bdp";

function ModalAccionIndividual(props: {
  jugador: string;
  enPista: string[];
  banquillo: string[];
  cfg: ConfigPartido; parteActual: ParteId;
  onCerrar: () => void;
  onCambio: (sale: string, entra: string) => void;
  onAmarilla: () => void;
  onRoja: () => void;
  onFalta: () => void;
  /** TODAS las acciones individuales con mapa: PF/PNF/Robo/Corte/BDG/BDP. */
  onAccionConZona: (tipo: AccionConZonaTipo, zonaCampo?: string) => void;
  onContador: (tipo: keyof ContadoresJugador) => void;
  onDisparo: (detalles: { resultado: ResultadoDisparo; zonaCampo: string; zonaPorteria: string }) => void;
}) {
  const [paso, setPaso] = useState<"menu" | "accionZona" | "disparoTipo" | "disparoCampo" | "disparoPorteria">("menu");
  const [disparoRes, setDisparoRes] = useState<ResultadoDisparo>("PUERTA");
  const [zonaCampo, setZonaCampo] = useState("");
  const [accionPendiente, setAccionPendiente] = useState<AccionConZonaTipo | null>(null);

  // Mapeo amigable acción → etiqueta + emoji
  const LBL_ACCION: Record<AccionConZonaTipo, string> = {
    pf:     "❌ Pérdida forzada",
    pnf:    "❌ Pérdida NO forzada",
    robos:  "🔁 Robo",
    cortes: "✂️ Corte",
    bdg:    "🥇 Bal. dividido ganado",
    bdp:    "🥈 Bal. dividido perdido",
  };

  // Pulsar una acción → ir a la pantalla del mapa para elegir zona.
  // Después se aplica la acción + zona.
  const irAAccionZona = (a: AccionConZonaTipo) => {
    setAccionPendiente(a);
    setPaso("accionZona");
  };

  if (paso === "menu") {
    return (
      <ModalShell titulo={`📊 ${props.jugador}`} onCerrar={props.onCerrar}>
        <p className="text-sm text-zinc-400 mb-3">
          Todas las acciones abren el mapa para situar la zona del campo.
        </p>
        <div className="grid grid-cols-3 gap-2 mb-4">
          <BotonGrande label="🔁 Robo"  onClick={() => irAAccionZona("robos")} />
          <BotonGrande label="✂️ Corte" onClick={() => irAAccionZona("cortes")} />
          <BotonGrande label="❌ PF"    subtitle="forzada" onClick={() => irAAccionZona("pf")} />
          <BotonGrande label="❌ PNF"   subtitle="no forzada" onClick={() => irAAccionZona("pnf")} />
          <BotonGrande label="🥇 BDG"   subtitle="dividido ganado" onClick={() => irAAccionZona("bdg")} />
          <BotonGrande label="🥈 BDP"   subtitle="dividido perdido" onClick={() => irAAccionZona("bdp")} />
        </div>
        <div className="grid grid-cols-1 gap-2 mb-2">
          <BotonGrande label="🎯 DISPARO" color="bg-pink-700" onClick={() => setPaso("disparoTipo")} />
        </div>

        {/* Disciplina: amarilla + roja + falta (cometida POR este jugador). */}
        <div className="grid grid-cols-3 gap-2">
          <BotonGrande label="🟨 Amarilla" color="bg-yellow-700" onClick={props.onAmarilla} />
          <BotonGrande label="🟥 Roja" color="bg-red-800" onClick={props.onRoja} />
          <BotonGrande label="⚠️ Falta" color="bg-orange-700" onClick={props.onFalta} />
        </div>

        {/* CAMBIO DIRECTO: tap en un jugador del banquillo y se hace el
            cambio inmediatamente (sin pasar por sub-menú). */}
        <div className="mt-4 pt-3 border-t border-zinc-800">
          <h3 className="text-sm font-semibold text-zinc-300 mb-2">
            🔄 Cambio rápido — toca al jugador de banquillo que entra:
          </h3>
          {props.banquillo.length === 0 ? (
            <p className="text-xs text-zinc-500">No hay jugadores en banquillo.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {props.banquillo.map((n) => (
                <button key={n}
                  onClick={() => props.onCambio(props.jugador, n)}
                  className="px-3 py-2 rounded bg-emerald-800 hover:bg-emerald-700 text-base font-bold">
                  ⤴ {n}
                </button>
              ))}
            </div>
          )}
          <p className="text-[11px] text-zinc-500 mt-2">
            Sale <strong>{props.jugador}</strong>, entra el que pulses.
          </p>
        </div>
      </ModalShell>
    );
  }

  if (paso === "accionZona" && accionPendiente) {
    return (
      <ModalShell titulo={`${LBL_ACCION[accionPendiente]} · ${props.jugador}`}
        onCerrar={props.onCerrar}>
        <Paso n={1} titulo="¿En qué zona del campo? (tap = guardar)" activo>
          <Campo
            onSelect={(z) => props.onAccionConZona(accionPendiente, z)}
            direccion={direccionAtaque(props.parteActual, "INTER", props.cfg)}
            nombreAtacante="Inter" />
          <div className="mt-2 flex justify-between">
            <button onClick={() => { setAccionPendiente(null); setPaso("menu"); }}
              className="px-4 py-2 bg-zinc-700 rounded">← Atrás</button>
            <button onClick={() => props.onAccionConZona(accionPendiente, undefined)}
              className="px-3 py-1 bg-zinc-700 hover:bg-zinc-600 rounded text-xs">
              Saltar zona y guardar
            </button>
          </div>
        </Paso>
      </ModalShell>
    );
  }

  if (paso === "disparoTipo") {
    return (
      <ModalShell titulo={`🎯 Disparo de ${props.jugador}`} onCerrar={props.onCerrar}>
        <Paso n={1} titulo="Resultado del disparo (tap)" activo>
          <div className="grid grid-cols-4 gap-2">
            {(["PUERTA", "PALO", "FUERA", "BLOQUEADO"] as ResultadoDisparo[]).map((r) => (
              <button key={r}
                onClick={() => { setDisparoRes(r); setPaso("disparoCampo"); }}
                className="py-4 rounded font-bold bg-pink-700 hover:bg-pink-600">{r}</button>
            ))}
          </div>
        </Paso>
        <button onClick={() => setPaso("menu")} className="px-4 py-2 bg-zinc-700 rounded">← Atrás</button>
      </ModalShell>
    );
  }

  if (paso === "disparoCampo") {
    return (
      <ModalShell titulo={`🎯 ${props.jugador} → ${disparoRes}`} onCerrar={props.onCerrar}>
        <Paso n={2} titulo="Zona del campo desde donde se dispara (tap)" activo>
          <Campo onSelect={(z) => {
            setZonaCampo(z);
            if (disparoRes === "PUERTA") setPaso("disparoPorteria");
            else props.onDisparo({ resultado: disparoRes, zonaCampo: z, zonaPorteria: "" });
          }}
          direccion={direccionAtaque(props.parteActual, "INTER", props.cfg)}
          nombreAtacante="Inter" />
          <div className="mt-2 flex justify-between">
            <button onClick={() => setPaso("disparoTipo")} className="px-4 py-2 bg-zinc-700 rounded">← Atrás</button>
            <button onClick={() => {
              if (disparoRes === "PUERTA") setPaso("disparoPorteria");
              else props.onDisparo({ resultado: disparoRes, zonaCampo: "", zonaPorteria: "" });
            }} className="px-4 py-2 bg-zinc-700 rounded text-xs">Saltar zona campo</button>
          </div>
        </Paso>
      </ModalShell>
    );
  }

  if (paso === "disparoPorteria") {
    return (
      <ModalShell titulo={`🎯 ${props.jugador} → PUERTA desde ${zonaCampo || "?"}`} onCerrar={props.onCerrar}>
        <Paso n={3} titulo="Zona de portería (tap = guardar)" activo>
          <Porteria onSelect={(z) =>
            props.onDisparo({ resultado: "PUERTA", zonaCampo, zonaPorteria: z })
          } />
          <div className="mt-2 flex justify-between">
            <button onClick={() => setPaso("disparoCampo")} className="px-4 py-2 bg-zinc-700 rounded">← Atrás</button>
            <button onClick={() =>
              props.onDisparo({ resultado: "PUERTA", zonaCampo, zonaPorteria: "" })
            } className="px-4 py-2 bg-zinc-700 rounded text-xs">Saltar zona portería</button>
          </div>
        </Paso>
      </ModalShell>
    );
  }

  return null;
}

function BotonGrande(props: { label: string; subtitle?: string; onClick: () => void; color?: string }) {
  return (
    <button onClick={props.onClick}
      className={`${props.color || "bg-zinc-700"} hover:opacity-90 py-4 rounded-xl font-bold flex flex-col items-center`}>
      <span className="text-base">{props.label}</span>
      {props.subtitle && <span className="text-xs opacity-70">{props.subtitle}</span>}
    </button>
  );
}

// ──────────────── MODAL TIEMPOS (resumen por jugador) ────────────────

function ModalTiempos(props: {
  partido: Partido;
  enPista: string[];
  segundosTurnoActual: (n: string) => number;
  onCerrar: () => void;
}) {
  const { partido, enPista } = props;
  if (!partido.config) return null;
  const partes: ParteId[] = ["1T", "2T", "PR1", "PR2"];
  // Filtramos solo las partes que se juegan (duración > 0)
  const partesActivas = partes.filter((p) => (partido.config!.duracionParte[p] ?? 0) > 0);

  // Para cada jugador: total (incluye live), por parte (incluye live de la parte actual).
  const filas = partido.config.convocados.map((nombre) => {
    const t = partido.tiempos[nombre];
    if (!t) return { nombre, total: 0, porParte: {} as Record<ParteId, number>, esPortero: false, enPista: false };
    const parteActual = partido.cronometro.parteActual;
    const enPistaAhora = enPista.includes(nombre);
    // Live: si está en pista con turnoStart, suma desde turnoStart.
    const liveExtra = (enPistaAhora && t.turnoStart != null && partido.cronometro.ultimoStart != null)
      ? (Date.now() - t.turnoStart) / 1000
      : 0;
    const porParte: Record<ParteId, number> = { ...t.porParte };
    if (liveExtra > 0) porParte[parteActual] = (porParte[parteActual] ?? 0) + liveExtra;
    const total = t.totalSegundos + liveExtra;
    const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
    return { nombre, total, porParte, esPortero, enPista: enPistaAhora };
  });
  // Orden: en pista primero, después por total descendente
  filas.sort((a, b) => {
    if (a.enPista !== b.enPista) return a.enPista ? -1 : 1;
    return b.total - a.total;
  });

  return (
    <ModalShell titulo="📊 Tiempo jugado por jugador" onCerrar={props.onCerrar}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-zinc-400 border-b border-zinc-800">
            <tr>
              <th className="text-left py-2 px-2">Jugador</th>
              <th className="text-right px-2">Total</th>
              {partesActivas.map((p) => (
                <th key={p} className="text-right px-2">{p}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
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
                {partesActivas.map((p) => (
                  <td key={p} className="text-right font-mono tabular-nums px-2 text-zinc-400">
                    {formatMMSS(f.porParte[p] ?? 0)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot className="text-xs text-zinc-500 border-t border-zinc-800">
            <tr>
              <td className="pt-2 px-2 italic">Total minutos jugados</td>
              <td className="text-right font-mono tabular-nums px-2 font-bold pt-2">
                {formatMMSS(filas.reduce((s, f) => s + f.total, 0))}
              </td>
              {partesActivas.map((p) => (
                <td key={p} className="text-right font-mono tabular-nums px-2 pt-2">
                  {formatMMSS(filas.reduce((s, f) => s + (f.porParte[p] ?? 0), 0))}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-xs text-zinc-500 mt-3">
        El valor de la parte actual incluye los segundos en vivo (se actualiza con el reloj).
        Los porteros marcados en amarillo.
      </p>
    </ModalShell>
  );
}

// ──────────────── MODAL TANDA DE PENALTIS ────────────────
// Flujo simple: lista de tiros + form para añadir el siguiente.
// Cada tiro: equipo → tirador (chips de convocados / texto rival) → portero
// → resultado → (si gol o parada/poste) zona portería = guardar.
// Marcador de la tanda se actualiza solo.

function ModalTanda(props: {
  tanda: TandaPenaltis;
  enPista: string[];
  convocados: string[];
  rivalNombre: string;
  onCerrar: () => void;
  onApuntar: (tiro: Omit<TiroTanda, "id" | "orden" | "timestampReal">) => void;
  onDeshacer: () => void;
}) {
  // Estado del formulario para el siguiente tiro
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL" | null>(null);
  const [tirador, setTirador] = useState("");
  const [portero, setPortero] = useState("");
  const [resultado, setResultado] = useState<"GOL" | "PARADA" | "POSTE" | "FUERA" | null>(null);

  const reset = () => { setEquipo(null); setTirador(""); setPortero(""); setResultado(null); };

  const aplicar = (zonaPorteria?: string) => {
    if (!equipo || !resultado) return;
    props.onApuntar({
      equipo,
      tirador: tirador || undefined,
      portero: portero || undefined,
      resultado,
      zonaPorteria: zonaPorteria,
    });
    reset();
  };

  const porterosNuestros = props.convocados.filter((n) =>
    ROSTER.find((j) => j.nombre === n)?.posicion === "PORTERO"
  );

  return (
    <ModalShell titulo={`🥇 Tanda de penaltis · ${props.tanda.marcador.inter} - ${props.tanda.marcador.rival}`}
      onCerrar={props.onCerrar}>

      {/* Historial de tiros */}
      <div className="mb-4 bg-zinc-950 rounded p-3 max-h-48 overflow-y-auto">
        <h3 className="text-sm text-zinc-400 mb-2">Tiros realizados ({props.tanda.tiros.length})</h3>
        {props.tanda.tiros.length === 0 && <p className="text-xs text-zinc-600">— ninguno aún —</p>}
        <ol className="text-sm space-y-1">
          {props.tanda.tiros.map((t) => (
            <li key={t.id} className="flex justify-between items-center">
              <span>
                <span className="text-zinc-500 text-xs">#{t.orden}</span>{" "}
                <span className={t.equipo === "INTER" ? "text-emerald-400" : "text-red-400"}>
                  {t.equipo === "INTER" ? "INTER" : props.rivalNombre}
                </span>
                {" · "}
                <span className="font-bold">{t.tirador || "—"}</span>
                {" → "}
                <span className={t.resultado === "GOL" ? "text-green-400 font-bold" : "text-yellow-400"}>{t.resultado}</span>
                {t.zonaPorteria && <span className="text-zinc-500 text-xs"> ({t.zonaPorteria})</span>}
              </span>
            </li>
          ))}
        </ol>
        {props.tanda.tiros.length > 0 && (
          <button onClick={props.onDeshacer}
            className="mt-2 text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 rounded">
            ↶ Deshacer último tiro
          </button>
        )}
      </div>

      {/* Form: siguiente tiro */}
      <div className="border-t border-zinc-800 pt-3">
        <h3 className="text-sm font-bold text-zinc-300 mb-2">Apuntar tiro #{props.tanda.tiros.length + 1}</h3>

        <Paso n={1} titulo="¿Quién lanza?" activo={!equipo}>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => setEquipo("INTER")}
              className={`py-3 rounded font-bold ${equipo === "INTER" ? "bg-emerald-700" : "bg-zinc-800"}`}>
              INTER</button>
            <button onClick={() => setEquipo("RIVAL")}
              className={`py-3 rounded font-bold ${equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"}`}>
              {props.rivalNombre}</button>
          </div>
        </Paso>

        {equipo === "INTER" && (
          <Paso n={2} titulo="Tirador (tap)" activo={!tirador}>
            <ChipsJugador opciones={props.convocados} seleccionado={tirador} onSelect={setTirador} />
          </Paso>
        )}
        {equipo === "RIVAL" && (
          <Paso n={2} titulo="Portero nuestro (tap)" activo={!portero}>
            <ChipsJugador opciones={porterosNuestros} seleccionado={portero} onSelect={setPortero} />
            <input className="w-full bg-zinc-800 rounded px-3 py-2 mt-2 text-sm"
              placeholder="Tirador rival (texto, opcional)"
              value={tirador} onChange={(e) => setTirador(e.target.value.toUpperCase())} />
          </Paso>
        )}

        {equipo && ((equipo === "INTER" && tirador) || (equipo === "RIVAL" && portero)) && (
          <Paso n={3} titulo="Resultado" activo={!resultado}>
            <div className="grid grid-cols-4 gap-2">
              {(["GOL", "PARADA", "POSTE", "FUERA"] as const).map((r) => (
                <button key={r} onClick={() => setResultado(r)}
                  className={`py-3 rounded font-bold ${
                    resultado === r
                      ? (r === "GOL" ? "bg-green-700" : "bg-yellow-700")
                      : "bg-zinc-800"
                  }`}>{r}</button>
              ))}
            </div>
          </Paso>
        )}

        {resultado && (
          <Paso n={4} titulo={resultado === "FUERA" ? "Guardar (FUERA)" : "Zona portería (tap = guardar)"} activo>
            {resultado !== "FUERA" ? (
              <Porteria onSelect={(z) => aplicar(z)} />
            ) : null}
            <div className="mt-2 flex justify-end gap-2">
              <button onClick={reset}
                className="px-3 py-1 bg-zinc-700 rounded text-xs">Reiniciar</button>
              <button onClick={() => aplicar(undefined)}
                className="px-4 py-2 bg-green-700 hover:bg-green-600 rounded font-bold">
                {resultado === "FUERA" ? "GUARDAR" : "Saltar zona y guardar"}
              </button>
            </div>
          </Paso>
        )}
      </div>

      <div className="mt-4 flex justify-end gap-2 border-t border-zinc-800 pt-3">
        <button onClick={props.onCerrar}
          className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded">Cerrar tanda</button>
      </div>
    </ModalShell>
  );
}

// ──────────────── MODAL CAMBIO DE PARTE / DESCANSO / FIN ────────────────
//
// Lógica según la parte de la que veníamos:
//   - 1T → modal "Descanso de 1ª parte" con resumen + botón "Empezar 2ª".
//   - 2T → modal "Final de 2ª parte" con 3 opciones:
//          - Hay prórroga (config minutos) → setDuracionesParte + avanzar a PR1.
//          - Tanda de penaltis directos → abrir tanda.
//          - Finalizar partido → ir a /resumen.
//   - PR1 → "Descanso de prórroga" con resumen + botón "Empezar PR2".
//   - PR2 → "Final de prórroga" con 2 opciones (tanda / finalizar).

function ModalCambioParte(props: {
  partido: Partido;
  desde: ParteId;
  onCerrar: () => void;
  onContinuarSiguienteParte: () => void;
  onConfigurarProrroga: (minutos: number) => void;
  onIrATanda: () => void;
  onFinalizar: () => void;
}) {
  const { partido, desde } = props;
  const cfg = partido.config!;
  const [minProrroga, setMinProrroga] = useState(5);

  const TITULOS: Record<ParteId, string> = {
    "1T": "🔵 Final de 1ª parte",
    "2T": "🏁 Final del partido (2ª parte)",
    PR1: "🟣 Final de prórroga 1",
    PR2: "🏁 Final de prórroga 2",
  };

  // Empate? Útil para 2T y PR2.
  const empate = partido.marcador.inter === partido.marcador.rival;

  // Resumen rápido por jugador (tiempo en la parte que acaba)
  const filasTiempos = cfg.convocados
    .map((nombre) => {
      const t = partido.tiempos[nombre];
      if (!t) return null;
      const totalParte = (t.porParte?.[desde] ?? 0);
      const total = t.totalSegundos ?? 0;
      const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
      const c = partido.acciones.porJugador[nombre];
      return { nombre, totalParte, total, esPortero, c };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null && (x.totalParte > 0 || x.total > 0))
    .sort((a, b) => b.totalParte - a.totalParte);

  // Totales de equipo (acumulados a TODO el partido, no solo a esta parte)
  const tot = cfg.convocados.reduce((acc, n) => {
    const c = partido.acciones.porJugador[n];
    if (!c) return acc;
    return {
      dpp: acc.dpp + (c.dpp || 0),
      dpa: acc.dpa + (c.dpa || 0),
      dpf: acc.dpf + (c.dpf || 0),
      dpb: acc.dpb + (c.dpb || 0),
      pf: acc.pf + (c.pf || 0),
      pnf: acc.pnf + (c.pnf || 0),
      robos: acc.robos + (c.robos || 0),
      cortes: acc.cortes + (c.cortes || 0),
      bdg: acc.bdg + (c.bdg || 0),
      bdp: acc.bdp + (c.bdp || 0),
    };
  }, { dpp:0,dpa:0,dpf:0,dpb:0,pf:0,pnf:0,robos:0,cortes:0,bdg:0,bdp:0 });

  const totalDispINTER = tot.dpp + tot.dpa + tot.dpf + tot.dpb;
  const r = partido.disparosRival;
  const totalDispRIVAL = r.puerta + r.palo + r.fuera + r.bloqueado;

  // ¿Mostramos opciones de final (2T o PR2)?
  const esFinal2T = desde === "2T";
  const esFinalPR2 = desde === "PR2";
  const esFinalParte = esFinal2T || esFinalPR2;

  return (
    <ModalShell titulo={TITULOS[desde]} onCerrar={props.onCerrar}>

      {/* Marcador actual + estado */}
      <div className="text-center bg-zinc-950 rounded-lg p-5 mb-4">
        <div className="text-5xl font-bold tabular-nums">
          <span className="text-emerald-400">INTER {partido.marcador.inter}</span>
          <span className="text-zinc-500 mx-2">-</span>
          <span className="text-red-400">{partido.marcador.rival} {cfg.rival}</span>
        </div>
        {esFinalParte && empate && (
          <div className="text-yellow-400 text-base mt-2">
            ⚠️ Empate · hay que decidir cómo seguir
          </div>
        )}
      </div>

      {/* ATAJO arriba — botón principal de avance bien visible.
          Para 1T = empezar 2T, PR1 = empezar PR2. En 2T y PR2 no hay
          un único atajo (hay 3 opciones), así que solo aparece para
          1T/PR1. Las opciones de 2T/PR2 siguen abajo. */}
      {(desde === "1T" || desde === "PR1") && (
        <button onClick={props.onContinuarSiguienteParte}
          className="w-full py-6 mb-4 bg-green-700 hover:bg-green-600 rounded-xl text-3xl font-bold">
          ▶ {desde === "1T" ? "Empezar 2ª parte" : "Empezar prórroga 2"}
        </button>
      )}

      {/* DISPAROS — destacado, grande y con énfasis */}
      <div className="bg-zinc-900 rounded-lg p-4 mb-4">
        <h3 className="text-lg font-bold text-zinc-200 mb-3">🎯 Disparos</h3>
        <div className="grid grid-cols-2 gap-3">
          {/* INTER */}
          <div className="bg-emerald-900/40 rounded-lg p-4 border border-emerald-700/40">
            <div className="text-base text-emerald-300 font-bold mb-2 uppercase tracking-wide">INTER</div>
            <div className="flex items-baseline gap-2">
              <span className="text-5xl font-bold text-white tabular-nums">{totalDispINTER}</span>
              <span className="text-sm text-emerald-300">total</span>
            </div>
            <div className="mt-3 grid grid-cols-4 gap-1 text-center">
              <div className="bg-emerald-800/40 rounded py-1.5">
                <div className="text-xl font-bold tabular-nums">{tot.dpp}</div>
                <div className="text-xs text-emerald-200 uppercase">Puerta</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1.5">
                <div className="text-xl font-bold tabular-nums">{tot.dpa}</div>
                <div className="text-xs text-zinc-400 uppercase">Palo</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1.5">
                <div className="text-xl font-bold tabular-nums">{tot.dpf}</div>
                <div className="text-xs text-zinc-400 uppercase">Fuera</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1.5">
                <div className="text-xl font-bold tabular-nums">{tot.dpb}</div>
                <div className="text-xs text-zinc-400 uppercase">Bloq.</div>
              </div>
            </div>
          </div>
          {/* RIVAL */}
          <div className="bg-red-900/40 rounded-lg p-4 border border-red-700/40">
            <div className="text-base text-red-300 font-bold mb-2 uppercase tracking-wide">{cfg.rival}</div>
            <div className="flex items-baseline gap-2">
              <span className="text-5xl font-bold text-white tabular-nums">{totalDispRIVAL}</span>
              <span className="text-sm text-red-300">total</span>
            </div>
            <div className="mt-3 grid grid-cols-4 gap-1 text-center">
              <div className="bg-red-800/40 rounded py-1.5">
                <div className="text-xl font-bold tabular-nums">{r.puerta}</div>
                <div className="text-xs text-red-200 uppercase">Puerta</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1.5">
                <div className="text-xl font-bold tabular-nums">{r.palo}</div>
                <div className="text-xs text-zinc-400 uppercase">Palo</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1.5">
                <div className="text-xl font-bold tabular-nums">{r.fuera}</div>
                <div className="text-xs text-zinc-400 uppercase">Fuera</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1.5">
                <div className="text-xl font-bold tabular-nums">{r.bloqueado}</div>
                <div className="text-xs text-zinc-400 uppercase">Bloq.</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* OTROS STATS DEL EQUIPO — Pérdidas / Recuperaciones / Balones divididos */}
      <div className="grid grid-cols-3 gap-3 text-sm mb-4">
        <div className="bg-red-900/20 rounded-lg p-3 border border-red-700/20">
          <div className="text-red-300 font-bold mb-2 text-base">❌ Pérdidas</div>
          <div className="flex justify-between"><span>Forzada</span><strong>{tot.pf}</strong></div>
          <div className="flex justify-between"><span>No forzada</span><strong>{tot.pnf}</strong></div>
          <div className="border-t border-red-700/40 mt-2 pt-2 flex justify-between text-red-200 text-base">
            <span>Total</span><strong>{tot.pf + tot.pnf}</strong>
          </div>
        </div>
        <div className="bg-green-900/20 rounded-lg p-3 border border-green-700/20">
          <div className="text-green-300 font-bold mb-2 text-base">✅ Recuperaciones</div>
          <div className="flex justify-between"><span>Robos</span><strong>{tot.robos}</strong></div>
          <div className="flex justify-between"><span>Cortes</span><strong>{tot.cortes}</strong></div>
          <div className="border-t border-green-700/40 mt-2 pt-2 flex justify-between text-green-200 text-base">
            <span>Total</span><strong>{tot.robos + tot.cortes}</strong>
          </div>
        </div>
        <div className="bg-purple-900/20 rounded-lg p-3 border border-purple-700/20">
          <div className="text-purple-300 font-bold mb-2 text-base">⚖️ Balones divididos</div>
          <div className="flex justify-between"><span>Ganados</span><strong>{tot.bdg}</strong></div>
          <div className="flex justify-between"><span>No ganados</span><strong>{tot.bdp}</strong></div>
          <div className="border-t border-purple-700/40 mt-2 pt-2 flex justify-between text-purple-200 text-base">
            <span>Ratio</span>
            <strong>{(tot.bdg + tot.bdp) > 0
              ? `${Math.round(tot.bdg / (tot.bdg + tot.bdp) * 100)}%`
              : "—"}</strong>
          </div>
        </div>
      </div>

      {/* TIEMPOS POR JUGADOR */}
      <div className="bg-zinc-900 rounded-lg p-4 mb-4">
        <h3 className="text-base font-bold text-zinc-300 mb-3">
          ⏱ Tiempos por jugador ({desde})
        </h3>
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-base">
            <thead className="text-sm text-zinc-500 border-b border-zinc-800">
              <tr>
                <th className="text-left py-2 px-2">Jugador</th>
                <th className="text-right px-2">{desde}</th>
                <th className="text-right px-2">Total partido</th>
              </tr>
            </thead>
            <tbody>
              {filasTiempos.map((f) => (
                <tr key={f.nombre} className="border-b border-zinc-900">
                  <td className={`py-1.5 px-2 ${f.esPortero ? "text-yellow-400" : ""} font-bold`}>
                    {f.nombre}{f.esPortero ? " 🥅" : ""}
                  </td>
                  <td className="text-right font-mono tabular-nums px-2 font-bold">{formatMMSS(f.totalParte)}</td>
                  <td className="text-right font-mono tabular-nums px-2 text-zinc-400">{formatMMSS(f.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* INDIVIDUAL — solo top scorers de cada categoría para no saturar */}
      <div className="bg-zinc-900 rounded-lg p-4 mb-4">
        <h3 className="text-base font-bold text-zinc-300 mb-3">👤 Acciones individuales (jugadores con stats)</h3>
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-zinc-500 border-b border-zinc-800">
              <tr>
                <th className="text-left py-2 px-2">Jugador</th>
                <th className="text-right px-2 text-emerald-300">Disp</th>
                <th className="text-right px-2 text-red-300">Pérd</th>
                <th className="text-right px-2 text-green-300">Recup</th>
                <th className="text-right px-2 text-purple-300">Divid</th>
              </tr>
            </thead>
            <tbody>
              {filasTiempos
                .filter((f) => f.c && (
                  (f.c.dpp || 0) + (f.c.dpa || 0) + (f.c.dpf || 0) + (f.c.dpb || 0) +
                  (f.c.pf || 0) + (f.c.pnf || 0) + (f.c.robos || 0) + (f.c.cortes || 0) +
                  (f.c.bdg || 0) + (f.c.bdp || 0) > 0
                ))
                .map((f) => {
                  const c = f.c!;
                  const disp = (c.dpp||0)+(c.dpa||0)+(c.dpf||0)+(c.dpb||0);
                  const perd = (c.pf||0)+(c.pnf||0);
                  const rec = (c.robos||0)+(c.cortes||0);
                  const div = (c.bdg||0)+(c.bdp||0);
                  return (
                    <tr key={f.nombre} className="border-b border-zinc-900">
                      <td className={`py-1.5 px-2 ${f.esPortero ? "text-yellow-400" : ""} font-bold`}>{f.nombre}</td>
                      <td className="text-right font-mono px-2">{disp}</td>
                      <td className="text-right font-mono px-2">{perd}</td>
                      <td className="text-right font-mono px-2">{rec}</td>
                      <td className="text-right font-mono px-2">{div}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ACCIONES SEGÚN PARTE */}
      <div className="border-t border-zinc-800 pt-4">

        {/* 1T y PR1 ya tienen el botón principal arriba (atajo visible).
            No lo duplicamos aquí abajo. */}

        {/* 2T → tres opciones (prórroga / penaltis / finalizar) */}
        {esFinal2T && (
          <div className="space-y-3">
            <h3 className="text-base font-bold text-zinc-300">¿Cómo seguimos?</h3>

            {/* Prórroga */}
            <div className="bg-zinc-800 rounded-lg p-4">
              <div className="flex items-center gap-3 mb-3">
                <label className="text-base font-semibold">🟣 Hay prórroga de</label>
                <input type="number" min={1} max={20} value={minProrroga}
                  onChange={(e) => setMinProrroga(Number(e.target.value) || 5)}
                  className="w-16 bg-zinc-950 rounded px-2 py-1 text-center text-base" />
                <span className="text-base">min cada parte</span>
              </div>
              <button onClick={() => props.onConfigurarProrroga(minProrroga)}
                className="w-full py-4 bg-purple-700 hover:bg-purple-600 rounded-lg text-lg font-bold">
                ▶ Empezar prórroga ({minProrroga}+{minProrroga} min)
              </button>
            </div>

            {/* Tanda directa (sin prórroga) — solo si la competición la permite */}
            {cfg.permiteTanda && (
              <button onClick={props.onIrATanda}
                className="w-full py-4 bg-pink-700 hover:bg-pink-600 rounded-lg text-lg font-bold">
                🥇 Pasar directo a tanda de penaltis
              </button>
            )}

            {/* Finalizar */}
            <button onClick={props.onFinalizar}
              className="w-full py-4 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-lg font-bold">
              🏁 Finalizar partido y ver resumen
            </button>
          </div>
        )}

        {/* PR2 → tanda o finalizar */}
        {esFinalPR2 && (
          <div className="space-y-3">
            <h3 className="text-base font-bold text-zinc-300">¿Cómo seguimos?</h3>
            {cfg.permiteTanda && (
              <button onClick={props.onIrATanda}
                className="w-full py-4 bg-pink-700 hover:bg-pink-600 rounded-lg text-lg font-bold">
                🥇 Tanda de penaltis
              </button>
            )}
            <button onClick={props.onFinalizar}
              className="w-full py-4 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-lg font-bold">
              🏁 Finalizar partido y ver resumen
            </button>
          </div>
        )}
      </div>
    </ModalShell>
  );
}

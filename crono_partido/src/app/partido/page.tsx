"use client";

import { useState, useMemo, useEffect } from "react";
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
  const [modalFalta, setModalFalta] = useState(false);
  const [modalGol, setModalGol] = useState(false);
  const [modalAmarilla, setModalAmarilla] = useState(false);
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

  if (!cargado) {
    return <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">Cargando…</div>;
  }
  if (partido.estado !== "en_curso" || !partido.config) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center gap-4">
        <p className="text-xl">No hay partido en curso.</p>
        <button onClick={() => router.push("/nuevo")}
          className="px-6 py-3 bg-blue-700 rounded-xl text-lg font-bold">
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
          <span className="text-blue-400">INTER {partido.marcador.inter}</span>
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

      <div className="grid grid-cols-[1fr_320px] gap-3 mb-3">
        {/* EN PISTA — tap abre acciones individuales */}
        <div className="bg-zinc-900 rounded-xl p-3">
          <h2 className="text-zinc-400 text-sm mb-2">EN PISTA (toca un jugador para apuntar acciones)</h2>
          <div className="grid grid-cols-5 gap-2">
            {enPista.map((nombre) => {
              const seg = segundosTurnoActual(nombre);
              const totalParte = segundosEnParte(nombre, p);
              const dorsal = ROSTER.find((j) => j.nombre === nombre)?.dorsal || "";
              const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
              const tieneAmarilla = jugadoresAmarilla.has(nombre);
              return (
                <button key={nombre}
                  onClick={() => setModalAccionInd({ jugador: nombre })}
                  className={`relative p-3 rounded-lg text-center ${
                    esPortero
                      ? "bg-zinc-800 border-2 border-zinc-600"  // portero neutro, sin código de color de minutos
                      : colorTiempoPista(seg)
                  } ${tieneAmarilla ? "ring-2 ring-yellow-400 ring-offset-2 ring-offset-zinc-900" : ""}`}>
                  {tieneAmarilla && (
                    <span className="absolute top-1 right-1 text-base leading-none" title="Amarilla">🟨</span>
                  )}
                  {esPortero && (
                    <span className="absolute top-1 left-1 text-xs">🥅</span>
                  )}
                  <div className="text-xs opacity-70">{dorsal ? `#${dorsal}` : "—"}</div>
                  <div className="text-base font-bold">{nombre}</div>
                  <div className="text-2xl font-mono tabular-nums mt-1">{formatMMSS(seg)}</div>
                  <div className="text-xs opacity-70 mt-0.5">parte {formatMMSS(totalParte)}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* STATS por parte */}
        <div className="bg-zinc-900 rounded-xl p-3">
          <h2 className="text-zinc-400 text-sm mb-2">STATS {p}</h2>
          <table className="w-full text-base">
            <thead className="text-xs text-zinc-500">
              <tr><th></th><th className="text-blue-400">INTER</th><th className="text-red-400">RIVAL</th></tr>
            </thead>
            <tbody>
              <tr><td className="py-1">Faltas</td><td className="text-center text-xl font-bold">{sFalt.inter}</td><td className="text-center text-xl font-bold">{sFalt.rival}</td></tr>
              <tr><td className="py-1">Amarillas</td><td className="text-center text-xl font-bold">{sAma.inter}</td><td className="text-center text-xl font-bold">{sAma.rival}</td></tr>
              <tr><td className="py-1">T. muertos</td><td className="text-center text-xl font-bold">{sTM.inter}</td><td className="text-center text-xl font-bold">{sTM.rival}</td></tr>
              <tr className="border-t border-zinc-800">
                <td className="py-1 text-xs text-zinc-500">Dispar. rival</td>
                <td></td>
                <td className="text-center text-sm">
                  {partido.disparosRival.puerta}p / {partido.disparosRival.fuera}f
                </td>
              </tr>
            </tbody>
          </table>
          {sFalt.inter >= 6 && (
            <div className="mt-2 p-2 bg-red-700 rounded text-sm font-bold text-center">⚠️ Inter 6ª falta → 10m rival</div>
          )}
          {sFalt.rival >= 6 && (
            <div className="mt-2 p-2 bg-green-700 rounded text-sm font-bold text-center">⚠️ Rival 6ª falta → 10m a favor</div>
          )}
        </div>
      </div>

      {/* BANQUILLO */}
      <div className="bg-zinc-900 rounded-xl p-3 mb-3">
        <h2 className="text-zinc-400 text-sm mb-2">BANQUILLO</h2>
        <div className="grid grid-cols-6 gap-2">
          {banquillo.map((nombre) => {
            const seg = segundosBanquillo(nombre);
            const dorsal = ROSTER.find((j) => j.nombre === nombre)?.dorsal || "";
            const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
            const tieneAmarilla = jugadoresAmarilla.has(nombre);
            return (
              <div key={nombre}
                className={`relative p-2 rounded-lg text-center ${
                  esPortero
                    ? "bg-zinc-800 border border-zinc-600"   // portero neutro
                    : colorTiempoBanquillo(seg)
                } ${tieneAmarilla ? "ring-2 ring-yellow-400 ring-offset-1 ring-offset-zinc-900" : ""}`}>
                {tieneAmarilla && (
                  <span className="absolute top-0.5 right-0.5 text-sm leading-none">🟨</span>
                )}
                <div className="text-xs opacity-70">{dorsal ? `#${dorsal}` : "—"}</div>
                <div className="text-sm font-bold">{nombre}</div>
                <div className="text-base font-mono tabular-nums mt-1">{formatMMSS(seg)}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* BOTONES ACCIÓN COLECTIVA */}
      <div className="grid grid-cols-7 gap-2">
        <BotonAccion label="⚽ GOL" color="bg-blue-700" onClick={() => setModalGol(true)} />
        <BotonAccion label="🎯 DISP. RIVAL" color="bg-red-700" onClick={() => setModalDisparoRival(true)} />
        <BotonAccion label="⚠️ FALTA" color="bg-orange-700" onClick={() => setModalFalta(true)} />
        <BotonAccion label="🟨 AMARILLA" color="bg-yellow-700" onClick={() => setModalAmarilla(true)} />
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
          className="py-3 bg-blue-700 hover:bg-blue-600 rounded-lg text-sm font-bold">
          🏁 RESUMEN
        </button>
        <button onClick={() => router.push("/")}
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
          🏠 Inicio
        </button>
      </div>

      {modalCambio && (
        <ModalCambio
          enPista={enPista}
          banquillo={banquillo}
          saleInicial={modalCambio.sale}
          onCerrar={() => setModalCambio(null)}
          onConfirmar={(sale, entra) => {
            cambiarJugador(sale, entra);
            setModalCambio(null);
          }}
        />
      )}

      {modalAccionInd && (
        <ModalAccionIndividual
          jugador={modalAccionInd.jugador}
          enPista={enPista}
          banquillo={banquillo}
          cfg={cfg}
          parteActual={p}
          onCerrar={() => setModalAccionInd(null)}
          onCambio={(sale, entra) => {
            cambiarJugador(sale, entra);
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
          enPista={enPista}
          banquillo={banquillo}
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
          enPista={enPista}
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
          enPista={enPista}
          banquillo={banquillo}
          rivalNombre={cfg.rival}
          onCerrar={() => setModalAmarilla(false)}
          onConfirmar={(ev) => { registrarEvento(ev as any); setModalAmarilla(false); }}
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
          enPista={enPista}
          rivalNombre={cfg.rival}
          onCerrar={() => setModalPen(false)}
          onConfirmar={(ev) => { registrarEvento(ev as any); setModalPen(false); }}
        />
      )}

      {modalDisparoRival && (
        <ModalDisparoRival
          enPista={enPista}
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
          enPista={enPista}
          convocados={cfg.convocados}
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
      className={`${props.color} hover:opacity-90 py-5 rounded-xl text-lg font-bold`}>
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
            props.seleccionado === n ? "bg-blue-700 text-white" : "bg-zinc-800 text-zinc-200"
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
                className="px-4 py-3 bg-blue-700 hover:bg-blue-600 rounded text-base font-bold">
                {n}
              </button>
            ))}
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
              equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"
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
                    jugador === n ? "bg-blue-700"
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
  banquillo: string[];     // tambien admitidos
  rivalNombre: string;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL" | null>(null);

  const aplicar = (jugador?: string) => {
    const ev: any = { tipo: "amarilla", equipo };
    if (jugador) ev.jugador = jugador;
    props.onConfirmar(ev);
  };

  const candidatos = [...props.enPista, ...props.banquillo];

  return (
    <ModalShell titulo="🟨 Tarjeta amarilla" onCerrar={props.onCerrar} maxW="max-w-2xl">
      <Paso n={1} titulo="Equipo" activo={!equipo}>
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => setEquipo("INTER")}
            className={`py-4 rounded text-lg font-bold ${
              equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"
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
                <button key={n} onClick={() => aplicar(n)}
                  className={`px-3 py-2 rounded ${
                    enBanquillo ? "bg-zinc-700 hover:bg-zinc-600 opacity-80"
                                : "bg-blue-700 hover:bg-blue-600"
                  }`}
                  title={enBanquillo ? "Jugador en banquillo" : undefined}>
                  {n}{enBanquillo ? " 🪑" : ""}
                </button>
              );
            })}
            <button onClick={() => aplicar(undefined)}
              className="px-3 py-2 rounded bg-zinc-700">SIN ASIGNAR</button>
          </div>
        </Paso>
      )}
      {equipo === "RIVAL" && (
        <Paso n={2} titulo="Confirmar amarilla a rival" activo>
          <button onClick={() => aplicar(undefined)}
            className="w-full py-4 rounded bg-red-700 hover:bg-red-600 font-bold">Aplicar</button>
        </Paso>
      )}
    </ModalShell>
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
          className="py-6 bg-blue-700 hover:bg-blue-600 rounded text-xl font-bold">INTER</button>
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
              equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"
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
                      asistente === n ? "bg-blue-700" : "bg-zinc-800"
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
                  accion === a ? "bg-blue-700" : "bg-zinc-800"
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

  const aplicar = () => {
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
          <div className="mt-3 flex justify-end gap-2">
            <button onClick={aplicar}
              className="px-4 py-2 bg-green-700 hover:bg-green-600 rounded font-bold">
              ✅ Guardar parada
            </button>
          </div>
        </Paso>
      )}

      {/* Para PALO / FUERA / BLOQUEADO, no hace falta zona portería; botón directo */}
      {resultado && resultado !== "PUERTA" && zonaCampo && (
        <div className="mt-3 flex justify-end">
          <button onClick={aplicar}
            className="px-4 py-2 bg-green-700 hover:bg-green-600 rounded font-bold">
            ✅ Guardar {resultado.toLowerCase()}
          </button>
        </div>
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
              className={`py-3 rounded font-bold ${equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"}`}>
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
        <div className="grid grid-cols-1 gap-2">
          <BotonGrande label="🎯 DISPARO" color="bg-pink-700" onClick={() => setPaso("disparoTipo")} />
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
                  className="px-3 py-2 rounded bg-blue-800 hover:bg-blue-700 text-base font-bold">
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
                <span className={t.equipo === "INTER" ? "text-blue-400" : "text-red-400"}>
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
              className={`py-3 rounded font-bold ${equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"}`}>
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
      <div className="text-center bg-zinc-950 rounded-lg p-3 mb-4">
        <div className="text-3xl font-bold tabular-nums">
          <span className="text-blue-400">INTER {partido.marcador.inter}</span>
          <span className="text-zinc-500 mx-2">-</span>
          <span className="text-red-400">{partido.marcador.rival} {cfg.rival}</span>
        </div>
        {esFinalParte && empate && (
          <div className="text-yellow-400 text-xs mt-1">
            ⚠️ Empate · hay que decidir cómo seguir
          </div>
        )}
      </div>

      {/* DISPAROS — destacado, grande y con énfasis */}
      <div className="bg-zinc-900 rounded-lg p-4 mb-3">
        <h3 className="text-base font-bold text-zinc-200 mb-3">🎯 Disparos</h3>
        <div className="grid grid-cols-2 gap-3">
          {/* INTER */}
          <div className="bg-blue-900/40 rounded-lg p-3 border border-blue-700/40">
            <div className="text-sm text-blue-300 font-bold mb-2 uppercase tracking-wide">INTER</div>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-bold text-white tabular-nums">{totalDispINTER}</span>
              <span className="text-xs text-blue-300">total</span>
            </div>
            <div className="mt-3 grid grid-cols-4 gap-1 text-center">
              <div className="bg-blue-800/40 rounded py-1">
                <div className="text-lg font-bold tabular-nums">{tot.dpp}</div>
                <div className="text-[10px] text-blue-200 uppercase">Puerta</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1">
                <div className="text-lg font-bold tabular-nums">{tot.dpa}</div>
                <div className="text-[10px] text-zinc-400 uppercase">Palo</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1">
                <div className="text-lg font-bold tabular-nums">{tot.dpf}</div>
                <div className="text-[10px] text-zinc-400 uppercase">Fuera</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1">
                <div className="text-lg font-bold tabular-nums">{tot.dpb}</div>
                <div className="text-[10px] text-zinc-400 uppercase">Bloq.</div>
              </div>
            </div>
          </div>
          {/* RIVAL */}
          <div className="bg-red-900/40 rounded-lg p-3 border border-red-700/40">
            <div className="text-sm text-red-300 font-bold mb-2 uppercase tracking-wide">{cfg.rival}</div>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-bold text-white tabular-nums">{totalDispRIVAL}</span>
              <span className="text-xs text-red-300">total</span>
            </div>
            <div className="mt-3 grid grid-cols-4 gap-1 text-center">
              <div className="bg-red-800/40 rounded py-1">
                <div className="text-lg font-bold tabular-nums">{r.puerta}</div>
                <div className="text-[10px] text-red-200 uppercase">Puerta</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1">
                <div className="text-lg font-bold tabular-nums">{r.palo}</div>
                <div className="text-[10px] text-zinc-400 uppercase">Palo</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1">
                <div className="text-lg font-bold tabular-nums">{r.fuera}</div>
                <div className="text-[10px] text-zinc-400 uppercase">Fuera</div>
              </div>
              <div className="bg-zinc-800/60 rounded py-1">
                <div className="text-lg font-bold tabular-nums">{r.bloqueado}</div>
                <div className="text-[10px] text-zinc-400 uppercase">Bloq.</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* OTROS STATS DEL EQUIPO — Pérdidas / Recuperaciones / Balones divididos */}
      <div className="grid grid-cols-3 gap-3 text-xs mb-3">
        <div className="bg-red-900/20 rounded-lg p-3 border border-red-700/20">
          <div className="text-red-300 font-bold mb-2 text-sm">❌ Pérdidas</div>
          <div className="flex justify-between"><span>Forzada</span><strong>{tot.pf}</strong></div>
          <div className="flex justify-between"><span>No forzada</span><strong>{tot.pnf}</strong></div>
          <div className="border-t border-red-700/40 mt-1 pt-1 flex justify-between text-red-200">
            <span>Total</span><strong>{tot.pf + tot.pnf}</strong>
          </div>
        </div>
        <div className="bg-green-900/20 rounded-lg p-3 border border-green-700/20">
          <div className="text-green-300 font-bold mb-2 text-sm">✅ Recuperaciones</div>
          <div className="flex justify-between"><span>Robos</span><strong>{tot.robos}</strong></div>
          <div className="flex justify-between"><span>Cortes</span><strong>{tot.cortes}</strong></div>
          <div className="border-t border-green-700/40 mt-1 pt-1 flex justify-between text-green-200">
            <span>Total</span><strong>{tot.robos + tot.cortes}</strong>
          </div>
        </div>
        <div className="bg-purple-900/20 rounded-lg p-3 border border-purple-700/20">
          <div className="text-purple-300 font-bold mb-2 text-sm">⚖️ Balones divididos</div>
          <div className="flex justify-between"><span>Ganados</span><strong>{tot.bdg}</strong></div>
          <div className="flex justify-between"><span>No ganados</span><strong>{tot.bdp}</strong></div>
          <div className="border-t border-purple-700/40 mt-1 pt-1 flex justify-between text-purple-200">
            <span>Ratio</span>
            <strong>{(tot.bdg + tot.bdp) > 0
              ? `${Math.round(tot.bdg / (tot.bdg + tot.bdp) * 100)}%`
              : "—"}</strong>
          </div>
        </div>
      </div>

      {/* TIEMPOS POR JUGADOR */}
      <div className="bg-zinc-900 rounded-lg p-3 mb-3">
        <h3 className="text-xs font-bold text-zinc-300 mb-2">
          ⏱ Tiempos por jugador ({desde})
        </h3>
        <div className="max-h-60 overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="text-[10px] text-zinc-500 border-b border-zinc-800">
              <tr>
                <th className="text-left py-1">Jugador</th>
                <th className="text-right px-1">{desde}</th>
                <th className="text-right px-1">Total partido</th>
              </tr>
            </thead>
            <tbody>
              {filasTiempos.map((f) => (
                <tr key={f.nombre} className="border-b border-zinc-900">
                  <td className={`py-1 ${f.esPortero ? "text-yellow-400" : ""} font-bold`}>
                    {f.nombre}{f.esPortero ? " 🥅" : ""}
                  </td>
                  <td className="text-right font-mono tabular-nums px-1">{formatMMSS(f.totalParte)}</td>
                  <td className="text-right font-mono tabular-nums px-1 text-zinc-400">{formatMMSS(f.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* INDIVIDUAL — solo top scorers de cada categoría para no saturar */}
      <div className="bg-zinc-900 rounded-lg p-3 mb-4">
        <h3 className="text-xs font-bold text-zinc-300 mb-2">👤 Acciones individuales (jugadores con stats)</h3>
        <div className="max-h-60 overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="text-[10px] text-zinc-500 border-b border-zinc-800">
              <tr>
                <th className="text-left py-1">Jugador</th>
                <th className="text-right px-1 text-blue-300">Disp</th>
                <th className="text-right px-1 text-red-300">Pérd</th>
                <th className="text-right px-1 text-green-300">Recup</th>
                <th className="text-right px-1 text-purple-300">Divid</th>
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
                      <td className={`py-1 ${f.esPortero ? "text-yellow-400" : ""} font-bold`}>{f.nombre}</td>
                      <td className="text-right font-mono px-1">{disp}</td>
                      <td className="text-right font-mono px-1">{perd}</td>
                      <td className="text-right font-mono px-1">{rec}</td>
                      <td className="text-right font-mono px-1">{div}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ACCIONES SEGÚN PARTE */}
      <div className="border-t border-zinc-800 pt-3">

        {/* 1T → solo botón continuar */}
        {desde === "1T" && (
          <div className="grid grid-cols-1 gap-2">
            <button onClick={props.onContinuarSiguienteParte}
              className="py-4 bg-green-700 hover:bg-green-600 rounded-lg text-lg font-bold">
              ▶ Empezar 2ª parte
            </button>
          </div>
        )}

        {/* PR1 → solo botón continuar a PR2 */}
        {desde === "PR1" && (
          <div className="grid grid-cols-1 gap-2">
            <button onClick={props.onContinuarSiguienteParte}
              className="py-4 bg-green-700 hover:bg-green-600 rounded-lg text-lg font-bold">
              ▶ Empezar prórroga 2
            </button>
          </div>
        )}

        {/* 2T → tres opciones (prórroga / penaltis / finalizar) */}
        {esFinal2T && (
          <div className="space-y-2">
            <h3 className="text-sm font-bold text-zinc-300">¿Cómo seguimos?</h3>

            {/* Prórroga */}
            <div className="bg-zinc-800 rounded-lg p-3">
              <div className="flex items-center gap-3 mb-2">
                <label className="text-sm font-semibold">🟣 Hay prórroga de</label>
                <input type="number" min={1} max={20} value={minProrroga}
                  onChange={(e) => setMinProrroga(Number(e.target.value) || 5)}
                  className="w-16 bg-zinc-950 rounded px-2 py-1 text-center" />
                <span className="text-sm">min cada parte</span>
              </div>
              <button onClick={() => props.onConfigurarProrroga(minProrroga)}
                className="w-full py-3 bg-purple-700 hover:bg-purple-600 rounded font-bold">
                ▶ Empezar prórroga ({minProrroga}+{minProrroga} min)
              </button>
            </div>

            {/* Tanda directa (sin prórroga) — solo si la competición la permite */}
            {cfg.permiteTanda && (
              <button onClick={props.onIrATanda}
                className="w-full py-3 bg-pink-700 hover:bg-pink-600 rounded font-bold">
                🥇 Pasar directo a tanda de penaltis
              </button>
            )}

            {/* Finalizar */}
            <button onClick={props.onFinalizar}
              className="w-full py-3 bg-zinc-700 hover:bg-zinc-600 rounded font-bold">
              🏁 Finalizar partido y ver resumen
            </button>
          </div>
        )}

        {/* PR2 → tanda o finalizar */}
        {esFinalPR2 && (
          <div className="space-y-2">
            <h3 className="text-sm font-bold text-zinc-300">¿Cómo seguimos?</h3>
            {cfg.permiteTanda && (
              <button onClick={props.onIrATanda}
                className="w-full py-3 bg-pink-700 hover:bg-pink-600 rounded font-bold">
                🥇 Tanda de penaltis
              </button>
            )}
            <button onClick={props.onFinalizar}
              className="w-full py-3 bg-zinc-700 hover:bg-zinc-600 rounded font-bold">
              🏁 Finalizar partido y ver resumen
            </button>
          </div>
        )}
      </div>
    </ModalShell>
  );
}

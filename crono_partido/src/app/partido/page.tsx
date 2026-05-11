"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { usePartido } from "@/lib/store";
import { ROSTER } from "@/lib/roster";
import { formatMMSS, colorTiempoPista, colorTiempoBanquillo } from "@/lib/utils";

export default function PartidoPage() {
  const router = useRouter();
  const {
    partido, cargado,
    segundosTurnoActual, segundosBanquillo, segundosParte, segundosPartidoTotal,
    play, pausa, avanzarParte, cambiarJugador,
    registrarEvento, deshacerUltimoEvento,
  } = usePartido();

  const [modalCambio, setModalCambio] = useState<{ sale: string } | null>(null);
  const [modalAccion, setModalAccion] = useState<null | "gol" | "falta" | "amarilla" | "tm" | "pen">(null);

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
  const enPista = partido.enPista;
  const banquillo = cfg.convocados.filter((n) => !enPista.includes(n));

  // KPIs por equipo en la parte actual
  const p = partido.cronometro.parteActual;
  const sFalt = partido.stats.faltas[p];
  const sAma = partido.stats.amarillas[p];
  const sTM = partido.stats.tiemposMuerto[p];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-3">
      {/* Header: cronómetro grande + marcador */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="text-6xl font-mono font-bold tabular-nums">
            {formatMMSS(segParte)}
          </div>
          <div className="text-sm text-zinc-400 ml-2">
            <div>{p}</div>
            <div>tot {formatMMSS(segundosPartidoTotal())}</div>
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
          <button onClick={avanzarParte} className="px-3 py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">⏭ parte</button>
        </div>
      </div>

      <div className="grid grid-cols-[1fr_320px] gap-3 mb-3">
        {/* EN PISTA */}
        <div className="bg-zinc-900 rounded-xl p-3">
          <h2 className="text-zinc-400 text-sm mb-2">EN PISTA</h2>
          <div className="grid grid-cols-5 gap-2">
            {enPista.map((nombre) => {
              const seg = segundosTurnoActual(nombre);
              const totalParte = (partido.tiempos[nombre]?.porParte[p] || 0)
                + (corriendo && partido.tiempos[nombre]?.ultimaEntrada
                  ? (Date.now() - partido.tiempos[nombre].ultimaEntrada) / 1000
                  : 0);
              const dorsal = ROSTER.find((j) => j.nombre === nombre)?.dorsal || "";
              const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
              return (
                <button key={nombre}
                  onClick={() => setModalCambio({ sale: nombre })}
                  className={`p-3 rounded-lg text-center ${
                    esPortero ? "bg-yellow-700/40 border-2 border-yellow-500"
                              : colorTiempoPista(seg)
                  }`}>
                  <div className="text-xs opacity-70">{dorsal ? `#${dorsal}` : "—"}</div>
                  <div className="text-base font-bold">{nombre}</div>
                  <div className="text-2xl font-mono tabular-nums mt-1">{formatMMSS(seg)}</div>
                  <div className="text-xs opacity-70 mt-0.5">parte {formatMMSS(totalParte)}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* STATS por equipo */}
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
        <h2 className="text-zinc-400 text-sm mb-2">BANQUILLO (toca para meterlo)</h2>
        <div className="grid grid-cols-6 gap-2">
          {banquillo.map((nombre) => {
            const seg = segundosBanquillo(nombre);
            const dorsal = ROSTER.find((j) => j.nombre === nombre)?.dorsal || "";
            const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
            return (
              <button key={nombre}
                onClick={() => setModalCambio({ sale: "" /* placeholder */ })}
                className={`p-2 rounded-lg text-center ${
                  esPortero ? "bg-yellow-700/40 border border-yellow-500"
                            : colorTiempoBanquillo(seg)
                }`}>
                <div className="text-xs opacity-70">{dorsal ? `#${dorsal}` : "—"}</div>
                <div className="text-sm font-bold">{nombre}</div>
                <div className="text-base font-mono tabular-nums mt-1">{formatMMSS(seg)}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* BOTONES DE ACCIÓN */}
      <div className="grid grid-cols-6 gap-2">
        <BotonAccion label="⚽ GOL" color="bg-blue-700" onClick={() => setModalAccion("gol")} />
        <BotonAccion label="⚠️ FALTA" color="bg-orange-700" onClick={() => setModalAccion("falta")} />
        <BotonAccion label="🟨 AMARILLA" color="bg-yellow-700" onClick={() => setModalAccion("amarilla")} />
        <BotonAccion label="🔄 CAMBIO" color="bg-zinc-700" onClick={() => setModalCambio({ sale: "" })} />
        <BotonAccion label="🛑 T.M." color="bg-purple-700" onClick={() => setModalAccion("tm")} />
        <BotonAccion label="🎯 PEN/10M" color="bg-pink-700" onClick={() => setModalAccion("pen")} />
      </div>
      <div className="grid grid-cols-2 gap-2 mt-2">
        <button onClick={deshacerUltimoEvento}
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
          ↶ Deshacer último evento
        </button>
        <button onClick={() => router.push("/acciones")}
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
          📊 Acciones individuales
        </button>
      </div>

      {/* MODAL CAMBIO */}
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

      {/* MODAL ACCIONES RÁPIDAS (gol/falta/amarilla/tm/pen) */}
      {modalAccion && (
        <ModalAccion
          tipo={modalAccion}
          enPista={enPista}
          rival={cfg.rival}
          onCerrar={() => setModalAccion(null)}
          onConfirmar={(ev) => {
            registrarEvento(ev as any);
            setModalAccion(null);
          }}
        />
      )}
    </div>
  );
}

function BotonAccion(props: { label: string; color: string; onClick: () => void }) {
  return (
    <button onClick={props.onClick}
      className={`${props.color} hover:opacity-90 py-5 rounded-xl text-lg font-bold`}>
      {props.label}
    </button>
  );
}

function ModalCambio(props: {
  enPista: string[];
  banquillo: string[];
  saleInicial: string;
  onCerrar: () => void;
  onConfirmar: (sale: string, entra: string) => void;
}) {
  const [sale, setSale] = useState(props.saleInicial);
  const [entra, setEntra] = useState("");
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50"
      onClick={props.onCerrar}>
      <div className="bg-zinc-900 rounded-xl p-5 w-full max-w-3xl"
        onClick={(e) => e.stopPropagation()}>
        <h2 className="text-2xl font-bold mb-4">🔄 Cambio</h2>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <h3 className="text-sm text-zinc-400 mb-2">SALE de pista</h3>
            <div className="flex flex-wrap gap-2">
              {props.enPista.map((n) => (
                <button key={n} onClick={() => setSale(n)}
                  className={`px-3 py-2 rounded ${
                    sale === n ? "bg-red-700 text-white" : "bg-zinc-800"
                  }`}>{n}</button>
              ))}
            </div>
          </div>
          <div>
            <h3 className="text-sm text-zinc-400 mb-2">ENTRA a pista</h3>
            <div className="flex flex-wrap gap-2">
              {props.banquillo.map((n) => (
                <button key={n} onClick={() => setEntra(n)}
                  className={`px-3 py-2 rounded ${
                    entra === n ? "bg-green-700 text-white" : "bg-zinc-800"
                  }`}>{n}</button>
              ))}
            </div>
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={props.onCerrar}
            className="px-4 py-2 bg-zinc-700 rounded">Cancelar</button>
          <button
            disabled={!sale || !entra || sale === entra}
            onClick={() => props.onConfirmar(sale, entra)}
            className="px-4 py-2 bg-blue-700 disabled:opacity-40 rounded font-bold">
            Confirmar cambio
          </button>
        </div>
      </div>
    </div>
  );
}

function ModalAccion(props: {
  tipo: "gol" | "falta" | "amarilla" | "tm" | "pen";
  enPista: string[];
  rival: string;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL">("INTER");
  const [jugador, setJugador] = useState("");
  const titulo = {
    gol: "⚽ GOL", falta: "⚠️ FALTA", amarilla: "🟨 AMARILLA",
    tm: "🛑 TIEMPO MUERTO", pen: "🎯 PENALTI/10M",
  }[props.tipo];
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50"
      onClick={props.onCerrar}>
      <div className="bg-zinc-900 rounded-xl p-5 w-full max-w-2xl"
        onClick={(e) => e.stopPropagation()}>
        <h2 className="text-2xl font-bold mb-4">{titulo}</h2>
        <div className="flex gap-2 mb-4">
          <button onClick={() => setEquipo("INTER")}
            className={`px-6 py-3 rounded text-lg font-bold ${
              equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"
            }`}>INTER</button>
          <button onClick={() => setEquipo("RIVAL")}
            className={`px-6 py-3 rounded text-lg font-bold ${
              equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"
            }`}>{props.rival}</button>
        </div>

        {props.tipo !== "tm" && equipo === "INTER" && (
          <div className="mb-4">
            <h3 className="text-sm text-zinc-400 mb-2">
              {props.tipo === "gol" ? "Goleador" :
                props.tipo === "pen" ? "Tirador" : "Jugador (opcional)"}
            </h3>
            <div className="flex flex-wrap gap-2">
              {props.enPista.map((n) => (
                <button key={n} onClick={() => setJugador(n)}
                  className={`px-3 py-2 rounded ${
                    jugador === n ? "bg-blue-700" : "bg-zinc-800"
                  }`}>{n}</button>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <button onClick={props.onCerrar}
            className="px-4 py-2 bg-zinc-700 rounded">Cancelar</button>
          <button
            onClick={() => {
              const base: any = { tipo: props.tipo === "tm" ? "tiempo_muerto" : props.tipo, equipo };
              if (props.tipo === "gol") {
                base.goleador = jugador;
                base.cuarteto = props.enPista.filter((n) => n !== jugador);
              } else if (props.tipo === "falta" || props.tipo === "amarilla") {
                if (jugador) base.jugador = jugador;
              } else if (props.tipo === "pen") {
                base.tipo = "penalti";
                base.tirador = jugador;
                base.portero = ""; base.resultado = "GOL";
              }
              props.onConfirmar(base);
            }}
            className="px-4 py-2 bg-green-700 rounded font-bold">
            Confirmar
          </button>
        </div>
      </div>
    </div>
  );
}

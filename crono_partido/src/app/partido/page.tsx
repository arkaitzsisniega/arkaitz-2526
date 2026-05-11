"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { usePartido } from "@/lib/store";
import { ROSTER } from "@/lib/roster";
import { formatMMSS, colorTiempoPista, colorTiempoBanquillo } from "@/lib/utils";

type AccionInd = "pf" | "pnf" | "robos" | "cortes" | "bdg" | "bdp" | "disparo";

export default function PartidoPage() {
  const router = useRouter();
  const {
    partido, cargado,
    segundosTurnoActual, segundosBanquillo, segundosParte,
    segundosPartidoTotal, segundosEnParte,
    play, pausa, avanzarParte, cambiarJugador,
    registrarEvento, deshacerUltimoEvento, incAccion,
  } = usePartido();

  // Estado UI
  const [modalCambio, setModalCambio] = useState<{ sale: string } | null>(null);
  const [modalAccionInd, setModalAccionInd] = useState<{ jugador: string } | null>(null);
  const [modalFalta, setModalFalta] = useState(false);
  const [modalGol, setModalGol] = useState(false);
  const [modalAmarilla, setModalAmarilla] = useState(false);
  const [modalTM, setModalTM] = useState(false);
  const [modalPen, setModalPen] = useState(false);

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

  const p = partido.cronometro.parteActual;
  const sFalt = partido.stats.faltas[p];
  const sAma = partido.stats.amarillas[p];
  const sTM = partido.stats.tiemposMuerto[p];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-3">
      {/* HEADER */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="text-6xl font-mono font-bold tabular-nums">
            {formatMMSS(segParte)}
          </div>
          <div className="text-sm text-zinc-400">
            <div>{p}</div>
            <div className="text-xs">tot {formatMMSS(segundosPartidoTotal())}</div>
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
        {/* EN PISTA — tap abre acciones individuales */}
        <div className="bg-zinc-900 rounded-xl p-3">
          <h2 className="text-zinc-400 text-sm mb-2">EN PISTA (toca un jugador para apuntar acciones)</h2>
          <div className="grid grid-cols-5 gap-2">
            {enPista.map((nombre) => {
              const seg = segundosTurnoActual(nombre);
              const totalParte = segundosEnParte(nombre, p);
              const dorsal = ROSTER.find((j) => j.nombre === nombre)?.dorsal || "";
              const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
              return (
                <button key={nombre}
                  onClick={() => setModalAccionInd({ jugador: nombre })}
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
        <h2 className="text-zinc-400 text-sm mb-2">BANQUILLO (toca + CAMBIO para meterlo)</h2>
        <div className="grid grid-cols-6 gap-2">
          {banquillo.map((nombre) => {
            const seg = segundosBanquillo(nombre);
            const dorsal = ROSTER.find((j) => j.nombre === nombre)?.dorsal || "";
            const esPortero = ROSTER.find((j) => j.nombre === nombre)?.posicion === "PORTERO";
            return (
              <div key={nombre}
                className={`p-2 rounded-lg text-center ${
                  esPortero ? "bg-yellow-700/40 border border-yellow-500"
                            : colorTiempoBanquillo(seg)
                }`}>
                <div className="text-xs opacity-70">{dorsal ? `#${dorsal}` : "—"}</div>
                <div className="text-sm font-bold">{nombre}</div>
                <div className="text-base font-mono tabular-nums mt-1">{formatMMSS(seg)}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* BOTONES ACCIÓN COLECTIVA */}
      <div className="grid grid-cols-6 gap-2">
        <BotonAccion label="⚽ GOL" color="bg-blue-700" onClick={() => setModalGol(true)} />
        <BotonAccion label="⚠️ FALTA" color="bg-orange-700" onClick={() => setModalFalta(true)} />
        <BotonAccion label="🟨 AMARILLA" color="bg-yellow-700" onClick={() => setModalAmarilla(true)} />
        <BotonAccion label="🔄 CAMBIO" color="bg-zinc-700" onClick={() => setModalCambio({ sale: "" })} />
        <BotonAccion label="🛑 T.M." color="bg-purple-700" onClick={() => setModalTM(true)} />
        <BotonAccion label="🎯 PEN/10M" color="bg-pink-700" onClick={() => setModalPen(true)} />
      </div>
      <div className="grid grid-cols-2 gap-2 mt-2">
        <button onClick={deshacerUltimoEvento}
          className="py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm">
          ↶ Deshacer último evento
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
          onCerrar={() => setModalAccionInd(null)}
          onCambio={(sale, entra) => {
            cambiarJugador(sale, entra);
            setModalAccionInd(null);
          }}
          onAccion={(tipo) => incAccion(modalAccionInd.jugador, tipo, 1)}
          onDisparo={(detalles) => {
            // Por ahora guardamos disparos como acción individual + evento custom.
            // En el MVP1 incrementamos contadores; el detalle (zona/resultado/etc.)
            // se mete en el evento para revisión final.
            registrarEvento({
              tipo: "gol", // truco: si es gol, evento "gol". Si no, no creamos evento.
              equipo: "INTER",
              goleador: modalAccionInd.jugador,
              cuarteto: enPista.filter((n) => n !== modalAccionInd.jugador),
            } as any);
            // Cierre
          }}
          onResetCierre={() => setModalAccionInd(null)}
        />
      )}

      {modalFalta && (
        <ModalFalta
          enPista={enPista}
          rivalNombre={cfg.rival}
          onCerrar={() => setModalFalta(false)}
          onConfirmar={(ev) => { registrarEvento(ev as any); setModalFalta(false); }}
        />
      )}

      {modalGol && (
        <ModalGol
          enPista={enPista}
          rivalNombre={cfg.rival}
          onCerrar={() => setModalGol(false)}
          onConfirmar={(ev) => { registrarEvento(ev as any); setModalGol(false); }}
        />
      )}

      {modalAmarilla && (
        <ModalAmarilla
          enPista={enPista}
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
    </div>
  );
}

// ──────────────── COMPONENTES ────────────────

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
      <div className={`bg-zinc-900 rounded-xl p-5 w-full ${props.maxW || "max-w-3xl"} max-h-[90vh] overflow-y-auto`}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold">{props.titulo}</h2>
          <button onClick={props.onCerrar} className="text-zinc-400 text-3xl leading-none">×</button>
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

const ZONAS_CAMPO = ["Z1","Z2","Z3","Z4","Z5","Z6","Z7","Z8","Z9","Z10","Z11"];
const ZONAS_PORTERIA = ["P1","P2","P3","P4","P5","P6","P7","P8","P9"];

function GridZonas(props: { zonas: string[]; sel: string; onSel: (z: string) => void; cols?: number }) {
  const cols = props.cols ?? 3;
  return (
    <div className={`grid grid-cols-${cols} gap-2`} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))` }}>
      {props.zonas.map((z) => (
        <button key={z} onClick={() => props.onSel(z)}
          className={`py-3 rounded font-bold ${
            props.sel === z ? "bg-blue-700 text-white" : "bg-zinc-800 text-zinc-200"
          }`}>{z}</button>
      ))}
    </div>
  );
}

// ──────────────── MODAL CAMBIO ────────────────

function ModalCambio(props: {
  enPista: string[]; banquillo: string[]; saleInicial: string;
  onCerrar: () => void;
  onConfirmar: (sale: string, entra: string) => void;
}) {
  const [sale, setSale] = useState(props.saleInicial);
  const [entra, setEntra] = useState("");
  return (
    <ModalShell titulo="🔄 Cambio" onCerrar={props.onCerrar}>
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <h3 className="text-sm text-zinc-400 mb-2">SALE de pista</h3>
          <ChipsJugador opciones={props.enPista} seleccionado={sale} onSelect={setSale} />
        </div>
        <div>
          <h3 className="text-sm text-zinc-400 mb-2">ENTRA a pista</h3>
          <ChipsJugador opciones={props.banquillo} seleccionado={entra} onSelect={setEntra} />
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button onClick={props.onCerrar} className="px-4 py-2 bg-zinc-700 rounded">Cancelar</button>
        <button
          disabled={!sale || !entra || sale === entra}
          onClick={() => props.onConfirmar(sale, entra)}
          className="px-4 py-2 bg-blue-700 disabled:opacity-40 rounded font-bold">
          Confirmar cambio
        </button>
      </div>
    </ModalShell>
  );
}

// ──────────────── MODAL FALTA ────────────────
// "A favor" = nos la hacen → quién la recibe (de nuestros) + opcional rival anónimo
// "En contra" = la hacemos → quién la comete + opción "rival" (mano, etc.)

function ModalFalta(props: {
  enPista: string[]; rivalNombre: string;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL">("INTER");
  const [jugador, setJugador] = useState("");
  const [esManoOAnon, setEsManoOAnon] = useState(false);

  // INTER = la hace nuestro jugador → "en contra"
  // RIVAL = la hace rival, la recibimos nosotros → "a favor"
  // En la columna stat del Sheet, las faltas se cuentan EN CONTRA del que las hace.
  // Aquí: equipo=INTER → falta en contra de Inter; equipo=RIVAL → falta en contra del rival.

  return (
    <ModalShell titulo="⚠️ Falta" onCerrar={props.onCerrar}>
      <div className="flex gap-2 mb-4">
        <button onClick={() => { setEquipo("INTER"); setEsManoOAnon(false); setJugador(""); }}
          className={`flex-1 px-6 py-4 rounded text-lg font-bold ${
            equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"
          }`}>
          La COMETEMOS nosotros
        </button>
        <button onClick={() => { setEquipo("RIVAL"); setEsManoOAnon(false); setJugador(""); }}
          className={`flex-1 px-6 py-4 rounded text-lg font-bold ${
            equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"
          }`}>
          La COMETE {props.rivalNombre}
        </button>
      </div>

      <div className="mb-4">
        <h3 className="text-sm text-zinc-400 mb-2">
          {equipo === "INTER"
            ? "¿Qué jugador nuestro la comete? (o anónimo/mano)"
            : "¿Qué jugador nuestro la recibe? (o sin asignar)"}
        </h3>
        <div className="flex flex-wrap gap-2">
          {props.enPista.map((n) => (
            <button key={n}
              onClick={() => { setJugador(n); setEsManoOAnon(false); }}
              className={`px-3 py-2 rounded text-base ${
                jugador === n && !esManoOAnon ? "bg-blue-700" : "bg-zinc-800"
              }`}>{n}</button>
          ))}
          <button
            onClick={() => { setJugador(""); setEsManoOAnon(true); }}
            className={`px-3 py-2 rounded text-base ${
              esManoOAnon ? "bg-purple-700" : "bg-zinc-800"
            }`}>
            {equipo === "INTER" ? "RIVAL/MANO" : "SIN ASIGNAR"}
          </button>
        </div>
      </div>

      <div className="flex gap-2 justify-end">
        <button onClick={props.onCerrar} className="px-4 py-2 bg-zinc-700 rounded">Cancelar</button>
        <button
          onClick={() => {
            const ev: any = { tipo: "falta", equipo };
            if (jugador) ev.jugador = jugador;
            if (esManoOAnon) ev.rivalMano = true;
            props.onConfirmar(ev);
          }}
          className="px-4 py-2 bg-green-700 rounded font-bold">
          Confirmar
        </button>
      </div>
    </ModalShell>
  );
}

// ──────────────── MODAL AMARILLA ────────────────

function ModalAmarilla(props: {
  enPista: string[]; rivalNombre: string;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL">("INTER");
  const [jugador, setJugador] = useState("");
  return (
    <ModalShell titulo="🟨 Tarjeta amarilla" onCerrar={props.onCerrar}>
      <div className="flex gap-2 mb-4">
        <button onClick={() => { setEquipo("INTER"); setJugador(""); }}
          className={`flex-1 px-6 py-4 rounded text-lg font-bold ${
            equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"
          }`}>INTER</button>
        <button onClick={() => { setEquipo("RIVAL"); setJugador(""); }}
          className={`flex-1 px-6 py-4 rounded text-lg font-bold ${
            equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"
          }`}>{props.rivalNombre}</button>
      </div>
      {equipo === "INTER" && (
        <div className="mb-4">
          <h3 className="text-sm text-zinc-400 mb-2">Jugador (opcional)</h3>
          <ChipsJugador opciones={props.enPista} seleccionado={jugador} onSelect={setJugador} />
        </div>
      )}
      <div className="flex gap-2 justify-end">
        <button onClick={props.onCerrar} className="px-4 py-2 bg-zinc-700 rounded">Cancelar</button>
        <button onClick={() => {
          const ev: any = { tipo: "amarilla", equipo };
          if (jugador) ev.jugador = jugador;
          props.onConfirmar(ev);
        }} className="px-4 py-2 bg-green-700 rounded font-bold">Confirmar</button>
      </div>
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
          className="py-6 bg-blue-700 rounded text-xl font-bold">INTER</button>
        <button onClick={() => props.onConfirmar("RIVAL")}
          className="py-6 bg-red-700 rounded text-xl font-bold">{props.rivalNombre}</button>
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
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL">("INTER");
  const [goleador, setGoleador] = useState("");
  const [asistente, setAsistente] = useState("");
  const [zona, setZona] = useState("");
  const [accion, setAccion] = useState("");
  return (
    <ModalShell titulo="⚽ GOL" onCerrar={props.onCerrar}>
      <div className="flex gap-2 mb-4">
        <button onClick={() => { setEquipo("INTER"); setGoleador(""); setAsistente(""); }}
          className={`flex-1 px-6 py-4 rounded text-lg font-bold ${
            equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"
          }`}>INTER</button>
        <button onClick={() => { setEquipo("RIVAL"); setGoleador(""); setAsistente(""); }}
          className={`flex-1 px-6 py-4 rounded text-lg font-bold ${
            equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"
          }`}>{props.rivalNombre}</button>
      </div>

      {equipo === "INTER" && (
        <>
          <div className="mb-3">
            <h3 className="text-sm text-zinc-400 mb-2">Goleador</h3>
            <ChipsJugador opciones={props.enPista} seleccionado={goleador} onSelect={setGoleador} />
          </div>
          <div className="mb-3">
            <h3 className="text-sm text-zinc-400 mb-2">Asistente (opcional)</h3>
            <ChipsJugador
              opciones={props.enPista.filter((n) => n !== goleador)}
              seleccionado={asistente} onSelect={setAsistente}
            />
          </div>
        </>
      )}

      <div className="mb-3">
        <h3 className="text-sm text-zinc-400 mb-2">Acción del gol</h3>
        <div className="flex flex-wrap gap-2">
          {ACCIONES_GOL.map((a) => (
            <button key={a} onClick={() => setAccion(a)}
              className={`px-3 py-2 rounded text-sm ${
                accion === a ? "bg-blue-700" : "bg-zinc-800"
              }`}>{a}</button>
          ))}
        </div>
      </div>

      <div className="mb-4">
        <h3 className="text-sm text-zinc-400 mb-2">Zona de portería</h3>
        <GridZonas zonas={ZONAS_PORTERIA} sel={zona} onSel={setZona} cols={3} />
      </div>

      <div className="flex gap-2 justify-end">
        <button onClick={props.onCerrar} className="px-4 py-2 bg-zinc-700 rounded">Cancelar</button>
        <button
          disabled={equipo === "INTER" && !goleador}
          onClick={() => {
            const ev: any = { tipo: "gol", equipo };
            if (equipo === "INTER") {
              ev.goleador = goleador;
              if (asistente) ev.asistente = asistente;
              ev.cuarteto = props.enPista.filter((n) => n !== goleador);
            }
            if (accion) ev.accion = accion;
            if (zona) ev.zonaPorteria = zona;
            props.onConfirmar(ev);
          }}
          className="px-4 py-2 bg-green-700 disabled:opacity-40 rounded font-bold">
          Confirmar gol
        </button>
      </div>
    </ModalShell>
  );
}

// ──────────────── MODAL PENALTI / 10M ────────────────

function ModalPenalti(props: {
  enPista: string[]; rivalNombre: string;
  onCerrar: () => void;
  onConfirmar: (ev: any) => void;
}) {
  const [tipo, setTipo] = useState<"penalti" | "diezm">("penalti");
  const [equipo, setEquipo] = useState<"INTER" | "RIVAL">("INTER");
  const [tirador, setTirador] = useState("");
  const [porteroRival, setPorteroRival] = useState("");
  const [porteroPropio, setPorteroPropio] = useState("");
  const [zona, setZona] = useState("");
  const [resultado, setResultado] = useState<"GOL" | "PARADA" | "POSTE" | "FUERA">("GOL");
  const RESULTADOS: ("GOL" | "PARADA" | "POSTE" | "FUERA")[] = ["GOL", "PARADA", "POSTE", "FUERA"];

  return (
    <ModalShell titulo="🎯 Penalti / 10 metros" onCerrar={props.onCerrar}>
      <div className="flex gap-2 mb-3">
        <button onClick={() => setTipo("penalti")}
          className={`flex-1 py-3 rounded font-bold ${
            tipo === "penalti" ? "bg-pink-700" : "bg-zinc-800"
          }`}>Penalti (6m)</button>
        <button onClick={() => setTipo("diezm")}
          className={`flex-1 py-3 rounded font-bold ${
            tipo === "diezm" ? "bg-pink-700" : "bg-zinc-800"
          }`}>10 metros</button>
      </div>

      <div className="flex gap-2 mb-3">
        <button onClick={() => { setEquipo("INTER"); setTirador(""); }}
          className={`flex-1 py-3 rounded font-bold ${
            equipo === "INTER" ? "bg-blue-700" : "bg-zinc-800"
          }`}>A FAVOR (lo tira Inter)</button>
        <button onClick={() => { setEquipo("RIVAL"); setTirador(""); }}
          className={`flex-1 py-3 rounded font-bold ${
            equipo === "RIVAL" ? "bg-red-700" : "bg-zinc-800"
          }`}>EN CONTRA (lo tira {props.rivalNombre})</button>
      </div>

      {equipo === "INTER" ? (
        <div className="mb-3">
          <h3 className="text-sm text-zinc-400 mb-2">Tirador (nuestro)</h3>
          <ChipsJugador opciones={props.enPista} seleccionado={tirador} onSelect={setTirador} />
          <p className="text-xs text-zinc-500 mt-2">Portero rival: nombre genérico (opcional)</p>
          <input className="w-full bg-zinc-800 rounded px-3 py-2 mt-1"
            placeholder="Portero rival (opcional)"
            value={porteroRival} onChange={(e) => setPorteroRival(e.target.value.toUpperCase())} />
        </div>
      ) : (
        <div className="mb-3">
          <h3 className="text-sm text-zinc-400 mb-2">Portero nuestro (quién para)</h3>
          <ChipsJugador
            opciones={props.enPista.filter((n) => {
              return ROSTER.find((j) => j.nombre === n)?.posicion === "PORTERO";
            })}
            seleccionado={porteroPropio} onSelect={setPorteroPropio} />
          <p className="text-xs text-zinc-500 mt-2">Tirador rival (texto, opcional)</p>
          <input className="w-full bg-zinc-800 rounded px-3 py-2 mt-1"
            placeholder="Nombre tirador rival"
            value={tirador} onChange={(e) => setTirador(e.target.value.toUpperCase())} />
        </div>
      )}

      <div className="mb-3">
        <h3 className="text-sm text-zinc-400 mb-2">Resultado</h3>
        <div className="grid grid-cols-4 gap-2">
          {RESULTADOS.map((r) => (
            <button key={r} onClick={() => setResultado(r)}
              className={`py-3 rounded font-bold ${
                resultado === r ? (r === "GOL" ? "bg-green-700" : "bg-yellow-700") : "bg-zinc-800"
              }`}>{r}</button>
          ))}
        </div>
      </div>

      <div className="mb-4">
        <h3 className="text-sm text-zinc-400 mb-2">Zona destino (portería)</h3>
        <GridZonas zonas={ZONAS_PORTERIA} sel={zona} onSel={setZona} cols={3} />
        <p className="text-xs text-zinc-500 mt-1">Si va FUERA, déjalo sin selección.</p>
      </div>

      <div className="flex gap-2 justify-end">
        <button onClick={props.onCerrar} className="px-4 py-2 bg-zinc-700 rounded">Cancelar</button>
        <button
          onClick={() => {
            const ev: any = {
              tipo, equipo,
              tirador: equipo === "INTER" ? tirador : tirador,
              portero: equipo === "INTER" ? porteroRival : porteroPropio,
              resultado,
            };
            if (zona) ev.zona = zona;
            props.onConfirmar(ev);
          }}
          className="px-4 py-2 bg-green-700 rounded font-bold">Confirmar</button>
      </div>
    </ModalShell>
  );
}

// ──────────────── MODAL ACCIÓN INDIVIDUAL (tap en jugador en pista) ────────────────

function ModalAccionIndividual(props: {
  jugador: string;
  enPista: string[];
  banquillo: string[];
  onCerrar: () => void;
  onCambio: (sale: string, entra: string) => void;
  onAccion: (tipo: "pf" | "pnf" | "robos" | "cortes" | "bdg" | "bdp") => void;
  onDisparo: (detalles: any) => void;
  onResetCierre: () => void;
}) {
  const [paso, setPaso] = useState<"menu" | "disparo" | "zona" | "cambio">("menu");
  const [disparoResultado, setDisparoResultado] = useState<"PUERTA" | "PALO" | "FUERA" | "BLOQUEADO">("PUERTA");
  const [zonaCampo, setZonaCampo] = useState("");
  const [zonaPorteria, setZonaPorteria] = useState("");
  const [cambioEntra, setCambioEntra] = useState("");

  const titulo = `📊 Acciones de ${props.jugador}`;

  if (paso === "menu") {
    return (
      <ModalShell titulo={titulo} onCerrar={props.onCerrar}>
        <p className="text-sm text-zinc-400 mb-3">Toca la acción a apuntar:</p>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <BotonGrande label="🔁 Robo" onClick={() => { props.onAccion("robos"); props.onResetCierre(); }} />
          <BotonGrande label="✂️ Corte" onClick={() => { props.onAccion("cortes"); props.onResetCierre(); }} />
          <BotonGrande label="❌ Pérdida forzada (PF)" onClick={() => { props.onAccion("pf"); props.onResetCierre(); }} />
          <BotonGrande label="❌ Pérdida NO forzada (PNF)" onClick={() => { props.onAccion("pnf"); props.onResetCierre(); }} />
          <BotonGrande label="🥇 Balón dividido GANADO" onClick={() => { props.onAccion("bdg"); props.onResetCierre(); }} />
          <BotonGrande label="🥈 Balón dividido PERDIDO" onClick={() => { props.onAccion("bdp"); props.onResetCierre(); }} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <BotonGrande label="🎯 Disparo" color="bg-pink-700" onClick={() => setPaso("disparo")} />
          <BotonGrande label="🔄 Cambio (este sale)" color="bg-zinc-700" onClick={() => setPaso("cambio")} />
        </div>
      </ModalShell>
    );
  }

  if (paso === "disparo") {
    return (
      <ModalShell titulo={`🎯 Disparo de ${props.jugador}`} onCerrar={props.onCerrar}>
        <div className="mb-4">
          <h3 className="text-sm text-zinc-400 mb-2">Tipo de disparo</h3>
          <div className="grid grid-cols-4 gap-2">
            {(["PUERTA", "PALO", "FUERA", "BLOQUEADO"] as const).map((r) => (
              <button key={r} onClick={() => setDisparoResultado(r)}
                className={`py-3 rounded font-bold ${
                  disparoResultado === r ? "bg-pink-700" : "bg-zinc-800"
                }`}>{r}</button>
            ))}
          </div>
        </div>
        <div className="mb-4">
          <h3 className="text-sm text-zinc-400 mb-2">Zona del campo (origen)</h3>
          <GridZonas zonas={ZONAS_CAMPO} sel={zonaCampo} onSel={setZonaCampo} cols={4} />
        </div>
        {disparoResultado === "PUERTA" && (
          <div className="mb-4">
            <h3 className="text-sm text-zinc-400 mb-2">Zona de portería (destino)</h3>
            <GridZonas zonas={ZONAS_PORTERIA} sel={zonaPorteria} onSel={setZonaPorteria} cols={3} />
          </div>
        )}
        <div className="flex gap-2 justify-end">
          <button onClick={() => setPaso("menu")} className="px-4 py-2 bg-zinc-700 rounded">← Atrás</button>
          <button
            onClick={() => {
              // Sumar el disparo al jugador como contador (de momento usamos
              // el dict de acciones — habrá que ampliar el schema para zonas).
              props.onDisparo({
                jugador: props.jugador,
                resultado: disparoResultado,
                zonaCampo, zonaPorteria,
              });
              props.onResetCierre();
            }}
            className="px-4 py-2 bg-green-700 rounded font-bold">Guardar disparo</button>
        </div>
      </ModalShell>
    );
  }

  if (paso === "cambio") {
    return (
      <ModalShell titulo={`🔄 Cambio: sale ${props.jugador}`} onCerrar={props.onCerrar}>
        <h3 className="text-sm text-zinc-400 mb-2">Entra:</h3>
        <ChipsJugador opciones={props.banquillo} seleccionado={cambioEntra} onSelect={setCambioEntra} />
        <div className="flex gap-2 justify-end mt-4">
          <button onClick={() => setPaso("menu")} className="px-4 py-2 bg-zinc-700 rounded">← Atrás</button>
          <button
            disabled={!cambioEntra}
            onClick={() => props.onCambio(props.jugador, cambioEntra)}
            className="px-4 py-2 bg-blue-700 disabled:opacity-40 rounded font-bold">Confirmar cambio</button>
        </div>
      </ModalShell>
    );
  }
  return null;
}

function BotonGrande(props: { label: string; onClick: () => void; color?: string }) {
  return (
    <button onClick={props.onClick}
      className={`${props.color || "bg-zinc-700"} hover:opacity-90 py-5 rounded-xl text-base font-bold`}>
      {props.label}
    </button>
  );
}

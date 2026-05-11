"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { usePartido } from "@/lib/store";
import { ROSTER, PORTEROS, CAMPO } from "@/lib/roster";
import { hoyISO } from "@/lib/utils";

export default function NuevoPartido() {
  const router = useRouter();
  const { iniciarPartido } = usePartido();

  const [rival, setRival] = useState("");
  const [fecha, setFecha] = useState(hoyISO());
  const [hora, setHora] = useState("18:00");
  const [lugar, setLugar] = useState("");
  const [competicion, setCompeticion] = useState("LIGA");
  const [local, setLocal] = useState(false);
  const [partidoId, setPartidoId] = useState("");

  // Pre-seleccionar primer equipo activo
  const [convocados, setConvocados] = useState<string[]>(
    ROSTER.filter((j) => j.equipo === "PRIMER").map((j) => j.nombre)
  );
  const toggleConvocado = (n: string) => {
    setConvocados((cur) =>
      cur.includes(n) ? cur.filter((x) => x !== n) : [...cur, n]
    );
  };

  const porterosConv = PORTEROS.filter((j) => convocados.includes(j.nombre));
  const campoConv = CAMPO.filter((j) => convocados.includes(j.nombre));

  const [portero, setPortero] = useState(porterosConv[0]?.nombre || "");
  const [pista1, setPista1] = useState(campoConv[0]?.nombre || "");
  const [pista2, setPista2] = useState(campoConv[1]?.nombre || "");
  const [pista3, setPista3] = useState(campoConv[2]?.nombre || "");
  const [pista4, setPista4] = useState(campoConv[3]?.nombre || "");

  const empezar = () => {
    if (!rival.trim()) { alert("Pon el nombre del rival"); return; }
    if (!partidoId.trim()) { alert("Pon el ID del partido (ej: J29.VALDEPEÑAS)"); return; }
    if (!portero || !pista1 || !pista2 || !pista3 || !pista4) {
      alert("Selecciona los 5 jugadores en pista (portero + 4 campo)");
      return;
    }
    const unicos = new Set([portero, pista1, pista2, pista3, pista4]);
    if (unicos.size < 5) { alert("Los 5 jugadores deben ser distintos"); return; }

    iniciarPartido({
      rival: rival.trim().toUpperCase(),
      fecha, hora, lugar: lugar.trim(), competicion,
      local, partido_id: partidoId.trim(),
      convocados,
      pista_inicial: { portero, pista1, pista2, pista3, pista4 },
    });
    router.push("/partido");
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      <h1 className="text-3xl font-bold mb-6">⚽ Nuevo partido</h1>

      {/* Cabecera */}
      <section className="grid grid-cols-2 gap-4 mb-6">
        <label className="flex flex-col">
          <span className="text-sm text-zinc-400 mb-1">Rival</span>
          <input className="bg-zinc-900 rounded px-3 py-2 text-lg" value={rival}
            onChange={(e) => setRival(e.target.value)} placeholder="Ej: VALDEPEÑAS" />
        </label>
        <label className="flex flex-col">
          <span className="text-sm text-zinc-400 mb-1">ID partido</span>
          <input className="bg-zinc-900 rounded px-3 py-2 text-lg" value={partidoId}
            onChange={(e) => setPartidoId(e.target.value.toUpperCase())} placeholder="J29.VALDEPEÑAS" />
        </label>
        <label className="flex flex-col">
          <span className="text-sm text-zinc-400 mb-1">Fecha</span>
          <input type="date" className="bg-zinc-900 rounded px-3 py-2 text-lg" value={fecha}
            onChange={(e) => setFecha(e.target.value)} />
        </label>
        <label className="flex flex-col">
          <span className="text-sm text-zinc-400 mb-1">Hora</span>
          <input className="bg-zinc-900 rounded px-3 py-2 text-lg" value={hora}
            onChange={(e) => setHora(e.target.value)} placeholder="18:00" />
        </label>
        <label className="flex flex-col">
          <span className="text-sm text-zinc-400 mb-1">Lugar</span>
          <input className="bg-zinc-900 rounded px-3 py-2 text-lg" value={lugar}
            onChange={(e) => setLugar(e.target.value)} placeholder="Pabellón..." />
        </label>
        <label className="flex flex-col">
          <span className="text-sm text-zinc-400 mb-1">Competición</span>
          <select className="bg-zinc-900 rounded px-3 py-2 text-lg" value={competicion}
            onChange={(e) => setCompeticion(e.target.value)}>
            <option>LIGA</option>
            <option>COPA_REY</option>
            <option>COPA_ESPANA</option>
            <option>COPA_MUNDO</option>
            <option>AMISTOSO</option>
            <option>PLAYOFF</option>
            <option>SUPERCOPA</option>
          </select>
        </label>
        <label className="flex items-center gap-2 col-span-2">
          <input type="checkbox" className="w-5 h-5" checked={local}
            onChange={(e) => setLocal(e.target.checked)} />
          <span>Inter juega como LOCAL</span>
        </label>
      </section>

      {/* Convocados */}
      <section className="mb-6">
        <h2 className="text-xl font-semibold mb-3">Convocados (toca para conmutar)</h2>
        <div className="flex flex-wrap gap-2">
          {ROSTER.map((j) => {
            const on = convocados.includes(j.nombre);
            return (
              <button key={j.nombre}
                onClick={() => toggleConvocado(j.nombre)}
                className={`px-3 py-2 rounded text-sm font-semibold ${
                  on
                    ? j.posicion === "PORTERO"
                      ? "bg-yellow-600 text-white"
                      : j.equipo === "PRIMER" ? "bg-blue-700 text-white" : "bg-zinc-700 text-white"
                    : "bg-zinc-900 text-zinc-500"
                }`}>
                {j.dorsal ? `#${j.dorsal} ` : ""}{j.nombre}
              </button>
            );
          })}
        </div>
        <p className="text-sm text-zinc-400 mt-2">{convocados.length} convocados</p>
      </section>

      {/* Pista inicial */}
      <section className="mb-6">
        <h2 className="text-xl font-semibold mb-3">Pista inicial</h2>
        <div className="grid grid-cols-2 gap-3">
          <SelectJugador label="🥅 Portero" value={portero} setValue={setPortero}
            opciones={porterosConv} />
          <SelectJugador label="⚽ Pista 1" value={pista1} setValue={setPista1}
            opciones={campoConv} />
          <SelectJugador label="⚽ Pista 2" value={pista2} setValue={setPista2}
            opciones={campoConv} />
          <SelectJugador label="⚽ Pista 3" value={pista3} setValue={setPista3}
            opciones={campoConv} />
          <SelectJugador label="⚽ Pista 4" value={pista4} setValue={setPista4}
            opciones={campoConv} />
        </div>
      </section>

      <button onClick={empezar}
        className="w-full py-5 bg-green-700 hover:bg-green-600 rounded-xl text-2xl font-bold">
        🏁 EMPEZAR PARTIDO
      </button>
    </div>
  );
}

function SelectJugador(props: {
  label: string; value: string; setValue: (v: string) => void;
  opciones: { nombre: string; dorsal: string }[];
}) {
  return (
    <label className="flex flex-col">
      <span className="text-sm text-zinc-400 mb-1">{props.label}</span>
      <select className="bg-zinc-900 rounded px-3 py-2 text-lg" value={props.value}
        onChange={(e) => props.setValue(e.target.value)}>
        <option value="">— elige —</option>
        {props.opciones.map((j) => (
          <option key={j.nombre} value={j.nombre}>
            {j.dorsal ? `#${j.dorsal} ` : ""}{j.nombre}
          </option>
        ))}
      </select>
    </label>
  );
}

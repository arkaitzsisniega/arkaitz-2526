"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { db, type Partido } from "@/lib/db";

export default function Home() {
  const [partidoExistente, setPartidoExistente] = useState<Partido | null>(null);
  const [cargado, setCargado] = useState(false);

  useEffect(() => {
    (async () => {
      const p = await db.partidos.get("current");
      if (p && p.estado !== "configurando") {
        setPartidoExistente(p);
      }
      setCargado(true);
    })();
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center p-6">
      <h1 className="text-5xl font-bold mb-4">⚽ Crono Inter FS</h1>
      <p className="text-zinc-400 mb-10 text-center">
        Cronómetro y registro en directo para el banquillo del Movistar Inter FS.
      </p>

      {cargado && partidoExistente && partidoExistente.config && (
        <div className="bg-zinc-900 rounded-xl p-5 mb-6 w-full max-w-md">
          <h2 className="text-lg font-bold mb-2">⏳ Hay un partido en curso</h2>
          <p className="text-sm text-zinc-400 mb-2">
            <strong className="text-white">{partidoExistente.config.partido_id}</strong> ·
            INTER {partidoExistente.marcador.inter}-{partidoExistente.marcador.rival} {partidoExistente.config.rival}
            <br />
            {partidoExistente.config.fecha} · {partidoExistente.cronometro.parteActual}
          </p>
          <Link href="/partido"
            className="block w-full py-3 bg-blue-700 hover:bg-blue-600 rounded-lg text-center font-bold">
            ⏯ Continuar partido
          </Link>
        </div>
      )}

      <Link href="/nuevo"
        className="px-8 py-5 bg-green-700 hover:bg-green-600 rounded-xl text-2xl font-bold">
        🏁 Nuevo partido
      </Link>

      <div className="mt-10 text-xs text-zinc-500 text-center">
        Funciona offline. Instala en el iPad como app: Compartir → Añadir a pantalla inicio.
      </div>
    </div>
  );
}

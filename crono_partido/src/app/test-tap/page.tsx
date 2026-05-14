"use client";

import { useState } from "react";

export default function TestTap() {
  const [n, setN] = useState(0);
  const [eventos, setEventos] = useState<string[]>([]);

  const log = (msg: string) => {
    const ts = new Date().toLocaleTimeString();
    setEventos((prev) => [`${ts} ${msg}`, ...prev].slice(0, 10));
  };

  return (
    <div style={{ padding: 20, fontFamily: "system-ui", color: "#fff", background: "#000", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 24, marginBottom: 16 }}>Test de hidratación</h1>
      <p style={{ marginBottom: 8 }}>
        Si React está vivo, al tocar el botón el contador sube. Si NO sube,
        React no se hidrata en este dispositivo.
      </p>

      <div style={{ fontSize: 48, fontWeight: 700, marginBottom: 16 }}>
        Contador: {n}
      </div>

      <button
        onClick={() => { setN(n + 1); log("onClick"); }}
        onTouchStart={() => log("onTouchStart")}
        onPointerDown={() => log("onPointerDown")}
        style={{
          width: "100%",
          padding: "20px",
          fontSize: 24,
          background: "#16a34a",
          color: "white",
          border: 0,
          borderRadius: 8,
          fontWeight: 700,
          marginBottom: 16,
        }}
      >
        TÓCAME
      </button>

      <div style={{ fontSize: 12 }}>
        <strong>UA:</strong>{" "}
        <span suppressHydrationWarning>
          {typeof navigator !== "undefined" ? navigator.userAgent : ""}
        </span>
      </div>

      <div style={{ marginTop: 16, fontSize: 14 }}>
        <strong>Últimos eventos:</strong>
        <ul style={{ marginTop: 8, paddingLeft: 20 }}>
          {eventos.length === 0 && <li style={{ opacity: 0.5 }}>(ninguno)</li>}
          {eventos.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      </div>
    </div>
  );
}

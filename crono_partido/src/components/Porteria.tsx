"use client";

/**
 * Portería 3x3 clicable. Cada celda es una zona P1..P9 con la siguiente
 * disposición (vista desde el campo, mirando a portería):
 *
 *    P1 | P2 | P3      ← arriba (escuadras y centro alto)
 *    P4 | P5 | P6      ← media altura
 *    P7 | P8 | P9      ← abajo (ras de suelo)
 *
 * Al pulsar una zona, dispara onSelect inmediatamente (zero-confirm).
 */
import React from "react";

interface Props {
  seleccionada?: string;
  onSelect: (zona: string) => void;
  /** Si quieres que muestre las redes y los postes. */
  mostrarRed?: boolean;
}

const ZONAS = [
  ["P1", "P2", "P3"],
  ["P4", "P5", "P6"],
  ["P7", "P8", "P9"],
];

export function Porteria({ seleccionada, onSelect, mostrarRed = true }: Props) {
  // SVG 600 x 360. Marco con postes blancos, red gris, 9 zonas como rects.
  const W = 600, H = 360;
  const MX = 30, MY = 20;   // márgenes (donde están los postes)
  const inW = W - 2 * MX;
  const inH = H - MY;        // suelo a tope
  const cellW = inW / 3;
  const cellH = inH / 3;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none">
      {/* Fondo (cielo abajo del campo) */}
      <rect x="0" y="0" width={W} height={H} fill="#0f1419" rx="8" />

      {/* Suelo */}
      <rect x="0" y={MY + inH} width={W} height={H - (MY + inH)} fill="#1a2330" />

      {/* RED (líneas finas) */}
      {mostrarRed && (
        <g stroke="#3a4250" strokeWidth="0.8" opacity="0.6">
          {Array.from({ length: 12 }).map((_, i) => (
            <line key={`v${i}`}
              x1={MX + (inW * i) / 11} y1={MY}
              x2={MX + (inW * i) / 11} y2={MY + inH} />
          ))}
          {Array.from({ length: 7 }).map((_, i) => (
            <line key={`h${i}`}
              x1={MX} y1={MY + (inH * i) / 6}
              x2={W - MX} y2={MY + (inH * i) / 6} />
          ))}
        </g>
      )}

      {/* 9 zonas clicables (rectángulos) */}
      {ZONAS.map((row, r) =>
        row.map((zona, c) => {
          const x = MX + c * cellW;
          const y = MY + r * cellH;
          const sel = seleccionada === zona;
          return (
            <g key={zona} onClick={() => onSelect(zona)} className="cursor-pointer">
              <rect
                x={x + 2} y={y + 2}
                width={cellW - 4} height={cellH - 4}
                fill={sel ? "#1d4ed8" : "#ffffff"}
                fillOpacity={sel ? 0.65 : 0.04}
                stroke={sel ? "#3b82f6" : "#ffffff"}
                strokeOpacity={sel ? 1 : 0.25}
                strokeWidth={sel ? 3 : 1.5}
                rx="6"
              />
              <text
                x={x + cellW / 2} y={y + cellH / 2 + 12}
                textAnchor="middle"
                fontSize="36" fontWeight="bold"
                fill={sel ? "#ffffff" : "#94a3b8"}
                style={{ pointerEvents: "none" }}>
                {zona}
              </text>
            </g>
          );
        })
      )}

      {/* Postes y travesaño (encima de todo) */}
      <g stroke="#ffffff" strokeWidth="6" fill="none" strokeLinecap="square">
        <line x1={MX} y1={MY} x2={MX} y2={MY + inH} />            {/* poste izq */}
        <line x1={W - MX} y1={MY} x2={W - MX} y2={MY + inH} />    {/* poste der */}
        <line x1={MX - 3} y1={MY} x2={W - MX + 3} y2={MY} />      {/* travesaño */}
      </g>

      {/* Botón "FUERA" arriba (opcional, si lo necesitas) */}
      {/* Comentado: en el flujo decidimos si llamamos al modal con resultado=FUERA antes */}
    </svg>
  );
}

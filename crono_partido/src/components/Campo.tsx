"use client";

/**
 * Campo de fútbol sala con zonas clicables (zero-confirm).
 *
 * Orientación: Inter ataca hacia la DERECHA. El portero propio defiende
 * a la izquierda; la portería rival está a la derecha.
 *
 * 11 zonas:
 *   Z1 = área propia (semicírculo del portero nuestro, izquierda)
 *   Z2 = banda izquierda zona defensiva
 *   Z3 = central zona defensiva
 *   Z4 = banda derecha zona defensiva
 *   Z5 = banda izquierda mediocampo
 *   Z6 = central mediocampo
 *   Z7 = banda derecha mediocampo
 *   Z8 = banda izquierda zona ofensiva
 *   Z9 = central zona ofensiva (frontal área rival)
 *   Z10 = banda derecha zona ofensiva
 *   Z11 = área rival (semicírculo, derecha) — donde están los penaltis
 */
import React from "react";

interface Props {
  seleccionada?: string;
  onSelect: (zona: string) => void;
}

const ETIQUETAS: Record<string, string> = {
  Z1: "Z1\nárea propia",
  Z2: "Z2",
  Z3: "Z3",
  Z4: "Z4",
  Z5: "Z5",
  Z6: "Z6",
  Z7: "Z7",
  Z8: "Z8",
  Z9: "Z9",
  Z10: "Z10",
  Z11: "Z11\nárea rival",
};

export function Campo({ seleccionada, onSelect }: Props) {
  // SVG 800 x 400 (proporción 2:1 = futsal 40m x 20m).
  const W = 800, H = 400;

  // Áreas: usamos elipses para imitar los semicírculos de 6m.
  // En futsal real son cuartos de círculo + recta entre postes, pero
  // simplifico a una elipse decorativa que el portero "abarca".
  const AREA_W = 120;
  const AREA_H = H * 0.7;

  // Zonas (rejilla 3x3 entre las dos áreas) — eje X: 120..680, eje Y: 0..400.
  const GX0 = AREA_W;
  const GX1 = W - AREA_W;
  const gridW = GX1 - GX0;
  const colW = gridW / 3;
  const rowH = H / 3;

  // Define cada zona como rectángulo (col, row) — row 0=arriba (banda izq).
  // Pero como horizontal: definimos coordenadas explícitas para legibilidad.
  type Z = { id: string; x: number; y: number; w: number; h: number };
  const zonas: Z[] = [
    { id: "Z2", x: GX0,           y: 0,         w: colW, h: rowH },   // def banda izq (arriba)
    { id: "Z5", x: GX0 + colW,    y: 0,         w: colW, h: rowH },   // medio banda izq
    { id: "Z8", x: GX0 + 2*colW,  y: 0,         w: colW, h: rowH },   // atac banda izq
    { id: "Z3", x: GX0,           y: rowH,      w: colW, h: rowH },   // def central
    { id: "Z6", x: GX0 + colW,    y: rowH,      w: colW, h: rowH },   // medio central
    { id: "Z9", x: GX0 + 2*colW,  y: rowH,      w: colW, h: rowH },   // atac central
    { id: "Z4", x: GX0,           y: 2*rowH,    w: colW, h: rowH },   // def banda der (abajo)
    { id: "Z7", x: GX0 + colW,    y: 2*rowH,    w: colW, h: rowH },   // medio banda der
    { id: "Z10", x: GX0 + 2*colW, y: 2*rowH,    w: colW, h: rowH },   // atac banda der
  ];

  const sel = (z: string) => seleccionada === z;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none">
      {/* Césped */}
      <rect x="0" y="0" width={W} height={H} fill="#1b5e20" rx="8" />

      {/* Líneas exteriores */}
      <rect x="2" y="2" width={W - 4} height={H - 4}
        fill="none" stroke="#ffffff" strokeWidth="3" rx="6" />

      {/* Línea media */}
      <line x1={W / 2} y1="0" x2={W / 2} y2={H}
        stroke="#ffffff" strokeWidth="3" />

      {/* Círculo central */}
      <circle cx={W / 2} cy={H / 2} r="55"
        fill="none" stroke="#ffffff" strokeWidth="3" />
      <circle cx={W / 2} cy={H / 2} r="4" fill="#ffffff" />

      {/* Área PROPIA (izquierda) — semielipse */}
      <path d={`M 0 ${(H - AREA_H) / 2}
                A ${AREA_W} ${AREA_H / 2} 0 0 1
                  0 ${(H + AREA_H) / 2}`}
        fill="none" stroke="#ffffff" strokeWidth="3" />
      {/* Punto 6m */}
      <circle cx={AREA_W - 30} cy={H / 2} r="3" fill="#ffffff" />
      {/* Punto 10m */}
      <circle cx={AREA_W + 80} cy={H / 2} r="3" fill="#ffffff" />
      {/* Portería propia (rect pequeño en el borde izq) */}
      <rect x="0" y={H / 2 - 28} width="6" height="56" fill="#ffffff" />

      {/* Área RIVAL (derecha) */}
      <path d={`M ${W} ${(H - AREA_H) / 2}
                A ${AREA_W} ${AREA_H / 2} 0 0 0
                  ${W} ${(H + AREA_H) / 2}`}
        fill="none" stroke="#ffffff" strokeWidth="3" />
      <circle cx={W - AREA_W + 30} cy={H / 2} r="3" fill="#ffffff" />
      <circle cx={W - AREA_W - 80} cy={H / 2} r="3" fill="#ffffff" />
      <rect x={W - 6} y={H / 2 - 28} width="6" height="56" fill="#ffffff" />

      {/* Zona PROPIA (Z1) clicable — toda el área izquierda */}
      <g onClick={() => onSelect("Z1")} className="cursor-pointer">
        <path d={`M 0 ${(H - AREA_H) / 2}
                  A ${AREA_W} ${AREA_H / 2} 0 0 1
                    0 ${(H + AREA_H) / 2}
                  Z`}
          fill={sel("Z1") ? "#1d4ed8" : "#ffffff"}
          fillOpacity={sel("Z1") ? 0.55 : 0.05} />
        <text x={AREA_W / 2 - 10} y={H / 2 + 5}
          textAnchor="middle" fontSize="18" fontWeight="bold"
          fill={sel("Z1") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>Z1</text>
      </g>

      {/* Zona RIVAL (Z11) clicable */}
      <g onClick={() => onSelect("Z11")} className="cursor-pointer">
        <path d={`M ${W} ${(H - AREA_H) / 2}
                  A ${AREA_W} ${AREA_H / 2} 0 0 0
                    ${W} ${(H + AREA_H) / 2}
                  Z`}
          fill={sel("Z11") ? "#1d4ed8" : "#ffffff"}
          fillOpacity={sel("Z11") ? 0.55 : 0.05} />
        <text x={W - AREA_W / 2 + 10} y={H / 2 + 5}
          textAnchor="middle" fontSize="18" fontWeight="bold"
          fill={sel("Z11") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>Z11</text>
      </g>

      {/* 9 zonas centrales clicables */}
      {zonas.map((z) => {
        const isSel = sel(z.id);
        return (
          <g key={z.id} onClick={() => onSelect(z.id)} className="cursor-pointer">
            <rect x={z.x + 3} y={z.y + 3} width={z.w - 6} height={z.h - 6}
              fill={isSel ? "#1d4ed8" : "#ffffff"}
              fillOpacity={isSel ? 0.55 : 0.04}
              stroke={isSel ? "#3b82f6" : "#ffffff"}
              strokeOpacity={isSel ? 1 : 0.25}
              strokeWidth={isSel ? 3 : 1}
              rx="4" />
            <text x={z.x + z.w / 2} y={z.y + z.h / 2 + 7}
              textAnchor="middle" fontSize="20" fontWeight="bold"
              fill={isSel ? "#ffffff" : "#d4d4d8"}
              style={{ pointerEvents: "none" }}>{z.id}</text>
          </g>
        );
      })}

      {/* Indicador de dirección de ataque */}
      <text x={W - 40} y="20" textAnchor="end" fontSize="11" fill="#ffffff" opacity="0.6">
        Inter ataca →
      </text>
    </svg>
  );
}

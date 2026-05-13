"use client";

/**
 * Versión del Campo (mismas zonas A1-A11 y geometría) para visualizar
 * conteos por zona. Cada zona se rellena con verde cuya intensidad es
 * proporcional al total de disparos en esa zona, y sobreimpone el total
 * en grande + un mini-desglose por resultado (G/Pa/Pl/B/F).
 *
 * No es interactivo; solo lectura.
 */
import React from "react";

export type ResD = "GOL" | "PUERTA" | "PALO" | "FUERA" | "BLOQUEADO";

export type ContadorZona = {
  GOL: number;
  PUERTA: number;
  PALO: number;
  FUERA: number;
  BLOQUEADO: number;
  total: number;
};

interface Props {
  /** Mapa zona → conteo. Zonas A1..A11. */
  conteos: Record<string, ContadorZona>;
  /** Dirección de ataque visual. "der" por defecto. */
  direccion?: "izq" | "der";
  nombreAtacante?: string;
}

// Misma geometría que Campo.tsx
const M = 20;
const W = 40 * M;
const H = 20 * M;
const POSTE_SUP_Y = H / 2 - 1.5 * M;
const POSTE_INF_Y = H / 2 + 1.5 * M;
const R_AREA = 6 * M;
const AREA_BORDE_X = W - R_AREA;
const BANDA_SUP_Y = 2.5 * M;
const BANDA_INF_Y = H - 2.5 * M;
const X_10 = W - 10 * M;
const X_MEDIA = W - 20 * M;
const Y_CENTRO = H / 2;

const LETRA_RES: Record<ResD, string> = {
  GOL: "G", PUERTA: "Pa", PALO: "Pl", BLOQUEADO: "B", FUERA: "F",
};
const ORDEN_RES: ResD[] = ["GOL", "PUERTA", "PALO", "BLOQUEADO", "FUERA"];

export function CampoConteos({ conteos, direccion = "der", nombreAtacante }: Props) {
  const flip = direccion === "izq";
  const gTransform = flip ? `rotate(180 ${W / 2} ${H / 2})` : undefined;
  const tT = (x: number, y: number) => flip ? `rotate(180 ${x} ${y})` : undefined;

  // Conteo máximo para escalar opacidad.
  const max = Math.max(1, ...Object.values(conteos).map((c) => c.total));
  // Opacidad: 0 disparos → 0 (verde sólo por el césped); >0 → 0.25 + 0.6 * pct
  const opZona = (z: string) => {
    const c = conteos[z];
    if (!c || c.total === 0) return 0;
    return 0.25 + 0.6 * (c.total / max);
  };

  // Paths del área (igual que Campo.tsx)
  const pathArea = `
    M ${W} ${BANDA_SUP_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${AREA_BORDE_X} ${POSTE_SUP_Y}
    L ${AREA_BORDE_X} ${POSTE_INF_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${W} ${BANDA_INF_Y}
  `.trim();
  const pathA1 = `
    M ${W} ${BANDA_SUP_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${AREA_BORDE_X} ${POSTE_SUP_Y}
    L ${AREA_BORDE_X} ${Y_CENTRO}
    L ${W} ${Y_CENTRO}
    Z
  `.trim();
  const pathA2 = `
    M ${W} ${Y_CENTRO}
    L ${AREA_BORDE_X} ${Y_CENTRO}
    L ${AREA_BORDE_X} ${POSTE_INF_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${W} ${BANDA_INF_Y}
    Z
  `.trim();
  const pathA4 = `
    M ${X_10} ${BANDA_SUP_Y}
    L ${W} ${BANDA_SUP_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${AREA_BORDE_X} ${POSTE_SUP_Y}
    L ${AREA_BORDE_X} ${Y_CENTRO}
    L ${X_10} ${Y_CENTRO}
    Z
  `.trim();
  const pathA5 = `
    M ${X_10} ${Y_CENTRO}
    L ${AREA_BORDE_X} ${Y_CENTRO}
    L ${AREA_BORDE_X} ${POSTE_INF_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${W} ${BANDA_INF_Y}
    L ${X_10} ${BANDA_INF_Y}
    Z
  `.trim();

  // Coordenadas (cx, cy) donde poner el TOTAL grande y el mini-desglose
  // de cada zona. Cogidas de los textos originales de Campo.tsx.
  const POS_Z: Record<string, { cx: number; cy: number }> = {
    A11: { cx: X_MEDIA / 2, cy: Y_CENTRO },
    A3:  { cx: X_10 + (W - X_10) / 2, cy: BANDA_SUP_Y / 2 + 5 },
    A6:  { cx: X_10 + (W - X_10) / 2, cy: BANDA_INF_Y + (H - BANDA_INF_Y) / 2 + 5 },
    A4:  { cx: (X_10 + AREA_BORDE_X) / 2 - 10, cy: (BANDA_SUP_Y + Y_CENTRO) / 2 + 6 },
    A5:  { cx: (X_10 + AREA_BORDE_X) / 2 - 10, cy: (Y_CENTRO + BANDA_INF_Y) / 2 + 6 },
    A7:  { cx: (X_MEDIA + X_10) / 2, cy: BANDA_SUP_Y / 2 + 5 },
    A10: { cx: (X_MEDIA + X_10) / 2, cy: BANDA_INF_Y + (H - BANDA_INF_Y) / 2 + 5 },
    A8:  { cx: (X_MEDIA + X_10) / 2, cy: (BANDA_SUP_Y + Y_CENTRO) / 2 + 8 },
    A9:  { cx: (X_MEDIA + X_10) / 2, cy: (Y_CENTRO + BANDA_INF_Y) / 2 + 8 },
    A1:  { cx: W - 50, cy: (BANDA_SUP_Y + Y_CENTRO) / 2 + 5 },
    A2:  { cx: W - 50, cy: (Y_CENTRO + BANDA_INF_Y) / 2 + 5 },
  };

  // Render del label de una zona: total grande + desglose en una línea.
  // Si no hay disparos, no se muestra nada (la zona queda vacía).
  const Label = ({ z, sizeTotal = 36 }: { z: string; sizeTotal?: number }) => {
    const c = conteos[z];
    const pos = POS_Z[z];
    if (!pos) return null;
    if (!c || c.total === 0) return null;
    return (
      <g style={{ pointerEvents: "none" }}>
        <text x={pos.cx} y={pos.cy - 2}
          transform={tT(pos.cx, pos.cy - 2)}
          textAnchor="middle" fontSize={sizeTotal} fontWeight="bold"
          fill="#ffffff"
          stroke="#0b0f0c" strokeWidth="1" paintOrder="stroke">
          {c.total}
        </text>
        <text x={pos.cx} y={pos.cy + sizeTotal * 0.55}
          transform={tT(pos.cx, pos.cy + sizeTotal * 0.55)}
          textAnchor="middle" fontSize={sizeTotal * 0.45} fontWeight="bold"
          fill="#fde68a"
          stroke="#0b0f0c" strokeWidth="0.8" paintOrder="stroke">
          {ORDEN_RES.filter((r) => c[r] > 0).map((r) => `${LETRA_RES[r]}${c[r]}`).join(" ")}
        </text>
      </g>
    );
  };

  // Helper: color verde proporcional, formato rgba para fillOpacity de SVG.
  const fillZona = (z: string) => {
    const op = opZona(z);
    if (op === 0) return { fill: "#ffffff", opacity: 0.04 };
    return { fill: "#10b981", opacity: op };
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none">
      <g transform={gTransform}>
        {/* Césped */}
        <rect x="0" y="0" width={W} height={H} fill="#1b5e20" rx="8" />
        {/* Borde exterior */}
        <rect x="2" y="2" width={W - 4} height={H - 4}
          fill="none" stroke="#ffffff" strokeWidth="3" rx="6" />
        {/* Línea media */}
        <line x1={X_MEDIA} y1="0" x2={X_MEDIA} y2={H} stroke="#ffffff" strokeWidth="3" />
        {/* Círculo central */}
        <circle cx={X_MEDIA} cy={Y_CENTRO} r={3 * M} fill="none" stroke="#ffffff" strokeWidth="2" />
        <circle cx={X_MEDIA} cy={Y_CENTRO} r="3" fill="#ffffff" />

        {/* ── ZONAS rellenas ── */}
        {/* A11 */}
        {(() => { const f = fillZona("A11"); return (
          <rect x="0" y="0" width={X_MEDIA} height={H}
            fill={f.fill} fillOpacity={f.opacity}
            stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        ); })()}
        {/* A3 */}
        {(() => { const f = fillZona("A3"); return (
          <rect x={X_10} y="0" width={W - X_10} height={BANDA_SUP_Y}
            fill={f.fill} fillOpacity={f.opacity}
            stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        ); })()}
        {/* A6 */}
        {(() => { const f = fillZona("A6"); return (
          <rect x={X_10} y={BANDA_INF_Y} width={W - X_10} height={H - BANDA_INF_Y}
            fill={f.fill} fillOpacity={f.opacity}
            stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        ); })()}
        {/* A4 */}
        {(() => { const f = fillZona("A4"); return (
          <path d={pathA4} fill={f.fill} fillOpacity={f.opacity}
            stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        ); })()}
        {/* A5 */}
        {(() => { const f = fillZona("A5"); return (
          <path d={pathA5} fill={f.fill} fillOpacity={f.opacity}
            stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        ); })()}
        {/* A7 */}
        {(() => { const f = fillZona("A7"); return (
          <rect x={X_MEDIA} y="0" width={X_10 - X_MEDIA} height={BANDA_SUP_Y}
            fill={f.fill} fillOpacity={f.opacity}
            stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        ); })()}
        {/* A10 */}
        {(() => { const f = fillZona("A10"); return (
          <rect x={X_MEDIA} y={BANDA_INF_Y} width={X_10 - X_MEDIA} height={H - BANDA_INF_Y}
            fill={f.fill} fillOpacity={f.opacity}
            stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        ); })()}
        {/* A8 */}
        {(() => { const f = fillZona("A8"); return (
          <rect x={X_MEDIA} y={BANDA_SUP_Y} width={X_10 - X_MEDIA} height={Y_CENTRO - BANDA_SUP_Y}
            fill={f.fill} fillOpacity={f.opacity}
            stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        ); })()}
        {/* A9 */}
        {(() => { const f = fillZona("A9"); return (
          <rect x={X_MEDIA} y={Y_CENTRO} width={X_10 - X_MEDIA} height={BANDA_INF_Y - Y_CENTRO}
            fill={f.fill} fillOpacity={f.opacity}
            stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        ); })()}
        {/* A1 */}
        {(() => { const f = fillZona("A1"); return (
          <path d={pathA1} fill={f.fill} fillOpacity={f.opacity} />
        ); })()}
        {/* A2 */}
        {(() => { const f = fillZona("A2"); return (
          <path d={pathA2} fill={f.fill} fillOpacity={f.opacity} />
        ); })()}

        {/* ── LÍNEAS DEL CAMPO encima ── */}
        <g style={{ pointerEvents: "none" }} fill="none" stroke="#ffffff" strokeWidth="2.5">
          <path d={pathArea} />
          <line x1={X_10} y1={Y_CENTRO} x2={AREA_BORDE_X} y2={Y_CENTRO}
            strokeDasharray="4 4" opacity="0.55" />
          <line x1={X_10} y1={BANDA_SUP_Y} x2={X_10} y2={BANDA_INF_Y}
            strokeDasharray="4 4" opacity="0.4" />
          <circle cx={AREA_BORDE_X} cy={Y_CENTRO} r="3" fill="#ffffff" stroke="none" />
          <circle cx={X_10} cy={Y_CENTRO} r="3" fill="#ffffff" stroke="none" />
          <rect x={W - 4} y={POSTE_SUP_Y} width="4" height={POSTE_INF_Y - POSTE_SUP_Y} fill="#ffffff" />
        </g>

        {/* ── Etiquetas (total + desglose) por zona ── */}
        <Label z="A11" sizeTotal={56} />
        <Label z="A3"  sizeTotal={22} />
        <Label z="A6"  sizeTotal={22} />
        <Label z="A4"  sizeTotal={36} />
        <Label z="A5"  sizeTotal={36} />
        <Label z="A7"  sizeTotal={22} />
        <Label z="A10" sizeTotal={22} />
        <Label z="A8"  sizeTotal={42} />
        <Label z="A9"  sizeTotal={42} />
        <Label z="A1"  sizeTotal={28} />
        <Label z="A2"  sizeTotal={28} />
      </g>

      <text x={flip ? W - 8 : 8} y="18"
        textAnchor={flip ? "end" : "start"} fontSize="11"
        fill="#ffffff" opacity="0.7">
        {flip
          ? `← ${nombreAtacante ?? "Atacante"} ataca`
          : `${nombreAtacante ?? "Atacante"} ataca →`}
      </text>
    </svg>
  );
}

"use client";

/**
 * Campo de fútbol sala con zonas clicables (zero-confirm).
 *
 * Pista 40m × 20m, dibujada VERTICAL con la portería rival arriba (es
 * hacia donde ataca el Inter en este dibujo) y la propia abajo. El
 * banquillo mira el campo así, por eso esta orientación.
 *
 * Las 11 zonas (A1..A11) están definidas por la geometría que Arkaitz
 * dictó (audio 2026-04-28):
 *
 *   A11 = toda la mitad propia (20m × 20m, parte inferior).
 *
 * En la mitad ofensiva (parte superior, 20m × 20m):
 *   - Portería rival, 3m de ancho, centrada en la línea de fondo arriba.
 *   - Área = cuartos de círculo de 6m radio desde cada poste + recta de
 *     3m a 6m de la línea de fondo.
 *   - A1 = mitad izquierda del área (mirando desde el centro hacia portería).
 *   - A2 = mitad derecha del área.
 *   - A3 = rectángulo 2,5m × 10m pegado a banda IZQUIERDA, primeros 10m
 *          desde la línea de fondo.
 *   - A6 = simétrico, banda DERECHA, primeros 10m.
 *   - A4 = zona central izquierda en la franja entre el área (6m) y los 10m.
 *          Limitada por A3 (a 2,5m de banda izq) y por una línea central
 *          vertical de 4m que va del centro a 10m hasta el centro del techo
 *          del área (6m).
 *   - A5 = simétrico, central derecha.
 *   - A7 = rectángulo 2,5m × 10m pegado a banda IZQUIERDA, segundos 10m
 *          (de 10m a 20m desde la línea de fondo).
 *   - A10 = simétrico, banda DERECHA.
 *   - A8 = rectángulo 7,5m × 10m, central izquierdo, entre A7 y A9.
 *   - A9 = central derecho, entre A8 y A10.
 *
 * Escala: 1m = 20px → pista 400px ancho × 800px alto.
 */
import React from "react";

interface Props {
  seleccionada?: string;
  onSelect: (zona: string) => void;
}

// Escala
const M = 20;          // 1m = 20px
const W = 20 * M;      // 400px (ancho 20m)
const H = 40 * M;      // 800px (alto 40m)

// Coordenadas clave (origen arriba izquierda):
// - Portería rival arriba: y=0, centrada en x=W/2, 3m ancho (60px)
const POSTE_IZ = W / 2 - 1.5 * M;   // 170
const POSTE_DR = W / 2 + 1.5 * M;   // 230
// - Área: cuartos de círculo de radio 6m (120px) desde cada poste
const R_AREA = 6 * M;               // 120
// - Borde inferior del área (recta de 3m paralela a fondo): y = 6m
const AREA_BORDE = 6 * M;           // 120
// - Banda 2,5m a cada lado
const BANDA_IZ = 2.5 * M;           // 50
const BANDA_DR = W - 2.5 * M;       // 350
// - Línea a 10m de la portería rival (franja "central")
const Y_10 = 10 * M;                // 200
// - Línea media del campo (20m)
const Y_MEDIA = 20 * M;             // 400
// - Centro de la mitad ofensiva (para la línea central de 4m que separa A4/A5)
const X_CENTRO = W / 2;             // 200
const Y_4M_TOP = 6 * M;             // 120 (mitad del techo del área)
const Y_4M_BOT = 10 * M;            // 200 (línea de 10m)

export function Campo({ seleccionada, onSelect }: Props) {
  const sel = (z: string) => seleccionada === z;
  const colorZona = (z: string) => sel(z) ? "#1d4ed8" : "#ffffff";
  const opZona = (z: string) => sel(z) ? 0.55 : 0.05;

  // Path del área rival (semicírculo con esquinas en cuartos de círculo):
  // Empieza en (BANDA_IZ, 0) → arco hasta (POSTE_IZ, AREA_BORDE) [cuarto izq]
  // → recta hasta (POSTE_DR, AREA_BORDE) [techo del área, 3m]
  // → arco hasta (BANDA_DR, 0) [cuarto der]
  // Pero ojo: la línea de fondo es y=0; el cuarto izq toca y=0 en x=BANDA_IZ
  // (=POSTE_IZ − 6m). En realidad PosteIz-6m = 170-120 = 50 = BANDA_IZ. ✓
  const pathArea = `
    M ${BANDA_IZ} 0
    A ${R_AREA} ${R_AREA} 0 0 1 ${POSTE_IZ} ${AREA_BORDE}
    L ${POSTE_DR} ${AREA_BORDE}
    A ${R_AREA} ${R_AREA} 0 0 1 ${BANDA_DR} 0
  `.trim();

  // Para clickabilidad, dividimos el área en dos paths (A1 izq, A2 der)
  // por la línea x = W/2.
  const pathA1 = `
    M ${BANDA_IZ} 0
    A ${R_AREA} ${R_AREA} 0 0 1 ${POSTE_IZ} ${AREA_BORDE}
    L ${X_CENTRO} ${AREA_BORDE}
    L ${X_CENTRO} 0
    Z
  `.trim();
  const pathA2 = `
    M ${X_CENTRO} 0
    L ${X_CENTRO} ${AREA_BORDE}
    L ${POSTE_DR} ${AREA_BORDE}
    A ${R_AREA} ${R_AREA} 0 0 1 ${BANDA_DR} 0
    Z
  `.trim();

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" style={{ maxHeight: "60vh" }}>
      {/* Césped */}
      <rect x="0" y="0" width={W} height={H} fill="#1b5e20" rx="8" />

      {/* Líneas exteriores */}
      <rect x="2" y="2" width={W - 4} height={H - 4}
        fill="none" stroke="#ffffff" strokeWidth="3" rx="6" />

      {/* Línea media */}
      <line x1="0" y1={Y_MEDIA} x2={W} y2={Y_MEDIA}
        stroke="#ffffff" strokeWidth="3" />
      {/* Círculo central */}
      <circle cx={W / 2} cy={Y_MEDIA} r={3 * M}
        fill="none" stroke="#ffffff" strokeWidth="2" />
      <circle cx={W / 2} cy={Y_MEDIA} r="3" fill="#ffffff" />

      {/* ── ZONAS (clicables) ── */}

      {/* A11 = mitad propia entera */}
      <g onClick={() => onSelect("A11")} className="cursor-pointer">
        <rect x="0" y={Y_MEDIA} width={W} height={H - Y_MEDIA}
          fill={colorZona("A11")} fillOpacity={opZona("A11")} />
        <text x={W / 2} y={Y_MEDIA + (H - Y_MEDIA) / 2 + 8}
          textAnchor="middle" fontSize="34" fontWeight="bold"
          fill={sel("A11") ? "#ffffff" : "#d4d4d8"} opacity="0.7"
          style={{ pointerEvents: "none" }}>A11</text>
        <text x={W / 2} y={Y_MEDIA + (H - Y_MEDIA) / 2 + 32}
          textAnchor="middle" fontSize="11"
          fill={sel("A11") ? "#ffffff" : "#a1a1aa"} opacity="0.7"
          style={{ pointerEvents: "none" }}>mitad propia</text>
      </g>

      {/* A3 = banda izq, primeros 10m */}
      <g onClick={() => onSelect("A3")} className="cursor-pointer">
        <rect x="0" y="0" width={BANDA_IZ} height={Y_10}
          fill={colorZona("A3")} fillOpacity={opZona("A3")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={BANDA_IZ / 2} y={Y_10 / 2 + 6}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A3") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A3</text>
      </g>

      {/* A6 = banda der, primeros 10m */}
      <g onClick={() => onSelect("A6")} className="cursor-pointer">
        <rect x={BANDA_DR} y="0" width={W - BANDA_DR} height={Y_10}
          fill={colorZona("A6")} fillOpacity={opZona("A6")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={BANDA_DR + (W - BANDA_DR) / 2} y={Y_10 / 2 + 6}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A6") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A6</text>
      </g>

      {/* A4 = central izq entre área y 10m */}
      {/* Polígono: (BANDA_IZ, AREA_BORDE) → (X_CENTRO, AREA_BORDE) → (X_CENTRO, Y_10) → (BANDA_IZ, Y_10) */}
      <g onClick={() => onSelect("A4")} className="cursor-pointer">
        <polygon points={`${BANDA_IZ},${AREA_BORDE} ${X_CENTRO},${AREA_BORDE} ${X_CENTRO},${Y_10} ${BANDA_IZ},${Y_10}`}
          fill={colorZona("A4")} fillOpacity={opZona("A4")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(BANDA_IZ + X_CENTRO) / 2} y={(AREA_BORDE + Y_10) / 2 + 6}
          textAnchor="middle" fontSize="16" fontWeight="bold"
          fill={sel("A4") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A4</text>
      </g>

      {/* A5 = central der entre área y 10m */}
      <g onClick={() => onSelect("A5")} className="cursor-pointer">
        <polygon points={`${X_CENTRO},${AREA_BORDE} ${BANDA_DR},${AREA_BORDE} ${BANDA_DR},${Y_10} ${X_CENTRO},${Y_10}`}
          fill={colorZona("A5")} fillOpacity={opZona("A5")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(X_CENTRO + BANDA_DR) / 2} y={(AREA_BORDE + Y_10) / 2 + 6}
          textAnchor="middle" fontSize="16" fontWeight="bold"
          fill={sel("A5") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A5</text>
      </g>

      {/* A7 = banda izq, segundos 10m */}
      <g onClick={() => onSelect("A7")} className="cursor-pointer">
        <rect x="0" y={Y_10} width={BANDA_IZ} height={Y_MEDIA - Y_10}
          fill={colorZona("A7")} fillOpacity={opZona("A7")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={BANDA_IZ / 2} y={(Y_10 + Y_MEDIA) / 2 + 6}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A7") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A7</text>
      </g>

      {/* A10 = banda der, segundos 10m */}
      <g onClick={() => onSelect("A10")} className="cursor-pointer">
        <rect x={BANDA_DR} y={Y_10} width={W - BANDA_DR} height={Y_MEDIA - Y_10}
          fill={colorZona("A10")} fillOpacity={opZona("A10")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={BANDA_DR + (W - BANDA_DR) / 2} y={(Y_10 + Y_MEDIA) / 2 + 6}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A10") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A10</text>
      </g>

      {/* A8 = central izq, 10m-20m */}
      <g onClick={() => onSelect("A8")} className="cursor-pointer">
        <rect x={BANDA_IZ} y={Y_10} width={X_CENTRO - BANDA_IZ} height={Y_MEDIA - Y_10}
          fill={colorZona("A8")} fillOpacity={opZona("A8")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(BANDA_IZ + X_CENTRO) / 2} y={(Y_10 + Y_MEDIA) / 2 + 7}
          textAnchor="middle" fontSize="20" fontWeight="bold"
          fill={sel("A8") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A8</text>
      </g>

      {/* A9 = central der, 10m-20m */}
      <g onClick={() => onSelect("A9")} className="cursor-pointer">
        <rect x={X_CENTRO} y={Y_10} width={BANDA_DR - X_CENTRO} height={Y_MEDIA - Y_10}
          fill={colorZona("A9")} fillOpacity={opZona("A9")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(X_CENTRO + BANDA_DR) / 2} y={(Y_10 + Y_MEDIA) / 2 + 7}
          textAnchor="middle" fontSize="20" fontWeight="bold"
          fill={sel("A9") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A9</text>
      </g>

      {/* A1 = mitad izquierda del área rival */}
      <g onClick={() => onSelect("A1")} className="cursor-pointer">
        <path d={pathA1}
          fill={colorZona("A1")} fillOpacity={opZona("A1")} />
        <text x={(BANDA_IZ + X_CENTRO) / 2 - 5} y={AREA_BORDE / 2 + 25}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A1") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A1</text>
      </g>

      {/* A2 = mitad derecha del área rival */}
      <g onClick={() => onSelect("A2")} className="cursor-pointer">
        <path d={pathA2}
          fill={colorZona("A2")} fillOpacity={opZona("A2")} />
        <text x={(X_CENTRO + BANDA_DR) / 2 + 5} y={AREA_BORDE / 2 + 25}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A2") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A2</text>
      </g>

      {/* ── LÍNEAS DEL CAMPO (encima de las zonas, sin pointerEvents) ── */}
      <g style={{ pointerEvents: "none" }}
        fill="none" stroke="#ffffff" strokeWidth="2.5">
        {/* Área rival (contorno) */}
        <path d={pathArea} />
        {/* Línea central de 4m que separa A4 de A5 */}
        <line x1={X_CENTRO} y1={Y_4M_TOP} x2={X_CENTRO} y2={Y_4M_BOT}
          strokeDasharray="4 4" opacity="0.55" />
        {/* Línea a 10m (paralela a portería rival) — punteada para no liar con área */}
        <line x1={BANDA_IZ} y1={Y_10} x2={BANDA_DR} y2={Y_10}
          strokeDasharray="4 4" opacity="0.4" />
        {/* Punto de penalti rival (6m) */}
        <circle cx={W / 2} cy={6 * M} r="3" fill="#ffffff" stroke="none" />
        {/* Punto de doble penalti rival (10m) */}
        <circle cx={W / 2} cy={10 * M} r="3" fill="#ffffff" stroke="none" />

        {/* Misma geometría reflejada para la portería propia (en A11),
            decorativa, no clicable. */}
        <path d={`
          M ${BANDA_IZ} ${H}
          A ${R_AREA} ${R_AREA} 0 0 0 ${POSTE_IZ} ${H - AREA_BORDE}
          L ${POSTE_DR} ${H - AREA_BORDE}
          A ${R_AREA} ${R_AREA} 0 0 0 ${BANDA_DR} ${H}
        `.trim()} />
        <circle cx={W / 2} cy={H - 6 * M} r="3" fill="#ffffff" stroke="none" />
        <circle cx={W / 2} cy={H - 10 * M} r="3" fill="#ffffff" stroke="none" />

        {/* Porterías (rectángulo blanco fino al borde) */}
        <rect x={POSTE_IZ} y="0" width={POSTE_DR - POSTE_IZ} height="4" fill="#ffffff" />
        <rect x={POSTE_IZ} y={H - 4} width={POSTE_DR - POSTE_IZ} height="4" fill="#ffffff" />
      </g>

      {/* Etiqueta "Inter ataca ↑" */}
      <text x={W - 8} y={Y_MEDIA - 8} textAnchor="end" fontSize="11"
        fill="#ffffff" opacity="0.5">Inter ataca ↑</text>
    </svg>
  );
}

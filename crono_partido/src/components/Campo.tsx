"use client";

/**
 * Campo de fútbol sala HORIZONTAL con zonas clicables (zero-confirm).
 *
 * ⚠️ REGLA FIJA: el campo se dibuja SIEMPRE en HORIZONTAL (40m × 20m,
 *    proporción 2:1). NUNCA en vertical. Lo único que cambia entre
 *    contextos es a qué lado apunta el atacante (izq o der), pero la
 *    orientación general es siempre horizontal.
 *
 * Pista 40m × 20m. La dirección de ataque va hacia la DERECHA (default).
 * La portería rival está a la derecha (x=W); la propia a la izquierda.
 *
 * Como las zonas A1-A11 son relativas al equipo que ataca:
 *  - A3 = "banda izquierda" del atacante.
 *    Mirando hacia la portería rival (derecha), tu izquierda visual es
 *    la banda SUPERIOR del dibujo. Así que A3 está arriba.
 *  - A6 = banda derecha del atacante → banda INFERIOR del dibujo.
 *  - A1 = mitad izquierda del área (del atacante) → mitad superior del área.
 *  - A2 = mitad derecha del área → mitad inferior.
 *
 * Geometría exacta (audio de Arkaitz, 2026-04-28):
 *  - Portería rival 3m centrada en la línea de fondo derecha.
 *  - Área = cuartos de círculo radio 6m con CENTRO EN CADA POSTE +
 *    recta de 3m a 6m de la línea de fondo (paralela a ella).
 *  - A11 = TODA la mitad del campo opuesta (mitad izquierda del dibujo).
 *
 * Escala: 1m = 20px → SVG 800px × 400px.
 */
import React from "react";

interface Props {
  seleccionada?: string;
  onSelect: (zona: string) => void;
  nombreAtacante?: string;
}

// Escala
const M = 20;
const W = 40 * M;   // 800
const H = 20 * M;   // 400

// Portería rival a la derecha, centrada en y = H/2
const POSTE_SUP_Y = H / 2 - 1.5 * M;   // 170
const POSTE_INF_Y = H / 2 + 1.5 * M;   // 230

// Área: cuartos de círculo 6m desde cada poste; techo a 6m de la línea de fondo derecha
const R_AREA = 6 * M;                  // 120
const AREA_BORDE_X = W - R_AREA;       // 680  (techo del área, paralelo a portería)

// Bandas 2,5m
const BANDA_SUP_Y = 2.5 * M;           // 50
const BANDA_INF_Y = H - 2.5 * M;       // 350

// Línea a 10m de la portería rival
const X_10 = W - 10 * M;               // 600

// Línea media del campo (a 20m de cada portería)
const X_MEDIA = W - 20 * M;            // 400

// Centro vertical del campo (para dividir A1/A2 y la línea de 4m central)
const Y_CENTRO = H / 2;                // 200

export function Campo({ seleccionada, onSelect, nombreAtacante }: Props) {
  const sel = (z: string) => seleccionada === z;
  const colorZona = (z: string) => sel(z) ? "#1d4ed8" : "#ffffff";
  const opZona = (z: string) => sel(z) ? 0.55 : 0.05;

  // Path del CONTORNO del área (línea blanca, no clicable).
  // Recorrido: esquina sup derecha → arco → techo (recta) → arco → esquina inf derecha.
  // Ambos arcos con CENTRO en su respectivo POSTE (sweep=0 en SVG con Y abajo).
  const pathArea = `
    M ${W} ${BANDA_SUP_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${AREA_BORDE_X} ${POSTE_SUP_Y}
    L ${AREA_BORDE_X} ${POSTE_INF_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${W} ${BANDA_INF_Y}
  `.trim();

  // A1 = mitad SUPERIOR del área (izquierda del atacante).
  // Polígono cerrado: (W, BANDA_SUP_Y) → arco → (AREA_BORDE_X, POSTE_SUP_Y)
  //                  → (AREA_BORDE_X, Y_CENTRO) → (W, Y_CENTRO) → close.
  const pathA1 = `
    M ${W} ${BANDA_SUP_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${AREA_BORDE_X} ${POSTE_SUP_Y}
    L ${AREA_BORDE_X} ${Y_CENTRO}
    L ${W} ${Y_CENTRO}
    Z
  `.trim();

  // A2 = mitad INFERIOR del área.
  const pathA2 = `
    M ${W} ${Y_CENTRO}
    L ${AREA_BORDE_X} ${Y_CENTRO}
    L ${AREA_BORDE_X} ${POSTE_INF_Y}
    A ${R_AREA} ${R_AREA} 0 0 0 ${W} ${BANDA_INF_Y}
    Z
  `.trim();

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" style={{ maxHeight: "60vh" }}>
      {/* Césped */}
      <rect x="0" y="0" width={W} height={H} fill="#1b5e20" rx="8" />

      {/* Borde exterior */}
      <rect x="2" y="2" width={W - 4} height={H - 4}
        fill="none" stroke="#ffffff" strokeWidth="3" rx="6" />

      {/* Línea media (vertical) */}
      <line x1={X_MEDIA} y1="0" x2={X_MEDIA} y2={H}
        stroke="#ffffff" strokeWidth="3" />
      {/* Círculo central */}
      <circle cx={X_MEDIA} cy={Y_CENTRO} r={3 * M}
        fill="none" stroke="#ffffff" strokeWidth="2" />
      <circle cx={X_MEDIA} cy={Y_CENTRO} r="3" fill="#ffffff" />

      {/* ── ZONAS ── */}

      {/* A11 = TODA la mitad izquierda */}
      <g onClick={() => onSelect("A11")} className="cursor-pointer">
        <rect x="0" y="0" width={X_MEDIA} height={H}
          fill={colorZona("A11")} fillOpacity={opZona("A11")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={X_MEDIA / 2} y={Y_CENTRO + 18}
          textAnchor="middle" fontSize="56" fontWeight="bold"
          fill={sel("A11") ? "#ffffff" : "#d4d4d8"} opacity="0.85"
          style={{ pointerEvents: "none" }}>A11</text>
        <text x={X_MEDIA / 2} y={Y_CENTRO + 42}
          textAnchor="middle" fontSize="11"
          fill={sel("A11") ? "#ffffff" : "#a1a1aa"} opacity="0.7"
          style={{ pointerEvents: "none" }}>todo el medio campo defensivo</text>
      </g>

      {/* A3 = banda IZQUIERDA del atacante = banda SUPERIOR del dibujo, primeros 10m */}
      <g onClick={() => onSelect("A3")} className="cursor-pointer">
        <rect x={X_10} y="0" width={W - X_10} height={BANDA_SUP_Y}
          fill={colorZona("A3")} fillOpacity={opZona("A3")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={X_10 + (W - X_10) / 2} y={BANDA_SUP_Y / 2 + 5}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A3") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A3</text>
      </g>

      {/* A6 = banda derecha del atacante = banda INFERIOR del dibujo, primeros 10m */}
      <g onClick={() => onSelect("A6")} className="cursor-pointer">
        <rect x={X_10} y={BANDA_INF_Y} width={W - X_10} height={H - BANDA_INF_Y}
          fill={colorZona("A6")} fillOpacity={opZona("A6")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={X_10 + (W - X_10) / 2} y={BANDA_INF_Y + (H - BANDA_INF_Y) / 2 + 5}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A6") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A6</text>
      </g>

      {/* A4 = central SUP entre área y 10m (4m horizontal × 7.5m vertical) */}
      <g onClick={() => onSelect("A4")} className="cursor-pointer">
        <rect x={X_10} y={BANDA_SUP_Y} width={AREA_BORDE_X - X_10} height={Y_CENTRO - BANDA_SUP_Y}
          fill={colorZona("A4")} fillOpacity={opZona("A4")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(X_10 + AREA_BORDE_X) / 2} y={(BANDA_SUP_Y + Y_CENTRO) / 2 + 6}
          textAnchor="middle" fontSize="16" fontWeight="bold"
          fill={sel("A4") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A4</text>
      </g>

      {/* A5 = central INF entre área y 10m */}
      <g onClick={() => onSelect("A5")} className="cursor-pointer">
        <rect x={X_10} y={Y_CENTRO} width={AREA_BORDE_X - X_10} height={BANDA_INF_Y - Y_CENTRO}
          fill={colorZona("A5")} fillOpacity={opZona("A5")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(X_10 + AREA_BORDE_X) / 2} y={(Y_CENTRO + BANDA_INF_Y) / 2 + 6}
          textAnchor="middle" fontSize="16" fontWeight="bold"
          fill={sel("A5") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A5</text>
      </g>

      {/* A7 = banda SUP, segundos 10m (de 10m a 20m de portería rival) */}
      <g onClick={() => onSelect("A7")} className="cursor-pointer">
        <rect x={X_MEDIA} y="0" width={X_10 - X_MEDIA} height={BANDA_SUP_Y}
          fill={colorZona("A7")} fillOpacity={opZona("A7")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(X_MEDIA + X_10) / 2} y={BANDA_SUP_Y / 2 + 5}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A7") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A7</text>
      </g>

      {/* A10 = banda INF, segundos 10m */}
      <g onClick={() => onSelect("A10")} className="cursor-pointer">
        <rect x={X_MEDIA} y={BANDA_INF_Y} width={X_10 - X_MEDIA} height={H - BANDA_INF_Y}
          fill={colorZona("A10")} fillOpacity={opZona("A10")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(X_MEDIA + X_10) / 2} y={BANDA_INF_Y + (H - BANDA_INF_Y) / 2 + 5}
          textAnchor="middle" fontSize="14" fontWeight="bold"
          fill={sel("A10") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A10</text>
      </g>

      {/* A8 = central SUP, segundos 10m (10m horizontal × 7.5m vertical) */}
      <g onClick={() => onSelect("A8")} className="cursor-pointer">
        <rect x={X_MEDIA} y={BANDA_SUP_Y} width={X_10 - X_MEDIA} height={Y_CENTRO - BANDA_SUP_Y}
          fill={colorZona("A8")} fillOpacity={opZona("A8")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(X_MEDIA + X_10) / 2} y={(BANDA_SUP_Y + Y_CENTRO) / 2 + 8}
          textAnchor="middle" fontSize="22" fontWeight="bold"
          fill={sel("A8") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A8</text>
      </g>

      {/* A9 = central INF, segundos 10m */}
      <g onClick={() => onSelect("A9")} className="cursor-pointer">
        <rect x={X_MEDIA} y={Y_CENTRO} width={X_10 - X_MEDIA} height={BANDA_INF_Y - Y_CENTRO}
          fill={colorZona("A9")} fillOpacity={opZona("A9")}
          stroke="#ffffff" strokeOpacity={0.3} strokeWidth="1" />
        <text x={(X_MEDIA + X_10) / 2} y={(Y_CENTRO + BANDA_INF_Y) / 2 + 8}
          textAnchor="middle" fontSize="22" fontWeight="bold"
          fill={sel("A9") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A9</text>
      </g>

      {/* A1 = mitad SUP del área (izquierda del atacante) */}
      <g onClick={() => onSelect("A1")} className="cursor-pointer">
        <path d={pathA1}
          fill={colorZona("A1")} fillOpacity={opZona("A1")} />
        <text x={W - 50} y={(BANDA_SUP_Y + Y_CENTRO) / 2 + 5}
          textAnchor="middle" fontSize="16" fontWeight="bold"
          fill={sel("A1") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A1</text>
      </g>

      {/* A2 = mitad INF del área (derecha del atacante) */}
      <g onClick={() => onSelect("A2")} className="cursor-pointer">
        <path d={pathA2}
          fill={colorZona("A2")} fillOpacity={opZona("A2")} />
        <text x={W - 50} y={(Y_CENTRO + BANDA_INF_Y) / 2 + 5}
          textAnchor="middle" fontSize="16" fontWeight="bold"
          fill={sel("A2") ? "#ffffff" : "#d4d4d8"}
          style={{ pointerEvents: "none" }}>A2</text>
      </g>

      {/* ── LÍNEAS DEL CAMPO (encima, sin pointerEvents) ── */}
      <g style={{ pointerEvents: "none" }}
        fill="none" stroke="#ffffff" strokeWidth="2.5">
        {/* Borde del área (contorno con cuartos de círculo) */}
        <path d={pathArea} />
        {/* Línea central de 4m que separa A4 de A5
            (paralela a la banda, en el centro horizontal de la mitad ofensiva) */}
        <line x1={X_10} y1={Y_CENTRO} x2={AREA_BORDE_X} y2={Y_CENTRO}
          strokeDasharray="4 4" opacity="0.55" />
        {/* Línea a 10m (paralela a la portería rival) */}
        <line x1={X_10} y1={BANDA_SUP_Y} x2={X_10} y2={BANDA_INF_Y}
          strokeDasharray="4 4" opacity="0.4" />
        {/* Punto penalti 6m */}
        <circle cx={AREA_BORDE_X} cy={Y_CENTRO} r="3" fill="#ffffff" stroke="none" />
        {/* Punto doble penalti 10m */}
        <circle cx={X_10} cy={Y_CENTRO} r="3" fill="#ffffff" stroke="none" />
        {/* Portería atacada (derecha) */}
        <rect x={W - 4} y={POSTE_SUP_Y} width="4" height={POSTE_INF_Y - POSTE_SUP_Y} fill="#ffffff" />
      </g>

      {/* Etiqueta del atacante */}
      <text x="8" y="18" textAnchor="start" fontSize="11"
        fill="#ffffff" opacity="0.55">
        {nombreAtacante ? `${nombreAtacante} ataca →` : "Atacante →"}
      </text>
    </svg>
  );
}

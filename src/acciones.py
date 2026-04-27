"""
Catálogo cerrado de tipos de acción de gol y normalizador.

Las hojas de partido escriben acciones en formatos variables:
  - "AF.4x4", "AF.CONTRAATAQUE", "AF.BANDA"
  - "EC.4x4", "EC.CONTRAATQUE" (con typo)
  - "INC. PORTERO", "Inc Portero"
  - etc.

Aquí lo aplanamos a un nombre CANÓNICO. La dirección (favor/contra) la
lleva la columna `equipo_marca` (INTER/RIVAL), no se mezcla con la
acción.

Excepción: la acción nº 14 es distinta en AF y EC (Robo vs Pérdida en
incorporación de portero), por lo que esos dos nombres canónicos
existen y se distinguen.
"""
from __future__ import annotations

import re
import unicodedata


# ── Catálogo canónico ────────────────────────────────────────────────────────
ACCIONES_AF: list[str] = [
    "Banda", "Córner", "Falta", "Saque de Centro", "2ª jugada de ABP",
    "10 metros", "Penalti", "Falta sin barrera", "Ataque Posicional 4x4",
    "1x1 en banda", "Salida de presión", "2ª jugada",
    "Incorporación del portero", "Robo en incorporación de portero",
    "5x4", "4x5", "4x3", "3x4", "Contraataque",
    "Robo en zona alta", "No calificado",
]

ACCIONES_EC: list[str] = [
    "Banda", "Córner", "Falta", "Saque de Centro", "2ª jugada de ABP",
    "10 metros", "Penalti", "Falta sin barrera", "Ataque Posicional 4x4",
    "1x1 en banda", "Salida de presión", "2ª jugada",
    "Incorporación del portero", "Pérdida en incorporación de portero",
    "5x4", "4x5", "4x3", "3x4", "Contraataque",
    "Robo en zona alta", "No calificado",
]

ACCIONES_TODAS: list[str] = sorted(set(ACCIONES_AF) | set(ACCIONES_EC))


# ── Mapeo bruto → canónico ───────────────────────────────────────────────────
# Las claves se comparan tras normalizar (uppercase, sin tildes, sin puntos
# extra ni espacios múltiples).
_CANONICO: dict[str, str] = {
    # Banda / 1x1 en banda
    "BANDA": "Banda",
    "1X1 EN BANDA": "1x1 en banda",
    "1X1 BANDA": "1x1 en banda",
    # Córner
    "CORNER": "Córner",
    "CÓRNER": "Córner",
    # Falta
    "FALTA": "Falta",
    "FALTA SIN BARRERA": "Falta sin barrera",
    "FSB": "Falta sin barrera",
    # Saque de centro
    "SAQUE DE CENTRO": "Saque de Centro",
    "SAQUE CENTRO": "Saque de Centro",
    "SQ CENTRO": "Saque de Centro",
    "SQ.CENTRO": "Saque de Centro",
    "SQ.CENT": "Saque de Centro",
    # 2ª jugada de ABP
    "2A JUGADA DE ABP": "2ª jugada de ABP",
    "2ª JUGADA DE ABP": "2ª jugada de ABP",
    "ABP 2A JUGADA": "2ª jugada de ABP",
    "ABP 2ª JUGADA": "2ª jugada de ABP",
    "ABP 2A": "2ª jugada de ABP",
    # 10 metros
    "10 METROS": "10 metros",
    "10M": "10 metros",
    "10 M": "10 metros",
    # Penalti
    "PENALTI": "Penalti",
    "P": "Penalti",
    # 4x4 y otras situaciones numéricas
    "4X4": "Ataque Posicional 4x4",
    "AP 4X4": "Ataque Posicional 4x4",
    "ATAQUE POSICIONAL 4X4": "Ataque Posicional 4x4",
    "5X4": "5x4",
    "4X5": "4x5",
    "4X3": "4x3",
    "3X4": "3x4",
    # Salida y 2ª jugada
    "SALIDA DE PRESION": "Salida de presión",
    "SALIDA DE PRESIÓN": "Salida de presión",
    "SALIDA PRESION": "Salida de presión",
    "2A JUGADA": "2ª jugada",
    "2ª JUGADA": "2ª jugada",
    # Incorporación del portero
    "INCORPORACION DEL PORTERO": "Incorporación del portero",
    "INCORPORACIÓN DEL PORTERO": "Incorporación del portero",
    "INC PORTERO": "Incorporación del portero",
    "INC. PORTERO": "Incorporación del portero",
    "INC PORT": "Incorporación del portero",
    # Robo (solo AF)
    "ROBO EN INCORPORACION DE PORTERO": "Robo en incorporación de portero",
    "ROBO INCORPORACION PORTERO": "Robo en incorporación de portero",
    "ROBO INC PORT": "Robo en incorporación de portero",
    # Pérdida (solo EC)
    "PERDIDA EN INCORPORACION DE PORTERO": "Pérdida en incorporación de portero",
    "PERDIDA INCORPORACION PORTERO": "Pérdida en incorporación de portero",
    "PERDIDA INC PORT": "Pérdida en incorporación de portero",
    # Contraataque
    "CONTRAATAQUE": "Contraataque",
    "CONTRAATQUE": "Contraataque",  # typo del archivo
    "CONTRA": "Contraataque",
    # Robo zona alta
    "ROBO EN ZONA ALTA": "Robo en zona alta",
    "ROBO ZONA ALTA": "Robo en zona alta",
    "ROBO Z ALTA": "Robo en zona alta",
    "ROBO ZA": "Robo en zona alta",
    # No calificado
    "NO CALIFICADO": "No calificado",
    "N C": "No calificado",
    "NC": "No calificado",
}


def _normalizar_clave(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s.strip().upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Quitar prefijos típicos del archivo
    s = re.sub(r"^(?:A\.?F\.?|E\.?C\.?)\s*[\.\s:]*", "", s)
    # Quitar puntos sueltos y colapsar espacios
    s = s.replace(".", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalizar_accion(raw: str, equipo_marca: str = "") -> str:
    """Devuelve el nombre canónico para una acción.

    Parámetros:
      raw           — texto bruto del Excel (ej. "AF.4x4", "EC.PERDIDA INC PORT").
      equipo_marca  — "INTER" o "RIVAL". Usado solo para desambiguar
                      "Incorporación del portero" → si AF y la
                      raw incluye "ROBO" lo lleva al canónico AF;
                      si EC y la raw incluye "PERDIDA" → canónico EC.
                      Si no incluye ninguna pista, se queda en
                      "Incorporación del portero" (genérico).

    Devuelve el canónico, o el raw original si no se reconoce.
    """
    if not raw:
        return "No calificado"
    clave = _normalizar_clave(raw)
    if not clave:
        return "No calificado"

    # Ajuste contextual para incorporación
    raw_up = raw.upper()
    if "INCORPORACION" in clave or "INC PORT" in clave:
        if "ROBO" in raw_up:
            return "Robo en incorporación de portero"
        if "PERDIDA" in raw_up or "PÉRDIDA" in raw_up:
            return "Pérdida en incorporación de portero"
        return "Incorporación del portero"

    return _CANONICO.get(clave, raw.strip())


def es_canonica(s: str) -> bool:
    return s in ACCIONES_TODAS

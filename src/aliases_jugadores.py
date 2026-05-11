"""
aliases_jugadores.py — Punto único de verdad para normalización de
nombres de jugadores. Cualquier código del proyecto que necesite mapear
'Herrero', 'J.Herrero', 'Jose Herrero' al canónico debe usar
`norm_jugador()` o importar `ALIASES_JUGADOR` desde aquí.

Decisión de canónicos (mayo 2026):
  - Versión SIN punto y SIN inicial cuando sea posible.
  - Coincide con cómo aparecen los nombres en BORG (consolidado de los
    Forms PRE/POST que rellenan los jugadores).
  - Roster oficial JUGADORES_ROSTER se ha actualizado a estos canónicos.

Canónicos:
  J.HERRERO   → HERRERO
  J.GARCIA    → GARCIA
  GONZA       → GONZALO

Resto del roster sin cambios (CECILIO, CHAGUINHA, RAUL, HARRISON, RAYA,
JAVI, PANI, PIRATA, BARONA, CARLOS, OSCAR, RUBIO, JAIME, SEGO, DANI,
PABLO, GABRI, NACHO).
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable, Optional


# ── Lista de canónicos del roster (mayúsculas, sin acentos ni puntos) ──
ROSTER_CANONICO: set[str] = {
    # Porteros
    "HERRERO", "GARCIA", "OSCAR",
    # Campo primer equipo
    "CECILIO", "CHAGUINHA", "RAUL", "HARRISON", "RAYA", "JAVI",
    "PANI", "PIRATA", "BARONA", "CARLOS",
    # Filial campo
    "RUBIO", "JAIME", "SEGO", "DANI", "GONZALO", "PABLO", "GABRI",
    "NACHO",
}

# Porteros (subset)
PORTEROS_CANONICO: set[str] = {"HERRERO", "GARCIA", "OSCAR"}


# ── Diccionario de aliases ────────────────────────────────────────────
# Clave = versión escrita (upper, sin espacios sobrantes).
# Valor = canónico exacto del roster.
# Si el canónico ya está aquí también (HERRERO→HERRERO), es OK por
# defensividad: si el usuario escribe el canónico, sale el canónico.
ALIASES_JUGADOR: dict[str, str] = {
    # Porteros 1er equipo
    "J.HERRERO": "HERRERO",
    "J HERRERO": "HERRERO",
    "JOSE HERRERO": "HERRERO",
    "JOSÉ HERRERO": "HERRERO",
    "HERRERO": "HERRERO",
    "J.GARCIA": "GARCIA",
    "J GARCIA": "GARCIA",
    "JAVI GARCIA": "GARCIA",
    "JAVIER GARCIA": "GARCIA",
    "GARCIA": "GARCIA",
    # Campo primer equipo
    "CHAGAS": "CHAGUINHA",
    "CHAGINHA": "CHAGUINHA",
    "JAVI MINGUEZ": "JAVI",
    "JAVI MÍNGUEZ": "JAVI",
    "JAVIER MINGUEZ": "JAVI",
    "JAVIER MÍNGUEZ": "JAVI",
    "JAVIER": "JAVI",
    # Filial / cambios de mote
    "GONZA": "GONZALO",
    "GONZALEZ": "GONZALO",
    "SERGIO": "RUBIO",
    "VIZUETE": "RUBIO",
    "SERGIO VIZUETE": "RUBIO",
    "SEGOVIA": "SEGO",
    "DAVID SEGOVIA": "SEGO",
}


def _strip_norm(nombre: str) -> str:
    """Normaliza: upper + sin espacios extras + sin acentos básicos."""
    if not nombre:
        return ""
    s = str(nombre).strip().upper()
    # Quitar acentos
    sustituciones = {
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
        "Ñ": "N",
    }
    for k, v in sustituciones.items():
        s = s.replace(k, v)
    return s


def norm_jugador(nombre: str,
                 roster: Optional[Iterable[str]] = None,
                 fuzzy_threshold: float = 0.85) -> str:
    """Devuelve el nombre canónico del jugador.

    Estrategia:
      1. Si está vacío, devuelve "".
      2. Normaliza upper+strip+sin acentos.
      3. Si está en ALIASES_JUGADOR, devuelve el mapeo.
      4. Si está en `roster` (custom o ROSTER_CANONICO por defecto), OK.
      5. Fuzzy match (SequenceMatcher) sobre el roster con umbral.
      6. Si nada matchea, devuelve el nombre normalizado tal cual.

    Pasa `roster=None` para usar ROSTER_CANONICO oficial.
    """
    if not nombre:
        return ""
    n = _strip_norm(nombre)
    if not n:
        return ""
    # Alias directo
    if n in ALIASES_JUGADOR:
        return ALIASES_JUGADOR[n]
    # Roster custom o por defecto
    rset = set(roster) if roster else ROSTER_CANONICO
    if n in rset:
        return n
    # Fuzzy fallback
    mejor_match = None
    mejor_score = 0.0
    for canon in rset:
        score = SequenceMatcher(None, n, canon).ratio()
        if score > mejor_score:
            mejor_score = score
            mejor_match = canon
    if mejor_match and mejor_score >= fuzzy_threshold:
        return mejor_match
    return n


def es_portero(nombre: str) -> bool:
    """True si el nombre (en cualquier forma) corresponde a un portero."""
    return norm_jugador(nombre) in PORTEROS_CANONICO


def es_jugador_conocido(nombre: str) -> bool:
    """True si tras normalizar coincide con un jugador del roster oficial."""
    return norm_jugador(nombre) in ROSTER_CANONICO


# Set de "viejos" canónicos (J.HERRERO/J.GARCIA/GONZA) para detectar
# datos antiguos que aún no se han migrado.
NOMBRES_LEGACY: set[str] = {"J.HERRERO", "J.GARCIA", "GONZA"}

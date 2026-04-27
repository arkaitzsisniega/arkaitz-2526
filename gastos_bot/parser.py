"""
Parsea un mensaje de texto libre o transcripción de voz a un gasto.

Ejemplos que debe manejar:
  - "acabo de gastarme en el Lidl 15,85 euros"
  - "cena en restaurante 23 euros"
  - "lidl 15.85"
  - "23€ cena restaurante"
  - "gasolina, 50"

Devuelve dict con:
  - cantidad (float) o None si no se ha detectado
  - concepto (str) — texto sin la cantidad ni muletillas
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Patrones para detectar la cantidad. Permitimos:
#   - "15", "15.85", "15,85"
#   - opcionalmente seguido de €, euro, euros, eur
NUM = r"(\d{1,5}(?:[.,]\d{1,2})?)"
UNIDAD = r"(?:\s*(?:€|eur|euros?|pavos?|pelas?))?"

PATRON_CANTIDAD = re.compile(rf"\b{NUM}{UNIDAD}\b", re.IGNORECASE)

# Muletillas a limpiar del concepto
MULETILLAS = [
    r"acabo de gastar(?:me)?(?:\s+en)?",
    r"me he gastado(?:\s+en)?",
    r"he gastado(?:\s+en)?",
    r"hemos gastado(?:\s+en)?",
    r"acabamos de gastar(?:\s+en)?",
    r"me gast(?:e|é)(?:\s+en)?",
    r"gast(?:e|é)(?:\s+en)?",
    r"hoy(?:\s+he)?",
    r"ayer(?:\s+he)?",
    r"apunta(?:me)?",
    r"anota(?:me)?",
    r"pon(?:me)?",
]
PATRON_MULETILLAS = re.compile(
    r"^\s*(?:" + "|".join(MULETILLAS) + r")\s+",
    re.IGNORECASE,
)

# Stop-words al principio o al final que no aportan al concepto
STOP_INICIAL = re.compile(
    r"^\s*(?:en\s+(?:el|la|los|las)\s+|en\s+|de\s+|por\s+|para\s+|un\s+|una\s+|"
    r"el\s+|la\s+|los\s+|las\s+|al\s+|del\s+)",
    re.IGNORECASE,
)
STOP_FINAL = re.compile(
    r"\s+(?:hoy|ayer|esta\s+manana|por\s+la\s+manana|por\s+la\s+tarde|por\s+la\s+noche)\s*$",
    re.IGNORECASE,
)
# Restos de unidad monetaria sueltos en el concepto (ej. "€ cena restaurante",
# "decathlon €", "23 eur cena").
PATRON_RESTO_UNIDAD = re.compile(
    r"(?:^|\s)(?:€|eur|euros?|pavos?|pelas?)(?=\s|$)",
    re.IGNORECASE,
)


@dataclass
class GastoParseado:
    cantidad: Optional[float]
    concepto: str
    raw: str
    categoria_explicita: Optional[str] = None


# Detector de "en categoría X" / "categoría X" para extraer la
# categoría que el usuario menciona explícitamente.
PATRON_CATEGORIA_EXPLICITA = re.compile(
    r"\b(?:en\s+)?categor[ií]a\s+(?:de\s+|el\s+|la\s+)?([A-Za-zÁÉÍÓÚáéíóúÑñ\/\s]+?)(?:\s*[,\.]|\s*$)",
    re.IGNORECASE,
)

# Mapa de palabras del usuario → categoría canónica (para "categoría supermercados" → "Supermercado").
_MAPA_CAT_USUARIO = {
    "supermercado": "Supermercado", "supermercados": "Supermercado",
    "restaurante": "Restaurantes", "restaurantes": "Restaurantes",
    "casa": "Casa", "hogar": "Casa",
    "alquiler": "Alquiler/Hipoteca", "hipoteca": "Alquiler/Hipoteca",
    "transporte": "Transporte",
    "salud": "Salud",
    "ocio": "Ocio",
    "compras": "Compras", "compra": "Compras",
    "mascotas": "Mascotas", "mascota": "Mascotas",
    "fin de semana": "Fin de semana", "finde": "Fin de semana",
    "otros": "Otros", "otro": "Otros",
}


def _detectar_categoria_explicita(texto: str) -> Optional[str]:
    m = PATRON_CATEGORIA_EXPLICITA.search(texto)
    if not m:
        return None
    raw = m.group(1).strip().lower().rstrip(",.;:")
    # Buscar match exacto o por palabra clave
    if raw in _MAPA_CAT_USUARIO:
        return _MAPA_CAT_USUARIO[raw]
    for k, v in _MAPA_CAT_USUARIO.items():
        if k in raw:
            return v
    return None


def parsear(texto: str) -> GastoParseado:
    raw = texto.strip()
    if not raw:
        return GastoParseado(None, "", raw)

    # Detectar categoría explícita ("en categoría X") ANTES de limpiar nada,
    # y borrarla del texto para que no contamine el concepto.
    categoria_explicita = _detectar_categoria_explicita(raw)
    s = PATRON_CATEGORIA_EXPLICITA.sub(" ", raw)

    # Limpiar puntuación final típica de transcripciones
    s = s.rstrip(" .!?¿¡,;:")

    # Quitar muletillas iniciales (varias pasadas por si hay encadenadas)
    for _ in range(3):
        nuevo = PATRON_MULETILLAS.sub("", s)
        if nuevo == s:
            break
        s = nuevo

    # Buscar TODOS los números candidatos. Heurística: el último suele
    # ser la cantidad ("cena 23 euros" o "23 cena de hace 3 días"
    # → preferimos el que va seguido de €/euro/etc, si existe).
    matches = list(PATRON_CANTIDAD.finditer(s))
    cantidad: Optional[float] = None
    span_cantidad: Optional[tuple[int, int]] = None

    if matches:
        # Prioridad 1: el que va seguido de unidad explícita
        con_unidad = [m for m in matches if re.search(r"€|eur|euro|pavo|pela", m.group(0), re.IGNORECASE)]
        elegido = con_unidad[-1] if con_unidad else matches[-1]
        num_str = elegido.group(1).replace(",", ".")
        try:
            cantidad = float(num_str)
            span_cantidad = elegido.span()
        except ValueError:
            cantidad = None

    # Concepto = texto sin la cantidad
    if span_cantidad:
        concepto = (s[: span_cantidad[0]] + " " + s[span_cantidad[1] :]).strip()
    else:
        concepto = s

    # Limpiar restos de unidad monetaria, comas/conectores residuales y stop-words
    concepto = PATRON_RESTO_UNIDAD.sub(" ", concepto)
    concepto = re.sub(r"\s+", " ", concepto)
    concepto = concepto.strip(" ,;.")
    for _ in range(3):
        nuevo = STOP_INICIAL.sub("", concepto).strip(" ,;.")
        if nuevo == concepto:
            break
        concepto = nuevo
    concepto = STOP_FINAL.sub("", concepto).strip(" ,;.")

    # Si el concepto queda vacío pero teníamos algo, dejar el raw original
    if not concepto and cantidad is not None:
        concepto = "(sin concepto)"

    return GastoParseado(cantidad, concepto, raw, categoria_explicita)

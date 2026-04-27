"""
Detección de intención de los mensajes de texto/voz.

Antes de tratar un mensaje como un gasto que apuntar, comprobamos si
parece una CONSULTA (resumen, listado, etc.). Si lo es, devolvemos el
tipo y parámetros; si no, devolvemos None y el bot intenta apuntar.

Tipos de intención:
  - ("ultimos", None)            — últimos gastos
  - ("resumen_semana", None)     — últimos 7 días
  - ("resumen_mes", None)        — mes en curso
  - ("resumen_mes_de", N)        — mes N (1-12) del año actual
  - ("ayuda", None)              — explicar qué puede hacer
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Tuple

# Reutilizamos el detector numérico del parser para "tiene número de gasto"
from parser import PATRON_CANTIDAD

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

PALABRAS_PREGUNTA_INICIAL = (
    "cuanto", "cuanta", "cuantos", "cuantas",
    "que ", "como ",
    "dame", "dime", "muestrame", "ensename", "enseñame",
)

FRASES_CONSULTA = (
    "puedes dar", "me puedes", "quiero ver", "podrias", "podria",
    "haz un resumen", "haces un resumen", "como vamos",
)

PALABRAS_RESUMEN = (
    "resumen", "resume", "resúmen", "resumir",
    "total", "totales", "balance",
    "llevo gastado", "hemos gastado", "gastado en",
)


def _normalizar(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s


def detectar_intencion(texto: str) -> Optional[Tuple[str, Optional[int]]]:
    if not texto:
        return None
    s = _normalizar(texto)

    # Si tiene una cantidad numérica clara → es un gasto a apuntar.
    # Excepción: si la cantidad va seguida o precedida de "gastos" / "gasto"
    # (por ejemplo "los 5 últimos gastos"), no la tratamos como cantidad.
    matches = list(PATRON_CANTIDAD.finditer(s))
    parece_apunte = False
    for m in matches:
        ventana = s[max(0, m.start() - 15): m.end() + 15]
        if "gasto" not in ventana and "ultimo" not in ventana and "ultima" not in ventana:
            parece_apunte = True
            break
    if parece_apunte:
        return None

    # ¿Tiene cara de consulta?
    es_pregunta = "?" in texto
    inicia_pregunta = any(s.startswith(p) for p in PALABRAS_PREGUNTA_INICIAL)
    contiene_frase = any(f in s for f in FRASES_CONSULTA)
    contiene_resumen = any(p in s for p in PALABRAS_RESUMEN)
    pide_listado = ("ultimos" in s or "ultimas" in s) and ("gasto" in s or "compra" in s)

    if not (es_pregunta or inicia_pregunta or contiene_frase or contiene_resumen or pide_listado):
        return None

    # 1) Mes específico ("abril", "mes de mayo", etc.)
    for nombre, num in MESES.items():
        if re.search(rf"\b{nombre}\b", s):
            return ("resumen_mes_de", num)

    # 2) Periodo semana
    if "semana" in s or "ultimos 7" in s or "siete dias" in s:
        return ("resumen_semana", None)

    # 3) Este mes / mes actual / del mes
    if "este mes" in s or "del mes" in s or "mes actual" in s or "mes en curso" in s:
        return ("resumen_mes", None)

    # 4) Listado de últimos gastos
    if pide_listado or "ultimos" in s or "ultimas" in s:
        return ("ultimos", None)

    # 5) "Resumen" / "total" sin más → mes en curso por defecto
    if contiene_resumen:
        return ("resumen_mes", None)

    # Si parece pregunta pero no hemos sabido qué quiere → ayuda
    if es_pregunta or inicia_pregunta or contiene_frase:
        return ("ayuda", None)

    return None

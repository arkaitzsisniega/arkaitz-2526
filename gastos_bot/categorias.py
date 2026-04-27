"""
Mapeo concepto → categoría por palabras clave.

Si una palabra clave aparece en el concepto (case-insensitive, sin tildes),
se asigna esa categoría. La primera coincidencia gana, así que el orden
de KEYWORDS importa: las categorías más específicas van primero.
"""
from __future__ import annotations

import re
import unicodedata

CATEGORIAS = [
    "Supermercado",
    "Restaurantes",
    "Casa",
    "Alquiler/Hipoteca",
    "Transporte",
    "Salud",
    "Ocio",
    "Compras",
    "Mascotas",
    "Fin de semana",
    "Otros",
]

# Orden importa: específicas primero. Las geográficas/personales (Fin de
# semana, Mascotas) van antes de las genéricas para que ganen.
KEYWORDS: list[tuple[str, list[str]]] = [
    ("Fin de semana", [
        "castro", "castro urdiales", "casa de la playa",
    ]),
    ("Alquiler/Hipoteca", [
        "alquiler", "hipoteca", "casero", "renta del piso", "comunidad de vecinos",
    ]),
    ("Supermercado", [
        "lidl", "mercadona", "carrefour", "alcampo", "ahorramas", "ahorra mas",
        "eroski", "dia", "consum", "hipercor", "supermercado", "super", "compra del super",
        "fruteria", "carniceria", "panaderia", "pescaderia", "compra semanal",
        "bm", "costco", "cotsco", "aldi", "bonpreu",
    ]),
    ("Restaurantes", [
        "restaurante", "cena", "cenado", "comida fuera", "comer fuera", "comimos fuera",
        "bar", "cafeteria", "cafe", "desayuno", "almuerzo", "brunch",
        "mcdonalds", "mcdonald", "burger", "kfc", "kebab", "pizza", "sushi", "telepizza",
        "domino", "glovo", "ubereats", "uber eats", "just eat", "pedido a domicilio",
        "vermut", "tapas", "menu", "menu del dia", "comer en", "cenar en",
        "thai", "chino", "chinorris", "coreano", "japones", "italiano",
        "bruxas", "di stefano", "distefano", "ruta 42", "ruta42",
        "pollos", "asador", "hamburgueseria", "hamburguesa",
    ]),
    ("Transporte", [
        "gasolina", "diesel", "gasolinera", "repsol", "cepsa", "shell", "bp ",
        "parking", "aparcamiento", "peaje", "via t", "viat",
        "taxi", "uber", "cabify", "bolt",
        "metro", "bus", "autobus", "tren", "ave", "renfe", "cercanias",
        "vuelo", "avion", "iberia", "ryanair", "vueling", "aeropuerto",
        "itv", "revision coche", "taller", "mecanico", "neumatico", "ruedas",
    ]),
    ("Casa", [
        # Suministros
        "luz", "factura luz", "endesa", "iberdrola", "naturgy", "totalenergies", "holaluz",
        "agua", "factura agua", "canal de isabel", "aqualia",
        "gas", "factura gas",
        # Internet/telefonía
        "internet", "fibra", "movistar", "vodafone", "orange", "yoigo", "masmovil", "lowi",
        # Servicios del hogar
        "tatiana", "limpieza", "limpiadora", "asistenta",
        "jardinero", "jardineria",
        "alarma", "seguridad", "seguro hogar", "segurpaek",
        "placas", "placas solares", "comunidad",
        # Ferretería / bricolaje / muebles
        "ikea", "leroy", "leroy merlin", "bricomart", "obramat", "obra mar", "bricolaje",
        "ferreteria", "muebles",
        # Limpieza
        "detergente", "fregona",
    ]),
    ("Salud", [
        "farmacia", "medicamento", "pastillas", "ibuprofeno", "paracetamol",
        "medico", "doctor", "consulta", "dentista", "clinica", "hospital",
        "fisio", "fisioterapeuta", "osteopata", "psicologo",
        "optica", "gafas", "lentillas",
        "masaje", "masajes",
    ]),
    ("Mascotas", [
        "veterinario", "veterinaria", "pienso", "perro", "gato",
        "kiwoko", "tiendanimal", "arena gato", "collar", "correa",
    ]),
    ("Ocio", [
        "cine", "teatro", "concierto", "entrada", "entradas",
        "viaje", "hotel", "airbnb", "booking", "alojamiento",
        "regalo", "regalos", "cumpleanos", "cumple",
        "museo", "exposicion", "spa", "balneario",
        "netflix", "spotify", "hbo", "disney+", "amazon prime", "prime video",
        "gimnasio", "gym",
    ]),
    ("Compras", [
        "ropa", "zapatos", "zapatilla", "zapatillas", "zara", "h&m", "mango",
        "decathlon", "el corte ingles", "primark", "uniqlo", "pull and bear", "bershka",
        "amazon", "aliexpress", "shein",
        "movil", "telefono", "iphone", "samsung", "ordenador", "portatil",
        "veepee", "vente privee", "vp", "cheerz", "gastos envio", "compras varias",
    ]),
]


def _normalizar(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s


def categorizar(concepto: str) -> str:
    """Devuelve la categoría más probable para un concepto."""
    if not concepto:
        return "Otros"
    txt = _normalizar(concepto)
    for cat, palabras in KEYWORDS:
        for kw in palabras:
            kw_norm = _normalizar(kw)
            # word boundary para evitar falsos positivos ("bar" en "barato")
            if re.search(rf"\b{re.escape(kw_norm)}\b", txt):
                return cat
    return "Otros"

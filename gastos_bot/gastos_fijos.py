"""
Gastos fijos mensuales — se inyectan automáticamente el día 1 de cada mes.

Configuración: `gastos_bot/gastos_fijos.json` (gitignored, es personal).

Ejemplo:
    {
      "gastos_fijos": [
        {"concepto": "Alquiler", "cantidad": 850,
         "categoria": "Alquiler/Hipoteca", "quien": "Arkaitz",
         "notas": "Gasto fijo mensual"},
        {"concepto": "Netflix", "cantidad": 12.99,
         "categoria": "Ocio", "quien": "Lis", "notas": ""},
        ...
      ]
    }

Si el archivo no existe o está vacío, no se hace nada (sin gastos fijos
configurados).

Marca de control: `.gastos_fijos_ultimo_mes_ejecutado` guarda el último
"YYYY-MM" en el que se aplicaron los gastos fijos. Sirve para:
  - Evitar dobles aplicaciones si la JobQueue dispara dos veces.
  - Recuperar si el bot estaba apagado el día 1: al arrancar, si la marca
    es de un mes anterior al actual y ya estamos en día 1 o posterior,
    se aplican.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from pathlib import Path
from typing import Optional

import sheets  # mismo directorio (igual que bot.py)  # type: ignore

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "gastos_fijos.json"
MARKER_FILE = HERE / ".gastos_fijos_ultimo_mes_ejecutado"


def _periodo_actual(fecha: Optional[_dt.date] = None) -> str:
    f = fecha or _dt.date.today()
    return f.strftime("%Y-%m")


def cargar_config() -> list[dict]:
    """Devuelve la lista de gastos fijos (lista vacía si no hay config)."""
    if not CONFIG_FILE.is_file():
        return []
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        log.error("gastos_fijos.json inválido: %s", e)
        return []
    fijos = data.get("gastos_fijos") or []
    # Validación mínima: tienen que tener concepto + cantidad
    out = []
    for g in fijos:
        if not isinstance(g, dict):
            continue
        if not g.get("concepto") or g.get("cantidad") is None:
            log.warning("Gasto fijo descartado por falta de campos: %s", g)
            continue
        try:
            g["cantidad"] = float(g["cantidad"])
        except (TypeError, ValueError):
            log.warning("Gasto fijo con cantidad inválida descartado: %s", g)
            continue
        out.append(g)
    return out


def _leer_marca() -> str:
    if not MARKER_FILE.is_file():
        return ""
    try:
        return MARKER_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _escribir_marca(periodo: str) -> None:
    try:
        MARKER_FILE.write_text(periodo, encoding="utf-8")
    except Exception as e:
        log.warning("No pude escribir marca de gastos fijos: %s", e)


def ya_aplicado(periodo: Optional[str] = None) -> bool:
    """¿Ya se aplicaron los gastos fijos del periodo (YYYY-MM)?"""
    p = periodo or _periodo_actual()
    return _leer_marca() == p


def aplicar(
    fecha: Optional[_dt.date] = None,
    forzar: bool = False,
) -> tuple[list[dict], list[str]]:
    """Aplica todos los gastos fijos al Sheet.

    Devuelve (insertados, errores) donde insertados es la lista de
    dicts realmente añadidos y errores es lista de strings con problemas
    por gasto (no detiene el resto si uno falla).

    Si ya se aplicaron este mes y forzar=False, devuelve ([], []).
    """
    f = fecha or _dt.date.today()
    periodo = _periodo_actual(f)
    if not forzar and ya_aplicado(periodo):
        log.info("Gastos fijos del periodo %s ya aplicados.", periodo)
        return [], []

    config = cargar_config()
    if not config:
        log.info("No hay gastos fijos configurados — nada que aplicar.")
        # Marcamos igualmente para no reintentar mil veces
        _escribir_marca(periodo)
        return [], []

    insertados: list[dict] = []
    errores: list[str] = []
    for g in config:
        try:
            sheets.append_gasto(
                concepto=str(g["concepto"]),
                cantidad=float(g["cantidad"]),
                categoria=str(g.get("categoria", "Otros") or "Otros"),
                quien=str(g.get("quien", "fijo") or "fijo"),
                notas=str(g.get("notas", "Gasto fijo mensual") or "Gasto fijo mensual"),
                fecha=f,
            )
            insertados.append(g)
        except Exception as e:
            err = f"{g.get('concepto', '?')}: {e}"
            log.exception("Fallo aplicando gasto fijo: %s", err)
            errores.append(err)

    if insertados:
        _escribir_marca(periodo)
    return insertados, errores


def resumen_para_telegram(insertados: list[dict], errores: list[str]) -> str:
    """Mensaje Markdown listo para mandar al chat tras aplicar gastos fijos."""
    if not insertados and not errores:
        return "🗓 *Gastos fijos*: nada configurado o ya aplicados este mes."
    lineas = ["🗓 *Gastos fijos del mes aplicados automáticamente:*"]
    total = 0.0
    for g in insertados:
        c = float(g.get("cantidad", 0))
        total += c
        lineas.append(
            f"  • {g.get('concepto', '?')} — {c:.2f}€ "
            f"_({g.get('categoria', '?')}, {g.get('quien', '?')})_"
        )
    if insertados:
        lineas.append("")
        lineas.append(f"💰 Total fijos: *{total:.2f}€*")
    if errores:
        lineas.append("")
        lineas.append("⚠️ *Errores*:")
        for e in errores:
            lineas.append(f"  · {e}")
    return "\n".join(lineas)

"""
limpiar_duplicados.py — Atajo SIN consolidación.

Lee _FORM_PRE y _FORM_POST, busca duplicados (mismo jugador+fecha+turno) y
borra las filas antiguas conservando la más reciente por TIMESTAMP.

Diferencia con `consolidar_forms.py`:
  - NO toca BORG/PESO/WELLNESS (no consolida).
  - NO recalcula vistas.
  - Solo limpia las hojas _FORM_PRE / _FORM_POST.

Útil cuando:
  - Ya consolidaste antes y han caído más respuestas duplicadas.
  - Solo quieres dejar limpias las hojas crudas del Form sin re-disparar
    todo el pipeline de vistas (que tarda ~10 min).

Uso:
  /usr/bin/python3 src/limpiar_duplicados.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(Path(__file__).parent))
import forms_utils as fu  # noqa: E402

SHEET_NAME = "Arkaitz - Datos Temporada 2526"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

MSG_SEP = "---MSG---"


def main():
    creds = Credentials.from_service_account_file(
        str(ROOT / "google_credentials.json"), scopes=SCOPES
    )
    ss = gspread.authorize(creds).open(SHEET_NAME)

    # 1) Detectar duplicados ANTES de borrar (para reporte transparente).
    pre = fu.leer_respuestas_pre(ss)
    post = fu.leer_respuestas_post(ss)
    duplicados = fu.detectar_duplicados(pre, post)

    if duplicados.empty:
        print(MSG_SEP)
        print(
            "✅ *Sin duplicados en _FORM_PRE / _FORM_POST.*\n\n"
            f"📝 PRE: {len(pre)} respuestas · POST: {len(post)} respuestas\n\n"
            "Nada que limpiar. Las hojas oficiales (BORG/PESO/WELLNESS) y las "
            "vistas del dashboard NO se han tocado."
        )
        return

    # 2) Limpieza determinista. Ya estaba implementada en forms_utils;
    # aquí solo la usamos sola.
    limpieza = fu.eliminar_duplicados_form(ss)

    # 3) Reporte.
    print(MSG_SEP)
    total_borrados = 0
    errores: list[str] = []
    lineas: list[str] = []
    for r in limpieza:
        if "error" in r:
            errores.append(f"  · {r.get('hoja','?')}: {r['error']}")
            continue
        lineas.append(
            f"• {r['jugador']} {r['tipo']} del {r['fecha']} {r['turno']}: "
            f"{r['borrados']} antiguos borrados (conservada fila {r['conservado_row']})"
        )
        total_borrados += r["borrados"]

    if total_borrados == 0 and not errores:
        # Detectados pero no se identificaron columnas → reporte de qué hay
        # y aviso al usuario para que revise manualmente.
        texto = (
            "⚠️ *Duplicados detectados pero no se pudo auto-limpiar.*\n"
            "Revisa _FORM_PRE / _FORM_POST manualmente:\n"
        )
        for _, r in duplicados.iterrows():
            texto += f"• {r['jugador']} {r['n_envios']}× {r['tipo']} {r['fecha']} {r['turno']}\n"
        print(texto)
        return

    texto = f"🧹 *Duplicados limpiados ({total_borrados} filas borradas):*\n"
    texto += "\n".join(lineas)
    if errores:
        texto += "\n\n⚠️ *Errores durante la limpieza:*\n" + "\n".join(errores)
        texto += "\nLos duplicados sin limpiar siguen en la hoja, revisa manualmente."
    texto += (
        "\n\nℹ️ NO he tocado BORG/PESO/WELLNESS ni recalculado vistas. "
        "Si necesitas que esos datos limpios se integren en las hojas "
        "oficiales y se refresquen las vistas del dashboard, lanza `/consolidar`."
    )
    print(texto)


if __name__ == "__main__":
    main()

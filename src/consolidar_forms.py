"""
consolidar_forms.py — Lee _FORM_PRE y _FORM_POST, los integra en las hojas
oficiales BORG/PESO/WELLNESS, y avisa de duplicados.

Uso:
  /usr/bin/python3 src/consolidar_forms.py
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

    # Paso 0: PRIMERO leemos para detectar duplicados (queremos reportarlos
    # al usuario antes de borrar nada — transparencia).
    pre = fu.leer_respuestas_pre(ss)
    post = fu.leer_respuestas_post(ss)
    duplicados = fu.detectar_duplicados(pre, post)

    # Paso 1: AUTO-LIMPIEZA de duplicados. Borra las filas antiguas de
    # _FORM_PRE / _FORM_POST conservando la más reciente (por TIMESTAMP).
    # Antes este paso era manual y requería que Alfred entrara a las hojas
    # de Form, lo cual no hacía bien. Ahora es determinista y siempre se
    # ejecuta tras detectarlos.
    limpieza = []
    if not duplicados.empty:
        limpieza = fu.eliminar_duplicados_form(ss)
        # Re-leer tras la limpieza, así la consolidación trabaja con datos
        # ya sin duplicados (igual que antes, pero garantizado).
        pre = fu.leer_respuestas_pre(ss)
        post = fu.leer_respuestas_post(ss)

    cont = fu.consolidar_a_sheet(ss, pre, post)

    print(MSG_SEP)
    print(
        f"✅ *Consolidación terminada*\n\n"
        f"📝 PRE: {len(pre)} respuestas · POST: {len(post)} respuestas\n\n"
        f"Integrado al Sheet:\n"
        f"• PESO: {cont['peso_nuevos']} nuevos, {cont['peso_actualizados']} actualizados\n"
        f"• BORG: {cont['borg_nuevos']} nuevos, {cont['borg_actualizados']} actualizados\n"
        f"• WELLNESS: {cont['wellness_nuevos']} nuevos, {cont['wellness_actualizados']} actualizados"
    )

    if not duplicados.empty:
        # Reporte: qué duplicados se detectaron Y cómo se limpiaron.
        print(MSG_SEP)
        texto = "🧹 *Duplicados detectados y auto-limpiados:*\n"
        total_borrados = 0
        errores: list[str] = []
        for r in limpieza:
            if "error" in r:
                errores.append(f"  · {r.get('hoja','?')}: {r['error']}")
                continue
            texto += (f"• {r['jugador']} {r['tipo']} del {r['fecha']} {r['turno']}: "
                      f"{r['borrados']} antiguos borrados (conservada fila {r['conservado_row']})\n")
            total_borrados += r["borrados"]
        if total_borrados == 0 and not errores:
            texto = "⚠️ Se detectaron duplicados pero no se pudo identificar columnas para auto-limpiar. Revisa _FORM_PRE / _FORM_POST manualmente.\n"
            for _, r in duplicados.iterrows():
                texto += f"• {r['jugador']} {r['n_envios']}× {r['tipo']} {r['fecha']} {r['turno']}\n"
        elif errores:
            texto += "\n⚠️ Errores durante la limpieza:\n" + "\n".join(errores) + "\n"
            texto += "Los duplicados sin limpiar siguen en la hoja, revisa manualmente."
        else:
            texto += f"\n✅ Total limpiado: {total_borrados} filas duplicadas. La hoja oficial (PESO/BORG/WELLNESS) ya conserva los datos correctos."
        print(texto)


if __name__ == "__main__":
    main()

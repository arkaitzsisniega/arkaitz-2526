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

    pre = fu.leer_respuestas_pre(ss)
    post = fu.leer_respuestas_post(ss)
    duplicados = fu.detectar_duplicados(pre, post)
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
        print(MSG_SEP)
        texto = "⚠️ *Alertas de duplicados:*\n"
        for _, r in duplicados.iterrows():
            texto += f"• {r['jugador']} envió {r['n_envios']}× el {r['tipo']} del {r['fecha']} {r['turno']}\n"
        print(texto)


if __name__ == "__main__":
    main()

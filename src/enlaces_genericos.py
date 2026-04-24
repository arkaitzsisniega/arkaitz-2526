"""
enlaces_genericos.py — Devuelve los 2 enlaces genéricos (PRE y POST) del
Form SIN pre-rellenar jugador. Pensado para enviar a un grupo de WhatsApp
una sola vez y que cada jugador elija su nombre.

Uso:
  /usr/bin/python3 src/enlaces_genericos.py [YYYY-MM-DD]

Con fecha, los enlaces llevan FECHA y TURNO pre-rellenados; sin fecha,
los enlaces son 100% genéricos (jugador + fecha + turno los elige el jugador).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import forms_utils as fu  # noqa: E402

MSG_SEP = "---MSG---"


def main():
    # Sin argumentos: enlaces 100% genéricos
    # Con fecha: prefill fecha + turno automático (primera sesión del día)
    cfg = fu.load_config()
    fecha = sys.argv[1] if len(sys.argv) > 1 else None

    if fecha:
        # Necesita saber el turno; por defecto "M" para simplificar
        # Esto es una simplificación; normalmente /enlaces_hoy sí detecta turno real
        turno = "M"
        pre_url = fu.enlace_pre("", fecha, turno)
        post_url = fu.enlace_post("", fecha, turno)
        contexto = f" para **{fecha}** (turno {turno})"
    else:
        pre_url = f"https://docs.google.com/forms/d/e/{cfg['pre']['form_id']}/viewform"
        post_url = f"https://docs.google.com/forms/d/e/{cfg['post']['form_id']}/viewform"
        contexto = ""

    print(MSG_SEP)
    print(f"📋 *Enlaces genéricos del Form*{contexto}\n\n"
          f"Copia los 2 enlaces al grupo de WhatsApp del equipo "
          f"una sola vez y todos los jugadores los usan.")

    print(MSG_SEP)
    print(f"🟦 *ANTES del entreno* (peso PRE + wellness):\n{pre_url}")

    print(MSG_SEP)
    print(f"🟥 *DESPUÉS del entreno* (peso POST + Borg):\n{post_url}")

    print(MSG_SEP)
    print("ℹ️ En ambos Forms el jugador elige su nombre del desplegable. "
          "Si hay doble sesión el mismo día, en la 2ª se deja wellness en blanco.")


if __name__ == "__main__":
    main()

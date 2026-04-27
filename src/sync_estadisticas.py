#!/usr/bin/env python3
"""
Sync único de TODAS las estadísticas al Google Sheet.

Lanza en cadena los 4 importadores para que con un solo comando
queden actualizadas todas las hojas de estadísticas:

  - estadisticas_partidos.py    → EST_PARTIDOS, EST_EVENTOS, _VISTA_EST_JUGADOR
  - estadisticas_disparos.py    → EST_DISPAROS
  - scouting_rivales.py         → SCOUTING_RIVALES, _VISTA_SCOUTING_RIVAL
  - estadisticas_avanzadas.py   → _VISTA_EST_AVANZADAS, _VISTA_EST_CUARTETOS

Uso:
  /usr/bin/python3 src/sync_estadisticas.py
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = "/usr/bin/python3"

PASOS = [
    ("Partidos + eventos + jugador", "src/estadisticas_partidos.py", ["--upload"]),
    ("Disparos por partido",          "src/estadisticas_disparos.py",  ["--upload"]),
    ("Scouting rivales",              "src/scouting_rivales.py",       ["--upload"]),
    ("Métricas avanzadas",            "src/estadisticas_avanzadas.py", ["--upload"]),
]


def main():
    print("🔄 Sync de estadísticas — 4 pasos")
    print("=" * 60)
    fallos = []
    for i, (nombre, script, args) in enumerate(PASOS, 1):
        print(f"\n[{i}/{len(PASOS)}] {nombre}…")
        t0 = time.time()
        try:
            r = subprocess.run(
                [PY, str(ROOT / script)] + args,
                cwd=str(ROOT),
                capture_output=True, text=True, timeout=600,
            )
            dt = time.time() - t0
            if r.returncode == 0:
                # mostrar últimas líneas útiles
                lineas_ok = [l for l in r.stdout.split("\n") if "✅" in l]
                for l in lineas_ok[-4:]:
                    print(f"   {l}")
                print(f"   ✓ {nombre} ({dt:.1f}s)")
            else:
                print(f"   ❌ {nombre} (exit {r.returncode}, {dt:.1f}s)")
                print(r.stderr[-500:])
                fallos.append(nombre)
        except subprocess.TimeoutExpired:
            print(f"   ⚠️  {nombre}: timeout (>600s)")
            fallos.append(nombre)
        except Exception as e:
            print(f"   ❌ {nombre}: {e}")
            fallos.append(nombre)

    print("\n" + "=" * 60)
    if fallos:
        print(f"❌ Sync con errores en: {', '.join(fallos)}")
        return 1
    print("✅ Sync completo. Refresca el dashboard de Streamlit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

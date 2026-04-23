"""Script de inspección: vuelca en consola el estado actual del Google Sheet
para diagnosticar bugs en el dashboard. No escribe nada."""
import warnings, sys
warnings.filterwarnings("ignore")

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_file("google_credentials.json", scopes=SCOPES)
ss = gspread.authorize(creds).open("Arkaitz - Datos Temporada 2526")

def leer(nombre, unformatted=False):
    opts = {}
    if unformatted:
        opts["value_render_option"] = gspread.utils.ValueRenderOption.unformatted
    return pd.DataFrame(ss.worksheet(nombre).get_all_records(**opts))

print("="*70)
print("SESIONES (raw con UNFORMATTED)")
print("="*70)
ses = leer("SESIONES", unformatted=True)
print(f"Filas: {len(ses)} | Columnas: {list(ses.columns)}")
print("Rango de FECHA (valores crudos):")
print(f"  min={ses['FECHA'].min()} | max={ses['FECHA'].max()} | tipo={ses['FECHA'].dtype}")
print(f"\nFechas únicas raras (<40000 o >55000 serial, fuera 2009-2050):")
f = pd.to_numeric(ses["FECHA"], errors="coerce")
raras = ses[(f < 40000) | (f > 55000) | f.isna()]
print(raras.head(10).to_string())

print("\n" + "="*70)
print("BORG (raw con UNFORMATTED)")
print("="*70)
borg = leer("BORG", unformatted=True)
print(f"Filas: {len(borg)} | Columnas: {list(borg.columns)}")
print(f"Jugadores únicos: {borg['JUGADOR'].nunique() if 'JUGADOR' in borg.columns else '?'}")
# Valores únicos de BORG
print(f"\nValores únicos de columna BORG (primeros 30):")
print(list(borg["BORG"].dropna().unique())[:30])
# Valores no-numéricos
print(f"\nValores no-numéricos en BORG:")
no_num = borg[pd.to_numeric(borg["BORG"], errors="coerce").isna() & borg["BORG"].notna() & (borg["BORG"] != "")]
print(f"Total filas con letras: {len(no_num)}")
print(no_num["BORG"].value_counts().head(20))

print("\n" + "="*70)
print("PESO (raw con UNFORMATTED) - buscar valores >200 o <40")
print("="*70)
peso = leer("PESO", unformatted=True)
print(f"Filas: {len(peso)} | Columnas: {list(peso.columns)}")
p = pd.to_numeric(peso["PESO_PRE"], errors="coerce")
raros = peso[((p < 40) | (p > 200)) & p.notna()]
print(f"Filas con PESO_PRE fuera de [40,200]: {len(raros)}")
print(raros.head(10).to_string())

print("\n" + "="*70)
print("LESIONES (raw)")
print("="*70)
les_rows = ss.worksheet("LESIONES").get_all_values()
print(f"Total filas físicas: {len(les_rows)}")
for i, row in enumerate(les_rows[:5]):
    print(f"Fila {i}: {row[:8]}...")

print("\n" + "="*70)
print("_VISTA_SEMAFORO (actual)")
print("="*70)
sem = leer("_VISTA_SEMAFORO")
print(sem.to_string())

print("\n" + "="*70)
print("_VISTA_SEMANAL (últimas 5 semanas)")
print("="*70)
sw = leer("_VISTA_SEMANAL")
print(f"Filas totales: {len(sw)}")
print(f"Rango FECHA_LUNES: {sw['FECHA_LUNES'].min()} → {sw['FECHA_LUNES'].max()}")
# Semanas únicas
print(f"\nÚltimas 5 semanas:")
ultimas = sorted(sw["FECHA_LUNES"].unique())[-5:]
for lun in ultimas:
    sub = sw[sw["FECHA_LUNES"] == lun]
    print(f"  {lun}: {len(sub)} jugadores, CARGA_SEMANAL suma={sub['CARGA_SEMANAL'].sum()}, ACWR media={sub['ACWR'].mean():.3f}")

print("\n" + "="*70)
print("_VISTA_RECUENTO")
print("="*70)
rec = leer("_VISTA_RECUENTO")
print(rec.to_string())

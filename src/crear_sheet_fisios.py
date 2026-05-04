"""
crear_sheet_fisios.py — Configura el Sheet de Lesiones y Tratamientos
para fisios. Es un sheet SEPARADO del principal para que los fisios
solo accedan a estos datos y no al resto.

⚠️ ATENCIÓN: la cuenta de servicio NO puede crear sheets nuevos (no
tiene cuota de Drive). El usuario tiene que crear el Sheet a MANO
y compartirlo con la cuenta de servicio:

  1. Ve a https://sheets.google.com → '+ En blanco' (sheet vacío)
  2. Renómbralo a 'Arkaitz - Lesiones y Tratamientos 2526'
  3. Comparte → escribe el email de la cuenta de servicio:
       arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com
     Permiso: Editor. Pulsa Enviar.
  4. Ejecuta este script: /usr/bin/python3 src/crear_sheet_fisios.py

El script entonces creará las hojas (LESIONES, TRATAMIENTOS,
JUGADORES, _META, _VISTA_*) y migrará los datos del Sheet principal.

Idempotente: ejecutarlo más de una vez NO duplica datos.
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE = ROOT / "google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHEET_PRINCIPAL = "Arkaitz - Datos Temporada 2526"
SHEET_FISIOS = "Arkaitz - Lesiones y Tratamientos 2526"
EMAIL_OWNER = "arkaitzsisniega@gmail.com"

# Estructura de las hojas (cabeceras)
HOJAS = {
    "LESIONES": [
        "id_lesion",  # autogenerado: L0001, L0002...
        "jugador",
        "dorsal",  # autocompletado
        "fecha_lesion",
        "momento",  # ENTRENO / PARTIDO / GYM / OTRO
        "tipo_lesion",  # MUSCULAR / LIGAMENTOSA / ÓSEA / CONTUSIÓN / TENDINOSA / ARTICULAR / OTRO
        "zona_corporal",  # CABEZA / CUELLO / TORSO / HOMBRO / BRAZO / CODO / MUÑECA / MANO / CADERA / MUSLO / RODILLA / TIBIA / TOBILLO / PIE
        "lado",  # IZQUIERDA / DERECHA / BILATERAL / N.A.
        "mecanismo",  # CONTACTO / NO_CONTACTO / SOBREUSO / RECIDIVA / OTRO
        "diagnostico",  # texto libre
        "dias_baja_estimados",
        "pruebas_medicas",  # texto libre
        "notas_iniciales",
        "estado_actual",  # ACTIVA / EN_RECUP / ALTA / RECAÍDA
        "fecha_revision",
        "tratamiento",  # texto libre
        "evolucion",
        "vuelta_programada",
        "notas_seguimiento",
        "fecha_alta",
        "dias_baja_real",  # CALCULADO automaticamente
        "diferencia_dias",  # CALCULADO (real - estimados)
        "recaida",  # SI / NO
        "baja_anterior",  # SI / NO
        "notas_alta",
        # Calculados (sesiones perdidas - rellena calcular_vistas_fisios)
        "total_sesiones",
        "entrenos_perdidos",
        "gym_perdidos",
        "partidos_perdidos",
        "recup_perdidos",
        "minutos_perdidos",
    ],
    "TRATAMIENTOS": [
        "id_tratamiento",  # T0001, T0002...
        "fecha",
        "jugador",
        "dorsal",
        "fisio",  # nombre del fisio (Pelu, Otros…)
        "tipo_tratamiento",  # MASAJE / ELECTRO / PUNCIÓN_SECA / VENDAJE / CRIOTERAPIA / MOVILIZACIÓN / READAPTACIÓN / OTRO
        "zona",  # zona del cuerpo
        "lado",
        "duracion_min",
        "es_vendaje",  # SÍ / NO
        "id_lesion_relacionada",  # vacío si es preventivo, si no = id_lesion
        "preventivo_o_curativo",  # PREVENTIVO / CURATIVO
        "observaciones",
    ],
    "JUGADORES": [
        "dorsal",
        "nombre",
        "posicion",
        "equipo",  # PRIMER / FILIAL
        "activo",  # TRUE / FALSE
    ],
    "_META": [
        "clave",
        "valor",
        "actualizado",
    ],
}


def _connect():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds)


def _crear_o_abrir_sheet(client) -> gspread.Spreadsheet:
    """Devuelve el Spreadsheet de fisios. Si no existe o no está
    compartido con la cuenta de servicio, da instrucciones al usuario."""
    try:
        sh = client.open(SHEET_FISIOS)
        print(f"📂 Sheet encontrado: '{SHEET_FISIOS}' (id: {sh.id})")
        return sh
    except gspread.exceptions.SpreadsheetNotFound:
        print()
        print("=" * 70)
        print(f"❌ No encuentro el Sheet '{SHEET_FISIOS}'")
        print("=" * 70)
        print()
        print("La cuenta de servicio NO tiene cuota para crear Sheets.")
        print("Tienes que crearlo TÚ a mano (30 segundos):")
        print()
        print("  1. Ve a https://sheets.google.com")
        print("  2. Pulsa '+ En blanco' (Sheet vacío)")
        print(f"  3. Renombra el documento a:  {SHEET_FISIOS}")
        print("  4. Compartir (botón arriba a la derecha)")
        print("  5. Escribe este email y pulsa Enviar (Editor):")
        print("     arkaitz-bot@norse-ward-494106-q6.iam.gserviceaccount.com")
        print()
        print("  6. Vuelve a ejecutar este script:")
        print("     /usr/bin/python3 src/crear_sheet_fisios.py")
        print()
        print("=" * 70)
        sys.exit(1)


def _asegurar_hoja(sh: gspread.Spreadsheet, nombre: str, cabeceras: list[str]):
    """Asegura que la hoja existe con las cabeceras correctas."""
    existe = nombre in [w.title for w in sh.worksheets()]
    if not existe:
        ws = sh.add_worksheet(title=nombre,
                                rows=max(500, len(cabeceras) + 50),
                                cols=len(cabeceras) + 5)
        ws.update(values=[cabeceras], range_name=f"A1:{chr(64+len(cabeceras))}1")
        # Negrita en cabeceras
        ws.format(f"A1:{chr(64+len(cabeceras))}1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.10, "green": 0.23, "blue": 0.42},
        })
        ws.format(f"A1:{chr(64+len(cabeceras))}1", {
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        })
        # Congelar fila de cabecera
        ws.freeze(rows=1)
        print(f"   ✅ Hoja creada: {nombre}")
    else:
        ws = sh.worksheet(nombre)
        # Verificar cabeceras
        actual = ws.row_values(1)
        if actual != cabeceras:
            print(f"   ⚠️ Cabeceras de '{nombre}' difieren del esperado.")
            print(f"      Actual:    {actual[:5]}…")
            print(f"      Esperado:  {cabeceras[:5]}…")
            print(f"      (no se sobreescribe automáticamente)")
        else:
            print(f"   ✓ Hoja OK: {nombre}")
    return ws


def _eliminar_hoja_default(sh):
    """Cuando se crea un Sheet nuevo trae una hoja por defecto 'Hoja 1' o
    'Sheet1'. La quitamos si tenemos al menos una de las nuestras."""
    titulos = [w.title for w in sh.worksheets()]
    nuestros = set(HOJAS.keys()) | {"_VISTA_LESIONES", "_VISTA_RESUMEN"}
    for t in titulos:
        if t not in nuestros and t in ("Sheet1", "Hoja 1", "Hoja1"):
            try:
                sh.del_worksheet(sh.worksheet(t))
                print(f"   🗑 Hoja default '{t}' eliminada")
            except Exception:
                pass


def _sincronizar_jugadores(sh_fisios, sh_principal):
    """Copia el roster del Sheet principal a la hoja JUGADORES del de fisios."""
    print("👥 Sincronizando JUGADORES desde roster principal…")
    ws_src = sh_principal.worksheet("JUGADORES_ROSTER")
    src_data = ws_src.get_all_records()
    if not src_data:
        print("   ⚠️ JUGADORES_ROSTER vacío, no se copia nada")
        return

    ws_dst = sh_fisios.worksheet("JUGADORES")
    # Solo limpiar a partir de la fila 2 (mantener cabeceras)
    ws_dst.batch_clear(["A2:Z"])
    time.sleep(1)

    filas = []
    for j in src_data:
        nombre = str(j.get("nombre", "")).strip().upper()
        if not nombre:
            continue
        d = j.get("dorsal", "")
        try:
            d = int(float(d)) if d not in ("", None) else ""
        except (ValueError, TypeError):
            d = ""
        # Decidir equipo: por defecto PRIMER si está en lista de primeros
        nombres_primer = {"HERRERO", "GARCIA", "J.HERRERO", "J.GARCIA",
                          "CECILIO", "CHAGUINHA", "RAUL", "HARRISON",
                          "RAYA", "JAVI", "PANI", "PIRATA", "BARONA", "CARLOS"}
        equipo = "PRIMER" if nombre in nombres_primer else "FILIAL"
        # Activo
        activo = str(j.get("activo", "TRUE")).upper()
        if activo not in ("TRUE", "FALSE"):
            activo = "TRUE"
        filas.append([str(d) if d != "" else "",
                      nombre,
                      str(j.get("posicion", "")).upper(),
                      equipo,
                      activo])

    if filas:
        ws_dst.update(values=filas, range_name=f"A2:E{len(filas)+1}",
                        value_input_option="USER_ENTERED")
        print(f"   ✅ {len(filas)} jugadores sincronizados")


def _migrar_lesiones(sh_fisios, sh_principal):
    """Migra las lesiones del Sheet principal al de fisios.
    Solo añade lesiones que NO estén ya en el destino (idempotente)."""
    print("🏥 Migrando LESIONES desde Sheet principal…")
    ws_src = sh_principal.worksheet("LESIONES")
    src = ws_src.get_all_values()

    if len(src) < 3:
        print("   ⚠️ LESIONES vacía o sin datos")
        return

    # La fila 1 son grupos, fila 2 cabeceras reales
    # Cabeceras viejas (fila 2):
    # JUGADOR, FECHA LESIÓN, MOMENTO, TIPO LESIÓN, ZONA CORPORAL, LADO,
    # MECANISMO, DIAGNÓSTICO, DÍAS BAJA EST., PRUEBAS MÉDICAS,
    # NOTAS INICIALES, ESTADO ACTUAL, FECHA REVISIÓN, TRATAMIENTO,
    # EVOLUCIÓN, VUELTA PROG., NOTAS SEGUIM., FECHA ALTA,
    # DÍAS BAJA REALES, DIFERENCIA DÍAS, RECAÍDA, BAJA ANTERIOR,
    # NOTAS ALTA, TOTAL SESIONES, ENTRENOS, GYM, PARTIDOS, RECUP,
    # MINUTOS PERDIDOS

    cab_viejas = src[1]
    data_viejas = src[2:]

    # Mapping cabeceras viejas → claves nuevas
    map_cols = {
        "JUGADOR": "jugador",
        "FECHA LESIÓN": "fecha_lesion",
        "MOMENTO": "momento",
        "TIPO LESIÓN": "tipo_lesion",
        "ZONA CORPORAL": "zona_corporal",
        "LADO": "lado",
        "MECANISMO": "mecanismo",
        "DIAGNÓSTICO": "diagnostico",
        "DÍAS BAJA EST.": "dias_baja_estimados",
        "PRUEBAS MÉDICAS": "pruebas_medicas",
        "NOTAS INICIALES": "notas_iniciales",
        "ESTADO ACTUAL": "estado_actual",
        "FECHA REVISIÓN": "fecha_revision",
        "TRATAMIENTO": "tratamiento",
        "EVOLUCIÓN": "evolucion",
        "VUELTA PROG.": "vuelta_programada",
        "NOTAS SEGUIM.": "notas_seguimiento",
        "FECHA ALTA": "fecha_alta",
        "DÍAS BAJA REALES": "dias_baja_real",
        "DIFERENCIA DÍAS": "diferencia_dias",
        "RECAÍDA": "recaida",
        "BAJA ANTERIOR": "baja_anterior",
        "NOTAS ALTA": "notas_alta",
        "TOTAL SESIONES": "total_sesiones",
        "ENTRENOS": "entrenos_perdidos",
        "GYM": "gym_perdidos",
        "PARTIDOS": "partidos_perdidos",
        "RECUP": "recup_perdidos",
        "MINUTOS PERDIDOS": "minutos_perdidos",
    }

    # Roster para mapear jugador → dorsal
    ws_roster = sh_fisios.worksheet("JUGADORES")
    roster_rows = ws_roster.get_all_records()
    nombre_a_dorsal = {str(r.get("nombre", "")).strip().upper(): r.get("dorsal", "")
                          for r in roster_rows if r.get("nombre")}

    # Lesiones ya existentes en destino (para idempotencia)
    ws_dst = sh_fisios.worksheet("LESIONES")
    existing = ws_dst.get_all_records()
    existing_keys = {(str(r.get("jugador", "")).upper(),
                       str(r.get("fecha_lesion", "")))
                       for r in existing if r.get("jugador") and r.get("fecha_lesion")}
    print(f"   Lesiones ya en destino: {len(existing_keys)}")

    # Construir filas nuevas
    nuevas = []
    siguiente_id = len(existing) + 1
    cab_nueva = HOJAS["LESIONES"]
    for i, fila in enumerate(data_viejas):
        # Si es fórmula (empieza con =) o vacía, saltar
        if not fila or all(not str(c).strip() or str(c).strip().startswith("=")
                            for c in fila):
            continue
        # Construir dict con cabecera vieja
        row_dict_vieja = {cab_viejas[j]: (fila[j] if j < len(fila) else "")
                            for j in range(len(cab_viejas))}
        # Saltar si fórmulas
        if not row_dict_vieja.get("JUGADOR") or row_dict_vieja["JUGADOR"].startswith("="):
            continue

        jugador = str(row_dict_vieja.get("JUGADOR", "")).strip().upper()
        fecha = str(row_dict_vieja.get("FECHA LESIÓN", "")).strip()
        if not jugador or not fecha:
            continue
        # Idempotencia
        if (jugador, fecha) in existing_keys:
            continue

        # Mapear a estructura nueva
        row_dict_nueva = {}
        for col_vieja, col_nueva in map_cols.items():
            val = row_dict_vieja.get(col_vieja, "")
            # Si es fórmula la dejamos vacía (calcular_vistas_fisios la rellenará)
            if isinstance(val, str) and val.startswith("="):
                val = ""
            row_dict_nueva[col_nueva] = val

        # Auto-rellenar id y dorsal
        row_dict_nueva["id_lesion"] = f"L{siguiente_id:04d}"
        siguiente_id += 1
        row_dict_nueva["dorsal"] = nombre_a_dorsal.get(jugador, "")

        # Construir fila en orden de cabecera nueva
        fila_nueva = [str(row_dict_nueva.get(h, "")) for h in cab_nueva]
        nuevas.append(fila_nueva)

    if not nuevas:
        print("   ✓ No hay lesiones nuevas que migrar")
        return

    # Buscar primera fila libre y escribir
    todas_dst = ws_dst.get_all_values()
    primera_libre = len(todas_dst) + 1
    ws_dst.update(values=nuevas,
                    range_name=f"A{primera_libre}:{chr(64+len(cab_nueva))}{primera_libre+len(nuevas)-1}",
                    value_input_option="USER_ENTERED")
    print(f"   ✅ {len(nuevas)} lesiones migradas")


def _guardar_meta(sh_fisios):
    """Guarda metadatos del último sync."""
    import datetime as dt
    ws = sh_fisios.worksheet("_META")
    ws.batch_clear(["A2:C"])
    time.sleep(0.5)
    rows = [
        ["sheet_id", sh_fisios.id, dt.datetime.now().isoformat()],
        ["sheet_principal", SHEET_PRINCIPAL, dt.datetime.now().isoformat()],
        ["ultimo_sync_jugadores", "OK", dt.datetime.now().isoformat()],
    ]
    ws.update(values=rows, range_name=f"A2:C{1+len(rows)}",
                value_input_option="USER_ENTERED")
    print("   ✅ _META actualizada")


def main():
    print("="*70)
    print("CREAR SHEET DE LESIONES Y TRATAMIENTOS PARA FISIOS")
    print("="*70)
    print()

    client = _connect()
    sh = _crear_o_abrir_sheet(client)

    print()
    print("📋 Asegurando estructura de hojas…")
    for nombre, cabeceras in HOJAS.items():
        _asegurar_hoja(sh, nombre, cabeceras)

    _eliminar_hoja_default(sh)

    # Sincronizar JUGADORES y migrar LESIONES desde el Sheet principal
    print()
    sh_principal = client.open(SHEET_PRINCIPAL)
    _sincronizar_jugadores(sh, sh_principal)
    print()
    _migrar_lesiones(sh, sh_principal)
    print()

    print("📌 Guardando metadatos…")
    _guardar_meta(sh)

    print()
    print("="*70)
    print(f"✅ Sheet de fisios listo: '{SHEET_FISIOS}'")
    print(f"   ID: {sh.id}")
    print(f"   URL: https://docs.google.com/spreadsheets/d/{sh.id}/")
    print()
    print("Próximos pasos:")
    print("  1. Abre la URL → confirma que tienes acceso como Editor.")
    print("  2. Comparte con los fisios (botón 'Compartir' en Sheets):")
    print("     · Email del fisio + permiso Editor")
    print("     · IMPORTANTE: NO les des acceso al Sheet principal")
    print("  3. Ejecuta src/calcular_vistas_fisios.py para rellenar")
    print("     las columnas de sesiones perdidas (cálculo automático).")
    print()


if __name__ == "__main__":
    sys.exit(main())

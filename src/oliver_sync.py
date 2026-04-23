"""
oliver_sync.py — Sincroniza datos de Oliver Sports con el Google Sheet.

Lee el token JWT del .env (se renueva manualmente cuando caduca), consulta
la API de Oliver (api-prod.tryoliver.com), extrae las 15 métricas MVP por
jugador/sesión y escribe a la hoja OLIVER del Sheet.

Uso:
  /usr/bin/python3 src/oliver_sync.py                 # sincroniza incremental
  /usr/bin/python3 src/oliver_sync.py --todas         # refuerza todas (más lento)
  /usr/bin/python3 src/oliver_sync.py --deep          # incluye las 68 métricas (quincenal)

Requisitos en .env (raíz del proyecto):
  OLIVER_TOKEN=<JWT de 531 chars>
  OLIVER_REFRESH_TOKEN=<refresh JWT>
  OLIVER_USER_ID=32194
  OLIVER_TEAM_ID=1728

Si el token caduca, el script lo dice claro y te da las instrucciones
para regenerarlo copiando un snippet de 4 líneas en la consola del navegador.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
import os

import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.resolve()
load_dotenv(ROOT / ".env")

# ─── Configuración ──────────────────────────────────────────────────────────
OLIVER_API    = "https://api-prod.tryoliver.com/v1"
OLIVER_TOKEN  = os.getenv("OLIVER_TOKEN", "").strip()
OLIVER_USER   = os.getenv("OLIVER_USER_ID", "").strip()
OLIVER_TEAM   = os.getenv("OLIVER_TEAM_ID", "1728").strip()
OLIVER_VERSION = "2.0.35"


def _decode_jwt_payload(jwt: str) -> dict:
    """Decodifica el payload del JWT (sin verificar firma — solo leer)."""
    try:
        parts = jwt.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)  # padding base64
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}

SHEET_NAME    = "Arkaitz - Datos Temporada 2526"
CREDS_FILE    = ROOT / "google_credentials.json"
HOJA_MVP      = "OLIVER"
HOJA_DEEP     = "_OLIVER_DEEP"
HOJA_SESS     = "_OLIVER_SESIONES"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ─── 15 métricas MVP que van a la hoja principal OLIVER ─────────────────────
# Claves ilustrativas; el aplanado se hace en extract_mvp().
MVP_COLUMNS = [
    "fecha", "jugador", "session_id", "session_name", "tipo",
    "played_time", "total_time",
    "distancia_total_m", "distancia_hsr_m", "velocidad_max_kmh",
    "acc_alta_count", "dec_alta_count", "acc_max_count", "dec_max_count",
    "oliver_load", "kcal",
    "cambios_direccion", "saltos", "sprints_count",
    "rpe_oliver",
]


# ─── Ayudantes ──────────────────────────────────────────────────────────────
def _fatal(msg: str, code: int = 1):
    print(f"\n❌ {msg}\n", file=sys.stderr)
    sys.exit(code)


def _warn(msg: str):
    print(f"⚠️  {msg}")


def _info(msg: str):
    print(msg)


def _instrucciones_token() -> str:
    return r"""
Para regenerar el token de Oliver (tarda 20 segundos):

1. Abre https://platform.oliversports.ai en tu navegador y logéate.
2. Abre la consola: Cmd+Option+J (Mac) o F12 (Windows).
3. Pega esto EXACTO y pulsa Enter:

   var s = JSON.parse(localStorage.getItem('OLIVER-Platform.session'));
   console.log('OLIVER_TOKEN=' + s.token);
   console.log('OLIVER_REFRESH_TOKEN=' + s.refresh_token);
   console.log('OLIVER_USER_ID=' + s.user.id);

4. Copia las 3 líneas que imprime.
5. Abre .env del proyecto y pega esas líneas (reemplazando las existentes).
6. Vuelve a lanzar el script.
"""


# ─── Cliente Oliver ─────────────────────────────────────────────────────────
class OliverAPI:
    def __init__(self, token: str, user_id: str):
        if not token:
            _fatal("Falta OLIVER_TOKEN en .env." + _instrucciones_token())
        if not user_id:
            _fatal("Falta OLIVER_USER_ID en .env." + _instrucciones_token())
        self.token = token
        self.user_id = str(user_id)
        self.base = OLIVER_API
        # El JWT lleva dentro los headers con los que se firmó.
        # Oliver valida que los request lleguen con EXACTAMENTE esos mismos headers.
        self._jwt = _decode_jwt_payload(token)

    def _hdr(self):
        # Headers base del cliente
        h = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "x-user-id": self.user_id,
            "x-version": self._jwt.get("x-version") or OLIVER_VERSION,
            "x-from": self._jwt.get("x-from") or "portal",
        }
        # Copiar el User-Agent, Accept-Language y Accept-Encoding tal como
        # los tiene firmados el token (si no coinciden → 401 Unauthorized).
        ua = self._jwt.get("user-agent")
        if ua:
            h["User-Agent"] = ua
        al = self._jwt.get("accept-language")
        if al:
            h["Accept-Language"] = al
        ae = self._jwt.get("accept-encoding")
        if ae:
            h["Accept-Encoding"] = ae
        return h

    def _get(self, path: str, params: dict | None = None, max_retries: int = 2):
        url = f"{self.base}{path}"
        for intento in range(max_retries + 1):
            r = requests.get(url, headers=self._hdr(), params=params, timeout=30)
            if r.status_code == 401:
                _fatal("Token de Oliver caducado o inválido (401)." + _instrucciones_token())
            if r.status_code == 429:
                time.sleep(2 ** intento)
                continue
            if r.status_code >= 500:
                time.sleep(1)
                continue
            r.raise_for_status()
            return r.json()
        _fatal(f"Fallo tras {max_retries+1} intentos en GET {path}")

    def list_sessions(self, team_id: str) -> list[dict]:
        """Devuelve todas las sesiones del equipo (pagina hasta completar)."""
        out: list[dict] = []
        offset, page_size = 0, 250
        while True:
            r = self._get("/sessions/", params={"team_id": team_id, "limit": page_size, "offset": offset})
            batch = r.get("sessions") or []
            total = r.get("total") or len(batch)
            out.extend(batch)
            _info(f"  · paginado: {len(out)}/{total}")
            if len(out) >= total or not batch:
                break
            offset += len(batch)
            if offset >= total:
                break
            time.sleep(0.3)
        return out

    def list_players(self, team_id: str) -> list[dict]:
        """Players del equipo (incluyen user_id)."""
        r = self._get("/players/", params={"team_id": team_id})
        return r.get("players") or []

    def list_users(self, team_id: str) -> list[dict]:
        """Users del equipo (tienen f_name y l_name)."""
        r = self._get("/users/", params={"team_id": team_id})
        return r.get("users") or []

    def build_player_name_map(self, team_id: str) -> dict:
        """Devuelve dict player_id → 'Nombre Apellido'."""
        try:
            players = self.list_players(team_id)
            users   = self.list_users(team_id)
        except Exception as e:
            _warn(f"No pude construir mapa de nombres: {e}")
            return {}
        user_by_id = {u["id"]: u for u in users}
        mapa = {}
        for p in players:
            uid = p.get("user_id")
            u = user_by_id.get(uid)
            if u:
                nom = f"{u.get('f_name','').strip()} {u.get('l_name','').strip()}".strip()
                if nom:
                    mapa[p["id"]] = nom
        return mapa

    def session_average(self, session_id: int) -> dict:
        """Devuelve player_sessions con las 68 métricas por jugador."""
        return self._get(f"/sessions/{session_id}/average", params={"raw_data": 1})

    def session_meta(self, session_id: int) -> dict:
        return self._get(f"/sessions/{session_id}")


# ─── Extracción de métricas ─────────────────────────────────────────────────
def _get_nested(d: dict, path: str, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def extract_mvp(session_meta: dict, player_session: dict, name_map: dict | None = None) -> dict:
    """Extrae las 15 columnas principales para un jugador/sesión."""
    psi = (player_session or {}).get("player_session_info") or {}
    metrics = psi.get("metrics") or {}
    player  = (player_session or {}).get("player") or {}
    player_id = player_session.get("player_id") or player.get("id")

    start_ms = session_meta.get("start") or 0
    fecha = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).date().isoformat() if start_ms else ""

    dist_lsprint = float(_get_nested(metrics, "stats.speed.segments.lsprint.dist", 0) or 0)
    dist_sprint  = float(_get_nested(metrics, "stats.speed.segments.sprint.dist", 0) or 0)
    dist_hsr     = round(dist_lsprint + dist_sprint, 1)

    vel_max_ms = _get_nested(metrics, "stats.speed.max", 0) or 0  # m/s
    vel_max_kmh = round(float(vel_max_ms) * 3.6, 2)

    # Nombre: prioriza mapa (construido desde /users/) → player.name+surname → id
    jugador_nombre = ""
    if name_map and player_id in name_map:
        jugador_nombre = name_map[player_id]
    if not jugador_nombre:
        jugador_nombre = ((player.get("name") or "") + " " + (player.get("surname") or "")).strip()
    if not jugador_nombre:
        jugador_nombre = str(player_id or "")

    return {
        "fecha": fecha,
        "jugador": jugador_nombre,
        "session_id": session_meta.get("id"),
        "session_name": session_meta.get("name") or "",
        "tipo": session_meta.get("type") or "",
        "played_time": round(float(_get_nested(metrics, "played_time", 0) or 0), 2),
        "total_time": round(float(_get_nested(metrics, "total_time", 0) or 0), 2),
        "distancia_total_m": round(float(_get_nested(metrics, "stats.speed.dist", 0) or 0), 1),
        "distancia_hsr_m": dist_hsr,
        "velocidad_max_kmh": vel_max_kmh,
        "acc_alta_count": int(_get_nested(metrics, "stats.acceleration.high.pos.count", 0) or 0),
        "dec_alta_count": int(_get_nested(metrics, "stats.acceleration.high.neg.count", 0) or 0),
        "acc_max_count": int(_get_nested(metrics, "stats.acceleration.max.pos.count", 0) or 0),
        "dec_max_count": int(_get_nested(metrics, "stats.acceleration.max.neg.count", 0) or 0),
        "oliver_load": round(float(_get_nested(metrics, "oli_session_load", 0) or 0), 1),
        "kcal": round(float(_get_nested(metrics, "metabolic_power.kcal_total", 0) or 0), 1),
        "cambios_direccion": int(_get_nested(metrics, "cods.count", 0) or 0),
        "saltos": int(_get_nested(metrics, "jumps.count", 0) or 0),
        "sprints_count": int(_get_nested(metrics, "stats.speed.segments.sprint.count", 0) or 0),
        "rpe_oliver": _rpe_value(player_session.get("rpe")),
    }


def _rpe_value(rpe):
    """Extrae el valor numérico del rpe. A veces Oliver devuelve un dict."""
    if rpe is None or rpe == "":
        return ""
    if isinstance(rpe, dict):
        return rpe.get("value", "")
    return rpe


def flatten_all(metrics: dict, parent: str = "") -> dict:
    """Aplanar cualquier dict anidado a 'a.b.c'."""
    out = {}
    for k, v in (metrics or {}).items():
        key = f"{parent}.{k}" if parent else k
        if isinstance(v, dict):
            out.update(flatten_all(v, key))
        elif isinstance(v, list):
            out[key] = f"[list {len(v)}]"
        else:
            out[key] = v
    return out


def extract_deep(session_meta: dict, player_session: dict, name_map: dict | None = None) -> dict:
    """Las 68 métricas aplanadas (para análisis quincenal)."""
    psi = (player_session or {}).get("player_session_info") or {}
    metrics_flat = flatten_all(psi.get("metrics") or {})
    player = (player_session or {}).get("player") or {}
    player_id = player_session.get("player_id") or player.get("id")
    start_ms = session_meta.get("start") or 0
    fecha = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).date().isoformat() if start_ms else ""
    jugador_nombre = ""
    if name_map and player_id in name_map:
        jugador_nombre = name_map[player_id]
    if not jugador_nombre:
        jugador_nombre = ((player.get("name") or "") + " " + (player.get("surname") or "")).strip()
    if not jugador_nombre:
        jugador_nombre = str(player_id or "")
    base = {
        "fecha": fecha,
        "jugador": jugador_nombre,
        "session_id": session_meta.get("id"),
        "session_name": session_meta.get("name") or "",
        "tipo": session_meta.get("type") or "",
    }
    base.update(metrics_flat)
    return base


# ─── Google Sheets ──────────────────────────────────────────────────────────
def gs_client():
    if not CREDS_FILE.is_file():
        _fatal(f"No encuentro credenciales en {CREDS_FILE}")
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds)


def escribir_vista(ss, nombre_hoja: str, df: pd.DataFrame) -> None:
    if df.empty:
        _warn(f"{nombre_hoja}: no hay filas que escribir.")
        return
    df = df.copy()
    # Serializar fechas si las hay
    for col in df.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]):
        df[col] = df[col].dt.strftime("%Y-%m-%d")
    df = df.where(pd.notnull(df), "")
    # Salvaguarda: convertir dict/list a string (gspread solo acepta escalares)
    def _flat(v):
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)[:200]
        return v
    df = df.map(_flat) if hasattr(df, "map") else df.applymap(_flat)

    existentes = {ws.title for ws in ss.worksheets()}
    if nombre_hoja in existentes:
        ws = ss.worksheet(nombre_hoja)
        ws.clear()
        time.sleep(0.5)
    else:
        ws = ss.add_worksheet(title=nombre_hoja, rows=max(len(df) + 10, 100), cols=len(df.columns) + 2)
        time.sleep(1)

    headers = [df.columns.tolist()]
    rows = df.astype(object).where(pd.notnull(df), "").values.tolist()
    ws.update("A1", headers + rows)
    time.sleep(1)
    _info(f"  ✓ {nombre_hoja}: {len(df)} filas, {len(df.columns)} columnas")


def leer_sesiones_previas(ss) -> set[int]:
    """Lista de session_id ya sincronizados (para modo incremental)."""
    existentes = {ws.title for ws in ss.worksheets()}
    if HOJA_SESS not in existentes:
        return set()
    ws = ss.worksheet(HOJA_SESS)
    valores = ws.col_values(1)[1:]  # saltar header
    return {int(v) for v in valores if v.strip().isdigit()}


def guardar_ids_sesiones(ss, session_ids: list[int]) -> None:
    """Guarda el listado de session_ids sincronizados."""
    df = pd.DataFrame({"session_id": session_ids})
    escribir_vista(ss, HOJA_SESS, df)


# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Sincroniza Oliver Sports con el Google Sheet.")
    parser.add_argument("--todas", action="store_true",
                        help="Rehace TODAS las sesiones (no solo las nuevas).")
    parser.add_argument("--deep", action="store_true",
                        help="Incluye las 68 métricas aplanadas en hoja _OLIVER_DEEP (quincenal).")
    args = parser.parse_args()

    api = OliverAPI(OLIVER_TOKEN, OLIVER_USER)
    client = gs_client()
    ss = client.open(SHEET_NAME)

    _info(f"▶ Construyendo mapa player_id → nombre…")
    name_map = api.build_player_name_map(OLIVER_TEAM)
    _info(f"  → {len(name_map)} jugadores mapeados")

    _info(f"▶ Listando sesiones del equipo {OLIVER_TEAM}…")
    sesiones = api.list_sessions(OLIVER_TEAM)
    _info(f"  → {len(sesiones)} sesiones totales en Oliver")

    # Solo PROCESSED
    sesiones = [s for s in sesiones if s.get("status") == "PROCESSED"]
    _info(f"  → {len(sesiones)} procesadas")

    # Filtrar incrementalmente
    ya_sincronizadas: set[int] = set() if args.todas else leer_sesiones_previas(ss)
    nuevas = [s for s in sesiones if s["id"] not in ya_sincronizadas]
    _info(f"  → {len(nuevas)} nuevas a procesar")

    if not nuevas and not args.todas:
        _info("✓ Nada que hacer. Todo al día.")
        return

    objetivo = sesiones if args.todas else nuevas

    filas_mvp = []
    filas_deep = []
    for i, sess_meta in enumerate(objetivo, 1):
        sid = sess_meta["id"]
        _info(f"  [{i}/{len(objetivo)}] session {sid} ({sess_meta.get('name','?')})")
        try:
            avg = api.session_average(sid)
        except Exception as e:
            _warn(f"    fallo session {sid}: {e}")
            continue
        player_sessions = (avg or {}).get("player_sessions") or []
        for ps in player_sessions:
            filas_mvp.append(extract_mvp(sess_meta, ps, name_map))
            if args.deep:
                filas_deep.append(extract_deep(sess_meta, ps, name_map))
        time.sleep(0.3)  # respetar rate limit

    if not filas_mvp:
        _info("Sin datos nuevos válidos.")
        return

    # Construir DataFrames
    df_mvp = pd.DataFrame(filas_mvp)[MVP_COLUMNS] if filas_mvp else pd.DataFrame(columns=MVP_COLUMNS)
    df_mvp = df_mvp.sort_values(["fecha", "jugador"])

    # Si es incremental: unir con existente antes de reescribir
    if not args.todas:
        existentes = {ws.title for ws in ss.worksheets()}
        if HOJA_MVP in existentes:
            ws_prev = ss.worksheet(HOJA_MVP)
            prev_data = ws_prev.get_all_records()
            if prev_data:
                df_prev = pd.DataFrame(prev_data)
                # Asegurar mismas columnas
                for c in MVP_COLUMNS:
                    if c not in df_prev.columns:
                        df_prev[c] = ""
                df_prev = df_prev[MVP_COLUMNS]
                df_mvp = pd.concat([df_prev, df_mvp], ignore_index=True)
                df_mvp = df_mvp.drop_duplicates(["session_id", "jugador"], keep="last")
                df_mvp = df_mvp.sort_values(["fecha", "jugador"])

    _info(f"▶ Escribiendo {len(df_mvp)} filas a hoja '{HOJA_MVP}'…")
    escribir_vista(ss, HOJA_MVP, df_mvp)

    # Deep (quincenal)
    if args.deep and filas_deep:
        df_deep = pd.DataFrame(filas_deep).sort_values(["fecha", "jugador"])
        _info(f"▶ Escribiendo {len(df_deep)} filas a hoja '{HOJA_DEEP}'…")
        escribir_vista(ss, HOJA_DEEP, df_deep)

    # Guardar IDs para próximo incremental
    todos_ids = sorted({int(r["session_id"]) for r in filas_mvp if r.get("session_id")} | ya_sincronizadas)
    guardar_ids_sesiones(ss, todos_ids)

    _info("\n✓ Sincronización terminada.")
    _info(f"  https://docs.google.com/spreadsheets/d/{ss.id}")


if __name__ == "__main__":
    main()

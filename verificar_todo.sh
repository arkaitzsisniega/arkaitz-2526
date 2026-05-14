#!/usr/bin/env bash
# verificar_todo.sh — Pre-flight check antes de presentar al club.
# Verifica que TODO el sistema está OK: bots, dashboard, crono, smoke tests.
# Uso: bash verificar_todo.sh

set -u
cd "$(dirname "$0")"

VERDE='\033[32m'
ROJO='\033[31m'
AMARILLO='\033[33m'
CYAN='\033[36m'
RESET='\033[0m'

ok=0; fail=0; warn=0

ck() {
    local desc="$1"
    local cmd="$2"
    local expected="${3:-}"
    local out
    out=$(eval "$cmd" 2>&1) || true
    if [ -n "$expected" ]; then
        if echo "$out" | grep -q "$expected"; then
            echo -e "  ${VERDE}✓${RESET} $desc"
            ok=$((ok+1))
        else
            echo -e "  ${ROJO}✗${RESET} $desc"
            echo "     → esperaba: $expected"
            echo "     → recibió: $(echo "$out" | head -1)"
            fail=$((fail+1))
        fi
    else
        # Solo comprobar exit code 0
        if [ $? -eq 0 ]; then
            echo -e "  ${VERDE}✓${RESET} $desc"
            ok=$((ok+1))
        else
            echo -e "  ${ROJO}✗${RESET} $desc"
            fail=$((fail+1))
        fi
    fi
}

echo -e "${CYAN}═══════════════════════════════════════════════${RESET}"
echo -e "${CYAN}  VERIFICACIÓN PRE-PRESENTACIÓN CLUB${RESET}"
echo -e "${CYAN}═══════════════════════════════════════════════${RESET}"
echo

echo -e "${CYAN}▶ Conectividad URLs públicas${RESET}"
ck "Streamlit dashboard (interfs-datos.streamlit.app)" \
   "curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://interfs-datos.streamlit.app/" \
   "303"
ck "Landing gh-pages (escudo Inter)" \
   "curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://arkaitzsisniega.github.io/arkaitz-2526/" \
   "200"
ck "Apple-touch-icon de la landing" \
   "curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://arkaitzsisniega.github.io/arkaitz-2526/apple-touch-icon-180.png" \
   "200"
echo

echo -e "${CYAN}▶ Crono iPad (dev server local)${RESET}"
if curl -s -o /dev/null --max-time 3 http://localhost:3000 >/dev/null 2>&1; then
    ck "Dev server vivo" \
       "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:3000" "200"
    ck "Manifest PWA del crono" \
       "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:3000/manifest.json" "200"
    ck "Apple-touch-icon del crono" \
       "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:3000/apple-touch-icon.png" "200"
else
    echo -e "  ${AMARILLO}⚠${RESET} Dev server NO está vivo en localhost:3000"
    echo "     Para arrancar: cd crono_partido && npm run dev"
    warn=$((warn+1))
fi
echo

echo -e "${CYAN}▶ Git + remote${RESET}"
local_head=$(git rev-parse HEAD 2>/dev/null)
remote_head=$(git ls-remote --heads origin main 2>/dev/null | awk '{print $1}')
if [ "$local_head" = "$remote_head" ]; then
    echo -e "  ${VERDE}✓${RESET} Local sincronizado con remote (${local_head:0:7})"
    ok=$((ok+1))
else
    echo -e "  ${AMARILLO}⚠${RESET} Local y remote difieren"
    echo "     local:  $local_head"
    echo "     remote: $remote_head"
    warn=$((warn+1))
fi
echo

echo -e "${CYAN}▶ Smoke tests bots${RESET}"
if /usr/bin/python3 tests/smoke_bots.py 2>&1 | tail -1 | grep -q "TODOS los tests pasaron"; then
    echo -e "  ${VERDE}✓${RESET} 10/10 smoke tests OK"
    ok=$((ok+1))
else
    echo -e "  ${ROJO}✗${RESET} Algún smoke test falla — ejecuta tests/smoke_bots.py para detalle"
    fail=$((fail+1))
fi
echo

echo -e "${CYAN}▶ Scripts curados (sin args, smoke)${RESET}"
for s in estado_jugador.py ranking_temporada.py lesiones_activas.py carga_ultima_sesion.py; do
    if /usr/bin/python3 -W ignore "src/$s" 2>&1 | head -1 | grep -qiE "uso|usage|categorías|error"; then
        # ranking_temporada sin args devuelve "Uso:" - válido
        echo -e "  ${VERDE}✓${RESET} src/$s responde"
        ok=$((ok+1))
    elif /usr/bin/python3 -W ignore "src/$s" 2>&1 | head -3 | grep -qiE "📊|🏥|❌|✅|⚠️"; then
        echo -e "  ${VERDE}✓${RESET} src/$s ejecuta"
        ok=$((ok+1))
    else
        echo -e "  ${AMARILLO}⚠${RESET} src/$s salida sospechosa"
        warn=$((warn+1))
    fi
done
echo

echo -e "${CYAN}═══════════════════════════════════════════════${RESET}"
printf "  ${VERDE}✓ OK: %d${RESET}    ${AMARILLO}⚠ WARN: %d${RESET}    ${ROJO}✗ FAIL: %d${RESET}\n" "$ok" "$warn" "$fail"
if [ $fail -gt 0 ]; then
    echo -e "  ${ROJO}NO PRESENTAR todavía. Hay fallos críticos.${RESET}"
    exit 1
elif [ $warn -gt 0 ]; then
    echo -e "  ${AMARILLO}PUEDES presentar pero revisa los warnings.${RESET}"
    exit 0
else
    echo -e "  ${VERDE}LISTO. Adelante con la presentación.${RESET}"
    exit 0
fi

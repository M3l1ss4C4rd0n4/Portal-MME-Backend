#!/bin/bash
# check_types.sh — Verificación rápida de tipos antes de push
# Uso: ./check_types.sh [--strict]

set -e
cd "$(dirname "$0")"
source venv/bin/activate

MODE="${1:-basic}"

echo "════════════════════════════════════════"
echo "  ENERTRACE — Type Check (Pyright)"
echo "════════════════════════════════════════"

if [ "$1" == "--strict" ]; then
    pyright --pythonversion 3.12 2>&1 | tail -20
else
    # Solo contar errores reales (severity=error)
    OUTPUT=$(pyright --outputjson 2>/dev/null || echo '{}')
    ERRORS=$(echo "$OUTPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    diags = data.get('generalDiagnostics', [])
    errors   = [d for d in diags if d.get('severity') == 'error']
    warnings = [d for d in diags if d.get('severity') == 'warning']
    print(f'Errores  : {len(errors)}')
    print(f'Warnings : {len(warnings)}')
    if errors:
        print()
        print('TOP ERRORES:')
        for e in errors[:15]:
            f = e.get('file','')
            # relative path
            import os
            f = os.path.relpath(f)
            r = e.get('range',{}).get('start',{}).get('line',0)+1
            msg = e.get('message','')[:90]
            print(f'  {f}:{r}  {msg}')
except Exception as ex:
    print(f'Error parseando output: {ex}')
" 2>&1)
    echo "$ERRORS"
    echo ""
    if echo "$ERRORS" | grep -q "Errores  : 0"; then
        echo "✅ Sin errores de tipo"
        exit 0
    else
        echo "❌ Hay errores — corrige antes de hacer push"
        exit 1
    fi
fi

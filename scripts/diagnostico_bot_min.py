#!/usr/bin/env python3
"""
DIAGNÓSTICO: session_id "bot_min" — Data quemada vs Data real

Script de simulación controlada para validar que las solicitudes con
session_id: "bot_min" llegan correctamente al endpoint del orquestador
y comparar la estructura de data quemada vs data real.

Ejecutar:
    python3 tests/test_bot_min_diagnostico.py

Autor: Diagnóstico técnico – Portal Energético MME
Fecha: 19 de febrero de 2026
"""

import os
import requests
import json
import sys
from datetime import datetime

API_BASE = os.environ.get("PORTAL_API_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("PORTAL_API_KEY", "")
HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
}
ENDPOINT = f"{API_BASE}/v1/chatbot/orchestrator"


def separador(titulo: str):
    print(f"\n{'='*80}")
    print(f"  {titulo}")
    print(f"{'='*80}\n")


def enviar_request(descripcion: str, body: dict) -> dict:
    """Envía un request al orquestador y muestra resultado detallado."""
    print(f"📤 {descripcion}")
    print(f"   Body: {json.dumps(body, ensure_ascii=False)}")
    try:
        r = requests.post(ENDPOINT, json=body, headers=HEADERS, timeout=60)
        print(f"   HTTP Status: {r.status_code}")
        try:
            data = r.json()
            print(f"   Response status: {data.get('status', 'N/A')}")
            print(f"   Response message: {data.get('message', 'N/A')[:100]}")
            print(f"   SessionId echo: {data.get('sessionId', 'N/A')}")
            print(f"   Intent echo: {data.get('intent', 'N/A')}")
            print(f"   Errors: {data.get('errors', [])}")
            if data.get('data'):
                keys = list(data['data'].keys())
                print(f"   Data keys: {keys}")
            else:
                print(f"   Data: VACÍO")
            return data
        except Exception:
            print(f"   Raw response: {r.text[:200]}")
            return {"raw": r.text, "status_code": r.status_code}
    except requests.exceptions.ConnectionError:
        print(f"   ❌ ERROR: No se pudo conectar al servidor en {API_BASE}")
        return {"error": "connection_error"}
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return {"error": str(e)}


def main():
    separador("DIAGNÓSTICO: session_id 'bot_min' — Validación completa")
    print(f"Fecha: {datetime.now().isoformat()}")
    print(f"Endpoint: {ENDPOINT}")

    # ══════════════════════════════════════════════════════════════
    # TEST 1: Request CORRECTO con sessionId (camelCase) — "data quemada" OK
    # ══════════════════════════════════════════════════════════════
    separador("TEST 1: sessionId (camelCase) — Formato correcto (data quemada)")
    r1 = enviar_request(
        "Request con sessionId camelCase + intent 'menu'",
        {
            "sessionId": "bot_min",
            "intent": "menu",
            "parameters": {}
        }
    )

    # ══════════════════════════════════════════════════════════════
    # TEST 2: Request con session_id (snake_case) — ERROR ESPERADO
    # ══════════════════════════════════════════════════════════════
    separador("TEST 2: session_id (snake_case) — Formato INCORRECTO")
    r2 = enviar_request(
        "Request con session_id snake_case (FALLA: sessionId requerido)",
        {
            "session_id": "bot_min",
            "intent": "menu",
            "parameters": {}
        }
    )

    # ══════════════════════════════════════════════════════════════
    # TEST 3: Request sin campo 'intent' — ERROR ESPERADO
    # ══════════════════════════════════════════════════════════════
    separador("TEST 3: Sin campo 'intent' — Formato INCORRECTO")
    r3 = enviar_request(
        "Request sin intent (FALLA: intent requerido)",
        {
            "sessionId": "bot_min",
            "message": "hola",
            "parameters": {}
        }
    )

    # ══════════════════════════════════════════════════════════════
    # TEST 4: Request con 'query' en lugar de 'intent' — ERROR ESPERADO
    # ══════════════════════════════════════════════════════════════
    separador("TEST 4: 'query' en lugar de 'intent' — Formato INCORRECTO")
    r4 = enviar_request(
        "Request con query en vez de intent (FALLA: intent requerido)",
        {
            "sessionId": "bot_min",
            "query": "estado_actual",
            "parameters": {}
        }
    )

    # ══════════════════════════════════════════════════════════════
    # TEST 5: Request CORRECTO con intent 'estado_actual' — data REAL
    # ══════════════════════════════════════════════════════════════
    separador("TEST 5: sessionId + intent 'estado_actual' — Data REAL")
    r5 = enviar_request(
        "Request correcto con datos reales del sistema",
        {
            "sessionId": "bot_min",
            "intent": "estado_actual",
            "parameters": {}
        }
    )

    # ══════════════════════════════════════════════════════════════
    # TEST 6: Request sin 'parameters' — Debe funcionar (default={})
    # ══════════════════════════════════════════════════════════════
    separador("TEST 6: Sin campo 'parameters' — Debe funcionar")
    r6 = enviar_request(
        "Request sin parameters (default: {})",
        {
            "sessionId": "bot_min",
            "intent": "estado_actual"
        }
    )

    # ══════════════════════════════════════════════════════════════
    # TEST 7: Request con intent NO reconocido
    # ══════════════════════════════════════════════════════════════
    separador("TEST 7: Intent no reconocido")
    r7 = enviar_request(
        "Request con intent desconocido",
        {
            "sessionId": "bot_min",
            "intent": "consulta_general",
            "parameters": {"pregunta": "hola"}
        }
    )

    # ══════════════════════════════════════════════════════════════
    # TEST 8: Request sin API Key — 401 esperado
    # ══════════════════════════════════════════════════════════════
    separador("TEST 8: Sin API Key — 401 esperado")
    print(f"📤 Request sin X-API-Key")
    try:
        r8_raw = requests.post(
            ENDPOINT,
            json={"sessionId": "bot_min", "intent": "menu", "parameters": {}},
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        print(f"   HTTP Status: {r8_raw.status_code}")
        print(f"   Response: {r8_raw.text[:200]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    # ══════════════════════════════════════════════════════════════
    # RESUMEN DE DIAGNÓSTICO
    # ══════════════════════════════════════════════════════════════
    separador("RESUMEN DE DIAGNÓSTICO")

    print("""
┌──────────────────────────────────────────────────────────────────────────────┐
│ CAMPO ESPERADO POR EL BACKEND (Pydantic schema)                            │
├──────────────────────────────────────────────────────────────────────────────┤
│ Campo          │ Tipo          │ Requerido │ Notas                          │
│────────────────│───────────────│───────────│────────────────────────────────│
│ sessionId      │ str           │ SÍ        │ camelCase, NO session_id       │
│ intent         │ str           │ SÍ        │ snake_case (ej: estado_actual) │
│ parameters     │ Dict[str,Any] │ NO        │ Default: {}                    │
└──────────────────────────────────────────────────────────────────────────────┘

⚠️  PROBLEMAS QUE CAUSAN FALLO EN PRODUCCIÓN (data real):

1) Si el cliente envía "session_id" → FALLA (el backend espera "sessionId")
2) Si el cliente envía "message"/"query" → FALLA (el backend espera "intent")
3) Si falta el header "X-API-Key" → 401 Unauthorized
4) Si el intent no está en la lista de intents válidos → ERROR "UNKNOWN_INTENT"

✅ EN MODO CONFIGURACIÓN (data quemada) funciona porque:
   - Se usa exactamente {sessionId, intent, parameters} con los nombres correctos
   - El intent es uno reconocido (menu, estado_actual, etc.)

❌ EN PRODUCCIÓN puede fallar si:
   - El cliente externo usa "session_id" (snake_case) en vez de "sessionId"
   - El cliente envía "message" o "query" en vez de "intent"
   - El intent enviado no coincide con los registrados en el orquestador
   - Falta el API Key en los headers
""")

    # Resultados
    tests_ok = 0
    tests_fail = 0

    for i, (nombre, resultado, esperado_ok) in enumerate([
        ("sessionId camelCase + intent", r1, True),
        ("session_id snake_case", r2, False),
        ("Sin campo intent", r3, False),
        ("query en vez de intent", r4, False),
        ("estado_actual (data real)", r5, True),
        ("Sin parameters", r6, True),
        ("Intent no reconocido", r7, False),
    ], 1):
        status = resultado.get('status', '')
        es_ok = status in ('SUCCESS', 'PARTIAL_SUCCESS') if esperado_ok else (status == 'ERROR' or 'error' in resultado)
        icono = "✅" if es_ok else "❌"
        if es_ok:
            tests_ok += 1
        else:
            tests_fail += 1
        print(f"   {icono} Test {i}: {nombre} → {status or resultado.get('error','VALIDATION_ERROR')}")

    print(f"\n   Total: {tests_ok} pasaron, {tests_fail} fallaron")
    print(f"   {'✅ Todos los tests pasaron correctamente' if tests_fail == 0 else '⚠️  Hay tests que fallaron'}")
    print()


if __name__ == "__main__":
    main()

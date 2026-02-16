#!/usr/bin/env python3
"""
Script de inspección senior para validar endpoint orquestador
Valida disponibilidad, seguridad, contratos y documentación
"""
import requests
import json
import sys
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "MME2026_SECURE_KEY"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")

def print_test(name, passed, details=""):
    status = f"{Colors.GREEN}✓ PASS{Colors.END}" if passed else f"{Colors.RED}✗ FAIL{Colors.END}"
    print(f"{status} | {name}")
    if details:
        print(f"      {details}")

# INSPECCIÓN 1: Health Check
print_header("INSPECCIÓN 1: ENDPOINT HEALTH CHECK")
try:
    response = requests.get(f"{BASE_URL}/api/v1/chatbot/health", timeout=5)
    health_ok = response.status_code == 200
    print_test("Health endpoint accesible", health_ok, f"HTTP {response.status_code}")
    
    if health_ok:
        data = response.json()
        print_test("Response es JSON válido", True)
        print_test("Contiene campo 'status'", 'status' in data, f"Status: {data.get('status', 'N/A')}")
        print_test("Contiene timestamp", 'timestamp' in data)
except Exception as e:
    print_test("Health endpoint accesible", False, str(e))
    health_ok = False

# INSPECCIÓN 2: Seguridad - API Key
print_header("INSPECCIÓN 2: SEGURIDAD (API KEY VALIDATION)")

# Test sin API Key
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/chatbot/orchestrator",
        json={"sessionId": "test", "intent": "metricas_generales", "parameters": {}},
        timeout=5
    )
    sin_key = response.status_code == 401
    print_test("Rechaza requests sin API Key", sin_key, f"HTTP {response.status_code}")
except Exception as e:
    print_test("Rechaza requests sin API Key", False, str(e))

# Test con API Key inválida
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/chatbot/orchestrator",
        headers={"X-API-Key": "INVALID_KEY"},
        json={"sessionId": "test", "intent": "metricas_generales", "parameters": {}},
        timeout=5
    )
    key_invalida = response.status_code == 401
    print_test("Rechaza API Key inválida", key_invalida, f"HTTP {response.status_code}")
except Exception as e:
    print_test("Rechaza API Key inválida", False, str(e))

# INSPECCIÓN 3: Validación de contratos
print_header("INSPECCIÓN 3: VALIDACIÓN DE CONTRATOS")

# Test con datos inválidos (sessionId vacío)
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/chatbot/orchestrator",
        headers={"X-API-Key": API_KEY},
        json={"sessionId": "", "intent": "metricas_generales", "parameters": {}},
        timeout=5
    )
    valida_sesion = response.status_code == 422
    print_test("Valida sessionId vacío", valida_sesion, f"HTTP {response.status_code}")
except Exception as e:
    print_test("Valida sessionId vacío", False, str(e))

# Test con intent inválido
try:
    response = requests.post(
        f"{BASE_URL}/api/v1/chatbot/orchestrator",
        headers={"X-API-Key": API_KEY},
        json={"sessionId": "test-123", "intent": "INTENT_NO_EXISTE", "parameters": {}},
        timeout=5
    )
    valida_intent = response.status_code == 422
    print_test("Valida intent inválido", valida_intent, f"HTTP {response.status_code}")
except Exception as e:
    print_test("Valida intent inválido", False, str(e))

# INSPECCIÓN 4: Endpoints funcionales
print_header("INSPECCIÓN 4: PRUEBAS FUNCIONALES POR INTENT")

intents_a_probar = [
    "metricas_generales",
    "generacion_electrica",
    "hidrologia",
    "demanda_sistema",
    "precio_bolsa",
    "predicciones",
    "informe_ejecutivo"
]

resultados_intents = {}
for intent in intents_a_probar:
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/chatbot/orchestrator",
            headers={
                "X-API-Key": API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "sessionId": f"test-{intent}-{datetime.now().timestamp()}",
                "intent": intent,
                "parameters": {}
            },
            timeout=30
        )
        
        success = response.status_code == 200
        resultados_intents[intent] = success
        
        if success:
            data = response.json()
            tiene_status = 'status' in data
            tiene_message = 'message' in data
            tiene_data = 'data' in data
            
            print_test(
                f"Intent '{intent}'",
                success and tiene_status and tiene_message,
                f"Status: {data.get('status', 'N/A')}"
            )
        else:
            print_test(f"Intent '{intent}'", False, f"HTTP {response.status_code}")
            
    except requests.Timeout:
        print_test(f"Intent '{intent}'", False, "Timeout (>30s)")
        resultados_intents[intent] = False
    except Exception as e:
        print_test(f"Intent '{intent}'", False, str(e)[:50])
        resultados_intents[intent] = False

# INSPECCIÓN 5: Formato de respuesta
print_header("INSPECCIÓN 5: FORMATO Y ESTRUCTURA DE RESPONSE")

try:
    response = requests.post(
        f"{BASE_URL}/api/v1/chatbot/orchestrator",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={"sessionId": "format-test", "intent": "metricas_generales", "parameters": {}},
        timeout=30
    )
    
    if response.status_code == 200:
        data = response.json()
        
        # Validar campos obligatorios del contrato
        print_test("Tiene campo 'status'", 'status' in data)
        print_test("Tiene campo 'message'", 'message' in data)
        print_test("Tiene campo 'data'", 'data' in data)
        print_test("Tiene campo 'errors'", 'errors' in data)
        print_test("Tiene campo 'timestamp'", 'timestamp' in data)
        print_test("Tiene campo 'sessionId'", 'sessionId' in data)
        print_test("Tiene campo 'intent'", 'intent' in data)
        
        # Validar valores permitidos en status
        status_valido = data.get('status') in ['SUCCESS', 'PARTIAL_SUCCESS', 'ERROR']
        print_test("Status es valor permitido", status_valido, f"Valor: {data.get('status')}")
        
        # Validar que errors es un array
        errors_es_lista = isinstance(data.get('errors', []), list)
        print_test("Errors es array/lista", errors_es_lista)
        
except Exception as e:
    print_test("Validación de formato", False, str(e))

# INSPECCIÓN 6: Disponibilidad 24/7 (configuración systemd)
print_header("INSPECCIÓN 6: CONFIGURACIÓN SERVICIO 24/7")

import subprocess

try:
    # Verificar estado del servicio
    result = subprocess.run(
        ["systemctl", "is-active", "api-mme"],
        capture_output=True,
        text=True
    )
    servicio_activo = result.stdout.strip() == "active"
    print_test("Servicio systemd activo", servicio_activo)
    
    # Verificar auto-start
    result = subprocess.run(
        ["systemctl", "is-enabled", "api-mme"],
        capture_output=True,
        text=True
    )
    auto_start = result.stdout.strip() == "enabled"
    print_test("Auto-start habilitado (boot)", auto_start)
    
    # Verificar procesos gunicorn
    result = subprocess.run(
        ["pgrep", "-f", "gunicorn.*api.main"],
        capture_output=True,
        text=True
    )
    num_workers = len(result.stdout.strip().split('\n'))
    tiene_workers = num_workers >= 4
    print_test("Múltiples workers activos", tiene_workers, f"{num_workers} procesos")
    
except Exception as e:
    print_test("Verificación systemd", False, str(e))

# INSPECCIÓN 7: Documentación
print_header("INSPECCIÓN 7: DOCUMENTACIÓN (SWAGGER/OPENAPI)")

try:
    # Verificar OpenAPI schema
    response = requests.get(f"{BASE_URL}/api/openapi.json", timeout=5)
    openapi_ok = response.status_code == 200
    print_test("OpenAPI schema accesible", openapi_ok, f"HTTP {response.status_code}")
    
    if openapi_ok:
        schema = response.json()
        tiene_info = 'info' in schema
        tiene_paths = 'paths' in schema
        print_test("Schema tiene 'info'", tiene_info)
        print_test("Schema tiene 'paths'", tiene_paths)
        
        if tiene_paths:
            orchestrator_documented = '/api/v1/chatbot/orchestrator' in schema['paths']
            health_documented = '/api/v1/chatbot/health' in schema['paths']
            print_test("Orchestrator documentado", orchestrator_documented)
            print_test("Health documentado", health_documented)
            
except Exception as e:
    print_test("Documentación OpenAPI", False, str(e))

try:
    response = requests.get(f"{BASE_URL}/api/docs", timeout=5)
    swagger_ok = response.status_code == 200
    print_test("Swagger UI accesible", swagger_ok, f"HTTP {response.status_code}")
except Exception as e:
    print_test("Swagger UI accesible", False, str(e))

# RESUMEN FINAL
print_header("RESUMEN EJECUTIVO")

total_intents = len(intents_a_probar)
intents_ok = sum(1 for v in resultados_intents.values() if v)

print(f"📊 Intents funcionales: {intents_ok}/{total_intents}")
print(f"🔐 Seguridad API Key: {'✓' if sin_key and key_invalida else '✗'}")
print(f"📋 Validación contratos: {'✓' if valida_sesion and valida_intent else '✗'}")
print(f"🚀 Servicio 24/7: {'✓' if servicio_activo and auto_start else '✗'}")
print(f"📚 Documentación: {'✓' if openapi_ok and swagger_ok else '✗'}")

# Porcentaje de cumplimiento
print(f"\n{Colors.BOLD}Porcentaje de cumplimiento:{Colors.END} {intents_ok/total_intents*100:.1f}% (intents)")

if intents_ok == total_intents and servicio_activo and openapi_ok:
    print(f"\n{Colors.GREEN}{Colors.BOLD}✅ SISTEMA COMPLETAMENTE OPERACIONAL{Colors.END}")
    print(f"{Colors.GREEN}Listo para consumo desde servidor externo{Colors.END}\n")
    sys.exit(0)
else:
    print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  REQUIERE ATENCIÓN{Colors.END}")
    print(f"{Colors.YELLOW}Algunos componentes necesitan revisión{Colors.END}\n")
    sys.exit(1)

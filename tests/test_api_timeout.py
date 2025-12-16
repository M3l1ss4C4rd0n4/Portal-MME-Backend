#!/usr/bin/env python3
"""
Test rápido para verificar si la API XM responde o hace timeout
"""
import sys
import time
import signal
from datetime import date, timedelta

# Timeout handler
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Timeout alcanzado")

signal.signal(signal.SIGALRM, timeout_handler)

try:
    from utils._xm import get_objetoAPI
    print("✅ Módulo utils._xm importado correctamente")
except Exception as e:
    print(f"❌ Error importando utils._xm: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("TEST: TIEMPO DE RESPUESTA DE API XM")
print("="*60)

# Test 1: Inicialización de API
print("\n1️⃣ Inicializando API XM...")
inicio = time.time()
try:
    signal.alarm(10)  # Timeout de 10 segundos
    objetoAPI = get_objetoAPI()
    signal.alarm(0)  # Cancelar alarma
    
    if objetoAPI is None:
        print("❌ API retornó None")
        sys.exit(1)
    
    tiempo_init = time.time() - inicio
    print(f"✅ API inicializada en {tiempo_init:.2f}s")
    
except TimeoutException:
    print("❌ TIMEOUT: Inicialización excedió 10 segundos")
    sys.exit(1)
except Exception as e:
    signal.alarm(0)
    print(f"❌ Error inicializando API: {e}")
    sys.exit(1)

# Test 2: Request simple
print("\n2️⃣ Probando request simple (ListadoRecursos)...")
fecha_fin = date.today() - timedelta(days=14)
fecha_inicio = fecha_fin - timedelta(days=7)

inicio = time.time()
try:
    signal.alarm(15)  # Timeout de 15 segundos
    recursos = objetoAPI.request_data("ListadoRecursos", "Sistema", fecha_inicio, fecha_fin)
    signal.alarm(0)
    
    tiempo_request = time.time() - inicio
    
    if recursos is not None and not recursos.empty:
        print(f"✅ Datos recibidos en {tiempo_request:.2f}s")
        print(f"   - Registros: {len(recursos)}")
        if 'Values_Type' in recursos.columns:
            tipos = recursos['Values_Type'].dropna().unique()
            print(f"   - Tipos de fuente: {len(tipos)}")
    else:
        print(f"⚠️ Request completó en {tiempo_request:.2f}s pero sin datos")
        
except TimeoutException:
    print("❌ TIMEOUT: Request excedió 15 segundos")
    print("\n🔍 DIAGNÓSTICO:")
    print("   - La API de XM está extremadamente lenta")
    print("   - Necesitas implementar timeout o cache")
    print("   - Considera usar datos pre-cargados")
    sys.exit(1)
except Exception as e:
    signal.alarm(0)
    print(f"❌ Error en request: {e}")
    sys.exit(1)

# Test 3: Request con mayor rango
print("\n3️⃣ Probando request con mayor rango (30 días)...")
fecha_fin = date.today() - timedelta(days=3)
fecha_inicio = fecha_fin - timedelta(days=30)

inicio = time.time()
try:
    signal.alarm(20)  # Timeout de 20 segundos
    
    # Solo probar si tenemos códigos
    if recursos is not None and not recursos.empty and 'Values_Code' in recursos.columns:
        codigos = recursos['Values_Code'].dropna().head(5).tolist()  # Solo 5 plantas
        print(f"   - Probando con {len(codigos)} plantas...")
        
        # Simulación de request de generación (sin hacer el request real para no tardar)
        print(f"   ⏭️  Saltado (tomaría demasiado tiempo)")
        signal.alarm(0)
    else:
        print("   ⚠️  No hay códigos de plantas para probar")
        signal.alarm(0)
        
except TimeoutException:
    print("❌ TIMEOUT: Request de generación excedió 20 segundos")
except Exception as e:
    signal.alarm(0)
    print(f"❌ Error: {e}")

print("\n" + "="*60)
print("✅ TEST COMPLETADO")
print("="*60)

print("\n📊 RESUMEN:")
if tiempo_init < 3:
    print("   ✅ Inicialización: RÁPIDA")
elif tiempo_init < 7:
    print("   ⚠️  Inicialización: NORMAL")
else:
    print("   ❌ Inicialización: LENTA")

if tiempo_request < 5:
    print("   ✅ Request básico: RÁPIDO")
elif tiempo_request < 10:
    print("   ⚠️  Request básico: NORMAL")
else:
    print("   ❌ Request básico: LENTO")

print("\n💡 RECOMENDACIONES:")
if tiempo_init > 5 or tiempo_request > 10:
    print("   1. Implementar cache de datos (Redis o archivo)")
    print("   2. Usar timeout de 15-20 segundos máximo")
    print("   3. Mostrar mensajes de progreso al usuario")
    print("   4. Considerar carga asíncrona o en background")
else:
    print("   ✅ La API está respondiendo bien actualmente")

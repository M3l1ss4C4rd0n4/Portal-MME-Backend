#!/usr/bin/env python3
"""
Test rápido para verificar que las funciones de tabs funcionan correctamente
"""

import sys
sys.path.insert(0, '/home/admonctrlxm/server')

from pages.generacion_fuentes_unificado import crear_contenido_analisis_general, crear_contenido_comparacion_anual

print("🧪 Probando funciones de tabs...")
print()

try:
    print("1️⃣ Probando crear_contenido_analisis_general()...")
    contenido_general = crear_contenido_analisis_general()
    print(f"   ✅ Devuelve {type(contenido_general)} con {len(contenido_general)} elementos")
    print()
    
    print("2️⃣ Probando crear_contenido_comparacion_anual()...")
    contenido_anual = crear_contenido_comparacion_anual()
    print(f"   ✅ Devuelve {type(contenido_anual)} con {len(contenido_anual)} elementos")
    print()
    
    print("✅ ¡Todas las funciones funcionan correctamente!")
    print()
    print("📋 Estructura de contenido_analisis_general:")
    for i, elemento in enumerate(contenido_general):
        print(f"   [{i}] {type(elemento).__name__}")
    print()
    print("📋 Estructura de contenido_comparacion_anual:")
    for i, elemento in enumerate(contenido_anual):
        print(f"   [{i}] {type(elemento).__name__}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

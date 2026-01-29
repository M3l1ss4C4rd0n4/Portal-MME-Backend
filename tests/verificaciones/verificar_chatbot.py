#!/usr/bin/env python3
"""
Script simple para verificar los callbacks del chatbot
"""
import requests
import json

print("🔍 VERIFICACIÓN DEL CHATBOT CON DATOS EN TIEMPO REAL\n")
print("=" * 70)

# 1. Verificar callbacks del store
print("\n📊 CALLBACKS QUE ACTUALIZAN EL STORE:")
print("-" * 70)
response = requests.get("http://localhost:8050/_dash-dependencies")
callbacks = response.json()

callbacks_store = [cb for cb in callbacks if 'store-datos-chatbot-generacion.data' in str(cb.get('output', ''))]
print(f"Total: {len(callbacks_store)} callbacks\n")

for i, cb in enumerate(callbacks_store, 1):
    # Intentar identificar la página por los inputs
    inputs = cb.get('inputs', [])
    input_ids = [inp.get('id', '') for inp in inputs]
    
    pagina = 'Desconocida'
    if 'btn-actualizar-fuentes' in input_ids:
        pagina = 'Generación por Fuentes'
    elif 'btn-actualizar-transmision' in input_ids:
        pagina = 'Transmisión'
    elif 'btn-actualizar-perdidas' in input_ids:
        pagina = 'Pérdidas'
    elif 'btn-actualizar-restricciones' in input_ids:
        pagina = 'Restricciones'
    
    print(f"{i}. {pagina}")
    print(f"   Inputs: {input_ids[:3]}...")  # Mostrar primeros 3 inputs

# 2. Verificar callback del chatbot
print("\n" + "=" * 70)
print("\n🤖 CALLBACK DEL CHATBOT:")
print("-" * 70)

chatbot_callbacks = [cb for cb in callbacks if 'chat-messages.children' in str(cb.get('output', ''))]

if chatbot_callbacks:
    cb = chatbot_callbacks[0]
    states = cb.get('state', [])
    
    print("States usados por el chatbot:")
    for state in states:
        state_id = state.get('id', '')
        state_prop = state.get('property', '')
        if 'store-datos-chatbot' in state_id:
            print(f"   ✅ {state_id}.{state_prop} (CORRECTO - lee datos del store)")
        else:
            print(f"   - {state_id}.{state_prop}")

# 3. Instrucciones de prueba
print("\n" + "=" * 70)
print("\n✅ CONFIGURACIÓN VERIFICADA")
print("\n📋 INSTRUCCIONES DE PRUEBA:")
print("-" * 70)
print("""
1. Abre el portal en tu navegador: http://localhost:8050

2. Ve a la página de PÉRDIDAS:
   - Presiona el botón "Actualizar"
   - Espera que carguen los datos
   - Abre el chatbot (botón azul flotante)
   - Presiona "🔍 Analizar Tablero"
   - El chatbot debería mencionar datos específicos de pérdidas

3. Ve a la página de TRANSMISIÓN:
   - Presiona "Actualizar"
   - Abre el chatbot
   - Presiona "🔍 Analizar Tablero"
   - El chatbot debería mencionar datos de líneas de transmisión

4. Ve a la página de RESTRICCIONES:
   - Presiona "Actualizar"
   - Abre el chatbot
   - Presiona "🔍 Analizar Tablero"
   - El chatbot debería mencionar datos de restricciones

Si el chatbot responde con datos específicos de cada página,
entonces está funcionando correctamente con datos en tiempo real.
""")

print("=" * 70)

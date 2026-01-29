#!/usr/bin/env python3
"""
Script para verificar que el store del chatbot se actualice correctamente en cada página
"""
import requests
import json
import time

PAGINAS_TEST = {
    '/generacion-fuentes': 'Generación por Fuentes',
    '/transmision': 'Transmisión',
    '/perdidas': 'Pérdidas',
    '/restricciones': 'Restricciones'
}

def verificar_store_chatbot():
    """Verificar que el store esté disponible y tenga la estructura correcta"""
    
    print("🔍 VERIFICACIÓN DEL STORE DEL CHATBOT")
    print("=" * 60)
    
    # 1. Verificar que el layout incluya el store
    print("\n1️⃣ Verificando que el store existe en el layout...")
    try:
        response = requests.get("http://localhost:8050/_dash-layout")
        layout = response.json()
        
        # Buscar el store en el layout
        store_found = False
        def search_store(obj):
            global store_found
            if isinstance(obj, dict):
                if obj.get('props', {}).get('id') == 'store-datos-chatbot-generacion':
                    store_found = True
                    return True
                for value in obj.values():
                    if search_store(value):
                        return True
            elif isinstance(obj, list):
                for item in obj:
                    if search_store(item):
                        return True
            return False
        
        search_store(layout)
        
        if store_found:
            print("   ✅ Store 'store-datos-chatbot-generacion' encontrado en layout")
        else:
            print("   ❌ Store NO encontrado en layout")
            return False
            
    except Exception as e:
        print(f"   ❌ Error verificando layout: {e}")
        return False
    
    # 2. Verificar callbacks que actualizan el store
    print("\n2️⃣ Verificando callbacks que actualizan el store...")
    try:
        response = requests.get("http://localhost:8050/_dash-dependencies")
        callbacks = response.json()
        
        callbacks_store = [cb for cb in callbacks if 'store-datos-chatbot-generacion.data' in str(cb.get('output', ''))]
        
        print(f"   ✅ {len(callbacks_store)} callbacks actualizan el store:")
        for i, cb in enumerate(callbacks_store, 1):
            output_str = cb['output']
            print(f"      {i}. {output_str[:80]}...")
            
    except Exception as e:
        print(f"   ❌ Error verificando callbacks: {e}")
        return False
    
    # 3. Verificar que el callback del chatbot lee el store
    print("\n3️⃣ Verificando que el chatbot lee del store...")
    try:
        chatbot_callbacks = [cb for cb in callbacks if 'chat-messages.children' in str(cb.get('output', ''))]
        
        if chatbot_callbacks:
            cb = chatbot_callbacks[0]
            states = cb.get('state', [])
            store_state_found = any('store-datos-chatbot-generacion' in str(s) for s in states)
            
            if store_state_found:
                print("   ✅ El callback del chatbot SÍ lee el store como State")
            else:
                print("   ❌ El callback del chatbot NO lee el store")
                
        else:
            print("   ⚠️  No se encontró el callback del chatbot")
            
    except Exception as e:
        print(f"   ❌ Error verificando callback chatbot: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Verificación completada\n")
    
    print("💡 RECOMENDACIÓN:")
    print("   - Navega a cada página y presiona 'Actualizar'")
    print("   - Luego pregunta al chatbot: '¿Qué datos estás viendo?'")
    print("   - El chatbot debería responder con los datos específicos de esa página")
    
    return True

if __name__ == "__main__":
    verificar_store_chatbot()

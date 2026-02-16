#!/usr/bin/env python3
"""
Ejemplo de uso del endpoint de Informe Ejecutivo

Este script muestra cómo consumir el endpoint de informes ejecutivos
desde Python usando requests.

Autor: Portal Energético MME
Fecha: 9 de febrero de 2026
"""

import requests
import json
from datetime import date, timedelta
from pprint import pprint

# Configuración
API_URL = "http://localhost:8000/api/v1/chatbot/orchestrator"
API_KEY = "tu_api_key_aquí"  # Reemplazar con tu API Key real

def generar_informe_ejecutivo_basico():
    """
    Ejemplo 1: Informe ejecutivo básico con las secciones principales
    """
    print("\n" + "="*80)
    print("📊 EJEMPLO 1: Informe Ejecutivo Básico")
    print("="*80 + "\n")
    
    # Calcular fechas (último mes)
    fecha_fin = (date.today() - timedelta(days=1)).isoformat()
    fecha_inicio = (date.today() - timedelta(days=30)).isoformat()
    
    payload = {
        "sessionId": "ejemplo_basico_001",
        "intent": "informe_ejecutivo",
        "parameters": {
            "sections": [
                "1_generacion_sistema",      # Generación total con estadísticas
                "2.1_generacion_actual",     # Mix energético
                "3.1_aportes_embalses",      # Hidrología
                "8_restricciones"            # Restricciones operativas
            ],
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    print(f"📤 Enviando request al endpoint...")
    print(f"   URL: {API_URL}")
    print(f"   Periodo: {fecha_inicio} a {fecha_fin}")
    print(f"   Secciones: {len(payload['parameters']['sections'])}")
    
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        
        print(f"\n✅ Respuesta recibida:")
        print(f"   Status: {data.get('status')}")
        print(f"   Message: {data.get('message')}")
        
        if data.get('status') in ['SUCCESS', 'PARTIAL_SUCCESS']:
            informe = data.get('data', {})
            
            print(f"\n{'='*80}")
            print("📋 RESUMEN DEL INFORME")
            print(f"{'='*80}")
            
            metadata = informe.get('metadata', {})
            print(f"\nFecha de generación: {metadata.get('fecha_generacion')}")
            print(f"Periodo analizado: {metadata.get('periodo_analisis')}")
            print(f"Secciones incluidas: {len(metadata.get('secciones_incluidas', []))}")
            
            # Mostrar conclusiones principales
            print(f"\n💡 CONCLUSIONES PRINCIPALES:")
            for i, conclusion in enumerate(informe.get('conclusiones_generales', []), 1):
                print(f"   {i}. {conclusion}")
            
            # Mostrar recomendaciones
            print(f"\n⚡ RECOMENDACIONES TÉCNICAS:")
            for i, recom in enumerate(informe.get('recomendaciones_tecnicas', []), 1):
                print(f"   {i}. {recom}")
            
            # Mostrar resumen ejecutivo
            print(f"\n{informe.get('resumen_ejecutivo', '')}")
            
        else:
            print(f"\n❌ Error en la generación del informe")
            for error in data.get('errors', []):
                print(f"   • {error.get('code')}: {error.get('message')}")
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error en la conexión: {e}")


def generar_informe_comparacion_anual():
    """
    Ejemplo 2: Informe de comparación anual
    """
    print("\n\n" + "="*80)
    print("📊 EJEMPLO 2: Comparación Anual 2024 vs 2025")
    print("="*80 + "\n")
    
    payload = {
        "sessionId": "ejemplo_comparacion_001",
        "intent": "informe_ejecutivo",
        "parameters": {
            "sections": [
                "2.2_comparacion_anual",     # Comparación de generación
                "3.2_comparacion_anual_hidro" # Comparación de hidrología
            ],
            "ano_comparacion_1": 2024,
            "ano_comparacion_2": 2025
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    print(f"📤 Enviando request al endpoint...")
    print(f"   Comparando: 2024 vs 2025")
    
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        
        print(f"\n✅ Respuesta recibida:")
        print(f"   Status: {data.get('status')}")
        
        if data.get('status') in ['SUCCESS', 'PARTIAL_SUCCESS']:
            informe = data.get('data', {})
            secciones = informe.get('secciones', {})
            
            # Mostrar comparación de generación
            if '2.2_comparacion_anual' in secciones:
                seccion = secciones['2.2_comparacion_anual']
                
                if 'comparacion' in seccion:
                    comp = seccion['comparacion']
                    
                    print(f"\n{'='*80}")
                    print("⚡ COMPARACIÓN DE GENERACIÓN")
                    print(f"{'='*80}")
                    
                    print(f"\n📊 Año {comp['ano_1']['ano']}:")
                    print(f"   Total: {comp['ano_1']['total_gwh']:,.2f} GWh")
                    print(f"   Promedio diario: {comp['ano_1']['promedio_diario']:.2f} GWh")
                    
                    print(f"\n📊 Año {comp['ano_2']['ano']}:")
                    print(f"   Total: {comp['ano_2']['total_gwh']:,.2f} GWh")
                    print(f"   Promedio diario: {comp['ano_2']['promedio_diario']:.2f} GWh")
                    
                    print(f"\n📈 Diferencias:")
                    dif = comp['diferencias']
                    print(f"   Total: {dif['total_gwh']:+,.2f} GWh ({dif['total_pct']:+.2f}%)")
                    print(f"   Promedio diario: {dif['promedio_diario_gwh']:+.2f} GWh ({dif['promedio_diario_pct']:+.2f}%)")
                    
                    if 'test_estadistico' in comp:
                        test = comp['test_estadistico']
                        print(f"\n🔬 Test Estadístico:")
                        print(f"   {test['interpretacion']}")
                        print(f"   p-valor: {test['p_valor']:.6f}")
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error en la conexión: {e}")


def generar_informe_completo():
    """
    Ejemplo 3: Informe completo con todas las secciones
    """
    print("\n\n" + "="*80)
    print("📊 EJEMPLO 3: Informe Completo (Todas las Secciones)")
    print("="*80 + "\n")
    
    fecha_fin = (date.today() - timedelta(days=1)).isoformat()
    fecha_inicio = (date.today() - timedelta(days=7)).isoformat()
    
    payload = {
        "sessionId": "ejemplo_completo_001",
        "intent": "informe_ejecutivo",
        "parameters": {
            "sections": [
                "1_generacion_sistema",
                "2.1_generacion_actual",
                "2.2_comparacion_anual",
                "3.1_aportes_embalses",
                "3.2_comparacion_anual_hidro",
                "4_transmision",
                "5_distribucion",
                "6_comercializacion",
                "7_perdidas",
                "8_restricciones"
            ],
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "ano_comparacion_1": 2024,
            "ano_comparacion_2": 2025,
            "dias_prediccion": 7
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    print(f"📤 Enviando request al endpoint...")
    print(f"   Secciones: {len(payload['parameters']['sections'])}")
    print(f"   Periodo: {fecha_inicio} a {fecha_fin}")
    
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=90)
        response.raise_for_status()
        
        data = response.json()
        
        print(f"\n✅ Respuesta recibida:")
        print(f"   Status: {data.get('status')}")
        
        if data.get('status') in ['SUCCESS', 'PARTIAL_SUCCESS']:
            informe = data.get('data', {})
            secciones = informe.get('secciones', {})
            
            print(f"\n{'='*80}")
            print(f"📋 SECCIONES PROCESADAS: {len(secciones)}")
            print(f"{'='*80}")
            
            for sec_nombre, sec_data in secciones.items():
                if isinstance(sec_data, dict):
                    if 'error' in sec_data:
                        print(f"\n❌ {sec_nombre}: Error - {sec_data['error']}")
                    else:
                        print(f"\n✅ {sec_nombre}: {sec_data.get('titulo', sec_nombre)}")
            
            print(f"\n{'='*80}")
            print("📊 RESUMEN GENERAL")
            print(f"{'='*80}")
            print(f"Conclusiones totales: {len(informe.get('conclusiones_generales', []))}")
            print(f"Recomendaciones totales: {len(informe.get('recomendaciones_tecnicas', []))}")
            
            # Guardar a archivo
            with open('informe_ejecutivo_completo.json', 'w', encoding='utf-8') as f:
                json.dump(informe, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Informe completo guardado en: informe_ejecutivo_completo.json")
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error en la conexión: {e}")


def main():
    """Ejecutar todos los ejemplos"""
    print("\n" + "="*80)
    print("🚀 EJEMPLOS DE USO - INFORME EJECUTIVO")
    print("Portal Energético MME")
    print("="*80)
    
    # Verificar configuración
    if API_KEY == "tu_api_key_aquí":
        print("\n⚠️ ADVERTENCIA: Necesitas configurar tu API_KEY en el script")
        print("   Edita la variable API_KEY en línea 15")
        return
    
    try:
        # Ejemplo 1: Informe básico
        generar_informe_ejecutivo_basico()
        
        # Ejemplo 2: Comparación anual
        generar_informe_comparacion_anual()
        
        # Ejemplo 3: Informe completo
        generar_informe_completo()
        
        print("\n\n" + "="*80)
        print("✅ TODOS LOS EJEMPLOS COMPLETADOS")
        print("="*80)
        print("\n💡 Tip: Revisa el archivo 'informe_ejecutivo_completo.json' para ver")
        print("   el informe completo en formato JSON")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Ejecución interrumpida por el usuario")
    except Exception as e:
        print(f"\n\n❌ Error inesperado: {e}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Test End-to-End del Sistema de Alertas
Simula una alerta crítica y verifica el flujo completo:
1. Detección de condición crítica
2. Guardado en BD
3. Envío de notificaciones (Email + WhatsApp)
4. Actualización de estado en BD
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.alertas_energeticas import notificar_alerta
from infrastructure.database.connection import PostgreSQLConnectionManager
import psycopg2
import json

def crear_alerta_test():
    """Crea una alerta de prueba en la BD"""
    print("\n" + "="*70)
    print("🧪 TEST END-TO-END - SISTEMA DE ALERTAS ENERGÉTICAS")
    print("="*70)
    
    # Conectar a BD
    manager = PostgreSQLConnectionManager()
    conn_params = {
        'host': manager.host,
        'port': manager.port,
        'database': manager.database,
        'user': manager.user
    }
    if manager.password:
        conn_params['password'] = manager.password
    
    conn = psycopg2.connect(**conn_params)
    cursor = conn.cursor()
    
    # 0. Limpiar alertas de test previas
    print("\n🧹 PASO 0: Limpiando alertas de test anteriores...")
    cursor.execute("DELETE FROM alertas_historial WHERE titulo LIKE 'TEST:%'")
    conn.commit()
    print("   ✅ Alertas de test anteriores eliminadas")
    
    # 1. Crear alerta de prueba en BD
    print("\n📝 PASO 1: Guardando alerta de prueba en BD...")
    
    alerta_test = {
        'categoria': 'DEMANDA',
        'severidad': 'CRÍTICO',
        'titulo': 'TEST: Demanda eléctrica excede capacidad',
        'descripcion': 'Proyección: 275.5 GWh/día. Umbral crítico: 250 GWh/día.',
        'valor': 275.5,
        'umbral': 250.0,
        'recomendacion': 'URGENTE: Activar generación térmica de respaldo. Contactar operadores.',
        'dias_afectados': 7
    }
    
    query = """
        INSERT INTO alertas_historial 
        (fecha_evaluacion, metrica, severidad, valor_promedio, 
         titulo, descripcion, recomendacion, dias_afectados,
         json_completo, notificacion_email_enviada, notificacion_whatsapp_enviada)
        VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, false, false)
        RETURNING id
    """
    
    cursor.execute(query, (
        alerta_test['categoria'],
        alerta_test['severidad'],
        alerta_test['valor'],
        alerta_test['titulo'],
        alerta_test['descripcion'],
        alerta_test['recomendacion'],
        alerta_test['dias_afectados'],
        json.dumps(alerta_test, ensure_ascii=False)
    ))
    
    alerta_id = cursor.fetchone()[0]
    conn.commit()
    
    print(f"   ✅ Alerta guardada con ID: {alerta_id}")
    print(f"   📊 Métrica: {alerta_test['categoria']}")
    print(f"   🚨 Severidad: {alerta_test['severidad']}")
    print(f"   💡 Título: {alerta_test['titulo']}")
    
    # 2. Enviar notificaciones
    print("\n📧 PASO 2: Enviando notificaciones...")
    print("   📱 Canales: EMAIL + WhatsApp")
    
    try:
        # Preparar alerta en formato esperado por notificar_alerta()
        alerta_para_notificacion = {
            'severidad': alerta_test['severidad'],
            'metrica': alerta_test['categoria'],
            'titulo': alerta_test['titulo'],
            'descripcion': alerta_test['descripcion'],
            'valor': alerta_test['valor'],
            'umbral': alerta_test['umbral'],
            'recomendacion': alerta_test['recomendacion'],
            'dias_afectados': alerta_test['dias_afectados'],
            'valor_promedio': alerta_test['valor']
        }
        
        resultado = notificar_alerta(
            alerta=alerta_para_notificacion,
            enviar_email=True,
            enviar_whatsapp=True,
            solo_criticas=False  # Enviar aunque sea test
        )
        
        print(f"\n   📊 Resultado de notificaciones:")
        email_ok = resultado.get('email', {}).get('success', False)
        whatsapp_ok = resultado.get('whatsapp', {}).get('success', False)
        
        print(f"      Email: {'✅ SÍ' if email_ok else '❌ NO'}")
        if not email_ok:
            print(f"         Razón: {resultado.get('email', {}).get('message', 'Desconocida')}")
        
        print(f"      WhatsApp: {'✅ SÍ' if whatsapp_ok else '❌ NO'}")
        if not whatsapp_ok:
            print(f"         Razón: {resultado.get('whatsapp', {}).get('message', 'Desconocida')}")
        
        # 3. Actualizar estado en BD
        print("\n💾 PASO 3: Actualizando estado de notificaciones en BD...")
        
        query_update = """
            UPDATE alertas_historial 
            SET notificacion_email_enviada = %s,
                notificacion_whatsapp_enviada = %s,
                fecha_notificacion = NOW()
            WHERE id = %s
        """
        
        cursor.execute(query_update, (
            email_ok,
            whatsapp_ok,
            alerta_id
        ))
        conn.commit()
        
        print("   ✅ Estado actualizado en BD")
        
        # 4. Verificar en BD
        print("\n🔍 PASO 4: Verificando registro en BD...")
        
        cursor.execute("""
            SELECT id, metrica, severidad, titulo, 
                   notificacion_email_enviada, notificacion_whatsapp_enviada,
                   fecha_notificacion
            FROM alertas_historial 
            WHERE id = %s
        """, (alerta_id,))
        
        registro = cursor.fetchone()
        
        if registro:
            print(f"   ✅ Registro encontrado:")
            print(f"      ID: {registro[0]}")
            print(f"      Métrica: {registro[1]}")
            print(f"      Severidad: {registro[2]}")
            print(f"      Título: {registro[3]}")
            print(f"      Email enviado: {'✅' if registro[4] else '❌'}")
            print(f"      WhatsApp enviado: {'✅' if registro[5] else '❌'}")
            print(f"      Fecha notificación: {registro[6]}")
        
        # Resumen final
        print("\n" + "="*70)
        print("📊 RESUMEN DEL TEST")
        print("="*70)
        print(f"🆔 ID Alerta: {alerta_id}")
        print(f"💾 Guardado en BD: ✅")
        print(f"📧 Notificación EMAIL: {'✅' if email_ok else '❌'}")
        print(f"📱 Notificación WhatsApp: {'✅' if whatsapp_ok else '❌'}")
        print(f"🔄 Estado actualizado: ✅")
        
        exito_total = email_ok or whatsapp_ok
        
        if exito_total:
            print("\n✅ TEST EXITOSO - El sistema de alertas funciona correctamente")
        else:
            print("\n⚠️  TEST PARCIAL - Alertas guardadas pero notificaciones fallaron")
            print("   Revisar configuración de SMTP_PASSWORD y WHATSAPP_BOT_URL")
        
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ ERROR en notificaciones: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    crear_alerta_test()

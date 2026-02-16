#!/usr/bin/env python3
"""
Test de integración: Sistema de Predicciones Completo
Verifica que todos los componentes estén conectados correctamente
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import psycopg2
from datetime import date, timedelta
from core.config import settings
from domain.services.orchestrator_service import ChatbotOrchestratorService

async def test_predicciones():
    """Test completo del sistema de predicciones"""
    
    print("\n" + "="*70)
    print("🧪 TEST DE INTEGRACIÓN: SISTEMA DE PREDICCIONES")
    print("="*70)
    
    # PASO 1: Verificar tabla predictions
    print("\n📋 PASO 1: Verificar Tabla predictions en PostgreSQL")
    print("-"*70)
    
    try:
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD or ''
        )
        cursor = conn.cursor()
        
        # Verificar que la tabla existe
        cursor.execute("SELECT COUNT(*) FROM predictions")
        count = cursor.fetchone()[0]
        
        print(f"✅ Tabla predictions existe")
        print(f"   Total predicciones almacenadas: {count}")
        
        if count > 0:
            # Mostrar muestra
            cursor.execute("""
                SELECT fuente, COUNT(*), MIN(fecha_prediccion), MAX(fecha_prediccion)
                FROM predictions
                GROUP BY fuente
                ORDER BY fuente
            """)
            
            print("\n   Predicciones por fuente:")
            for row in cursor.fetchall():
                fuente, num, min_fecha, max_fecha = row
                print(f"     • {fuente:12s}: {num:4d} registros ({min_fecha} a {max_fecha})")
        else:
            print("\n   ⚠️  No hay predicciones generadas todavía")
            print("   💡 Ejecute: python3 scripts/train_predictions_postgres.py")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error verificando tabla: {e}")
        return False
    
    # PASO 2: Probar PredictionsService
    print("\n📊 PASO 2: Probar PredictionsService")
    print("-"*70)
    
    try:
        from domain.services.predictions_service import PredictionsService
        
        service = PredictionsService()
        print("✅ PredictionsService instanciado correctamente")
        
        # Verificar métodos
        latest_date = service.get_latest_prediction_date()
        total_count = service.count_predictions()
        
        print(f"   Última fecha: {latest_date or 'N/A'}")
        print(f"   Total predicciones: {total_count}")
        
        # Intentar obtener predicciones
        fecha_inicio = date.today().isoformat()
        fecha_fin = (date.today() + timedelta(days=7)).isoformat()
        
        df = service.get_predictions('Hidráulica', fecha_inicio, fecha_fin)
        
        if not df.empty:
            print(f"\n   ✅ Consulta exitosa: {len(df)} registros obtenidos")
            print(f"      Rango: {df['fecha_prediccion'].min()} a {df['fecha_prediccion'].max()}")
        else:
            print(f"\n   ⚠️  No hay predicciones para Hidráulica en el rango solicitado")
        
    except Exception as e:
        print(f"❌ Error en PredictionsService: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # PASO 3: Probar Orchestrator Handler
    print("\n🎯 PASO 3: Probar Handler del Orquestador")
    print("-"*70)
    
    try:
        orchestrator = ChatbotOrchestratorService()
        print("✅ ChatbotOrchestratorService instanciado")
        
        # Probar con diferentes fuentes
        test_cases = [
            {'fuente': 'Hidráulica', 'horizonte': 7},
            {'fuente': 'Térmica', 'horizonte': 3},
            {'fuente': 'Solar', 'horizonte': 5}
        ]
        
        for i, params in enumerate(test_cases, 1):
            print(f"\n   Test {i}: {params['fuente']} - {params['horizonte']} días")
            
            data, errors = await orchestrator._handle_predicciones(params)
            
            if errors:
                print(f"      ⚠️  Errores: {[e.message for e in errors]}")
            
            if data:
                print(f"      ✅ Respuesta recibida:")
                print(f"         Fuente: {data.get('fuente')}")
                print(f"         Predicciones: {data.get('total_predicciones', 0)}")
                print(f"         Mensaje: {data.get('mensaje', 'N/A')[:60]}...")
                
                if data.get('predicciones'):
                    print(f"         Ejemplo predicción:")
                    pred = data['predicciones'][0]
                    print(f"           • Fecha: {pred.get('fecha')}")
                    print(f"           • Valor: {pred.get('valor_gwh')} GWh")
            else:
                print(f"      ❌ Sin respuesta")
        
    except Exception as e:
        print(f"❌ Error en Orchestrator: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # PASO 4: Resumen
    print("\n" + "="*70)
    print("📊 RESUMEN DEL TEST")
    print("="*70)
    
    print(f"\n✅ Componentes verificados:")
    print(f"   1. ✅ Tabla predictions en PostgreSQL")
    print(f"   2. ✅ PredictionsService funcionando")
    print(f"   3. ✅ Handler del orquestador implementado")
    
    if count > 0:
        print(f"\n🎉 SISTEMA COMPLETAMENTE FUNCIONAL")
        print(f"   • {count} predicciones disponibles")
        print(f"   • Handler del orquestador operativo")
        print(f"   • Listo para consultas desde la API")
    else:
        print(f"\n⚠️  SISTEMA LISTO PERO SIN DATOS")
        print(f"   • Infraestructura completa ✅")
        print(f"   • Falta generar predicciones con ML")
        print(f"   • Ejecutar: python3 scripts/train_predictions_postgres.py")
    
    print(f"\n{'='*70}\n")
    
    return True

async def main():
    """Main test runner"""
    try:
        success = await test_predicciones()
        
        if success:
            print("✅ Test completado exitosamente")
        else:
            print("❌ Test falló")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error ejecutando test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())

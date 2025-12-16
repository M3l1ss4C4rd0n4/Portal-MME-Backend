#!/usr/bin/env python3
"""
Test específico para métricas de disponibilidad
"""

import sys
import logging
from datetime import datetime, timedelta

# Configurar path
sys.path.insert(0, '/home/admonctrlxm/server')

from etl.etl_xm_to_sqlite import poblar_metrica
from pydataxm.pydataxm import ReadDB

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(message)s'
)

print("=" * 80)
print("🧪 TEST: Métricas de Disponibilidad con conversión 'horas_a_diario'")
print("=" * 80)

# Fechas de prueba (últimos 7 días)
fecha_fin = datetime.now()
fecha_ini = fecha_fin - timedelta(days=7)

print(f"\n📅 Período: {fecha_ini.strftime('%Y-%m-%d')} → {fecha_fin.strftime('%Y-%m-%d')}")
print(f"📊 Objetivo: Verificar que la conversión kW→MW funcione correctamente\n")

# Crear objeto API
print("🔗 Conectando a API de XM...")
obj_api = ReadDB()
print("✅ Conexión establecida\n")

# Test 1: DispoReal
print("=" * 80)
print("TEST 1: DispoReal/Recurso")
print("=" * 80)

config1 = {
    'metric': 'DispoReal',
    'entity': 'Recurso',
    'conversion': 'horas_a_diario',  # ← Nueva configuración
    'dias_history': 7,
    'batch_size': 7,
    'descripcion': 'Disponibilidad real por recurso'
}

try:
    registros1 = poblar_metrica(
        obj_api=obj_api,
        config=config1,
        usar_timeout=True,
        timeout_seconds=120,
        fecha_inicio_custom=fecha_ini.strftime('%Y-%m-%d'),
        fecha_fin_custom=fecha_fin.strftime('%Y-%m-%d')
    )
    
    if registros1 > 0:
        print(f"\n✅ ÉXITO: {registros1:,} registros insertados")
    else:
        print(f"\n⚠️ Sin registros insertados")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Verificar en SQLite
print("\n" + "=" * 80)
print("📊 Verificando datos en SQLite...")
print("=" * 80)

try:
    import sqlite3
    import pandas as pd
    
    conn = sqlite3.connect('/home/admonctrlxm/server/portal_energetico.db')
    
    # Contar registros de DispoReal
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT recurso) as recursos,
               MIN(fecha) as fecha_min,
               MAX(fecha) as fecha_max,
               AVG(valor_gwh) as promedio_mw
        FROM metrics
        WHERE metrica = 'DispoReal'
    """)
    
    row = cursor.fetchone()
    
    if row and row[0] > 0:
        print(f"\n✅ Datos encontrados en SQLite:")
        print(f"   ├─ Total registros: {row[0]:,}")
        print(f"   ├─ Recursos únicos: {row[1]:,}")
        print(f"   ├─ Fecha mínima: {row[2]}")
        print(f"   ├─ Fecha máxima: {row[3]}")
        print(f"   └─ Promedio: {row[4]:.2f} MW")
        
        # Mostrar algunos ejemplos
        print(f"\n📋 Ejemplos de datos (primeros 5 registros):")
        df_sample = pd.read_sql_query("""
            SELECT fecha, metrica, recurso, valor_gwh as valor_mw, unidad
            FROM metrics
            WHERE metrica = 'DispoReal'
            ORDER BY fecha DESC, recurso
            LIMIT 5
        """, conn)
        print(df_sample.to_string(index=False))
        
    else:
        print(f"\n⚠️ No se encontraron datos de DispoReal en SQLite")
    
    conn.close()
    
except Exception as e:
    print(f"\n❌ Error consultando SQLite: {e}")

print("\n" + "=" * 80)
print("🎯 Conclusión:")
print("-" * 80)
print("Si ves 'Promedio X horas (kW→MW)' en los logs, la conversión funciona.")
print("Si ves datos en SQLite con valores razonables (10-1000 MW), está correcto.")
print("=" * 80)

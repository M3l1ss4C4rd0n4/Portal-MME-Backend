#!/usr/bin/env python3
"""
Análisis Detallado de Métricas con Valores Sospechosos
Portal Energético MME
Diciembre 17, 2025
"""

import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = '/home/admonctrlxm/server/portal_energetico.db'

def analizar_metricas_sospechosas():
    """Analiza en detalle las 16 métricas con valores > 1M"""
    
    conn = sqlite3.connect(DB_PATH)
    
    print("=" * 80)
    print("🔍 ANÁLISIS DETALLADO DE MÉTRICAS SOSPECHOSAS")
    print("=" * 80)
    print()
    
    # Lista de métricas problemáticas
    metricas_problema = [
        'VolTurbMasa',
        'VoluUtilDiarMasa',
        'CapaUtilDiarMasa',
        'VertMasa',
        'ENFICC',
        'ComContRespEner',
        'CargoUsoSTN',
        'CargoUsoSTR',
        'FAER',
        'PRONE',
        'EscDemUPMEAlto',
        'EscDemUPMEMedio',
        'EscDemUPMEBajo',
        'FAZNI',
        'RemuRealIndiv',
        'DescMasa'
    ]
    
    resultados = []
    
    for metrica in metricas_problema:
        query = f"""
        SELECT 
            metrica,
            entidad,
            unidad,
            COUNT(*) as total_registros,
            COUNT(CASE WHEN valor_gwh > 1000000 THEN 1 END) as registros_gt_1m,
            ROUND(MIN(valor_gwh), 2) as minimo,
            ROUND(MAX(valor_gwh), 2) as maximo,
            ROUND(AVG(valor_gwh), 2) as promedio,
            ROUND(AVG(CASE WHEN valor_gwh > 1000000 THEN valor_gwh END), 2) as promedio_gt_1m,
            MIN(fecha) as fecha_inicio,
            MAX(fecha) as fecha_fin
        FROM metrics
        WHERE metrica = '{metrica}'
        GROUP BY metrica, entidad, unidad
        """
        
        df = pd.read_sql_query(query, conn)
        if not df.empty:
            resultados.append(df)
    
    if resultados:
        df_final = pd.concat(resultados, ignore_index=True)
        
        print("\n📊 TABLA DE MÉTRICAS SOSPECHOSAS:\n")
        print(df_final.to_string(index=False))
        print()
        
        # Clasificación por tipo
        print("\n" + "=" * 80)
        print("🏷️  CLASIFICACIÓN POR TIPO DE MÉTRICA")
        print("=" * 80)
        
        hidrologia = ['VolTurbMasa', 'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'VertMasa']
        energia = ['ENFICC', 'ComContRespEner']
        financiero = ['CargoUsoSTN', 'CargoUsoSTR', 'FAER', 'PRONE', 'FAZNI', 'RemuRealIndiv', 'DescMasa']
        proyecciones = ['EscDemUPMEAlto', 'EscDemUPMEMedio', 'EscDemUPMEBajo']
        
        print("\n🌊 HIDROLOGÍA (Volúmenes en m³):")
        print("-" * 80)
        for m in hidrologia:
            info = df_final[df_final['metrica'] == m]
            if not info.empty:
                row = info.iloc[0]
                print(f"  • {m:25} | Max: {row['maximo']:>15,.0f} m³ → {row['maximo']/1e6:>10,.2f} Hm³")
        
        print("\n⚡ ENERGÍA (Probablemente en kWh):")
        print("-" * 80)
        for m in energia:
            info = df_final[df_final['metrica'] == m]
            if not info.empty:
                row = info.iloc[0]
                print(f"  • {m:25} | Max: {row['maximo']:>15,.0f} kWh → {row['maximo']/1e6:>10,.2f} GWh")
        
        print("\n💰 FINANCIERO (Valores en COP):")
        print("-" * 80)
        for m in financiero:
            info = df_final[df_final['metrica'] == m]
            if not info.empty:
                row = info.iloc[0]
                millones = row['maximo'] / 1e6
                print(f"  • {m:25} | Max: ${row['maximo']:>15,.0f} → ${millones:>12,.2f} MM")
        
        print("\n📈 PROYECCIONES UPME (Probablemente en kWh):")
        print("-" * 80)
        for m in proyecciones:
            info = df_final[df_final['metrica'] == m]
            if not info.empty:
                row = info.iloc[0]
                print(f"  • {m:25} | Max: {row['maximo']:>15,.0f} kWh → {row['maximo']/1e6:>10,.2f} GWh")
    
    # Verificar ejemplos específicos
    print("\n" + "=" * 80)
    print("📋 EJEMPLOS DE REGISTROS ESPECÍFICOS")
    print("=" * 80)
    
    print("\n🌊 Ejemplo: VolTurbMasa (Volumen Turbinado)")
    query_ejemplo = """
    SELECT fecha, metrica, entidad, recurso, 
           ROUND(valor_gwh, 2) as valor_original,
           unidad,
           ROUND(valor_gwh / 1000000.0, 2) as valor_corregido_hm3
    FROM metrics
    WHERE metrica = 'VolTurbMasa'
      AND valor_gwh > 1000000
    ORDER BY valor_gwh DESC
    LIMIT 5
    """
    df_ejemplo = pd.read_sql_query(query_ejemplo, conn)
    if not df_ejemplo.empty:
        print(df_ejemplo.to_string(index=False))
    
    print("\n💰 Ejemplo: CargoUsoSTN (Cargo Uso Sistema de Transmisión Nacional)")
    query_ejemplo = """
    SELECT fecha, metrica, entidad, 
           ROUND(valor_gwh, 2) as valor_original_cop,
           unidad,
           ROUND(valor_gwh / 1000000.0, 2) as valor_corregido_millones_cop
    FROM metrics
    WHERE metrica = 'CargoUsoSTN'
      AND valor_gwh > 1000000
    ORDER BY fecha DESC
    LIMIT 5
    """
    df_ejemplo = pd.read_sql_query(query_ejemplo, conn)
    if not df_ejemplo.empty:
        print(df_ejemplo.to_string(index=False))
    
    # Análisis de impacto
    print("\n" + "=" * 80)
    print("📊 ANÁLISIS DE IMPACTO DE LAS CORRECCIONES")
    print("=" * 80)
    
    query_impacto = """
    SELECT 
        CASE 
            WHEN metrica IN ('VolTurbMasa', 'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'VertMasa') 
                THEN 'Hidrología'
            WHEN metrica IN ('ENFICC', 'ComContRespEner') 
                THEN 'Energía'
            WHEN metrica IN ('CargoUsoSTN', 'CargoUsoSTR', 'FAER', 'PRONE', 'FAZNI', 'RemuRealIndiv', 'DescMasa') 
                THEN 'Financiero'
            WHEN metrica IN ('EscDemUPMEAlto', 'EscDemUPMEMedio', 'EscDemUPMEBajo') 
                THEN 'Proyecciones'
            ELSE 'Otros'
        END as categoria,
        COUNT(DISTINCT metrica) as num_metricas,
        COUNT(*) as total_registros,
        COUNT(CASE WHEN valor_gwh > 1000000 THEN 1 END) as registros_a_corregir,
        ROUND(100.0 * COUNT(CASE WHEN valor_gwh > 1000000 THEN 1 END) / COUNT(*), 2) as porcentaje_afectado
    FROM metrics
    WHERE metrica IN ({metricas_str})
    GROUP BY categoria
    ORDER BY registros_a_corregir DESC
    """.format(metricas_str=','.join(["'" + m + "'" for m in metricas_problema]))
    
    df_impacto = pd.read_sql_query(query_impacto, conn)
    if not df_impacto.empty:
        print("\nRegistros que serán corregidos por categoría:\n")
        print(df_impacto.to_string(index=False))
    
    # Guardar resultados
    print("\n" + "=" * 80)
    print("💾 GUARDANDO RESULTADOS")
    print("=" * 80)
    
    with open('/home/admonctrlxm/server/analisis_metricas_sospechosas.txt', 'w') as f:
        f.write("ANÁLISIS DETALLADO DE MÉTRICAS SOSPECHOSAS\n")
        f.write("=" * 80 + "\n\n")
        f.write(df_final.to_string(index=False))
        f.write("\n\n")
        f.write("IMPACTO DE CORRECCIONES:\n")
        f.write("-" * 80 + "\n")
        f.write(df_impacto.to_string(index=False))
    
    print("✅ Resultados guardados en: analisis_metricas_sospechosas.txt")
    
    conn.close()
    
    # Resumen ejecutivo
    print("\n" + "=" * 80)
    print("✅ RESUMEN EJECUTIVO")
    print("=" * 80)
    total_afectados = df_impacto['registros_a_corregir'].sum() if not df_impacto.empty else 0
    print(f"""
    • Total de métricas problemáticas: {len(metricas_problema)}
    • Total de registros a corregir: {total_afectados:,}
    • Categorías afectadas: {len(df_impacto)}
    
    RECOMENDACIÓN:
    ✅ Ejecutar script: scripts/corregir_conversiones_masa.sql
    ⚠️  Hacer BACKUP antes: sqlite3 portal_energetico.db ".backup backup_antes_correccion_masa.db"
    ✅ Verificar resultados después de la corrección
    """)

if __name__ == '__main__':
    analizar_metricas_sospechosas()

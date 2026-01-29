#!/usr/bin/env python3
"""Análisis completo de la base de datos portal_energetico.db"""

import sqlite3
import pandas as pd
import os
from datetime import datetime

db_path = 'portal_energetico.db'

print("\n" + "="*80)
print(" "*20 + "REVISIÓN BASE DE DATOS portal_energetico.db")
print("="*80 + "\n")

conn = sqlite3.connect(db_path)

# 1. LISTAR TABLAS Y CONTEO
print("📊 TABLAS EN LA BASE DE DATOS:")
print("-"*80)

tablas_query = """
    SELECT name FROM sqlite_master 
    WHERE type='table' AND name NOT LIKE 'sqlite_%'
    ORDER BY name
"""
tablas = pd.read_sql_query(tablas_query, conn)

total_registros = 0
for tabla in tablas['name']:
    count_query = f"SELECT COUNT(*) as total FROM {tabla}"
    count = pd.read_sql_query(count_query, conn)['total'][0]
    total_registros += count
    print(f"  • {tabla:35} {count:>15,} registros")

print(f"\n  {'TOTAL':35} {total_registros:>15,} registros")
print("-"*80)

# 2. FECHAS MÁS RECIENTES
print("\n📅 FECHAS MÁS RECIENTES DE DATOS:")
print("-"*80)

tablas_fecha = {
    'metrics_hourly': 'timestamp',
    'predictions': 'timestamp',
    'metrics': 'date'
}

for tabla, col in tablas_fecha.items():
    try:
        query = f"SELECT MAX({col}) as ultima_fecha FROM {tabla}"
        result = pd.read_sql_query(query, conn)
        fecha = result['ultima_fecha'][0]
        if fecha:
            # Calcular días de antigüedad
            try:
                fecha_dt = pd.to_datetime(fecha)
                dias_atras = (datetime.now() - fecha_dt).days
                print(f"  • {tabla:30} {fecha:25} ({dias_atras} días atrás)")
            except:
                print(f"  • {tabla:30} {fecha}")
        else:
            print(f"  • {tabla:30} Sin datos")
    except Exception as e:
        print(f"  • {tabla:30} ERROR: {str(e)[:30]}")

print("-"*80)

# 3. VERIFICAR DATOS NULOS
print("\n⚠️  DATOS NULOS EN COLUMNAS CRÍTICAS:")
print("-"*80)

try:
    nulos_query = """
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN timestamp IS NULL THEN 1 ELSE 0 END) as null_timestamp,
            SUM(CASE WHEN metric_name IS NULL THEN 1 ELSE 0 END) as null_metric,
            SUM(CASE WHEN value IS NULL THEN 1 ELSE 0 END) as null_value
        FROM metrics_hourly
    """
    nulos = pd.read_sql_query(nulos_query, conn)
    print(f"\n  metrics_hourly:")
    print(f"    Total registros:     {nulos['total'][0]:>15,}")
    print(f"    Nulos timestamp:     {nulos['null_timestamp'][0]:>15,}")
    print(f"    Nulos metric_name:   {nulos['null_metric'][0]:>15,}")
    print(f"    Nulos value:         {nulos['null_value'][0]:>15,}")
    
    if nulos['null_value'][0] > 0:
        print(f"\n    ⚠️  ADVERTENCIA: {nulos['null_value'][0]:,} valores nulos detectados")
except Exception as e:
    print(f"  metrics_hourly: ERROR - {e}")

print("-"*80)

# 4. MUESTRA DE DATOS RECIENTES
print("\n📌 MUESTRA DE DATOS MÁS RECIENTES (metrics_hourly):")
print("-"*80)

try:
    muestra_query = """
        SELECT timestamp, metric_name, value, unit
        FROM metrics_hourly
        ORDER BY timestamp DESC
        LIMIT 10
    """
    muestra = pd.read_sql_query(muestra_query, conn)
    if len(muestra) > 0:
        print(muestra.to_string(index=False))
    else:
        print("  No hay datos en metrics_hourly")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "-"*80)

# 5. MÉTRICAS DISPONIBLES
print("\n📋 MÉTRICAS DISPONIBLES:")
print("-"*80)

try:
    metricas_query = """
        SELECT metric_name, COUNT(*) as registros, 
               MIN(timestamp) as desde, MAX(timestamp) as hasta
        FROM metrics_hourly
        GROUP BY metric_name
        ORDER BY registros DESC
        LIMIT 15
    """
    metricas = pd.read_sql_query(metricas_query, conn)
    if len(metricas) > 0:
        print(f"\n  Total de métricas diferentes: {len(metricas)}")
        print("\n  Top 15 métricas por cantidad de registros:")
        for _, row in metricas.iterrows():
            print(f"    • {row['metric_name']:50} {row['registros']:>10,} registros")
    else:
        print("  No hay métricas registradas")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "-"*80)

# 6. VERIFICAR DUPLICADOS
print("\n🔄 VERIFICACIÓN DE DUPLICADOS:")
print("-"*80)

try:
    dup_query = """
        SELECT COUNT(*) as total_duplicados
        FROM (
            SELECT timestamp, metric_name, COUNT(*) as cnt
            FROM metrics_hourly
            GROUP BY timestamp, metric_name
            HAVING COUNT(*) > 1
        )
    """
    duplicados = pd.read_sql_query(dup_query, conn)
    num_dup = duplicados['total_duplicados'][0]
    
    if num_dup > 0:
        print(f"\n  ⚠️  Se encontraron {num_dup:,} combinaciones timestamp+metric con duplicados")
        
        # Mostrar ejemplos
        ejemplos_query = """
            SELECT timestamp, metric_name, COUNT(*) as duplicados
            FROM metrics_hourly
            GROUP BY timestamp, metric_name
            HAVING COUNT(*) > 1
            LIMIT 5
        """
        ejemplos = pd.read_sql_query(ejemplos_query, conn)
        print("\n  Ejemplos:")
        print(ejemplos.to_string(index=False))
    else:
        print("\n  ✅ No se encontraron duplicados")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "-"*80)

# 7. TAMAÑO DEL ARCHIVO
db_size_bytes = os.path.getsize(db_path)
db_size_gb = db_size_bytes / (1024**3)
db_size_mb = db_size_bytes / (1024**2)

print(f"\n💾 TAMAÑO DE LA BASE DE DATOS:")
print("-"*80)
print(f"  Archivo: {db_path}")
print(f"  Tamaño:  {db_size_gb:.2f} GB ({db_size_mb:,.0f} MB)")
print(f"  Registros totales: {total_registros:,}")
print(f"  Promedio por registro: {db_size_bytes/total_registros if total_registros > 0 else 0:.0f} bytes")

# 8. RESUMEN FINAL
print("\n" + "="*80)
print(" "*30 + "📊 RESUMEN EJECUTIVO")
print("="*80)

# Calcular estado
estado = "✅ COMPLETA"
advertencias = []

try:
    # Verificar última actualización
    ultima_fecha = pd.read_sql_query("SELECT MAX(timestamp) as f FROM metrics_hourly", conn)['f'][0]
    if ultima_fecha:
        fecha_dt = pd.to_datetime(ultima_fecha)
        dias = (datetime.now() - fecha_dt).days
        if dias > 7:
            advertencias.append(f"⚠️  Datos desactualizados ({dias} días)")
            estado = "⚠️  CON ADVERTENCIAS"
except:
    advertencias.append("⚠️  No se pudo verificar fecha de actualización")
    estado = "⚠️  CON ADVERTENCIAS"

try:
    # Verificar nulos
    nulos = pd.read_sql_query("SELECT SUM(CASE WHEN value IS NULL THEN 1 ELSE 0 END) as n FROM metrics_hourly", conn)['n'][0]
    if nulos > 0:
        advertencias.append(f"⚠️  {nulos:,} valores nulos en metrics_hourly")
        estado = "⚠️  CON ADVERTENCIAS"
except:
    pass

print(f"\n  Estado general: {estado}")
print(f"  Total de tablas: {len(tablas)}")
print(f"  Total de registros: {total_registros:,}")
print(f"  Tamaño: {db_size_gb:.2f} GB")

if advertencias:
    print("\n  Advertencias:")
    for adv in advertencias:
        print(f"    {adv}")
else:
    print("\n  ✅ No se detectaron problemas")

print("\n" + "="*80)

conn.close()

print("\n✅ Revisión completada\n")

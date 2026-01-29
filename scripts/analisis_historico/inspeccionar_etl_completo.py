#!/usr/bin/env python3
"""
Inspección completa del ETL y base de datos SQLite portal_energetico.db
Verifica: métricas, conversiones, unidades, integridad de datos
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import json

DB_PATH = "/home/admonctrlxm/server/portal_energetico.db"

def conectar_db():
    """Conectar a la base de datos"""
    return sqlite3.connect(DB_PATH)

print("="*80)
print("🔍 INSPECCIÓN PROFUNDA DEL ETL Y BASE DE DATOS")
print("="*80)

# 1. ESTRUCTURA DE LA BASE DE DATOS
print("\n📊 1. ESTRUCTURA DE LA BASE DE DATOS")
print("-"*80)

conn = conectar_db()

# Listar tablas
tablas = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)
print(f"\nTablas encontradas: {len(tablas)}")
for idx, tabla in tablas.iterrows():
    nombre_tabla = tabla['name']
    count = pd.read_sql_query(f"SELECT COUNT(*) as cnt FROM {nombre_tabla}", conn)['cnt'][0]
    print(f"  - {nombre_tabla}: {count:,} registros")

# Ver estructura de tabla metrics
print("\n📋 Estructura de tabla 'metrics':")
cursor = conn.execute('PRAGMA table_info(metrics)')
for row in cursor.fetchall():
    print(f"  - {row[1]:25s} ({row[2]})")

# 2. ANÁLISIS DE MÉTRICAS
print("\n📈 2. ANÁLISIS DE MÉTRICAS ENERGÉTICAS")
print("-"*80)

# Total de registros y rango de fechas
query = """
SELECT 
    COUNT(*) as total_registros,
    MIN(fecha) as fecha_min,
    MAX(fecha) as fecha_max,
    COUNT(DISTINCT metrica) as total_metricas,
    COUNT(DISTINCT entidad) as total_entidades
FROM metrics
"""
stats = pd.read_sql_query(query, conn)
print(f"\n📊 Estadísticas Generales:")
print(f"  Total registros: {stats['total_registros'][0]:,}")
print(f"  Fecha mínima: {stats['fecha_min'][0]}")
print(f"  Fecha máxima: {stats['fecha_max'][0]}")
print(f"  Métricas únicas: {stats['total_metricas'][0]}")
print(f"  Entidades únicas: {stats['total_entidades'][0]}")

# 3. MÉTRICAS POR CANTIDAD DE REGISTROS
print("\n📋 3. MÉTRICAS POR CANTIDAD DE REGISTROS (Top 30)")
print("-"*80)

query = """
SELECT 
    metrica,
    COUNT(*) as registros,
    MIN(fecha) as desde,
    MAX(fecha) as hasta,
    COUNT(DISTINCT entidad) as entidades
FROM metrics
GROUP BY metrica
ORDER BY registros DESC
LIMIT 30
"""
metricas_top = pd.read_sql_query(query, conn)
for idx, row in metricas_top.iterrows():
    print(f"{idx+1:2d}. {row['metrica']:30s} - {row['registros']:7,} registros | {row['entidades']:3d} entidades | {row['desde']} → {row['hasta']}")

# 4. VERIFICAR CONVERSIONES DE UNIDADES
print("\n🔄 4. VERIFICACIÓN DE CONVERSIONES DE UNIDADES")
print("-"*80)

# Verificar métricas que deberían estar en GWh
metricas_gwh = ['AporEner', 'Gene', 'DemaCome', 'PerdidasEner', 'PerdidasEnerReg', 'PerdidasEnerNoReg']

for metrica in metricas_gwh:
    query = f"""
    SELECT 
        metrica,
        MIN(valor_gwh) as min_val,
        MAX(valor_gwh) as max_val,
        AVG(valor_gwh) as avg_val,
        COUNT(*) as registros,
        MAX(unidad) as unidad
    FROM metrics
    WHERE metrica = '{metrica}'
    """
    df = pd.read_sql_query(query, conn)
    if not df.empty and df['registros'][0] > 0:
        min_val = df['min_val'][0]
        max_val = df['max_val'][0]
        avg_val = df['avg_val'][0]
        unidad = df['unidad'][0]
        
        # Detectar valores sospechosos (muy grandes o muy pequeños para GWh)
        sospechoso = ""
        if max_val > 1_000_000:  # Valores > 1M GWh son sospechosos (posible kWh sin convertir)
            sospechoso = " ⚠️ VALORES MUY GRANDES - Posible error de conversión"
        elif max_val < 0.001:  # Valores muy pequeños
            sospechoso = " ⚠️ VALORES MUY PEQUEÑOS"
        
        print(f"  {metrica:25s} [{unidad}]: Min={min_val:12.2f} | Max={max_val:12.2f} | Avg={avg_val:10.2f} | N={df['registros'][0]:6,}{sospechoso}")

# 5. BUSCAR MÉTRICAS CON POSIBLES ERRORES DE CONVERSIÓN DOBLE
print("\n⚠️  5. DETECCIÓN DE CONVERSIONES DOBLES O ERRORES")
print("-"*80)

# Verificar AporEnerMediHist (la que tuvimos que corregir antes)
query = """
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN valor_gwh > 1000000 THEN 1 ELSE 0 END) as valores_sospechosos,
    MAX(valor_gwh) as max_value
FROM metrics
WHERE metrica = 'AporEnerMediHist'
"""
apor_check = pd.read_sql_query(query, conn)
if apor_check['total'][0] > 0:
    print(f"\n✅ AporEnerMediHist (ya corregida anteriormente):")
    print(f"  Total registros: {apor_check['total'][0]:,}")
    print(f"  Valores > 1M (sospechosos): {apor_check['valores_sospechosos'][0]:,}")
    print(f"  Valor máximo: {apor_check['max_value'][0]:,.2f}")
    if apor_check['valores_sospechosos'][0] > 0:
        print("  ❌ PROBLEMA: Aún hay valores astronómicos")
    else:
        print("  ✅ OK: Sin valores astronómicos")

# Buscar otras métricas con valores sospechosos
query = """
SELECT 
    metrica,
    COUNT(*) as total_registros,
    SUM(CASE WHEN valor_gwh > 1000000 THEN 1 ELSE 0 END) as valores_muy_grandes,
    SUM(CASE WHEN valor_gwh < 0 THEN 1 ELSE 0 END) as valores_negativos,
    MAX(valor_gwh) as max_value,
    MIN(valor_gwh) as min_value
FROM metrics
GROUP BY metrica
HAVING valores_muy_grandes > 0 OR valores_negativos > 0
"""
metricas_sospechosas = pd.read_sql_query(query, conn)
if not metricas_sospechosas.empty:
    print(f"\n⚠️ Métricas con valores sospechosos:")
    for idx, row in metricas_sospechosas.iterrows():
        print(f"  - {row['metrica']:30s}: {row['valores_muy_grandes']:5,} valores >1M | {row['valores_negativos']:5,} negativos | Max={row['max_value']:,.0f}")
else:
    print("\n✅ No se detectaron métricas con valores sospechosos")

# 6. VERIFICAR COMPLETITUD DE DATOS RECIENTES
print("\n📅 6. COMPLETITUD DE DATOS RECIENTES (Últimos 30 días)")
print("-"*80)

fecha_limite = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

query = f"""
SELECT 
    metrica,
    COUNT(*) as registros_30dias,
    MAX(fecha) as ultima_fecha
FROM metrics
WHERE fecha >= '{fecha_limite}'
GROUP BY metrica
ORDER BY registros_30dias DESC
LIMIT 20
"""
recientes = pd.read_sql_query(query, conn)
print(f"\nMétricas con datos recientes (desde {fecha_limite}):")
for idx, row in recientes.iterrows():
    dias_desde_ultimo = (datetime.now() - datetime.strptime(row['ultima_fecha'], '%Y-%m-%d')).days
    actualizado = "✅" if dias_desde_ultimo < 7 else "⚠️"
    print(f"{actualizado} {row['metrica']:30s}: {row['registros_30dias']:5,} registros | Último: {row['ultima_fecha']} ({dias_desde_ultimo}d)")

# 7. VERIFICAR MÉTRICAS CRÍTICAS DEL PROYECTO
print("\n🎯 7. VERIFICACIÓN DE MÉTRICAS CRÍTICAS")
print("-"*80)

metricas_criticas = {
    'AporEner': 'Aportes de Energía Hídrica',
    'AporEnerMediHist': 'Aportes Medios Históricos',
    'Gene': 'Generación Total',
    'DemaCome': 'Demanda Comercial',
    'PerdidasEner': 'Pérdidas de Energía',
    'CapaEfecNeta': 'Capacidad Efectiva Neta',
    'RestAliv': 'Restricciones Aliviadas',
    'RestSinAliv': 'Restricciones Sin Aliviar',
}

for metric_id, descripcion in metricas_criticas.items():
    query = f"""
    SELECT 
        COUNT(*) as total,
        MIN(fecha) as desde,
        MAX(fecha) as hasta,
        COUNT(DISTINCT entidad) as entidades
    FROM metrics
    WHERE metrica = '{metric_id}'
    """
    df = pd.read_sql_query(query, conn)
    if df['total'][0] > 0:
        status = "✅"
        print(f"{status} {metric_id:25s} ({descripcion})")
        print(f"     {df['total'][0]:7,} registros | {df['entidades'][0]:3d} entidades | {df['desde'][0]} → {df['hasta'][0]}")
    else:
        print(f"❌ {metric_id:25s} ({descripcion}) - SIN DATOS")

# 8. VERIFICAR UNIDADES
print("\n📏 8. VERIFICACIÓN DE UNIDADES")
print("-"*80)

query = """
SELECT 
    unidad,
    COUNT(DISTINCT metrica) as metricas,
    COUNT(*) as registros
FROM metrics
GROUP BY unidad
ORDER BY registros DESC
"""
unidades = pd.read_sql_query(query, conn)
print("\nUnidades en uso:")
for idx, row in unidades.iterrows():
    print(f"  - {row['unidad']:10s}: {row['metricas']:3d} métricas | {row['registros']:,} registros")

# 9. REVISAR CONFIGURACIÓN DEL ETL
print("\n⚙️  9. REVISIÓN DE CONFIGURACIÓN DEL ETL")
print("-"*80)

try:
    from etl.config_metricas import METRICAS_CONFIG
    print(f"\nMétricas configuradas en ETL: {len(METRICAS_CONFIG)}")
    
    # Contar por categoría
    categorias = {}
    for metric_id, config in METRICAS_CONFIG.items():
        cat = config.get('categoria', 'Sin categoría')
        categorias[cat] = categorias.get(cat, 0) + 1
    
    print("\nMétricas por categoría:")
    for cat, count in sorted(categorias.items()):
        print(f"  - {cat}: {count} métricas")
    
    # Verificar conversiones configuradas
    print("\nConversiones configuradas:")
    conversiones = {}
    for metric_id, config in METRICAS_CONFIG.items():
        conv = config.get('conversion', 'ninguna')
        conversiones[conv] = conversiones.get(conv, 0) + 1
    
    for conv, count in sorted(conversiones.items()):
        print(f"  - {conv}: {count} métricas")
        
except Exception as e:
    print(f"⚠️ No se pudo cargar config_metricas.py: {e}")

# 10. COMPARAR MÉTRICAS EN DB vs CONFIGURACIÓN
print("\n🔍 10. COMPARACIÓN DB vs CONFIGURACIÓN ETL")
print("-"*80)

try:
    from etl.config_metricas import METRICAS_CONFIG
    
    # Métricas en DB
    query = "SELECT DISTINCT metrica FROM metrics"
    metricas_db = set(pd.read_sql_query(query, conn)['metrica'].tolist())
    
    # Métricas en config
    metricas_config = set(METRICAS_CONFIG.keys())
    
    # Comparar
    solo_en_db = metricas_db - metricas_config
    solo_en_config = metricas_config - metricas_db
    en_ambos = metricas_db & metricas_config
    
    print(f"\n✅ Métricas en ambos (DB y Config): {len(en_ambos)}")
    
    if solo_en_db:
        print(f"\n⚠️ Métricas en DB pero NO en config ({len(solo_en_db)}):")
        for m in sorted(list(solo_en_db)[:10]):
            print(f"  - {m}")
        if len(solo_en_db) > 10:
            print(f"  ... y {len(solo_en_db) - 10} más")
    
    if solo_en_config:
        print(f"\n⚠️ Métricas en config pero NO en DB ({len(solo_en_config)}):")
        for m in sorted(list(solo_en_config)[:10]):
            print(f"  - {m}")
        if len(solo_en_config) > 10:
            print(f"  ... y {len(solo_en_config) - 10} más")
            
except Exception as e:
    print(f"⚠️ No se pudo comparar: {e}")

conn.close()

print("\n" + "="*80)
print("✅ INSPECCIÓN COMPLETADA")
print("="*80)

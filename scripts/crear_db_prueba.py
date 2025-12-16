#!/usr/bin/env python3
"""
Script para crear una base de datos de prueba más pequeña
Copia solo los últimos 6 meses de datos de la BD completa
"""

import sqlite3
from datetime import datetime, timedelta
import os

def crear_db_prueba():
    """Crear BD de prueba con últimos 6 meses"""
    
    DB_COMPLETA = "/home/admonctrlxm/server/portal_energetico.db"
    DB_PRUEBA = "/home/admonctrlxm/server/portal_energetico_prueba.db"
    
    print("="*80)
    print("   📊 CREANDO BASE DE DATOS DE PRUEBA")
    print("="*80)
    print()
    
    # Calcular fecha de corte (6 meses atrás)
    fecha_corte = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    print(f"📅 Copiando datos desde: {fecha_corte}")
    print()
    
    # Conectar a BD completa
    print("📂 Conectando a BD completa...")
    conn_completa = sqlite3.connect(DB_COMPLETA)
    cursor_completa = conn_completa.cursor()
    
    # Obtener esquema
    print("📋 Obteniendo esquema...")
    cursor_completa.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='metrics'")
    create_table_sql = cursor_completa.fetchone()[0]
    
    # Crear BD de prueba
    print("🔨 Creando BD de prueba...")
    if os.path.exists(DB_PRUEBA):
        os.remove(DB_PRUEBA)
    
    conn_prueba = sqlite3.connect(DB_PRUEBA)
    cursor_prueba = conn_prueba.cursor()
    
    # Crear tabla
    cursor_prueba.execute(create_table_sql)
    
    # Copiar datos de últimos 6 meses
    print(f"📥 Copiando registros desde {fecha_corte}...")
    cursor_completa.execute("""
        SELECT * FROM metrics 
        WHERE fecha >= ?
        ORDER BY fecha DESC
    """, (fecha_corte,))
    
    registros = cursor_completa.fetchall()
    print(f"   Total registros a copiar: {len(registros):,}")
    
    # Insertar en BD de prueba
    cursor_completa.execute("PRAGMA table_info(metrics)")
    columnas = [col[1] for col in cursor_completa.fetchall()]
    placeholders = ",".join(["?" for _ in columnas])
    
    cursor_prueba.executemany(
        f"INSERT INTO metrics VALUES ({placeholders})",
        registros
    )
    
    # Crear índices
    print("🔍 Creando índices...")
    cursor_completa.execute("""
        SELECT sql FROM sqlite_master 
        WHERE type='index' AND tbl_name='metrics' AND sql IS NOT NULL
    """)
    
    for (index_sql,) in cursor_completa.fetchall():
        try:
            cursor_prueba.execute(index_sql)
        except sqlite3.OperationalError:
            pass  # Índice ya existe
    
    # Commit y cerrar
    conn_prueba.commit()
    
    # Estadísticas
    print()
    print("="*80)
    print("   ✅ BASE DE DATOS DE PRUEBA CREADA")
    print("="*80)
    print()
    
    cursor_prueba.execute("SELECT COUNT(*) FROM metrics")
    total = cursor_prueba.fetchone()[0]
    print(f"📊 Total registros: {total:,}")
    
    cursor_prueba.execute("SELECT MIN(fecha), MAX(fecha) FROM metrics")
    fecha_min, fecha_max = cursor_prueba.fetchone()
    print(f"📅 Rango de fechas: {fecha_min} a {fecha_max}")
    
    # Tamaño del archivo
    size_mb = os.path.getsize(DB_PRUEBA) / (1024 * 1024)
    print(f"💾 Tamaño archivo: {size_mb:.2f} MB")
    print()
    print(f"📁 Ubicación: {DB_PRUEBA}")
    print()
    print("Para descargar:")
    print(f"   scp admonctrlxm@Srvwebprdctrlxm:{DB_PRUEBA} ./")
    print()
    
    conn_completa.close()
    conn_prueba.close()

if __name__ == "__main__":
    crear_db_prueba()

#!/usr/bin/env python3
"""
Migración SQLite → PostgreSQL para Portal MME
Migra todas las tablas manteniendo estructura y datos
"""

import sqlite3
import subprocess
import sys
import time
from datetime import datetime

def log(msg):
    """Logging con timestamp"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_sqlite_schema():
    """Obtener esquema de todas las tablas"""
    conn = sqlite3.connect('portal_energetico.db')
    cursor = conn.cursor()
    
    # Obtener todas las tablas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]
    
    schema = {}
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        schema[table] = columns
    
    conn.close()
    return schema

def sqlite_to_postgres_type(sqlite_type):
    """Convertir tipos SQLite a PostgreSQL"""
    sqlite_type = sqlite_type.upper()
    
    if 'INT' in sqlite_type:
        return 'INTEGER'
    elif 'CHAR' in sqlite_type or 'TEXT' in sqlite_type:
        return 'TEXT'
    elif 'REAL' in sqlite_type or 'FLOAT' in sqlite_type or 'DOUBLE' in sqlite_type:
        return 'DOUBLE PRECISION'
    elif 'DATE' in sqlite_type or 'TIME' in sqlite_type:
        return 'TIMESTAMP'
    elif 'BOOL' in sqlite_type:
        return 'BOOLEAN'
    else:
        return 'TEXT'  # Default

def create_postgres_tables(schema):
    """Crear tablas en PostgreSQL"""
    log("📋 Creando esquema en PostgreSQL...")
    
    for table, columns in schema.items():
        # Construir CREATE TABLE
        col_defs = []
        for col in columns:
            cid, name, type_, notnull, dflt_value, pk = col
            pg_type = sqlite_to_postgres_type(type_)
            
            col_def = f'"{name}" {pg_type}'
            if pk:
                col_def += ' PRIMARY KEY'
            if notnull and not pk:
                col_def += ' NOT NULL'
            
            col_defs.append(col_def)
        
        create_sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(col_defs)});'
        
        # Ejecutar en PostgreSQL
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'portal_energetico', '-c', create_sql],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            log(f"  ✅ Tabla '{table}' creada")
        else:
            log(f"  ❌ Error en tabla '{table}': {result.stderr}")
            return False
    
    return True

def migrate_table_data(table, batch_size=10000):
    """Migrar datos de una tabla en lotes usando INSERT"""
    log(f"📦 Migrando tabla '{table}'...")
    
    # Conectar a SQLite
    sqlite_conn = sqlite3.connect('portal_energetico.db')
    sqlite_cursor = sqlite_conn.cursor()
    
    # Contar registros
    sqlite_cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
    total_rows = sqlite_cursor.fetchone()[0]
    
    if total_rows == 0:
        log(f"  ⚠️ Tabla '{table}' vacía, saltando...")
        sqlite_conn.close()
        return True
    
    log(f"  📊 Total registros: {total_rows:,}")
    
    # Obtener nombres de columnas
    sqlite_cursor.execute(f'SELECT * FROM "{table}" LIMIT 1')
    columns = [description[0] for description in sqlite_cursor.description]
    col_names = ','.join(f'"{col}"' for col in columns)
    placeholders = ','.join(['%s'] * len(columns))
    
    # Migrar en lotes
    offset = 0
    migrated = 0
    start_time = time.time()
    
    while offset < total_rows:
        # Leer lote desde SQLite
        sqlite_cursor.execute(f'SELECT * FROM "{table}" LIMIT {batch_size} OFFSET {offset}')
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            break
        
        # Construir sentencias INSERT
        import tempfile
        import os
        
        # Usar /tmp/postgres_migration/ con permisos adecuados
        migration_dir = '/tmp/postgres_migration'
        os.makedirs(migration_dir, exist_ok=True)
        os.chmod(migration_dir, 0o777)
        
        tmp_path = f'{migration_dir}/batch_{offset}.sql'
        
        with open(tmp_path, 'w') as f:
            for row in rows:
                # Escapar valores
                values = []
                for val in row:
                    if val is None:
                        values.append('NULL')
                    elif isinstance(val, str):
                        # Escapar comillas simples y backslashes
                        escaped = val.replace('\\', '\\\\').replace("'", "''")
                        values.append(f"'{escaped}'")
                    elif isinstance(val, (int, float)):
                        values.append(str(val))
                    else:
                        values.append(f"'{str(val)}'")
                
                values_str = ','.join(values)
                f.write(f'INSERT INTO "{table}" ({col_names}) VALUES ({values_str});\n')
        
        # Dar permisos de lectura para postgres
        os.chmod(tmp_path, 0o644)
        
        # Ejecutar en PostgreSQL
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'portal_energetico', '-f', tmp_path],
            capture_output=True,
            text=True
        )
        
        # Limpiar archivo temporal
        os.unlink(tmp_path)
        
        if result.returncode != 0:
            log(f"  ❌ Error migrando lote: {result.stderr[:200]}")
            sqlite_conn.close()
            return False
        
        migrated += len(rows)
        offset += batch_size
        
        # Progreso
        progress = (migrated / total_rows) * 100
        elapsed = time.time() - start_time
        rate = migrated / elapsed if elapsed > 0 else 0
        eta = (total_rows - migrated) / rate if rate > 0 else 0
        
        log(f"  ⏳ {migrated:,}/{total_rows:,} ({progress:.1f}%) - {rate:.0f} rows/s - ETA {eta/60:.1f}min")
    
    sqlite_conn.close()
    
    elapsed = time.time() - start_time
    log(f"  ✅ Tabla '{table}' migrada en {elapsed/60:.1f} minutos")
    
    return True

def verify_migration():
    """Verificar que la migración fue exitosa"""
    log("🔍 Verificando migración...")
    
    # Contar en SQLite
    sqlite_conn = sqlite3.connect('portal_energetico.db')
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in sqlite_cursor.fetchall()]
    
    all_ok = True
    
    for table in tables:
        # Count SQLite
        sqlite_cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        sqlite_count = sqlite_cursor.fetchone()[0]
        
        # Count PostgreSQL
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'portal_energetico', '-t', '-c', 
             f'SELECT COUNT(*) FROM "{table}"'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            pg_count = int(result.stdout.strip())
            
            if sqlite_count == pg_count:
                log(f"  ✅ '{table}': {sqlite_count:,} registros migrados correctamente")
            else:
                log(f"  ❌ '{table}': SQLite={sqlite_count:,}, PostgreSQL={pg_count:,} - DIFERENCIA")
                all_ok = False
        else:
            log(f"  ❌ Error verificando '{table}': {result.stderr}")
            all_ok = False
    
    sqlite_conn.close()
    return all_ok

def main():
    """Proceso principal de migración"""
    log("=" * 70)
    log("🚀 INICIANDO MIGRACIÓN SQLITE → POSTGRESQL")
    log("=" * 70)
    
    start_time = time.time()
    
    try:
        # 1. Obtener esquema
        log("📋 Paso 1: Analizando esquema SQLite...")
        schema = get_sqlite_schema()
        log(f"  ✅ {len(schema)} tablas encontradas: {', '.join(schema.keys())}")
        
        # 2. Crear tablas en PostgreSQL
        log("\n📋 Paso 2: Creando tablas en PostgreSQL...")
        if not create_postgres_tables(schema):
            log("❌ Error creando tablas, abortando")
            return 1
        
        # 3. Migrar datos
        log("\n📦 Paso 3: Migrando datos...")
        for table in schema.keys():
            if not migrate_table_data(table):
                log(f"❌ Error migrando tabla '{table}', abortando")
                return 1
        
        # 4. Verificar
        log("\n🔍 Paso 4: Verificando migración...")
        if not verify_migration():
            log("⚠️ Verificación encontró diferencias")
            return 1
        
        elapsed = time.time() - start_time
        log("\n" + "=" * 70)
        log(f"✅ MIGRACIÓN COMPLETADA EXITOSAMENTE en {elapsed/60:.1f} minutos")
        log("=" * 70)
        
        return 0
        
    except Exception as e:
        log(f"\n❌ ERROR FATAL: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())

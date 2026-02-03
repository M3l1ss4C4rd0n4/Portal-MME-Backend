#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
PostgreSQL Database Explorer - Portal Energético MME
═══════════════════════════════════════════════════════════════
Herramienta CLI para explorar la base de datos PostgreSQL
Uso: python3 scripts/db_explorer.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor
from tabulate import tabulate
from core.config import Settings

settings = Settings()


def get_connection():
    """Crear conexión a PostgreSQL"""
    return psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        cursor_factory=RealDictCursor
    )


def list_tables():
    """Listar todas las tablas"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
                FROM pg_tables 
                WHERE schemaname = 'public' 
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
            """)
            tables = cursor.fetchall()
            
            print("\n" + "="*80)
            print("📊 TABLAS EN portal_energetico")
            print("="*80)
            print(tabulate(tables, headers="keys", tablefmt="grid"))
            return [t['tablename'] for t in tables]


def table_info(table_name):
    """Información detallada de una tabla"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # Estructura
            cursor.execute(f"""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable
                FROM information_schema.columns 
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position;
            """)
            columns = cursor.fetchall()
            
            # Conteo
            cursor.execute(f"SELECT COUNT(*) as total FROM {table_name};")
            count = cursor.fetchone()['total']
            
            print(f"\n{'='*80}")
            print(f"📋 TABLA: {table_name}")
            print(f"📊 Total registros: {count:,}")
            print(f"{'='*80}")
            print(tabulate(columns, headers="keys", tablefmt="grid"))


def preview_data(table_name, limit=10):
    """Previsualizar datos de una tabla"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit};")
            rows = cursor.fetchall()
            
            if rows:
                print(f"\n{'='*80}")
                print(f"🔍 PREVIEW: {table_name} (primeros {limit} registros)")
                print(f"{'='*80}")
                print(tabulate(rows, headers="keys", tablefmt="grid"))
            else:
                print(f"\n⚠️  Tabla {table_name} vacía")


def execute_query(query):
    """Ejecutar consulta personalizada"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            
            if cursor.description:  # Si hay resultados
                rows = cursor.fetchall()
                print(f"\n{'='*80}")
                print(f"✅ Resultados ({len(rows)} filas)")
                print(f"{'='*80}")
                if rows:
                    print(tabulate(rows, headers="keys", tablefmt="grid"))
                else:
                    print("Sin resultados")
            else:
                print("\n✅ Query ejecutada exitosamente")


def main_menu():
    """Menú principal interactivo"""
    while True:
        print("\n" + "="*80)
        print("🗄️  POSTGRESQL DATABASE EXPLORER - Portal Energético MME")
        print("="*80)
        print("\n1. Listar todas las tablas")
        print("2. Ver información de una tabla")
        print("3. Previsualizar datos de una tabla")
        print("4. Ejecutar consulta SQL personalizada")
        print("5. Estadísticas rápidas")
        print("6. Salir")
        
        choice = input("\n👉 Selecciona una opción (1-6): ").strip()
        
        try:
            if choice == '1':
                tables = list_tables()
                
            elif choice == '2':
                table = input("📋 Nombre de la tabla: ").strip()
                table_info(table)
                
            elif choice == '3':
                table = input("📋 Nombre de la tabla: ").strip()
                limit = input("🔢 Límite de registros (default 10): ").strip() or "10"
                preview_data(table, int(limit))
                
            elif choice == '4':
                print("\n💡 Ejemplo: SELECT * FROM metrics WHERE fecha >= '2026-01-01' LIMIT 10;")
                query = input("\n📝 SQL Query: ").strip()
                if query:
                    execute_query(query)
                    
            elif choice == '5':
                print("\n📊 Ejecutando estadísticas...")
                execute_query("""
                    SELECT 
                        'metrics' as tabla,
                        COUNT(*) as registros,
                        MIN(fecha) as fecha_min,
                        MAX(fecha) as fecha_max
                    FROM metrics
                    UNION ALL
                    SELECT 
                        'metrics_hourly',
                        COUNT(*),
                        MIN(fecha),
                        MAX(fecha)
                    FROM metrics_hourly
                    UNION ALL
                    SELECT 
                        'distribution_metrics',
                        COUNT(*),
                        NULL,
                        NULL
                    FROM distribution_metrics;
                """)
                
            elif choice == '6':
                print("\n👋 ¡Hasta luego!\n")
                break
                
            else:
                print("\n⚠️  Opción inválida")
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n👋 ¡Hasta luego!\n")
        sys.exit(0)

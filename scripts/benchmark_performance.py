#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    BENCHMARK DE PERFORMANCE - Fase 4                          ║
║                                                                               ║
║  Script para medir y comparar performance antes/después de optimizaciones    ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Uso:
    cd /home/admonctrlxm/server
    python3 scripts/benchmark_performance.py

Métricas medidas:
    - Tiempo de carga de módulos
    - Tiempo de queries a DB
    - Tiempo de respuesta de API
    - Uso de memoria
"""

import sys
import time
import psutil
import os
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)


def print_result(name, value, unit="ms", threshold=None):
    """Imprime resultado con color según threshold."""
    if threshold:
        if value <= threshold:
            status = "✅"
        elif value <= threshold * 1.5:
            status = "⚠️"
        else:
            status = "❌"
    else:
        status = "📊"
    
    print(f"  {status} {name}: {value:.2f} {unit}")


def benchmark_module_imports():
    """Benchmark de tiempos de importación de módulos."""
    print_header("1. TIEMPOS DE IMPORTACIÓN")
    
    modules = [
        ('core.config', 'settings'),
        ('infrastructure.database.manager', 'db_manager'),
        ('domain.services.generation_service', 'GenerationService'),
        ('domain.services.metrics_service', 'MetricsService'),
        ('api.main', 'app'),
        ('core.app_factory', 'create_app'),
    ]
    
    results = {}
    for module_name, import_name in modules:
        start = time.time()
        try:
            exec(f"from {module_name} import {import_name}")
            elapsed = (time.time() - start) * 1000
            results[module_name] = elapsed
            print_result(module_name, elapsed, threshold=1000)
        except Exception as e:
            print(f"  ❌ {module_name}: ERROR - {e}")
    
    return results


def benchmark_database_queries():
    """Benchmark de queries a base de datos."""
    print_header("2. QUERIES A BASE DE DATOS")
    
    try:
        from infrastructure.database.manager import db_manager
        
        queries = [
            ("COUNT metrics", "SELECT COUNT(*) FROM metrics"),
            ("COUNT metrics_hourly", "SELECT COUNT(*) FROM metrics_hourly"),
            ("Metrics recientes", "SELECT * FROM metrics WHERE fecha >= CURRENT_DATE - INTERVAL '7 days' LIMIT 100"),
            ("Métrica específica", "SELECT * FROM metrics WHERE metrica = 'Gene' ORDER BY fecha DESC LIMIT 100"),
            ("Predicciones", "SELECT * FROM predictions ORDER BY fecha_prediccion DESC LIMIT 100"),
        ]
        
        results = {}
        for name, query in queries:
            start = time.time()
            try:
                df = db_manager.query_df(query)
                elapsed = (time.time() - start) * 1000
                row_count = len(df)
                results[name] = {'time_ms': elapsed, 'rows': row_count}
                print(f"  📊 {name}: {elapsed:.2f} ms ({row_count:,} filas)")
            except Exception as e:
                print(f"  ❌ {name}: ERROR - {e}")
        
        return results
        
    except Exception as e:
        print(f"  ❌ Error conectando a DB: {e}")
        return {}


def benchmark_cache_operations():
    """Benchmark de operaciones de caché."""
    print_header("3. OPERACIONES DE CACHÉ (Redis)")
    
    try:
        from core.cache import cache_manager
        
        # Test SET
        start = time.time()
        for i in range(100):
            cache_manager.set(f"benchmark_key_{i}", {"data": f"value_{i}", "number": i})
        set_time = (time.time() - start) * 1000 / 100
        
        # Test GET (hit)
        start = time.time()
        for i in range(100):
            cache_manager.get(f"benchmark_key_{i}")
        get_hit_time = (time.time() - start) * 1000 / 100
        
        # Test GET (miss)
        start = time.time()
        for i in range(100):
            cache_manager.get(f"nonexistent_key_{i}")
        get_miss_time = (time.time() - start) * 1000 / 100
        
        # Limpiar
        for i in range(100):
            cache_manager.delete(f"benchmark_key_{i}")
        
        print_result("SET", set_time, threshold=5)
        print_result("GET (hit)", get_hit_time, threshold=2)
        print_result("GET (miss)", get_miss_time, threshold=2)
        
        stats = cache_manager.get_stats()
        print(f"\n  📊 Estadísticas de caché:")
        print(f"     Hits: {stats['hits']}")
        print(f"     Misses: {stats['misses']}")
        print(f"     Hit rate: {stats['hit_rate_percent']:.1f}%")
        
        return {
            'set_ms': set_time,
            'get_hit_ms': get_hit_time,
            'get_miss_ms': get_miss_time,
        }
        
    except Exception as e:
        print(f"  ❌ Error con caché: {e}")
        return {}


def benchmark_memory_usage():
    """Benchmark de uso de memoria."""
    print_header("4. USO DE MEMORIA")
    
    process = psutil.Process(os.getpid())
    
    # Memoria base
    base_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # Importar módulos pesados
    start_mem = process.memory_info().rss / 1024 / 1024
    from core.app_factory import create_app
    import pandas as pd
    import numpy as np
    end_mem = process.memory_info().rss / 1024 / 1024
    
    # Crear app
    app_mem_before = process.memory_info().rss / 1024 / 1024
    app = create_app()
    app_mem_after = process.memory_info().rss / 1024 / 1024
    
    print(f"  📊 Memoria base: {base_memory:.1f} MB")
    print(f"  📊 Memoria después de imports: {end_mem:.1f} MB (+{end_mem - start_mem:.1f} MB)")
    print(f"  📊 Memoria después de crear app: {app_mem_after:.1f} MB (+{app_mem_after - app_mem_before:.1f} MB)")
    print(f"  📊 Memoria total usada: {app_mem_after:.1f} MB")
    
    return {
        'base_mb': base_memory,
        'after_imports_mb': end_mem,
        'after_app_mb': app_mem_after,
    }


def benchmark_api_response():
    """Benchmark de respuesta de API."""
    print_header("5. RESPUESTA DE API (FastAPI)")
    
    try:
        from fastapi.testclient import TestClient
        from api.main import app
        
        client = TestClient(app)
        
        endpoints = [
            ("GET /health", lambda: client.get("/health")),
            ("GET /", lambda: client.get("/")),
        ]
        
        results = {}
        for name, func in endpoints:
            times = []
            for _ in range(5):  # 5 requests
                start = time.time()
                response = func()
                elapsed = (time.time() - start) * 1000
                times.append(elapsed)
            
            avg_time = sum(times) / len(times)
            results[name] = avg_time
            status = "✅" if response.status_code == 200 else "❌"
            print(f"  {status} {name}: {avg_time:.2f} ms (status: {response.status_code})")
        
        return results
        
    except Exception as e:
        print(f"  ❌ Error en benchmark API: {e}")
        return {}


def generate_report(all_results):
    """Genera reporte final."""
    print_header("REPORTE FINAL DE PERFORMANCE")
    
    print("\n  📈 Resumen de métricas:")
    
    # Module imports
    if 'modules' in all_results:
        avg_import = sum(all_results['modules'].values()) / len(all_results['modules'])
        print(f"     Tiempo promedio de import: {avg_import:.1f} ms")
    
    # DB queries
    if 'db' in all_results:
        total_db_time = sum(r['time_ms'] for r in all_results['db'].values())
        print(f"     Tiempo total queries DB: {total_db_time:.1f} ms")
    
    # Cache
    if 'cache' in all_results:
        print(f"     Cache SET: {all_results['cache']['set_ms']:.2f} ms")
        print(f"     Cache GET (hit): {all_results['cache']['get_hit_ms']:.2f} ms")
    
    # Memory
    if 'memory' in all_results:
        print(f"     Memoria total: {all_results['memory']['after_app_mb']:.1f} MB")
    
    # API
    if 'api' in all_results:
        avg_api = sum(all_results['api'].values()) / len(all_results['api'])
        print(f"     Tiempo promedio API: {avg_api:.2f} ms")
    
    # Umbrales de referencia
    print("\n  📋 Umbrales de referencia:")
    print("     ✅ Import módulo: < 1000 ms")
    print("     ✅ Query DB simple: < 100 ms")
    print("     ✅ Cache GET: < 2 ms")
    print("     ✅ API response: < 50 ms")
    print("     ✅ Memoria total: < 500 MB")
    
    print("\n  💡 Recomendaciones:")
    if 'modules' in all_results:
        slow_modules = [m for m, t in all_results['modules'].items() if t > 1000]
        if slow_modules:
            print(f"     - Optimizar imports: {', '.join(slow_modules)}")
    
    if 'db' in all_results:
        slow_queries = [n for n, r in all_results['db'].items() if r['time_ms'] > 500]
        if slow_queries:
            print(f"     - Agregar índices para: {', '.join(slow_queries)}")
    
    print("     - Usar @cached para queries frecuentes")
    print("     - Implementar lazy loading para módulos pesados")


def main():
    print("\n" + "="*70)
    print("  BENCHMARK DE PERFORMANCE - PORTAL ENERGÉTICO MME")
    print("="*70)
    print(f"\n  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  PID: {os.getpid()}")
    
    all_results = {}
    
    # Ejecutar benchmarks
    all_results['modules'] = benchmark_module_imports()
    all_results['db'] = benchmark_database_queries()
    all_results['cache'] = benchmark_cache_operations()
    all_results['memory'] = benchmark_memory_usage()
    all_results['api'] = benchmark_api_response()
    
    # Generar reporte
    generate_report(all_results)
    
    print("\n" + "="*70)
    print("  BENCHMARK COMPLETADO")
    print("="*70)


if __name__ == "__main__":
    main()

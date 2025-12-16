#!/usr/bin/env python3
"""
Script de diagnóstico de performance para tablero de generación por fuentes
"""

import sys
import time
from datetime import date, timedelta
import pandas as pd

# Agregar path
sys.path.insert(0, '/home/admonctrlxm/server')

from utils._xm import get_objetoAPI
from utils.cache_manager import get_cache_key, get_from_cache
from pages.generacion_fuentes_unificado import (
    obtener_listado_recursos,
    obtener_generacion_plantas,
    calcular_kpis_fuente
)

def test_performance():
    """Prueba de performance paso a paso"""
    print("=" * 80)
    print("DIAGNÓSTICO DE PERFORMANCE - Generación por Fuentes")
    print("=" * 80)
    
    tipo_fuente = 'EOLICA'
    fecha_fin = date.today()
    
    # TEST 1: Rango pequeño (7 días)
    print("\n📊 TEST 1: Rango PEQUEÑO (7 días)")
    print("-" * 80)
    fecha_inicio_small = fecha_fin - timedelta(days=7)
    
    t0 = time.time()
    plantas_df = obtener_listado_recursos(tipo_fuente)
    t1 = time.time()
    print(f"✓ obtener_listado_recursos: {t1-t0:.2f}s ({len(plantas_df)} plantas)")
    
    if not plantas_df.empty:
        t0 = time.time()
        df_gen, df_part, kpis = obtener_generacion_plantas(
            fecha_inicio_small, fecha_fin, plantas_df
        )
        t1 = time.time()
        print(f"✓ obtener_generacion_plantas: {t1-t0:.2f}s ({len(df_gen)} registros)")
        print(f"  - KPIs: {kpis}")
    
    # TEST 2: Rango mediano (60 días)
    print("\n📊 TEST 2: Rango MEDIANO (60 días)")
    print("-" * 80)
    fecha_inicio_med = fecha_fin - timedelta(days=60)
    
    t0 = time.time()
    df_gen, df_part, kpis = obtener_generacion_plantas(
        fecha_inicio_med, fecha_fin, plantas_df
    )
    t1 = time.time()
    print(f"✓ obtener_generacion_plantas: {t1-t0:.2f}s ({len(df_gen)} registros)")
    print(f"  - KPIs: {kpis}")
    
    # TEST 3: Rango grande (365 días)
    print("\n📊 TEST 3: Rango GRANDE (365 días)")
    print("-" * 80)
    fecha_inicio_large = fecha_fin - timedelta(days=365)
    
    t0 = time.time()
    df_gen, df_part, kpis = obtener_generacion_plantas(
        fecha_inicio_large, fecha_fin, plantas_df
    )
    t1 = time.time()
    print(f"✓ obtener_generacion_plantas: {t1-t0:.2f}s ({len(df_gen)} registros)")
    print(f"  - KPIs: {kpis}")
    
    # TEST 4: Segunda llamada (cache test)
    print("\n📊 TEST 4: Segunda llamada (CACHE TEST - 365 días)")
    print("-" * 80)
    t0 = time.time()
    df_gen, df_part, kpis = obtener_generacion_plantas(
        fecha_inicio_large, fecha_fin, plantas_df
    )
    t1 = time.time()
    print(f"✓ obtener_generacion_plantas (CACHE): {t1-t0:.2f}s ⚡")
    print(f"  - Registros: {len(df_gen)}")
    print(f"  - KPIs incluidos: {list(kpis.keys())}")
    
    # TEST 5: Verificar estado del cache
    print("\n📊 TEST 5: Estado del Cache")
    print("-" * 80)
    import os
    cache_dirs = [
        '/var/cache/portal_energetico_cache',
        os.path.expanduser('~/.cache/portal_energetico_cache'),
        '/tmp/portal_energetico_cache'
    ]
    
    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir):
            archivos = len([f for f in os.listdir(cache_dir) if f.endswith('.pkl')])
            size = sum(os.path.getsize(os.path.join(cache_dir, f)) 
                      for f in os.listdir(cache_dir) if f.endswith('.pkl'))
            print(f"✓ {cache_dir}")
            print(f"  - Archivos: {archivos}")
            print(f"  - Tamaño: {size/1024/1024:.2f} MB")
            break
    
    print("\n" + "=" * 80)
    print("DIAGNÓSTICO COMPLETADO")
    print("=" * 80)

if __name__ == '__main__':
    test_performance()

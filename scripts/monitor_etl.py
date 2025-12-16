#!/usr/bin/env python3
"""
Monitor de progreso del ETL
Muestra estadísticas en tiempo real de la carga de métricas
"""

import sqlite3
import time
import os
from datetime import datetime

DB_PATH = '/home/admonctrlxm/server/portal_energetico.db'

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Métricas únicas
    cursor.execute("SELECT COUNT(DISTINCT metrica) FROM metrics")
    metricas = cursor.fetchone()[0]
    
    # Total registros
    cursor.execute("SELECT COUNT(*) FROM metrics")
    registros = cursor.fetchone()[0]
    
    # Métricas por sección
    cursor.execute("""
        SELECT metrica, COUNT(*) as registros, 
               COUNT(DISTINCT fecha) as dias,
               MIN(fecha) as fecha_min,
               MAX(fecha) as fecha_max
        FROM metrics
        GROUP BY metrica
        ORDER BY metrica
    """)
    metricas_detalle = cursor.fetchall()
    
    conn.close()
    
    return {
        'metricas_unicas': metricas,
        'total_registros': registros,
        'detalle': metricas_detalle
    }

def clasificar_metrica(metrica):
    """Clasificar métrica por sección"""
    if 'Gene' in metrica or 'CapEfec' in metrica or 'ENFICC' in metrica or 'Oblig' in metrica:
        return '⚡ Generación'
    elif 'Dema' in metrica or 'RecuMe' in metrica or 'GranCons' in metrica:
        return '📊 Demanda'
    elif 'Dispo' in metrica or 'CargoUso' in metrica:
        return '⚡ Transmisión'
    elif 'Rest' in metrica or 'DesvGen' in metrica:
        return '🚫 Restricciones'
    elif 'Prec' in metrica or 'Cost' in metrica:
        return '💰 Precios'
    elif 'Comp' in metrica or 'Vent' in metrica or 'Trans' in metrica:
        return '💼 Transacciones'
    elif 'Perdidas' in metrica or 'Perdi' in metrica:
        return '📉 Pérdidas'
    elif 'Impo' in metrica or 'Expo' in metrica or 'TIE' in metrica:
        return '🌍 Intercambios'
    elif 'Apor' in metrica or 'Volu' in metrica or 'Vert' in metrica or 'Cota' in metrica or 'Nivel' in metrica:
        return '💧 Hidrología'
    elif 'Cons' in metrica or 'Emision' in metrica or 'factor' in metrica:
        return '🔥 Combustibles'
    elif 'Irr' in metrica or 'Temp' in metrica and 'Solar' in metrica:
        return '☀️ Renovables'
    elif 'FAZ' in metrica or 'FAER' in metrica or 'PRONE' in metrica or 'Cargo' in metrica or 'Carg' in metrica:
        return '💵 Cargos'
    else:
        return '❓ Otros'

def mostrar_stats():
    os.system('clear')
    stats = get_stats()
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         MONITOR ETL - MÉTRICAS XM → SQLITE                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"\n⏰ Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n📊 Resumen General:")
    print(f"  • Métricas únicas: {stats['metricas_unicas']}")
    print(f"  • Total registros: {stats['total_registros']:,}")
    print(f"  • Promedio registros/métrica: {stats['total_registros'] // max(stats['metricas_unicas'], 1):,}")
    
    # Agrupar por sección
    secciones = {}
    for metrica, registros, dias, fecha_min, fecha_max in stats['detalle']:
        seccion = clasificar_metrica(metrica)
        if seccion not in secciones:
            secciones[seccion] = []
        secciones[seccion].append((metrica, registros, dias, fecha_min, fecha_max))
    
    print(f"\n📁 Métricas por Sección:")
    for seccion, metricas in sorted(secciones.items()):
        total_reg = sum(m[1] for m in metricas)
        print(f"\n{seccion}")
        print(f"  Métricas: {len(metricas)} | Registros: {total_reg:,}")
        for metrica, registros, dias, fecha_min, fecha_max in sorted(metricas):
            print(f"    • {metrica:20} {registros:>8,} reg | {dias:>3} días | {fecha_min} → {fecha_max}")
    
    print(f"\n" + "="*70)
    print(f"💡 Para detener este monitor: Ctrl+C")
    print(f"📄 Log ETL: tail -f /home/admonctrlxm/server/logs/etl_todas_metricas.log")

if __name__ == "__main__":
    try:
        while True:
            mostrar_stats()
            time.sleep(10)  # Actualizar cada 10 segundos
    except KeyboardInterrupt:
        print("\n\n✅ Monitor detenido")

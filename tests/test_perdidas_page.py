#!/usr/bin/env python3
"""
Script de prueba para página de Pérdidas
Inserta datos temporales para probar funcionalidad
"""

import sqlite3
import pandas as pd
from datetime import date, timedelta

def insertar_datos_prueba():
    """Insertar datos de prueba de pérdidas en SQLite"""
    
    conn = sqlite3.connect('portal_energetico.db')
    cursor = conn.cursor()
    
    print('🔧 Insertando datos de prueba para Pérdidas...\n')
    
    # Generar 30 días de datos de prueba
    hoy = date.today()
    fecha_inicio = hoy - timedelta(days=30)
    
    datos_prueba = []
    
    for i in range(31):
        fecha = fecha_inicio + timedelta(days=i)
        
        # Datos simulados (valores aproximados reales)
        perdidas_total = 40.0 + (i % 10) * 2.0  # 40-60 GWh/día
        perdidas_reg = perdidas_total * 0.68    # ~68% reguladas
        perdidas_no_reg = perdidas_total * 0.32 # ~32% no reguladas
        
        # PerdidasEner
        datos_prueba.append((
            fecha.strftime('%Y-%m-%d'),
            'PerdidasEner',
            'Sistema',
            'Sistema',
            perdidas_total,
            'GWh',
            pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        
        # PerdidasEnerReg
        datos_prueba.append((
            fecha.strftime('%Y-%m-%d'),
            'PerdidasEnerReg',
            'Sistema',
            'Sistema',
            perdidas_reg,
            'GWh',
            pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        
        # PerdidasEnerNoReg
        datos_prueba.append((
            fecha.strftime('%Y-%m-%d'),
            'PerdidasEnerNoReg',
            'Sistema',
            'Sistema',
            perdidas_no_reg,
            'GWh',
            pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
    
    # Insertar en SQLite
    cursor.executemany('''
        INSERT INTO metrics (fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', datos_prueba)
    
    conn.commit()
    
    print(f'✅ Insertados {len(datos_prueba)} registros de prueba')
    print(f'   Período: {fecha_inicio} a {hoy}')
    print(f'   Métricas: PerdidasEner, PerdidasEnerReg, PerdidasEnerNoReg')
    
    # Verificar
    print('\n📊 Verificando datos insertados:\n')
    
    for metric in ['PerdidasEner', 'PerdidasEnerReg', 'PerdidasEnerNoReg']:
        cursor.execute('''
            SELECT COUNT(*), MIN(fecha), MAX(fecha), AVG(valor_gwh)
            FROM metrics
            WHERE metrica = ?
        ''', (metric,))
        
        result = cursor.fetchone()
        print(f'   {metric}:')
        print(f'      Registros: {result[0]}')
        print(f'      Período: {result[1]} a {result[2]}')
        print(f'      Promedio: {result[3]:.2f} GWh/día')
    
    conn.close()
    
    print('\n✅ Datos de prueba listos!')
    print('\n🌐 Puedes probar la página en:')
    print('   http://172.17.0.46:8050/perdidas-tecnicas')
    print()

if __name__ == '__main__':
    insertar_datos_prueba()

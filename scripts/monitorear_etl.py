#!/usr/bin/env python3
"""
Script para monitorear el progreso del ETL histórico
"""

import time
import os
from infrastructure.database.connection import connection_manager

def monitorear():
    metricas_restricciones = ['RespComerAGC', 'RestAliv', 'RestSinAliv']
    
    print('🔄 MONITOREO ETL HISTÓRICO - RESTRICCIONES')
    print('='*80)
    print('Presiona Ctrl+C para salir\n')
    
    try:
        while True:
            with connection_manager.get_connection() as conn:
                cur = conn.cursor()
                
                print(f'\r⏰ {time.strftime("%H:%M:%S")} | ', end='')
                
                for metrica in metricas_restricciones:
                    cur.execute('''
                        SELECT COUNT(*), MIN(fecha), MAX(fecha)
                        FROM metrics
                        WHERE metrica = %s
                    ''', (metrica,))
                    row = cur.fetchone()
                    count = row[0] if row else 0
                    
                    if count > 0:
                        min_fecha = str(row[1])[:10] if row[1] else 'N/A'
                        max_fecha = str(row[2])[:10] if row[2] else 'N/A'
                        print(f'{metrica}: {count:>5,} ({min_fecha} a {max_fecha}) | ', end='')
                    else:
                        print(f'{metrica}: {count:>5,} | ', end='')
                
                # Buscar el log más reciente
                log_dir = '/home/admonctrlxm/server/logs'
                logs = [f for f in os.listdir(log_dir) if f.startswith('etl_historico_')]
                if logs:
                    latest_log = max([os.path.join(log_dir, f) for f in logs], key=os.path.getmtime)
                    # Leer última línea del log
                    with open(latest_log, 'r') as f:
                        lines = f.readlines()
                        if lines:
                            last_line = lines[-1].strip()
                            # Extraer fecha si está en el log
                            if 'Batch:' in last_line:
                                print(f'| Log: {last_line[-50:]}', end='')
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        print('\n\n✅ Monitoreo finalizado')

if __name__ == '__main__':
    monitorear()

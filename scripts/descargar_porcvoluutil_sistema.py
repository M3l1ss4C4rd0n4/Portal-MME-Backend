#!/usr/bin/env python3
"""
Script temporal: Descarga PorcVoluUtilDiar/Sistema de XM e inserta en PostgreSQL.
Ejecutar una vez para poblar la métrica precalculada de XM.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime, timedelta
from pydataxm.pydataxm import ReadDB
from infrastructure.database.manager import db_manager

METRICA = 'PorcVoluUtilDiar'
ENTIDAD = 'Sistema'
UNIDAD = '%'
DIAS = 30  # últimos 30 días

def main():
    print(f"📡 Descargando {METRICA}/{ENTIDAD} de XM...")
    api = ReadDB()
    
    fecha_fin = datetime.now().date() - timedelta(days=1)
    fecha_inicio = fecha_fin - timedelta(days=DIAS)
    
    df = api.request_data(METRICA, ENTIDAD, str(fecha_inicio), str(fecha_fin))
    
    if df is None or df.empty:
        print("❌ Sin datos de API")
        return
    
    print(f"✅ API devolvió {len(df)} filas")
    print(f"📋 Columnas: {df.columns.tolist()}")
    print(df.head())
    
    # Preparar datos para inserción
    registros = []
    for _, row in df.iterrows():
        fecha = row.get('Date')
        if fecha is None:
            continue
        # Asegurar formato fecha
        if hasattr(fecha, 'strftime'):
            fecha_str = fecha.strftime('%Y-%m-%d')
        else:
            fecha_str = str(fecha)[:10]
        
        valor = row.get('Value')
        if valor is None or pd.isna(valor):
            continue
        
        # PorcVoluUtilDiar viene como fracción 0-1 (según scripts existentes)
        # pero también podría venir como porcentaje. Verificamos:
        valor_float = float(valor)
        if valor_float > 1:
            # Si viene como 62.73, convertir a fracción 0.6273
            valor_float = valor_float / 100.0
        
        registros.append((fecha_str, METRICA, ENTIDAD, ENTIDAD, valor_float, UNIDAD))
    
    if not registros:
        print("⚠️ No se generaron registros válidos")
        return
    
    print(f"📥 Insertando {len(registros)} registros...")
    insertados = db_manager.upsert_metrics_bulk(registros)
    print(f"✅ {insertados} registros insertados/actualizados")
    
    # Verificar
    df_check = db_manager.query_df(
        "SELECT fecha::date, valor_gwh FROM metrics WHERE metrica = %s AND entidad = %s ORDER BY fecha DESC LIMIT 5",
        params=(METRICA, ENTIDAD)
    )
    if df_check is not None and not df_check.empty:
        print("\n📊 Últimos datos en BD:")
        print(df_check)

if __name__ == '__main__':
    main()

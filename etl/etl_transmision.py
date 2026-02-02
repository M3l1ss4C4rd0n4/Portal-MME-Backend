#!/usr/bin/env python3
"""
ETL para Líneas de Transmisión
Descarga datos desde SIMEM API y los almacena en SQLite

Uso:
    python3 etl/etl_transmision.py [--days DAYS] [--clean]
    
Opciones:
    --days DAYS    Días hacia atrás para descargar (default: 7)
    --clean        Limpia datos antiguos (>90 días)
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pydataxm.pydatasimem import ReadSIMEM
import pandas as pd
from infrastructure.database.repositories.transmission_repository import TransmissionRepository


def fetch_transmission_data(days_back: int = 7) -> pd.DataFrame:
    """
    Descarga datos de transmisión desde SIMEM API
    
    Args:
        days_back: Días hacia atrás para descargar
        
    Returns:
        DataFrame con datos de líneas
    """
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        print(f"📡 Descargando datos SIMEM desde {start_date} hasta {end_date}...")
        print("🔄 Dataset: 7538fd (Parámetros técnicos de líneas de transmisión)")
        
        # Dataset 7538fd: Parámetros técnicos de líneas de transmisión
        reader = ReadSIMEM('7538fd', start_date, end_date)
        df = reader.main()
        
        if df is None or df.empty:
            print("⚠️ SIMEM API retornó DataFrame vacío")
            return pd.DataFrame()
        
        print(f"✅ Descargados {len(df)} registros")
        
        # Convertir fechas
        df['Fecha'] = pd.to_datetime(df['Fecha'])
        df['FechaPublicacion'] = pd.to_datetime(df['FechaPublicacion'])
        if 'FPO' in df.columns:
            df['FPO'] = pd.to_datetime(df['FPO'], errors='coerce')
        
        return df
        
    except Exception as e:
        print(f"❌ Error descargando datos SIMEM: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def run_etl(days_back: int = 7, clean_old: bool = False):
    """
    Ejecuta el proceso ETL completo
    
    Args:
        days_back: Días hacia atrás para descargar
        clean_old: Si es True, elimina datos antiguos
    """
    print("=" * 60)
    print("ETL TRANSMISIÓN - Líneas de Transmisión Nacional")
    print("=" * 60)
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 1. Descargar datos
    df = fetch_transmission_data(days_back)
    
    if df.empty:
        print("❌ No se pudieron descargar datos. ETL abortado.")
        return False
    
    # 2. Insertar en DB
    try:
        repo = TransmissionRepository()
        
        print(f"💾 Insertando {len(df)} registros en SQLite...")
        inserted = repo.bulk_insert_lines(df)
        print(f"✅ Insertados {inserted} registros nuevos (duplicados omitidos)")
        
        # 3. Limpieza (opcional)
        if clean_old:
            print("🧹 Limpiando datos antiguos (>90 días)...")
            deleted = repo.delete_old_data(days_to_keep=90)
            print(f"✅ Eliminados {deleted} registros antiguos")
        
        # 4. Estadísticas finales
        total_lines = repo.get_total_lines()
        latest_date = repo.get_latest_date()
        
        print()
        print("=" * 60)
        print("RESUMEN")
        print("=" * 60)
        print(f"Total líneas únicas en DB: {total_lines}")
        print(f"Fecha más reciente: {latest_date}")
        print(f"Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ Error en ETL: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='ETL para Líneas de Transmisión')
    parser.add_argument('--days', type=int, default=7, help='Días hacia atrás para descargar (default: 7)')
    parser.add_argument('--clean', action='store_true', help='Limpia datos antiguos (>90 días)')
    
    args = parser.parse_args()
    
    success = run_etl(days_back=args.days, clean_old=args.clean)
    sys.exit(0 if success else 1)

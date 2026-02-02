
import sys
import os
import logging
import pandas as pd
from datetime import datetime, timedelta

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydataxm.pydataxm import ReadDB
from infrastructure.database.manager import db_manager

logging.basicConfig(level=logging.INFO)

def backfill():
    api = ReadDB()
    metrics = ['PerdidasEner', 'PerdidasEnerReg', 'PerdidasEnerNoReg']
    entity = 'Sistema'
    days = 180
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    logging.info(f"Backfilling {metrics} for {days} days")
    
    for metric in metrics:
        df = api.request_data(metric, entity, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        if df is None or df.empty: continue
            
        hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
        existing_cols = [col for col in hour_cols if col in df.columns]
        
        if existing_cols:
            # Perdidas is in kWh -> Sum -> / 1M => GWh
            df['Value'] = df[existing_cols].sum(axis=1) / 1_000_000
        
        records = []
        for _, row in df.iterrows():
            date_str = str(row['Date'])[:10]
            val = float(row['Value'])
            records.append((date_str, metric, entity, 'Sistema', val, 'GWh'))
            
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany("INSERT OR REPLACE INTO metrics (fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))", records)
            conn.commit()
            logging.info(f"Inserted {len(records)} for {metric}")

if __name__ == "__main__":
    backfill()

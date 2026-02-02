
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
    metrics = ['RestAliv', 'RestSinAliv', 'RespComerAGC']
    entity = 'Sistema'
    days = 180  # Backfill 6 months
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    logging.info(f"Backfilling {metrics} for {days} days ({start_date.date()} to {end_date.date()})")
    
    for metric in metrics:
        logging.info(f"Downloading {metric}...")
        df = api.request_data(metric, entity, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        
        if df is None or df.empty:
            logging.warning(f"No data for {metric}")
            continue
            
        logging.info(f"Downloaded {len(df)} rows. Processing...")
        
        # SUM HOURS Logic
        hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
        existing_cols = [col for col in hour_cols if col in df.columns]
        
        if existing_cols:
            # SUM VALUES (COP)
            df['Value'] = df[existing_cols].sum(axis=1)
            # DO NOT DIVIDE BY 1M because Dashboard expects raw COP
        else:
            logging.warning(f"No hourly columns for {metric}. Using default Value column if exists.")
            # If default Value exists, assume it is correct
        
        # Prepare for DB
        records = []
        for _, row in df.iterrows():
            date_str = str(row['Date'])[:10]
            val = float(row['Value'])
            
            # Recurso logic: Normalize to 'Sistema' for clarity or match DB
            # DB has Mixed '_SISTEMA_' and 'Sistema'.
            # Let's standardize on 'Sistema' to distinguish from old bad data.
            recurso = 'Sistema'
            
            records.append((
                date_str,
                metric,
                entity,
                recurso,
                val,
                'COP' # Unit
            ))
            
        # Insert
        if records:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany("""
                    INSERT OR REPLACE INTO metrics 
                    (fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, records)
                conn.commit()
            logging.info(f"Inserted {len(records)} records for {metric}")

if __name__ == "__main__":
    backfill()

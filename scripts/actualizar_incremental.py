#!/usr/bin/env python3
"""
Actualización incremental del ETL - Solo datos nuevos desde última fecha en BD
Usa las MISMAS conversiones que etl_xm_to_sqlite.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
from datetime import datetime, timedelta
# from utils._xm import get_objetoAPI  <-- REEMPLAZADO
from infrastructure.external.xm_service import XMService
# from utils.db_manager import upsert_metrics_bulk <-- REEMPLAZADO
from infrastructure.database.manager import DatabaseManager
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Configuración de conversiones (debe coincidir con etl/config_metricas.py)
CONVERSION_CONFIG = {
    'VoluUtilDiarEner': 'kWh_a_GWh',  # API devuelve en kWh
    'CapaUtilDiarEner': 'kWh_a_GWh',  # API devuelve en kWh
    'AporEner': 'Wh_a_GWh',           # API devuelve en Wh
    'AporEnerMediHist': 'Wh_a_GWh',   # API devuelve en Wh
    'Gene': 'horas_a_diario',         # Sumar Values_Hour01-24 en kWh → GWh
    'DemaCome': 'horas_a_diario'      # Sumar Values_Hour01-24 en kWh → GWh
}

def convertir_valor(df, metrica, valor):
    """
    Convierte el valor según el tipo de métrica usando las reglas del ETL original
    
    Conversiones:
    - Wh_a_GWh: Divide por 1,000,000 (no 1e9)
    - kWh_a_GWh: Divide por 1,000,000 (no 1e9)
    - horas_a_diario: Suma Values_Hour01-24 y divide por 1,000,000
    """
    conversion = CONVERSION_CONFIG.get(metrica)
    
    if conversion == 'Wh_a_GWh':
        return valor / 1_000_000  # Wh → GWh
    elif conversion == 'kWh_a_GWh':
        return valor / 1_000_000  # kWh → GWh
    elif conversion == 'horas_a_diario':
        # Si el DataFrame tiene columnas Values_Hour*, sumarlas
        hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
        existing_cols = [col for col in hour_cols if col in df.columns]
        if existing_cols:
            # Retornar None para indicar que se debe sumar después
            return None
        else:
            # Si no hay columnas horarias, convertir el valor directo
            return valor / 1_000_000
    else:
        # Sin conversión, retornar el valor original
        return valor

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'portal_energetico.db')

def obtener_ultima_fecha(metrica, entidad):
    """Obtiene la última fecha disponible en BD para una métrica"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(fecha) FROM metrics 
            WHERE metrica = ? AND entidad = ?
        """, (metrica, entidad))
        result = cursor.fetchone()[0]
        conn.close()
        return result
    except:
        return None

def actualizar_metrica(xm_service, metrica, entidad, nombre):
    """Actualiza una métrica específica desde última fecha hasta hoy"""
    logger.info(f"\n{'='*60}")
    logger.info(f"📡 {nombre} ({metrica}/{entidad})")
    logger.info(f"{'='*60}")
    
    # Obtener última fecha en BD
    ultima_fecha_str = obtener_ultima_fecha(metrica, entidad)
    
    if ultima_fecha_str:
        ultima_fecha = datetime.strptime(ultima_fecha_str, '%Y-%m-%d').date()
        fecha_inicio = ultima_fecha - timedelta(days=3)  # 3 días de overlap por seguridad
        logger.info(f"   Última fecha en BD: {ultima_fecha}")
    else:
        # Si no hay datos, traer últimos 7 días
        fecha_inicio = datetime.now().date() - timedelta(days=7)
        logger.info(f"   Sin datos previos, trayendo últimos 7 días")
    
    fecha_fin = datetime.now().date()
    
    logger.info(f"   Rango: {fecha_inicio} a {fecha_fin}")
    
    try:
        df = xm_service.request_data(
            metrica, 
            entidad,
            fecha_inicio.strftime('%Y-%m-%d'),
            fecha_fin.strftime('%Y-%m-%d')
        )
        
        if df is None or df.empty:
            logger.warning(f"   ⚠️  Sin datos disponibles")
            return 0
        
        # Preparar datos para inserción
        metrics_data = []
        
        # Para métricas con horas, sumar primero
        conversion = CONVERSION_CONFIG.get(metrica)
        if conversion == 'horas_a_diario':
            hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
            existing_cols = [col for col in hour_cols if col in df.columns]
            
            if existing_cols:
                # Sumar todas las horas por fila
                df_processed = df.copy()
                df_processed['Value'] = df_processed[existing_cols].sum(axis=1) / 1_000_000  # kWh → GWh
                logger.info(f"   ✅ Sumadas {len(existing_cols)} horas, promedio: {df_processed['Value'].mean():.2f} GWh")
                df = df_processed
        
        for _, row in df.iterrows():
            fecha = row['Date'] if isinstance(row['Date'], str) else row['Date'].strftime('%Y-%m-%d')
            
            # Obtener valor crudo
            valor_raw = row.get('Value', 0)
            
            # Detectar recurso: priorizar Name (embalses), luego Values_code, luego _SISTEMA_
            if 'Name' in df.columns and pd.notna(row.get('Name')):
                recurso_val = row['Name']
            elif 'Values_code' in df.columns and pd.notna(row.get('Values_code')):
                recurso_val = row['Values_code']
            else:
                recurso_val = '_SISTEMA_'
            
            # Convertir usando la función correcta
            valor_convertido = convertir_valor(df, metrica, valor_raw)
            
            # Si la función retorna None, significa que ya se procesó en el paso anterior
            if valor_convertido is None:
                valor_convertido = valor_raw  # Ya está convertido en el DataFrame
            
            metrics_data.append((fecha, metrica, entidad, recurso_val, valor_convertido, 'GWh'))
        
        # Insertar en BD
        db = DatabaseManager()
        registros = db.upsert_metrics_bulk(metrics_data)
        logger.info(f"   ✅ {registros} registros actualizados")
        
        # Mostrar rango de fechas actualizado
        if 'Date' in df.columns:
            fecha_min = df['Date'].min()
            fecha_max = df['Date'].max()
            logger.info(f"   📅 Rango actualizado: {fecha_min} a {fecha_max}")
        
        return registros
        
    except Exception as e:
        logger.error(f"   ❌ Error: {e}")
        return 0

def main():
    print("[DEBUG] INICIO main()")
    logger.info("\n" + "="*60)
    logger.info("⚡ ACTUALIZACIÓN INCREMENTAL - SOLO DATOS NUEVOS")
    logger.info("⚙️  Usando conversiones del ETL original:")
    logger.info("   • Wh → GWh: ÷ 1,000,000")
    logger.info("   • kWh → GWh: ÷ 1,000,000")
    logger.info("   • Horas → Diario: Sumar 24 horas")
    logger.info("="*60)
    logger.info(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print("[DEBUG] Antes de XMService()")
    api = XMService()
    print("[DEBUG] Después de XMService()")

    metricas = [
        ('VoluUtilDiarEner', 'Embalse', 'Volumen Útil Diario (kWh→GWh)'),
        ('CapaUtilDiarEner', 'Embalse', 'Capacidad Útil Diario (kWh→GWh)'),
        ('AporEner', 'Sistema', 'Aportes Energía Sistema (Wh→GWh)'),
        ('AporEnerMediHist', 'Sistema', 'Aportes Media Histórica (Wh→GWh)'),
        ('Gene', 'Sistema', 'Generación Sistema (24h→GWh)'),
        ('DemaCome', 'Sistema', 'Demanda Comercial (24h→GWh)'),
    ]

    total_registros = 0
    for metrica, entidad, nombre in metricas:
        print(f"[DEBUG] Actualizando {metrica} / {entidad}")
        registros = actualizar_metrica(api, metrica, entidad, nombre)
        print(f"[DEBUG] Registros actualizados para {metrica}: {registros}")
        total_registros += registros

    logger.info("\n" + "="*60)
    logger.info(f"✅ ACTUALIZACIÓN COMPLETADA")
    logger.info(f"Total registros actualizados: {total_registros}")
    logger.info(f"Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)
    
    # Auto-corrección automática después de cada actualización
    logger.info("\n" + "="*60)
    logger.info("🔧 INICIANDO AUTO-CORRECCIÓN POST-ACTUALIZACIÓN")
    logger.info("⚠️ Auto-corrección deshabilitada temporalmente (módulo en legacy_archive)")
    logger.info("="*60)
    
    # try:
    #     # Importar y ejecutar auto-corrección
    #     from autocorreccion import AutoCorrector
    #     corrector = AutoCorrector(db_path=DB_PATH, dry_run=False)
    #     exito = corrector.ejecutar_todo()
    #     
    #     if exito:
    #         logger.info("✅ Auto-corrección completada exitosamente")
    #     else:
    #         logger.warning("⚠️ Auto-corrección completada con advertencias")
    # except Exception as e:
    #     logger.error(f"❌ Error en auto-corrección: {e}")
    #     logger.info("⚠️ Continuando sin auto-corrección (actualización fue exitosa)")

if __name__ == '__main__':
    main()

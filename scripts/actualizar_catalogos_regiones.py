#!/usr/bin/env python3
"""
Script para actualizar la columna 'region' en la tabla catalogos
con datos de la API XM (ListadoEmbalses y ListadoRios)
"""
import sys
import os
from pathlib import Path

# Agregar path del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import db_manager
from utils._xm import obtener_datos_inteligente
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def actualizar_regiones_embalses():
    """Actualizar región de embalses desde API XM"""
    try:
        logger.info("🔄 Obteniendo datos de ListadoEmbalses desde API XM...")
        
        # Usar fechas recientes
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Obtener datos desde SQLite/API
        df, warning = obtener_datos_inteligente('ListadoEmbalses', 'Sistema', yesterday, today)
        
        if df is None or df.empty:
            logger.error("❌ No se pudieron obtener datos de ListadoEmbalses")
            return False
        
        # Verificar columnas necesarias
        if 'Values_Name' not in df.columns or 'Values_HydroRegion' not in df.columns:
            logger.error(f"❌ Columnas faltantes. Disponibles: {df.columns.tolist()}")
            return False
        
        logger.info(f"✅ Datos obtenidos: {len(df)} embalses")
        
        # Normalizar datos
        df['Values_Name'] = df['Values_Name'].str.strip().str.upper()
        df['Values_HydroRegion'] = df['Values_HydroRegion'].str.strip().str.title()
        
        # Actualizar cada embalse en la base de datos
        actualizados = 0
        errores = 0
        
        import sqlite3
        conn = sqlite3.connect(str(db_manager.DB_PATH))
        cursor = conn.cursor()
        
        for _, row in df.iterrows():
            codigo = row['Values_Name']
            region = row['Values_HydroRegion']
            
            if not codigo or not region:
                continue
            
            try:
                # Insertar o actualizar región en catalogos
                cursor.execute("""
                    INSERT INTO catalogos (catalogo, codigo, nombre, tipo, region, fecha_actualizacion)
                    VALUES ('ListadoEmbalses', ?, ?, 'EMBALSE', ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(catalogo, codigo) DO UPDATE SET
                        region = excluded.region,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                """, (codigo, codigo, region))
                
                actualizados += 1
                logger.debug(f"✅ Insertado/Actualizado: {codigo} -> {region}")
            except Exception as e:
                errores += 1
                logger.error(f"❌ Error actualizando {codigo}: {e}")
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Actualización completada: {actualizados} embalses actualizados, {errores} errores")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en actualizar_regiones_embalses: {e}")
        import traceback
        traceback.print_exc()
        return False


def actualizar_regiones_rios():
    """Actualizar región de ríos desde API XM"""
    try:
        logger.info("🔄 Obteniendo datos de ListadoRios desde API XM...")
        
        # Usar fechas recientes
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Obtener datos desde SQLite/API
        df, warning = obtener_datos_inteligente('ListadoRios', 'Sistema', yesterday, today)
        
        if df is None or df.empty:
            logger.error("❌ No se pudieron obtener datos de ListadoRios")
            return False
        
        # Verificar columnas necesarias
        if 'Values_Name' not in df.columns or 'Values_HydroRegion' not in df.columns:
            logger.error(f"❌ Columnas faltantes. Disponibles: {df.columns.tolist()}")
            return False
        
        logger.info(f"✅ Datos obtenidos: {len(df)} ríos")
        
        # Normalizar datos
        df['Values_Name'] = df['Values_Name'].str.strip().str.upper()
        df['Values_HydroRegion'] = df['Values_HydroRegion'].str.strip().str.title()
        
        # Actualizar cada río en la base de datos
        actualizados = 0
        errores = 0
        
        import sqlite3
        conn = sqlite3.connect(str(db_manager.DB_PATH))
        cursor = conn.cursor()
        
        for _, row in df.iterrows():
            codigo = row['Values_Name']
            region = row['Values_HydroRegion']
            
            if not codigo or not region:
                continue
            
            try:
                # Insertar o actualizar región en catalogos
                cursor.execute("""
                    INSERT INTO catalogos (catalogo, codigo, nombre, tipo, region, fecha_actualizacion)
                    VALUES ('ListadoRios', ?, ?, 'RIO', ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(catalogo, codigo) DO UPDATE SET
                        region = excluded.region,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                """, (codigo, codigo, region))
                
                actualizados += 1
                logger.debug(f"✅ Insertado/Actualizado: {codigo} -> {region}")
            except Exception as e:
                errores += 1
                logger.error(f"❌ Error actualizando {codigo}: {e}")
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Actualización completada: {actualizados} ríos actualizados, {errores} errores")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en actualizar_regiones_rios: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("ACTUALIZACIÓN DE REGIONES EN CATÁLOGOS")
    print("=" * 60)
    
    # Actualizar embalses
    print("\n1. Actualizando regiones de EMBALSES...")
    exito_embalses = actualizar_regiones_embalses()
    
    # Actualizar ríos
    print("\n2. Actualizando regiones de RÍOS...")
    exito_rios = actualizar_regiones_rios()
    
    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Embalses: {'✅ OK' if exito_embalses else '❌ ERROR'}")
    print(f"Ríos: {'✅ OK' if exito_rios else '❌ ERROR'}")
    
    if exito_embalses and exito_rios:
        print("\n✅ TODAS LAS ACTUALIZACIONES COMPLETADAS EXITOSAMENTE")
        sys.exit(0)
    else:
        print("\n❌ HUBO ERRORES EN LA ACTUALIZACIÓN")
        sys.exit(1)

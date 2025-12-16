#!/usr/bin/env python3
"""
ETL COMPLETO: Descarga TODAS las métricas de XM (193 métricas)
================================================================

Este script consulta la API de XM, obtiene la lista completa de métricas
disponibles y las descarga todas a la base de datos SQLite.

Uso:
    python3 etl/etl_todas_metricas_xm.py [--dias 90] [--solo-nuevas]
    
Argumentos:
    --dias: Número de días de historia (default: 90)
    --solo-nuevas: Solo descargar métricas que no están en BD
    --metrica: Descargar solo una métrica específica
    --seccion: Descargar solo métricas de una sección específica
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydataxm.pydataxm import ReadDB
from datetime import datetime, timedelta
import time
import logging
import pandas as pd
import argparse
import sqlite3
from utils import db_manager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

DB_PATH = '/home/admonctrlxm/server/portal_energetico.db'

# Clasificación de métricas por sección
METRICAS_POR_SECCION = {
    'Generación': ['Gene', 'GeneIdea', 'GeneProgDesp', 'GeneProgRedesp', 'GeneFueraMerito', 
                   'GeneSeguridad', 'CapEfecNeta', 'ENFICC', 'ObligEnerFirme', 'DDVContratada',
                   'CapaTeoHidroNacion', 'CapaEfecPorRecDesp', 'CapaDispoReduObli'],
    'Demanda': ['DemaReal', 'DemaCome', 'DemaRealReg', 'DemaRealNoReg', 'DemaComeReg', 
                'DemaComeNoReg', 'DemaSIN', 'DemaMaxPot', 'DemaNoAtenProg', 'DemaNoAtenNoProg', 
                'DemaOR', 'DemaNOOR', 'DemaProgRegu', 'DemaProgNoRegu', 'DemaTotalBolsa',
                'RecuMeReguMora', 'RecuMeNoReguMora', 'RecuMeMoraTotal', 'GranConsPrecRegu',
                'GranConsPromNoRegu', 'ValorDemandaProgDesp'],
    'Transmisión': ['DispoReal', 'DispoCome', 'DispoDeclarada', 'CargoUsoSTN', 'CargoUsoSTR'],
    'Restricciones': ['RestAliv', 'RestSinAliv', 'RentasCongestRestr', 'EjecGarantRestr', 
                      'DesvGenVariableDesp', 'DesvGenVariableRedesp'],
    'Precios': ['PrecBolsNaci', 'PrecBolsNaciTX1', 'PPPrecBolsNaci', 'PrecTransBolsa',
                'PrecPromCont', 'PrecPromContRegu', 'PrecPromContNoRegu',
                'PrecEsca', 'PrecEscaAct', 'PrecEscaMarg', 'PrecEscaPon',
                'PrecOferDesp', 'PrecOferIdeal', 'MaxPrecOferNal',
                'CostMargDesp', 'CostRecPos', 'CostRecNeg', 'PrecCargConf',
                'PrecPromBolsAgen', 'PromPondPrecBolsNaci', 'PrecDespIdealTX1',
                'PrecNudoCont', 'PrecContDeclaTX1'],
    'Transacciones': ['CompBolsNaciEner', 'VentBolsNaciEner', 'CompContEner', 'VentContEner',
                      'CompBolsaTIEEner', 'VentBolsaTIEEner', 'CompBolsaIntEner', 'VentBolsaIntEner',
                      'CompAcumBolsaNaci', 'VentAcumBolsaNaci', 'CompAcumBolsaTIE', 'VentAcumBolsaTIE',
                      'CompAcumBolsaInt', 'VentAcumBolsaInt', 'TransacFrontera', 'LiqContBilateral',
                      'IngresosContrato', 'CompContDeclaTX1', 'VentContDeclaTX1', 'TransInternNaci',
                      'CompNudoCont', 'VentNudoCont', 'CompGenCont', 'VentGenCont'],
    'Pérdidas': ['PerdidasEner', 'PerdidasEnerReg', 'PerdidasEnerNoReg',
                 'CompPerdiEner', 'CompPerdiReg', 'CompPerdiNoReg'],
    'Intercambios': ['ImpoEner', 'ExpoEner', 'SnTIEMerito', 'DeltaInt', 'ImpoMerito',
                     'ExpoMerito', 'ImpoCapacidad', 'ExpoCapacidad', 'TransFrontera',
                     'CapaTotalTIE', 'ImpoProgrTIE', 'ExpoProgrTIE', 'ImpoRealTIE', 'ExpoRealTIE', 'CapaDispoTIE'],
    'Hidrología': ['AporEner', 'VoluUtilDiarEner', 'CapaUtilDiarEner', 'VertEner',
                   'AporValorEner', 'VoluFinalMensEner', 'EneIndisp',
                   'AportHidricoMens', 'VolUtilesMens', 'VolUtilAgre',
                   'AportPorRecur', 'VolUtilPorRecur', 'MediaHist', 'PromediosAlDia',
                   'SeriesHistAport', 'AporMedioBasin', 'VolUtilBasin', 'AporAfluen',
                   'VolUtilAfluen', 'AporMedioAfluen', 'VolMedioAfluen', 'CotaEmbalse', 'NivelRio'],
    'Combustibles': ['ConsCombustibleMBTU', 'EmisionesCO2', 'factorEmisionCO2e',
                     'ConsGasKPCE', 'ConsCarbon', 'ConsJetA1', 'ConsFuelOil', 'ConsGasNatural'],
    'Renovables': ['IrrPanel', 'IrrGlobal', 'TempPanel', 'TempAmbSolar'],
    'Cargos': ['FAZNI', 'FAER', 'PRONE', 'CargoUsoSTN', 'CargoUsoSTR',
               'CargMaxTPrima', 'CargDistribu', 'CargComer', 'CargRestric',
               'CargConfiabili', 'CargAGC']
}

def obtener_todas_metricas_xm(obj_api):
    """Obtener lista completa de métricas disponibles en XM"""
    logging.info("📡 Consultando lista completa de métricas en API XM...")
    
    try:
        df_metricas = obj_api.all_variables()
        logging.info(f"✅ Encontradas {len(df_metricas)} métricas en XM")
        return df_metricas
    except Exception as e:
        logging.error(f"❌ Error al consultar métricas: {e}")
        return None

def obtener_metricas_en_bd():
    """Obtener lista de métricas que ya están en la base de datos"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT DISTINCT metrica FROM metrics"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return set(df['metrica'].tolist())
    except Exception as e:
        logging.error(f"❌ Error al consultar BD: {e}")
        return set()

def detectar_conversion(metric_id, entity):
    """Detectar tipo de conversión necesaria basado en el nombre de la métrica"""
    # Hidrología - datos en Wh
    if metric_id in ['AporEner', 'VoluUtilDiarEner', 'CapaUtilDiarEner', 'VertEner', 
                     'AporValorEner', 'VoluFinalMensEner', 'EneIndisp']:
        return 'Wh_a_GWh'
    
    # Disponibilidad - promedio horario
    if 'Dispo' in metric_id:
        return 'horas_a_MW'
    
    # Generación - suma horaria
    if 'Gene' in metric_id or metric_id in ['CapEfecNeta', 'CapaTeoHidroNacion']:
        return 'horas_a_GWh'
    
    # Demanda - suma horaria
    if 'Dema' in metric_id:
        return 'horas_a_GWh'
    
    # Precios, cargos - sin conversión
    if 'Prec' in metric_id or 'Cargo' in metric_id or 'Cost' in metric_id:
        return 'sin_conversion'
    
    # Transacciones - suma horaria generalmente
    if 'Comp' in metric_id or 'Vent' in metric_id or 'Trans' in metric_id:
        return 'horas_a_GWh'
    
    # Por defecto
    return 'sin_conversion'

def convertir_unidades(df, metric, conversion_type):
    """Convertir unidades de datos crudos de XM"""
    if df is None or df.empty:
        return df
    
    df = df.copy()
    
    try:
        if conversion_type == 'Wh_a_GWh':
            if 'Value' in df.columns:
                df['Value'] = df['Value'] / 1_000_000
                logging.info(f"  ✅ Convertido Wh → GWh")
        
        elif conversion_type == 'kWh_a_GWh':
            if 'Value' in df.columns:
                df['Value'] = df['Value'] / 1_000_000
                logging.info(f"  ✅ Convertido kWh → GWh")
        
        elif conversion_type == 'horas_a_MW':
            # Disponibilidad: Promediar valores horarios
            hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
            existing_cols = [col for col in hour_cols if col in df.columns]
            
            if existing_cols:
                df['Value'] = df[existing_cols].mean(axis=1) / 1_000  # kW → MW
                df = df.dropna(subset=['Value'])
                logging.info(f"  ✅ Promediado {len(existing_cols)} horas → MW")
            elif 'Value' in df.columns:
                df['Value'] = df['Value'] / 1_000
                logging.info(f"  ✅ Convertido kW → MW")
        
        elif conversion_type == 'horas_a_GWh':
            # Generación/Demanda: Sumar valores horarios
            hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
            existing_cols = [col for col in hour_cols if col in df.columns]
            
            if existing_cols:
                df['Value'] = df[existing_cols].sum(axis=1) / 1_000_000  # kWh → GWh
                df = df.dropna(subset=['Value'])
                logging.info(f"  ✅ Sumado {len(existing_cols)} horas → GWh")
            elif 'Value' in df.columns:
                df['Value'] = df['Value'] / 1_000_000
                logging.info(f"  ✅ Convertido kWh → GWh")
        
    except Exception as e:
        logging.warning(f"  ⚠️ Error en conversión: {e}")
    
    return df

def descargar_metrica(obj_api, metric_id, entity, dias_historia=90):
    """Descargar una métrica específica de XM"""
    fecha_fin = datetime.now() - timedelta(days=1)
    fecha_inicio = fecha_fin - timedelta(days=dias_historia)
    
    logging.info(f"\n{'='*70}")
    logging.info(f"📊 Métrica: {metric_id} | Entidad: {entity}")
    logging.info(f"📅 Período: {fecha_inicio.date()} → {fecha_fin.date()}")
    
    try:
        # Consultar API
        df = obj_api.request_data(
            metric_id,
            entity,
            start_date=fecha_inicio.strftime('%Y-%m-%d'),
            end_date=fecha_fin.strftime('%Y-%m-%d')
        )
        
        if df is None or df.empty:
            logging.warning(f"  ⚠️ Sin datos disponibles")
            return 0
        
        logging.info(f"  ✅ Descargados {len(df)} registros")
        
        # Detectar y aplicar conversión
        conversion = detectar_conversion(metric_id, entity)
        df = convertir_unidades(df, metric_id, conversion)
        
        if df.empty:
            logging.warning(f"  ⚠️ Sin datos después de conversión")
            return 0
        
        # Preparar datos para inserción
        registros = []
        
        # Detectar columnas relevantes
        fecha_col = 'Date' if 'Date' in df.columns else 'date'
        valor_col = 'Value'
        
        # Columnas de identificación (priorizar Name sobre Id)
        id_cols = []
        if 'Name' in df.columns:
            id_cols.append('Name')
        elif 'Code' in df.columns:
            id_cols.append('Code')
        elif 'Agent' in df.columns:
            id_cols.append('Agent')
        elif 'Id' in df.columns:
            id_cols.append('Id')
        
        for _, row in df.iterrows():
            # Recurso/Agente/Id
            recurso = None
            if id_cols:
                recurso = str(row[id_cols[0]]) if pd.notna(row[id_cols[0]]) else None
            
            # Fecha
            fecha = pd.to_datetime(row[fecha_col]).strftime('%Y-%m-%d')
            
            # Valor
            valor = float(row[valor_col]) if pd.notna(row[valor_col]) else None
            
            if valor is not None:
                registros.append({
                    'fecha': fecha,
                    'metrica': metric_id,
                    'entidad': entity,
                    'recurso': recurso,
                    'valor_gwh': valor
                })
        
        # Insertar en BD
        if registros:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            for reg in registros:
                cursor.execute("""
                    INSERT OR REPLACE INTO metrics 
                    (fecha, metrica, entidad, recurso, valor_gwh, fecha_actualizacion)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (reg['fecha'], reg['metrica'], reg['entidad'], 
                      reg['recurso'], reg['valor_gwh']))
            
            conn.commit()
            conn.close()
            
            logging.info(f"  💾 Insertados {len(registros)} registros en BD")
            return len(registros)
        else:
            logging.warning(f"  ⚠️ No hay registros para insertar")
            return 0
            
    except Exception as e:
        logging.error(f"  ❌ Error: {e}")
        return 0

def ejecutar_etl_completo(dias=90, solo_nuevas=False, metrica_especifica=None, seccion_especifica=None):
    """Ejecutar ETL completo de todas las métricas"""
    inicio = time.time()
    stats = {
        'total': 0,
        'exitosas': 0,
        'fallidas': 0,
        'sin_datos': 0,
        'registros': 0
    }
    
    logging.info("╔══════════════════════════════════════════════════════════════╗")
    logging.info("║     ETL COMPLETO - TODAS LAS MÉTRICAS XM → SQLite           ║")
    logging.info("╚══════════════════════════════════════════════════════════════╝")
    logging.info(f"📅 Días de historia: {dias}")
    logging.info(f"🔄 Solo nuevas: {'Sí' if solo_nuevas else 'No'}")
    
    # Conectar a API
    logging.info("\n🔌 Conectando a API XM...")
    obj_api = ReadDB()
    
    # Obtener lista completa de métricas
    df_metricas = obtener_todas_metricas_xm(obj_api)
    if df_metricas is None:
        logging.error("❌ No se pudo obtener lista de métricas")
        return
    
    # Filtrar por métrica específica
    if metrica_especifica:
        df_metricas = df_metricas[df_metricas['MetricId'] == metrica_especifica]
        logging.info(f"🎯 Filtrando por métrica: {metrica_especifica}")
    
    # Filtrar por sección
    if seccion_especifica and seccion_especifica in METRICAS_POR_SECCION:
        metricas_seccion = METRICAS_POR_SECCION[seccion_especifica]
        df_metricas = df_metricas[df_metricas['MetricId'].isin(metricas_seccion)]
        logging.info(f"📂 Filtrando por sección: {seccion_especifica} ({len(df_metricas)} métricas)")
    
    # Obtener métricas ya en BD
    if solo_nuevas:
        metricas_bd = obtener_metricas_en_bd()
        logging.info(f"📊 Métricas ya en BD: {len(metricas_bd)}")
        df_metricas = df_metricas[~df_metricas['MetricId'].isin(metricas_bd)]
        logging.info(f"🆕 Métricas nuevas a descargar: {len(df_metricas)}")
    
    stats['total'] = len(df_metricas)
    
    # Procesar cada métrica
    for idx, row in df_metricas.iterrows():
        metric_id = row['MetricId']
        entity = row['Entity']
        
        registros = descargar_metrica(obj_api, metric_id, entity, dias)
        
        if registros > 0:
            stats['exitosas'] += 1
            stats['registros'] += registros
        elif registros == 0:
            stats['sin_datos'] += 1
        else:
            stats['fallidas'] += 1
        
        # Pausa entre métricas
        time.sleep(0.5)
    
    # Resumen
    tiempo_total = time.time() - inicio
    
    logging.info("\n╔══════════════════════════════════════════════════════════════╗")
    logging.info("║                    RESUMEN ETL COMPLETO                      ║")
    logging.info("╚══════════════════════════════════════════════════════════════╝")
    logging.info(f"📊 Total métricas procesadas: {stats['total']}")
    logging.info(f"  ✅ Exitosas (con datos): {stats['exitosas']}")
    logging.info(f"  ⚠️  Sin datos: {stats['sin_datos']}")
    logging.info(f"  ❌ Fallidas: {stats['fallidas']}")
    logging.info(f"💾 Total registros insertados: {stats['registros']:,}")
    logging.info(f"⏱️  Tiempo total: {tiempo_total:.1f} seg ({tiempo_total/60:.1f} min)")
    
    # Estadísticas de BD
    try:
        conn = sqlite3.connect(DB_PATH)
        df_stats = pd.read_sql_query("""
            SELECT 
                COUNT(*) as total_registros,
                COUNT(DISTINCT metrica) as metricas_unicas,
                COUNT(DISTINCT fecha) as dias_unicos,
                MIN(fecha) as fecha_min,
                MAX(fecha) as fecha_max
            FROM metrics
        """, conn)
        conn.close()
        
        logging.info(f"\n📈 Estadísticas de Base de Datos:")
        logging.info(f"  Total registros: {df_stats['total_registros'][0]:,}")
        logging.info(f"  Métricas únicas: {df_stats['metricas_unicas'][0]}")
        logging.info(f"  Días únicos: {df_stats['dias_unicos'][0]}")
        logging.info(f"  Rango: {df_stats['fecha_min'][0]} → {df_stats['fecha_max'][0]}")
    except Exception as e:
        logging.error(f"❌ Error al obtener estadísticas: {e}")
    
    logging.info(f"\n✅ ETL completado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ETL Completo: Todas las métricas XM')
    parser.add_argument('--dias', type=int, default=90, help='Días de historia (default: 90)')
    parser.add_argument('--solo-nuevas', action='store_true', help='Solo descargar métricas nuevas')
    parser.add_argument('--metrica', type=str, help='Descargar solo una métrica específica')
    parser.add_argument('--seccion', type=str, help='Descargar solo métricas de una sección',
                       choices=list(METRICAS_POR_SECCION.keys()))
    
    args = parser.parse_args()
    
    ejecutar_etl_completo(
        dias=args.dias,
        solo_nuevas=args.solo_nuevas,
        metrica_especifica=args.metrica,
        seccion_especifica=args.seccion
    )

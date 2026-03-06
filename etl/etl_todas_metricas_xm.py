#!/usr/bin/env python3
"""
ETL COMPLETO: Descarga TODAS las métricas de XM (193 métricas)
================================================================

Este script consulta la API de XM, obtiene la lista completa de métricas
disponibles y las descarga todas a la base de datos PostgreSQL.

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
import time
import logging
import argparse
from datetime import datetime, timedelta
import pandas as pd
from pydataxm.pydataxm import ReadDB

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.database.manager import db_manager

# Reglas centralizadas — fuente única de verdad para conversiones y unidades
from etl.etl_rules import (
    get_expected_unit,
    get_conversion_type as rules_get_conversion,
    validate_metric_df,
    ConversionType,
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
        query = "SELECT DISTINCT metrica FROM metrics"
        df = db_manager.query_df(query)
        if not df.empty:
            return set(df['metrica'].tolist())
        return set()
    except Exception as e:
        logging.error(f"❌ Error al consultar BD: {e}")
        return set()

def detectar_conversion(metric_id, entity):
    """Detectar tipo de conversión necesaria basado en el nombre de la métrica.
    
    NOTA: Primero consulta las reglas centralizadas (etl_rules.py).
    Si la métrica tiene regla, usa esa conversión.
    Si no, cae a la lógica local de pattern matching (legacy).
    """
    # ── Consultar reglas centralizadas primero ──
    conv_enum = rules_get_conversion(metric_id)
    if conv_enum != ConversionType.NONE or metric_id in (
        'PrecBolsNaci', 'PrecBolsNaciTX1', 'PrecOferDesp', 'PrecOferIdeal',
        'PrecEsca', 'PrecEscaAct', 'PrecEscaMarg', 'CostMargDesp',
        'PrecPromCont', 'MaxPrecOferNal', 'AporCaudal', 'AporCaudalMediHist',
        'VoluUtilDiarMasa', 'CapaUtilDiarMasa', 'CapEfecNeta', 'ConsCombustibleMBTU',
    ):
        # La métrica está en las reglas — usar su conversión
        from etl.etl_rules import get_rule
        rule = get_rule(metric_id)
        if rule is not None:
            return rule.conversion.value  # Retorna string compatible con convertir_unidades()
    
    # ── Fallback: lógica legacy de pattern matching ──
    # Hidrología - datos en Wh (incluye medias históricas y series)
    if metric_id in ['AporEner', 'VoluUtilDiarEner', 'CapaUtilDiarEner', 'VertEner', 
                     'AporValorEner', 'VoluFinalMensEner', 'EneIndisp',
                     'AporEnerMediHist', 'AportHidricoMens', 'VolUtilesMens', 'VolUtilAgre',
                     'SeriesHistAport', 'MediaHist', 'PromediosAlDia']:
        return 'Wh_a_GWh'
    
    # Energía firme y DDV - datos en kWh
    if metric_id in ['ENFICC', 'ObligEnerFirme', 'DDVContratada']:
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
    
    # Restricciones - promedio $/kWh → Millones COP
    if metric_id in ['RestAliv', 'RestSinAliv']:
        return 'restricciones_a_MCOP'
    
    # Responsabilidad AGC y garantías - COP diario → Millones COP
    if metric_id in ['RespComerAGC', 'EjecGarantRestr', 'RentasCongestRestr',
                     'DesvMoneda', 'RecoNegMoneda', 'RecoPosMoneda',
                     'ComContRespEner', 'RemuRealIndiv', 'FAZNI']:
        return 'COP_a_MCOP'
    
    # Desviaciones energía - kWh → GWh
    if metric_id in ['DesvEner', 'RecoNegEner', 'RecoPosEner',
                     'DesvGenVariableDesp', 'DesvGenVariableRedesp']:
        return 'Wh_a_GWh'
    
    # Precios, cargos - sin conversión (ya vienen en $/kWh)
    if 'Prec' in metric_id or 'Cargo' in metric_id or 'Cost' in metric_id:
        return 'sin_conversion'
    
    # Transacciones - suma horaria generalmente
    if 'Comp' in metric_id or 'Vent' in metric_id or 'Trans' in metric_id:
        return 'horas_a_GWh'
    
    # Pérdidas - suma horaria (kWh -> GWh)
    if 'Perdidas' in metric_id:
        return 'horas_a_GWh'
    
    # Por defecto
    return 'sin_conversion'

def convertir_unidades(df, metric, conversion_type):
    """Convertir unidades de datos crudos de XM"""
    if df is None or df.empty:
        return df
    
    df = df.copy()

    # Normalizar nombre de columna value si viene en minúscula
    if 'Value' not in df.columns and 'value' in df.columns:
        df['Value'] = df['value']
    
    try:
        if conversion_type == 'Wh_a_GWh':
            if 'Value' in df.columns:
                df['Value'] = df['Value'] / 1_000_000
                logging.info(f"  ✅ Convertido Wh → GWh")
        
        elif conversion_type == 'kWh_a_GWh':
            if 'Value' in df.columns:
                df['Value'] = df['Value'] / 1_000_000
                logging.info(f"  ✅ Convertido kWh → GWh")
        
        elif conversion_type == 'restricciones_a_MCOP':
            # ✅ FIX CRÍTICO: Restricciones vienen en $/kWh horario
            # Promediar 24 horas y convertir a Millones COP
            hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
            existing_cols = [col for col in hour_cols if col in df.columns]
            
            if existing_cols:
                df['Value'] = df[existing_cols].mean(axis=1) / 1_000_000  # → Millones COP
                df = df.dropna(subset=['Value'])
                logging.info(f"  ✅ Promediado 24h: $/kWh → Millones COP")
            elif 'Value' in df.columns:
                df['Value'] = df['Value'] / 1_000_000
                logging.info(f"  ✅ Convertido $/kWh → Millones COP")
        
        elif conversion_type == 'COP_a_MCOP':
            # Valores monetarios diarios en COP → Millones COP
            if 'Value' in df.columns:
                df['Value'] = df['Value'] / 1_000_000
                logging.info(f"  ✅ Convertido COP → Millones COP")
            else:
                # Si viene con columnas horarias, sumar y convertir
                hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
                existing_cols = [col for col in hour_cols if col in df.columns]
                if existing_cols:
                    df['Value'] = df[existing_cols].sum(axis=1) / 1_000_000
                    df = df.dropna(subset=['Value'])
                    logging.info(f"  ✅ Sumado {len(existing_cols)} horas COP → Millones COP")
        
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


def asegurar_columna_valor(df, conversion_type):
    """Asegura que exista columna 'Value' para el ETL"""
    if df is None or df.empty:
        return df

    df = df.copy()

    # Normalizar nombre
    if 'Value' not in df.columns and 'value' in df.columns:
        df['Value'] = df['value']

    if 'Value' in df.columns:
        return df

    # Intentar derivar desde columnas horarias
    hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
    existing_cols = [col for col in hour_cols if col in df.columns]

    if not existing_cols:
        return df

    if conversion_type == 'horas_a_MW':
        df['Value'] = df[existing_cols].mean(axis=1) / 1_000
        logging.info(f"  ✅ Derivado Value desde horas (MW)")
    elif conversion_type in ['horas_a_GWh', 'Wh_a_GWh', 'kWh_a_GWh']:
        df['Value'] = df[existing_cols].sum(axis=1) / 1_000_000
        logging.info(f"  ✅ Derivado Value desde horas (GWh)")
    elif conversion_type == 'COP_a_MCOP':
        df['Value'] = df[existing_cols].sum(axis=1) / 1_000_000
        logging.info(f"  ✅ Derivado Value desde horas (Millones COP)")
    elif conversion_type == 'restricciones_a_MCOP':
        df['Value'] = df[existing_cols].mean(axis=1) / 1_000_000
        logging.info(f"  ✅ Derivado Value desde horas restricciones (Millones COP)")
    else:
        df['Value'] = df[existing_cols].mean(axis=1)
        logging.info(f"  ✅ Derivado Value desde horas (promedio)")

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
        df = asegurar_columna_valor(df, conversion)
        
        if df.empty:
            logging.warning(f"  ⚠️ Sin datos después de conversión")
            return 0
        
        # ✅ FIX: Determinar unidad desde reglas centralizadas (fallback a lógica local)
        unidad = get_expected_unit(metric_id)
        if unidad is None:
            # Fallback para métricas sin regla definida
            if conversion in ['restricciones_a_MCOP', 'COP_a_MCOP']:
                unidad = 'Millones COP'
            elif conversion in ['Wh_a_GWh', 'horas_a_GWh', 'kWh_a_GWh']:
                unidad = 'GWh'
            elif conversion == 'horas_a_MW':
                unidad = 'MW'
            else:
                unidad = None
        
        # ✅ VALIDACIÓN PRE-INSERT: verificar datos antes de insertar en BD
        if 'Value' in df.columns or 'value' in df.columns:
            v_col = 'Value' if 'Value' in df.columns else 'value'
            df_check = df.copy()
            df_check['valor_gwh'] = df_check[v_col]
            df_check['unidad'] = unidad
            issues = validate_metric_df(df_check, metric_id, value_col='valor_gwh', unit_col='unidad')
            for issue in issues:
                if issue.startswith("ERROR"):
                    logging.error(f"  🛑 {issue}")
                else:
                    logging.warning(f"  ⚠️ {issue}")
            # Solo bloquear inserción por errores de UNIDAD (no por rangos/warnings)
            error_criticos = [i for i in issues if i.startswith("ERROR UNIDAD")]
            if error_criticos:
                logging.error(f"  🛑 Inserción BLOQUEADA para {metric_id}: error de unidad crítico")
                return 0
        
        # Preparar datos para inserción
        registros = []
        
        # Detectar columnas relevantes
        if 'Date' in df.columns:
            fecha_col = 'Date'
        elif 'date' in df.columns:
            fecha_col = 'date'
        elif 'Fecha' in df.columns:
            fecha_col = 'Fecha'
        else:
            logging.warning("  ⚠️ No se encontró columna de fecha")
            return 0

        if 'Value' in df.columns:
            valor_col = 'Value'
        elif 'value' in df.columns:
            valor_col = 'value'
        else:
            logging.warning("  ⚠️ No se encontró columna de valor")
            return 0
        
        # Columnas de identificación (priorizar Values_code para distinguir agentes individuales)
        id_cols = []
        if 'Values_code' in df.columns:
            id_cols.append('Values_code')  # AAGG, ASCC, etc. para Agente; "Sistema" para Sistema
        elif 'Name' in df.columns:
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
                    'valor_gwh': valor,
                    'unidad': unidad  # ✅ FIX: Incluir unidad
                })
        
        # Insertar en BD
        if registros:
            try:
                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    data_tuples = [(
                        reg['fecha'], 
                        reg['metrica'], 
                        reg['entidad'], 
                        reg['recurso'], 
                        reg['valor_gwh'],
                        reg['unidad']
                    ) for reg in registros]
                    
                    cursor.executemany("""
                        INSERT INTO metrics 
                        (fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion)
                        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (fecha, metrica, entidad, recurso) 
                        DO UPDATE SET 
                            valor_gwh = EXCLUDED.valor_gwh,
                            unidad = EXCLUDED.unidad,
                            fecha_actualizacion = CURRENT_TIMESTAMP
                    """, data_tuples)
                    
                    conn.commit()
                
                logging.info(f"  💾 Insertados {len(registros)} registros en BD")
                return len(registros)
            except Exception as e:
                logging.error(f"  ❌ Error insertando en BD: {e}")
                return 0
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
    logging.info("║     ETL COMPLETO - TODAS LAS MÉTRICAS XM → PostgreSQL       ║")
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
        query_stats = """
            SELECT 
                COUNT(*) as total_registros,
                COUNT(DISTINCT metrica) as metricas_unicas,
                COUNT(DISTINCT fecha) as dias_unicos,
                MIN(fecha) as fecha_min,
                MAX(fecha) as fecha_max
            FROM metrics
        """
        df_stats = db_manager.query_df(query_stats)
        
        if not df_stats.empty:
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

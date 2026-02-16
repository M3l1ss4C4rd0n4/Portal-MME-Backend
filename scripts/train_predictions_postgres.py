#!/usr/bin/env python3
"""
Script de Entrenamiento y Generación de Predicciones - PostgreSQL
Sistema ENSEMBLE: Prophet + SARIMA + Validación Estadística
FASE 2 - Modelos ML Reales para Portal Energético MME

Objetivo: Predicciones precisas (MAPE < 5%) para planificación nacional
Horizonte: 3 meses (90 días)
Fuentes: Hidráulica, Térmica, Eólica, Solar, Biomasa

IMPORTANTE: Este script usa PostgreSQL en lugar de SQLite
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from prophet import Prophet
from pmdarima import auto_arima
from statsmodels.tsa.statespace.sarimax import SARIMAX
from sklearn.metrics import mean_absolute_percentage_error
import warnings
warnings.filterwarnings('ignore')

HORIZONTE_DIAS = 90  # 3 meses
CONFIANZA = 0.95
MODELO_VERSION = 'ENSEMBLE_v1.0'

# Fuentes de generación
FUENTES = ['Hidráulica', 'Térmica', 'Eólica', 'Solar', 'Biomasa']


def get_postgres_connection():
    """Obtiene conexión a PostgreSQL usando el connection manager del sistema"""
    from infrastructure.database.connection import PostgreSQLConnectionManager
    manager = PostgreSQLConnectionManager()
    # Crear conexión sin context manager para pandas
    conn_params = {
        'host': manager.host,
        'port': manager.port,
        'database': manager.database,
        'user': manager.user
    }
    if manager.password:
        conn_params['password'] = manager.password
    return psycopg2.connect(**conn_params)


class PredictorEnsemble:
    """Predictor ENSEMBLE combinando Prophet y SARIMA"""
    
    def __init__(self, nombre_fuente):
        self.fuente = nombre_fuente
        self.modelo_prophet = None
        self.modelo_sarima = None
        self.pesos = {'prophet': 0.5, 'sarima': 0.5}  # Pesos iniciales
        self.metricas = {}
        
    def preparar_datos(self, df):
        """Prepara datos para entrenamiento"""
        # Para Prophet: ds (fecha), y (valor)
        df_prophet = df[['fecha', 'valor_gwh']].copy()
        df_prophet.columns = ['ds', 'y']
        
        # Para SARIMA: serie temporal con frecuencia diaria
        df_sarima = df.set_index('fecha')['valor_gwh'].asfreq('D')
        
        return df_prophet, df_sarima
    
    def entrenar_prophet(self, df_prophet):
        """Entrena modelo Prophet con componentes estacionales"""
        print(f"  → Entrenando Prophet para {self.fuente}...", flush=True)
        
        modelo = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            interval_width=CONFIANZA,
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10.0,
            mcmc_samples=0
        )
        
        import logging
        logging.getLogger('prophet').setLevel(logging.ERROR)
        logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
        
        modelo.fit(df_prophet)
        self.modelo_prophet = modelo
        
        print(f"    ✓ Prophet entrenado", flush=True)
        return modelo
    
    def entrenar_sarima(self, serie_sarima):
        """Entrena modelo SARIMA con auto-selección de parámetros"""
        print(f"  → Entrenando SARIMA para {self.fuente} (puede tardar)...", flush=True)
        
        try:
            modelo = auto_arima(
                serie_sarima,
                start_p=0, start_q=0,
                max_p=2, max_q=2,
                m=7,
                start_P=0, start_Q=0,
                max_P=1, max_Q=1,
                seasonal=True,
                d=None,
                D=1,
                trace=False,
                error_action='ignore',
                suppress_warnings=True,
                stepwise=True,
                n_jobs=-1
            )
            
            self.modelo_sarima = modelo
            print(f"    ✓ SARIMA entrenado: {modelo.order} x {modelo.seasonal_order}", flush=True)
            return modelo
            
        except Exception as e:
            print(f"    ⚠️  SARIMA falló: {e}. Usando solo Prophet.", flush=True)
            return None
    
    def validar_modelos(self, df_prophet, serie_sarima, dias_validacion=30):
        """Valida modelos con holdout y calcula pesos óptimos basados en MAPE real"""
        print(f"  → Validando modelos con holdout de {dias_validacion} días...", flush=True)
        
        import logging
        logging.getLogger('prophet').setLevel(logging.ERROR)
        logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
        
        # Split: train vs validación (últimos N días)
        df_train_p = df_prophet.iloc[:-dias_validacion]
        df_val_p = df_prophet.iloc[-dias_validacion:]
        
        if len(df_train_p) < 365:
            print(f"    ⚠️  Datos insuficientes para validación con holdout, usando pesos fijos", flush=True)
            self.pesos = {'prophet': 0.6, 'sarima': 0.4} if self.modelo_sarima else {'prophet': 1.0, 'sarima': 0.0}
            self.metricas = {'mape_ensemble': -1, 'mape_prophet': -1, 'mape_sarima': -1}
            return
        
        # Re-entrenar Prophet con subset de entrenamiento
        modelo_p_temp = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            interval_width=CONFIANZA,
            mcmc_samples=0
        ).fit(df_train_p)
        
        # Predicciones Prophet sobre período de validación
        future_p = modelo_p_temp.make_future_dataframe(periods=dias_validacion)
        pred_prophet = modelo_p_temp.predict(future_p)
        pred_prophet_val = pred_prophet.iloc[-dias_validacion:]['yhat'].values
        
        y_real = df_val_p['y'].values
        
        if self.modelo_sarima:
            # FASE 7B: Re-entrenar SARIMA con solo datos de entrenamiento (sin holdout)
            # Antes: usaba self.modelo_sarima entrenado con TODOS los datos → data leak
            try:
                serie_train_s = serie_sarima.iloc[:-dias_validacion]
                modelo_sarima_temp = auto_arima(
                    serie_train_s.dropna(),
                    seasonal=True, m=7,
                    start_p=0, start_q=0, max_p=2, max_q=2,
                    max_P=1, max_Q=1, D=1,
                    suppress_warnings=True, error_action='ignore',
                    stepwise=True, n_jobs=-1
                )
                pred_sarima_val = modelo_sarima_temp.predict(n_periods=dias_validacion)
            except Exception as e_sarima:
                print(f"    ⚠️  SARIMA holdout falló: {e_sarima}. Usando solo Prophet.", flush=True)
                pred_sarima_val = None
            
            if pred_sarima_val is not None:
                # Calcular MAPE real para cada modelo
                mape_prophet = mean_absolute_percentage_error(y_real, pred_prophet_val)
                mape_sarima = mean_absolute_percentage_error(y_real, pred_sarima_val)
                
                # Pesos inversamente proporcionales al error
                total_error = mape_prophet + mape_sarima
                if total_error > 0:
                    self.pesos['prophet'] = (1 - mape_prophet / total_error)
                    self.pesos['sarima'] = (1 - mape_sarima / total_error)
                else:
                    self.pesos = {'prophet': 0.5, 'sarima': 0.5}
                
                # Normalizar pesos
                suma_pesos = self.pesos['prophet'] + self.pesos['sarima']
                self.pesos['prophet'] /= suma_pesos
                self.pesos['sarima'] /= suma_pesos
                
                # MAPE ensemble real
                pred_ensemble_val = self.pesos['prophet'] * pred_prophet_val + self.pesos['sarima'] * pred_sarima_val
                mape_ensemble = mean_absolute_percentage_error(y_real, pred_ensemble_val)
                
                # FASE 7B: Calcular RMSE
                from sklearn.metrics import mean_squared_error
                rmse_ensemble = np.sqrt(mean_squared_error(y_real, pred_ensemble_val))
                
                self.metricas = {
                    'mape_prophet': mape_prophet,
                    'mape_sarima': mape_sarima,
                    'mape_ensemble': mape_ensemble,
                    'rmse': rmse_ensemble,
                    'confianza': max(0.0, 1.0 - mape_ensemble)
                }
                
                print(f"    ✓ MAPE Prophet: {mape_prophet:.2%}, SARIMA: {mape_sarima:.2%}, ENSEMBLE: {mape_ensemble:.2%}", flush=True)
                print(f"    ✓ RMSE: {rmse_ensemble:.4f}, Confianza: {self.metricas['confianza']:.2%}", flush=True)
                print(f"    ✓ Pesos óptimos: Prophet={self.pesos['prophet']:.2f}, SARIMA={self.pesos['sarima']:.2f}", flush=True)
            else:
                # SARIMA holdout falló, usar solo Prophet
                mape_prophet = mean_absolute_percentage_error(y_real, pred_prophet_val)
                from sklearn.metrics import mean_squared_error
                rmse_prophet = np.sqrt(mean_squared_error(y_real, pred_prophet_val))
                self.pesos = {'prophet': 1.0, 'sarima': 0.0}
                self.metricas = {
                    'mape_prophet': mape_prophet,
                    'mape_sarima': None,
                    'mape_ensemble': mape_prophet,
                    'rmse': rmse_prophet,
                    'confianza': max(0.0, 1.0 - mape_prophet)
                }
                print(f"    ✓ MAPE Prophet (solo, SARIMA holdout falló): {mape_prophet:.2%}", flush=True)
        else:
            mape_prophet = mean_absolute_percentage_error(y_real, pred_prophet_val)
            from sklearn.metrics import mean_squared_error
            rmse_prophet = np.sqrt(mean_squared_error(y_real, pred_prophet_val))
            self.pesos = {'prophet': 1.0, 'sarima': 0.0}
            self.metricas = {
                'mape_prophet': mape_prophet,
                'mape_sarima': None,
                'mape_ensemble': mape_prophet,
                'rmse': rmse_prophet,
                'confianza': max(0.0, 1.0 - mape_prophet)
            }
            print(f"    ✓ MAPE Prophet (solo): {mape_prophet:.2%}", flush=True)
    
    def predecir(self, horizonte_dias):
        """Genera predicciones combinadas con intervalos estadísticos reales"""
        print(f"  → Generando predicciones {horizonte_dias} días...", flush=True)
        
        # Prophet
        future = self.modelo_prophet.make_future_dataframe(periods=horizonte_dias, freq='D')
        pred_prophet = self.modelo_prophet.predict(future)
        pred_prophet = pred_prophet.tail(horizonte_dias)
        
        # SARIMA
        if self.modelo_sarima and self.pesos['sarima'] > 0:
            try:
                pred_sarima = self.modelo_sarima.predict(n_periods=horizonte_dias)
                sarima_conf = self.modelo_sarima.predict(n_periods=horizonte_dias, return_conf_int=True)
                sarima_lower = sarima_conf[1][:, 0] if len(sarima_conf) > 1 else pred_sarima * 0.8
                sarima_upper = sarima_conf[1][:, 1] if len(sarima_conf) > 1 else pred_sarima * 1.2
                
                # Ensemble ponderado
                predicciones_ensemble = (
                    self.pesos['prophet'] * pred_prophet['yhat'].values +
                    self.pesos['sarima'] * pred_sarima
                )
                
                # Intervalos ponderados con intervalos reales de SARIMA
                intervalo_inferior = (
                    self.pesos['prophet'] * pred_prophet['yhat_lower'].values +
                    self.pesos['sarima'] * sarima_lower
                )
                intervalo_superior = (
                    self.pesos['prophet'] * pred_prophet['yhat_upper'].values +
                    self.pesos['sarima'] * sarima_upper
                )
                
            except Exception:
                # Fallback a Prophet
                predicciones_ensemble = pred_prophet['yhat'].values
                intervalo_inferior = pred_prophet['yhat_lower'].values
                intervalo_superior = pred_prophet['yhat_upper'].values
        else:
            # Solo Prophet
            predicciones_ensemble = pred_prophet['yhat'].values
            intervalo_inferior = pred_prophet['yhat_lower'].values
            intervalo_superior = pred_prophet['yhat_upper'].values
        
        # CLAMP: Generación eléctrica no puede ser negativa
        predicciones_ensemble = np.maximum(predicciones_ensemble, 0.0)
        intervalo_inferior = np.maximum(intervalo_inferior, 0.0)
        intervalo_superior = np.maximum(intervalo_superior, 0.0)
        
        # Crear DataFrame de resultados
        fechas_prediccion = pred_prophet['ds'].values
        
        df_predicciones = pd.DataFrame({
            'fecha_prediccion': fechas_prediccion,
            'valor_gwh_predicho': predicciones_ensemble,
            'intervalo_inferior': intervalo_inferior,
            'intervalo_superior': intervalo_superior
        })
        
        return df_predicciones


def cargar_datos_historicos(fuente, fecha_inicio='2020-01-01'):
    """Carga datos históricos de generación desde PostgreSQL"""
    print(f"\n📊 Cargando datos históricos para {fuente}...")
    
    conn = get_postgres_connection()
    
    # Mapeo de nombres de fuentes a tipos en catálogo
    tipo_mapa = {
        'Hidráulica': 'HIDRAULICA',
        'Térmica': 'TERMICA',
        'Eólica': 'EOLICA',
        'Solar': 'SOLAR',
        'Biomasa': 'COGENERADOR'
    }
    
    tipo_catalogo = tipo_mapa.get(fuente, fuente.upper())
    
    # Consulta usando catalogos para filtrar por tipo de recurso
    query = """
    SELECT m.fecha, SUM(m.valor_gwh) as valor_gwh
    FROM metrics m
    INNER JOIN catalogos c ON m.recurso = c.codigo
    WHERE m.metrica = 'Gene'
      AND c.catalogo = 'ListadoRecursos'
      AND c.tipo = %s
      AND m.fecha >= %s
      AND m.valor_gwh > 0
    GROUP BY m.fecha
    ORDER BY m.fecha
    """
    
    try:
        df = pd.read_sql_query(query, conn, params=(tipo_catalogo, fecha_inicio))
        conn.close()
        
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.sort_values('fecha')
        
        if len(df) > 0:
            print(f"  ✓ Cargados {len(df)} registros ({df['fecha'].min().date()} a {df['fecha'].max().date()})")
            print(f"    Promedio diario: {df['valor_gwh'].mean():.2f} GWh")
        else:
            print(f"  ⚠️  No se encontraron datos para {fuente}")
        
        return df
        
    except Exception as e:
        print(f"  ❌ Error cargando datos: {e}")
        conn.close()
        return pd.DataFrame()


def guardar_predicciones(predicciones_dict, predictores):
    """Guarda predicciones en PostgreSQL con métricas de calidad (FASE 7B)"""
    print("\n💾 Guardando predicciones en PostgreSQL...")
    
    conn = get_postgres_connection()
    conn.autocommit = False
    cursor = conn.cursor()
    
    try:
        # Limpiar predicciones antiguas del mismo modelo
        print("  → Limpiando predicciones antiguas...")
        cursor.execute("DELETE FROM predictions WHERE modelo = %s", (MODELO_VERSION,))
        
        fecha_generacion = datetime.now()
        total_registros = 0
        
        for fuente, df_pred in predicciones_dict.items():
            # FASE 7B: Obtener métricas reales del predictor
            predictor = predictores.get(fuente)
            if predictor:
                mape_val = predictor.metricas.get('mape_ensemble')
                rmse_val = predictor.metricas.get('rmse')
                confianza_real = predictor.metricas.get('confianza')
                # Si no se pudo calcular, usar fallback
                if confianza_real is None or (mape_val is not None and mape_val < 0):
                    confianza_real = CONFIANZA
                    mape_val = None
                    rmse_val = None
                else:
                    # Cast numpy → Python float para psycopg2
                    confianza_real = float(confianza_real)
                    mape_val = float(mape_val) if mape_val is not None else None
                    rmse_val = float(rmse_val) if rmse_val is not None else None
            else:
                confianza_real = CONFIANZA
                mape_val = None
                rmse_val = None
            
            print(f"  → Guardando {len(df_pred)} predicciones de {fuente} "
                  f"(confianza={confianza_real:.2f}, "
                  f"mape={f'{mape_val:.4f}' if mape_val is not None else 'N/A'}, "
                  f"rmse={f'{rmse_val:.2f}' if rmse_val is not None else 'N/A'})")
            
            for _, row in df_pred.iterrows():
                cursor.execute("""
                    INSERT INTO predictions (
                        fecha_prediccion, fecha_generacion, fuente,
                        valor_gwh_predicho, intervalo_inferior, intervalo_superior,
                        horizonte_dias, modelo, confianza, mape, rmse
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    row['fecha_prediccion'],
                    fecha_generacion,
                    fuente,
                    float(row['valor_gwh_predicho']),
                    float(row['intervalo_inferior']),
                    float(row['intervalo_superior']),
                    HORIZONTE_DIAS,
                    MODELO_VERSION,
                    confianza_real,
                    mape_val,
                    rmse_val
                ))
                total_registros += 1
        
        conn.commit()
        print(f"  ✓ {total_registros} predicciones guardadas exitosamente")
        
    except Exception as e:
        conn.rollback()
        print(f"  ❌ Error guardando predicciones: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()


def generar_reporte_metricas(predictores):
    """Genera reporte de métricas de precisión"""
    print("\n" + "="*60)
    print("📈 REPORTE DE MÉTRICAS - ENSEMBLE")
    print("="*60)
    
    for fuente, predictor in predictores.items():
        metricas = predictor.metricas
        mape_val = metricas.get('mape_ensemble', -1)
        print(f"\n{fuente}:")
        if mape_val is None or mape_val < 0:
            print(f"  MAPE ENSEMBLE: N/A (datos insuficientes para validar)")
        else:
            print(f"  MAPE ENSEMBLE: {mape_val:.2%}")
            mp = metricas.get('mape_prophet')
            ms = metricas.get('mape_sarima')
            print(f"  MAPE Prophet:  {mp:.2%}" if mp is not None else "  MAPE Prophet:  N/A")
            print(f"  MAPE SARIMA:   {ms:.2%}" if ms is not None else "  MAPE SARIMA:   N/A (no disponible)")
            
            if mape_val < 0.05:
                print(f"  ✅ OBJETIVO CUMPLIDO (< 5%)")
            elif mape_val < 0.10:
                print(f"  ⚠️  ACEPTABLE (< 10%)")
            else:
                print(f"  ❌ MEJORA REQUERIDA (> 10%)")
    
    # Promedio general
    mape_promedio = np.mean([p.metricas.get('mape_ensemble', 0) for p in predictores.values()])
    print(f"\n{'='*60}")
    print(f"MAPE PROMEDIO GENERAL: {mape_promedio:.2%}")
    
    if mape_promedio < 0.05:
        print("✅ SISTEMA ENSEMBLE APROBADO - Precisión nacional garantizada")
    else:
        print("⚠️  Considerar FASE 3 (TFT) para mejorar precisión")
    
    print("="*60)


def main():
    """Función principal de entrenamiento y predicción"""
    print("\n" + "="*60)
    print("🚀 SISTEMA DE PREDICCIONES - FASE 2 (PostgreSQL)")
    print("   Modelo: ENSEMBLE (Prophet + SARIMA)")
    print("   Horizonte: 3 meses (90 días)")
    print("   Objetivo: MAPE < 5%")
    print("="*60)
    
    # Verificar conexión PostgreSQL
    try:
        conn = get_postgres_connection()
        # Obtener nombre de la base de datos
        cur = conn.cursor()
        cur.execute("SELECT current_database()")
        db_name = cur.fetchone()[0]
        print(f"✅ Conectado a PostgreSQL: {db_name}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error conectando a PostgreSQL: {e}")
        return
    
    predictores = {}
    predicciones_dict = {}
    
    for fuente in FUENTES:
        print(f"\n{'='*60}")
        print(f"🔧 Procesando: {fuente}")
        print("="*60)
        
        try:
            # 1. Cargar datos históricos
            df = cargar_datos_historicos(fuente)
            
            if len(df) < 365:
                print(f"  ⚠️  Datos insuficientes para {fuente} (< 1 año)")
                continue
            
            # 2. Crear predictor
            predictor = PredictorEnsemble(fuente)
            
            # 3. Preparar datos
            df_prophet, serie_sarima = predictor.preparar_datos(df)
            
            # 4. Entrenar modelos
            predictor.entrenar_prophet(df_prophet)
            predictor.entrenar_sarima(serie_sarima)
            
            # 5. Validar y optimizar pesos
            predictor.validar_modelos(df_prophet, serie_sarima)
            
            # 6. Generar predicciones
            df_predicciones = predictor.predecir(HORIZONTE_DIAS)
            
            # 7. Guardar en diccionarios
            predictores[fuente] = predictor
            predicciones_dict[fuente] = df_predicciones
            
            print(f"  ✅ {fuente} completado exitosamente")
            
        except Exception as e:
            print(f"  ❌ Error procesando {fuente}: {e}")
            import traceback
            traceback.print_exc()
    
    # Guardar predicciones en PostgreSQL
    if predicciones_dict:
        guardar_predicciones(predicciones_dict, predictores)
        generar_reporte_metricas(predictores)
    else:
        print("\n❌ No se generaron predicciones")
    
    print("\n✅ Proceso completado\n")


if __name__ == '__main__':
    main()

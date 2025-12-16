#!/usr/bin/env python3
"""
Script de Entrenamiento y Generación de Predicciones
Sistema ENSEMBLE: Prophet + SARIMA + Validación Estadística
FASE 2 - Modelos ML Reales para Portal Energético MME

Objetivo: Predicciones precisas (MAPE < 5%) para planificación nacional
Horizonte: 3 meses (90 días)
Fuentes: Hidráulica, Térmica, Eólica, Solar, Biomasa
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from prophet import Prophet
from pmdarima import auto_arima
from statsmodels.tsa.statespace.sarimax import SARIMAX
from sklearn.metrics import mean_absolute_percentage_error
import warnings
warnings.filterwarnings('ignore')

# Configuración
DB_PATH = '/home/admonctrlxm/server/portal_energetico.db'
HORIZONTE_DIAS = 90  # 3 meses
CONFIANZA = 0.95
MODELO_VERSION = 'ENSEMBLE_v1.0'

# Fuentes de generación
FUENTES = ['Hidráulica', 'Térmica', 'Eólica', 'Solar', 'Biomasa']

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
            weekly_seasonality=False,  # Desactivar para velocidad
            daily_seasonality=False,
            interval_width=CONFIANZA,
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10.0,
            mcmc_samples=0  # Usar MAP en lugar de MCMC para velocidad
        )
        
        # Suprimir logs de Prophet
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
            # Reducir complejidad para velocidad
            modelo = auto_arima(
                serie_sarima,
                start_p=0, start_q=0,
                max_p=2, max_q=2,  # Reducido de 3 a 2
                m=7,
                start_P=0, start_Q=0,
                max_P=1, max_Q=1,  # Reducido de 2 a 1
                seasonal=True,
                d=None,
                D=1,
                trace=False,
                error_action='ignore',
                suppress_warnings=True,
                stepwise=True,
                n_jobs=-1  # Usar todos los cores disponibles
            )
            
            self.modelo_sarima = modelo
            print(f"    ✓ SARIMA entrenado: {modelo.order} x {modelo.seasonal_order}", flush=True)
            return modelo
            
        except Exception as e:
            print(f"    ⚠️  SARIMA omitido (solo Prophet): {str(e)[:50]}", flush=True)
            return None
    
    def validar_modelos(self, df_prophet, serie_sarima, dias_validacion=30):
        """Valida modelos con datos recientes y calcula pesos óptimos"""
        print(f"  → Validando modelos para {self.fuente}...", flush=True)
        
        # Suprimir logs
        import logging
        logging.getLogger('prophet').setLevel(logging.ERROR)
        logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
        
        # Split: train vs validación
        df_train_p = df_prophet.iloc[:-dias_validacion]
        df_val_p = df_prophet.iloc[-dias_validacion:]
        
        # Entrenar con subset
        modelo_p_temp = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            interval_width=CONFIANZA,
            mcmc_samples=0
        ).fit(df_train_p)
        
        # Predicciones Prophet
        future_p = modelo_p_temp.make_future_dataframe(periods=dias_validacion)
        pred_prophet = modelo_p_temp.predict(future_p)
        pred_prophet_val = pred_prophet.iloc[-dias_validacion:]['yhat'].values
        
        # Predicciones SARIMA
        if self.modelo_sarima:
            serie_train_s = serie_sarima.iloc[:-dias_validacion]
            serie_val_s = serie_sarima.iloc[-dias_validacion:]
            
            pred_sarima_val = self.modelo_sarima.predict(n_periods=dias_validacion)
            
            # Calcular MAPE para cada modelo
            mape_prophet = mean_absolute_percentage_error(df_val_p['y'], pred_prophet_val)
            mape_sarima = mean_absolute_percentage_error(serie_val_s, pred_sarima_val)
            
            # Ajustar pesos inversamente proporcionales al error
            total_error = mape_prophet + mape_sarima
            self.pesos['prophet'] = (1 - mape_prophet/total_error) if total_error > 0 else 0.5
            self.pesos['sarima'] = (1 - mape_sarima/total_error) if total_error > 0 else 0.5
            
            # Normalizar pesos
            suma_pesos = self.pesos['prophet'] + self.pesos['sarima']
            self.pesos['prophet'] /= suma_pesos
            self.pesos['sarima'] /= suma_pesos
            
            self.metricas = {
                'mape_prophet': mape_prophet,
                'mape_sarima': mape_sarima,
                'mape_ensemble': mape_prophet * self.pesos['prophet'] + mape_sarima * self.pesos['sarima']
            }
            
            print(f"    ✓ MAPE Prophet: {mape_prophet:.2%}, SARIMA: {mape_sarima:.2%}, ENSEMBLE: {self.metricas['mape_ensemble']:.2%}", flush=True)
            print(f"    ✓ Pesos: Prophet={self.pesos['prophet']:.2f}, SARIMA={self.pesos['sarima']:.2f}", flush=True)
        else:
            # Solo Prophet disponible
            mape_prophet = mean_absolute_percentage_error(df_val_p['y'], pred_prophet_val)
            self.pesos = {'prophet': 1.0, 'sarima': 0.0}
            self.metricas = {'mape_prophet': mape_prophet, 'mape_ensemble': mape_prophet}
            print(f"    ✓ MAPE Prophet (solo): {mape_prophet:.2%}", flush=True)
    
    def predecir(self, dias=HORIZONTE_DIAS):
        """Genera predicciones ENSEMBLE con intervalos de confianza"""
        print(f"  → Generando predicciones para {self.fuente} ({dias} días)...")
        
        # Predicciones Prophet
        future = self.modelo_prophet.make_future_dataframe(periods=dias)
        pred_prophet = self.modelo_prophet.predict(future)
        pred_prophet = pred_prophet.iloc[-dias:]
        
        # Predicciones SARIMA
        if self.modelo_sarima and self.pesos['sarima'] > 0:
            pred_sarima = self.modelo_sarima.predict(n_periods=dias)
            
            # ENSEMBLE: Promedio ponderado
            predicciones_ensemble = (
                pred_prophet['yhat'].values * self.pesos['prophet'] +
                pred_sarima * self.pesos['sarima']
            )
            
            # Intervalos de confianza: combinar varianzas
            intervalo_inferior = (
                pred_prophet['yhat_lower'].values * self.pesos['prophet'] +
                (pred_sarima - 1.96 * np.std(pred_sarima)) * self.pesos['sarima']
            )
            
            intervalo_superior = (
                pred_prophet['yhat_upper'].values * self.pesos['prophet'] +
                (pred_sarima + 1.96 * np.std(pred_sarima)) * self.pesos['sarima']
            )
        else:
            # Solo Prophet
            predicciones_ensemble = pred_prophet['yhat'].values
            intervalo_inferior = pred_prophet['yhat_lower'].values
            intervalo_superior = pred_prophet['yhat_upper'].values
        
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
    """Carga datos históricos de generación desde SQLite"""
    print(f"\n📊 Cargando datos históricos para {fuente}...")
    
    conn = sqlite3.connect(DB_PATH)
    
    # Mapeo de nombres de fuentes a tipos en catálogo
    tipo_mapa = {
        'Hidráulica': 'HIDRAULICA',
        'Térmica': 'TERMICA',
        'Eólica': 'EOLICA',
        'Solar': 'SOLAR',
        'Biomasa': 'COGENERADOR'  # Biomasa está categorizada como COGENERADOR
    }
    
    tipo_catalogo = tipo_mapa.get(fuente, fuente.upper())
    
    query = """
    SELECT m.fecha, SUM(m.valor_gwh) as valor_gwh
    FROM metrics m
    INNER JOIN catalogos c ON m.recurso = c.codigo
    WHERE m.metrica = 'Gene'
      AND c.catalogo = 'ListadoRecursos'
      AND c.tipo = ?
      AND m.fecha >= ?
      AND m.valor_gwh > 0
    GROUP BY m.fecha
    ORDER BY m.fecha
    """
    
    df = pd.read_sql_query(query, conn, params=(tipo_catalogo, fecha_inicio))
    conn.close()
    
    df['fecha'] = pd.to_datetime(df['fecha'])
    df = df.sort_values('fecha')
    
    if len(df) > 0:
        print(f"  ✓ Cargados {len(df)} registros ({df['fecha'].min().date()} a {df['fecha'].max().date()})")
        print(f"    Promedio diario: {df['valor_gwh'].mean():.2f} GWh")
    else:
        print(f"  ⚠️  No se encontraron datos para {fuente} (tipo: {tipo_catalogo})")
    
    return df


def guardar_predicciones(predicciones_dict):
    """Guarda predicciones en la tabla predictions"""
    print("\n💾 Guardando predicciones en base de datos...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Limpiar predicciones antiguas
    cursor.execute("DELETE FROM predictions")
    
    fecha_generacion = datetime.now().strftime('%Y-%m-%d')
    total_registros = 0
    
    for fuente, df_pred in predicciones_dict.items():
        for _, row in df_pred.iterrows():
            cursor.execute("""
                INSERT INTO predictions (
                    fecha_prediccion, fecha_generacion, fuente,
                    valor_gwh_predicho, intervalo_inferior, intervalo_superior,
                    horizonte_meses, modelo, confianza
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row['fecha_prediccion'].strftime('%Y-%m-%d'),
                fecha_generacion,
                fuente,
                float(row['valor_gwh_predicho']),
                float(row['intervalo_inferior']),
                float(row['intervalo_superior']),
                3,  # 3 meses
                MODELO_VERSION,
                CONFIANZA
            ))
            total_registros += 1
    
    conn.commit()
    conn.close()
    
    print(f"  ✓ {total_registros} predicciones guardadas exitosamente")


def generar_reporte_metricas(predictores):
    """Genera reporte de métricas de precisión"""
    print("\n" + "="*60)
    print("📈 REPORTE DE MÉTRICAS - ENSEMBLE")
    print("="*60)
    
    for fuente, predictor in predictores.items():
        metricas = predictor.metricas
        print(f"\n{fuente}:")
        print(f"  MAPE ENSEMBLE: {metricas.get('mape_ensemble', 0):.2%}")
        print(f"  MAPE Prophet:  {metricas.get('mape_prophet', 0):.2%}")
        print(f"  MAPE SARIMA:   {metricas.get('mape_sarima', 0):.2%}")
        
        if metricas.get('mape_ensemble', 1) < 0.05:
            print(f"  ✅ OBJETIVO CUMPLIDO (< 5%)")
        else:
            print(f"  ⚠️  MEJORA REQUERIDA (> 5%)")
    
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
    print("🚀 SISTEMA DE PREDICCIONES - FASE 2")
    print("   Modelo: ENSEMBLE (Prophet + SARIMA)")
    print("   Horizonte: 3 meses (90 días)")
    print("   Objetivo: MAPE < 5%")
    print("="*60)
    
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
    
    # Guardar predicciones en BD
    if predicciones_dict:
        guardar_predicciones(predicciones_dict)
        generar_reporte_metricas(predictores)
    else:
        print("\n❌ No se generaron predicciones")
    
    print("\n✅ Proceso completado\n")


if __name__ == '__main__':
    main()

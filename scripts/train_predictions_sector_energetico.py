#!/usr/bin/env python3
"""
SISTEMA DE PREDICCIONES ESTRATÉGICAS - SECTOR ELÉCTRICO COLOMBIANO
Viceministro de Energía - Predicciones ML para Toma de Decisiones

Métricas Críticas (Nivel Viceministro):
1. GENERACIÓN por fuentes (YA IMPLEMENTADO) ✅
2. DEMANDA Nacional y Segmentada
3. PRECIO DE BOLSA Nacional
4. HIDROLOGÍA: Aportes Energéticos y Niveles de Embalses
5. PÉRDIDAS del Sistema

Horizonte: 90 días (3 meses) - Planificación estratégica
Modelos: ENSEMBLE (Prophet + SARIMA)
Objetivo: MAPE < 5-10% según criticidad
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
from sklearn.metrics import mean_absolute_percentage_error
import warnings
warnings.filterwarnings('ignore')

HORIZONTE_DIAS = 90  # 3 meses
CONFIANZA = 0.95
MODELO_VERSION = 'ENSEMBLE_SECTOR_v1.0'

# =============================================================================
# CONFIGURACIÓN DE MÉTRICAS ESTRATÉGICAS
# =============================================================================

METRICAS_CONFIG = {
    # 1. GENERACIÓN POR FUENTE (YA IMPLEMENTADO en train_predictions_postgres.py) ✅
    'GENERACION': {
        'metricas': ['Gene'],
        'tipo': 'agregado_por_recurso',
        'descripcion': 'Generación de energía por tipo de fuente',
        'unidad': 'GWh',
        'criticidad': 'CRÍTICA',
        'ya_implementado': True
    },
    
    # 1b. GENERACIÓN TOTAL DEL SISTEMA - Para chatbot Viceministro
    'GENE_TOTAL': {
        'metricas': [
            'Gene'             # Generación Total Nacional
        ],
        'tipo': 'suma_diaria',
        'entidad_filtro': 'Sistema',   # Total nacional únicamente
        'descripcion': 'Generación total del SIN (Sistema Interconectado Nacional)',
        'unidad': 'GWh',
        'criticidad': 'CRÍTICA',
        'prioridad': 1
    },
    
    # 2. DEMANDA - Consumo Nacional
    'DEMANDA': {
        'metricas': [
            'DemaReal',        # Demanda Real Total (MÁS IMPORTANTE)
            'DemaCome',        # Demanda Comercial
            'DemaRealReg',     # Demanda Regulada
            'DemaRealNoReg'    # Demanda No Regulada
        ],
        'tipo': 'suma_diaria',
        'prefer_sistema': True,  # Preferir Sistema; si no existe, sumar Agentes (evita doble conteo)
        'descripcion': 'Demanda eléctrica nacional segmentada',
        'unidad': 'GWh',
        'criticidad': 'CRÍTICA',
        'prioridad': 1
    },
    
    # 3. PRECIO DE BOLSA - Mercado Spot
    'PRECIO_BOLSA': {
        'metricas': [
            'PrecBolsNaci'     # Precio de Bolsa Nacional (CRÍTICO)
        ],
        'tipo': 'promedio_ponderado',
        'entidad_filtro': 'Sistema',   # Precio nacional único (sin promediar con agentes)
        'solo_prophet': True,          # SARIMA extrapola tendencia bajista a 0; Prophet captura estacionalidad
        'prophet_growth': 'flat',      # Precios spot son mean-reverting, no trend
        'prophet_seasonality_mode': 'multiplicative',
        'ventana_meses': 8,            # Usar solo últimos 8 meses (evita shock 2023-2024)
        'piso_historico': 86.0,        # Mínimo histórico $/kWh
        'descripcion': 'Precio de Bolsa Nacional - Mercado Spot',
        'unidad': '$/kWh',
        'criticidad': 'CRÍTICA',
        'prioridad': 1
    },
    
    # 4. PRECIO DE ESCASEZ
    'PRECIO_ESCASEZ': {
        'metricas': [
            'PrecEsca'         # Precio de Escasez (Señal de Confiabilidad)
        ],
        'tipo': 'promedio_diario',
        'descripcion': 'Precio de Escasez - Señal de confiabilidad',
        'unidad': '$/kWh',
        'criticidad': 'CRÍTICA',
        'prioridad': 2
    },
    
    # 5. HIDROLOGÍA - Aportes Energéticos
    'APORTES_HIDRICOS': {
        'metricas': [
            'AporEner'         # Aportes de Energía Hidroeléctrica
        ],
        'tipo': 'suma_embalses',
        'descripcion': 'Aportes de energía hidrológica a embalses',
        'unidad': 'GWh',
        'criticidad': 'CRÍTICA',
        'prioridad': 1
    },
    
    # 6. CAPACIDAD DE EMBALSES (Energía)
    'EMBALSES': {
        'metricas': [
            'CapaUtilDiarEner',  # Almacenamiento en GWh
        ],
        'tipo': 'suma_embalses',
        'entidad_filtro': 'Sistema',   # Total nacional
        'descripcion': 'Capacidad útil de embalses - Energía',
        'unidad': 'GWh',
        'criticidad': 'CRÍTICA',
        'prioridad': 1
    },
    
    # 6b. EMBALSES - Porcentaje de volumen útil
    'EMBALSES_PCT': {
        'metricas': [
            'PorcVoluUtilDiar'   # % volumen útil diario (XM lo entrega como fracción 0-1)
        ],
        'tipo': 'promedio_diario',
        'entidad_filtro': 'Sistema',   # Promedio nacional
        'escala_factor': 100,          # Convertir fracción 0-1 → porcentaje 0-100 (dashboard usa 0-100)
        'descripcion': 'Porcentaje volumen útil de embalses',
        'unidad': '%',
        'criticidad': 'CRÍTICA',
        'prioridad': 1
    },
    
    # 7. PÉRDIDAS DEL SISTEMA
    'PERDIDAS': {
        'metricas': [
            'PerdidasEner'       # Pérdidas totales del sistema
        ],
        'tipo': 'suma_diaria',
        'prefer_sistema': True,  # Preferir Sistema; si no existe, sumar Agentes (evita doble conteo)
        'descripcion': 'Pérdidas técnicas y no técnicas del SIN',
        'unidad': 'GWh',
        'criticidad': 'IMPORTANTE',
        'prioridad': 2
    }
}


def get_postgres_connection():
    """Obtiene conexión a PostgreSQL usando el connection manager del sistema"""
    from infrastructure.database.connection import PostgreSQLConnectionManager
    manager = PostgreSQLConnectionManager()
    conn_params = {
        'host': manager.host,
        'port': manager.port,
        'database': manager.database,
        'user': manager.user
    }
    if manager.password:
        conn_params['password'] = manager.password
    return psycopg2.connect(**conn_params)


class PredictorMetricaSectorial:
    """Predictor especializado para métricas del sector energético"""
    
    def __init__(self, nombre_metrica, config):
        self.nombre = nombre_metrica
        self.config = config
        self.modelo_prophet = None
        self.modelo_sarima = None
        self.pesos = {'prophet': 0.6, 'sarima': 0.4}
        self.metricas = {}
        
    def entrenar_prophet(self, df_prophet):
        """Entrena modelo Prophet con estacionalidad anual"""
        print(f"  → Entrenando Prophet para {self.nombre}...", flush=True)
        
        # Config overrides para métricas especiales (ej: precios spot)
        growth = self.config.get('prophet_growth', 'linear')
        seasonality_mode = self.config.get('prophet_seasonality_mode', 'additive')
        has_yearly = len(df_prophet) >= 365  # Solo si hay ≥1 año de datos
        
        modelo = Prophet(
            growth=growth,
            yearly_seasonality=has_yearly,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=CONFIANZA,
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10.0,
            seasonality_mode=seasonality_mode,
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
        print(f"  → Entrenando SARIMA para {self.nombre} (puede tardar)...", flush=True)
        
        try:
            modelo = auto_arima(
                serie_sarima.dropna(),
                seasonal=True,
                m=7,  # Estacionalidad semanal
                max_order=5,
                suppress_warnings=True,
                error_action='ignore',
                stepwise=True,
                n_jobs=-1
            )
            self.modelo_sarima = modelo
            print(f"    ✓ SARIMA entrenado: {modelo.order} x {modelo.seasonal_order}", flush=True)
            return modelo
            
        except Exception as e:
            print(f"    ⚠️  SARIMA falló: {e}. Usando solo Prophet.", flush=True)
            return None
    
    def validar_y_generar(self, df_prophet, serie_sarima, dias_validacion=30):
        """Validación REAL con holdout y cálculo de MAPE auténtico"""
        print(f"  → Validando modelos con holdout de {dias_validacion} días...", flush=True)
        
        import logging
        logging.getLogger('prophet').setLevel(logging.ERROR)
        logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
        
        # Split: train vs validación
        df_train_p = df_prophet.iloc[:-dias_validacion]
        df_val_p = df_prophet.iloc[-dias_validacion:]
        y_real = df_val_p['y'].values
        
        if len(df_train_p) < 365:
            print(f"    ⚠️  Datos insuficientes para holdout, usando pesos fijos", flush=True)
            self.pesos = {'prophet': 0.6, 'sarima': 0.4} if self.modelo_sarima else {'prophet': 1.0, 'sarima': 0.0}
            self.metricas = {'mape_ensemble': -1, 'confianza': 0.5}
            return
        
        # Re-entrenar Prophet temporalmente con subset
        modelo_p_temp = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=CONFIANZA,
            mcmc_samples=0
        ).fit(df_train_p)
        
        future_p = modelo_p_temp.make_future_dataframe(periods=dias_validacion)
        pred_prophet = modelo_p_temp.predict(future_p)
        pred_prophet_val = pred_prophet.iloc[-dias_validacion:]['yhat'].values
        
        if self.modelo_sarima:
            # FASE 7B: Re-entrenar SARIMA con solo datos de entrenamiento (sin holdout)
            # Antes: usaba self.modelo_sarima entrenado con TODOS los datos → data leak
            try:
                serie_train_s = serie_sarima.iloc[:-dias_validacion]
                modelo_sarima_temp = auto_arima(
                    serie_train_s.dropna(),
                    seasonal=True, m=7,
                    max_order=5,
                    suppress_warnings=True, error_action='ignore',
                    stepwise=True, n_jobs=-1
                )
                pred_sarima_val = modelo_sarima_temp.predict(n_periods=dias_validacion)
            except Exception as e_sarima:
                print(f"    ⚠️  SARIMA holdout falló: {e_sarima}. Usando solo Prophet.", flush=True)
                pred_sarima_val = None
            
            if pred_sarima_val is not None:
                # MAPE REAL
                from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error
                mape_prophet = mean_absolute_percentage_error(y_real, pred_prophet_val)
                mape_sarima = mean_absolute_percentage_error(y_real, pred_sarima_val)
                
                # Pesos inversamente proporcionales al error
                total_error = mape_prophet + mape_sarima
                if total_error > 0:
                    self.pesos['prophet'] = (1 - mape_prophet / total_error)
                    self.pesos['sarima'] = (1 - mape_sarima / total_error)
                else:
                    self.pesos = {'prophet': 0.5, 'sarima': 0.5}
                
                # Normalizar
                suma = self.pesos['prophet'] + self.pesos['sarima']
                self.pesos['prophet'] /= suma
                self.pesos['sarima'] /= suma
                
                # MAPE ensemble real
                pred_ensemble_val = self.pesos['prophet'] * pred_prophet_val + self.pesos['sarima'] * pred_sarima_val
                mape_ensemble = mean_absolute_percentage_error(y_real, pred_ensemble_val)
                
                # FASE 7B: Calcular RMSE
                rmse_ensemble = np.sqrt(mean_squared_error(y_real, pred_ensemble_val))
                
                self.metricas = {
                    'mape_ensemble': mape_ensemble,
                    'mape_prophet': mape_prophet,
                    'mape_sarima': mape_sarima,
                    'rmse': rmse_ensemble,
                    'confianza': max(0.0, 1.0 - mape_ensemble)
                }
                
                print(f"    ✓ MAPE Prophet: {mape_prophet:.2%}, SARIMA: {mape_sarima:.2%}", flush=True)
                print(f"    ✓ MAPE Ensemble: {mape_ensemble:.2%}", flush=True)
                print(f"    ✓ RMSE: {rmse_ensemble:.4f}, Confianza: {self.metricas['confianza']:.2%}", flush=True)
                print(f"    Pesos óptimos: Prophet={self.pesos['prophet']:.2f}, SARIMA={self.pesos['sarima']:.2f}", flush=True)
            else:
                # SARIMA holdout falló, usar solo Prophet
                from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error
                mape_prophet = mean_absolute_percentage_error(y_real, pred_prophet_val)
                rmse_prophet = np.sqrt(mean_squared_error(y_real, pred_prophet_val))
                self.pesos = {'prophet': 1.0, 'sarima': 0.0}
                self.metricas = {
                    'mape_ensemble': mape_prophet,
                    'mape_prophet': mape_prophet,
                    'mape_sarima': None,
                    'rmse': rmse_prophet,
                    'confianza': max(0.0, 1.0 - mape_prophet)
                }
                print(f"    ✓ MAPE Prophet (solo, SARIMA holdout falló): {mape_prophet:.2%}", flush=True)
        else:
            from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error
            mape_prophet = mean_absolute_percentage_error(y_real, pred_prophet_val)
            rmse_prophet = np.sqrt(mean_squared_error(y_real, pred_prophet_val))
            self.pesos = {'prophet': 1.0, 'sarima': 0.0}
            self.metricas = {
                'mape_ensemble': mape_prophet,
                'mape_prophet': mape_prophet,
                'rmse': rmse_prophet,
                'confianza': max(0.0, 1.0 - mape_prophet)
            }
            print(f"    ✓ MAPE Prophet (solo): {mape_prophet:.2%}", flush=True)
    
    def predecir(self, horizonte_dias, allow_negative=False):
        """Genera predicciones combinadas con intervalos estadísticos reales"""
        print(f"  → Generando predicciones {horizonte_dias} días...", flush=True)
        
        # Prophet
        future = self.modelo_prophet.make_future_dataframe(periods=horizonte_dias, freq='D')
        pred_prophet = self.modelo_prophet.predict(future)
        pred_prophet = pred_prophet.tail(horizonte_dias)
        
        # SARIMA
        if self.modelo_sarima:
            try:
                pred_sarima = self.modelo_sarima.predict(n_periods=horizonte_dias)
                # Obtener intervalos de confianza REALES de SARIMA (no ±20%)
                sarima_conf = self.modelo_sarima.predict(n_periods=horizonte_dias, return_conf_int=True)
                sarima_lower = sarima_conf[1][:, 0] if len(sarima_conf) > 1 else pred_sarima * 0.8
                sarima_upper = sarima_conf[1][:, 1] if len(sarima_conf) > 1 else pred_sarima * 1.2
                
                # Ensemble ponderado
                predicciones_ensemble = (
                    self.pesos['prophet'] * pred_prophet['yhat'].values +
                    self.pesos['sarima'] * pred_sarima
                )
                intervalo_inferior = (
                    self.pesos['prophet'] * pred_prophet['yhat_lower'].values +
                    self.pesos['sarima'] * sarima_lower
                )
                intervalo_superior = (
                    self.pesos['prophet'] * pred_prophet['yhat_upper'].values +
                    self.pesos['sarima'] * sarima_upper
                )
            except Exception:
                predicciones_ensemble = pred_prophet['yhat'].values
                intervalo_inferior = pred_prophet['yhat_lower'].values
                intervalo_superior = pred_prophet['yhat_upper'].values
        else:
            predicciones_ensemble = pred_prophet['yhat'].values
            intervalo_inferior = pred_prophet['yhat_lower'].values
            intervalo_superior = pred_prophet['yhat_upper'].values
        
        # CLAMP: Para métricas que no pueden ser negativas (demanda, generación, embalses, etc.)
        if not allow_negative:
            predicciones_ensemble = np.maximum(predicciones_ensemble, 0.0)
            intervalo_inferior = np.maximum(intervalo_inferior, 0.0)
            intervalo_superior = np.maximum(intervalo_superior, 0.0)
        
        # Piso histórico configurable (ej: precio de bolsa nunca < 86 $/kWh)
        piso = self.config.get('piso_historico', 0.0)
        if piso > 0:
            predicciones_ensemble = np.maximum(predicciones_ensemble, piso)
            intervalo_inferior = np.maximum(intervalo_inferior, piso)
        
        # Crear DataFrame
        fechas_prediccion = pred_prophet['ds'].values
        
        df_predicciones = pd.DataFrame({
            'fecha_prediccion': fechas_prediccion,
            'valor_predicho': predicciones_ensemble,
            'intervalo_inferior': intervalo_inferior,
            'intervalo_superior': intervalo_superior
        })
        
        return df_predicciones


def cargar_datos_metrica(metrica_nombre, config, fecha_inicio='2020-01-01'):
    """Carga datos históricos de una métrica específica"""
    # Ventana limitada: usar solo últimos N meses si configurado
    ventana = config.get('ventana_meses')
    if ventana:
        from dateutil.relativedelta import relativedelta
        fecha_inicio = (datetime.now() - relativedelta(months=ventana)).strftime('%Y-%m-%d')
    print(f"\n📊 Cargando datos históricos para {metrica_nombre} (desde {fecha_inicio})...")
    
    conn = get_postgres_connection()
    
    # Configuración de filtrado de entidad
    entidad_filtro = config.get('entidad_filtro')        # Filtro estricto (solo esa entidad)
    prefer_sistema = config.get('prefer_sistema', False)  # Preferir Sistema, fallback a SUM(Agentes)
    
    # Construir cláusula WHERE adicional
    if entidad_filtro:
        extra_clause = "AND entidad = %s"
        extra_params = (entidad_filtro,)
    else:
        extra_clause = ""
        extra_params = ()
    
    # Función de agregación según tipo
    if config['tipo'] in ('promedio_ponderado', 'promedio_diario'):
        agg_fn = 'AVG'
    else:
        agg_fn = 'SUM'
    
    # Query con lógica anti doble-conteo
    if prefer_sistema and not entidad_filtro:
        # Preferir Sistema cuando existe; si no existe, SUM(todos=Agentes)
        # Evita doble conteo en días que tienen Sistema + Agentes simultáneamente
        query = f"""
        SELECT fecha,
          CASE
            WHEN MAX(CASE WHEN entidad='Sistema' THEN 1 ELSE 0 END) = 1
            THEN {agg_fn}(CASE WHEN entidad='Sistema' THEN valor_gwh END)
            ELSE {agg_fn}(valor_gwh)
          END as valor
        FROM metrics
        WHERE metrica = %s
          AND fecha >= %s
          AND valor_gwh > 0
        GROUP BY fecha
        ORDER BY fecha
        """
        params = (config['metricas'][0], fecha_inicio)
    else:
        # Query estándar (con o sin filtro de entidad)
        query = f"""
        SELECT fecha, {agg_fn}(valor_gwh) as valor
        FROM metrics
        WHERE metrica = %s
          AND fecha >= %s
          AND valor_gwh > 0
          {extra_clause}
        GROUP BY fecha
        ORDER BY fecha
        """
        params = (config['metricas'][0], fecha_inicio) + extra_params
    
    try:
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.sort_values('fecha')
        
        # ── FASE LIMPIEZA DATOS: Excluir datos parciales recientes ──
        # Los últimos 2-3 días de XM pueden venir parciales (DemaReal=45 GWh
        # cuando lo real es ~230 GWh). Detectamos outliers extremos en los
        # últimos 5 días comparando con la mediana de los 90 días previos.
        # Si un valor reciente es < 50% de la mediana, se descarta.
        # NOTA: Solo aplica a métricas de energía/volumen (tipo suma_diaria,
        # suma_embalses, agregado_por_recurso). NO aplica a precios ni
        # porcentajes, donde caídas de 50% son variación legítima de mercado.
        # Cambio: Protege contra datos parciales sin afectar series históricas.
        # Revertir: eliminar este bloque; el filtro valor_gwh > 0 sigue activo.
        tipos_con_filtro_parciales = ('suma_diaria', 'suma_embalses', 'agregado_por_recurso')
        if config['tipo'] in tipos_con_filtro_parciales and len(df) > 95:
            mediana_reciente = df['valor'].iloc[-95:-5].median()
            if mediana_reciente > 0:
                umbral_parcial = mediana_reciente * 0.5
                ultimos_5 = df.tail(5)
                parciales = ultimos_5[ultimos_5['valor'] < umbral_parcial]
                if len(parciales) > 0:
                    fechas_excl = parciales['fecha'].dt.date.tolist()
                    df = df[~df['fecha'].isin(parciales['fecha'])]
                    print(f"  ⚠️  Excluidos {len(parciales)} datos parciales recientes: {fechas_excl}")
                    print(f"      (umbral: {umbral_parcial:.2f}, mediana 90d: {mediana_reciente:.2f})")
        
        # Aplicar factor de escala si existe (ej: PorcVoluUtilDiar 0-1 → 0-100%)
        escala = config.get('escala_factor', 1)
        if escala != 1:
            df['valor'] = df['valor'] * escala
            print(f"  ℹ️  Escala aplicada: ×{escala}")
        
        if len(df) > 0:
            print(f"  ✓ Cargados {len(df)} registros ({df['fecha'].min().date()} a {df['fecha'].max().date()})")
            print(f"    Promedio: {df['valor'].mean():.2f} {config['unidad']}")
            return df
        else:
            print(f"  ❌ No hay datos para {metrica_nombre}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error cargando datos: {e}")
        conn.close()
        return None


def guardar_predicciones_bd(metrica_nombre, df_predicciones, config):
    """Guarda predicciones en la tabla predictions con métricas de calidad (FASE 7B)"""
    print(f"  → Guardando {len(df_predicciones)} predicciones de {metrica_nombre}...")
    
    conn = get_postgres_connection()
    cursor = conn.cursor()
    
    try:
        # Limpiar predicciones antiguas de esta métrica
        cursor.execute("DELETE FROM predictions WHERE fuente = %s", (metrica_nombre,))
        
        # FASE 7B: Confianza real basada en MAPE + métricas de error
        confianza_real = config.get('confianza_real', CONFIANZA)
        mape_val = config.get('mape_real')    # Nuevo: MAPE real del ensemble
        rmse_val = config.get('rmse_real')     # Nuevo: RMSE real del ensemble
        
        # Cast numpy → Python float para psycopg2
        confianza_real = float(confianza_real) if confianza_real is not None else CONFIANZA
        mape_val = float(mape_val) if mape_val is not None else None
        rmse_val = float(rmse_val) if rmse_val is not None else None
        
        print(f"    métricas: confianza={confianza_real:.2f}, "
              f"mape={f'{mape_val:.4f}' if mape_val is not None else 'N/A'}, "
              f"rmse={f'{rmse_val:.2f}' if rmse_val is not None else 'N/A'}")
        
        # Insertar nuevas predicciones
        for _, row in df_predicciones.iterrows():
            cursor.execute("""
                INSERT INTO predictions (
                    fecha_prediccion, fecha_generacion, fuente,
                    valor_gwh_predicho, intervalo_inferior, intervalo_superior,
                    horizonte_dias, modelo, confianza, mape, rmse
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row['fecha_prediccion'],
                datetime.now(),
                metrica_nombre,
                float(row['valor_predicho']),
                float(row['intervalo_inferior']),
                float(row['intervalo_superior']),
                HORIZONTE_DIAS,
                MODELO_VERSION,
                confianza_real,
                mape_val,
                rmse_val
            ))
        
        conn.commit()
        print(f"    ✓ {len(df_predicciones)} predicciones guardadas")
        return True
        
    except Exception as e:
        print(f"    ❌ Error guardando: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def main():
    """Función principal - Genera predicciones para todas las métricas estratégicas"""
    print("\n" + "="*70)
    print("🇨🇴 SISTEMA DE PREDICCIONES ESTRATÉGICAS - MINISTERIO DE ENERGÍA")
    print("   Viceministro de Energía - República de Colombia")
    print("="*70)
    print(f"   Modelo: {MODELO_VERSION}")
    print(f"   Horizonte: {HORIZONTE_DIAS} días (3 meses)")
    print(f"   Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Verificar conexión
    try:
        conn = get_postgres_connection()
        cur = conn.cursor()
        cur.execute("SELECT current_database()")
        db_name = cur.fetchone()[0]
        print(f"✅ Conectado a PostgreSQL: {db_name}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error conectando a PostgreSQL: {e}")
        return
    
    resultados = []
    total_predicciones = 0
    
    # Procesar cada categoría de métricas
    for categoria, config in METRICAS_CONFIG.items():
        
        # Saltar generación si ya está implementado
        if config.get('ya_implementado'):
            print(f"\n{'='*70}")
            print(f"✅ {categoria}: YA IMPLEMENTADO")
            print(f"{'='*70}")
            continue
        
        print(f"\n{'='*70}")
        print(f"🔧 Procesando: {categoria}")
        print(f"   Descripción: {config['descripcion']}")
        print(f"   Criticidad: {config['criticidad']}")
        print("="*70)
        
        try:
            # 1. Cargar datos históricos
            df = cargar_datos_metrica(categoria, config)
            
            # ── Umbral mínimo de datos ──
            # Métricas con ventana limitada (ej: PRECIO_BOLSA, ventana_meses=8)
            # pueden tener <365 registros. Aceptar ≥120 registros (~4 meses)
            # para poder entrenar Prophet con estacionalidad semanal.
            # Cambio: permite entrenar métricas con ventana corta configurada.
            # Revertir: cambiar min_registros a 365.
            min_registros = 120 if config.get('ventana_meses') else 365
            
            if df is None or len(df) < min_registros:
                print(f"  ⚠️  Datos insuficientes para {categoria} (< {min_registros} registros)")
                continue
            
            # 2. Crear predictor
            predictor = PredictorMetricaSectorial(categoria, config)
            
            # 3. Preparar datos
            df_prophet = df[['fecha', 'valor']].copy()
            df_prophet.columns = ['ds', 'y']
            df_prophet = df_prophet[df_prophet['y'] > 0]  # Eliminar valores negativos/cero
            
            serie_sarima = df.set_index('fecha')['valor'].asfreq('D')
            
            # 4. Entrenar modelos
            predictor.entrenar_prophet(df_prophet)
            if not config.get('solo_prophet', False):
                predictor.entrenar_sarima(serie_sarima)
            else:
                print(f"  ℹ️  Modo solo-Prophet para {categoria} (SARIMA deshabilitado)", flush=True)
            
            # 5. Validar con holdout REAL
            predictor.validar_y_generar(df_prophet, serie_sarima)
            
            # 6. Predecir (PRECIO_BOLSA puede tener valores que fluctúan, pero no negativos)
            allow_neg = False  # Ninguna métrica energética debe ser negativa
            df_pred = predictor.predecir(HORIZONTE_DIAS, allow_negative=allow_neg)
            
            # 7. Guardar en BD — FASE 7B: propagar mape y rmse al INSERT
            config['confianza_real'] = predictor.metricas.get('confianza', CONFIANZA)
            mape_real = predictor.metricas.get('mape_ensemble', -1)
            config['mape_real'] = mape_real if mape_real is not None and mape_real >= 0 else None
            config['rmse_real'] = predictor.metricas.get('rmse')
            if guardar_predicciones_bd(categoria, df_pred, config):
                total_predicciones += len(df_pred)
                mape_real = predictor.metricas.get('mape_ensemble', -1)
                resultados.append({
                    'categoria': categoria,
                    'predicciones': len(df_pred),
                    'mape': mape_real,
                    'status': 'OK'
                })
                if mape_real >= 0:
                    print(f"  ✅ {categoria} completado — MAPE real: {mape_real:.2%}\n")
                else:
                    print(f"  ✅ {categoria} completado (sin validación holdout)\n")
            else:
                resultados.append({
                    'categoria': categoria,
                    'status': 'ERROR_BD'
                })
            
        except Exception as e:
            print(f"❌ Error procesando {categoria}: {e}\n")
            resultados.append({
                'categoria': categoria,
                'status': 'ERROR',
                'error': str(e)
            })
    
    # Reporte final
    print("\n" + "="*70)
    print("📊 REPORTE FINAL - PREDICCIONES SECTOR ENERGÉTICO")
    print("="*70)
    
    exitosas = [r for r in resultados if r.get('status') == 'OK']
    fallidas = [r for r in resultados if r.get('status') != 'OK']
    
    print(f"\n✅ Métricas procesadas exitosamente: {len(exitosas)}")
    for r in exitosas:
        mape_str = f"MAPE={r['mape']:.2%}" if r.get('mape', -1) >= 0 else "MAPE=N/A"
        print(f"   • {r['categoria']:30s} - {r['predicciones']} predicciones ({mape_str})")
    
    if fallidas:
        print(f"\n❌ Métricas con errores: {len(fallidas)}")
        for r in fallidas:
            print(f"   • {r['categoria']:30s} - {r.get('status', 'ERROR')}")
    
    print(f"\n💾 TOTAL PREDICCIONES GENERADAS: {total_predicciones}")
    print(f"📅 Horizonte: {HORIZONTE_DIAS} días")
    print("="*70)
    print("\n✅ Proceso completado\n")


if __name__ == "__main__":
    main()

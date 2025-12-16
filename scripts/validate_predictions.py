#!/usr/bin/env python3
"""
Script de Validación y Monitoreo de Predicciones
Compara predicciones generadas vs datos reales observados
Calcula métricas de precisión y ajusta modelos si es necesario

Ejecutar diariamente para monitorear accuracy del sistema
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.metrics import mean_absolute_percentage_error, mean_absolute_error, mean_squared_error
import json

# Configuración
DB_PATH = '/home/admonctrlxm/server/portal_energetico.db'
LOG_PATH = '/home/admonctrlxm/server/logs/validation_metrics.json'
UMBRAL_MAPE = 0.15  # 15% - Si supera este valor, alertar
DIAS_VALIDACION = 30  # Validar predicciones de los últimos 30 días

class ValidadorPredicciones:
    """Valida predicciones vs datos reales y calcula métricas"""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.metricas = {}
        self.alertas = []
        
    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()
    
    def obtener_predicciones_historicas(self, dias=DIAS_VALIDACION):
        """Obtiene predicciones que ya tienen datos reales disponibles"""
        fecha_inicio = (datetime.now() - timedelta(days=dias)).strftime('%Y-%m-%d')
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        
        query = """
        SELECT fecha_prediccion, fuente, valor_gwh_predicho, 
               intervalo_inferior, intervalo_superior,
               fecha_generacion, modelo
        FROM predictions
        WHERE fecha_prediccion BETWEEN ? AND ?
        ORDER BY fecha_prediccion, fuente
        """
        
        df_pred = pd.read_sql_query(query, self.conn, params=(fecha_inicio, fecha_hoy))
        df_pred['fecha_prediccion'] = pd.to_datetime(df_pred['fecha_prediccion'])
        
        return df_pred
    
    def obtener_datos_reales(self, fecha_inicio, fecha_fin):
        """Obtiene datos reales observados para comparación"""
        tipo_mapa = {
            'Hidráulica': 'HIDRAULICA',
            'Térmica': 'TERMICA',
            'Eólica': 'EOLICA',
            'Solar': 'SOLAR',
            'Biomasa': 'COGENERADOR'
        }
        
        datos_reales = []
        
        for fuente, tipo in tipo_mapa.items():
            query = """
            SELECT m.fecha, SUM(m.valor_gwh) as valor_real
            FROM metrics m
            INNER JOIN catalogos c ON m.recurso = c.codigo
            WHERE m.metrica = 'Gene'
              AND c.catalogo = 'ListadoRecursos'
              AND c.tipo = ?
              AND m.fecha BETWEEN ? AND ?
              AND m.valor_gwh > 0
            GROUP BY m.fecha
            ORDER BY m.fecha
            """
            
            df = pd.read_sql_query(query, self.conn, params=(tipo, fecha_inicio, fecha_fin))
            if not df.empty:
                df['fuente'] = fuente
                df['fecha'] = pd.to_datetime(df['fecha'])
                datos_reales.append(df)
        
        if datos_reales:
            return pd.concat(datos_reales, ignore_index=True)
        else:
            return pd.DataFrame()
    
    def calcular_metricas(self, df_pred, df_real):
        """Calcula métricas de precisión por fuente"""
        metricas_por_fuente = {}
        
        # Merge predicciones con datos reales
        df_merged = pd.merge(
            df_pred,
            df_real,
            left_on=['fecha_prediccion', 'fuente'],
            right_on=['fecha', 'fuente'],
            how='inner'
        )
        
        if df_merged.empty:
            print("⚠️  No hay datos suficientes para validar")
            return metricas_por_fuente
        
        for fuente in df_merged['fuente'].unique():
            df_fuente = df_merged[df_merged['fuente'] == fuente]
            
            if len(df_fuente) < 5:
                continue
            
            y_true = df_fuente['valor_real'].values
            y_pred = df_fuente['valor_gwh_predicho'].values
            
            # Calcular métricas
            mape = mean_absolute_percentage_error(y_true, y_pred)
            mae = mean_absolute_error(y_true, y_pred)
            rmse = np.sqrt(mean_squared_error(y_true, y_pred))
            
            # Calcular cobertura de intervalos de confianza
            dentro_intervalo = (
                (df_fuente['valor_real'] >= df_fuente['intervalo_inferior']) &
                (df_fuente['valor_real'] <= df_fuente['intervalo_superior'])
            ).mean()
            
            metricas_por_fuente[fuente] = {
                'mape': mape,
                'mae': mae,
                'rmse': rmse,
                'cobertura_ic95': dentro_intervalo,
                'n_observaciones': len(df_fuente),
                'promedio_real': y_true.mean(),
                'promedio_predicho': y_pred.mean(),
                'sesgo': (y_pred.mean() - y_true.mean()) / y_true.mean() if y_true.mean() > 0 else 0
            }
            
            # Generar alertas si MAPE > umbral
            if mape > UMBRAL_MAPE:
                self.alertas.append({
                    'fuente': fuente,
                    'metrica': 'MAPE',
                    'valor': mape,
                    'umbral': UMBRAL_MAPE,
                    'mensaje': f"Precisión de {fuente} por debajo del umbral: {mape:.1%} > {UMBRAL_MAPE:.1%}"
                })
        
        return metricas_por_fuente
    
    def guardar_metricas(self, metricas):
        """Guarda métricas en archivo JSON para historial"""
        try:
            # Cargar historial existente
            try:
                with open(LOG_PATH, 'r') as f:
                    historial = json.load(f)
            except FileNotFoundError:
                historial = []
            
            # Agregar nuevas métricas
            registro = {
                'fecha_validacion': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'metricas': metricas,
                'alertas': self.alertas
            }
            
            historial.append(registro)
            
            # Mantener solo últimos 90 días
            if len(historial) > 90:
                historial = historial[-90:]
            
            # Guardar
            with open(LOG_PATH, 'w') as f:
                json.dump(historial, f, indent=2)
            
            print(f"✅ Métricas guardadas en {LOG_PATH}")
            
        except Exception as e:
            print(f"❌ Error guardando métricas: {e}")
    
    def generar_reporte(self, metricas):
        """Genera reporte de validación"""
        print("\n" + "="*70)
        print("📊 REPORTE DE VALIDACIÓN DE PREDICCIONES")
        print("="*70)
        print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Periodo validado: Últimos {DIAS_VALIDACION} días")
        print("="*70)
        
        if not metricas:
            print("⚠️  No hay datos suficientes para validar")
            return
        
        # Tabla de métricas
        print("\n{:<15} {:>10} {:>10} {:>10} {:>12} {:>8}".format(
            "FUENTE", "MAPE", "MAE (GWh)", "RMSE", "Cobertura IC", "N Obs"
        ))
        print("-" * 70)
        
        for fuente, m in metricas.items():
            estado = "✅" if m['mape'] <= UMBRAL_MAPE else "⚠️ "
            print("{} {:<13} {:>9.1%} {:>10.2f} {:>10.2f} {:>11.1%} {:>8d}".format(
                estado, fuente, m['mape'], m['mae'], m['rmse'], 
                m['cobertura_ic95'], m['n_observaciones']
            ))
        
        # MAPE promedio
        mape_promedio = np.mean([m['mape'] for m in metricas.values()])
        print("-" * 70)
        print(f"{'PROMEDIO':<15} {mape_promedio:>9.1%}")
        print("="*70)
        
        # Alertas
        if self.alertas:
            print("\n⚠️  ALERTAS:")
            for alerta in self.alertas:
                print(f"  • {alerta['mensaje']}")
        else:
            print("\n✅ Todas las fuentes dentro del umbral de precisión")
        
        # Recomendaciones
        print("\n📋 RECOMENDACIONES:")
        for fuente, m in metricas.items():
            if m['mape'] > UMBRAL_MAPE:
                if abs(m['sesgo']) > 0.1:
                    direccion = "sobreestima" if m['sesgo'] > 0 else "subestima"
                    print(f"  • {fuente}: Modelo {direccion} en {abs(m['sesgo']):.1%} - Reentrenar con datos recientes")
                else:
                    print(f"  • {fuente}: Alta variabilidad - Considerar features adicionales (clima, demanda)")
        
        print("\n" + "="*70)
    
    def validar(self):
        """Ejecuta validación completa"""
        print("🔍 Iniciando validación de predicciones...")
        
        # Obtener predicciones históricas
        df_pred = self.obtener_predicciones_historicas()
        
        if df_pred.empty:
            print("⚠️  No hay predicciones históricas para validar")
            return
        
        # Obtener datos reales
        fecha_inicio = df_pred['fecha_prediccion'].min().strftime('%Y-%m-%d')
        fecha_fin = df_pred['fecha_prediccion'].max().strftime('%Y-%m-%d')
        
        df_real = self.obtener_datos_reales(fecha_inicio, fecha_fin)
        
        if df_real.empty:
            print("⚠️  No hay datos reales disponibles para comparación")
            return
        
        # Calcular métricas
        metricas = self.calcular_metricas(df_pred, df_real)
        
        # Generar reporte
        self.generar_reporte(metricas)
        
        # Guardar métricas
        self.guardar_metricas(metricas)
        
        return metricas


def main():
    """Función principal de validación"""
    validador = ValidadorPredicciones()
    metricas = validador.validar()
    
    # Verificar si necesita reentrenamiento
    if validador.alertas:
        print("\n⚙️  ACCIÓN RECOMENDADA:")
        print("   Ejecutar reentrenamiento: python scripts/train_predictions.py")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           VALIDACIÓN POST-ETL: API vs SQLite                 ║
║                                                              ║
║  Compara datos en SQLite contra API XM para detectar        ║
║  inconsistencias, datos inventados o corrupción.            ║
║                                                              ║
║  Uso: python3 scripts/validar_etl.py                        ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Tuple

# Importar desde utils la función para obtener API XM
from utils._xm import get_objetoAPI

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class ValidadorETL:
    """Valida que los datos en SQLite coincidan con la API XM"""
    
    def __init__(self, db_path: str = 'portal_energetico.db'):
        # Si es ruta relativa, construir desde directorio del script
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.path.dirname(__file__), '..', db_path)
        
        self.db_path = db_path
        self.api = get_objetoAPI()
        if not self.api:
            logger.error("❌ No se pudo inicializar la API XM")
        self.resultados = {
            'metricas_validadas': 0,
            'metricas_correctas': 0,
            'metricas_incorrectas': 0,
            'errores': []
        }
    
    def conectar_sqlite(self):
        """Conecta a la base de datos SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            logger.error(f"❌ Error al conectar a SQLite: {e}")
            return None
    
    def obtener_ultima_fecha_sqlite(self, conn, metrica: str, entidad: str) -> Tuple[datetime, float]:
        """Obtiene la última fecha y valor de SQLite"""
        try:
            cursor = conn.cursor()
            # La tabla se llama 'metrics', los campos son 'fecha', 'metrica', 'entidad', 'valor_gwh'
            cursor.execute("""
                SELECT fecha, valor_gwh 
                FROM metrics 
                WHERE metrica = ? AND entidad = ?
                ORDER BY fecha DESC 
                LIMIT 1
            """, (metrica, entidad))
            
            row = cursor.fetchone()
            if row:
                # Convertir fecha a datetime object (puede venir como string o ya ser datetime/Timestamp)
                fecha = row['fecha']
                if isinstance(fecha, str):
                    fecha_dt = datetime.strptime(fecha, '%Y-%m-%d')
                elif hasattr(fecha, 'to_pydatetime'):  # pandas Timestamp
                    fecha_dt = fecha.to_pydatetime()
                else:
                    fecha_dt = fecha  # Ya es datetime
                return fecha_dt, row['valor_gwh']
            return None, None
        except Exception as e:
            logger.error(f"❌ Error al consultar SQLite: {e}")
            return None, None
    
    def obtener_ultima_fecha_api(self, metrica: str, entidad: str) -> Tuple[datetime, float]:
        """Obtiene la última fecha y valor de la API XM"""
        try:
            # Calcular rango de fechas (últimos 7 días)
            fecha_fin = datetime.now()
            fecha_inicio = fecha_fin - timedelta(days=7)
            
            # Consultar API
            df = self.api.request_data(
                metrica, 
                entidad,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
            
            if df is None or df.empty:
                return None, None
            
            # Obtener última fecha disponible
            df = df.sort_values('Date', ascending=False)
            ultima_fila = df.iloc[0]
            
            fecha = ultima_fila['Date']
            # Convertir a datetime si es string o Timestamp
            if isinstance(fecha, str):
                fecha_dt = datetime.strptime(fecha, '%Y-%m-%d')
            elif hasattr(fecha, 'to_pydatetime'):
                fecha_dt = fecha.to_pydatetime()
            else:
                fecha_dt = fecha
                
            valor = ultima_fila.get('Values_Hour24', ultima_fila.get('Values_Energy', None))
            
            return fecha_dt, valor
        except Exception as e:
            logger.error(f"❌ Error al consultar API XM ({metrica}/{entidad}): {e}")
            return None, None
    
    def validar_metrica(self, metrica: str, entidad: str, nombre_amigable: str) -> bool:
        """Valida una métrica específica comparando SQLite vs API"""
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 Validando: {nombre_amigable}")
        logger.info(f"   Métrica: {metrica}/{entidad}")
        logger.info(f"{'='*60}")
        
        self.resultados['metricas_validadas'] += 1
        
        # Conectar a SQLite
        conn = self.conectar_sqlite()
        if not conn:
            self.resultados['errores'].append(f"{nombre_amigable}: Error de conexión SQLite")
            return False
        
        try:
            # Obtener datos de SQLite
            fecha_sqlite, valor_sqlite = self.obtener_ultima_fecha_sqlite(conn, metrica, entidad)
            logger.info(f"📦 SQLite: fecha={fecha_sqlite}, valor={valor_sqlite}")
            
            # Obtener datos de API
            fecha_api, valor_api = self.obtener_ultima_fecha_api(metrica, entidad)
            logger.info(f"🌐 API XM:  fecha={fecha_api}, valor={valor_api}")
            
            # Validar
            if fecha_sqlite is None or fecha_api is None:
                logger.warning(f"⚠️  {nombre_amigable}: Datos no disponibles")
                self.resultados['errores'].append(f"{nombre_amigable}: Datos no disponibles")
                return False
            
            # Comparar fechas (convertir a date para comparar solo día, mes, año)
            fecha_sqlite_date = fecha_sqlite.date() if hasattr(fecha_sqlite, 'date') else fecha_sqlite
            fecha_api_date = fecha_api.date() if hasattr(fecha_api, 'date') else fecha_api
            
            if fecha_sqlite_date == fecha_api_date:
                logger.info(f"✅ {nombre_amigable}: Fechas coinciden")
                
                # Comparar valores (con tolerancia del 0.1%)
                if valor_sqlite is not None and valor_api is not None:
                    diferencia_pct = abs(valor_sqlite - valor_api) / valor_api * 100 if valor_api != 0 else 0
                    if diferencia_pct < 0.1:
                        logger.info(f"✅ {nombre_amigable}: Valores coinciden (diff: {diferencia_pct:.4f}%)")
                        self.resultados['metricas_correctas'] += 1
                        return True
                    else:
                        logger.error(f"❌ {nombre_amigable}: Valores difieren {diferencia_pct:.2f}%")
                        logger.error(f"   SQLite: {valor_sqlite}, API: {valor_api}")
                        self.resultados['errores'].append(
                            f"{nombre_amigable}: Valores difieren {diferencia_pct:.2f}%"
                        )
                        self.resultados['metricas_incorrectas'] += 1
                        return False
            else:
                # Verificar si SQLite está adelantado (datos inventados)
                if fecha_sqlite_date > fecha_api_date:
                    logger.error(f"❌ {nombre_amigable}: ¡SQLite tiene fecha FUTURA!")
                    logger.error(f"   SQLite: {fecha_sqlite_date}, API: {fecha_api_date}")
                    self.resultados['errores'].append(
                        f"{nombre_amigable}: Fecha inventada (SQLite: {fecha_sqlite_date}, API: {fecha_api_date})"
                    )
                    self.resultados['metricas_incorrectas'] += 1
                    return False
                else:
                    # SQLite está atrasado (no es crítico, puede ser actualización pendiente)
                    dias_atraso = (fecha_api - fecha_sqlite).days
                    logger.warning(f"⚠️  {nombre_amigable}: SQLite {dias_atraso} días atrasado")
                    logger.warning(f"   SQLite: {fecha_sqlite.strftime('%Y-%m-%d')}, API: {fecha_api.strftime('%Y-%m-%d')}")
                    
                    if dias_atraso > 2:
                        self.resultados['errores'].append(
                            f"{nombre_amigable}: {dias_atraso} días atrasado"
                        )
                        self.resultados['metricas_incorrectas'] += 1
                        return False
                    else:
                        # Atraso menor a 2 días es aceptable
                        self.resultados['metricas_correctas'] += 1
                        return True
        
        except Exception as e:
            logger.error(f"❌ Error al validar {nombre_amigable}: {e}")
            self.resultados['errores'].append(f"{nombre_amigable}: {str(e)}")
            self.resultados['metricas_incorrectas'] += 1
            return False
        finally:
            conn.close()
    
    def validar_todo(self) -> bool:
        """Valida todas las métricas críticas"""
        logger.info("\n" + "="*60)
        logger.info("🔍 VALIDACIÓN POST-ETL: API XM vs SQLite")
        logger.info("="*60)
        logger.info(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Métricas críticas a validar (entidad debe coincidir con API XM)
        metricas = [
            ('Gene', 'Sistema', 'Generación Sistema'),
            ('DemaCome', 'Sistema', 'Demanda Comercial'),
            ('AporEner', 'Sistema', 'Aportes Energía'),
            ('VoluUtilDiarEner', 'Embalse', 'Volumen Útil Diario'),
            ('CapaUtilDiarEner', 'Embalse', 'Capacidad Útil Diario'),
        ]
        
        resultados = []
        for metrica, entidad, nombre in metricas:
            resultado = self.validar_metrica(metrica, entidad, nombre)
            resultados.append(resultado)
        
        # Reporte final
        logger.info("\n" + "="*60)
        logger.info("📊 REPORTE FINAL DE VALIDACIÓN")
        logger.info("="*60)
        logger.info(f"✅ Métricas validadas: {self.resultados['metricas_validadas']}")
        logger.info(f"✅ Métricas correctas: {self.resultados['metricas_correctas']}")
        logger.info(f"❌ Métricas incorrectas: {self.resultados['metricas_incorrectas']}")
        
        if self.resultados['errores']:
            logger.info(f"\n🔴 ERRORES DETECTADOS ({len(self.resultados['errores'])}):")
            for error in self.resultados['errores']:
                logger.info(f"   - {error}")
        
        # Calcular tasa de éxito
        tasa_exito = (self.resultados['metricas_correctas'] / 
                     self.resultados['metricas_validadas'] * 100)
        logger.info(f"\n📈 Tasa de éxito: {tasa_exito:.1f}%")
        logger.info("="*60)
        
        # Retornar True si todas las métricas están correctas
        return all(resultados)


def main():
    """Función principal"""
    validador = ValidadorETL()
    exito = validador.validar_todo()
    
    # Código de salida
    sys.exit(0 if exito else 1)


if __name__ == '__main__':
    main()

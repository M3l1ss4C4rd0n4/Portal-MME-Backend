#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script: Actualización automática de datos XM en ArcGIS Online
Usuario ArcGIS: melissacardona2
Fecha: 2026-02-06

Descripción:
    Extrae datos diarios de XM Colombia (Generación, Precio de Bolsa, Volumen de Embalses)
    y los publica/actualiza en ArcGIS Online para visualización en dashboards.

Uso:
    python actualizar_datos_xm_online.py [--dry-run]

Requisitos:
    pip install pydataxm arcgis pandas python-dotenv
"""

import sys
import os
import logging
import argparse
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from pydataxm.pydataxm import ReadDB
from arcgis.gis import GIS
from arcgis.geometry import Point
from arcgis.features import FeatureLayer, GeoAccessor, GeoSeriesAccessor

# Determinar archivo .env (soporta --env-file para múltiples cuentas)
_env_file = Path(__file__).parent / '.env'
for _i, _arg in enumerate(sys.argv):
    if _arg == '--env-file' and _i + 1 < len(sys.argv):
        _env_file = Path(sys.argv[_i + 1])
        if not _env_file.is_absolute():
            _env_file = Path(__file__).parent / _env_file
        break

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_file, override=True)
    print(f"📄 Usando env: {_env_file.name}")
except ImportError:
    pass

# ============================================
# CONFIGURACIÓN - CREDENCIALES
# ============================================

# IMPORTANTE: Por seguridad, usa variables de entorno
# Crea un archivo .env en el mismo directorio con:
# ARCGIS_PORTAL_URL=https://arcgisenterprise.minenergia.gov.co/portal/
# ARCGIS_USERNAME=Vice_Energia
# ARCGIS_PASSWORD=Survey123+
# FEATURE_LAYER_ID=id_obtenido_primera_vez

ARCGIS_PORTAL_URL = os.getenv("ARCGIS_PORTAL_URL", "https://arcgisenterprise.minenergia.gov.co/portal/")
ARCGIS_USERNAME = os.getenv("ARCGIS_USERNAME", "Vice_Energia")
ARCGIS_PASSWORD = os.getenv("ARCGIS_PASSWORD", "Survey123+")

# ID del Feature Layer (obtenido después de la primera ejecución)
FEATURE_LAYER_ID = os.getenv("FEATURE_LAYER_ID", None)

# Configuración de fechas (días hacia atrás para extraer)
DIAS_ATRAS = int(os.getenv("DIAS_ATRAS", "7"))

# Ubicación geográfica (Bogotá - Centro de Colombia)
BOGOTA_COORDS = {"x": -74.0721, "y": 4.7110, "spatialReference": {"wkid": 4326}}

# Configuración de logging y archivos
BASE_DIR = Path(__file__).parent.parent.parent  # /home/admonctrlxm/server
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "actualizacion_xm_arcgis.log"

# Directorio para guardar copia permanente del CSV (sin backups)
DATA_DIR = BASE_DIR / "data"
CSV_OUTPUT_FILE = DATA_DIR / "metricas_xm_arcgis.csv"

# ============================================
# CONFIGURAR LOGGING Y DIRECTORIOS
# ============================================

LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# ============================================
# FUNCIONES
# ============================================

def validar_credenciales():
    """Valida que las credenciales estén configuradas"""
    if not ARCGIS_USERNAME or not ARCGIS_PASSWORD:
        logger.error("❌ Credenciales no configuradas. Configura las variables de entorno:")
        logger.error("   ARCGIS_USERNAME y ARCGIS_PASSWORD")
        raise ValueError("Credenciales de ArcGIS no configuradas")


# ============================================
# TRACKING PER-CUENTA: hash del CSV publicado
# ============================================
# Cada cuenta guarda el hash MD5 del CSV la última vez que publicó.
# Si otra cuenta actualizó el CSV pero esta no ha publicado aún,
# los hashes no coincidirán y se forzará la publicación.

def _hash_file(path: Path) -> str:
    """Calcula MD5 del contenido del archivo."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_file_path() -> Path:
    """Ruta del archivo de hash per-cuenta (ej. .last_xm_hash_Adminportal.txt)."""
    return Path(__file__).parent / f".last_xm_hash_{ARCGIS_USERNAME}.txt"


def csv_ya_publicado_para_esta_cuenta() -> bool:
    """Retorna True si el CSV local ya fue publicado por ESTA cuenta."""
    hash_path = _hash_file_path()
    if not hash_path.exists() or not CSV_OUTPUT_FILE.exists():
        return False
    try:
        last_hash = hash_path.read_text().strip()
        current_hash = _hash_file(CSV_OUTPUT_FILE)
        return last_hash == current_hash
    except Exception:
        return False


def registrar_publicacion():
    """Guarda el hash del CSV actual como 'publicado' para esta cuenta."""
    try:
        if CSV_OUTPUT_FILE.exists():
            current_hash = _hash_file(CSV_OUTPUT_FILE)
            _hash_file_path().write_text(current_hash)
            logger.info(f"📝 Hash de CSV registrado para {ARCGIS_USERNAME}")
    except Exception as e:
        logger.warning(f"⚠️  No se pudo guardar hash de publicación: {e}")


def verificar_datos_nuevos():
    """Verifica si hay datos nuevos disponibles en XM comparando con el CSV local"""
    try:
        if not CSV_OUTPUT_FILE.exists():
            logger.info("📄 No existe CSV previo. Se extraerán todos los datos.")
            return True, None
        
        # Leer CSV existente y obtener la última fecha
        df_existente = pd.read_csv(CSV_OUTPUT_FILE)
        if len(df_existente) == 0:
            logger.info("📄 CSV existente está vacío. Se extraerán datos.")
            return True, None
        
        ultima_fecha_str = df_existente['Fecha'].max()
        ultima_fecha = pd.to_datetime(ultima_fecha_str).date()
        
        # Verificar si hay datos más recientes disponibles en XM
        # Probar desde la fecha siguiente a la última hasta ayer
        fecha_probar = ultima_fecha + timedelta(days=1)
        fecha_ayer = (datetime.now() - timedelta(days=1)).date()
        
        logger.info(f"📅 Última fecha en CSV: {ultima_fecha}")
        logger.info(f"🔍 Verificando disponibilidad de datos desde {fecha_probar} hasta {fecha_ayer}...")
        
        if fecha_probar > fecha_ayer:
            logger.info(f"ℹ️  CSV ya está actualizado hasta {ultima_fecha}. No hay fechas nuevas que verificar.")
            return False, ultima_fecha
        
        # Verificar rápidamente si hay datos nuevos
        api = ReadDB()
        fecha_probar_str = fecha_probar.strftime('%Y-%m-%d')
        
        try:
            datos_test = api.request_data('Gene', 'Sistema', start_date=fecha_probar_str, end_date=fecha_probar_str)
            if datos_test is not None and len(datos_test) > 0:
                logger.info(f"✅ Datos nuevos disponibles desde {fecha_probar}!")
                return True, ultima_fecha
            else:
                logger.info(f"⏳ No hay datos nuevos disponibles aún. Última fecha: {ultima_fecha}")
                return False, ultima_fecha
        except Exception as e:
            logger.warning(f"⚠️  Error verificando datos: {e}. Continuando con actualización...")
            return True, ultima_fecha
            
    except Exception as e:
        logger.warning(f"⚠️  Error leyendo CSV existente: {e}. Continuando con actualización completa...")
        return True, None


#LO IMPORTANTE PARA LUISA
def extraer_datos_xm():
    """Extrae datos de la API XM"""
    try:
        logger.info("🚀 Iniciando extracción de datos de API XM...")
        
        api = ReadDB()
        
        # Obtener fechas recientes (como en el ETL del proyecto)
        fecha_fin = datetime.now() - timedelta(days=1)  # Ayer
        fecha_inicio = fecha_fin - timedelta(days=DIAS_ATRAS)
        
        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
        fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')
        
        logger.info(f"📅 Rango: {fecha_inicio_str} a {fecha_fin_str}")
        
        # Extraer métricas con manejo de errores individual
        metricas = {}
        
        try:
            logger.info("⏳ Extrayendo Generación Total del Sistema...")
            metricas['generacion'] = api.request_data(
                'Gene',
                'Sistema',
                start_date=fecha_inicio_str,
                end_date=fecha_fin_str
            )
            logger.info(f"   ✓ Generación: {len(metricas['generacion'])} registros")
        except Exception as e:
            logger.error(f"   ✗ Error extrayendo Generación: {e}")
            raise
        
        try:
            logger.info("⏳ Extrayendo Precio de Bolsa Nacional...")
            metricas['precio'] = api.request_data(
                'PrecBolsNaci',
                'Sistema',
                start_date=fecha_inicio_str,
                end_date=fecha_fin_str
            )
            logger.info(f"   ✓ Precio: {len(metricas['precio'])} registros")
        except Exception as e:
            logger.error(f"   ✗ Error extrayendo Precio: {e}")
            raise
        
        try:
            logger.info("⏳ Extrayendo Volumen Útil de Embalses...")
            metricas['volumen'] = api.request_data(
                'VoluUtilDiarEner',
                'Sistema',
                start_date=fecha_inicio_str,
                end_date=fecha_fin_str
            )
            logger.info(f"   ✓ Volumen: {len(metricas['volumen'])} registros")
        except Exception as e:
            logger.error(f"   ✗ Error extrayendo Volumen: {e}")
            raise
        
        try:
            logger.info("⏳ Extrayendo Capacidad Útil de Embalses...")
            metricas['capacidad'] = api.request_data(
                'CapaUtilDiarEner',
                'Sistema',
                start_date=fecha_inicio_str,
                end_date=fecha_fin_str
            )
            logger.info(f"   ✓ Capacidad: {len(metricas['capacidad'])} registros")
        except Exception as e:
            logger.error(f"   ✗ Error extrayendo Capacidad: {e}")
            raise
        
        # Validar que se extrajeron datos
        for nombre, df in metricas.items():
            if df is None or len(df) == 0:
                raise ValueError(f"No se extrajeron datos para {nombre}")
        
        logger.info("✅ Extracción completada exitosamente")
        
        return metricas['generacion'], metricas['precio'], metricas['volumen'], metricas['capacidad']
        
    except Exception as e:
        logger.error(f"❌ Error en extracción de datos XM: {str(e)}")
        raise


def procesar_datos(gene_df, precio_df, volumen_df, capacidad_df):
    """Procesa y combina datos de XM"""
    try:
        logger.info("🔧 Procesando y combinando datos...")
        
        # Validar DataFrames de entrada
        for nombre, df in [('Generación', gene_df), ('Precio', precio_df), 
                          ('Volumen', volumen_df), ('Capacidad', capacidad_df)]:
            if df is None or len(df) == 0:
                raise ValueError(f"DataFrame de {nombre} vacío")
            if 'Date' not in df.columns:
                raise ValueError(f"DataFrame de {nombre} sin columna Date")
        
        # Función para agregar valores horarios (columnas Values_HourXX)
        def agregar_valores_horarios(df, metrica_nombre):
            """Suma las 24 horas para obtener el total diario"""
            columnas_horarias = [col for col in df.columns if col.startswith('Values_Hour')]
            
            if not columnas_horarias:
                raise ValueError(f"No se encontraron columnas horarias en {metrica_nombre}")
            
            logger.info(f"   📊 Agregando {len(columnas_horarias)} horas para {metrica_nombre}")
            
            # Sumar todas las horas (convertir a numérico primero por si acaso)
            for col in columnas_horarias:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Total diario = suma de las 24 horas
            df['Values'] = df[columnas_horarias].sum(axis=1)
            
            return df[['Date', 'Values']]
        
        # Función para promediar valores horarios (para precios)
        def promediar_valores_horarios(df, metrica_nombre):
            """Promedia las 24 horas para obtener el precio promedio diario"""
            columnas_horarias = [col for col in df.columns if col.startswith('Values_Hour')]
            
            if not columnas_horarias:
                raise ValueError(f"No se encontraron columnas horarias en {metrica_nombre}")
            
            logger.info(f"   📊 Promediando {len(columnas_horarias)} horas para {metrica_nombre}")
            
            # Convertir a numérico
            for col in columnas_horarias:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Promedio diario de las 24 horas
            df['Values'] = df[columnas_horarias].mean(axis=1)
            
            return df[['Date', 'Values']]
        
        # Procesar cada métrica
        logger.info("   🔄 Procesando generación (suma horaria)...")
        gene_df = agregar_valores_horarios(gene_df, 'Generación')
        
        logger.info("   🔄 Procesando precio (promedio horario)...")
        precio_df = promediar_valores_horarios(precio_df, 'Precio')
        
        # Los datos de embalses ya son diarios (columna 'Value' en lugar de horarias)
        logger.info("   🔄 Procesando volumen embalses (ya es diario)...")
        if 'Value' in volumen_df.columns:
            volumen_df = volumen_df.rename(columns={'Value': 'Values'})[['Date', 'Values']]
        else:
            volumen_df = agregar_valores_horarios(volumen_df, 'Volumen')
        
        logger.info("   🔄 Procesando capacidad embalses (ya es diario)...")
        if 'Value' in capacidad_df.columns:
            capacidad_df = capacidad_df.rename(columns={'Value': 'Values'})[['Date', 'Values']]
        else:
            capacidad_df = agregar_valores_horarios(capacidad_df, 'Capacidad')
        
        # Calcular porcentaje de embalses
        logger.info("   📊 Calculando porcentaje de embalses...")
        embalse_df = pd.merge(
            volumen_df[['Date', 'Values']], 
            capacidad_df[['Date', 'Values']], 
            on='Date', 
            suffixes=('_vol', '_cap'),
            how='inner'
        )
        
        # Evitar división por cero
        embalse_df['PorcentajeEmbalse'] = (
            (embalse_df['Values_vol'] / embalse_df['Values_cap'].replace(0, pd.NA)) * 100
        )
        embalse_df = embalse_df[['Date', 'PorcentajeEmbalse']]
        
        # Combinar todas las métricas
        logger.info("   🔀 Combinando métricas...")
        df_combined = pd.merge(
            gene_df[['Date', 'Values']], 
            precio_df[['Date', 'Values']], 
            on='Date', 
            suffixes=('_gene', '_precio'),
            how='inner'
        )
        
        df_combined = pd.merge(
            df_combined, 
            embalse_df, 
            on='Date',
            how='inner'
        )
        
        # Convertir generación de Wh a GWh (como en el ETL)
        df_combined['Values_gene'] = df_combined['Values_gene'] / 1_000_000
        
        # Renombrar columnas con nombres descriptivos
        df_combined.rename(columns={
            'Values_gene': 'Generacion_GWh',
            'Values_precio': 'PrecioBolsa_COP_kWh',
            'Date': 'Fecha'
        }, inplace=True)
        
        # Limpiar valores nulos e infinitos
        df_combined = df_combined.replace([float('inf'), float('-inf')], pd.NA)
        df_combined = df_combined.dropna()
        
        # Convertir Fecha a datetime si no lo es
        if not pd.api.types.is_datetime64_any_dtype(df_combined['Fecha']):
            df_combined['Fecha'] = pd.to_datetime(df_combined['Fecha'])
        
        # Ordenar por fecha
        df_combined = df_combined.sort_values('Fecha')
        
        # Agregar columna de timestamp actualizado
        df_combined['FechaActualizacion'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Validar resultado final
        if len(df_combined) == 0:
            raise ValueError("No hay datos después del procesamiento")
        
        logger.info(f"✅ Procesamiento completado: {len(df_combined)} registros válidos")
        logger.info(f"   📅 Rango de fechas: {df_combined['Fecha'].min()} a {df_combined['Fecha'].max()}")
        logger.info(f"   📈 Generación promedio: {df_combined['Generacion_GWh'].mean():.2f} GWh")
        logger.info(f"   💰 Precio promedio: {df_combined['PrecioBolsa_COP_kWh'].mean():.2f} COP/kWh")
        logger.info(f"   🌊 Embalses promedio: {df_combined['PorcentajeEmbalse'].mean():.2f}%")
        
        return df_combined
        
    except Exception as e:
        logger.error(f"❌ Error procesando datos: {str(e)}")
        raise


def crear_spatial_dataframe(df_combined):
    """Convierte DataFrame a Spatial DataFrame con geometría"""
    try:
        logger.info("🗺️  Creando Spatial DataFrame...")
        
        # Agregar columnas de coordenadas
        df_combined['X'] = BOGOTA_COORDS['x']
        df_combined['Y'] = BOGOTA_COORDS['y']
        
        # Crear geometría Point para cada registro
        geometry = [Point(BOGOTA_COORDS) for _ in range(len(df_combined))]
        
        # Crear Spatial DataFrame usando GeoAccessor
        sedf = pd.DataFrame.spatial.from_xy(
            df=df_combined,
            x_column='X',
            y_column='Y',
            sr=4326
        )
        
        logger.info(f"✅ Spatial DataFrame creado con {len(sedf)} features")
        
        return sedf
        
    except Exception as e:
        logger.error(f"❌ Error creando Spatial DataFrame: {str(e)}")
        raise


def verificar_feature_layer_existe(gis, layer_id):
    """Verifica si existe el CSV Item"""
    try:
        if not layer_id:
            return False
        
        item = gis.content.get(layer_id)
        if item and item.type == 'CSV':
            logger.info(f"✓ CSV Item encontrado: {item.title}")
            return True
        else:
            logger.warning(f"⚠️  ID {layer_id} no corresponde a un CSV válido")
            return False
    except Exception as e:
        logger.warning(f"⚠️  No se pudo verificar CSV Item: {e}")
        return False


def publicar_nuevo_feature_layer(gis, sedf):
    """Publica un nuevo CSV Layer en ArcGIS Enterprise (compatible con cuentas estándar)"""
    import tempfile
    import os
    
    try:
        logger.info("📤 Publicando datos a ArcGIS Enterprise como CSV...")
        
        # Crear archivo CSV temporal
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
            csv_path = tmp.name
            # Convertir DataFrame a CSV (sin la columna geometry)
            df_export = sedf.copy()
            # Agregar columnas de latitud y longitud
            df_export['Latitude'] = df_export['SHAPE'].apply(lambda x: x.y if hasattr(x, 'y') else None)
            df_export['Longitude'] = df_export['SHAPE'].apply(lambda x: x.x if hasattr(x, 'x') else None)
            # Eliminar columna SHAPE
            df_export = df_export.drop(columns=['SHAPE'])
            df_export.to_csv(tmp.name, index=False)
        
        logger.info(f"   ✓ CSV temporal creado: {csv_path}")
        
        # Publicar solo CSV como Item (sin Feature Service)
        item_properties = {
            'title': 'Metricas Energia XM Colombia',
            'description': 'Datos de generación, precio de bolsa y porcentaje de embalses del Sistema Eléctrico Colombiano (fuente: XM). Incluye coordenadas para visualización en mapas.',
            'tags': 'energia, XM, Colombia, dashboard, generacion, precio, embalses, melissa, CSV',
            'type': 'CSV'
        }
        
        csv_item = gis.content.add(item_properties, data=csv_path)
        logger.info(f"   ✓ CSV publicado ID: {csv_item.id}")
        
        # Limpiar archivo temporal
        os.unlink(csv_path)
        
        logger.info("✅ CSV Layer publicado exitosamente!")
        logger.info(f"   📍 Título: {csv_item.title}")
        logger.info(f"   🔗 URL: {ARCGIS_PORTAL_URL}home/item.html?id={csv_item.id}")
        logger.info(f"   🆔 Item ID: {csv_item.id}")
        logger.info("")
        logger.info("=" * 70)
        logger.info("⚠️  ACCIÓN REQUERIDA: Guarda este ID para futuras actualizaciones")
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"Agrega esta línea a tu archivo .env:")
        logger.info(f"FEATURE_LAYER_ID={csv_item.id}")
        logger.info("")
        logger.info(f"O actualiza la variable en el script:")
        logger.info(f'FEATURE_LAYER_ID = "{csv_item.id}"')
        logger.info("=" * 70)
        logger.info("")
        logger.info("💡 NOTA: Este CSV puede visualizarse en mapas de ArcGIS Enterprise")
        logger.info("         agregando las columnas Latitude y Longitude como coordenadas.")
        logger.info("")
        
        return csv_item
        
    except Exception as e:
        logger.error(f"❌ Error publicando Feature Layer: {str(e)}")
        raise


def actualizar_feature_layer(gis, layer_id, sedf):
    """Actualiza un CSV Item existente con nuevos datos"""
    import tempfile
    import os
    
    try:
        logger.info("🔄 Actualizando CSV Item existente...")
        
        # Obtener el Item
        item = gis.content.get(layer_id)
        if not item:
            raise ValueError(f"No se encontró Item con ID: {layer_id}")
        
        logger.info(f"   📍 Título: {item.title}")
        logger.info(f"   🔗 URL: {ARCGIS_PORTAL_URL}home/item.html?id={item.id}")
        
        # Crear archivo CSV temporal con nuevos datos
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
            csv_path = tmp.name
            # Convertir DataFrame a CSV
            df_export = sedf.copy()
            # Agregar coordenadas
            df_export['Latitude'] = df_export['SHAPE'].apply(lambda x: x.y if hasattr(x, 'y') else None)
            df_export['Longitude'] = df_export['SHAPE'].apply(lambda x: x.x if hasattr(x, 'x') else None)
            # Eliminar columna SHAPE
            df_export = df_export.drop(columns=['SHAPE'])
            df_export.to_csv(tmp.name, index=False)
        
        logger.info(f"   ✓ CSV temporal creado con {len(df_export)} registros")
        
        # Actualizar Item con nuevos datos
        logger.info("   📤 Subiendo nuevos datos...")
        update_result = item.update(data=csv_path)
        
        # Limpiar archivo temporal
        os.unlink(csv_path)
        
        if update_result:
            logger.info(f"✅ CSV actualizado exitosamente con {len(sedf)} registros")
        else:
            raise Exception("La actualización falló")
        
        return item
        
    except Exception as e:
        logger.error(f"❌ Error actualizando Feature Layer: {str(e)}")
        raise


def guardar_csv_local(sedf):
    """Guarda una copia permanente del CSV en el servidor (sin backups)"""
    try:
        logger.info("💾 Guardando CSV en el servidor...")
        
        # Preparar DataFrame para exportar
        df_export = sedf.copy()
        df_export['Latitude'] = df_export['SHAPE'].apply(lambda x: x.y if hasattr(x, 'y') else None)
        df_export['Longitude'] = df_export['SHAPE'].apply(lambda x: x.x if hasattr(x, 'x') else None)
        df_export = df_export.drop(columns=['SHAPE'])
        
        # Guardar CSV principal (reemplaza el existente)
        df_export.to_csv(CSV_OUTPUT_FILE, index=False, encoding='utf-8')
        
        # Mostrar información del archivo
        file_size = CSV_OUTPUT_FILE.stat().st_size / 1024  # KB
        logger.info(f"   ✓ CSV actualizado: {CSV_OUTPUT_FILE}")
        logger.info(f"   📊 Tamaño: {file_size:.2f} KB")
        logger.info(f"   📝 Registros: {len(df_export)}")
        logger.info("✅ CSV actualizado exitosamente")
        
    except Exception as e:
        logger.error(f"❌ Error guardando CSV local: {str(e)}")
        # No fallar el proceso completo si solo falla el guardado local
        logger.warning("⚠️  Continuando con la actualización de ArcGIS...")


def limpiar_backups_antiguos(dias=30):
    """Elimina backups más antiguos que X días"""
    try:
        import time
        tiempo_limite = time.time() - (dias * 86400)
        
        archivos_eliminados = 0
        for backup_file in CSV_BACKUP_DIR.glob("metricas_xm_*.csv"):
            if backup_file.stat().st_mtime < tiempo_limite:
                backup_file.unlink()
                archivos_eliminados += 1
        
        if archivos_eliminados > 0:
            logger.info(f"   🗑️  Backups antiguos eliminados: {archivos_eliminados}")
            
    except Exception as e:
        logger.warning(f"⚠️  Error limpiando backups: {str(e)}")


def publicar_o_actualizar(gis, sedf, dry_run=False):
    """Publica nuevo Feature Layer o actualiza existente"""
    try:
        # Primero guardar copia local (siempre, incluso en dry-run)
        guardar_csv_local(sedf)
        
        if dry_run:
            logger.info("🔍 MODO DRY-RUN: No se realizarán cambios en ArcGIS")
            logger.info(f"   Se publicarían/actualizarían {len(sedf)} registros")
            return None
        
        logger.info(f"🔍 FEATURE_LAYER_ID configurado: {FEATURE_LAYER_ID}")
        
        if FEATURE_LAYER_ID and verificar_feature_layer_existe(gis, FEATURE_LAYER_ID):
            # Actualizar Feature Layer existente
            return actualizar_feature_layer(gis, FEATURE_LAYER_ID, sedf)
        else:
            # Publicar nuevo Feature Layer
            if FEATURE_LAYER_ID:
                logger.warning("⚠️  FEATURE_LAYER_ID configurado pero no válido. Creando nuevo...")
            else:
                logger.info("📝 No hay FEATURE_LAYER_ID configurado. Creando nuevo...")
            return publicar_nuevo_feature_layer(gis, sedf)
            
    except Exception as e:
        logger.error(f"❌ Error en publicación/actualización: {str(e)}")
        raise


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(
        description='Actualiza datos de XM en ArcGIS Online'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Ejecuta sin publicar cambios (solo prueba)'
    )
    parser.add_argument(
        '--env-file',
        type=str,
        default=None,
        help='Archivo .env alternativo (ej: .env.adminportal)'
    )
    args = parser.parse_args()
    
    try:
        logger.info("=" * 70)
        logger.info("   ACTUALIZACIÓN DE DATOS XM EN ARCGIS ENTERPRISE - MINENERGIA")
        logger.info("=" * 70)
        logger.info(f"Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Portal: {ARCGIS_PORTAL_URL}")
        logger.info(f"Usuario ArcGIS: {ARCGIS_USERNAME}")
        logger.info(f"Modo: {'DRY-RUN (Prueba)' if args.dry_run else 'PRODUCCIÓN'}")
        logger.info(f"Días de historia: {DIAS_ATRAS}")
        logger.info("=" * 70)
        
        # Validar credenciales
        validar_credenciales()
        
        # Verificar si hay datos nuevos disponibles (optimización para ejecución horaria)
        hay_datos_nuevos, ultima_fecha = verificar_datos_nuevos()
        
        # Si FEATURE_LAYER_ID está vacío, es una cuenta nueva que nunca ha publicado
        # → forzar publicación aunque el CSV local ya esté actualizado
        cuenta_nueva = not FEATURE_LAYER_ID
        if cuenta_nueva:
            logger.info("🆕 FEATURE_LAYER_ID vacío — cuenta nueva, forzando primera publicación")
            hay_datos_nuevos = True
        
        # Verificar si el CSV fue actualizado por otra cuenta pero no publicado a ESTA cuenta
        # (escenario dual: Vice_Energia actualiza el CSV, Adminportal necesita publicarlo también)
        csv_pendiente = False
        if not hay_datos_nuevos and not cuenta_nueva and CSV_OUTPUT_FILE.exists():
            if not csv_ya_publicado_para_esta_cuenta():
                logger.info(f"🔄 CSV actualizado por otra cuenta pero no publicado a {ARCGIS_USERNAME}")
                logger.info("   Se procederá a publicar los datos existentes.")
                csv_pendiente = True
                hay_datos_nuevos = True
        
        if not hay_datos_nuevos:
            logger.info("=" * 70)
            logger.info(f"✅ CSV ya actualizado hasta {ultima_fecha}. No se requiere actualización.")
            logger.info("💡 XM aún no ha publicado datos más recientes.")
            logger.info("   El script volverá a verificar en la próxima ejecución horaria.")
            logger.info("=" * 70)
            return 0
        
        # 1-3. Extraer y procesar datos de XM (o reusar CSV existente si csv_pendiente)
        if csv_pendiente:
            # El CSV ya fue actualizado por otra cuenta → reusar sin llamar a la API XM
            logger.info("📄 Reusando CSV existente (actualizado por otra cuenta)...")
            df_existente = pd.read_csv(CSV_OUTPUT_FILE)
            df_combined = df_existente
            sedf = crear_spatial_dataframe(df_combined)
        else:
            # 1. Extraer datos de XM
            gene_df, precio_df, volumen_df, capacidad_df = extraer_datos_xm()
            
            # 2. Procesar y combinar datos
            df_combined = procesar_datos(gene_df, precio_df, volumen_df, capacidad_df)
            
            # 3. Crear Spatial DataFrame
            sedf = crear_spatial_dataframe(df_combined)
        
        # 4. Conectar a ArcGIS Enterprise
        logger.info(f"🔌 Conectando a ArcGIS Enterprise: {ARCGIS_PORTAL_URL}")
        gis = GIS(url=ARCGIS_PORTAL_URL, username=ARCGIS_USERNAME, password=ARCGIS_PASSWORD)
        logger.info(f"✅ Conectado como: {gis.properties.user.username}")
        
        # 5. Publicar o actualizar datos (CSV Item en el portal)
        publicar_o_actualizar(gis, sedf, dry_run=args.dry_run)
        
        # 6. Actualizar la CAPA HOSPEDADA (Feature Service) para que dashboards vean datos nuevos
        #    Esto es necesario porque el Feature Service está desacoplado del CSV:
        #    actualizar el CSV no actualiza la capa ni los dashboards.
        if not args.dry_run:
            try:
                from actualizar_capa_hospedada import actualizar_capa_hospedada
                hosted_id = os.getenv("HOSTED_LAYER_ITEM_ID", "")
                if hosted_id:
                    logger.info("🔄 Actualizando capa hospedada (Feature Service)...")
                    actualizar_capa_hospedada(csv_path=str(CSV_OUTPUT_FILE))
                    logger.info("✅ Capa hospedada actualizada — dashboards verán datos nuevos.")
                else:
                    logger.info("ℹ️  HOSTED_LAYER_ITEM_ID no configurado. Solo se actualizó el CSV.")
                    logger.info("   Configura HOSTED_LAYER_ITEM_ID en .env para actualizar la capa hospedada.")
            except ImportError:
                logger.warning("⚠️  No se encontró actualizar_capa_hospedada.py. Solo se actualizó el CSV.")
            except Exception as e:
                logger.error(f"⚠️  Error actualizando capa hospedada: {e}")
                logger.error("   El CSV se actualizó correctamente, pero la capa hospedada no.")
        
        # 7. Registrar hash del CSV publicado para esta cuenta
        if not args.dry_run:
            registrar_publicacion()
        
        logger.info("=" * 70)
        logger.info("🎉 PROCESO COMPLETADO EXITOSAMENTE")
        logger.info("=" * 70)
        
        return 0
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Proceso interrumpido por el usuario")
        return 130
        
    except Exception as e:
        logger.error("=" * 70)
        logger.error(f"💥 ERROR CRÍTICO: {str(e)}")
        logger.error("=" * 70)
        import traceback
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())

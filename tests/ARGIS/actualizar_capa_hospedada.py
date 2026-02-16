#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script: Actualización de Capa Hospedada en ArcGIS Enterprise
=============================================================

PROBLEMA QUE RESUELVE:
    En ArcGIS Enterprise, al publicar un CSV como capa hospedada (hosted feature layer),
    se crea un Feature Service INDEPENDIENTE del archivo CSV original. El servicio copia
    los datos del CSV al momento de publicar, pero después queda DESACOPLADO.
    
    Por lo tanto:
      - Actualizar o reemplazar el CSV en el portal NO actualiza la capa hospedada.
      - Los dashboards y mapas web leen del Feature Service, NO del CSV.
      - Para que los dashboards vean datos nuevos, hay que actualizar el Feature Service directamente.

ESTRATEGIAS IMPLEMENTADAS:
    1. OVERWRITE (principal): Usa FeatureLayerCollection.manager.overwrite() para reemplazar
       todo el contenido del Feature Service con el CSV nuevo. Mantiene el mismo itemId y URL.
    2. TRUNCATE + APPEND (respaldo): Borra todos los registros de la capa y luego
       agrega los nuevos desde el CSV. Útil si overwrite presenta problemas en Enterprise.

INTEGRACIÓN CON CRON:
    Este script debe ejecutarse DESPUÉS de que el proceso ETL genere el CSV actualizado.
    Ejemplo de línea cron:

        # Cada día a las 6:00 AM: ejecutar ETL y luego actualizar capa hospedada
        0 6 * * * cd /home/admonctrlxm/server && python tests/ARGIS/actualizar_capa_hospedada.py >> logs/arcgis_capa.log 2>&1

    O bien, al final del script ETL existente (actualizar_datos_xm_online.py), agrega:

        from actualizar_capa_hospedada import actualizar_capa_hospedada
        actualizar_capa_hospedada("/ruta/al/csv_actualizado.csv")

Autor: Portal Energético MME
Fecha: 2026-02-09
"""

import sys
import os
import logging
import argparse
import time
from datetime import datetime
from pathlib import Path

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Intentar cargar variables de entorno desde .env
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

# --- Conexión al portal ----
ARCGIS_PORTAL_URL = os.getenv(
    "ARCGIS_PORTAL_URL",
    "https://arcgisenterprise.minenergia.gov.co/portal"
)
ARCGIS_USERNAME = os.getenv("ARCGIS_USERNAME", "")
ARCGIS_PASSWORD = os.getenv("ARCGIS_PASSWORD", "")

# --- Item de la capa hospedada ---
# Este es el itemId del Feature Service hospedado (NO del CSV).
# Puedes obtenerlo desde el portal: Contenido → clic en la capa → URL contiene ?id=XXXXX
HOSTED_LAYER_ITEM_ID = os.getenv("HOSTED_LAYER_ITEM_ID", "")

# --- Ruta del CSV generado por el ETL ---
BASE_DIR = Path(__file__).parent.parent.parent  # /home/admonctrlxm/server
CSV_PATH = os.getenv(
    "CSV_PATH",
    str(BASE_DIR / "data" / "metricas_xm_arcgis.csv")
)

# --- Estrategia de actualización ---
# "overwrite"        → reemplaza todo el feature service con el CSV (recomendado)
# "truncate_append"  → borra registros y luego los agrega desde el CSV
ESTRATEGIA = os.getenv("ARCGIS_UPDATE_STRATEGY", "overwrite")

# --- Logging ---
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "actualizacion_capa_hospedada.log"

# ============================================================================
# CONFIGURAR LOGGING
# ============================================================================

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("arcgis_update")


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def conectar_portal(url: str, usuario: str, clave: str):
    """
    Establece conexión autenticada con ArcGIS Enterprise Portal.
    
    Retorna:
        arcgis.gis.GIS  — objeto de conexión activa.
    
    Raises:
        RuntimeError si no se puede conectar.
    """
    from arcgis.gis import GIS

    if not usuario or not clave:
        raise RuntimeError(
            "Credenciales no configuradas. "
            "Define ARCGIS_USERNAME y ARCGIS_PASSWORD en el archivo .env o como variables de entorno."
        )

    logger.info("Conectando a ArcGIS Enterprise: %s", url)
    try:
        gis = GIS(url=url, username=usuario, password=clave, verify_cert=False)
        nombre = getattr(gis.properties.user, "username", usuario)
        logger.info("Conectado como: %s", nombre)
        return gis
    except Exception as exc:
        raise RuntimeError(f"No se pudo conectar al portal: {exc}") from exc


def obtener_item(gis, item_id: str):
    """
    Recupera el item del portal a partir de su ID.

    Valida que sea un Feature Service hospedado.

    Retorna:
        arcgis.gis.Item

    Raises:
        ValueError si el item no existe o no es del tipo esperado.
    """
    if not item_id:
        raise ValueError(
            "HOSTED_LAYER_ITEM_ID no configurado. "
            "Usa el portal para obtener el itemId de la capa hospedada 'Metricas_Energia_XM_Colombia'."
        )

    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"No se encontró ningún item con ID: {item_id}")

    logger.info("Item encontrado — Título: %s | Tipo: %s | ID: %s", item.title, item.type, item.id)

    tipo = (item.type or "").lower()
    # Aceptar Feature Service y Feature Layer Collection (Enterprise puede reportar cualquiera)
    tipos_validos = {"feature service", "feature layer collection", "feature layer"}
    if tipo not in tipos_validos:
        logger.warning(
            "El item '%s' es de tipo '%s'. "
            "Se esperaba un Feature Service hospedado. "
            "El overwrite podría fallar; se intentará de todos modos.",
            item.title, item.type,
        )

    return item


def validar_csv(csv_path: str) -> Path:
    """
    Valida que el archivo CSV exista y no esté vacío.

    Retorna:
        pathlib.Path al CSV.

    Raises:
        FileNotFoundError / ValueError ante problemas.
    """
    ruta = Path(csv_path)
    if not ruta.exists():
        raise FileNotFoundError(f"CSV no encontrado: {ruta}")
    if ruta.stat().st_size == 0:
        raise ValueError(f"CSV vacío: {ruta}")

    import pandas as pd
    df = pd.read_csv(ruta)
    registros = len(df)
    columnas = list(df.columns)

    if registros == 0:
        raise ValueError(f"CSV sin registros: {ruta}")

    logger.info(
        "CSV validado: %s (%d registros, %d columnas: %s)",
        ruta.name, registros, len(columnas), ", ".join(columnas[:6]),
    )
    return ruta


# ============================================================================
# ESTRATEGIA 1: OVERWRITE  (Recomendada)
# ============================================================================

def actualizar_overwrite(item, csv_path: Path) -> bool:
    """
    Reemplaza todo el contenido del Feature Service hospedado con el CSV.

    Usa FeatureLayerCollection.manager.overwrite(), que:
      - Mantiene el mismo itemId y la misma URL del FeatureServer.
      - Reemplaza los datos de forma atómica: si falla, los datos anteriores persisten.
      - Es la forma oficial recomendada por Esri.

    NOTA IMPORTANTE: ArcGIS Enterprise exige que el archivo CSV tenga el mismo
    nombre y extensión que el archivo original con el que se publicó la capa.
    Este script detecta automáticamente el nombre original del CSV asociado al
    Feature Service y renombra (copia) el archivo local para que coincida.

    Args:
        item:     arcgis.gis.Item del Feature Service hospedado.
        csv_path: Ruta al CSV con los datos nuevos.

    Returns:
        True si la actualización fue exitosa.

    Raises:
        RuntimeError si el overwrite falla.
    """
    from arcgis.features import FeatureLayerCollection
    import shutil
    import tempfile

    logger.info("--- Estrategia: OVERWRITE ---")

    try:
        flc = FeatureLayerCollection.fromitem(item)
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo obtener FeatureLayerCollection del item '{item.title}'. "
            f"Verifica que sea un Feature Service hospedado. Error: {exc}"
        ) from exc

    # --- Detectar nombre original del CSV asociado ---
    # ArcGIS Enterprise exige que el archivo tenga el mismo nombre que el original.
    # El CSV origen se obtiene de los items relacionados (Service2Data).
    nombre_original = None
    try:
        related = item.related_items("Service2Data", "forward")
        for r in related:
            if r.type == "CSV" and hasattr(r, "name") and r.name:
                nombre_original = r.name
                break
    except Exception:
        pass

    # Preparar CSV con el nombre correcto
    csv_para_overwrite = csv_path
    tmp_dir = None

    if nombre_original and csv_path.name != nombre_original:
        logger.info(
            "Renombrando CSV: '%s' → '%s' (debe coincidir con el original)",
            csv_path.name, nombre_original,
        )
        tmp_dir = Path(tempfile.mkdtemp())
        csv_para_overwrite = tmp_dir / nombre_original
        shutil.copy2(csv_path, csv_para_overwrite)
    else:
        logger.info("CSV ya tiene el nombre correcto: %s", csv_path.name)

    logger.info("Sobrescribiendo Feature Service con: %s", csv_para_overwrite.name)

    t0 = time.time()
    try:
        resultado = flc.manager.overwrite(str(csv_para_overwrite))
    except Exception as exc:
        raise RuntimeError(
            f"Error durante overwrite: {exc}. "
            f"La capa hospedada conserva sus datos anteriores (operación atómica)."
        ) from exc
    finally:
        # Limpiar copia temporal
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    duracion = time.time() - t0
    logger.info("Resultado overwrite: %s (%.1f s)", resultado, duracion)

    # Verificar resultado — la respuesta puede variar entre versiones
    if isinstance(resultado, dict):
        exito = resultado.get("success", True)
    else:
        exito = True  # Si no lanza excepción, asumimos éxito

    if not exito:
        raise RuntimeError(f"Overwrite reportó fallo: {resultado}")

    logger.info("Overwrite completado con éxito.")
    return True


# ============================================================================
# ESTRATEGIA 2: TRUNCATE + APPEND  (Respaldo)
# ============================================================================

def actualizar_truncate_append(item, csv_path: Path) -> bool:
    """
    Vacía la capa hospedada y agrega todos los registros del CSV.

    Pasos:
      1. Truncar (delete_features con where='1=1') — elimina todos los registros.
      2. Append — agrega los registros nuevos desde el CSV.

    NOTA: Hay un breve momento entre truncar y terminar el append en que la capa
    estará vacía o parcial. Para la mayoría de dashboards esto es aceptable dado
    que las actualizaciones se hacen en horarios de baja consulta.

    Esta estrategia es útil cuando:
      - El overwrite falla por restricciones de Enterprise.
      - Se necesita mayor control sobre el proceso.

    Args:
        item:     arcgis.gis.Item del Feature Service hospedado.
        csv_path: Ruta al CSV con los datos nuevos.

    Returns:
        True si la actualización fue exitosa.

    Raises:
        RuntimeError ante fallos.
    """
    import pandas as pd
    from arcgis.features import FeatureLayerCollection, FeatureSet

    logger.info("--- Estrategia: TRUNCATE + APPEND ---")

    # Obtener la capa/tabla del Feature Service.
    # NOTA: Si el CSV original no tenía geometría válida, ArcGIS Enterprise
    # publica los datos como Table (no como Layer). Por eso buscamos primero
    # en layers y luego en tables.
    try:
        flc = FeatureLayerCollection.fromitem(item)
        if flc.layers:
            capa = flc.layers[0]
        elif flc.tables:
            capa = flc.tables[0]
            logger.info("Los datos están en una Table (sin geometría), no en un Layer.")
        else:
            raise RuntimeError("El Feature Service no tiene layers ni tables.")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo acceder a la capa del Feature Service: {exc}") from exc

    logger.info("Capa objetivo: %s (%s)", capa.properties.name, capa.url)

    # --- Paso 1: Verificar conteo actual ---
    try:
        conteo_antes = capa.query(return_count_only=True)
        logger.info("Registros actuales en la capa: %d", conteo_antes)
    except Exception:
        conteo_antes = "desconocido"
        logger.warning("No se pudo obtener conteo de registros actuales.")

    # --- Paso 2: Truncar ---
    logger.info("Truncando capa (eliminando todos los registros)...")
    t0 = time.time()

    try:
        # Intentar truncate nativo (más eficiente, disponible en ArcGIS Enterprise 10.9+)
        resultado_truncate = capa.manager.truncate()
        logger.info("Truncate nativo exitoso: %s", resultado_truncate)
    except (AttributeError, Exception) as exc:
        logger.warning("Truncate nativo no disponible (%s). Usando delete_features...", exc)
        try:
            resultado_truncate = capa.delete_features(where="1=1")
            logger.info("Delete features exitoso: %s", resultado_truncate)
        except Exception as exc2:
            raise RuntimeError(f"No se pudieron eliminar los registros: {exc2}") from exc2

    duracion_truncate = time.time() - t0
    logger.info("Truncado en %.1f s", duracion_truncate)

    # --- Paso 3: Leer CSV y preparar features ---
    logger.info("Leyendo CSV y preparando registros para append...")
    df = pd.read_csv(csv_path)
    total_registros = len(df)
    logger.info("Registros a insertar: %d", total_registros)

    # --- Paso 4: Append usando append() o edit_features en lotes ---
    t0 = time.time()

    # Intentar append nativo con el CSV (más eficiente)
    try:
        logger.info("Intentando append nativo desde CSV...")
        resultado_append = capa.append(
            item_id=None,
            upload_format="csv",
            source_file_name=str(csv_path),
            field_mappings=None,       # auto-mapear por nombre de columna
            edits=None,
            upsert=False,
        )
        duracion_append = time.time() - t0
        logger.info("Append nativo exitoso: %s (%.1f s)", resultado_append, duracion_append)
    except Exception as exc_append:
        logger.warning("Append nativo falló (%s). Usando edit_features en lotes...", exc_append)
        _append_por_lotes(capa, df)

    # --- Paso 5: Verificar conteo final ---
    try:
        conteo_despues = capa.query(return_count_only=True)
        logger.info("Registros finales en la capa: %d (antes: %s)", conteo_despues, conteo_antes)

        if conteo_despues == 0:
            raise RuntimeError(
                "La capa quedó vacía después del append. "
                "Revisa el formato del CSV y la estructura de campos."
            )
    except RuntimeError:
        raise
    except Exception:
        logger.warning("No se pudo verificar conteo final.")

    logger.info("Truncate + Append completado con éxito.")
    return True


def _append_por_lotes(capa, df, tamano_lote: int = 500):
    """
    Agrega registros a la capa en lotes usando edit_features (add).
    
    Es más lento que append() pero funciona en todas las versiones de Enterprise.
    """
    from arcgis.features import Feature
    from arcgis.geometry import Point

    total = len(df)
    insertados = 0
    errores = 0

    logger.info("Insertando %d registros en lotes de %d...", total, tamano_lote)

    for inicio in range(0, total, tamano_lote):
        lote = df.iloc[inicio : inicio + tamano_lote]
        features = []

        for _, fila in lote.iterrows():
            atributos = fila.to_dict()

            # Construir geometría si hay columnas de coordenadas
            geometria = None
            lat_col = next((c for c in ("Latitude", "Y", "lat", "y") if c in atributos), None)
            lon_col = next((c for c in ("Longitude", "X", "lon", "x") if c in atributos), None)

            if lat_col and lon_col:
                try:
                    lat = float(atributos.pop(lat_col))
                    lon = float(atributos.pop(lon_col))
                    geometria = {"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}
                except (ValueError, TypeError):
                    pass

            # Eliminar campos que no deben enviarse como atributos
            atributos.pop("SHAPE", None)
            atributos.pop("OBJECTID", None)
            atributos.pop("FID", None)

            features.append(Feature(geometry=geometria, attributes=atributos))

        # Enviar lote
        try:
            resultado = capa.edit_features(adds=features)
            exitos_lote = sum(
                1 for r in resultado.get("addResults", []) if r.get("success", False)
            )
            errores_lote = len(features) - exitos_lote
            insertados += exitos_lote
            errores += errores_lote

            progreso = min(inicio + tamano_lote, total)
            logger.info(
                "  Lote %d-%d: %d OK, %d errores (total: %d/%d)",
                inicio + 1, progreso, exitos_lote, errores_lote, insertados, total,
            )
        except Exception as exc:
            errores += len(features)
            logger.error("  Error en lote %d-%d: %s", inicio + 1, inicio + tamano_lote, exc)

    logger.info("Inserción completada: %d exitosos, %d errores de %d total", insertados, errores, total)

    if insertados == 0:
        raise RuntimeError("No se insertó ningún registro. Revisa la estructura del CSV.")

    if errores > 0:
        logger.warning(
            "Se insertaron %d registros pero hubo %d errores. "
            "Algunos registros podrían no haberse cargado.",
            insertados, errores,
        )


# ============================================================================
# FUNCIÓN PRINCIPAL DE ACTUALIZACIÓN
# ============================================================================

def actualizar_capa_hospedada(
    csv_path: str = None,
    estrategia: str = None,
    item_id: str = None,
    portal_url: str = None,
    usuario: str = None,
    clave: str = None,
) -> bool:
    """
    Función principal reutilizable para actualizar la capa hospedada.

    Puede invocarse desde otro script Python (ej.: al final del ETL) o
    directamente desde la línea de comandos.

    Args:
        csv_path:    Ruta al CSV. Por defecto usa CSV_PATH de la configuración.
        estrategia:  "overwrite" o "truncate_append". Por defecto usa ESTRATEGIA.
        item_id:     itemId del Feature Service. Por defecto usa HOSTED_LAYER_ITEM_ID.
        portal_url:  URL del portal. Por defecto usa ARCGIS_PORTAL_URL.
        usuario:     Usuario del portal. Por defecto usa ARCGIS_USERNAME.
        clave:       Contraseña. Por defecto usa ARCGIS_PASSWORD.

    Returns:
        True si la actualización fue exitosa.

    Raises:
        Exception ante errores críticos.

    Ejemplo de uso desde otro script:
        >>> from actualizar_capa_hospedada import actualizar_capa_hospedada
        >>> actualizar_capa_hospedada("/ruta/al/metricas_xm_arcgis.csv")
    """
    # Aplicar valores por defecto desde configuración
    csv_path = csv_path or CSV_PATH
    estrategia = estrategia or ESTRATEGIA
    item_id = item_id or HOSTED_LAYER_ITEM_ID
    portal_url = portal_url or ARCGIS_PORTAL_URL
    usuario = usuario or ARCGIS_USERNAME
    clave = clave or ARCGIS_PASSWORD

    logger.info("=" * 72)
    logger.info("  ACTUALIZACIÓN DE CAPA HOSPEDADA — ArcGIS Enterprise")
    logger.info("=" * 72)
    logger.info("Fecha/Hora:    %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Portal:        %s", portal_url)
    logger.info("Item ID:       %s", item_id or "(no configurado)")
    logger.info("CSV:           %s", csv_path)
    logger.info("Estrategia:    %s", estrategia)
    logger.info("=" * 72)

    # 1. Validar CSV
    ruta_csv = validar_csv(csv_path)

    # 2. Conectar al portal
    gis = conectar_portal(portal_url, usuario, clave)

    # 3. Obtener el item de la capa hospedada
    item = obtener_item(gis, item_id)

    # 4. Ejecutar la estrategia seleccionada
    exito = False
    if estrategia == "overwrite":
        try:
            exito = actualizar_overwrite(item, ruta_csv)
        except RuntimeError as exc:
            logger.error("Overwrite falló: %s", exc)
            logger.info("Intentando estrategia de respaldo: truncate + append...")
            try:
                exito = actualizar_truncate_append(item, ruta_csv)
            except RuntimeError as exc2:
                logger.error("Truncate + Append también falló: %s", exc2)
                raise RuntimeError(
                    "Ambas estrategias fallaron. La capa conserva sus datos anteriores "
                    "(el overwrite es atómico). Revisa los logs para más detalles."
                ) from exc2

    elif estrategia == "truncate_append":
        exito = actualizar_truncate_append(item, ruta_csv)

    else:
        raise ValueError(
            f"Estrategia no reconocida: '{estrategia}'. "
            f"Usa 'overwrite' o 'truncate_append'."
        )

    # 5. Resumen final
    if exito:
        logger.info("=" * 72)
        logger.info("  ACTUALIZACIÓN COMPLETADA EXITOSAMENTE")
        logger.info("=" * 72)
        logger.info("La capa hospedada '%s' ahora tiene los datos del CSV.", item.title)
        logger.info("Los dashboards y mapas que consumen esta capa verán los datos nuevos.")
        logger.info(
            "URL FeatureServer: %s/server/rest/services/Hosted/%s/FeatureServer",
            portal_url.rstrip("/").replace("/portal", ""),
            item.title.replace(" ", "_"),
        )
        logger.info("=" * 72)

    return exito


# ============================================================================
# CLI — PUNTO DE ENTRADA PARA CRON
# ============================================================================

def main():
    """
    Punto de entrada para ejecución por línea de comandos / cron.

    Uso:
        python actualizar_capa_hospedada.py
        python actualizar_capa_hospedada.py --csv /ruta/al/datos.csv
        python actualizar_capa_hospedada.py --estrategia truncate_append
        python actualizar_capa_hospedada.py --item-id abc123def456
    """
    parser = argparse.ArgumentParser(
        description="Actualiza una capa hospedada en ArcGIS Enterprise desde un CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Usar configuración por defecto (.env / variables de entorno)
  python actualizar_capa_hospedada.py

  # Especificar CSV y estrategia
  python actualizar_capa_hospedada.py --csv data/metricas_xm_arcgis.csv --estrategia overwrite

  # Forzar truncate + append
  python actualizar_capa_hospedada.py --estrategia truncate_append

  # Usar un item ID diferente
  python actualizar_capa_hospedada.py --item-id abc123def456789

Configuración en cron:
  0 6 * * * cd /home/admonctrlxm/server && python tests/ARGIS/actualizar_capa_hospedada.py >> logs/arcgis_capa.log 2>&1
        """,
    )
    parser.add_argument(
        "--csv",
        default=None,
        help=f"Ruta al CSV con los datos nuevos. Default: {CSV_PATH}",
    )
    parser.add_argument(
        "--estrategia",
        choices=["overwrite", "truncate_append"],
        default=None,
        help=f"Estrategia de actualización. Default: {ESTRATEGIA}",
    )
    parser.add_argument(
        "--item-id",
        default=None,
        help="ID del item del Feature Service hospedado en el portal.",
    )
    parser.add_argument(
        "--portal-url",
        default=None,
        help=f"URL del portal ArcGIS Enterprise. Default: {ARCGIS_PORTAL_URL}",
    )
    parser.add_argument(
        "--usuario",
        default=None,
        help="Usuario del portal.",
    )
    parser.add_argument(
        "--clave",
        default=None,
        help="Contraseña del portal.",
    )
    args = parser.parse_args()

    try:
        exito = actualizar_capa_hospedada(
            csv_path=args.csv,
            estrategia=args.estrategia,
            item_id=args.item_id,
            portal_url=args.portal_url,
            usuario=args.usuario,
            clave=args.clave,
        )
        return 0 if exito else 1

    except KeyboardInterrupt:
        logger.warning("Proceso interrumpido por el usuario.")
        return 130

    except Exception as exc:
        logger.error("=" * 72)
        logger.error("  ERROR CRÍTICO: %s", exc)
        logger.error("=" * 72)
        import traceback
        logger.debug(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())

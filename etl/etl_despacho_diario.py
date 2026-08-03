#!/usr/bin/env python3
"""
ETL: Disponibilidad de plantas y precio de predespacho ideal (informe diario XM
"Seguimiento de Despacho") → PostgreSQL
================================================================================

Descarga el informe diario "Seguimiento de Despacho" de XM (ya sincronizado vía
OneDrive/SharePoint, mismas funciones reusables de api/v1/routes/reports.py que
usa el ETL de Senda de Referencia) y extrae, del texto real del PDF (sin
imágenes, sin OCR — ver etl/despacho_pdf_parser.py):

  1. Qué plantas están indisponibles (mantenimiento vs. sin registro) para el
     día siguiente → sector_energetico.disponibilidad_plantas
  2. Precio promedio de oferta del recurso marginal del predespacho ideal para
     hoy, ayer y mañana → sector_energetico.precio_predespacho_ideal

Ejecución:
    Automático: Cron 1×/día
    Manual: python3 etl/etl_despacho_diario.py [--dry-run]
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def _get_connection():
    import psycopg2
    from core.config import settings
    params = {
        'host': settings.POSTGRES_HOST,
        'port': settings.POSTGRES_PORT,
        'database': settings.POSTGRES_DB,
        'user': settings.POSTGRES_USER,
    }
    if settings.POSTGRES_PASSWORD:
        params['password'] = settings.POSTGRES_PASSWORD
    return psycopg2.connect(**params)


def _upsert_indisponibilidades(indisp, fecha_publicacion, fuente: str) -> int:
    conn = _get_connection()
    cur = conn.cursor()
    insertados = 0
    try:
        # Limpiar filas previas de esa misma fecha antes de reinsertar el set
        # completo del día (evita arrastrar recursos que ya volvieron a estar
        # disponibles en una corrida posterior).
        cur.execute(
            "DELETE FROM sector_energetico.disponibilidad_plantas WHERE fecha = %s",
            (indisp.fecha,),
        )
        for recurso, tipo in indisp.recursos:
            cur.execute("""
                INSERT INTO sector_energetico.disponibilidad_plantas
                    (fecha, recurso, tipo_indisponibilidad, total_recursos_disp_menor_100,
                     fecha_publicacion, fuente)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (fecha, recurso) DO UPDATE SET
                    tipo_indisponibilidad = EXCLUDED.tipo_indisponibilidad,
                    total_recursos_disp_menor_100 = EXCLUDED.total_recursos_disp_menor_100,
                    fecha_publicacion = EXCLUDED.fecha_publicacion,
                    fuente = EXCLUDED.fuente
            """, (indisp.fecha, recurso, tipo, indisp.total_recursos_disp_menor_100,
                  fecha_publicacion, fuente))
            insertados += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return insertados


def _upsert_precios_predespacho(precios, fecha_publicacion, fuente: str) -> int:
    conn = _get_connection()
    cur = conn.cursor()
    insertados = 0
    try:
        for fecha, precio in precios:
            cur.execute("""
                INSERT INTO sector_energetico.precio_predespacho_ideal
                    (fecha, precio_cop_kwh, fecha_publicacion, fuente)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (fecha) DO UPDATE SET
                    precio_cop_kwh = EXCLUDED.precio_cop_kwh,
                    fecha_publicacion = EXCLUDED.fecha_publicacion,
                    fuente = EXCLUDED.fuente,
                    actualizado_en = NOW()
            """, (fecha, precio, fecha_publicacion, fuente))
            insertados += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return insertados


def ejecutar_etl(dry_run: bool = False) -> dict:
    from api.v1.routes.reports import (
        _sp_open_folder, _index_informes_diarios_folders, _resolver_informes_diarios,
        _sp_download_item, INFORMES_DIARIOS_XM_FOLDER,
    )
    from etl.despacho_pdf_parser import extraer_indisponibilidades, extraer_precios_predespacho

    resultado = {
        'exito': False, 'plantas_insertadas': 0, 'precios_insertados': 0,
        'indisponibilidades': None, 'precios_predespacho': None, 'error': None,
    }
    try:
        headers, drive_id, root_id = _sp_open_folder(INFORMES_DIARIOS_XM_FOLDER)
        folders = _index_informes_diarios_folders(headers, drive_id, root_id)
        if not folders:
            raise RuntimeError("No se encontraron carpetas de informes diarios en SharePoint")
        resolved, resolved_from = _resolver_informes_diarios(folders)
        item = resolved.get('SeguimientoDespacho')
        if item is None:
            raise RuntimeError("Informe 'SeguimientoDespacho' no disponible")
        fecha_publicacion = resolved_from['SeguimientoDespacho']

        pdf_bytes = _sp_download_item(headers, drive_id, item, read_timeout=120)

        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        texto_pdf = "\n".join(page.get_text() for page in doc)
        doc.close()

        indisp = extraer_indisponibilidades(texto_pdf, fecha_publicacion)
        precios = extraer_precios_predespacho(texto_pdf, fecha_publicacion)

        if indisp is not None:
            resultado['indisponibilidades'] = {
                'fecha': str(indisp.fecha),
                'total_disp_menor_100': indisp.total_recursos_disp_menor_100,
                'recursos': indisp.recursos,
            }
        resultado['precios_predespacho'] = [(str(f), p) for f, p in precios]

        if dry_run:
            resultado['exito'] = True
            logger.info(f"[DRY-RUN] Indisponibilidades: {resultado['indisponibilidades']}")
            logger.info(f"[DRY-RUN] Precios predespacho: {resultado['precios_predespacho']}")
            return resultado

        fuente = f"PDF XM SeguimientoDespacho {fecha_publicacion.isoformat()}"
        if indisp is not None:
            resultado['plantas_insertadas'] = _upsert_indisponibilidades(indisp, fecha_publicacion, fuente)
        if precios:
            resultado['precios_insertados'] = _upsert_precios_predespacho(precios, fecha_publicacion, fuente)

        resultado['exito'] = True
        logger.info(
            f"✅ Despacho diario: {resultado['plantas_insertadas']} plantas, "
            f"{resultado['precios_insertados']} precios predespacho actualizados"
        )
    except Exception as e:
        resultado['error'] = str(e)
        logger.error(f"❌ Error importando despacho diario: {e}")
    return resultado


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL: Disponibilidad de plantas y precio predespacho (XM)")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar lo que se extraería, sin escribir en BD")
    args = parser.parse_args()

    import json
    resultado = ejecutar_etl(dry_run=args.dry_run)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    sys.exit(0 if resultado['exito'] else 1)

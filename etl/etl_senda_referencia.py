"""
═══════════════════════════════════════════════════════════════════════════════
ETL — Senda de Referencia del Embalse Agregado del SIN

Fuente oficial: Resolución CREG 209 de 2020 + publicaciones XM/CND
Publicación: https://www.xm.com.co/resoluciones/operacion-y-mercado/resolucion-creg-209-de-2020-condicion-del-sistema
Repositorio FTPS: /INFORMACION_XM/Publico/PlaneacionOperacion/Senda%20de%20Referencia/

XM publica la Senda como archivo XLSX al inicio de cada estación (mayo y diciembre).
Este ETL:
  1. Lee la senda más reciente desde la tabla `sector_energetico.senda_referencia`.
  2. Soporta carga manual de un archivo XLSX descargado de XM.
  3. Mantiene los valores oficiales conocidos como respaldo.
  4. NO requiere credenciales (descarga es opcional; carga manual es la vía principal).

Uso:
    python3 etl_senda_referencia.py --seed              # Carga valores conocidos
    python3 etl_senda_referencia.py --xlsx archivo.xlsx # Importa XLSX de XM
    python3 etl_senda_referencia.py --info              # Muestra senda activa
═══════════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Valores oficiales conocidos de la Senda de Referencia
# (publicados por XM/CND según Circular CREG 023/2024 y reportes públicos)
# ═══════════════════════════════════════════════════════════════════════════════
SENDA_VALORES_OFICIALES = [
    # (fecha, porcentaje, estación, fecha_publicación, fuente)
    (date(2024, 5, 1),  28.70, 'INVIERNO', date(2024, 4, 27), 'Circular CREG 023/2024 - Senda Invierno 2024'),
    (date(2024, 4, 29), 35.40, 'VERANO',   date(2024, 4, 29), 'Reporte CREG abril 2024'),
    (date(2024, 11, 30), 67.80, 'INVIERNO', date(2024, 4, 27), 'Circular CREG 023/2024 - Fin Invierno 2024'),
]

# Tabla mensual aproximada (respaldo cuando no hay valores diarios oficiales en BD)
# Estos valores son ESTIMACIONES derivadas de las sendas oficiales conocidas.
# Cuando XM publique una nueva senda, debe importarse con --xlsx para reemplazar.
SENDA_MENSUAL_RESPALDO = {
    1:  55.0, 2:  47.0, 3:  37.0, 4:  35.4, 5:  28.7,
    6:  35.0, 7:  45.0, 8:  55.0, 9:  62.0, 10: 65.0,
    11: 67.8, 12: 65.0,
}


def _get_connection():
    """Conexión a PostgreSQL usando settings del proyecto."""
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


def cargar_valores_semilla() -> int:
    """Carga los valores oficiales conocidos a la BD (idempotente)."""
    conn = _get_connection()
    cur = conn.cursor()
    insertados = 0
    try:
        for fecha, pct, estacion, fecha_publ, fuente in SENDA_VALORES_OFICIALES:
            cur.execute("""
                INSERT INTO sector_energetico.senda_referencia
                    (fecha, porcentaje_volumen_util, estacion, fecha_publicacion, fuente)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (fecha) DO UPDATE SET
                    porcentaje_volumen_util = EXCLUDED.porcentaje_volumen_util,
                    estacion = EXCLUDED.estacion,
                    fecha_publicacion = EXCLUDED.fecha_publicacion,
                    fuente = EXCLUDED.fuente,
                    actualizado_en = NOW()
            """, (fecha, pct, estacion, fecha_publ, fuente))
            insertados += 1
        conn.commit()
        logger.info(f"Senda: {insertados} valores oficiales sembrados/actualizados")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error sembrando senda: {e}")
        raise
    finally:
        cur.close()
        conn.close()
    return insertados


def importar_xlsx(ruta: str, estacion: str, fecha_publicacion: Optional[date] = None) -> int:
    """Importa una Senda de Referencia desde un archivo XLSX de XM.

    El formato esperado tiene dos columnas: fecha y porcentaje.
    El estándar de XM es la primera columna con fechas diarias y la segunda
    con el valor de la senda en %.
    """
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl no está instalado. Ejecutar: pip install openpyxl")
        raise

    if not Path(ruta).exists():
        raise FileNotFoundError(f"Archivo no encontrado: {ruta}")

    wb = openpyxl.load_workbook(ruta, data_only=True)
    ws = wb.active
    if fecha_publicacion is None:
        fecha_publicacion = date.today()

    conn = _get_connection()
    cur = conn.cursor()
    insertados = 0
    try:
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None or row[1] is None:
                continue
            fecha_val = row[0]
            pct_val = row[1]
            # Normalizar fecha
            if isinstance(fecha_val, datetime):
                fecha_val = fecha_val.date()
            elif isinstance(fecha_val, str):
                try:
                    fecha_val = datetime.strptime(fecha_val, '%Y-%m-%d').date()
                except ValueError:
                    continue
            # Normalizar porcentaje (puede venir como decimal 0-1 o como entero 0-100)
            pct = float(pct_val)
            if pct <= 1.0:
                pct *= 100.0

            cur.execute("""
                INSERT INTO sector_energetico.senda_referencia
                    (fecha, porcentaje_volumen_util, estacion, fecha_publicacion, fuente)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (fecha) DO UPDATE SET
                    porcentaje_volumen_util = EXCLUDED.porcentaje_volumen_util,
                    estacion = EXCLUDED.estacion,
                    fecha_publicacion = EXCLUDED.fecha_publicacion,
                    fuente = EXCLUDED.fuente,
                    actualizado_en = NOW()
            """, (fecha_val, pct, estacion.upper(), fecha_publicacion,
                  f'XLSX importado de XM ({Path(ruta).name})'))
            insertados += 1
        conn.commit()
        logger.info(f"Senda XLSX: {insertados} valores importados desde {ruta}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error importando XLSX: {e}")
        raise
    finally:
        cur.close()
        conn.close()
    return insertados


def _estacion_para_fecha(fecha: date) -> str:
    """INVIERNO (temporada de lluvias, mayo-noviembre) o VERANO (diciembre-abril)."""
    return 'INVIERNO' if 5 <= fecha.month <= 11 else 'VERANO'


def _upsert_curva_senda(curva: dict, fuente_por_fecha_ancla: str, fuente_proyectada: str,
                         fecha_ancla: date, fecha_publicacion: date) -> int:
    """Guarda la curva completa {fecha: pct} — misma sentencia upsert que importar_xlsx."""
    conn = _get_connection()
    cur = conn.cursor()
    insertados = 0
    try:
        for fecha_val, pct in curva.items():
            fuente = fuente_por_fecha_ancla if fecha_val == fecha_ancla else fuente_proyectada
            cur.execute("""
                INSERT INTO sector_energetico.senda_referencia
                    (fecha, porcentaje_volumen_util, estacion, fecha_publicacion, fuente)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (fecha) DO UPDATE SET
                    porcentaje_volumen_util = EXCLUDED.porcentaje_volumen_util,
                    estacion = EXCLUDED.estacion,
                    fecha_publicacion = EXCLUDED.fecha_publicacion,
                    fuente = EXCLUDED.fuente,
                    actualizado_en = NOW()
            """, (fecha_val, pct, _estacion_para_fecha(fecha_val), fecha_publicacion, fuente))
            insertados += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error guardando curva de senda: {e}")
        raise
    finally:
        cur.close()
        conn.close()
    return insertados


def importar_desde_informe_diario(dry_run: bool = False) -> dict:
    """Descarga el informe diario "Variables Hidrológicas" de XM (ya sincronizado vía
    OneDrive/SharePoint) y extrae de su gráfica la curva completa de Senda de Referencia,
    calibrando ejes con el ancla exacta de texto (ver etl/senda_pdf_parser.py).

    100% automatizado: no requiere XLSX manual ni intervención humana.
    """
    from api.v1.routes.reports import (
        _sp_open_folder, _index_informes_diarios_folders, _resolver_informes_diarios,
        _sp_download_item, INFORMES_DIARIOS_XM_FOLDER,
    )
    from etl.senda_pdf_parser import (
        extraer_grafica_y_texto, extraer_ancla_textual, extraer_curva_senda,
        ExtraccionSendaError,
    )

    resultado = {
        'exito': False, 'insertados': 0, 'ancla_fecha': None, 'ancla_valor': None,
        'rango_curva': None, 'error': None,
    }
    try:
        headers, drive_id, root_id = _sp_open_folder(INFORMES_DIARIOS_XM_FOLDER)
        folders = _index_informes_diarios_folders(headers, drive_id, root_id)
        if not folders:
            raise RuntimeError("No se encontraron carpetas de informes diarios en SharePoint")
        resolved, resolved_from = _resolver_informes_diarios(folders)
        item = resolved.get('VariablesHidrologicas')
        if item is None:
            raise RuntimeError("Informe 'VariablesHidrologicas' no disponible")
        fecha_publicacion = resolved_from['VariablesHidrologicas']

        pdf_bytes = _sp_download_item(headers, drive_id, item, read_timeout=120)

        arr, texto_pagina = extraer_grafica_y_texto(pdf_bytes)
        ancla = extraer_ancla_textual(texto_pagina, fecha_publicacion)
        if ancla is None:
            raise ExtraccionSendaError(
                "No se pudo extraer el ancla textual (nivel embalse / diferencia) del PDF"
            )

        curva = extraer_curva_senda(arr, ancla)

        resultado['ancla_fecha'] = str(ancla.fecha)
        resultado['ancla_valor'] = ancla.valor_senda
        resultado['rango_curva'] = (str(min(curva)), str(max(curva)))

        if dry_run:
            resultado['exito'] = True
            logger.info(
                f"[DRY-RUN] Ancla {ancla.fecha}: senda={ancla.valor_senda}% "
                f"(real={ancla.valor_real}%) | curva: {len(curva)} fechas "
                f"[{min(curva)} .. {max(curva)}]"
            )
            return resultado

        fuente_ancla = f"PDF XM VariablesHidrologicas {fecha_publicacion.isoformat()} — ancla texto"
        fuente_proyectada = f"PDF XM VariablesHidrologicas {fecha_publicacion.isoformat()} — curva proyectada por píxeles"
        insertados = _upsert_curva_senda(
            curva, fuente_ancla, fuente_proyectada, ancla.fecha, fecha_publicacion,
        )
        resultado['insertados'] = insertados
        resultado['exito'] = True
        logger.info(f"✅ Senda: {insertados} fechas actualizadas (ancla {ancla.fecha}={ancla.valor_senda}%)")
    except Exception as e:
        resultado['error'] = str(e)
        logger.error(f"❌ Error importando senda desde informe diario: {e}")
    return resultado


def obtener_senda_para_fecha(fecha: Optional[date] = None) -> Optional[float]:
    """Devuelve el % de senda para una fecha consultando la BD.

    Estrategia:
      1. Buscar valor exacto en la fecha pedida.
      2. Si no existe, buscar el valor publicado más cercano (menor o igual).
      3. Si no hay ninguno en BD, retornar None (el llamador usará fallback).
    """
    fecha = fecha or date.today()
    try:
        conn = _get_connection()
        cur = conn.cursor()
        # 1) Valor exacto
        cur.execute("""
            SELECT porcentaje_volumen_util
            FROM sector_energetico.senda_referencia
            WHERE fecha = %s
            LIMIT 1
        """, (fecha,))
        row = cur.fetchone()
        if row:
            return float(row[0])
        # 2) Valor más cercano (interpolación simple: tomar el más reciente <= fecha)
        cur.execute("""
            SELECT porcentaje_volumen_util
            FROM sector_energetico.senda_referencia
            WHERE fecha <= %s
            ORDER BY fecha DESC
            LIMIT 1
        """, (fecha,))
        row = cur.fetchone()
        if row:
            return float(row[0])
    except Exception as e:
        logger.warning(f"Error consultando senda BD: {e}")
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
    return None


def info_senda() -> dict:
    """Devuelve metadata de la senda actualmente cargada en BD."""
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*),
                   MIN(fecha),
                   MAX(fecha),
                   MAX(actualizado_en),
                   MAX(fecha_publicacion)
            FROM sector_energetico.senda_referencia
        """)
        total, fmin, fmax, ult_act, ult_publ = cur.fetchone()
        return {
            'total_registros': total,
            'fecha_min': str(fmin) if fmin else None,
            'fecha_max': str(fmax) if fmax else None,
            'ultima_actualizacion': str(ult_act) if ult_act else None,
            'ultima_publicacion_xm': str(ult_publ) if ult_publ else None,
            'senda_hoy': obtener_senda_para_fecha(),
        }
    except Exception as e:
        logger.error(f"Error info senda: {e}")
        return {'error': str(e)}
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description='ETL Senda de Referencia XM/CND')
    parser.add_argument('--seed', action='store_true', help='Cargar valores oficiales conocidos')
    parser.add_argument('--xlsx', type=str, help='Ruta a archivo XLSX de XM')
    parser.add_argument('--estacion', type=str, choices=['VERANO', 'INVIERNO'], help='Estación del XLSX')
    parser.add_argument('--info', action='store_true', help='Mostrar estado de la senda')
    parser.add_argument('--pdf-diario', action='store_true',
                         help='Extraer senda del informe diario XM "Variables Hidrológicas" (automático)')
    parser.add_argument('--dry-run', action='store_true',
                         help='Con --pdf-diario: solo mostrar lo que se extraería, sin escribir en BD')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    if args.pdf_diario:
        import json
        resultado = importar_desde_informe_diario(dry_run=args.dry_run)
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
        sys.exit(0 if resultado['exito'] else 1)

    if args.info:
        import json
        print(json.dumps(info_senda(), indent=2, ensure_ascii=False))
        return

    if args.seed:
        n = cargar_valores_semilla()
        print(f"✓ {n} valores oficiales sembrados/actualizados en BD")
        return

    if args.xlsx:
        if not args.estacion:
            print("ERROR: --xlsx requiere --estacion VERANO|INVIERNO")
            sys.exit(1)
        n = importar_xlsx(args.xlsx, args.estacion)
        print(f"✓ {n} valores importados desde {args.xlsx}")
        return

    parser.print_help()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
ETL: Base_Subsidios_DDE.xlsx → PostgreSQL
Importa hojas Pagos, Inicio (empresas) y Mapa a la base portal_energetico.

Uso:
    python etl/etl_subsidios.py                          # importar todo
    python etl/etl_subsidios.py --hoja pagos             # solo pagos
    python etl/etl_subsidios.py --hoja empresas          # solo catálogo
    python etl/etl_subsidios.py --hoja mapa              # solo mapa
    python etl/etl_subsidios.py --archivo /ruta/otro.xlsx # archivo diferente
"""
import argparse
import hashlib
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = BASE_DIR / 'data' / 'onedrive' / 'Base_Subsidios_DDE.xlsx'

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [ETL_SUBSIDIOS] - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / 'etl_subsidios.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

# ─── DB ───────────────────────────────────────────────────────────────────────

def get_connection():
    """Conexión directa a PostgreSQL (misma config que el resto de ETLs)."""
    return psycopg2.connect(
        dbname='portal_energetico',
        user='postgres',
        host='localhost',
        port=5432,
    )


def ensure_schema(conn):
    """Crea tablas si no existen ejecutando el DDL."""
    schema_path = BASE_DIR / 'sql' / 'subsidios_schema.sql'
    if not schema_path.exists():
        logger.error(f"Schema no encontrado: {schema_path}")
        return
    with conn.cursor() as cur:
        cur.execute(schema_path.read_text(encoding='utf-8'))
    conn.commit()
    logger.info("✅ Schema verificado/creado")


# ─── Hash para dedup ─────────────────────────────────────────────────────────

def row_hash(row: pd.Series) -> str:
    """SHA-256 de todos los valores de la fila (orden estable)."""
    raw = '|'.join(str(v) for v in row.values)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGOS
# ═══════════════════════════════════════════════════════════════════════════════

PAGOS_COL_MAP = {
    'Fecha actualización':              'fecha_actualizacion',
    'Persona Actualiza':                'persona_actualiza',
    'Fondo':                            'fondo',
    'Area':                             'area',
    'Año':                              'anio',
    'Trimestre':                        'trimestre',
    'Concepto Trimestre':               'concepto_trimestre',
    'Código\nSUI/FSSRI':               'codigo_sui',
    'Nombre del Prestador':             'nombre_prestador',
    'Estado Resolución':                'estado_resolucion',
    'No. de Resolución':                'no_resolucion',
    'Fecha Resolución (DD/MM/AAAA)':    'fecha_resolucion',
    'Valor Resolución':                 'valor_resolucion',
    'Link Resolución':                  'link_resolucion',
    'Tipo de Giro':                     'tipo_giro',
    'Distribuidor Mayorista/Combustible': 'distribuidor_mayorista',
    'Estado Pago':                      'estado_pago',
    'Tipo Pago':                        'tipo_pago',
    'Valor Pagado':                     'valor_pagado',
    '%Pagado':                          'pct_pagado',
    'Diferencia (Saldo Pendiente)':     'saldo_pendiente',
    'Observación':                      'observacion',
    'A COD General':                    'cod_general',
    'Año / Trimestre Resolución':       'anio_trimestre_resolucion',
    'Valor Disponible':                 'valor_disponible',
    'Valor Disponible 2':               'valor_disponible_2',
}


def importar_pagos(xlsx_path: Path, conn) -> dict:
    """Lee hoja Pagos, elimina duplicados exactos, calcula hash e inserta."""
    t0 = time.time()
    logger.info(f"📖 Leyendo hoja 'Pagos' de {xlsx_path.name}...")
    df = pd.read_excel(xlsx_path, sheet_name='Pagos')

    # Quedarse solo con columnas conocidas
    cols_utiles = [c for c in df.columns if c in PAGOS_COL_MAP]
    df = df[cols_utiles]

    filas_leidas = len(df)
    logger.info(f"   Filas leídas: {filas_leidas}")

    # Eliminar duplicados exactos (94 conocidos)
    df = df.drop_duplicates()
    filas_dedup = filas_leidas - len(df)
    logger.info(f"   Duplicados exactos eliminados: {filas_dedup}")

    # Renombrar columnas
    df = df.rename(columns=PAGOS_COL_MAP)

    # Limpiar tipos
    df['trimestre'] = pd.to_numeric(df['trimestre'], errors='coerce').astype('Int64')
    df['no_resolucion'] = pd.to_numeric(df['no_resolucion'], errors='coerce').astype('Int64')
    df['anio'] = pd.to_numeric(df['anio'], errors='coerce').astype('Int64')
    for col in ['valor_resolucion', 'valor_pagado', 'saldo_pendiente',
                'pct_pagado', 'valor_disponible', 'valor_disponible_2']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['valor_resolucion'] = df['valor_resolucion'].fillna(0)
    df['valor_pagado'] = df['valor_pagado'].fillna(0)
    df['saldo_pendiente'] = df['saldo_pendiente'].fillna(0)

    # Fechas
    df['fecha_actualizacion'] = pd.to_datetime(df['fecha_actualizacion'], errors='coerce')
    df['fecha_resolucion'] = pd.to_datetime(df['fecha_resolucion'], errors='coerce')

    # Hash para dedup incremental
    hash_cols = [c for c in df.columns]  # todas las columnas
    df['hash_fila'] = df[hash_cols].apply(row_hash, axis=1)

    # Convertir NaN/NA → None para PostgreSQL
    # El tipo Int64 produce pd.NA que psycopg2 no acepta; convertir a object
    for col in df.columns:
        if pd.api.types.is_integer_dtype(df[col]) or str(df[col].dtype) == 'Int64':
            df[col] = df[col].astype(object)
    df = df.where(pd.notna(df), None)

    # Columnas destino (orden fijo)
    dest_cols = [
        'fecha_actualizacion', 'persona_actualiza', 'fondo', 'area', 'anio',
        'trimestre', 'concepto_trimestre', 'codigo_sui', 'nombre_prestador',
        'estado_resolucion', 'no_resolucion', 'fecha_resolucion',
        'valor_resolucion', 'link_resolucion', 'tipo_giro',
        'distribuidor_mayorista', 'estado_pago', 'tipo_pago', 'valor_pagado',
        'pct_pagado', 'saldo_pendiente', 'observacion', 'cod_general',
        'anio_trimestre_resolucion', 'valor_disponible', 'valor_disponible_2',
        'hash_fila',
    ]

    placeholders = ', '.join(['%s'] * len(dest_cols))
    col_list = ', '.join(dest_cols)
    insert_sql = f"""
        INSERT INTO subsidios_pagos ({col_list})
        VALUES ({placeholders})
        ON CONFLICT (hash_fila) DO NOTHING
    """

    rows = [tuple(r[c] for c in dest_cols) for _, r in df.iterrows()]

    with conn.cursor() as cur:
        filas_antes = _count_table(cur, 'subsidios_pagos')
        psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=500)
        conn.commit()
        filas_despues = _count_table(cur, 'subsidios_pagos')

    filas_importadas = filas_despues - filas_antes
    filas_dup = len(df) - filas_importadas
    duracion = time.time() - t0

    stats = {
        'hoja': 'Pagos',
        'filas_leidas': filas_leidas,
        'filas_importadas': filas_importadas,
        'filas_duplicadas': filas_dup + filas_dedup,
        'filas_error': 0,
        'duracion_seg': round(duracion, 2),
    }
    _log_import(conn, xlsx_path.name, stats)

    logger.info(f"✅ Pagos: {filas_importadas} nuevas, {filas_dup} ya existían, "
                f"{filas_dedup} exactos eliminados ({duracion:.1f}s)")
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRESAS (Inicio)
# ═══════════════════════════════════════════════════════════════════════════════

def importar_empresas(xlsx_path: Path, conn) -> dict:
    """Lee hoja Inicio (catálogo de empresas) e inserta/actualiza."""
    t0 = time.time()
    logger.info(f"📖 Leyendo hoja 'Inicio' de {xlsx_path.name}...")
    df = pd.read_excel(xlsx_path, sheet_name='Inicio')
    cols = [c for c in df.columns if not str(c).startswith('Unnamed')]
    df = df[cols]

    filas_leidas = len(df)

    col_map = {
        'Fondo': 'fondo',
        'Subclase': 'subclase',
        'Código\nSUI/FSSRI': 'codigo_sui',
        'NIT': 'nit',
        'Nombre del Prestador': 'nombre_prestador',
        'Sigla del Prestador': 'sigla',
        'Estado (Activa - A, Cerrada - C y Desaparecida - D)': 'estado',
        'Tipo de empresa (Deficitaria - D, Superavitaria - S y Exenta - E)': 'tipo_empresa',
        'Fuente de generación': 'fuente_generacion',
        'Departamento': 'departamento',
        'Ciudad/Municipio': 'municipio',
        'Profesional Encargado': 'profesional',
    }

    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    df = df[[c for c in col_map.values() if c in df.columns]]
    df['codigo_sui'] = df['codigo_sui'].astype(str).str.strip()
    df = df.where(pd.notna(df), None)

    insert_sql = """
        INSERT INTO subsidios_empresas (
            fondo, subclase, codigo_sui, nit, nombre_prestador, sigla,
            estado, tipo_empresa, fuente_generacion, departamento, municipio, profesional
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (codigo_sui) DO UPDATE SET
            nombre_prestador = EXCLUDED.nombre_prestador,
            nit              = EXCLUDED.nit,
            sigla            = EXCLUDED.sigla,
            estado           = EXCLUDED.estado,
            tipo_empresa     = EXCLUDED.tipo_empresa,
            departamento     = EXCLUDED.departamento,
            municipio        = EXCLUDED.municipio,
            profesional      = EXCLUDED.profesional,
            fecha_importacion = NOW()
    """

    dest_cols = ['fondo', 'subclase', 'codigo_sui', 'nit', 'nombre_prestador',
                 'sigla', 'estado', 'tipo_empresa', 'fuente_generacion',
                 'departamento', 'municipio', 'profesional']

    rows = [tuple(r.get(c) for c in dest_cols) for _, r in df.iterrows()]

    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=200)
        conn.commit()

    duracion = time.time() - t0
    stats = {
        'hoja': 'Inicio (empresas)',
        'filas_leidas': filas_leidas,
        'filas_importadas': len(rows),
        'filas_duplicadas': 0,
        'filas_error': 0,
        'duracion_seg': round(duracion, 2),
    }
    _log_import(conn, xlsx_path.name, stats)
    logger.info(f"✅ Empresas: {len(rows)} registros upserted ({duracion:.1f}s)")
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# MAPA
# ═══════════════════════════════════════════════════════════════════════════════

def importar_mapa(xlsx_path: Path, conn) -> dict:
    """Lee hoja Mapa (cobertura geográfica) e inserta."""
    t0 = time.time()
    logger.info(f"📖 Leyendo hoja 'Mapa' de {xlsx_path.name}...")
    df = pd.read_excel(xlsx_path, sheet_name='Mapa')
    cols = [c for c in df.columns if not str(c).startswith('Unnamed')]
    df = df[cols]

    filas_leidas = len(df)

    # Columnas: Departamento, Municipio, ZNI/SIN, 0 (nombre empresa), #Localidades, #Usuarios
    rename = {}
    for c in df.columns:
        cl = str(c).lower()
        if 'departamento' in cl:
            rename[c] = 'departamento'
        elif 'municipio' in cl:
            rename[c] = 'municipio'
        elif 'zni' in cl or 'sin' in cl:
            rename[c] = 'area'
        elif 'localidades' in cl:
            rename[c] = 'localidades'
        elif 'usuarios' in cl:
            rename[c] = 'usuarios'
        elif str(c) == '0' or 'prestador' in cl or 'empresa' in cl:
            rename[c] = 'nombre_prestador'
    df = df.rename(columns=rename)

    # Asegurar columnas destino
    for col in ['departamento', 'municipio', 'area', 'nombre_prestador', 'localidades', 'usuarios']:
        if col not in df.columns:
            df[col] = None

    df['localidades'] = pd.to_numeric(df['localidades'], errors='coerce')
    df['usuarios'] = pd.to_numeric(df['usuarios'], errors='coerce')
    df = df.where(pd.notna(df), None)

    # Truncar y reinsertar (la hoja Mapa es un snapshot completo)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE subsidios_mapa RESTART IDENTITY")

    insert_sql = """
        INSERT INTO subsidios_mapa (departamento, municipio, area, nombre_prestador, localidades, usuarios)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    dest_cols = ['departamento', 'municipio', 'area', 'nombre_prestador', 'localidades', 'usuarios']

    def safe_val(v):
        """Convert NaN/NaT to None, large floats to int."""
        if v is None or (isinstance(v, float) and (pd.isna(v) or v != v)):
            return None
        if isinstance(v, float) and v == int(v):
            return int(v)
        return v

    rows = [tuple(safe_val(r.get(c)) for c in dest_cols) for _, r in df.iterrows()]

    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=500)
        conn.commit()

    duracion = time.time() - t0
    stats = {
        'hoja': 'Mapa',
        'filas_leidas': filas_leidas,
        'filas_importadas': len(rows),
        'filas_duplicadas': 0,
        'filas_error': 0,
        'duracion_seg': round(duracion, 2),
    }
    _log_import(conn, xlsx_path.name, stats)
    logger.info(f"✅ Mapa: {len(rows)} registros ({duracion:.1f}s)")
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _count_table(cur, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def _log_import(conn, archivo: str, stats: dict):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO subsidios_import_log
                (archivo, hoja, filas_leidas, filas_importadas, filas_duplicadas,
                 filas_error, duracion_seg, observaciones)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            archivo, stats['hoja'], stats['filas_leidas'],
            stats['filas_importadas'], stats['filas_duplicadas'],
            stats['filas_error'], stats['duracion_seg'], None,
        ))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='ETL Subsidios DDE → PostgreSQL')
    parser.add_argument('--archivo', type=str, default=str(DEFAULT_XLSX),
                        help='Ruta al archivo Excel')
    parser.add_argument('--hoja', type=str, default='todas',
                        choices=['todas', 'pagos', 'empresas', 'mapa'],
                        help='Hoja a importar')
    parser.add_argument('--reload', action='store_true',
                        help='Truncar subsidios_pagos antes de importar (carga completa)')
    args = parser.parse_args()

    xlsx_path = Path(args.archivo)
    if not xlsx_path.exists():
        logger.error(f"❌ Archivo no encontrado: {xlsx_path}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("🔄 ETL Subsidios DDE → PostgreSQL")
    logger.info(f"   Archivo: {xlsx_path}")
    logger.info(f"   Hoja: {args.hoja}")
    logger.info("=" * 60)

    conn = get_connection()
    try:
        ensure_schema(conn)

        if args.reload and args.hoja in ('todas', 'pagos'):
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE subsidios_pagos RESTART IDENTITY")
            conn.commit()
            logger.info("🗑️  subsidios_pagos truncado para recarga completa")

        if args.hoja in ('todas', 'pagos'):
            importar_pagos(xlsx_path, conn)
        if args.hoja in ('todas', 'empresas'):
            importar_empresas(xlsx_path, conn)
        if args.hoja in ('todas', 'mapa'):
            importar_mapa(xlsx_path, conn)

        logger.info("🏁 ETL completado exitosamente")
    except Exception as e:
        logger.error(f"❌ Error ETL: {e}", exc_info=True)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()

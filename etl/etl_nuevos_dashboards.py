#!/usr/bin/env python3
"""
ETL: Carga inicial de Excel → schemas de portal_energetico
Cubre: supervision, comunidades, presupuesto, contratos_or

Uso:
    python etl/etl_nuevos_dashboards.py                   # todos
    python etl/etl_nuevos_dashboards.py --schema supervision
    python etl/etl_nuevos_dashboards.py --schema comunidades
    python etl/etl_nuevos_dashboards.py --schema presupuesto
    python etl/etl_nuevos_dashboards.py --schema contratos_or
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from infrastructure.database.connection import connection_manager
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _clean_col(name: str) -> str:
    """Convierte nombre de columna a snake_case válido para PostgreSQL."""
    name = str(name).strip()
    name = re.sub(r'[\r\n\t]+', ' ', name)
    name = re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚüÜñÑ _%]', ' ', name)
    name = name.strip().lower()
    name = re.sub(r'\s+', '_', name)
    # Replace accented chars
    replacements = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
                    'ü': 'u', 'ñ': 'n', 'Á': 'a', 'É': 'e', 'Í': 'i',
                    'Ó': 'o', 'Ú': 'u', 'Ü': 'u', 'Ñ': 'n'}
    for src, dst in replacements.items():
        name = name.replace(src, dst)
    name = re.sub(r'[^a-z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    if not name or name[0].isdigit():
        name = 'col_' + name
    return name[:63]  # PostgreSQL max identifier length


def _make_cols_unique(cols: list) -> list:
    """Asegura que los nombres de columna sean únicos y no colisionen con columnas reservadas."""
    # Rename reserved names
    reserved = {'id', 'fecha_carga'}
    seen = {}
    result = []
    for c in cols:
        original = c
        if c in reserved:
            c = f'{c}_origen'
        if c in seen:
            seen[c] += 1
            c = f"{c}_{seen[c]}"
        seen[c] = 0
        result.append(c)
    return result


def _pg_type(series: pd.Series) -> str:
    """Infiere tipo PostgreSQL desde una Serie de pandas."""
    dtype = series.dtype
    if pd.api.types.is_integer_dtype(dtype):
        return 'BIGINT'
    if pd.api.types.is_float_dtype(dtype):
        return 'NUMERIC'
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return 'TIMESTAMP'
    if pd.api.types.is_bool_dtype(dtype):
        return 'BOOLEAN'
    # Only try date detection on object/string columns
    if dtype == object:
        sample = series.dropna().head(5)
        if len(sample) > 0 and all(isinstance(v, str) for v in sample):
            try:
                parsed = pd.to_datetime(sample, errors='raise', format='mixed')
                return 'TIMESTAMP'
            except Exception:
                pass
    return 'TEXT'


def load_dataframe(conn, schema: str, table: str, df: pd.DataFrame, truncate: bool = True) -> int:
    """
    Carga un DataFrame en schema.table.
    Crea la tabla si no existe, trunca si truncate=True.
    Retorna número de filas insertadas.
    """
    if df.empty:
        logger.warning(f"{schema}.{table}: DataFrame vacío, se omite")
        return 0

    # Clean column names
    clean_names = _make_cols_unique([_clean_col(c) for c in df.columns])
    df.columns = clean_names

    # Drop fully-empty columns
    df = df.dropna(axis=1, how='all')
    df = df.dropna(how='all')  # drop empty rows

    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}, public;")

        # Build CREATE TABLE
        col_defs = ['id SERIAL PRIMARY KEY',
                    'fecha_carga TIMESTAMP DEFAULT NOW()']
        for col in df.columns:
            pg_t = _pg_type(df[col])
            col_defs.append(f'"{col}" {pg_t}')

        create_sql = (
            f'CREATE TABLE IF NOT EXISTS {schema}."{table}" '
            f'({", ".join(col_defs)});'
        )
        cur.execute(create_sql)

        if truncate:
            cur.execute(f'TRUNCATE TABLE {schema}."{table}" RESTART IDENTITY;')

        # Insert rows
        cols_quoted = ', '.join(f'"{c}"' for c in df.columns)
        placeholders = ', '.join(['%s'] * len(df.columns))
        insert_sql = (
            f'INSERT INTO {schema}."{table}" ({cols_quoted}) '
            f'VALUES ({placeholders})'
        )

        rows = []
        for _, row in df.iterrows():
            vals = []
            for val in row.values:
                if val is None:
                    vals.append(None)
                elif isinstance(val, float) and pd.isna(val):
                    vals.append(None)
                elif isinstance(val, pd.Timestamp):
                    vals.append(None if pd.isnull(val) else val.to_pydatetime())
                elif hasattr(val, '__class__') and val.__class__.__name__ == 'NaTType':
                    vals.append(None)
                elif isinstance(val, str):
                    vals.append(val)
                elif hasattr(val, 'item'):  # numpy scalar (np.float64, np.int64, etc.)
                    vals.append(None if pd.isnull(val) else val.item())
                else:
                    try:
                        if pd.isnull(val):
                            vals.append(None)
                        else:
                            vals.append(val)
                    except (TypeError, ValueError):
                        vals.append(val)
            rows.append(tuple(vals))

        psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=500)
        # Restore search_path to database default before returning the
        # connection to the shared pool — conn.reset() only rolls back
        # transactions, it does NOT send RESET ALL.
        cur.execute("RESET search_path")

    conn.commit()
    logger.info(f"  ✅ {schema}.{table}: {len(rows)} filas cargadas")
    return len(rows)


# ─── ETL Supervision ──────────────────────────────────────────────────────────

def etl_supervision() -> None:
    """Carga Matriz General de Reparto.xlsx → schema supervision."""
    xlsx_path = BASE_DIR / 'data' / 'base_de_datos_supervision' / 'Matriz General de Reparto.xlsx'
    logger.info(f"=== ETL SUPERVISION: {xlsx_path.name} ===")

    # Main sheet: Matriz General de Reparto
    df_main = pd.read_excel(xlsx_path, sheet_name='Matriz General de Reparto')
    # Liquidacion
    df_liq = pd.read_excel(xlsx_path, sheet_name='Grupo liquidacion')
    # Ejecucion
    df_ejec = pd.read_excel(xlsx_path, sheet_name='Grupo Ejecucion')

    with connection_manager.get_connection() as conn:
        load_dataframe(conn, 'supervision', 'contratos', df_main)
        load_dataframe(conn, 'supervision', 'contratos_liquidacion', df_liq)
        load_dataframe(conn, 'supervision', 'contratos_ejecucion', df_ejec)

    logger.info("=== supervision: completado ===")


# ─── ETL Comunidades ──────────────────────────────────────────────────────────

def etl_comunidades() -> None:
    """Carga Resumen_Implementación.xlsx → schema comunidades."""
    xlsx_path = BASE_DIR / 'data' / 'base de datos comunidades energeticas' / 'Resumen_Implementación.xlsx'
    logger.info(f"=== ETL COMUNIDADES: {xlsx_path.name} ===")

    # Base: main registry of communities
    df_base = pd.read_excel(xlsx_path, sheet_name='Base')
    # Implementadas: implemented communities
    df_impl = pd.read_excel(xlsx_path, sheet_name='Implementadas')

    with connection_manager.get_connection() as conn:
        load_dataframe(conn, 'comunidades', 'base', df_base)
        load_dataframe(conn, 'comunidades', 'implementadas', df_impl)

    logger.info("=== comunidades: completado ===")


# ─── ETL Presupuesto ──────────────────────────────────────────────────────────

def etl_presupuesto() -> None:
    """Carga Acuerdos de Gestión DEE 2026.xlsx → schema presupuesto."""
    xlsx_path = BASE_DIR / 'data' / 'ejecucion_presupuestal' / 'Acuerdos de Gestión DEE 2026.xlsx'
    logger.info(f"=== ETL PRESUPUESTO: {xlsx_path.name} ===")

    # Resumen por proyecto/fondo (header en fila 3, índice 0-based)
    df_res = pd.read_excel(xlsx_path, sheet_name='resumen', header=3)
    df_res = df_res.dropna(how='all')
    # Eliminar columnas sin nombre
    df_res = df_res.loc[:, ~df_res.columns.str.startswith('Unnamed')]

    # Compromisos total mensual (header on row index 1, data rows 2-6)
    df_comp = pd.read_excel(xlsx_path, sheet_name='Compromisostotal', header=1)
    df_comp = df_comp.dropna(how='all').dropna(axis=1, how='all')
    # Eliminar columnas sin nombre (columnas basura del Excel)
    df_comp = df_comp.loc[:, ~df_comp.columns.str.startswith('Unnamed')]

    with connection_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS presupuesto.resumen CASCADE;")
            cur.execute("DROP TABLE IF EXISTS presupuesto.compromisos_mensual CASCADE;")
        conn.commit()
        load_dataframe(conn, 'presupuesto', 'resumen', df_res)
        load_dataframe(conn, 'presupuesto', 'compromisos_mensual', df_comp)

    logger.info("=== presupuesto: completado ===")


# ─── ETL Contratos OR ─────────────────────────────────────────────────────────

def etl_contratos_or() -> None:
    """Carga Seguimiento Completo_CE_Contratos.xlsx → schema contratos_or."""
    xlsx_path = (BASE_DIR / 'data' / 'base_de_datos_contratos_or' /
                 'Seguimiento Completo_CE_Contratos.xlsx')
    logger.info(f"=== ETL CONTRATOS OR: {xlsx_path.name} ===")

    # Header is on row index 1 (row 0 is blank)
    df = pd.read_excel(xlsx_path, sheet_name='Hoja1', header=1)
    # Drop the first (empty) column
    df = df.dropna(axis=1, how='all').dropna(how='all')

    with connection_manager.get_connection() as conn:
        load_dataframe(conn, 'contratos_or', 'seguimiento', df)

    logger.info("=== contratos_or: completado ===")


# ─── ETL Subsidios ────────────────────────────────────────────────────────────

def etl_subsidios() -> None:
    """Carga 2026-02-17 Info Subs y Cont - Info tablero.xlsx → schema subsidios."""
    xlsx_path = (BASE_DIR / 'data' / 'onedrive' /
                 '2026-02-17 Info Subs y Cont - Info tablero (1).xlsx')
    logger.info(f"=== ETL SUBSIDIOS: {xlsx_path.name} ===")

    # Hoja5 tiene el histórico consolidado con Deficit acumulado
    df = pd.read_excel(xlsx_path, sheet_name='Hoja5', header=0)
    df = df.dropna(how='all')

    # Seleccionar y renombrar columnas clave
    columnas = {
        'Año': 'anio',
        'Subsidios (SIN+ZNI)': 'subsidios',
        'Contribuciones': 'contribuciones',
        'Déficit Año': 'deficit_anual',
        'Deficit acumulado': 'deficit_acumulado',
        'Apropiación PGN': 'apropiacion_pgn',
        'Recursos Faltantes Año': 'recursos_faltantes',
    }
    df = df[list(columnas.keys())].rename(columns=columnas)
    # Filtrar solo filas con año válido
    df = df[df['anio'].notna()]
    df['anio'] = df['anio'].astype(int)

    with connection_manager.get_connection() as conn:
        load_dataframe(conn, 'subsidios', 'deficit_historico', df)

    logger.info("=== subsidios: completado ===")


# ─── Main ─────────────────────────────────────────────────────────────────────

HANDLERS = {
    'supervision': etl_supervision,
    'comunidades': etl_comunidades,
    'presupuesto': etl_presupuesto,
    'contratos_or': etl_contratos_or,
    'subsidios': etl_subsidios,
}


def main():
    parser = argparse.ArgumentParser(description='ETL nuevos dashboards → PostgreSQL')
    parser.add_argument(
        '--schema',
        choices=list(HANDLERS.keys()),
        default=None,
        help='Schema a cargar (default: todos)'
    )
    args = parser.parse_args()

    targets = [args.schema] if args.schema else list(HANDLERS.keys())
    errors = []

    for schema in targets:
        try:
            HANDLERS[schema]()
        except Exception as e:
            logger.error(f"Error en {schema}: {e}", exc_info=True)
            errors.append(schema)

    if errors:
        logger.error(f"Fallaron: {errors}")
        sys.exit(1)
    else:
        logger.info("✅ ETL completado sin errores")


if __name__ == '__main__':
    main()

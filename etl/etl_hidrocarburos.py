#!/usr/bin/env python3
"""
ETL: Direccion_Hidrocarburos.xlsx → PostgreSQL (schema hidrocarburos)

Hojas:
  - "Ejecución Presupuestal": resumen + tabla de proyectos (layout irregular,
    no es una tabla limpia — se ancla por etiquetas de la columna 0/1).
  - "Producción petroleo_gas": serie diaria (cols A-D) + 4 mini-tablas "Top 5"
    apiladas en las columnas F-G (campos/contratos de petróleo y gas).

Uso:
    python etl/etl_hidrocarburos.py                          # importar todo
    python etl/etl_hidrocarburos.py --archivo /ruta/otro.xlsx
"""
import argparse
import logging
import math
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import psycopg2

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = BASE_DIR / "data" / "onedrive" / "Direccion_Hidrocarburos.xlsx"
SCHEMA_SQL = BASE_DIR / "sql" / "hidrocarburos_schema.sql"

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [ETL_HIDROCARBUROS] - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "etl_hidrocarburos.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

SHEET_PRESUPUESTO = "Ejecución Presupuestal"
SHEET_PRODUCCION = "Producción petroleo_gas"

CATEGORIA_TOP5 = {
    "Campos Productores de Petroleo": ("campos_petroleo", "BLS"),
    "Contratos Productores de Petroleo": ("contratos_petroleo", "BLS"),
    "Campos Productores de Gas": ("campos_gas", "MPC"),
    "Contratos Productores de Gas": ("contratos_gas", "MPC"),
}


def get_connection():
    """Conexión directa a PostgreSQL (misma config que el resto de ETLs)."""
    return psycopg2.connect(
        dbname="portal_energetico",
        user="postgres",
        host="localhost",
        port=5432,
        options="-c search_path=hidrocarburos,public",
    )


def ensure_schema(conn) -> None:
    """Crea el schema/tablas si no existen ejecutando el DDL idempotente."""
    if not SCHEMA_SQL.exists():
        logger.error("Schema no encontrado: %s", SCHEMA_SQL)
        return
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()
    logger.info("✅ Schema hidrocarburos verificado/creado")


def _num(v):
    """Convierte NaN/None/strings vacíos a None; el resto a float."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _parse_top5(raw: "pd.DataFrame") -> list[dict]:
    """Parsea las 4 mini-tablas 'Top 5' apiladas en las columnas F-G (índices 6-7)."""
    registros: list[dict] = []
    categoria_actual: str | None = None
    unidad_actual: str | None = None
    mes: str | None = None

    for _, row in raw.iterrows():
        c6, c7 = row.get(6), row.get(7)
        etiqueta = c6.strip() if isinstance(c6, str) else None

        if etiqueta and etiqueta.startswith("Información Mes"):
            mes = etiqueta.split(":", 1)[-1].strip()
            continue
        if etiqueta in CATEGORIA_TOP5:
            categoria_actual, unidad_actual = CATEGORIA_TOP5[etiqueta]
            continue
        if etiqueta in ("Campo", "Contrato", "Top 5"):
            continue
        if categoria_actual and etiqueta and pd.notna(c7):
            registros.append({
                "mes": mes,
                "categoria": categoria_actual,
                "nombre": etiqueta,
                "valor": _num(c7),
                "unidad": unidad_actual,
            })

    return registros


def importar_presupuesto(xlsx_path: Path, conn) -> dict:
    """Parsea la hoja 'Ejecución Presupuestal' y carga resumen + proyectos."""
    raw = pd.read_excel(xlsx_path, sheet_name=SHEET_PRESUPUESTO, header=None)
    col0 = raw[0].astype(str).str.strip()
    col1 = raw[1].astype(str).str.strip()

    def _fila_por_etiqueta(etiqueta: str):
        m = raw[col0 == etiqueta]
        return m.iloc[0] if not m.empty else None

    fecha_actualizacion = None
    fila_fecha = raw[col1 == "Fecha actualización"]
    if not fila_fecha.empty:
        fecha_actualizacion = pd.to_datetime(fila_fecha.iloc[0][2], errors="coerce")

    # fecha_actualizacion es la clave del histórico — nunca debe quedar NULL.
    # Si el Excel no trae la fila "Fecha actualización" (caso borde), se usa
    # la fecha de hoy como fallback para no romper el upsert.
    fecha_resumen: date = fecha_actualizacion.date() if pd.notna(fecha_actualizacion) else date.today()

    r_apr = _fila_por_etiqueta("Apropiación Vigente")
    r_com = _fila_por_etiqueta("Compromisos")
    r_obl = _fila_por_etiqueta("Obligaciones")
    r_pxc = _fila_por_etiqueta("Por comprometer")

    resumen = {
        "fecha_actualizacion": fecha_resumen,
        "apropiacion_vigente": _num(r_apr[1]) if r_apr is not None else None,
        "compromisos": _num(r_com[1]) if r_com is not None else None,
        "obligaciones": _num(r_obl[1]) if r_obl is not None else None,
        "por_comprometer": _num(r_pxc[1]) if r_pxc is not None else None,
        "pct_compromisos": _num(r_com[2]) if r_com is not None else None,
        "pct_obligaciones": _num(r_obl[2]) if r_obl is not None else None,
    }

    proyectos: list[dict] = []
    header_rows = raw[col1 == "Apropiacion vigente"]
    if not header_rows.empty:
        hi = header_rows.index[0]
        for _, row in raw.iloc[hi + 1:].iterrows():
            nombre = row[0]
            if not isinstance(nombre, str) or not nombre.strip():
                continue  # fila de totales u otra fila vacía: no es un proyecto
            proyectos.append({
                "proyecto": nombre.strip(),
                "apropiacion_vigente": _num(row[1]),
                "compromisos": _num(row[2]),
                "obligaciones": _num(row[3]),
                "por_comprometer": _num(row[4]),
                "pct_compromisos": _num(row[5]),
                "pct_obligacion": _num(row[6]),
            })

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO hidrocarburos.presupuesto_resumen
            (fecha_actualizacion, apropiacion_vigente, compromisos, obligaciones,
             por_comprometer, pct_compromisos, pct_obligaciones)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fecha_actualizacion) DO UPDATE SET
            apropiacion_vigente = EXCLUDED.apropiacion_vigente,
            compromisos         = EXCLUDED.compromisos,
            obligaciones        = EXCLUDED.obligaciones,
            por_comprometer     = EXCLUDED.por_comprometer,
            pct_compromisos     = EXCLUDED.pct_compromisos,
            pct_obligaciones    = EXCLUDED.pct_obligaciones,
            fecha_carga         = NOW()
        """,
        (
            resumen["fecha_actualizacion"], resumen["apropiacion_vigente"], resumen["compromisos"],
            resumen["obligaciones"], resumen["por_comprometer"], resumen["pct_compromisos"],
            resumen["pct_obligaciones"],
        ),
    )

    for p in proyectos:
        cur.execute(
            """
            INSERT INTO hidrocarburos.presupuesto_proyectos
                (fecha_actualizacion, proyecto, apropiacion_vigente, compromisos, obligaciones,
                 por_comprometer, pct_compromisos, pct_obligacion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (fecha_actualizacion, proyecto) DO UPDATE SET
                apropiacion_vigente = EXCLUDED.apropiacion_vigente,
                compromisos         = EXCLUDED.compromisos,
                obligaciones        = EXCLUDED.obligaciones,
                por_comprometer     = EXCLUDED.por_comprometer,
                pct_compromisos     = EXCLUDED.pct_compromisos,
                pct_obligacion      = EXCLUDED.pct_obligacion,
                fecha_carga         = NOW()
            """,
            (
                resumen["fecha_actualizacion"], p["proyecto"], p["apropiacion_vigente"], p["compromisos"],
                p["obligaciones"], p["por_comprometer"], p["pct_compromisos"], p["pct_obligacion"],
            ),
        )

    logger.info(
        "  presupuesto_resumen: upsert fecha=%s · presupuesto_proyectos: %d filas upsert",
        resumen["fecha_actualizacion"], len(proyectos),
    )
    return {"resumen": 1, "proyectos": len(proyectos)}


def importar_produccion(xlsx_path: Path, conn) -> dict:
    """Parsea la hoja 'Producción petroleo_gas': serie diaria + mini-tablas Top 5."""
    df = pd.read_excel(xlsx_path, sheet_name=SHEET_PRODUCCION, header=0, usecols=[0, 1, 2, 3])
    df.columns = ["fecha", "petroleo_bbl", "gas_fiscalizado_mpc", "gas_comercializado_mpc"]
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"])

    raw = pd.read_excel(xlsx_path, sheet_name=SHEET_PRODUCCION, header=None)
    top5 = _parse_top5(raw)

    # `periodo` (YYYY-MM) ancla el Top 5 al mes real de los datos — más
    # confiable que el texto libre "Junio" del Excel (sin año, colisionaría
    # entre años). Se deriva de la fecha más reciente de la serie diaria.
    periodo = df["fecha"].max().strftime("%Y-%m") if not df.empty else date.today().strftime("%Y-%m")

    cur = conn.cursor()
    for _, row in df.iterrows():
        cur.execute(
            """
            INSERT INTO hidrocarburos.produccion_diaria
                (fecha, petroleo_bbl, gas_fiscalizado_mpc, gas_comercializado_mpc)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (fecha) DO UPDATE SET
                petroleo_bbl           = EXCLUDED.petroleo_bbl,
                gas_fiscalizado_mpc    = EXCLUDED.gas_fiscalizado_mpc,
                gas_comercializado_mpc = EXCLUDED.gas_comercializado_mpc,
                fecha_carga            = NOW()
            """,
            (
                row["fecha"].date(), _num(row["petroleo_bbl"]),
                _num(row["gas_fiscalizado_mpc"]), _num(row["gas_comercializado_mpc"]),
            ),
        )

    for t in top5:
        cur.execute(
            """
            INSERT INTO hidrocarburos.produccion_top5 (periodo, mes, categoria, nombre, valor, unidad)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (periodo, categoria, nombre) DO UPDATE SET
                mes         = EXCLUDED.mes,
                valor       = EXCLUDED.valor,
                unidad      = EXCLUDED.unidad,
                fecha_carga = NOW()
            """,
            (periodo, t["mes"], t["categoria"], t["nombre"], t["valor"], t["unidad"]),
        )

    logger.info(
        "  produccion_diaria: %d filas upsert · produccion_top5: %d filas upsert (periodo=%s)",
        len(df), len(top5), periodo,
    )
    return {"produccion_diaria": len(df), "top5": len(top5), "periodo": periodo}


def run_etl(xlsx_path: Path) -> dict:
    """Carga las 4 tablas de hidrocarburos en una sola transacción atómica."""
    conn = get_connection()
    try:
        ensure_schema(conn)
        r_presupuesto = importar_presupuesto(xlsx_path, conn)
        r_produccion = importar_produccion(xlsx_path, conn)
        conn.commit()
        logger.info("✅ ETL hidrocarburos: transacción commiteada")
        return {"presupuesto": r_presupuesto, "produccion": r_produccion}
    except Exception:
        conn.rollback()
        logger.error("❌ Error en ETL hidrocarburos — ROLLBACK ejecutado", exc_info=True)
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="ETL Direccion_Hidrocarburos.xlsx → PostgreSQL")
    parser.add_argument("--archivo", type=Path, default=DEFAULT_XLSX, help="Ruta al Excel a importar")
    args = parser.parse_args()

    if not args.archivo.exists():
        logger.error("Archivo no encontrado: %s", args.archivo)
        sys.exit(1)

    resultado = run_etl(args.archivo)
    logger.info("Resultado: %s", resultado)


if __name__ == "__main__":
    main()

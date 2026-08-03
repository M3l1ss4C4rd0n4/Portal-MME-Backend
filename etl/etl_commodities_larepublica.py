#!/usr/bin/env python3
"""
ETL: larepublica.co /api/quote/multiple → PostgreSQL (hidrocarburos.commodities_historico)

Guarda el histórico diario de PETRÓLEO WTI (id 55) y PETRÓLEO BRENT (id 57).
Endpoint público (sin auth), descubierto inspeccionando con Playwright el
tráfico real de la página https://www.larepublica.co/indicadores-economicos/commodities/petroleo
(el parámetro correcto es `names[]=<id>|<nombre>`, no `ids=<id>,<id>` como
sugeriría el nombre del endpoint). Con idx=4/scale=4 devuelve ~1 año de
histórico diario, así que cada corrida trae y upsertea (ON CONFLICT) el año
completo — autocorrige cualquier día que el cron se haya saltado.

Uso:
    python etl/etl_commodities_larepublica.py
"""
import logging
import sys
from datetime import date
from pathlib import Path

import psycopg2
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_SQL = BASE_DIR / "sql" / "hidrocarburos_schema.sql"

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [ETL_COMMODITIES] - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "etl_commodities.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

MULTIPLE_URL = "https://www.larepublica.co/api/quote/multiple"
QUOTES = [("55", "PETRÓLEO WTI", "WTI"), ("57", "PETRÓLEO BRENT", "BRENT")]

MESES_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def get_connection():
    return psycopg2.connect(
        dbname="portal_energetico",
        user="postgres",
        host="localhost",
        port=5432,
        options="-c search_path=hidrocarburos,public",
    )


def ensure_schema(conn) -> None:
    if not SCHEMA_SQL.exists():
        logger.error("Schema no encontrado: %s", SCHEMA_SQL)
        return
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()


def _parse_fecha_es(s: str) -> date | None:
    """Convierte 'dd mmm yy' (español, ej. '06 jul 26') a date."""
    try:
        dia_str, mes_str, anio_str = s.strip().split()
        return date(2000 + int(anio_str), MESES_ES[mes_str.lower()], int(dia_str))
    except (ValueError, KeyError, IndexError):
        return None


def fetch_historico(dias: str = "4", escala: str = "4") -> dict:
    """
    Consulta /api/quote/multiple y retorna {commodity: [(fecha, valor), ...]}
    ordenado por fecha ascendente. idx=4/scale=4 = rango "1A" (~1 año).
    """
    params = [("names[]", f"{qid}|{nombre}") for qid, nombre, _ in QUOTES]
    params += [("idx", dias), ("scale", escala)]
    resp = requests.get(params=params, url=MULTIPLE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    graph = data.get("graphData", [])
    if len(graph) < 2:
        logger.warning("graphData vacío en la respuesta de %s", MULTIPLE_URL)
        return {}

    header = graph[0]  # ["Fecha", "PETRÓLEO WTI", "PETRÓLEO BRENT"]
    nombre_a_commodity = {nombre: commodity for _, nombre, commodity in QUOTES}
    columnas = [nombre_a_commodity.get(h) for h in header[1:]]

    series: dict[str, list] = {c: [] for c in columnas if c}
    for fila in graph[1:]:
        fecha = _parse_fecha_es(fila[0])
        if fecha is None:
            continue
        for commodity, valor in zip(columnas, fila[1:]):
            if commodity and valor is not None:
                series[commodity].append((fecha, float(valor)))

    for commodity in series:
        series[commodity].sort(key=lambda t: t[0])
    return series


def guardar_historico(series: dict) -> int:
    if not series:
        logger.warning("No hay series de commodities para guardar")
        return 0

    conn = get_connection()
    total = 0
    try:
        ensure_schema(conn)
        cur = conn.cursor()
        for commodity, puntos in series.items():
            for i, (fecha, valor) in enumerate(puntos):
                anterior = puntos[i - 1][1] if i > 0 else None
                variacion_abs = round(valor - anterior, 4) if anterior is not None else None
                variacion_pct = round(variacion_abs / anterior * 100, 4) if anterior else None
                cur.execute(
                    """
                    INSERT INTO hidrocarburos.commodities_historico
                        (fecha, commodity, valor_usd, variacion_abs, variacion_pct, fecha_carga)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (fecha, commodity) DO UPDATE SET
                        valor_usd     = EXCLUDED.valor_usd,
                        variacion_abs = EXCLUDED.variacion_abs,
                        variacion_pct = EXCLUDED.variacion_pct,
                        fecha_carga   = NOW()
                    """,
                    (fecha, commodity, valor, variacion_abs, variacion_pct),
                )
                total += 1
        conn.commit()
        logger.info("✅ %d filas upserted (%s)", total, {c: len(p) for c, p in series.items()})
        return total
    except Exception:
        conn.rollback()
        logger.error("❌ Error guardando histórico de commodities", exc_info=True)
        raise
    finally:
        conn.close()


def main():
    series = fetch_historico()
    n = guardar_historico(series)
    if n == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

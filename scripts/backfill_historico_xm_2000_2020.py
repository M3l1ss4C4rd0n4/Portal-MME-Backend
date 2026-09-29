#!/usr/bin/env python3
"""
Backfill histórico XM 2000-2020 para el tablero Balance Oferta-Demanda del SIN.

Contexto (2026-09-23): el usuario notó, correctamente, que la falta de
historia previa a 2020 en sector_energetico.metrics para DemaReal/
DispoDeclarada/CapEfecNeta NO es una limitación real de la API de XM — es
solo que nunca se hizo un backfill deliberado; el cron normal solo mantiene
una ventana rodante reciente (dias_history en etl/config_metricas.py). Se
verificó en vivo contra la API de XM (pydataxm.ReadDB) que SÍ hay datos
reales desde 2000-01-01 (1999 y antes: la API responde 400/vacío) para
Gene, DemaReal y DispoDeclarada; CapEfecNeta también responde datos reales
desde 2000-01-01.

Además se encontró un bug de datos real en CapEfecNeta: unas pocas filas
de 2021 quedaron guardadas con el valor dividido por 1 000 000 (p. ej.
Guavio/GVIO = 1.25 en vez de 1 250 000 kW), de una implementación de ETL
anterior — y luego hay un vacío casi total entre 2021 y marzo de 2026,
cuando empezó a cargarse de forma completa y correcta (valor crudo en kW,
sin conversión, ver etl/etl_rules.py::_r("CapEfecNeta", ...)). Este script
re-descarga TODO el rango de CapEfecNeta (no solo el hueco 2000-2020) para
que el upsert (ON CONFLICT ... DO UPDATE, ver
infrastructure/database/manager.py::upsert_metrics_bulk) sobreescriba esas
filas viejas con el valor correcto.

IMPORTANTE — por qué CapEfecNeta no reusa poblar_metrica() de
etl_xm_to_postgres.py como DemaReal/DispoDeclarada: la respuesta cruda de
XM para CapEfecNeta tiene columnas ['Id','Code','Value','Date'], donde
'Id' es una etiqueta genérica del TIPO de entidad ('Recurso' literal, no
el código de la planta) y 'Code' trae el código real. La lista de
prioridad de columnas de poblar_metrica() (['Values_code','Name','Id',...])
NO incluye 'Code' y encuentra 'Id' primero → asignaría recurso='Recurso'
a TODAS las filas, que luego la validación de poblar_metrica() rechaza
por ser un código genérico. Se verificó este comportamiento antes de
escribir este script — por eso CapEfecNeta usa su propia función de carga
aquí en vez de poblar_metrica().

Uso:
    venv/bin/python3 scripts/backfill_historico_xm_2000_2020.py [--solo-metrica NOMBRE]
"""

import argparse
import logging
import os
import sys
import time
import warnings
from datetime import date, timedelta

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

FECHA_INICIO_XM = date(2000, 1, 1)  # confirmado en vivo: 1999 y antes → sin datos
FECHA_INICIO_ENFICC = date(2007, 1, 1)  # confirmado en vivo: 2006-06 → 0 filas, 2007-01 → datos reales
                                          # (coincide con la entrada en vigor del Cargo por
                                          # Confiabilidad, Res. CREG 071/2006)


def backfill_via_poblar_metrica(obj_api, metric: str, entity: str, fecha_inicio: date, fecha_fin: date, batch_size: int):
    """Reusa etl_xm_to_postgres.py::poblar_metrica() — ya prueba, convierte
    unidades y valida correctamente para métricas con columna Values_code
    (DemaReal, DispoDeclarada)."""
    from etl.etl_xm_to_postgres import poblar_metrica

    config = {
        "metric": metric,
        "entity": entity,
        "conversion": "horas_a_diario",
        "dias_history": (fecha_fin - fecha_inicio).days + 1,
        "batch_size": batch_size,
    }
    total = poblar_metrica(
        obj_api, config, usar_timeout=False,
        fecha_inicio_custom=fecha_inicio.isoformat(),
        fecha_fin_custom=fecha_fin.isoformat(),
    )
    log.info(f"[{metric}/{entity}] TOTAL insertado/actualizado: {total} filas")
    return total


def backfill_metrica_id_code_value(
    obj_api, metric: str, entity: str, fecha_inicio: date, fecha_fin: date,
    unidad: str, divisor: float = 1.0, batch_size_dias: int = 30,
):
    """
    Backfill genérico para métricas cuya respuesta cruda de XM trae columnas
    ['Id','Code','Value','Date'] (Id = etiqueta genérica del tipo de entidad,
    NO el código de la planta — ver docstring del módulo sobre por qué estas
    métricas no pueden reusar poblar_metrica() de etl_xm_to_postgres.py).

    Usado para CapEfecNeta (divisor=1, valor crudo en kW — ver
    etl/etl_rules.py::_r("CapEfecNeta", conversion=ConversionType.NONE)) y
    para ENFICC/ObligEnerFirme (divisor=1_000_000, kWh→GWh — verificado
    comparando el valor crudo de la API contra el valor ya almacenado en BD
    para fechas recientes donde la carga actual sí es correcta).
    """
    from infrastructure.database.manager import db_manager

    total_general = 0
    current = fecha_inicio
    while current <= fecha_fin:
        batch_end = min(current + timedelta(days=batch_size_dias - 1), fecha_fin)
        try:
            df = obj_api.request_data(metric, entity, str(current), str(batch_end))
        except Exception as e:
            log.warning(f"[{metric}] batch {current}..{batch_end} ERROR: {e}")
            current = batch_end + timedelta(days=1)
            time.sleep(1.0)
            continue

        if df is None or df.empty:
            log.info(f"[{metric}] batch {current}..{batch_end}: sin datos")
            current = batch_end + timedelta(days=1)
            time.sleep(0.3)
            continue

        filas = []
        for _, row in df.iterrows():
            codigo = row.get("Code")
            valor = row.get("Value")
            fecha_raw = row.get("Date")
            if codigo is None or str(codigo).strip().upper() in ("", "NULL", "NONE", "RECURSO"):
                continue
            if valor is None:
                continue
            fecha_str = str(fecha_raw)[:10]
            filas.append((fecha_str, metric, entity, str(codigo), float(valor) / divisor, unidad))

        if filas:
            n = db_manager.upsert_metrics_bulk(filas)
            total_general += n
            log.info(f"[{metric}] batch {current}..{batch_end}: {len(filas)} filas → {n} guardadas/actualizadas")
        current = batch_end + timedelta(days=1)
        time.sleep(0.3)

    log.info(f"[{metric}] TOTAL insertado/actualizado: {total_general} filas")
    return total_general


def backfill_cap_efec_neta(obj_api, fecha_inicio: date, fecha_fin: date, batch_size_dias: int = 30):
    """CapEfecNeta: valor crudo en kW, sin convertir (ver docstring general)."""
    return backfill_metrica_id_code_value(
        obj_api, "CapEfecNeta", "Recurso", fecha_inicio, fecha_fin,
        unidad="MW", divisor=1.0, batch_size_dias=batch_size_dias,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--solo-metrica",
        choices=["DemaReal", "DispoDeclarada", "CapEfecNeta", "ENFICC", "ObligEnerFirme"],
        default=None,
    )
    args = parser.parse_args()

    from pydataxm.pydataxm import ReadDB
    obj_api = ReadDB()

    resumen = {}

    if args.solo_metrica in (None, "DemaReal"):
        # Hueco real: 2000-01-01 .. 2020-02-05 (2020-02-06 ya existe en BD)
        log.info("=== Backfill DemaReal/Sistema 2000-01-01 .. 2020-02-05 ===")
        resumen["DemaReal/Sistema"] = backfill_via_poblar_metrica(
            obj_api, "DemaReal", "Sistema", FECHA_INICIO_XM, date(2020, 2, 5), batch_size=180
        )

    if args.solo_metrica in (None, "DispoDeclarada"):
        # Hueco real: 2000-01-01 .. 2019-12-31 (2020-01-01 ya existe en BD)
        log.info("=== Backfill DispoDeclarada/Recurso 2000-01-01 .. 2019-12-31 ===")
        resumen["DispoDeclarada/Recurso"] = backfill_via_poblar_metrica(
            obj_api, "DispoDeclarada", "Recurso", FECHA_INICIO_XM, date(2019, 12, 31), batch_size=7
        )

    if args.solo_metrica in (None, "CapEfecNeta"):
        # Rango completo (no solo el hueco) — corrige también las filas de
        # 2021 con el bug de unidad y el vacío 2021-2026 (ver docstring).
        log.info("=== Backfill/Corrección CapEfecNeta/Recurso 2000-01-01 .. hoy ===")
        resumen["CapEfecNeta/Recurso"] = backfill_cap_efec_neta(
            obj_api, FECHA_INICIO_XM, date.today()
        )

    if args.solo_metrica in (None, "ENFICC"):
        # ENFICC (Energía Firme Cargo por Confiabilidad) — el indicador de
        # ADECUACIÓN DE OFERTA oficial diseñado por la CREG (Res. 071/2006),
        # no un cálculo propio como el margen operativo de DispoDeclarada.
        # Rango completo: también corrige los ceros esporádicos vistos en
        # la carga reciente (2026) de este script.
        log.info("=== Backfill ENFICC/Recurso 2007-01-01 .. hoy ===")
        resumen["ENFICC/Recurso"] = backfill_metrica_id_code_value(
            obj_api, "ENFICC", "Recurso", FECHA_INICIO_ENFICC, date.today(),
            unidad="GWh", divisor=1_000_000.0, batch_size_dias=30,
        )

    if args.solo_metrica in (None, "ObligEnerFirme"):
        # OEF — la contraparte de demanda proyectada del mecanismo oficial.
        log.info("=== Backfill ObligEnerFirme/Recurso 2007-01-01 .. hoy ===")
        resumen["ObligEnerFirme/Recurso"] = backfill_metrica_id_code_value(
            obj_api, "ObligEnerFirme", "Recurso", FECHA_INICIO_ENFICC, date.today(),
            unidad="GWh", divisor=1_000_000.0, batch_size_dias=30,
        )

    log.info("=== RESUMEN FINAL ===")
    for k, v in resumen.items():
        log.info(f"  {k}: {v} filas")


if __name__ == "__main__":
    main()

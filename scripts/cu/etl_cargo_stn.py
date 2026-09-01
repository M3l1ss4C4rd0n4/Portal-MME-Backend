"""
Fase 40 (Costo Unitario) — ETL del componente T (transmisión STN) en vivo.

Fuente: CargoUsoSTN de XM (pydataxm), publicado MENSUAL, valor NACIONAL
único — coincide con lo que exige el Art. 4 de la Resolución CREG 119 de
2007 (mod. Res. CREG 101-28/2023): T varía solo por mes, no por
comercializador/mercado.

CargoUsoSTN viene en COP TOTALES del mes (no COP/kWh) — se convierte
dividiendo entre la demanda comercial nacional (DemaCome, entidad=Sistema)
sumada en kWh para el mismo mes:

    T_cop_kwh = CargoUsoSTN_cop_mes / DemaCome_kwh_mes

Uso:
    python3 scripts/cu/etl_cargo_stn.py [--dias 400]
"""
import argparse
import logging
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

from infrastructure.database.connection import PostgreSQLConnectionManager  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("etl_cargo_stn")


def _mes_inicio(d: date) -> date:
    return d.replace(day=1)


def main(dias: int = 400) -> None:
    from pydataxm.pydataxm import ReadDB

    api = ReadDB()
    fin = date.today()
    inicio = fin - timedelta(days=dias)

    logger.info(f"Descargando CargoUsoSTN {inicio} → {fin}")
    df_cargo = api.request_data(
        "CargoUsoSTN", "Sistema",
        start_date=inicio.strftime("%Y-%m-%d"),
        end_date=fin.strftime("%Y-%m-%d"),
    )
    if df_cargo is None or df_cargo.empty:
        logger.error("Sin datos de CargoUsoSTN en el rango solicitado — abortando")
        return

    logger.info(f"Descargando DemaCome (Sistema) {inicio} → {fin} (para ponderar por mes)")
    df_dema = api.request_data(
        "DemaCome", "Sistema",
        start_date=inicio.strftime("%Y-%m-%d"),
        end_date=fin.strftime("%Y-%m-%d"),
    )
    if df_dema is None or df_dema.empty:
        logger.error("Sin datos de DemaCome en el rango solicitado — abortando")
        return

    hour_cols = [c for c in df_dema.columns if c.startswith("Values_Hour")]
    df_dema["kwh_dia"] = df_dema[hour_cols].sum(axis=1)
    df_dema["mes"] = df_dema["Date"].apply(lambda d: _mes_inicio(d.date() if hasattr(d, "date") else d))
    dema_por_mes = df_dema.groupby("mes")["kwh_dia"].sum()

    df_cargo["mes"] = df_cargo["Date"].apply(lambda d: _mes_inicio(d.date() if hasattr(d, "date") else d))

    filas = []
    for _, row in df_cargo.iterrows():
        mes = row["mes"]
        cargo_total = float(row["Value"])
        dema_kwh = dema_por_mes.get(mes)
        if dema_kwh is None or dema_kwh <= 0:
            logger.warning(f"Mes {mes}: sin DemaCome real para ponderar — se omite")
            continue
        t_cop_kwh = float(cargo_total / dema_kwh)
        filas.append((mes, cargo_total, float(dema_kwh), t_cop_kwh))
        logger.info(f"{mes}: CargoUsoSTN={cargo_total:,.0f} COP  DemaCome={dema_kwh:,.0f} kWh  T={t_cop_kwh:.4f} COP/kWh")

    if not filas:
        logger.error("Ningún mes con datos completos (CargoUsoSTN + DemaCome) — nada que guardar")
        return

    mgr = PostgreSQLConnectionManager()
    upsert_sql = """
        INSERT INTO cargo_stn_mensual (mes, cargo_stn_cop_total, demacome_kwh_mes, cargo_stn_cop_kwh)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (mes) DO UPDATE SET
            cargo_stn_cop_total = EXCLUDED.cargo_stn_cop_total,
            demacome_kwh_mes    = EXCLUDED.demacome_kwh_mes,
            cargo_stn_cop_kwh   = EXCLUDED.cargo_stn_cop_kwh,
            actualizado_en      = now()
    """
    with mgr.get_connection() as conn:
        with conn.cursor() as cur:
            for fila in filas:
                cur.execute(upsert_sql, fila)
        conn.commit()

    logger.info(f"Guardados/actualizados {len(filas)} meses en cargo_stn_mensual")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=400)
    args = parser.parse_args()
    main(dias=args.dias)

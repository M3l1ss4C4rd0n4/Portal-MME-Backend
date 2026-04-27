#!/usr/bin/env python3
"""
Recalcula PrecBolsNaci usando PPP (Precio Promedio Ponderado por generación)
en vez de promedio aritmético simple.

Fórmula XM oficial: PPP = Σ(Precio_h × Gene_h) / Σ(Gene_h)
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime, timedelta
from pydataxm.pydataxm import ReadDB
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

def calcular_ppp(fecha_str: str, api: ReadDB) -> float | None:
    """Calcula PPP para una fecha descargando PrecBolsNaci y Gene horarios."""
    fecha = pd.Timestamp(fecha_str)
    try:
        df_prec = api.request_data('PrecBolsNaci', 'Sistema', fecha, fecha)
        df_gene = api.request_data('Gene', 'Sistema', fecha, fecha)
        
        hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
        prec_cols = [c for c in hour_cols if c in df_prec.columns]
        gene_cols = [c for c in hour_cols if c in df_gene.columns]
        
        if not prec_cols or not gene_cols:
            logger.warning(f"  Sin datos horarios para {fecha_str}")
            return None
        
        prec_vals = df_prec[prec_cols].iloc[0].values
        gene_vals = df_gene[gene_cols].iloc[0].values
        
        # PPP ponderado por generación
        numerador = sum(p * g for p, g in zip(prec_vals, gene_vals))
        denominador = sum(gene_vals)
        
        if denominador == 0:
            return None
        
        ppp = float(numerador / denominador)  # Convertir a float nativo de Python
        return round(ppp, 6)
        
    except Exception as e:
        logger.error(f"  Error calculando PPP para {fecha_str}: {e}")
        return None


def main():
    repo = MetricsRepository()
    api = ReadDB()
    
    logger.info("=== Recalculando PPP PrecBolsNaci (últimos 90 días) ===")
    
    q = """
        SELECT DISTINCT fecha::date as fecha
        FROM metrics
        WHERE metrica = 'PrecBolsNaci' AND entidad = 'Sistema' AND recurso = 'Sistema'
          AND fecha::date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY fecha DESC
    """
    df_fechas = repo.execute_dataframe(q)
    fechas = [str(f) for f in df_fechas['fecha'].tolist()]
    
    logger.info(f"Fechas a recalcular: {len(fechas)}")
    
    actualizados = 0
    errores = 0
    
    for fecha_str in fechas:
        ppp = calcular_ppp(fecha_str, api)
        if ppp is None:
            errores += 1
            continue
        
        q_update = """
            UPDATE metrics
            SET valor_gwh = %s
            WHERE metrica = 'PrecBolsNaci'
              AND entidad = 'Sistema'
              AND recurso = 'Sistema'
              AND fecha::date = %s
        """
        try:
            n = repo.execute_non_query(q_update, (ppp, fecha_str))
            if n > 0:
                actualizados += 1
                logger.info(f"  ✅ {fecha_str}: PPP = {ppp:.4f}")
            else:
                logger.warning(f"  ⚠️ {fecha_str}: No se actualizó ningún registro")
        except Exception as e:
            logger.error(f"  ❌ {fecha_str}: Error actualizando BD: {e}")
            errores += 1
    
    logger.info(f"\n=== Resumen ===")
    logger.info(f"Actualizados: {actualizados}")
    logger.info(f"Errores: {errores}")


if __name__ == "__main__":
    main()

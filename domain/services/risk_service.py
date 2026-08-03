"""
Servicio de riesgo de atraso — Fase 4 (analítica predictiva expandida, Palantir-IA).

Score de riesgo de atraso por contrato OR, basado en contratos_or.cronograma_obra
(cronograma físico de obra: ítems con fecha_final y estado aprobado/valido).

Mismo enfoque que domain/services/losses_nt_service.py::detect_anomalies_isolation_forest
(Isolation Forest, sklearn, contamination fija, severidad por percentiles del score)
cuando hay suficientes contratos para que el modelo sea estadísticamente significativo.
Con menos datos (hoy: 9 contratos con cronograma cargado), usa un ranking determinístico
transparente en vez de forzar ML sobre una muestra demasiado pequeña — el mismo umbral
mínimo (12 filas) que ya usa losses_nt_service para bloquear Isolation Forest con pocos
datos.

100% analítico/informativo — no cambia el estado de ningún contrato ni escribe en
contratos_or.*.
"""

import logging
from typing import Any, Dict, List

import pandas as pd

from infrastructure.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)

MIN_GRUPOS_PARA_ISOLATION_FOREST = 12


class RiskService(BaseRepository):
    """
    Riesgo de atraso de contratos OR — capa de solo lectura sobre contratos_or.*.

    Usa BaseRepository.execute_query() (cursor con dict, vía PostgreSQLConnectionManager)
    en vez de db_manager.query_df() — este último ejecuta pd.read_sql_query() sobre una
    conexión psycopg2 cruda, un camino que pandas marca explícitamente como "no
    testeado" para DBAPI2 genérico y que se comprobó no es fiable bajo llamadas
    concurrentes vía asyncio.to_thread() (la fila de encabezados de columna aparecía
    como si fuera una fila de datos). execute_query() no tiene ese problema.
    """

    def _get_features_cronograma_obra(self) -> pd.DataFrame:
        query = """
            SELECT ejecutor, contrato, municipio,
                   count(*) AS n_items,
                   count(*) FILTER (WHERE fecha_final < now()) AS items_vencidos,
                   count(*) FILTER (
                       WHERE fecha_final < now() AND (aprobado IS NULL OR aprobado = 0)
                   ) AS items_vencidos_sin_aprobar,
                   COALESCE(
                       avg(EXTRACT(DAY FROM now() - fecha_final))
                           FILTER (WHERE fecha_final < now() AND (aprobado IS NULL OR aprobado = 0)),
                       0
                   ) AS dias_promedio_retraso
            FROM contratos_or.cronograma_obra
            WHERE contrato IS NOT NULL AND fecha_final IS NOT NULL
            GROUP BY ejecutor, contrato, municipio
        """
        rows = self.execute_query(query)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # psycopg2 puede devolver columnas numéricas como Decimal — coerción explícita
        # evita depender de que pandas infiera el dtype correcto a partir de dicts.
        columnas_numericas = ["n_items", "items_vencidos", "items_vencidos_sin_aprobar", "dias_promedio_retraso"]
        for col in columnas_numericas:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df["pct_vencidos_sin_aprobar"] = (
            df["items_vencidos_sin_aprobar"] / df["n_items"].replace(0, 1)
        )
        return df

    def riesgo_atraso_contratos_or(self) -> List[Dict[str, Any]]:
        """
        Ranking de contratos OR por riesgo de atraso, mayor riesgo primero.
        Cada fila incluye 'metodo' (isolation_forest | ranking_determinista) para que
        el consumidor sepa qué tan robusto es el score.
        """
        df = self._get_features_cronograma_obra()
        if df.empty:
            return []

        if len(df) >= MIN_GRUPOS_PARA_ISOLATION_FOREST:
            df = self._score_isolation_forest(df)
        else:
            logger.info(
                f"[RISK] Solo {len(df)} contratos con cronograma de obra cargado — "
                f"usando ranking determinístico en vez de Isolation Forest "
                f"(mínimo {MIN_GRUPOS_PARA_ISOLATION_FOREST} para que el modelo sea "
                "estadísticamente significativo)"
            )
            df = self._score_determinista(df)

        df = df.sort_values("riesgo_score", ascending=False)
        return df.round(3).to_dict(orient="records")

    def _score_determinista(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["riesgo_score"] = df["pct_vencidos_sin_aprobar"]
        df["metodo"] = "ranking_determinista"
        df["severidad"] = df["pct_vencidos_sin_aprobar"].apply(
            lambda p: "CRITICO" if p >= 0.66 else ("ALERTA" if p >= 0.33 else "NORMAL")
        )
        return df

    def _score_isolation_forest(self, df: pd.DataFrame) -> pd.DataFrame:
        from sklearn.ensemble import IsolationForest

        df = df.copy()
        features = ["pct_vencidos_sin_aprobar", "dias_promedio_retraso", "n_items"]
        X = df[features].values

        iso = IsolationForest(contamination=0.15, random_state=42, n_estimators=100)
        df["anomaly"] = iso.fit_predict(X)
        # score_samples: más negativo = más anómalo. Invertido para que
        # riesgo_score más alto = más riesgo (más intuitivo para el consumidor).
        df["riesgo_score"] = -iso.score_samples(X)
        df["metodo"] = "isolation_forest"

        threshold_critico = float(df["riesgo_score"].quantile(0.85))
        threshold_alerta = float(df["riesgo_score"].quantile(0.70))

        def _severidad(row):
            if row["anomaly"] == 1:
                return "NORMAL"
            return "CRITICO" if row["riesgo_score"] >= threshold_critico else "ALERTA"

        df["severidad"] = df.apply(_severidad, axis=1)
        return df

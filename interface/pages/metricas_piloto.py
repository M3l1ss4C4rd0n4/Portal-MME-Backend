"""
Página piloto de métricas usando nueva arquitectura
Capa Interface (Antes Presentation)
"""

from dash import html, dcc, Input, Output, callback, register_page
import dash_bootstrap_components as dbc
from datetime import datetime

from domain.services.metrics_service import MetricsService
from domain.services.predictions_service import PredictionsService
from infrastructure.logging.logger import get_logger

register_page(
    __name__,
    path="/metricas-piloto",
    name="Métricas (Piloto)",
    title="Métricas Piloto",
    description="Página piloto con nueva arquitectura",
)

logger = get_logger(__name__)

# Instancia de servicios (podría inyectarse)
metrics_service = MetricsService()
predictions_service = PredictionsService()

def _get_summary():
    """Obtiene resumen desde servicios de dominio"""
    try:
        latest_metrics_date = metrics_service.get_latest_date()
        total_metrics = metrics_service.get_total_records()
        predictions_count = predictions_service.count_predictions()
        latest_prediction_date = predictions_service.get_latest_prediction_date()
        
        return {
            "latest_metrics_date": latest_metrics_date,
            "total_metrics": total_metrics,
            "predictions_count": predictions_count,
            "latest_prediction_date": latest_prediction_date,
        }
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        return {
            "latest_metrics_date": "Error",
            "total_metrics": 0,
            "predictions_count": 0,
            "latest_prediction_date": "Error",
        }

layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(
                    html.H3("📊 Métricas - Piloto (Nueva Arquitectura)", className="mb-2"),
                    width=12,
                ),
                dbc.Col(
                    html.P(
                        "Esta página usa domain/services + infrastructure/repos.",
                        className="text-muted",
                    ),
                    width=12,
                ),
            ],
            className="mt-3",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Button("Actualizar", id="btn-refresh-metricas-piloto", color="primary"),
                    width="auto",
                ),
                dbc.Col(
                    html.Span(id="last-refresh-metricas-piloto", className="text-muted"),
                    width="auto",
                ),
            ],
            className="mb-3",
        ),
        dbc.Row(
            [
                dbc.Col(dbc.Card([dbc.CardHeader("Total registros"), dbc.CardBody(html.H4(id="total-metrics"))])),
                dbc.Col(dbc.Card([dbc.CardHeader("Última fecha métricas"), dbc.CardBody(html.H4(id="latest-metrics-date"))])),
                dbc.Col(dbc.Card([dbc.CardHeader("Total predicciones"), dbc.CardBody(html.H4(id="total-predictions"))])),
                dbc.Col(dbc.Card([dbc.CardHeader("Última fecha predicción"), dbc.CardBody(html.H4(id="latest-prediction-date"))])),
            ],
            className="g-3",
        ),
        dcc.Interval(id="interval-metricas-piloto", interval=300000, n_intervals=0),
    ],
    fluid=True,
)

@callback(
    Output("total-metrics", "children"),
    Output("latest-metrics-date", "children"),
    Output("total-predictions", "children"),
    Output("latest-prediction-date", "children"),
    Output("last-refresh-metricas-piloto", "children"),
    Input("btn-refresh-metricas-piloto", "n_clicks"),
    Input("interval-metricas-piloto", "n_intervals"),
)
def update_summary(n_clicks, n_intervals):
    try:
        summary = _get_summary()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"{summary['total_metrics']}",
            str(summary["latest_metrics_date"] or "N/D"),
            f"{summary['predictions_count']}",
            str(summary["latest_prediction_date"] or "N/D"),
            f"Última actualización: {timestamp}",
        )
    except Exception as e:
        logger.error(f"Error in callback: {e}")
        return "0", "N/D", "0", "N/D", "Error"

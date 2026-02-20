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
from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import crear_page_header, crear_filter_bar

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

layout = html.Div(className="t-page", children=[
    crear_page_header(
        "Métricas (Piloto)",
        "fas fa-flask",
        "Inicio / Métricas Piloto"
    ),
    crear_filter_bar(
        dbc.Button("Actualizar", id="btn-refresh-metricas-piloto", color="primary", size="sm"),
        html.Span(id="last-refresh-metricas-piloto", className="text-muted", style={"fontSize": "0.8rem"}),
    ),
    html.Div(id="kpis-metricas-piloto", className="mt-3"),
    dcc.Interval(id="interval-metricas-piloto", interval=300000, n_intervals=0),
])

@callback(
    Output("kpis-metricas-piloto", "children"),
    Output("last-refresh-metricas-piloto", "children"),
    Input("btn-refresh-metricas-piloto", "n_clicks"),
    Input("interval-metricas-piloto", "n_intervals"),
)
def update_summary(n_clicks, n_intervals):
    try:
        summary = _get_summary()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        kpis = crear_kpi_row([
            {"titulo": "Total registros", "valor": str(summary['total_metrics']), "icono": "fas fa-database", "color": "blue"},
            {"titulo": "Última fecha métricas", "valor": str(summary['latest_metrics_date'] or 'N/D'), "icono": "fas fa-calendar", "color": "green"},
            {"titulo": "Total predicciones", "valor": str(summary['predictions_count']), "icono": "fas fa-brain", "color": "purple"},
            {"titulo": "Última fecha predicción", "valor": str(summary['latest_prediction_date'] or 'N/D'), "icono": "fas fa-clock", "color": "orange"},
        ])
        return kpis, f"Última actualización: {timestamp}"
    except Exception as e:
        logger.error(f"Error in callback: {e}")
        error_kpis = crear_kpi_row([
            {"titulo": "Total registros", "valor": "0", "icono": "fas fa-database", "color": "blue"},
            {"titulo": "Última fecha métricas", "valor": "N/D", "icono": "fas fa-calendar", "color": "green"},
            {"titulo": "Total predicciones", "valor": "0", "icono": "fas fa-brain", "color": "purple"},
            {"titulo": "Última fecha predicción", "valor": "N/D", "icono": "fas fa-clock", "color": "orange"},
        ])
        return error_kpis, "Error"

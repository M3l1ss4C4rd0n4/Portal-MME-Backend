"""
Página /inversiones — Propuestas de Inversión en Energías Renovables.
OE7 MVP: Tabla LCOE comparativa + calculadora de impacto en CU.

Fuentes: IRENA 2023 · UPME Plan Expansión 2023-2037 · XM Colombia 2024
"""
import dash
from dash import html, dcc, dash_table, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from domain.services.investment_service import InvestmentService

dash.register_page(
    __name__,
    path="/inversiones",
    title="Propuestas de Inversión | ENERTRACE",
)

_svc = InvestmentService()

# ══════════════════════════════════════════════════════════════
# DATOS PARA TABLA
# ══════════════════════════════════════════════════════════════

_BENCHMARKS = _svc.get_benchmarks()
_TABLE_COLS = [
    {"name": "Tecnología", "id": "tecnologia"},
    {"name": "LCOE Colombia", "id": "lcoe_colombia"},
    {"name": "China", "id": "lcoe_china"},
    {"name": "Alemania", "id": "lcoe_alemania"},
    {"name": "España", "id": "lcoe_espana"},
    {"name": "Factor Cap. Colombia", "id": "factor_cap_colombia"},
    {"name": "Meta UPME 2027", "id": "meta_upme_2027_mw"},
]

_STYLE_DATA_CONDITIONAL = [
    # Verde suave donde Colombia es competitivo (tecnología solar/eólica)
    {
        "if": {
            "filter_query": "{_competitivo} = true",
            "column_id": "lcoe_colombia",
        },
        "backgroundColor": "#d4edda",
        "color": "#155724",
        "fontWeight": "600",
    },
]

# ══════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════

layout = html.Div([

    # ── Header ───────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.H3(
                "💡 Propuestas de Inversión en Energías Renovables",
                className="fw-bold mb-1",
            ),
            html.P(
                "Benchmarks internacionales y estimación de impacto tarifario",
                className="text-muted mb-0",
            ),
            html.Small(
                "Fuentes: IRENA 2023 · UPME Plan Expansión 2023-2037 · XM Colombia 2024",
                className="text-secondary",
            ),
        ]),
    ], className="mb-4"),

    # ── Tabla LCOE ───────────────────────────────────────────
    dbc.Card([
        dbc.CardHeader(
            html.H5("📊 Comparativo LCOE Internacional", className="mb-0 fw-bold")
        ),
        dbc.CardBody([
            html.P(
                "Costo Nivelado de Energía (LCOE) en USD/MWh. "
                "Resaltado verde = Colombia es competitivo respecto a economías desarrolladas.",
                className="text-muted small mb-3",
            ),
            dash_table.DataTable(
                id="tabla-lcoe",
                columns=_TABLE_COLS,
                data=_BENCHMARKS,
                style_table={"overflowX": "auto"},
                style_header={
                    "backgroundColor": "#264653",
                    "color": "white",
                    "fontWeight": "bold",
                    "textAlign": "center",
                    "fontSize": "0.85rem",
                },
                style_cell={
                    "textAlign": "center",
                    "padding": "8px 12px",
                    "fontSize": "0.88rem",
                    "fontFamily": "system-ui, sans-serif",
                },
                style_cell_conditional=[
                    {"if": {"column_id": "tecnologia"}, "textAlign": "left", "fontWeight": "600"},
                ],
                style_data_conditional=_STYLE_DATA_CONDITIONAL,
                style_data={"border": "1px solid #dee2e6"},
                hidden_columns=["_competitivo"],
                page_action="none",
            ),
        ]),
    ], className="shadow-sm mb-4"),

    # ── Calculadora de impacto ────────────────────────────────
    dbc.Card([
        dbc.CardHeader(
            html.H5("🧮 Calculadora de Impacto en CU", className="mb-0 fw-bold")
        ),
        dbc.CardBody([
            html.P(
                "Estimación de la reducción tarifaria dado un incremento de capacidad renovable.",
                className="text-muted small mb-3",
            ),
            dbc.Row([
                # Sliders
                dbc.Col([
                    html.Label("☀️ MW Solares a instalar", className="fw-semibold"),
                    dcc.Slider(
                        id="inv-mw-solar",
                        min=0, max=3000, step=100, value=500,
                        marks={0: "0", 500: "500", 1000: "1.000",
                               2000: "2.000", 3000: "3.000 MW"},
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),
                    html.Div(className="mb-4"),
                    html.Label("💨 MW Eólicos a instalar", className="fw-semibold"),
                    dcc.Slider(
                        id="inv-mw-eolica",
                        min=0, max=5000, step=100, value=1000,
                        marks={0: "0", 1000: "1.000", 2000: "2.000",
                               3000: "3.000", 5000: "5.000 MW"},
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),
                ], md=7),

                # Resultado
                dbc.Col([
                    html.Div(id="inv-resultado"),
                ], md=5),
            ]),
        ]),
    ], className="shadow-sm mb-4"),

    # ── Nota metodológica ────────────────────────────────────
    dbc.Card([
        dbc.CardBody(
            html.P([
                html.Strong("Nota metodológica: "),
                "Los cálculos son estimaciones basadas en factores de capacidad "
                "típicos para Colombia (IDEAM/UPME) y datos de generación del SIN "
                "(XM 2024). Factor de desplazamiento térmico conservador: 0.6 "
                "(no toda la generación renovable adicional desplaza generación "
                "térmica en el despacho). ",
                html.Br(),
                html.Strong("Fuentes: "),
                "IRENA Renewable Power Generation Costs 2023, "
                "UPME Plan de Expansión 2023-2037, XM Colombia — Informe SIN 2024.",
            ], className="text-muted small mb-0"),
        ),
    ], className="shadow-sm border-secondary"),

], className="container-fluid px-4 py-3")


# ══════════════════════════════════════════════════════════════
# CALLBACK — Calculadora de impacto
# ══════════════════════════════════════════════════════════════

@callback(
    Output("inv-resultado", "children"),
    Input("inv-mw-solar", "value"),
    Input("inv-mw-eolica", "value"),
)
def calcular_impacto(mw_solar, mw_eolica):
    mw_solar = mw_solar or 0
    mw_eolica = mw_eolica or 0

    result = _svc.calculate_cu_impact(
        mw_solar=float(mw_solar),
        mw_eolica=float(mw_eolica),
    )

    reduccion = result["reduccion_cu_pct"]
    ahorro = result["ahorro_estimado_cop_kwh"]
    gen = result["generacion_adicional_gwh"]
    mw_total = result["mw_total"]

    color = "success" if reduccion > 0 else "secondary"

    return dbc.Card([
        dbc.CardBody([
            html.H6("Resultado estimado", className="text-muted mb-3"),
            dbc.Row([
                dbc.Col([
                    html.P("Capacidad total", className="text-muted small mb-1"),
                    html.H4(f"{mw_total:,.0f} MW", className="fw-bold text-primary mb-0"),
                ], className="text-center"),
                dbc.Col([
                    html.P("Generación adicional", className="text-muted small mb-1"),
                    html.H4(f"{gen:,.1f} GWh/año", className="fw-bold text-info mb-0"),
                ], className="text-center"),
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    html.P("Reducción CU estimada", className="text-muted small mb-1"),
                    html.H3(
                        f"{reduccion:.2f}%",
                        className=f"fw-bold text-{color} mb-0",
                    ),
                ], className="text-center"),
                dbc.Col([
                    html.P("Ahorro estimado", className="text-muted small mb-1"),
                    html.H3(
                        f"{ahorro:.1f} COP/kWh",
                        className=f"fw-bold text-{color} mb-0",
                    ),
                ], className="text-center"),
            ], className="mb-3"),
            html.Hr(),
            html.P(
                f"Instalar {mw_solar:,.0f} MW solares + {mw_eolica:,.0f} MW eólicos "
                f"generaría {gen:,.1f} GWh/año adicionales, "
                f"reduciendo el CU estimado en {reduccion:.2f}% "
                f"(≈ {ahorro:.1f} COP/kWh de ahorro al usuario final).",
                className="text-muted small fst-italic mb-0",
            ),
        ]),
    ], color=color, outline=True)

"""
Página /inversiones — Propuestas de Inversión en Energías Renovables.
OE7 MVP: Tabla LCOE comparativa + calculadora de impacto en CU.

Fuentes: IRENA 2023 · UPME Plan Expansión 2023-2037 · XM Colombia 2024
"""
import dash
from dash import html, dcc, dash_table, callback, Input, Output, State
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

    # ── Análisis Financiero ───────────────────────────────────
    dbc.Card([
        dbc.CardHeader(
            html.H5("📈 Análisis Financiero del Proyecto", className="mb-0 fw-bold")
        ),
        dbc.CardBody([
            html.P(
                "TIR, VAN, Payback, CO₂ evitado y empleos generados por tecnología.",
                className="text-muted small mb-3",
            ),
            dbc.Row([
                dbc.Col([
                    html.Label("Tecnología", className="fw-semibold"),
                    dcc.Dropdown(
                        id="inv-tecnologia",
                        options=[
                            {"label": "☀️ Solar FV", "value": "solar_fv"},
                            {"label": "💨 Eólica", "value": "eolica"},
                            {"label": "💧 Hidro Pequeña", "value": "hidro_pequena"},
                        ],
                        value="solar_fv",
                        clearable=False,
                    ),
                ], md=4),
                dbc.Col([
                    html.Label("Capacidad a instalar (MW)", className="fw-semibold"),
                    dcc.Slider(
                        id="inv-mw",
                        min=10, max=1000, step=10, value=100,
                        marks={10: "10", 100: "100 MW", 500: "500 MW", 1000: "1 GW"},
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),
                ], md=6),
                dbc.Col([
                    html.Label("\u00a0", className="d-block"),
                    dbc.Button(
                        "Calcular TIR y retorno",
                        id="btn-calcular-tir",
                        color="primary",
                        size="sm",
                        className="mt-2",
                    ),
                ], md=2),
            ], className="mb-3"),
            html.Div(id="inv-financial-kpis"),
            html.Div(id="inv-cashflow-summary"),
            html.Hr(),
            dbc.Button(
                "📄 Descargar propuesta PDF",
                id="btn-download-inv-pdf",
                color="outline-secondary",
                size="sm",
                className="mt-1",
            ),
            dcc.Download(id="inv-pdf-download"),
        ]),
    ], className="shadow-sm mt-4 mb-4"),

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
    cu_ref = result.get("cu_referencia_cop_kwh", 250.0)
    gen_sin = result.get("gen_total_sin_gwh", 80_000)

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
                className="text-muted small fst-italic mb-1",
            ),
            html.Small(
                f"📊 Calculado con datos reales: CU={cu_ref:.1f} COP/kWh (BD, 30d) · "
                f"SIN={gen_sin:,.0f} GWh/año (BD, 365d)",
                className="text-secondary",
                style={"fontSize": "0.75rem"},
            ),
        ]),
    ], color=color, outline=True)


# ══════════════════════════════════════════════════════════════
# CALLBACK — Análisis Financiero (TIR, VAN, CO2, Empleos)
# ══════════════════════════════════════════════════════════════

@callback(
    Output("inv-financial-kpis", "children"),
    Output("inv-cashflow-summary", "children"),
    Input("btn-calcular-tir", "n_clicks"),
    State("inv-tecnologia", "value"),
    State("inv-mw", "value"),
    prevent_initial_call=True,
)
def calcular_tir(n_clicks, tecnologia, mw):
    if not n_clicks:
        return "", ""
    mw = float(mw or 100)
    r = _svc.calculate_financial_analysis(tecnologia, mw)

    van_m = r["van_usd"] / 1_000_000
    capex_m = r["capex_total_usd"] / 1_000_000
    ingresos_m = r["ingresos_anuales_usd"] / 1_000_000

    color_van = "success" if r["van_usd"] > 0 else "danger"
    color_tir = "success" if r["tir_pct"] > 8 else ("warning" if r["tir_pct"] > 0 else "danger")

    kpis = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("💰 CAPEX Total", className="text-muted small mb-1"),
            html.H5(f"USD {capex_m:,.1f} M", className="fw-bold mb-0"),
            html.Small(f"COP {r['capex_total_cop']/1e9:,.1f} B", className="text-muted"),
        ])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("📈 TIR", className="text-muted small mb-1"),
            html.H5(f"{r['tir_pct']}%", className=f"fw-bold text-{color_tir} mb-0"),
            html.Small(f"WACC ref: {r['tasa_descuento_pct']}%", className="text-muted"),
        ])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("⏱️ Payback", className="text-muted small mb-1"),
            html.H5(f"{r['payback_años']} años", className="fw-bold mb-0"),
            html.Small(f"Vida útil: {r['vida_util_años']} años", className="text-muted"),
        ])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("🌱 CO₂ evitado/año", className="text-muted small mb-1"),
            html.H5(f"{r['co2_evitado_ton_anual']:,.0f} tCO₂", className="fw-bold text-success mb-0"),
            html.Small(f"Total vida útil: {r['co2_evitado_total']/1e6:,.2f} M ton", className="text-muted"),
        ])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("👥 Empleos", className="text-muted small mb-1"),
            html.H5(f"{r['empleos_directos']} directos", className="fw-bold mb-0"),
            html.Small(f"+ {r['empleos_indirectos']} indirectos = {r['empleos_total']} total", className="text-muted"),
        ])), md=2),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("💵 VAN", className="text-muted small mb-1"),
            html.H5(f"USD {van_m:,.1f} M", className=f"fw-bold text-{color_van} mb-0"),
            html.Small(f"Ingresos: USD {ingresos_m:,.1f} M/año", className="text-muted"),
        ])), md=2),
    ], className="g-2 mt-2")

    nombre_tec = {"solar_fv": "Solar FV", "eolica": "Eólica", "hidro_pequena": "Hidro Pequeña"}
    resumen = html.P(
        f"Proyecto {nombre_tec.get(tecnologia, tecnologia)} de {mw:.0f} MW: "
        f"CAPEX USD {capex_m:,.1f} M · TIR {r['tir_pct']}% · Payback {r['payback_años']} años · "
        f"VAN USD {van_m:,.1f} M · CO₂ evitado {r['co2_evitado_ton_anual']:,.0f} tCO₂/año · "
        f"{r['empleos_total']} empleos generados.",
        className="text-muted small fst-italic mt-3 mb-0",
    )

    return kpis, resumen


# ══════════════════════════════════════════════════════════════
# CALLBACK — Descarga PDF propuesta
# ══════════════════════════════════════════════════════════════

@callback(
    Output("inv-pdf-download", "data"),
    Input("btn-download-inv-pdf", "n_clicks"),
    State("inv-tecnologia", "value"),
    State("inv-mw", "value"),
    prevent_initial_call=True,
)
def download_inv_pdf(n_clicks, tecnologia, mw):
    if not n_clicks:
        return dash.no_update
    import weasyprint as _wp
    mw = float(mw or 100)
    r = _svc.calculate_financial_analysis(tecnologia, mw)
    nombre_tec = {"solar_fv": "Solar FV", "eolica": "Eólica", "hidro_pequena": "Hidro Pequeña"}
    html_content = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<style>
body{{font-family:Arial,sans-serif;margin:40px;color:#1a1a1a}}
h1{{color:#264653}}h2{{color:#2a9d8f;margin-top:24px}}
table{{border-collapse:collapse;width:100%}}
th{{background:#264653;color:white;padding:8px 12px;text-align:left}}
td{{border:1px solid #dee2e6;padding:8px 12px}}
.footer{{font-size:11px;color:#888;margin-top:40px;border-top:1px solid #dee2e6;padding-top:8px}}
</style></head><body>
<h1>ENERTRACE — Propuesta de Inversión</h1>
<h2>Proyecto: {mw:.0f} MW {nombre_tec.get(tecnologia, tecnologia)}</h2>
<table>
<tr><th>Indicador</th><th>Valor</th></tr>
<tr><td>CAPEX Total</td><td>USD {r['capex_total_usd']:,.0f} ({r['capex_total_cop']/1e9:,.1f} B COP)</td></tr>
<tr><td>OPEX Anual</td><td>USD {r['opex_anual_usd']:,.0f}</td></tr>
<tr><td>Generación Anual</td><td>{r['generacion_anual_mwh']:,.0f} MWh/año</td></tr>
<tr><td>Ingresos Anuales</td><td>USD {r['ingresos_anuales_usd']:,.0f}</td></tr>
<tr><td>TIR</td><td><strong>{r['tir_pct']}%</strong></td></tr>
<tr><td>VAN (WACC {r['tasa_descuento_pct']}%)</td><td>USD {r['van_usd']:,.0f}</td></tr>
<tr><td>Payback Simple</td><td>{r['payback_años']} años</td></tr>
<tr><td>CO₂ Evitado / Año</td><td>{r['co2_evitado_ton_anual']:,.0f} tCO₂</td></tr>
<tr><td>CO₂ Evitado Vida Útil</td><td>{r['co2_evitado_total']:,.0f} tCO₂</td></tr>
<tr><td>Empleos Directos</td><td>{r['empleos_directos']:,}</td></tr>
<tr><td>Empleos Indirectos</td><td>{r['empleos_indirectos']:,}</td></tr>
<tr><td>Empleos Total</td><td>{r['empleos_total']:,}</td></tr>
</table>
<div class="footer">
Fuentes: IRENA 2023, UPME 2024, IDEAM 2023 (factor CO2: 0.126 tCO2/MWh),
XM Colombia. TRM referencia: 4,200 COP/USD. Generado por ENERTRACE v1.2.0.
</div>
</body></html>"""
    pdf = _wp.HTML(string=html_content).write_pdf()
    return dcc.send_bytes(pdf, f"ENERTRACE_propuesta_{tecnologia}_{mw:.0f}MW.pdf")
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

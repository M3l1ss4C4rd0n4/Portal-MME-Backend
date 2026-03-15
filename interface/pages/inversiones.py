"""
Página /inversiones — Propuestas de Inversión en Energías Renovables.
OE7 MVP: Tabla LCOE comparativa + calculadora de impacto en CU.

Fuentes: IRENA 2023 · UPME Plan Expansión 2023-2037 · XM Colombia 2024
"""
import dash
from dash import html, dcc, dash_table, callback, Input, Output, State
import dash_bootstrap_components as dbc

from domain.services.investment_service import InvestmentService
from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import crear_chart_card_custom, crear_page_header

dash.register_page(
    __name__,
    path="/inversiones",
    title="Propuestas de Inversión | ENERTRACE",
)

_svc = InvestmentService()

# Paleta de colores página
INV_COLORS = {
    'solar': '#F5A623',
    'eolica': '#2A9D8F',
    'hidro': '#457B9D',
    'positivo': '#2A9D8F',
    'negativo': '#E63946',
    'acento': '#264653',
}

# ══════════════════════════════════════════════════════════════
# DATOS PARA TABLA
# ══════════════════════════════════════════════════════════════

_BENCHMARKS = _svc.get_benchmarks()
# TRM leído desde config (sobreescribible vía env var TRM_REF_COP_USD)
try:
    from core.config import settings as _inv_settings
    _trm: float = _inv_settings.TRM_REF_COP_USD
except Exception:
    _trm = 4_200.0
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

    crear_page_header(
        titulo="Propuestas de Inversión en Renovables",
        breadcrumb="Inicio / Inversiones",
        icono="fas fa-lightbulb",
    ),

    dbc.Row([
        # ── COLUMNA IZQ — Panel de control ──────────────────
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H6(
                    "⚙️ Parámetros de Inversión",
                    className='mb-0 fw-bold',
                )),
                dbc.CardBody([
                    dbc.Alert([
                        html.Strong("Referencias: "),
                        "IRENA 2023 · UPME 2023-2037 · XM 2024",
                        html.Br(),
                        html.Small(
                            "Cap. SIN: ~20 GW instalados | FCP solar Caribe: 24%",
                            className='text-muted',
                        ),
                    ], color='light', className='py-2 mb-3',
                       style={'borderLeft': f'4px solid {INV_COLORS["solar"]}'}),

                    # ─ Sección: Impacto CU ─────────────────
                    html.H6([
                        html.I(className='fas fa-solar-panel me-2',
                               style={'color': INV_COLORS['solar']}),
                        "Calculadora de Impacto CU",
                    ], className='fw-semibold mb-3',
                       style={'borderBottom': '2px solid #f0f0f0',
                              'paddingBottom': '8px'}),

                    html.Label("☀️ MW Solares a instalar",
                               className='fw-semibold small'),
                    dcc.Slider(
                        id="inv-mw-solar",
                        min=0, max=3000, step=100, value=500,
                        marks={0: "0", 500: "500", 1000: "1.000",
                               2000: "2.000", 3000: "3.000 MW"},
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),

                    html.Label("💨 MW Eólicos a instalar",
                               className='fw-semibold small mt-4 d-block'),
                    dcc.Slider(
                        id="inv-mw-eolica",
                        min=0, max=5000, step=100, value=1000,
                        marks={0: "0", 1000: "1.000", 2000: "2.000",
                               3000: "3.000", 5000: "5.000 MW"},
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),

                    html.Hr(className='my-4'),

                    # ─ Sección: Análisis Financiero ─────────
                    html.H6([
                        html.I(className='fas fa-chart-line me-2',
                               style={'color': INV_COLORS['eolica']}),
                        "Análisis Financiero",
                    ], className='fw-semibold mb-3',
                       style={'borderBottom': '2px solid #f0f0f0',
                              'paddingBottom': '8px'}),

                    html.Label("Tecnología",
                               className='text-muted small fw-semibold'),
                    dcc.Dropdown(
                        id="inv-tecnologia",
                        options=[
                            {"label": "☀️ Solar FV", "value": "solar_fv"},
                            {"label": "💨 Eólica", "value": "eolica"},
                            {"label": "💧 Hidro Pequeña", "value": "hidro_pequena"},
                        ],
                        value="solar_fv",
                        clearable=False,
                        className='mb-3',
                    ),

                    html.Label("Capacidad a instalar (MW)",
                               className='text-muted small fw-semibold'),
                    dcc.Slider(
                        id="inv-mw",
                        min=10, max=1000, step=10, value=100,
                        marks={10: "10", 100: "100 MW",
                               500: "500 MW", 1000: "1 GW"},
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),

                    dbc.Button(
                        [html.I(className='fas fa-calculator me-2'),
                         "Calcular TIR y retorno"],
                        id="btn-calcular-tir",
                        color="primary",
                        className="w-100 mt-4",
                    ),

                    html.Hr(className='my-3'),

                    dbc.Button(
                        [html.I(className='fas fa-file-pdf me-2'),
                         "Descargar propuesta PDF"],
                        id="btn-download-inv-pdf",
                        color="outline-secondary",
                        size="sm",
                        className="w-100",
                    ),
                    dcc.Download(id="inv-pdf-download"),
                ]),
            ], className='shadow-sm', style={'position': 'sticky', 'top': '60px'}),
        ], md=4),

        # ── COLUMNA DER — Resultados ─────────────────────────
        dbc.Col([
            # KPIs de impacto CU (se actualiza automáticamente con los sliders)
            dcc.Loading(html.Div(id="inv-resultado"), type="circle"),

            # Tabla LCOE comparativa
            crear_chart_card_custom(
                titulo="Comparativo LCOE Internacional",
                subtitulo="Costo Nivelado en USD/MWh — verde = Colombia es competitivo",
                children=dash_table.DataTable(
                    id="tabla-lcoe",
                    columns=_TABLE_COLS,  # type: ignore[arg-type]
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
                        "fontFamily": "Inter, system-ui, sans-serif",
                    },
                    style_cell_conditional=[  # type: ignore[arg-type]
                        {"if": {"column_id": "tecnologia"},
                         "textAlign": "left", "fontWeight": "600"},
                    ],
                    style_data_conditional=_STYLE_DATA_CONDITIONAL,  # type: ignore[arg-type]
                    style_data={"border": "1px solid #dee2e6"},
                    hidden_columns=["_competitivo"],
                    page_action="none",
                ),
            ),

            # Resultados análisis financiero (se llena al hacer clic)
            dcc.Loading(html.Div(id="inv-financial-kpis"), type="circle"),
            dcc.Loading(html.Div(id="inv-cashflow-summary"), type="circle"),

        ], md=8),

    ], className='g-3 mt-0'),

    html.Small(
        [html.I(className='fas fa-info-circle me-1 text-muted'),
         "Estimaciones basadas en factores de capacidad típicos Colombia (IDEAM/UPME), "
         f"factor desplazamiento térmico: 0.6. TRM ref.: {_trm:,.0f} COP/USD. "
         "No representa datos reales ni proyecciones oficiales del MME."],
        className='text-muted fst-italic d-block mt-3 mb-4',
    ),

    # ══════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════
    # SECCIÓN: LCOE Eólico Offshore — La Guajira (Fases 5)
    # ══════════════════════════════════════════════════════════
    html.Hr(className='my-4'),
    dbc.Card([
        dbc.CardHeader([
            html.I(className='fas fa-wind me-2', style={'color': '#2A9D8F'}),
            html.Strong("LCOE Eólico Offshore — Parque La Guajira"),
            dbc.Badge("Weibull ERA5 k=2.2 c=9.5 m/s", color="info", pill=True,
                      className="ms-2", style={'fontSize': '0.75rem'}),
        ], style={'backgroundColor': '#f0fafa'}),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Turbina", className="fw-semibold mb-1"),
                    dcc.Dropdown(
                        id='guajira-turbina',
                        options=[
                            {'label': 'Goldwind GW155-4.0 MW (nearshore)', 'value': 'GOLDWIND_GW155_4MW'},
                            {'label': 'Mingyang MySE 5.5-155 (offshore)', 'value': 'MINGYANG_MYSE_5_5_155'},
                        ],
                        value='GOLDWIND_GW155_4MW',
                        clearable=False,
                    ),
                    html.Div(className='mt-3'),
                    html.Label("Número de aerogeneradores", className="fw-semibold mb-1"),
                    dcc.Slider(
                        id='guajira-n-turbinas',
                        min=10, max=200, step=10, value=100,
                        marks={10: '10', 50: '50', 100: '100', 150: '150', 200: '200'},
                        tooltip={'placement': 'bottom'},
                    ),
                ], md=4),
                dbc.Col([
                    dcc.Loading(
                        html.Div(id='guajira-lcoe-resultado'),
                        type='circle',
                    ),
                ], md=8),
            ]),
            html.Small([
                html.I(className='fas fa-info-circle me-1 text-muted'),
                "CAPEX basado en NREL ATB 2023 + factor Colombia (+15%). "
                "Factor de capacidad: integral Weibull × curva turbina (ERA5 La Guajira). "
                "OPEX incluye mantenimiento marino. Créditos carbono: 15 USD/tCO₂."
            ], className='text-muted fst-italic d-block mt-3'),
        ]),
    ], className='shadow-sm mb-4'),

    # SECCIÓN: Simulación de Expansión — Estabilidad de Red
    # ══════════════════════════════════════════════════════════
    html.Hr(className='my-4'),
    dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.Span([
                    html.I(className='fas fa-wave-square me-2',
                           style={'color': '#2A9D8F'}),
                    html.Strong("Simulación de Estabilidad de Red — Plan Expansión"),
                ]),
                dbc.Badge("En desarrollo", color="warning", pill=True,
                          className="ms-2", style={'fontSize': '0.75rem'}),
            ], className='d-flex align-items-center'),
        ], style={'backgroundColor': '#f8f9fa'}),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.H5("⚡ Kuramoto-SIN: Simulador de Estabilidad",
                            className='fw-bold mb-3'),
                    html.P(
                        "Módulo de simulación basado en el modelo de Kuramoto-Sakaguchi "
                        "para evaluar la estabilidad de frecuencia del SIN Colombia "
                        "ante la penetración de tecnología eólica offshore china "
                        "(Goldwind / Mingyang) en La Guajira.",
                        className='text-muted',
                    ),
                    html.Hr(className='my-3'),
                    html.H6("¿Qué simulará este módulo?",
                            className='fw-semibold mb-2'),
                    html.Ul([
                        html.Li([
                            html.Strong("Inercia equivalente del SIN "),
                            "(H_eq) al incorporar mix eólico offshore con y sin "
                            "inercia virtual síncrona (VSM).",
                        ], className='mb-1'),
                        html.Li([
                            html.Strong("RoCoF y frecuencia nadir "),
                            "tras pérdida de mayor unidad generadora (N-1) "
                            "con distintos niveles de penetración ERNC.",
                        ], className='mb-1'),
                        html.Li([
                            html.Strong("Eigenvalores λ₂ (Laplaciano) "),
                            "del grafo SIN agregado (10-15 nodos por zona geográfica) "
                            "para detectar bifurcaciones de sincronización.",
                        ], className='mb-1'),
                        html.Li([
                            html.Strong("Correlación ENSO → Generación eólica "),
                            "usando índice ONI (NOAA) y datos ERA5 de La Guajira.",
                        ], className='mb-1'),
                    ], style={'fontSize': '0.88rem'}),
                ], md=7),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H6("Parámetros del modelo",
                                    className='fw-semibold mb-3 text-center'),
                            html.Div([
                                html.Div([
                                    html.Span("Tecnología offshore",
                                             className='text-muted small'),
                                    html.Br(),
                                    html.Strong("Goldwind 3 MW / Mingyang 5.5 MW"),
                                ], className='mb-3'),
                                html.Div([
                                    html.Span("Factor de planta estimado",
                                             className='text-muted small'),
                                    html.Br(),
                                    html.Strong("35 – 44 % (La Guajira offshore ERA5)"),
                                ], className='mb-3'),
                                html.Div([
                                    html.Span("Inercia turbinas PMDD",
                                             className='text-muted small'),
                                    html.Br(),
                                    html.Strong("H = 0.5 s (convencional) / 3.0 s (VSM)"),
                                ], className='mb-3'),
                                html.Div([
                                    html.Span("Nodos del grafo SIN",
                                             className='text-muted small'),
                                    html.Br(),
                                    html.Strong("10 – 15 zonas (Caribe, Andina, Pacifico, Orinoquía)"),
                                ], className='mb-3'),
                                html.Div([
                                    html.Span("Benchmark de validación",
                                             className='text-muted small'),
                                    html.Br(),
                                    html.Strong("CU histórico XM (cu_daily) + ONI NOAA"),
                                ], className='mb-3'),
                            ]),
                            html.Hr(className='my-2'),
                            dbc.Alert([
                                html.I(className='fas fa-clock me-2'),
                                "Desarrollo estimado: Q3 2026. "
                                "Requiere datos ERA5 (Copernicus CDS) y "
                                "topología de red (XM/UPME).",
                            ], color='info', className='py-2 mb-0',
                               style={'fontSize': '0.82rem'}),
                        ]),
                    ], className='shadow-sm',
                       style={'borderTop': f'4px solid {INV_COLORS["eolica"]}'}),
                ], md=5),
            ]),
        ]),
    ], className='shadow-sm mb-4'),

], className="container-fluid px-4 py-3")


# ══════════════════════════════════════════════════════════════
# CALLBACK — LCOE Eólico Offshore La Guajira (Fase 5)
# ══════════════════════════════════════════════════════════════

@callback(
    Output("guajira-lcoe-resultado", "children"),
    Input("guajira-turbina", "value"),
    Input("guajira-n-turbinas", "value"),
)
def calcular_lcoe_guajira(turbine_key, n_turbinas):
    n_turbinas = n_turbinas or 100
    turbine_key = turbine_key or "GOLDWIND_GW155_4MW"
    try:
        r = _svc.calculate_lcoe_eolico_guajira(
            turbine_key=turbine_key,
            n_turbinas=int(n_turbinas),
        )
    except Exception as e:
        return dbc.Alert(f"Error calculando LCOE: {e}", color="danger")

    lcoe_b = r.get("lcoe_bruto_usd_mwh", 0)
    lcoe_n = r.get("lcoe_neto_usd_mwh", 0)
    lcoe_cop = r.get("lcoe_neto_cop_kwh", 0)
    cf_pct = r.get("factor_capacidad_pct", 0)
    gen_gwh = r.get("generacion_anual_mwh", 0) / 1_000
    capex_usd = r.get("capex_total_usd", 0)
    co2 = r.get("co2_evitado_ton_anual", 0)
    pot_mw = r.get("potencia_total_mw", 0)
    trm = r.get("trm_usada", 4200)

    return html.Div([
        crear_kpi_row([
            {"titulo": "LCOE Bruto", "valor": f"{lcoe_b:.1f}", "unidad": "USD/MWh",
             "subtitulo": "Sin créditos carbono", "color": "info"},
            {"titulo": "LCOE Neto", "valor": f"{lcoe_n:.1f}", "unidad": "USD/MWh",
             "subtitulo": f"≈ {lcoe_cop:.2f} COP/kWh", "color": "success"},
            {"titulo": "Factor Capacidad", "valor": f"{cf_pct:.1f}", "unidad": "%",
             "subtitulo": "Weibull ERA5 La Guajira", "color": "primary"},
            {"titulo": "Generación Anual", "valor": f"{gen_gwh:.0f}", "unidad": "GWh/año",
             "subtitulo": f"Parque {pot_mw:.0f} MW", "color": "warning"},
        ]),
        dbc.Row([
            dbc.Col([
                html.Small([
                    html.Strong("CAPEX: "),
                    f"USD {capex_usd/1e6:,.0f} M  |  ",
                    html.Strong("CO₂ evitado: "),
                    f"{co2/1e3:,.0f} ktCO₂/año  |  ",
                    html.Strong("TRM ref: "),
                    f"{trm:,.0f} COP/USD",
                ], className="text-muted"),
            ]),
        ], className="mt-2"),
    ])


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

    color_reduccion = "green" if reduccion > 0 else "orange"

    return html.Div([
        crear_kpi_row([
            {
                "titulo": "Capacidad Total",
                "valor": f"{mw_total:,.0f}",
                "unidad": "MW",
                "icono": "fas fa-solar-panel",
                "color": "orange",
            },
            {
                "titulo": "Generación Adicional",
                "valor": f"{gen:,.1f}",
                "unidad": "GWh/año",
                "icono": "fas fa-bolt",
                "color": "blue",
            },
            {
                "titulo": "Reducción CU",
                "valor": f"{reduccion:.2f}",
                "unidad": "%",
                "icono": "fas fa-arrow-down",
                "color": color_reduccion,
            },
            {
                "titulo": "Ahorro Estimado",
                "valor": f"{ahorro:.1f}",
                "unidad": "COP/kWh",
                "icono": "fas fa-piggy-bank",
                "color": color_reduccion,
            },
        ]),
        html.Small(
            f"📊 CU ref={cu_ref:.1f} COP/kWh · SIN={gen_sin:,.0f} GWh/año · "
            f"{mw_solar:,.0f} MW solar + {mw_eolica:,.0f} MW eólico",
            className="text-muted fst-italic d-block mt-1 mb-3",
            style={"fontSize": "0.75rem"},
        ),
    ])


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

    color_van = "green" if r["van_usd"] > 0 else "red"
    color_tir = "green" if r["tir_pct"] > 8 else ("orange" if r["tir_pct"] > 0 else "red")

    nombre_tec = {"solar_fv": "Solar FV", "eolica": "Eólica",
                  "hidro_pequena": "Hidro Pequeña"}

    kpis = crear_chart_card_custom(
        titulo=f"Análisis Financiero — {mw:.0f} MW {nombre_tec.get(tecnologia, tecnologia)}",
        subtitulo="TIR · VAN · Payback · CO₂ evitado · Empleos generados",
        children=crear_kpi_row([
            {
                "titulo": "CAPEX Total",
                "valor": f"USD {capex_m:,.1f} M",
                "unidad": "",
                "icono": "fas fa-coins",
                "color": "blue",
                "subtexto": f"COP {r['capex_total_cop']/1e9:,.1f} B",
            },
            {
                "titulo": "TIR",
                "valor": f"{r['tir_pct']}",
                "unidad": "%",
                "icono": "fas fa-percent",
                "color": color_tir,
                "subtexto": f"WACC ref: {r['tasa_descuento_pct']}%",
            },
            {
                "titulo": "Payback",
                "valor": f"{r['payback_años']}",
                "unidad": "años",
                "icono": "fas fa-hourglass-half",
                "color": "purple",
                "subtexto": f"Vida útil: {r['vida_util_años']} años",
            },
            {
                "titulo": "VAN",
                "valor": f"USD {van_m:,.1f} M",
                "unidad": "",
                "icono": "fas fa-chart-line",
                "color": color_van,
                "subtexto": f"Ingresos: USD {ingresos_m:,.1f} M/año",
            },
            {
                "titulo": "CO₂ Evitado/año",
                "valor": f"{r['co2_evitado_ton_anual']:,.0f}",
                "unidad": "tCO₂",
                "icono": "fas fa-leaf",
                "color": "green",
                "subtexto": f"Total: {r['co2_evitado_total']/1e6:,.2f} M ton",
            },
            {
                "titulo": "Empleos",
                "valor": f"{r['empleos_total']:,}",
                "unidad": "",
                "icono": "fas fa-users",
                "color": "cyan",
                "subtexto": f"{r['empleos_directos']} dir. + {r['empleos_indirectos']} ind.",
            },
        ]),
    )

    resumen = html.P(
        f"Proyecto {nombre_tec.get(tecnologia, tecnologia)} de {mw:.0f} MW: "
        f"CAPEX USD {capex_m:,.1f} M · TIR {r['tir_pct']}% · Payback {r['payback_años']} años · "
        f"VAN USD {van_m:,.1f} M · CO₂ {r['co2_evitado_ton_anual']:,.0f} tCO₂/año · "
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
XM Colombia. TRM referencia: {r.get('trm_ref_cop_usd', _trm):,.0f} COP/USD. Generado por ENERTRACE v1.2.0.
</div>
</body></html>"""
    pdf = _wp.HTML(string=html_content).write_pdf()
    return dcc.send_bytes(pdf, f"ENERTRACE_propuesta_{tecnologia}_{mw:.0f}MW.pdf")

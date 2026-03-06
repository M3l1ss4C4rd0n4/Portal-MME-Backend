"""
Página de Pérdidas No Técnicas (PNT) — Portal Energético MME
Análisis histórico detallado y metodología CREG.

FASE 5 — TAREA 5.3
"""

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
from datetime import date, timedelta
import pandas as pd
import traceback
import logging

from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import (
    crear_chart_card_custom,
    crear_page_header,
    crear_filter_bar,
)
from domain.services.losses_nt_service import LossesNTService

def get_plotly_modules():
    """Importación diferida de Plotly"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

logger = logging.getLogger(__name__)

# Servicio
_losses_service = LossesNTService()

# ── Registrar la página ──────────────────────────────────────
dash.register_page(
    __name__,
    path="/perdidas-nt",
    name="Pérdidas NT",
    title="Pérdidas No Técnicas — Portal Energético MME",
    order=55,
)

# ── Paleta PNT ───────────────────────────────────────────────
PNT_COLORS = {
    "p_tec": "#457B9D",
    "p_nt": "#E63946",
    "p_total": "#2C3E50",
    "umbral_ok": "#28a745",
    "umbral_mod": "#ffc107",
    "umbral_alto": "#dc3545",
}


def _semaforo_pnt(val):
    """Semáforo: <5% verde, 5-10% amarillo, >10% rojo."""
    if val is None:
        return ("⚪", "secondary", "Sin datos")
    if val < 5:
        return ("🟢", "success", "Normal")
    if val < 10:
        return ("🟡", "warning", "Moderado")
    return ("🔴", "danger", "Alto")


# ═══════════════════════════════════════════════════════════════
# LAYOUT
# ═══════════════════════════════════════════════════════════════

def layout(**kwargs):
    hoy = date.today()
    hace_365 = hoy - timedelta(days=365)

    return html.Div([
        crear_page_header(
            titulo="Pérdidas No Técnicas (PNT)",
            icono="fas fa-plug-circle-exclamation",
            breadcrumb="Inicio / Pérdidas / Pérdidas NT",
            fecha=hoy.strftime("%d/%m/%Y"),
        ),

        crear_filter_bar(
            html.Div([
                html.Label("Periodo", className="t-filter-label"),
                dcc.Dropdown(
                    id="dropdown-rango-pnt",
                    options=[
                        {"label": "Últimos 30 días", "value": "30d"},
                        {"label": "Último Trimestre", "value": "90d"},
                        {"label": "Últimos 6 Meses", "value": "180d"},
                        {"label": "Último Año", "value": "365d"},
                        {"label": "Últimos 2 Años", "value": "730d"},
                        {"label": "Toda la serie", "value": "all"},
                        {"label": "Personalizado", "value": "custom"},
                    ],
                    value="365d",
                    clearable=False,
                    style={"width": "180px", "fontSize": "0.85rem"},
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),

            html.Div([
                html.Label("Fechas", className="t-filter-label"),
                dcc.DatePickerRange(
                    id="fecha-filtro-pnt",
                    min_date_allowed=date(2020, 1, 1),
                    max_date_allowed=hoy,
                    initial_visible_month=hoy,
                    start_date=hace_365,
                    end_date=hoy,
                    display_format="YYYY-MM-DD",
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),

            dbc.Button([
                html.I(className="fas fa-search me-1"), "Actualizar"
            ], id="btn-actualizar-pnt", color="primary", size="sm"),
        ),

        # KPIs
        html.Div(id="kpis-pnt"),

        # Tabs
        dcc.Tabs(
            id="pnt-tabs",
            value="tab-historico",
            children=[
                dcc.Tab(
                    label="Análisis Histórico",
                    value="tab-historico",
                    className="custom-tab",
                    selected_className="custom-tab--selected",
                ),
                dcc.Tab(
                    label="Metodología CREG",
                    value="tab-metodologia",
                    className="custom-tab",
                    selected_className="custom-tab--selected",
                ),
            ],
            style={"marginBottom": "16px"},
        ),

        dcc.Loading(
            id="loading-pnt",
            type="dot",
            color=PNT_COLORS["p_nt"],
            children=html.Div(id="pnt-tab-content"),
        ),

        dcc.Store(id="store-pnt", data=None),

    ], className="t-page")


# ═══════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════

# 1) Dropdown → fechas
@callback(
    [Output("fecha-filtro-pnt", "start_date"),
     Output("fecha-filtro-pnt", "end_date")],
    Input("dropdown-rango-pnt", "value"),
    prevent_initial_call=True,
)
def actualizar_fechas_rango_pnt(rango):
    hoy = date.today()
    mapping = {
        "30d": 30, "90d": 90, "180d": 180,
        "365d": 365, "730d": 730, "all": 3650,
    }
    days = mapping.get(rango)
    if days:
        return hoy - timedelta(days=days), hoy
    return dash.no_update, dash.no_update


# 2) Filtros → store + KPIs
@callback(
    [Output("store-pnt", "data"),
     Output("kpis-pnt", "children")],
    [Input("btn-actualizar-pnt", "n_clicks"),
     Input("fecha-filtro-pnt", "start_date"),
     Input("fecha-filtro-pnt", "end_date")],
    prevent_initial_call="initial_duplicate",
)
def actualizar_store_pnt(_n, fecha_inicio_str, fecha_fin_str):
    try:
        if not fecha_inicio_str or not fecha_fin_str:
            return None, html.Div()

        fi = pd.to_datetime(fecha_inicio_str).date()
        ff = pd.to_datetime(fecha_fin_str).date()

        stats = _losses_service.get_losses_statistics()

        if "error" in stats:
            return None, dbc.Alert("Sin datos de PNT.", color="warning")

        pnt_30d = stats.get("pct_promedio_nt_30d", 0) or 0
        pnt_12m = stats.get("pct_promedio_nt_12m", 0) or 0
        tendencia = stats.get("tendencia_nt", "ESTABLE")
        dias_anom = stats.get("anomalias_30d", 0) or 0
        costo_12m = stats.get("costo_nt_12m_mcop", 0) or 0
        total_dias = stats.get("total_dias", 0) or 0

        emoji, _, sem_label = _semaforo_pnt(pnt_30d)

        tend_icon = "fas fa-arrow-down" if tendencia == "MEJORANDO" else (
            "fas fa-arrow-up" if tendencia == "EMPEORANDO" else "fas fa-minus"
        )
        tend_color = "green" if tendencia == "MEJORANDO" else (
            "red" if tendencia == "EMPEORANDO" else "blue"
        )

        kpis = crear_kpi_row([
            {
                "titulo": f"{emoji} PNT (30d)",
                "valor": f"{pnt_30d:.2f}",
                "unidad": "%",
                "icono": "fas fa-chart-line",
                "color": "red" if pnt_30d > 10 else ("orange" if pnt_30d > 5 else "green"),
                "subtexto": f"Semáforo: {sem_label}",
            },
            {
                "titulo": "Tendencia",
                "valor": tendencia,
                "unidad": "",
                "icono": tend_icon,
                "color": tend_color,
                "subtexto": f"PNT 12m: {pnt_12m:.2f}%",
            },
            {
                "titulo": "Costo PNT (12m)",
                "valor": f"{costo_12m:,.0f}",
                "unidad": "MCOP",
                "icono": "fas fa-money-bill-wave",
                "color": "purple",
                "subtexto": f"Hist: {stats.get('costo_nt_historico_mcop', 0) or 0:,.0f} MCOP",
            },
            {
                "titulo": "Anomalías (30d)",
                "valor": str(dias_anom),
                "unidad": "días",
                "icono": "fas fa-exclamation-triangle",
                "color": "orange" if dias_anom > 0 else "green",
                "subtexto": f"Total: {stats.get('dias_anomalia', 0) or 0} / {total_dias}",
            },
        ], columnas=4)

        store = {"fecha_inicio": str(fi), "fecha_fin": str(ff)}
        return store, kpis

    except Exception as e:
        logger.error("Error store PNT: %s", e)
        return None, dbc.Alert(f"Error: {e}", color="danger")


# 3) Store + tab → contenido
@callback(
    Output("pnt-tab-content", "children"),
    [Input("store-pnt", "data"),
     Input("pnt-tabs", "value")],
    prevent_initial_call="initial_duplicate",
)
def renderizar_tab_pnt(store_data, tab_activo):
    px, go = get_plotly_modules()

    # ═══ TAB 2: Metodología (ESTÁTICO) ═══════════════════════
    if tab_activo == "tab-metodologia":
        return _crear_tab_metodologia()

    # ═══ TAB 1: Análisis Histórico ═══════════════════════════
    if not store_data:
        return dbc.Alert("Seleccione un rango y pulse Actualizar.", color="info")

    try:
        fi = pd.to_datetime(store_data["fecha_inicio"]).date()
        ff = pd.to_datetime(store_data["fecha_fin"]).date()

        df = _losses_service.get_losses_historico(fi, ff)
        if df.empty:
            return dbc.Alert("Sin datos de pérdidas para el período.", color="warning")

        df['fecha'] = pd.to_datetime(df['fecha'])
        for c in ['perdidas_total_pct', 'perdidas_tecnicas_pct', 'perdidas_nt_pct',
                   'perdidas_total_gwh', 'perdidas_tecnicas_gwh', 'perdidas_nt_gwh',
                   'costo_nt_mcop']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')

        # ── Gráfico 1: Stacked area (P_tec + P_NT) ──────────
        fig_stack = go.Figure()
        if 'perdidas_tecnicas_pct' in df.columns:
            fig_stack.add_trace(go.Scatter(
                x=df['fecha'], y=df['perdidas_tecnicas_pct'],
                mode='lines', name='P. Técnicas (%)',
                line=dict(color=PNT_COLORS['p_tec'], width=2),
                fill='tozeroy',
                fillcolor=_hex_to_rgba(PNT_COLORS['p_tec'], 0.3),
                stackgroup='one',
            ))
        if 'perdidas_nt_pct' in df.columns:
            fig_stack.add_trace(go.Scatter(
                x=df['fecha'], y=df['perdidas_nt_pct'].clip(lower=0),
                mode='lines', name='P. No Técnicas (%)',
                line=dict(color=PNT_COLORS['p_nt'], width=2),
                fill='tonexty',
                fillcolor=_hex_to_rgba(PNT_COLORS['p_nt'], 0.3),
                stackgroup='one',
            ))
        if 'perdidas_total_pct' in df.columns:
            fig_stack.add_trace(go.Scatter(
                x=df['fecha'], y=df['perdidas_total_pct'],
                mode='lines', name='P. Totales (%)',
                line=dict(color=PNT_COLORS['p_total'], width=1.5, dash='dot'),
            ))

        # Umbral CREG 5% y 10%
        fig_stack.add_hline(y=5, line_dash='dash', line_color=PNT_COLORS['umbral_mod'],
                            annotation_text='5% moderado')
        fig_stack.add_hline(y=10, line_dash='dash', line_color=PNT_COLORS['umbral_alto'],
                            annotation_text='10% alto')

        fig_stack.update_layout(
            height=460,
            hovermode='x unified',
            plot_bgcolor='#FAFAFA',
            paper_bgcolor='white',
            font=dict(family='Inter, sans-serif', size=12),
            margin=dict(l=60, r=20, t=30, b=60),
            xaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='Fecha'),
            yaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='Pérdidas (%)'),
            legend=dict(orientation='h', yanchor='top', y=-0.15, xanchor='center', x=0.5),
        )

        # ── Gráfico 2: PNT % barras semáforo ────────────────
        fig_bars = go.Figure()
        if 'perdidas_nt_pct' in df.columns:
            nt_vals = df['perdidas_nt_pct'].fillna(0)
            bar_colors = [
                PNT_COLORS['umbral_alto'] if v > 10 else (
                    PNT_COLORS['umbral_mod'] if v > 5 else PNT_COLORS['umbral_ok']
                ) for v in nt_vals
            ]
            fig_bars.add_trace(go.Bar(
                x=df['fecha'], y=nt_vals,
                name='PNT (%)',
                marker_color=bar_colors,
                opacity=0.85,
                hovertemplate='%{x|%Y-%m-%d}: %{y:.2f}%<extra></extra>',
            ))
            fig_bars.add_hline(y=0, line_color='gray', line_dash='dash')
            fig_bars.add_hline(y=5, line_dash='dash', line_color=PNT_COLORS['umbral_mod'])
            fig_bars.add_hline(y=10, line_dash='dash', line_color=PNT_COLORS['umbral_alto'])

        fig_bars.update_layout(
            height=350,
            hovermode='x unified',
            plot_bgcolor='#FAFAFA',
            paper_bgcolor='white',
            font=dict(family='Inter, sans-serif', size=12),
            margin=dict(l=60, r=20, t=30, b=60),
            xaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='Fecha'),
            yaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='PNT (%)'),
            showlegend=False,
        )

        # ── Gráfico 3: Costo PNT acumulado ──────────────────
        fig_costo = go.Figure()
        if 'costo_nt_mcop' in df.columns:
            df_costo = df.dropna(subset=['costo_nt_mcop']).copy()
            if not df_costo.empty:
                df_costo['costo_acum'] = df_costo['costo_nt_mcop'].cumsum()
                fig_costo.add_trace(go.Scatter(
                    x=df_costo['fecha'], y=df_costo['costo_acum'],
                    mode='lines',
                    name='Costo acumulado PNT',
                    fill='tozeroy',
                    fillcolor=_hex_to_rgba(PNT_COLORS['p_nt'], 0.15),
                    line=dict(color=PNT_COLORS['p_nt'], width=2),
                    hovertemplate='%{x|%Y-%m-%d}: %{y:,.1f} MCOP<extra></extra>',
                ))

        fig_costo.update_layout(
            height=320,
            hovermode='x unified',
            plot_bgcolor='#FAFAFA',
            paper_bgcolor='white',
            font=dict(family='Inter, sans-serif', size=12),
            margin=dict(l=60, r=20, t=30, b=60),
            xaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='Fecha'),
            yaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='MCOP acumulado'),
            showlegend=False,
        )

        # ── Interpretación ───────────────────────────────────
        stats = _losses_service.get_losses_statistics()
        avg_nt = stats.get('pct_promedio_nt', 0) or 0
        avg_tec = stats.get('pct_promedio_tecnicas', 0) or 0
        avg_total = stats.get('pct_promedio_total', 0) or 0
        pnt_30d = stats.get('pct_promedio_nt_30d', 0) or 0
        emoji, _, sem_label = _semaforo_pnt(pnt_30d)

        interpretacion = dbc.Card([
            dbc.CardHeader([
                html.I(className="fas fa-info-circle me-2"),
                "Interpretación PNT"
            ], style={'fontWeight': '600', 'backgroundColor': '#f8f9fa'}),
            dbc.CardBody([
                html.P([
                    html.Strong("Promedios históricos: "),
                    f"P_total={avg_total:.2f}%, P_tec={avg_tec:.2f}%, ",
                    html.Strong(f"P_NT={avg_nt:.2f}%"),
                ], style={'fontSize': '0.85rem', 'marginBottom': '8px'}),
                html.P([
                    html.Strong("Semáforo CREG: "),
                    html.Span("< 5% Normal ", style={'color': PNT_COLORS['umbral_ok'], 'fontWeight': '600'}),
                    html.Span("| 5-10% Moderado ", style={'color': PNT_COLORS['umbral_mod'], 'fontWeight': '600'}),
                    html.Span("| > 10% Alto", style={'color': PNT_COLORS['umbral_alto'], 'fontWeight': '600'}),
                ], style={'fontSize': '0.85rem'}),
                html.Hr(),
                html.Div([
                    html.Span(f"{emoji} ", style={'fontSize': '1.5rem'}),
                    html.Span(f"Nivel actual: {sem_label} — PNT 30d: {pnt_30d:.2f}%",
                              style={'fontWeight': '600'}),
                ], style={
                    'padding': '10px', 'borderRadius': '8px',
                    'backgroundColor': '#f0f0f0', 'textAlign': 'center',
                }),
            ]),
        ], style={'marginBottom': '16px'})

        # ── Layout final ─────────────────────────────────────
        return html.Div([
            crear_chart_card_custom(
                "Evolución de Pérdidas: Técnicas vs No Técnicas",
                dcc.Graph(figure=fig_stack, config={'displayModeBar': True, 'displaylogo': False}),
                subtitulo=f"{fi} → {ff}",
            ),

            html.Div([
                html.Div([
                    crear_chart_card_custom(
                        "PNT (%) — Semáforo Diario",
                        dcc.Graph(figure=fig_bars, config={'displayModeBar': True, 'displaylogo': False}),
                    ),
                ], style={'flex': '2'}),
                html.Div([
                    interpretacion,
                ], style={'flex': '1'}),
            ], className="t-grid t-grid-2", style={'marginTop': '16px'}),

            crear_chart_card_custom(
                "Costo Acumulado de Pérdidas No Técnicas",
                dcc.Graph(figure=fig_costo, config={'displayModeBar': True, 'displaylogo': False}),
            ),
        ])

    except Exception as e:
        logger.error("Error renderizando tab PNT: %s", e)
        traceback.print_exc()
        return dbc.Alert(f"Error: {e}", color="danger")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convierte #RRGGBB a rgba(r,g,b,a)."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _crear_tab_metodologia():
    """Tab estática — Explicación de la metodología CREG para cálculo de PNT."""
    return html.Div([
        dbc.Card([
            dbc.CardHeader([
                html.I(className="fas fa-book me-2"),
                html.Strong("Metodología de Cálculo de Pérdidas No Técnicas"),
            ], style={'backgroundColor': '#f8f9fa', 'fontWeight': '600'}),
            dbc.CardBody([
                html.H5("Método: RESIDUO_HÍBRIDO_CREG", style={'color': PNT_COLORS['p_nt'], 'marginBottom': '16px'}),

                html.P([
                    "El cálculo de pérdidas no técnicas (PNT) se realiza mediante un ",
                    html.Strong("método híbrido"), " que combina datos medidos del SIN ",
                    "(generación, demanda real en frontera STN/SDL) con parámetros regulatorios ",
                    "de la CREG para estimar las pérdidas por componente.",
                ], style={'fontSize': '0.9rem', 'lineHeight': '1.6', 'marginBottom': '16px'}),

                html.Hr(),

                html.H6("1. Pérdidas Totales (%)", style={'color': '#2C3E50', 'marginBottom': '8px'}),
                html.Div([
                    html.Code(
                        "P_total = (Generación − DemaUsuario_est) / Generación × 100",
                        style={
                            'display': 'block', 'padding': '12px',
                            'backgroundColor': '#f5f5f5',
                            'borderLeft': f'4px solid {PNT_COLORS["p_total"]}',
                            'fontFamily': 'monospace', 'fontSize': '0.9rem',
                            'borderRadius': '4px',
                        }
                    ),
                ], style={'marginBottom': '16px'}),
                html.P([
                    "Donde: ", html.Code("DemaUsuario_est = DemaReal × (1 − SDL_total)"),
                    html.Br(),
                    html.Code("SDL_total"), " = Factor de pérdidas totales del SDL reconocido por CREG ",
                    "(actualmente ", html.Strong("12%"), " según configuración).",
                ], style={'fontSize': '0.85rem', 'color': '#555', 'marginBottom': '16px'}),

                html.Hr(),

                html.H6("2. Pérdidas Técnicas (%)", style={'color': '#2C3E50', 'marginBottom': '8px'}),
                html.Div([
                    html.Code(
                        "P_tec = P_STN_medido + P_SDL_distribución",
                        style={
                            'display': 'block', 'padding': '12px',
                            'backgroundColor': '#f5f5f5',
                            'borderLeft': f'4px solid {PNT_COLORS["p_tec"]}',
                            'fontFamily': 'monospace', 'fontSize': '0.9rem',
                            'borderRadius': '4px',
                        }
                    ),
                ], style={'marginBottom': '16px'}),
                html.P([
                    html.Code("P_STN_medido"), " = Pérdidas del STN (dato observado en metrics: ",
                    html.Code("PerdidasSTN"), ").",
                    html.Br(),
                    html.Code("P_SDL_distribución"), " = Pérdidas técnicas del SDL según CREG ",
                    "(actualmente ", html.Strong("8.5%"), ").",
                ], style={'fontSize': '0.85rem', 'color': '#555', 'marginBottom': '16px'}),

                html.Hr(),

                html.H6("3. Pérdidas No Técnicas — Residuo (%)", style={'color': PNT_COLORS['p_nt'], 'marginBottom': '8px'}),
                html.Div([
                    html.Code(
                        "P_NT = P_total − P_tec",
                        style={
                            'display': 'block', 'padding': '12px',
                            'backgroundColor': '#fff5f5',
                            'borderLeft': f'4px solid {PNT_COLORS["p_nt"]}',
                            'fontFamily': 'monospace', 'fontSize': '1rem',
                            'fontWeight': 'bold',
                            'borderRadius': '4px',
                        }
                    ),
                ], style={'marginBottom': '16px'}),
                html.P([
                    "Las PNT son el residuo entre las pérdidas totales estimadas y las ",
                    "pérdidas técnicas (STN medido + SDL regulatorio). Un valor positivo indica ",
                    "que existe energía no contabilizada (fraude, conexiones ilegales, errores de medición).",
                ], style={'fontSize': '0.85rem', 'color': '#555', 'marginBottom': '16px'}),

                html.Hr(),

                html.H6("4. Clasificación por Semáforo", style={'color': '#2C3E50', 'marginBottom': '12px'}),
                html.Div([
                    html.Div([
                        html.Span("🟢", style={'fontSize': '1.3rem', 'marginRight': '8px'}),
                        html.Strong("PNT < 5%: "),
                        html.Span("Normal — dentro de márgenes esperados."),
                    ], style={'marginBottom': '8px'}),
                    html.Div([
                        html.Span("🟡", style={'fontSize': '1.3rem', 'marginRight': '8px'}),
                        html.Strong("5% ≤ PNT < 10%: "),
                        html.Span("Moderado — requiere monitoreo."),
                    ], style={'marginBottom': '8px'}),
                    html.Div([
                        html.Span("🔴", style={'fontSize': '1.3rem', 'marginRight': '8px'}),
                        html.Strong("PNT ≥ 10%: "),
                        html.Span("Alto — se recomienda investigación."),
                    ]),
                ], style={
                    'padding': '16px', 'backgroundColor': '#f8f9fa',
                    'borderRadius': '8px', 'marginBottom': '16px',
                }),

                html.Hr(),

                html.H6("5. Detección de Anomalías", style={'color': '#2C3E50', 'marginBottom': '8px'}),
                html.P([
                    "Un día se marca como ", html.Strong("anomalía"), " cuando el PNT cae fuera del ",
                    "rango intercuartílico (IQR ×1.5) de la serie histórica, o cuando es negativo ",
                    "(indicando posible error en los datos fuente).",
                ], style={'fontSize': '0.85rem', 'color': '#555', 'marginBottom': '16px'}),

                html.Hr(),

                html.H6("6. Fuentes de Datos", style={'color': '#2C3E50', 'marginBottom': '12px'}),
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("Variable", style={'padding': '8px', 'borderBottom': '2px solid #dee2e6'}),
                        html.Th("Fuente", style={'padding': '8px', 'borderBottom': '2px solid #dee2e6'}),
                        html.Th("Tabla", style={'padding': '8px', 'borderBottom': '2px solid #dee2e6'}),
                    ])),
                    html.Tbody([
                        html.Tr([html.Td("Generación"), html.Td("XM — API SIMEM"), html.Td("metrics (Gene_*)")]),
                        html.Tr([html.Td("Demanda Real"), html.Td("XM — API SIMEM"), html.Td("metrics (DemaReal)")]),
                        html.Tr([html.Td("Pérdidas STN"), html.Td("XM — API SIMEM"), html.Td("metrics (PerdidasSTN)")]),
                        html.Tr([html.Td("SDL total"), html.Td("CREG / config"), html.Td("core/config.py")]),
                        html.Tr([html.Td("SDL distribución"), html.Td("CREG / config"), html.Td("core/config.py")]),
                        html.Tr([html.Td("Precio Bolsa"), html.Td("XM — API SIMEM"), html.Td("metrics (PrecBolsNaci)")]),
                    ]),
                ], style={
                    'width': '100%', 'borderCollapse': 'collapse',
                    'fontSize': '0.85rem', 'marginBottom': '16px',
                }),

                html.Hr(),

                # ══════════════════════════════════════════════
                # SECCIÓN 7 — LIMITACIONES METODOLÓGICAS
                # ══════════════════════════════════════════════
                html.H6("7. Limitaciones Metodológicas", style={
                    'color': PNT_COLORS['p_nt'], 'marginBottom': '12px', 'marginTop': '8px',
                }),
                html.P([
                    html.I(className="fas fa-exclamation-triangle me-2", style={'color': '#F59E0B'}),
                    html.Strong("El Ministerio debe conocer estas limitaciones antes de usar estos datos "
                                "en decisiones regulatorias."),
                ], style={'fontSize': '0.9rem', 'marginBottom': '16px', 'color': '#856404',
                           'backgroundColor': '#fff3cd', 'padding': '12px', 'borderRadius': '6px'}),

                # Limitación 1 — Factor regulatorio vs medido
                html.Div([
                    html.Strong("Limitación 1 — El 8.5% de distribución es regulatorio, no medido",
                                style={'color': '#2C3E50'}),
                    html.P([
                        "El ", html.Code("factor_perdidas_distribucion = 8.5%"),
                        " es lo que la CREG ", html.Strong("reconoce"), " para efectos tarifarios, ",
                        "no la medición física real del SDL. Las pérdidas reales de distribución pueden ",
                        "ser 9–11% en zonas rurales y 7–9% en zonas urbanas.",
                    ], style={'fontSize': '0.85rem', 'color': '#555', 'marginTop': '4px'}),
                    html.Div([
                        html.Code(
                            "Impacto: Si pérdidas reales SDL = 9.5%  →  P_NT = P_total − (1.7% + 9.5%) "
                            "podría ser negativo → anomalía falsa.",
                            style={'display': 'block', 'padding': '10px', 'backgroundColor': '#fff5f5',
                                   'borderLeft': '4px solid #E63946', 'fontFamily': 'monospace',
                                   'fontSize': '0.82rem', 'borderRadius': '4px'}
                        ),
                    ]),
                ], style={'marginBottom': '16px', 'padding': '12px', 'backgroundColor': '#f8f9fa',
                           'borderRadius': '6px', 'borderLeft': '4px solid #F59E0B'}),

                # Limitación 2 — DemaReal solo mide en STN
                html.Div([
                    html.Strong("Limitación 2 — DemaReal solo mide en subestaciones del STN",
                                style={'color': '#2C3E50'}),
                    html.P([
                        html.Code("DemaReal"), " de XM mide la demanda en frontera STN/SDL ",
                        "(sistema de transmisión nacional). ", html.Strong("No incluye"),
                        " la energía que entra al SDL y se pierde antes de llegar al usuario final.",
                    ], style={'fontSize': '0.85rem', 'color': '#555', 'marginTop': '4px'}),
                    html.P([
                        html.Em("Consecuencia: "),
                        "parte de las pérdidas técnicas reales en redes de distribución ",
                        "aparecen clasificadas como P_NT en el cálculo residual.",
                    ], style={'fontSize': '0.85rem', 'color': '#555'}),
                ], style={'marginBottom': '16px', 'padding': '12px', 'backgroundColor': '#f8f9fa',
                           'borderRadius': '6px', 'borderLeft': '4px solid #F59E0B'}),

                # Limitación 3 — Diferencia registros disponibles
                html.Div([
                    html.Strong("Limitación 3 — Diferencia en registros disponibles",
                                style={'color': '#2C3E50'}),
                    html.P([
                        "En la base de datos: ", html.Code("Gene"), " tiene ~534,554 registros mientras que ",
                        html.Code("DemaReal"), " tiene ~186,419 registros (3× menos). ",
                        "Los días sin DemaReal se llenan por interpolación, lo que introduce ",
                        "ruido en el cálculo residual de P_NT.",
                    ], style={'fontSize': '0.85rem', 'color': '#555', 'marginTop': '4px'}),
                ], style={'marginBottom': '16px', 'padding': '12px', 'backgroundColor': '#f8f9fa',
                           'borderRadius': '6px', 'borderLeft': '4px solid #F59E0B'}),

                # Limitación 4 — CREG en revisión
                html.Div([
                    html.Strong("Limitación 4 — La CREG está revisando estos factores",
                                style={'color': '#2C3E50'}),
                    html.P([
                        html.Em('"La Comisión se encuentra analizando el reconocimiento tanto de pérdidas '
                                'técnicas como no técnicas de acuerdo con criterios de eficiencia"'),
                        " — CREG Concepto 2921/2025.",
                    ], style={'fontSize': '0.85rem', 'color': '#555', 'marginTop': '4px'}),
                    html.P([
                        "Cuando la CREG actualice los factores regulatorios, los parámetros ",
                        html.Code("factor_perdidas_distribucion"), " y ", html.Code("factor_sdl_total"),
                        " deben actualizarse en ", html.Code("core/config.py"), ".",
                    ], style={'fontSize': '0.85rem', 'color': '#555'}),
                ], style={'marginBottom': '16px', 'padding': '12px', 'backgroundColor': '#f8f9fa',
                           'borderRadius': '6px', 'borderLeft': '4px solid #F59E0B'}),

                html.Hr(),

                # ══════════════════════════════════════════════
                # SECCIÓN 8 — INTERPRETACIÓN Y VALIDACIÓN
                # ══════════════════════════════════════════════
                html.H6("8. Interpretación y Validación", style={
                    'color': '#2C3E50', 'marginBottom': '12px',
                }),
                html.Div([
                    html.Div([
                        html.Span("✅", style={'fontSize': '1.2rem', 'marginRight': '8px'}),
                        html.Span("Este es un "),
                        html.Strong("estimado por método residuo"),
                        html.Span(" — el único viable con datos públicos de XM. "),
                        html.Strong("No es una medición directa."),
                    ], style={'marginBottom': '10px'}),
                    html.Div([
                        html.Span("✅", style={'fontSize': '1.2rem', 'marginRight': '8px'}),
                        html.Span("El resultado P_NT ≈ 2–4% es el "),
                        html.Strong("promedio nacional del SIN"),
                        html.Span(" — no aplica a nivel de empresa distribuidora individual."),
                    ], style={'marginBottom': '10px'}),
                    html.Div([
                        html.Span("✅", style={'fontSize': '1.2rem', 'marginRight': '8px'}),
                        html.Span("Rango esperado sector colombiano: P_total 10–13%, P_NT 2–8% "),
                        html.Span("(sistemas urbanos bien gestionados)."),
                    ], style={'marginBottom': '10px'}),
                    html.Div([
                        html.Span("✅", style={'fontSize': '1.2rem', 'marginRight': '8px'}),
                        html.Strong("Validación recomendada: "),
                        html.Span("Comparar con Sinergox XM → 'Demanda Comercial, Real y Pérdidas'. "
                                  "Si coincide dentro de ±1%, la metodología está validada para uso en "
                                  "decisiones de política."),
                    ]),
                ], style={
                    'padding': '16px', 'backgroundColor': '#f0fdf4',
                    'borderRadius': '8px', 'borderLeft': '4px solid #10B981',
                    'fontSize': '0.88rem', 'lineHeight': '1.6', 'marginBottom': '16px',
                }),

                html.Hr(),

                # ══════════════════════════════════════════════
                # SECCIÓN 9 — REFERENCIAS OFICIALES
                # ══════════════════════════════════════════════
                html.H6("9. Referencias Oficiales", style={
                    'color': '#2C3E50', 'marginBottom': '12px',
                }),
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("Dato", style={'padding': '8px', 'borderBottom': '2px solid #dee2e6'}),
                        html.Th("Fuente oficial", style={'padding': '8px', 'borderBottom': '2px solid #dee2e6'}),
                        html.Th("Enlace", style={'padding': '8px', 'borderBottom': '2px solid #dee2e6'}),
                    ])),
                    html.Tbody([
                        html.Tr([
                            html.Td("Gene, DemaReal"),
                            html.Td("XM Sinergox — Demanda Real y Pérdidas"),
                            html.Td(html.A("sinergox.xm.com.co",
                                           href="https://sinergox.xm.com.co/dmnd/Paginas/Informes/DemandaRealPerdidas.aspx",
                                           target="_blank", style={'color': '#1E3A8A'})),
                        ]),
                        html.Tr([
                            html.Td("P_STN ≈ 1.7%"),
                            html.Td("XM — Índices de pérdidas STN"),
                            html.Td(html.A("xm.com.co",
                                           href="https://www.xm.com.co/noticias/6730-actualizacion-indices-de-perdidas-y-factores-para-referir-al-stn-abril-2024",
                                           target="_blank", style={'color': '#1E3A8A'})),
                        ]),
                        html.Tr([
                            html.Td("Factor 8.5% SDL"),
                            html.Td("CREG — Metodología tarifaria vigente"),
                            html.Td(html.A("Concepto 2921/2025",
                                           href="https://gestornormativo.creg.gov.co/gestor/entorno/docs/concepto_creg_0002921_2025.htm",
                                           target="_blank", style={'color': '#1E3A8A'})),
                        ]),
                        html.Tr([
                            html.Td("PNT 2–8% Colombia"),
                            html.Td("Análisis pérdidas no técnicas — IberoReport"),
                            html.Td(html.A("investigaciones.ibero.edu.co",
                                           href="https://investigaciones.ibero.edu.co/wp-content/uploads/2024/11/iberoreport-54.pdf",
                                           target="_blank", style={'color': '#1E3A8A'})),
                        ]),
                        html.Tr([
                            html.Td("P. Ley pérdidas"),
                            html.Td("Cámara de Representantes — PL.403/2024C"),
                            html.Td(html.A("camara.gov.co",
                                           href="https://www.camara.gov.co/sites/default/files/2024-03/PL.403-2024C%20(P%C3%89RDIDAS%20DE%20ENERG%C3%8DA%20EL%C3%89CTRICA).pdf",
                                           target="_blank", style={'color': '#1E3A8A'})),
                        ]),
                    ]),
                ], style={
                    'width': '100%', 'borderCollapse': 'collapse',
                    'fontSize': '0.82rem', 'marginBottom': '16px',
                }),

                html.Hr(),
                html.P([
                    html.Em("Implementado en HOTFIX 4.0 — FASE 4/5 del Portal Energético MME. "),
                    "Metodología: RESIDUO_HÍBRIDO_CREG. ",
                    "Ref: CREG 015/2018, Res. CREG 119/2007, Concepto CREG 2921/2025.",
                ], style={'fontSize': '0.8rem', 'color': '#999'}),
            ]),
        ]),

        # Enlace de retorno
        html.Div([
            dbc.Button([
                html.I(className="fas fa-arrow-left me-2"),
                "Volver a Pérdidas"
            ], href="/perdidas", color="light", className="mt-3",
            style={'border': '2px solid #dee2e6', 'fontWeight': '500'}),
        ]),
    ])

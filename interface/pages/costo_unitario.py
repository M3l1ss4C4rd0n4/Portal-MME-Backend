"""
Página de Costo Unitario (CU) — Portal Energético MME
Evolución histórica, desglose por componentes y pronóstico a 30 días.

FASE 5 — TAREA 5.2
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
from domain.services.cu_service import CUService

def get_plotly_modules():
    """Importación diferida de Plotly"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

logger = logging.getLogger(__name__)

# Instanciar servicio (singleton en la práctica)
_cu_service = CUService()

# ── Registrar la página ──────────────────────────────────────
dash.register_page(
    __name__,
    path="/costo-unitario",
    name="Costo Unitario",
    title="Costo Unitario — Portal Energético MME",
    order=25,
)

# ── Paleta de colores CU ────────────────────────────────────
CU_COLORS = {
    "cu_total": "#E63946",
    "comp_G": "#F5A623",
    "comp_T": "#457B9D",
    "comp_D": "#2A9D8F",
    "comp_C": "#E9C46A",
    "comp_P": "#A8DADC",
    "comp_R": "#6C757D",
    "forecast_band": "rgba(230,57,70,0.15)",
    "forecast_line": "#E63946",
}

COMP_LABELS = {
    "componente_g": "Generación (G)",
    "componente_t": "Transmisión (T)",
    "componente_d": "Distribución (D)",
    "componente_c": "Comercialización (C)",
    "componente_p": "Pérdidas (P)",
    "componente_r": "Restricciones (R)",
}

COMP_COLORS = {
    "componente_g": CU_COLORS["comp_G"],
    "componente_t": CU_COLORS["comp_T"],
    "componente_d": CU_COLORS["comp_D"],
    "componente_c": CU_COLORS["comp_C"],
    "componente_p": CU_COLORS["comp_P"],
    "componente_r": CU_COLORS["comp_R"],
}


# ═══════════════════════════════════════════════════════════════
# LAYOUT
# ═══════════════════════════════════════════════════════════════

def layout(**kwargs):
    hoy = date.today()
    hace_180 = hoy - timedelta(days=180)

    return html.Div([
        # ── Page header ──────────────────────
        crear_page_header(
            titulo="Costo Unitario (CU)",
            icono="fas fa-file-invoice-dollar",
            breadcrumb="Inicio / Costo Unitario",
            fecha=hoy.strftime("%d/%m/%Y"),
        ),

        # ── Filter bar ───────────────────────
        crear_filter_bar(
            html.Div([
                html.Label("Periodo", className="t-filter-label"),
                dcc.Dropdown(
                    id="dropdown-rango-cu",
                    options=[
                        {"label": "Últimos 30 días", "value": "30d"},
                        {"label": "Último Trimestre", "value": "90d"},
                        {"label": "Últimos 6 Meses", "value": "180d"},
                        {"label": "Último Año", "value": "365d"},
                        {"label": "Últimos 2 Años", "value": "730d"},
                        {"label": "Últimos 5 Años", "value": "1825d"},
                        {"label": "Personalizado", "value": "custom"},
                    ],
                    value="180d",
                    clearable=False,
                    style={"width": "180px", "fontSize": "0.85rem"},
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),

            html.Div([
                html.Label("Fechas", className="t-filter-label"),
                dcc.DatePickerRange(
                    id="fecha-filtro-cu",
                    min_date_allowed=date(2020, 1, 1),
                    max_date_allowed=hoy,
                    initial_visible_month=hoy,
                    start_date=hace_180,
                    end_date=hoy,
                    display_format="YYYY-MM-DD",
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),

            dbc.Button([
                html.I(className="fas fa-search me-1"), "Actualizar"
            ], id="btn-actualizar-cu", color="primary", size="sm"),
        ),

        # ── KPIs (callback-updated) ─────────
        html.Div(id="kpis-cu"),

        # ── Tabs ─────────────────────────────
        dcc.Tabs(
            id="cu-tabs",
            value="tab-evolucion",
            children=[
                dcc.Tab(
                    label="Evolución Histórica",
                    value="tab-evolucion",
                    className="custom-tab",
                    selected_className="custom-tab--selected",
                ),
                dcc.Tab(
                    label="Desglose Componentes",
                    value="tab-desglose",
                    className="custom-tab",
                    selected_className="custom-tab--selected",
                ),
                dcc.Tab(
                    label="Pronóstico 30 días",
                    value="tab-forecast",
                    className="custom-tab",
                    selected_className="custom-tab--selected",
                ),
            ],
            style={"marginBottom": "16px"},
        ),

        # ── Tab content ──────────────────────
        dcc.Loading(
            id="loading-cu",
            type="dot",
            color=CU_COLORS["cu_total"],
            children=html.Div(id="cu-tab-content"),
        ),

        # ── Store ────────────────────────────
        dcc.Store(id="store-cu", data=None),

    ], className="t-page")


# ═══════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════

# 1) Dropdown rango → fechas
@callback(
    [Output("fecha-filtro-cu", "start_date"),
     Output("fecha-filtro-cu", "end_date")],
    Input("dropdown-rango-cu", "value"),
    prevent_initial_call=True,
)
def actualizar_fechas_rango_cu(rango):
    hoy = date.today()
    mapping = {
        "30d": 30, "90d": 90, "180d": 180,
        "365d": 365, "730d": 730, "1825d": 1825,
    }
    days = mapping.get(rango)
    if days:
        return hoy - timedelta(days=days), hoy
    return dash.no_update, dash.no_update


# 2) Filtros → store + KPIs
@callback(
    [Output("store-cu", "data"),
     Output("kpis-cu", "children")],
    [Input("btn-actualizar-cu", "n_clicks"),
     Input("fecha-filtro-cu", "start_date"),
     Input("fecha-filtro-cu", "end_date")],
    prevent_initial_call="initial_duplicate",
)
def actualizar_store_cu(_n, fecha_inicio_str, fecha_fin_str):
    try:
        if not fecha_inicio_str or not fecha_fin_str:
            return None, html.Div()

        fi = pd.to_datetime(fecha_inicio_str).date()
        ff = pd.to_datetime(fecha_fin_str).date()

        df = _cu_service.get_cu_historico(fi, ff)

        if df.empty:
            return None, dbc.Alert("Sin datos de CU para el período.", color="warning")

        # Asegurar tipos numéricos
        for col in ['cu_total', 'componente_g', 'componente_t', 'componente_d',
                     'componente_c', 'componente_p', 'componente_r']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        cu_ultimo = df['cu_total'].dropna().iloc[-1] if not df['cu_total'].dropna().empty else 0
        cu_promedio = df['cu_total'].mean()
        cu_max = df['cu_total'].max()
        cu_min = df['cu_total'].min()

        # Variación último vs penúltimo
        vals = df['cu_total'].dropna()
        if len(vals) >= 2:
            diff_pct = ((vals.iloc[-1] - vals.iloc[-2]) / vals.iloc[-2]) * 100
            var_dir = "up" if diff_pct > 0 else ("down" if diff_pct < 0 else "flat")
            var_text = f"{diff_pct:+.1f}%"
        else:
            var_dir, var_text = "flat", ""

        kpis = crear_kpi_row([
            {
                "titulo": "CU Actual",
                "valor": f"{cu_ultimo:,.2f}",
                "unidad": "COP/kWh",
                "icono": "fas fa-file-invoice-dollar",
                "color": "red",
                "variacion": var_text,
                "variacion_dir": var_dir,
            },
            {
                "titulo": "Promedio Periodo",
                "valor": f"{cu_promedio:,.2f}",
                "unidad": "COP/kWh",
                "icono": "fas fa-chart-bar",
                "color": "blue",
            },
            {
                "titulo": "Máximo",
                "valor": f"{cu_max:,.2f}",
                "unidad": "COP/kWh",
                "icono": "fas fa-arrow-up",
                "color": "orange",
            },
            {
                "titulo": "Mínimo",
                "valor": f"{cu_min:,.2f}",
                "unidad": "COP/kWh",
                "icono": "fas fa-arrow-down",
                "color": "green",
            },
        ], columnas=4)

        # Serializar store
        store = {
            "fecha_inicio": str(fi),
            "fecha_fin": str(ff),
        }
        return store, kpis

    except Exception as e:
        logger.error("Error actualizando store CU: %s", e)
        traceback.print_exc()
        return None, dbc.Alert(f"Error: {e}", color="danger")


# 3) Store + tab → contenido
@callback(
    Output("cu-tab-content", "children"),
    [Input("store-cu", "data"),
     Input("cu-tabs", "value")],
    prevent_initial_call="initial_duplicate",
)
def renderizar_tab_cu(store_data, tab_activo):
    px, go = get_plotly_modules()

    if not store_data:
        return dbc.Alert("Seleccione un rango de fechas y pulse Actualizar.", color="info")

    try:
        fi = pd.to_datetime(store_data["fecha_inicio"]).date()
        ff = pd.to_datetime(store_data["fecha_fin"]).date()

        # ═══ TAB 1: Evolución Histórica ═══════════════════════
        if tab_activo == "tab-evolucion":
            df = _cu_service.get_cu_historico(fi, ff)
            if df.empty:
                return dbc.Alert("Sin datos históricos.", color="warning")

            df['fecha'] = pd.to_datetime(df['fecha'])
            for c in ['cu_total', 'componente_g', 'componente_t', 'componente_d',
                       'componente_c', 'componente_p', 'componente_r']:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')

            # Línea principal CU total
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df['fecha'], y=df['cu_total'],
                mode='lines',
                name='CU Total',
                line=dict(color=CU_COLORS['cu_total'], width=2.5),
                hovertemplate='%{x|%Y-%m-%d}<br>CU: %{y:,.2f} COP/kWh<extra></extra>',
            ))

            # Área stacked de componentes
            for comp_col, label in COMP_LABELS.items():
                if comp_col in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df['fecha'], y=df[comp_col],
                        mode='lines',
                        name=label,
                        line=dict(width=0),
                        stackgroup='componentes',
                        fillcolor=COMP_COLORS[comp_col].replace(')', ',0.35)').replace('rgb', 'rgba') if 'rgb' in COMP_COLORS[comp_col] else _hex_to_rgba(COMP_COLORS[comp_col], 0.35),
                        hovertemplate=f'{label}: ' + '%{y:,.2f}<extra></extra>',
                    ))

            fig.update_layout(
                height=480,
                hovermode='x unified',
                plot_bgcolor='#FAFAFA',
                paper_bgcolor='white',
                font=dict(family='Inter, sans-serif', size=12),
                margin=dict(l=60, r=20, t=30, b=60),
                xaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='Fecha'),
                yaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='COP/kWh'),
                legend=dict(orientation='h', yanchor='top', y=-0.15, xanchor='center', x=0.5),
            )

            return html.Div([
                crear_chart_card_custom(
                    "Evolución del Costo Unitario (CU)",
                    dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False}),
                    subtitulo=f"{fi} → {ff}",
                ),
            ])

        # ═══ TAB 2: Desglose Componentes ═════════════════════
        elif tab_activo == "tab-desglose":
            df = _cu_service.get_cu_historico(fi, ff)
            if df.empty:
                return dbc.Alert("Sin datos para desglose.", color="warning")

            df['fecha'] = pd.to_datetime(df['fecha'])
            for c in COMP_LABELS:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')

            # Área stacked (100% mode)
            fig_stacked = go.Figure()
            for comp_col, label in COMP_LABELS.items():
                if comp_col in df.columns:
                    fig_stacked.add_trace(go.Scatter(
                        x=df['fecha'], y=df[comp_col],
                        mode='lines',
                        name=label,
                        stackgroup='one',
                        line=dict(width=0.5, color=COMP_COLORS[comp_col]),
                        fillcolor=_hex_to_rgba(COMP_COLORS[comp_col], 0.7),
                        hovertemplate=f'{label}: ' + '%{y:,.2f} COP/kWh<extra></extra>',
                    ))

            fig_stacked.update_layout(
                height=420,
                hovermode='x unified',
                plot_bgcolor='#FAFAFA',
                paper_bgcolor='white',
                font=dict(family='Inter, sans-serif', size=12),
                margin=dict(l=60, r=20, t=30, b=60),
                xaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='Fecha'),
                yaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='COP/kWh'),
                legend=dict(orientation='h', yanchor='top', y=-0.15, xanchor='center', x=0.5),
            )

            # Pie chart (donut) del último día con datos
            last_row = df.dropna(subset=['cu_total']).iloc[-1] if not df.dropna(subset=['cu_total']).empty else None
            if last_row is not None:
                labels = list(COMP_LABELS.values())
                values = [float(last_row.get(c, 0) or 0) for c in COMP_LABELS]
                colors = [COMP_COLORS[c] for c in COMP_LABELS]

                fig_pie = go.Figure(data=[go.Pie(
                    labels=labels,
                    values=values,
                    hole=0.4,
                    marker=dict(colors=colors),
                    textinfo='label+percent',
                    textposition='outside',
                    hovertemplate='%{label}: %{value:,.2f} COP/kWh (%{percent})<extra></extra>',
                )])
                fecha_pie = pd.to_datetime(last_row['fecha']).strftime('%Y-%m-%d') if hasattr(last_row['fecha'], 'strftime') else str(last_row['fecha'])[:10]
                fig_pie.update_layout(
                    height=380,
                    paper_bgcolor='white',
                    font=dict(family='Inter, sans-serif', size=11),
                    margin=dict(l=20, r=20, t=30, b=20),
                    annotations=[dict(
                        text=f"CU<br>{float(last_row.get('cu_total', 0)):,.1f}",
                        x=0.5, y=0.5, font_size=14, showarrow=False,
                        font_color=CU_COLORS['cu_total'],
                    )],
                    showlegend=False,
                )
            else:
                fig_pie = go.Figure()
                fecha_pie = ""

            return html.Div([
                crear_chart_card_custom(
                    "Desglose de Componentes — Área Stacked",
                    dcc.Graph(figure=fig_stacked, config={'displayModeBar': True, 'displaylogo': False}),
                ),
                html.Div([
                    html.Div([
                        crear_chart_card_custom(
                            f"Distribución Porcentual — {fecha_pie}",
                            dcc.Graph(figure=fig_pie, config={'displayModeBar': True, 'displaylogo': False}),
                        ),
                    ], style={'flex': '1'}),
                    html.Div([
                        _crear_tabla_componentes(last_row),
                    ], style={'flex': '1'}),
                ], className="t-grid t-grid-2", style={'marginTop': '16px'}),
            ])

        # ═══ TAB 3: Pronóstico 30 días ═══════════════════════
        elif tab_activo == "tab-forecast":
            df_fc = _cu_service.get_cu_forecast(30)

            if df_fc.empty:
                return dbc.Alert("No hay pronóstico disponible. Se requiere al menos 30 días de datos en cu_daily.", color="warning")

            df_fc['fecha'] = pd.to_datetime(df_fc['fecha'])
            for c in ['cu_predicho', 'limite_inferior', 'limite_superior', 'confianza']:
                df_fc[c] = pd.to_numeric(df_fc[c], errors='coerce')

            # Cargar últimos 30 días de historia para contexto
            hoy = date.today()
            df_hist = _cu_service.get_cu_historico(hoy - timedelta(days=30), hoy)
            if not df_hist.empty:
                df_hist['fecha'] = pd.to_datetime(df_hist['fecha'])
                df_hist['cu_total'] = pd.to_numeric(df_hist['cu_total'], errors='coerce')

            fig = go.Figure()

            # Histórico reciente
            if not df_hist.empty:
                fig.add_trace(go.Scatter(
                    x=df_hist['fecha'], y=df_hist['cu_total'],
                    mode='lines',
                    name='Histórico',
                    line=dict(color=CU_COLORS['cu_total'], width=2),
                ))

            # Banda de confianza
            fig.add_trace(go.Scatter(
                x=pd.concat([df_fc['fecha'], df_fc['fecha'][::-1]]),
                y=pd.concat([df_fc['limite_superior'], df_fc['limite_inferior'][::-1]]),
                fill='toself',
                fillcolor=CU_COLORS['forecast_band'],
                line=dict(color='rgba(255,255,255,0)'),
                name='Intervalo 95%',
                hoverinfo='skip',
            ))

            # Línea de pronóstico
            fig.add_trace(go.Scatter(
                x=df_fc['fecha'], y=df_fc['cu_predicho'],
                mode='lines',
                name='Pronóstico CU',
                line=dict(color=CU_COLORS['forecast_line'], width=2, dash='dashdot'),
                hovertemplate='%{x|%Y-%m-%d}<br>Pronóstico: %{y:,.2f} COP/kWh<extra></extra>',
            ))

            modelo_usado = df_fc['modelo'].iloc[0] if not df_fc.empty else 'N/A'
            confianza_prom = df_fc['confianza'].mean() if not df_fc.empty else 0

            fig.update_layout(
                height=480,
                hovermode='x unified',
                plot_bgcolor='#FAFAFA',
                paper_bgcolor='white',
                font=dict(family='Inter, sans-serif', size=12),
                margin=dict(l=60, r=20, t=30, b=60),
                xaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='Fecha'),
                yaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='COP/kWh'),
                legend=dict(orientation='h', yanchor='top', y=-0.15, xanchor='center', x=0.5),
            )

            # Info card
            info_card = dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-info-circle me-2"),
                    "Información del Pronóstico"
                ], style={'fontWeight': '600', 'backgroundColor': '#f8f9fa'}),
                dbc.CardBody([
                    html.P([html.Strong("Modelo: "), modelo_usado], style={'fontSize': '0.85rem'}),
                    html.P([html.Strong("Confianza promedio: "), f"{confianza_prom:.0%}"], style={'fontSize': '0.85rem'}),
                    html.P([html.Strong("Horizonte: "), "30 días"], style={'fontSize': '0.85rem'}),
                    html.Hr(),
                    html.P([
                        html.Strong("Nota: "),
                        "El pronóstico utiliza predicciones ML cuando están disponibles. "
                        "Si no existen, se genera una tendencia lineal naive basada en los "
                        "últimos 30 días de cu_daily. La banda gris representa el intervalo "
                        "de confianza al 95%."
                    ], style={'fontSize': '0.8rem', 'color': '#666'}),
                ]),
            ], style={'marginTop': '16px'})

            return html.Div([
                crear_chart_card_custom(
                    "Pronóstico del Costo Unitario — 30 días",
                    dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False}),
                ),
                info_card,
            ])

        return html.Div()

    except Exception as e:
        logger.error("Error renderizando tab CU: %s", e)
        traceback.print_exc()
        return dbc.Alert(f"Error al cargar contenido: {e}", color="danger")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convierte #RRGGBB a rgba(r,g,b,a)."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _crear_tabla_componentes(row):
    """Tabla resumen de componentes para el último día."""
    if row is None:
        return dbc.Alert("Sin datos para desglose.", color="info")

    cu_total = float(row.get('cu_total', 0) or 0)
    if cu_total <= 0:
        return dbc.Alert("CU total ≤ 0, sin desglose.", color="info")

    filas = []
    for comp_col, label in COMP_LABELS.items():
        val = float(row.get(comp_col, 0) or 0)
        pct = (val / cu_total * 100) if cu_total > 0 else 0
        color = COMP_COLORS[comp_col]
        filas.append(html.Tr([
            html.Td(
                html.Span("●", style={'color': color, 'fontSize': '1.2rem', 'marginRight': '6px'}),
                style={'width': '30px', 'textAlign': 'center'},
            ),
            html.Td(label, style={'fontWeight': '500', 'fontSize': '0.85rem'}),
            html.Td(f"{val:,.2f}", style={'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': 'bold'}),
            html.Td(f"{pct:.1f}%", style={'textAlign': 'right', 'fontSize': '0.85rem', 'color': '#666'}),
        ]))

    # Total row
    filas.append(html.Tr([
        html.Td("", style={'borderTop': '2px solid #333'}),
        html.Td(html.Strong("CU TOTAL"), style={'borderTop': '2px solid #333'}),
        html.Td(html.Strong(f"{cu_total:,.2f}"), style={'textAlign': 'right', 'fontFamily': 'monospace', 'borderTop': '2px solid #333'}),
        html.Td("100%", style={'textAlign': 'right', 'borderTop': '2px solid #333'}),
    ]))

    fecha_str = str(row.get('fecha', ''))[:10]

    return crear_chart_card_custom(
        f"Desglose CU — {fecha_str}",
        html.Table([
            html.Thead(html.Tr([
                html.Th("", style={'width': '30px'}),
                html.Th("Componente", style={'fontSize': '0.8rem', 'color': '#666'}),
                html.Th("COP/kWh", style={'textAlign': 'right', 'fontSize': '0.8rem', 'color': '#666'}),
                html.Th("%", style={'textAlign': 'right', 'fontSize': '0.8rem', 'color': '#666'}),
            ])),
            html.Tbody(filas),
        ], style={
            'width': '100%',
            'borderCollapse': 'collapse',
            'fontSize': '0.9rem',
        }),
        subtitulo="COP/kWh | Último día disponible",
    )

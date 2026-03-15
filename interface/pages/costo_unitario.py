"""
Página de Costo Unitario (CU) — Portal Energético MME
Evolución histórica, desglose por componentes y pronóstico a 30 días.

FASE 5 — TAREA 5.2
"""

import dash
from dash import html, dcc, callback, Input, Output, State, no_update
import dash_bootstrap_components as dbc
from datetime import date, timedelta
import math
import pandas as pd
import traceback
import logging
import io
import os

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

# Instanciar servicios
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
            dbc.Button([
                html.I(className="fas fa-file-excel me-1"), "Excel"
            ], id="btn-excel-cu", color="success", size="sm", outline=True),
            dcc.Download(id="download-excel-cu"),
            dcc.Download(id="download-pdf-metodologia"),
        ),

        # ── KPIs (callback-updated) ─────────
        html.Div(id="kpis-cu"),

        # ── Tabs ─────────────────────────────
        dcc.Tabs(
            id="cu-tabs",
            value="tab-evolucion",
            children=[
                dcc.Tab(
                    label="Histórico & Desglose",
                    value="tab-evolucion",
                    className="custom-tab",
                    selected_className="custom-tab--selected",
                ),
                dcc.Tab(
                    label="Pronóstico 30 días",
                    value="tab-forecast",
                    className="custom-tab",
                    selected_className="custom-tab--selected",
                ),
                dcc.Tab(
                    label="⚙️ Simulación CREG",
                    value="tab-simulacion",
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
# CALLBACK: Descargar metodología en PDF
# ═══════════════════════════════════════════════════════════════

@callback(
    Output('download-pdf-metodologia', 'data'),
    Input('btn-descargar-pdf-metodologia', 'n_clicks'),
    prevent_initial_call=True,
)
def descargar_pdf_metodologia(n_clicks):
    if not n_clicks:
        return no_update
    try:
        import markdown as md_lib
        import weasyprint

        md_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'METODOLOGIA_CU.md')
        md_path = os.path.normpath(md_path)
        with open(md_path, encoding='utf-8') as f:
            md_text = f.read()

        html_body = md_lib.markdown(md_text, extensions=['tables', 'fenced_code'])
        html_full = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<style>
  body {{ font-family: 'Arial', sans-serif; margin: 48px 56px; color: #222; font-size: 11pt; line-height: 1.6; }}
  h1 {{ font-size: 18pt; color: #1a237e; border-bottom: 2px solid #1a237e; padding-bottom: 6px; margin-bottom: 16px; }}
  h2 {{ font-size: 14pt; color: #1565C0; margin-top: 24px; border-bottom: 1px solid #dce8f5; padding-bottom: 4px; }}
  h3 {{ font-size: 12pt; color: #0d47a1; margin-top: 18px; }}
  h4 {{ font-size: 11pt; color: #01579b; margin-top: 14px; }}
  code, pre {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: 'Courier New', monospace; font-size: 9.5pt; }}
  pre {{ padding: 10px 14px; display: block; white-space: pre-wrap; margin: 10px 0; border-left: 3px solid #1565C0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 9.5pt; }}
  th {{ background: #1565C0; color: white; padding: 6px 8px; text-align: left; }}
  td {{ border: 1px solid #ddd; padding: 5px 8px; }}
  tr:nth-child(even) td {{ background: #f7f9fc; }}
  blockquote {{ border-left: 4px solid #90caf9; margin-left: 0; padding-left: 14px; color: #555; }}
  a {{ color: #1565C0; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 20px 0; }}
  strong {{ font-weight: 700; }}
</style>
</head><body>{html_body}</body></html>"""

        pdf_bytes = weasyprint.HTML(string=html_full).write_pdf()
        return dcc.send_bytes(pdf_bytes, 'METODOLOGIA_CU_Portal_Energetico.pdf')
    except Exception as e:
        logger.error(f"Error generando PDF metodología: {e}")
        return no_update
# CALLBACKS
# ═══════════════════════════════════════════════════════════════

# 1) Dropdown rango → fechas
@callback(
    [Output("fecha-filtro-cu", "start_date"),
     Output("fecha-filtro-cu", "end_date")],
    Input("dropdown-rango-cu", "value"),
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
    prevent_initial_call=True,
)
def actualizar_store_cu(_n, fecha_inicio_str, fecha_fin_str):
    try:
        if not fecha_inicio_str or not fecha_fin_str:
            return dash.no_update, dash.no_update

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

        # Usar solo filas con datos completos (G_CREG_FORMULA) para KPIs de referencia
        df_creg = df[df['notas'].str.contains('G_CREG_FORMULA', na=False)] if 'notas' in df.columns else df
        df_ref = df_creg if not df_creg.empty else df

        vals_creg = df_ref['cu_total'].dropna()
        cu_ultimo = vals_creg.iloc[-1] if not vals_creg.empty else 0
        cu_promedio = df_ref['cu_total'].mean()
        cu_max = df['cu_total'].max()   # máximo histórico incluye todos
        cu_min = df_ref['cu_total'].min()

        # Fecha del último dato CREG disponible
        if not vals_creg.empty:
            idx_ultimo = vals_creg.index[-1]
            fecha_ultimo_dato = str(df_ref.loc[idx_ultimo, 'fecha'])[:10]
        else:
            fecha_ultimo_dato = ""

        # Variación: usar los dos últimos días CREG con datos
        if len(vals_creg) >= 2:
            diff_pct = ((vals_creg.iloc[-1] - vals_creg.iloc[-2]) / vals_creg.iloc[-2]) * 100
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
                "subtexto": f"Datos al {fecha_ultimo_dato}" if fecha_ultimo_dato else "",
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

        # ═══ TAB 1: Histórico & Desglose (unificado) ══════════
        if tab_activo == "tab-evolucion":
            df = _cu_service.get_cu_historico(fi, ff)
            if df.empty:
                return dbc.Alert("Sin datos históricos.", color="warning")

            df['fecha'] = pd.to_datetime(df['fecha'])
            for c in ['cu_total'] + list(COMP_LABELS.keys()):
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')

            # ── Gráfico 1: Series CU total + componentes stacked ──
            fig = go.Figure()
            fig.add_trace(go.Scattergl(
                x=df['fecha'], y=df['cu_total'],
                mode='lines',
                name='CU Total',
                line=dict(color=CU_COLORS['cu_total'], width=2.5),
                hovertemplate='%{x|%Y-%m-%d}<br>CU: %{y:,.2f} COP/kWh<extra></extra>',
            ))
            for comp_col, label in COMP_LABELS.items():
                if comp_col in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df['fecha'], y=df[comp_col],
                        mode='lines',
                        name=label,
                        line=dict(width=0),
                        stackgroup='componentes',
                        fillcolor=_hex_to_rgba(COMP_COLORS[comp_col], 0.35),
                        hovertemplate=f'{label}: ' + '%{y:,.2f}<extra></extra>',
                    ))
            fig.update_layout(
                height=460,
                hovermode='x unified',
                plot_bgcolor='#FAFAFA',
                paper_bgcolor='white',
                font=dict(family='Inter, sans-serif', size=12),
                margin=dict(l=60, r=20, t=30, b=60),
                xaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='Fecha'),
                yaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='COP/kWh'),
                legend=dict(orientation='h', yanchor='top', y=-0.15, xanchor='center', x=0.5),
            )

            # ── Último día con datos CREG completos ──
            df_creg_tab = df[df['notas'].str.contains('G_CREG_FORMULA', na=False)] if 'notas' in df.columns else df
            df_last = df_creg_tab if not df_creg_tab.empty else df
            last_row = df_last.dropna(subset=['cu_total']).iloc[-1] if not df_last.dropna(subset=['cu_total']).empty else None
            fecha_pie = ""
            fig_pie = go.Figure()
            if last_row is not None:
                labels = list(COMP_LABELS.values())
                values = [
                    0.0 if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v)
                    for v in (last_row.get(c, 0) for c in COMP_LABELS)
                ]
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
                    height=360,
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

            # ── Cuadro de metodología y fuentes ──
            metodologia_card = dbc.Card([
                dbc.CardHeader([
                    html.Div([
                        html.Span([
                            html.I(className="fas fa-book-open me-2"),
                            "Metodología de cálculo y fuentes de información",
                        ], style={'fontWeight': '600'}),
                        dbc.Button([
                            html.I(className="fas fa-file-pdf me-1"),
                            "Descargar PDF",
                        ], id='btn-descargar-pdf-metodologia', color='danger',
                           size='sm', outline=True,
                           style={'marginLeft': 'auto'}),
                    ], style={'display': 'flex', 'alignItems': 'center', 'width': '100%'}),
                ], style={'backgroundColor': '#f8f9fa'}),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.H6("Fórmula general", className="fw-bold text-danger mb-2"),
                            html.Code(
                                "CU = G + T + D + C + P + R",
                                style={'fontSize': '0.95rem', 'backgroundColor': '#f8f9fa',
                                       'padding': '6px 12px', 'borderRadius': '4px', 'display': 'block'},
                            ),
                            html.P("Regulado por CREG 119/2007 y actualizaciones SSPD.",
                                   style={'fontSize': '0.78rem', 'color': '#666', 'marginTop': '6px'}),
                        ], md=4),
                        dbc.Col([
                            html.Table([
                                html.Thead(html.Tr([
                                    html.Th("Comp.", style={'width': '50px', 'fontSize': '0.75rem', 'color': '#888'}),
                                    html.Th("Descripción", style={'fontSize': '0.75rem', 'color': '#888'}),
                                    html.Th("Metodología", style={'fontSize': '0.75rem', 'color': '#888'}),
                                    html.Th("Fuente", style={'fontSize': '0.75rem', 'color': '#888'}),
                                ])),
                                html.Tbody([
                                    html.Tr([
                                        html.Td(html.Span("G", style={'fontWeight': 'bold', 'color': CU_COLORS['comp_G']})),
                                        html.Td("Generación", style={'fontSize': '0.8rem'}),
                                        html.Td("Precio promedio ponderado bolsa + contratos bilaterales (LAC)", style={'fontSize': '0.78rem'}),
                                        html.Td(html.A("XM · SIMEM LAC", href="https://www.simem.co/estadisticas/indicadores-de-mercado", target="_blank", style={'fontSize': '0.75rem', 'color': '#1565C0', 'fontWeight': '500', 'textDecoration': 'none'})),
                                    ], style={'borderBottom': '1px solid #f0f0f0'}),
                                    html.Tr([
                                        html.Td(html.Span("T", style={'fontWeight': 'bold', 'color': CU_COLORS['comp_T']})),
                                        html.Td("Transmisión", style={'fontSize': '0.8rem'}),
                                        html.Td("Cargo CND (Sistema de Transmisión Nacional, nivel 1–2)", style={'fontSize': '0.78rem'}),
                                        html.Td(html.A("XM · Cargos regulados", href="https://www.xm.com.co/transmision/cargos-regulados", target="_blank", style={'fontSize': '0.75rem', 'color': '#1565C0', 'fontWeight': '500', 'textDecoration': 'none'})),
                                    ], style={'borderBottom': '1px solid #f0f0f0'}),
                                    html.Tr([
                                        html.Td(html.Span("D", style={'fontWeight': 'bold', 'color': CU_COLORS['comp_D']})),
                                        html.Td("Distribución", style={'fontSize': '0.8rem'}),
                                        html.Td("Cargos por uso STR/SDL aprobados por CREG por OR (nivel 3–6)", style={'fontSize': '0.78rem'}),
                                        html.Td(html.A("SSPD · Boletín Tarifario", href="https://www.superservicios.gov.co/content/boletin-tarifario", target="_blank", style={'fontSize': '0.75rem', 'color': '#1565C0', 'fontWeight': '500', 'textDecoration': 'none'})),
                                    ], style={'borderBottom': '1px solid #f0f0f0'}),
                                    html.Tr([
                                        html.Td(html.Span("C", style={'fontWeight': 'bold', 'color': CU_COLORS['comp_C']})),
                                        html.Td("Comercialización", style={'fontSize': '0.8rem'}),
                                        html.Td("Margen fijo regulado por CREG para comercializadores", style={'fontSize': '0.78rem'}),
                                        html.Td(html.A("SSPD · Boletín Tarifario", href="https://www.superservicios.gov.co/content/boletin-tarifario", target="_blank", style={'fontSize': '0.75rem', 'color': '#1565C0', 'fontWeight': '500', 'textDecoration': 'none'})),
                                    ], style={'borderBottom': '1px solid #f0f0f0'}),
                                    html.Tr([
                                        html.Td(html.Span("P", style={'fontWeight': 'bold', 'color': CU_COLORS['comp_P']})),
                                        html.Td("Pérdidas", style={'fontSize': '0.8rem'}),
                                        html.Td("Factor de pérdidas reconocidas por OR (divide CU antes de P y R)", style={'fontSize': '0.78rem'}),
                                        html.Td(html.A("SSPD · Boletín Tarifario", href="https://www.superservicios.gov.co/content/boletin-tarifario", target="_blank", style={'fontSize': '0.75rem', 'color': '#1565C0', 'fontWeight': '500', 'textDecoration': 'none'})),
                                    ], style={'borderBottom': '1px solid #f0f0f0'}),
                                    html.Tr([
                                        html.Td(html.Span("R", style={'fontWeight': 'bold', 'color': CU_COLORS['comp_R']})),
                                        html.Td("Restricciones", style={'fontSize': '0.8rem'}),
                                        html.Td("Cargo diario por restricciones y redespacho aprobado por CND", style={'fontSize': '0.78rem'}),
                                        html.Td(html.A("XM · Restricciones SIN", href="https://www.xm.com.co/operacion/restricciones", target="_blank", style={'fontSize': '0.75rem', 'color': '#1565C0', 'fontWeight': '500', 'textDecoration': 'none'})),
                                    ]),
                                ]),
                            ], style={'width': '100%', 'borderCollapse': 'collapse'}),
                        ], md=8),
                    ]),
                    html.Hr(style={'margin': '12px 0'}),
                    html.Div([
                        html.Span([html.I(className="fas fa-database me-1"), "Base de datos: "],
                                  style={'fontWeight': '600', 'fontSize': '0.8rem'}),
                        html.Span("PostgreSQL local — actualización diaria vía ETL desde API SIMEM/XM (métricas cu_daily, metricas_xm). ",
                                  style={'fontSize': '0.78rem', 'color': '#555'}),
                        html.Span([html.I(className="fas fa-calendar-alt me-1 ms-3"), "Frecuencia: "],
                                  style={'fontWeight': '600', 'fontSize': '0.8rem'}),
                        html.Span("Diaria (D–1). Los valores de G se calculan con fórmula CREG 119/2007 sobre el precio LAC del día anterior. "
                                  "T, D, C, P se actualizan con cada publicación del Boletín Tarifario SSPD (trimestral).",
                                  style={'fontSize': '0.78rem', 'color': '#555'}),
                    ]),
                ]),
            ], className="shadow-sm", style={'marginTop': '16px'})

            return html.Div([
                crear_chart_card_custom(
                    "Evolución del Costo Unitario (CU) y composición por componentes",
                    dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False}),
                    subtitulo=f"{fi} → {ff}",
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
                metodologia_card,
            ])

        # ═══ TAB 3: Pronóstico 30 días ═══════════════════════
        elif tab_activo == "tab-forecast":
            df_fc = _cu_service.get_cu_forecast(30)

            if df_fc.empty:
                return dbc.Alert("No hay pronóstico disponible. Se requiere al menos 30 días de datos en cu_daily.", color="warning")

            df_fc['fecha'] = pd.to_datetime(df_fc['fecha'])
            for c in ['cu_predicho', 'limite_inferior', 'limite_superior', 'confianza']:
                df_fc[c] = pd.to_numeric(df_fc[c], errors='coerce')

            # Cargar últimos 30 días de historia para contexto (solo días CREG completos)
            hoy = date.today()
            df_hist = _cu_service.get_cu_historico(hoy - timedelta(days=30), hoy)
            if not df_hist.empty:
                df_hist['fecha'] = pd.to_datetime(df_hist['fecha'])
                df_hist['cu_total'] = pd.to_numeric(df_hist['cu_total'], errors='coerce')
                # Excluir días fallback para que el pronóstico no vea la caída artificial
                if 'notas' in df_hist.columns:
                    df_hist = df_hist[df_hist['notas'].str.contains('G_CREG_FORMULA', na=False)]

            fig = go.Figure()

            # Histórico reciente
            if not df_hist.empty:
                fig.add_trace(go.Scattergl(
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
            fig.add_trace(go.Scattergl(
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

            # Tabla comparativa de modelos experimentados
            exp_models = [
                {"modelo": "LightGBM (lag + hidro + calendario)", "mape": "~16–18%", "estado": "🏆 Mejor — en despliegue", "color": "#2E7D32"},
                {"modelo": "RandomForest (multivariable)", "mape": "16.0%", "estado": "✅ Validado (holdout 30d)", "color": "#1565C0"},
                {"modelo": "XGBoost (multivariable)", "mape": "18.1%", "estado": "✅ Validado (holdout 30d)", "color": "#1565C0"},
                {"modelo": "Tendencia lineal naive (30d)", "mape": "~25–40%", "estado": "⚠️ Fallback de emergencia", "color": "#E65100"},
                {"modelo": "Ensemble Prophet + SARIMA", "mape": ">40%", "estado": "❌ Superado por ML", "color": "#B71C1C"},
            ]
            tabla_modelos = html.Table([
                html.Thead(html.Tr([
                    html.Th("Modelo", style={'fontSize': '0.75rem', 'color': '#666', 'fontWeight': '600'}),
                    html.Th("MAPE estimado", style={'fontSize': '0.75rem', 'color': '#666', 'textAlign': 'center'}),
                    html.Th("Estado", style={'fontSize': '0.75rem', 'color': '#666'}),
                ], style={'backgroundColor': '#f8f9fa'})),
                html.Tbody([
                    html.Tr([
                        html.Td(m['modelo'], style={'fontSize': '0.8rem', 'fontWeight': '500' if i == 0 else 'normal'}),
                        html.Td(m['mape'], style={'textAlign': 'center', 'fontFamily': 'monospace', 'fontSize': '0.8rem'}),
                        html.Td(html.Span(m['estado'], style={'color': m['color'], 'fontSize': '0.78rem', 'fontWeight': '500'})),
                    ], style={'borderBottom': '1px solid #f0f0f0'})
                    for i, m in enumerate(exp_models)
                ]),
            ], style={'width': '100%', 'borderCollapse': 'collapse'})

            # Info card
            modelo_usado_label = {
                'lgbm_lag_hidro': 'LightGBM (lag + hidro + calendario)',
                'naive_trend_30d': 'Tendencia lineal naive (30d)',
            }.get(modelo_usado, modelo_usado)

            info_card = dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-flask me-2"),
                    "Metodología del Pronóstico — Resultados de Experimentos ML",
                ], style={'fontWeight': '600', 'backgroundColor': '#f8f9fa'}),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.P([html.Strong("Modelo activo: "), modelo_usado_label], style={'fontSize': '0.85rem'}),
                            html.P([html.Strong("Confianza promedio: "), f"{confianza_prom:.0%}"], style={'fontSize': '0.85rem'}),
                            html.P([html.Strong("Horizonte: "), "30 días"], style={'fontSize': '0.85rem'}),
                            html.Hr(),
                            html.P([
                                html.Strong("Características usadas: "),
                                "y_lag1 (valor del día anterior, ~65% importancia), y_lag7 (semana anterior, ~12%), "
                                "embalses_pct (nivel de embalses, ~7%), aportes_gwh (~7%), "
                                "variables de calendario (día de semana, festivos, mes).",
                            ], style={'fontSize': '0.78rem', 'color': '#555'}),
                            html.P([
                                html.Strong("Validación: "),
                                "Holdout temporal estricto de 30 días (sin data leakage). "
                                "Fuente: experimentos FASE 5–6 del portal, ejecutados en febrero–marzo 2026.",
                            ], style={'fontSize': '0.78rem', 'color': '#555'}),
                        ], md=5),
                        dbc.Col([
                            html.H6("Comparación de modelos evaluados para pronóstico de CU",
                                    className="fw-bold mb-2", style={'fontSize': '0.82rem'}),
                            tabla_modelos,
                        ], md=7),
                    ]),
                ]),
            ], style={'marginTop': '16px'})

            return html.Div([
                crear_chart_card_custom(
                    "Pronóstico del Costo Unitario — 30 días",
                    dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False}),
                ),
                info_card,
            ])

        # ═══ TAB 4: Simulación CREG ══════════════════════════
        elif tab_activo == "tab-simulacion":
            return html.Div([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-flask fa-3x mb-3",
                                   style={'color': '#E63946'}),
                            html.H4("Simulador CREG", className="fw-bold mb-2"),
                            html.P(
                                "Evalúa el impacto regulatorio de cambios en precio de bolsa, "
                                "pérdidas, restricciones, transmisión y comercialización "
                                "sobre el CU y la factura de hogares estrato 3. "
                                "Incluye análisis de incertidumbre con Monte Carlo.",
                                className="text-muted mb-4",
                                style={'maxWidth': '500px'},
                            ),
                            dcc.Link(
                                dbc.Button(
                                    [html.I(className="fas fa-arrow-right me-2"),
                                     "Abrir Simulador CREG"],
                                    color="danger",
                                    size="lg",
                                    className="fw-bold px-4",
                                ),
                                href="/costo-unitario/simulacion",
                            ),
                            html.P(
                                html.Small(
                                    [html.I(className="fas fa-info-circle me-1"),
                                     "La simulación incluye 7 escenarios predefinidos "
                                     "(sequía, apagón, reforma CREG, expansión renovable) "
                                     "y modo personalizado con 5 parámetros ajustables."],
                                    className="text-muted",
                                ),
                                className="mt-3 mb-0",
                            ),
                        ], className="text-center py-4"),
                    ]),
                ], className="shadow-sm"),
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
        val_raw = row.get(comp_col, 0)
        val = 0.0 if (val_raw is None or (isinstance(val_raw, float) and math.isnan(val_raw))) else float(val_raw)
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


# Fase G — Excel export
@callback(
    Output('download-excel-cu', 'data'),
    Input('btn-excel-cu', 'n_clicks'),
    [State('fecha-filtro-cu', 'start_date'),
     State('fecha-filtro-cu', 'end_date')],
    prevent_initial_call=True,
)
def exportar_excel_cu(n_clicks, fecha_inicio_str, fecha_fin_str):
    import io
    try:
        if not fecha_inicio_str or not fecha_fin_str:
            return dash.no_update
        fi = pd.to_datetime(fecha_inicio_str).date()
        ff = pd.to_datetime(fecha_fin_str).date()
        df = _cu_service.get_cu_historico(fi, ff)
        if df is None or df.empty:
            return dash.no_update

        # Forecast en hoja separada
        try:
            df_fc = _cu_service.get_cu_forecast(30)
        except Exception:
            df_fc = pd.DataFrame()

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='CU_Historico', index=False)
            if not df_fc.empty:
                df_fc.to_excel(writer, sheet_name='CU_Pronostico_30d', index=False)
        buf.seek(0)
        return dcc.send_bytes(buf.read(), f"costo_unitario_{str(fi)}_al_{str(ff)}.xlsx")
    except Exception as e:
        logger.error("Error Excel CU: %s", e)
        return dash.no_update

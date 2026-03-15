"""
Costo Unitario — Tarifa Usuario Final
======================================
Tablero detallado de CU por Operador de Red (distribuidora) en Colombia.

Permite filtrar por región, OR/distribuidora y comparar el CU mayorista
(Boletín LAC de XM) con la tarifa que efectivamente paga el usuario final.

Los cargos de referencia provienen del Boletín Tarifario SSPD 2024-Q4.
El componente G se toma del mercado mayorista (cu_daily) y varía cada día.

FÓRMULA (CREG 119 / SSPD Boletín Tarifario):
  CU_usuario = (G + T_STN + T_STR + D + C + Cargos_Sociales) / (1 - Pérd%)
"""

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
from datetime import date, timedelta
import pandas as pd
import logging
import traceback

from interface.components.chart_card import (
    crear_chart_card_custom,
    crear_page_header,
    crear_filter_bar,
)
from interface.components.kpi_card import crear_kpi_row
from domain.services.cu_minorista_service import CUMinoristaService
from domain.services.cu_service import CUService

logger = logging.getLogger(__name__)

dash.register_page(
    __name__,
    path="/costo-usuario-final",
    name="CU Usuario Final",
    title="Costo Unitario — Tarifa Usuario Final",
    order=26,
)

_svc    = CUMinoristaService()
_cu_svc = CUService()

# ── Paleta de colores por región ───────────────────────────────
REGION_COLORS = {
    'Andina':    '#1565C0',
    'Caribe':    '#E65100',
    'Pacifico':  '#2E7D32',
    'Orinoquia': '#6A1B9A',
    'Amazonia':  '#C62828',
}

COMP_COLORS_MIN = {
    'g_mayorista':      '#F5A623',
    't_stn':            '#457B9D',
    't_str':            '#00ACC1',
    'd':                '#2A9D8F',
    'c':                '#7B68EE',
    'r_restricciones':  '#E63946',
    'cargos_sociales':  '#A8DADC',
}

COMP_LABELS_MIN = {
    'g_mayorista':      'G — Generación (mayorista)',
    't_stn':            'T_STN — Transmisión Nacional',
    't_str':            'T_STR — Transmisión Local/STR',
    'd':                'D — Distribución SDL',
    'c':                'C — Comercialización',
    'r_restricciones':  'R — Restricciones Despacho',
    'cargos_sociales':  'Cargos Sociales (FAZNI+FAER+PRONE)',
}


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Geodatos — Mapa Colombia ───────────────────────────────────
import json as _json
import os as _os

_GEOJSON_PATH = _os.path.join(
    _os.path.dirname(__file__), '..', '..', 'assets', 'departamentos_colombia.geojson'
)
try:
    with open(_GEOJSON_PATH, encoding='utf-8') as _gf:
        _GEOJSON_COL = _json.load(_gf)
    for _feat in _GEOJSON_COL['features']:
        _feat['id'] = _feat['properties']['NOMBRE_DPT']
except Exception:
    _GEOJSON_COL = None

# Mapeo departamento (nombre en GeoJSON) → región en cu_tarifas_or
_DEPT_REGION_MAP: dict[str, str] = {
    # Andina (11 depts)
    'ANTIOQUIA':              'Andina',
    'BOYACA':                 'Andina',
    'CALDAS':                 'Andina',
    'CUNDINAMARCA':           'Andina',
    'SANTAFE DE BOGOTA D.C':  'Andina',
    'HUILA':                  'Andina',
    'NORTE DE SANTANDER':     'Andina',
    'QUINDIO':                'Andina',
    'RISARALDA':              'Andina',
    'SANTANDER':              'Andina',
    'TOLIMA':                 'Andina',
    # Caribe (8 depts)
    'ATLANTICO':              'Caribe',
    'BOLIVAR':                'Caribe',
    'CESAR':                  'Caribe',
    'CORDOBA':                'Caribe',
    'LA GUAJIRA':             'Caribe',
    'MAGDALENA':              'Caribe',
    'SUCRE':                  'Caribe',
    'ARCHIPIELAGO DE SAN ANDRES PROVIDENCIA Y SANTA CATALINA': 'Caribe',
    # Pacifico (4 depts)
    'CHOCO':                  'Pacifico',
    'VALLE DEL CAUCA':        'Pacifico',
    'CAUCA':                  'Pacifico',
    'NARINO':                 'Pacifico',
    'NARIÑO':                 'Pacifico',
    # Orinoquia (4 depts)
    'ARAUCA':                 'Orinoquia',
    'CASANARE':               'Orinoquia',
    'META':                   'Orinoquia',
    'VICHADA':                'Orinoquia',
    # Amazonia (6 depts)
    'AMAZONAS':               'Amazonia',
    'CAQUETA':                'Amazonia',
    'GUAINIA':                'Amazonia',
    'GUAVIARE':               'Amazonia',
    'PUTUMAYO':               'Amazonia',
    'VAUPES':                 'Amazonia',
}


# ── Layout ─────────────────────────────────────────────────────

def layout(**kwargs):
    hoy = date.today()

    # Opciones de región y OR para los dropdowns
    try:
        df_ref = _svc.get_tarifas_or()
        regiones_opts = [{"label": "Todas las regiones", "value": "TODAS"}] + [
            {"label": r, "value": r}
            for r in sorted(df_ref['region'].unique())
        ]
        or_opts = [{"label": "Todos los OR", "value": "TODOS"}] + [
            {"label": f"{row['or_codigo']} — {row['or_nombre'][:40]}", "value": row['or_codigo']}
            for _, row in df_ref.sort_values(['region', 'or_codigo']).iterrows()
        ]
    except Exception:
        regiones_opts = [{"label": "Todas las regiones", "value": "TODAS"}]
        or_opts       = [{"label": "Todos los OR", "value": "TODOS"}]

    return html.Div([
        crear_page_header(
            titulo="Tarifa Usuario Final por Distribuidora",
            icono="fas fa-home",
            breadcrumb="Inicio / Costo Unitario / Usuario Final",
            fecha=hoy.strftime("%d/%m/%Y"),
        ),

        crear_filter_bar(
            html.Div([
                # Filtro región
                html.Div([
                    html.Label("Región", className="t-filter-label"),
                    dcc.Dropdown(
                        id="filtro-region-mino",
                        options=regiones_opts,
                        value="TODAS",
                        clearable=False,
                        style={"width": "200px", "fontSize": "0.85rem"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),

                # Filtro OR
                html.Div([
                    html.Label("Distribuidora / OR", className="t-filter-label"),
                    dcc.Dropdown(
                        id="filtro-or-mino",
                        options=or_opts,
                        value="TODOS",
                        clearable=False,
                        style={"width": "280px", "fontSize": "0.85rem"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),

                # Filtro estrato
                html.Div([
                    html.Label("Estrato / Tipo", className="t-filter-label"),
                    dcc.Dropdown(
                        id="filtro-estrato-mino",
                        options=[
                            {"label": "Estrato 1 (subsidio −60%)", "value": "E1"},
                            {"label": "Estrato 2 (subsidio −50%)", "value": "E2"},
                            {"label": "Estrato 3 (subsidio −15%)", "value": "E3"},
                            {"label": "Estrato 4 — tarifa plena",  "value": "E4"},
                            {"label": "Estrato 5 (+20% contrib.)", "value": "E5"},
                            {"label": "Estrato 6 (+20% contrib.)", "value": "E6"},
                            {"label": "Industrial (+20%)",         "value": "Industrial"},
                            {"label": "Comercial (+20%)",          "value": "Comercial"},
                        ],
                        value="E4",
                        clearable=False,
                        style={"width": "230px", "fontSize": "0.85rem"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),

                # Toggle IVA
                html.Div([
                    dbc.Switch(
                        id="toggle-iva-mino",
                        label="+ IVA (19%)",
                        value=False,
                        style={"fontSize": "0.85rem"},
                    ),
                    html.Small(
                        "Aplica a E5/E6/Ind/Com",
                        style={"color": "#888", "fontSize": "0.72rem", "marginLeft": "4px"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),

                # Modo G: mensual (tarifa facturada) vs diario (mercado actual)
                html.Div([
                    html.Label("G referencia", className="t-filter-label",
                               title="Componente G mayorista usado en el cálculo"),
                    dcc.RadioItems(
                        id="radio-modo-g-mino",
                        options=[
                            {"label": "Mensual (tarifa facturada)", "value": "mensual"},
                            {"label": "Diario (mercado actual)",    "value": "diario"},
                        ],
                        value="mensual",
                        inline=True,
                        inputStyle={"marginRight": "4px"},
                        labelStyle={"marginRight": "12px", "fontSize": "0.82rem", "cursor": "pointer"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),

                # Rango histórico (para serie temporal por OR)
                html.Div([
                    html.Label("Histórico", className="t-filter-label"),
                    dcc.Dropdown(
                        id="filtro-rango-mino",
                        options=[
                            {"label": "30 días", "value": "30"},
                            {"label": "90 días", "value": "90"},
                            {"label": "180 días", "value": "180"},
                            {"label": "1 año", "value": "365"},
                        ],
                        value="90",
                        clearable=False,
                        style={"width": "120px", "fontSize": "0.85rem"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),

                dbc.Button([
                    html.I(className="fas fa-file-pdf me-1"), "Descargar PDF"
                ], id="btn-download-pdf-cu", color="secondary", size="sm", outline=True,
                   style={"marginRight": "8px"}),

                dbc.Button([
                    html.I(className="fas fa-sync me-1"), "Actualizar"
                ], id="btn-actualizar-mino", color="primary", size="sm"),
            ]),
        ),

        # KPIs (rellenas por callback)
        html.Div(id="kpis-mino"),

        # Tabs
        dcc.Tabs(
            id="tabs-mino",
            value="tab-mino-comparativa",
            children=[
                dcc.Tab(label="Comparativa por OR",   value="tab-mino-comparativa",
                        className="custom-tab", selected_className="custom-tab--selected"),
                dcc.Tab(label="Desglose Componentes", value="tab-mino-desglose",
                        className="custom-tab", selected_className="custom-tab--selected"),
                dcc.Tab(label="Serie Histórica por OR", value="tab-mino-historico",
                        className="custom-tab", selected_className="custom-tab--selected"),
                dcc.Tab(label="Mapa por Región",     value="tab-mino-mapa",
                        className="custom-tab", selected_className="custom-tab--selected"),
            ],
            style={"marginBottom": "16px"},
        ),

        dcc.Loading(
            id="loading-mino",
            type="dot",
            color="#1565C0",
            children=html.Div(id="contenido-mino"),
        ),

        dcc.Download(id="download-pdf-cu"),

    ], className="t-page")


# ── Callbacks ──────────────────────────────────────────────────

@callback(
    [Output("kpis-mino", "children"),
     Output("contenido-mino", "children")],
    [Input("btn-actualizar-mino", "n_clicks"),
     Input("filtro-region-mino", "value"),
     Input("filtro-or-mino", "value"),
     Input("filtro-rango-mino", "value"),
     Input("filtro-estrato-mino", "value"),
     Input("toggle-iva-mino", "value"),
     Input("tabs-mino", "value"),
     Input("radio-modo-g-mino", "value")],
    prevent_initial_call=False,
)
def actualizar_tablero_mino(_n, region_sel, or_sel, rango_dias, estrato_sel, iva_sel, tab_activo, modo_g):
    import plotly.graph_objects as go

    estrato_sel = estrato_sel or 'E4'
    iva_sel     = bool(iva_sel)
    modo_g      = modo_g or 'mensual'

    try:
        # --- Datos base de todos los OR ---
        df_todos = _svc.get_cu_minorista_todos_or(estrato=estrato_sel, incluir_iva=iva_sel, modo_g=modo_g)
        if df_todos.empty:
            vacio = dbc.Alert("Sin datos de tarifas. Verifique la tabla cu_tarifas_or y cu_daily.", color="warning")
            return html.Div(), vacio

        # Columna activa según IVA
        col_activa = 'cu_con_iva' if iva_sel else 'cu_con_estrato'

        # Filtrar por región
        df = df_todos.copy()
        if region_sel and region_sel != "TODAS":
            df = df[df['region'] == region_sel]

        # Filtrar por OR (para tab historia: aplica solo ahí)
        or_para_historial = or_sel if or_sel and or_sel != "TODOS" else None

        # Meta-info del G
        fecha_g_str = ''
        fuente_g    = ''
        periodo_ref = ''
        if not df_todos.empty:
            fecha_g    = df_todos['fecha_g'].iloc[0]
            fuente_g   = df_todos['fuente_g'].iloc[0] if 'fuente_g' in df_todos.columns else ''
            periodo_ref = df_todos['periodo_ref'].iloc[0] if 'periodo_ref' in df_todos.columns else ''
            try:
                if periodo_ref:
                    fecha_g_str = f" ({periodo_ref})"
                elif fecha_g is not None:
                    fecha_g_str = f" ({fecha_g.strftime('%d/%m/%Y') if hasattr(fecha_g, 'strftime') else fecha_g})"
            except Exception:
                fecha_g_str = ''
        icono_fuente = '📅' if fuente_g == 'G_MENSUAL' else ('✅' if 'CREG_FORMULA' in fuente_g else '⚠️')

        # Información de subsidio/contribución
        from domain.services.cu_minorista_service import FACTOR_ESTRATO, LABELS_ESTRATO
        factor_est  = FACTOR_ESTRATO.get(estrato_sel, 1.0)
        label_est   = LABELS_ESTRATO.get(estrato_sel, estrato_sel)
        pct_delta   = int((factor_est - 1.0) * 100)
        signo_delta = '+' if pct_delta >= 0 else ''

        # ── KPIs ─────────────────────────────────────────────
        cu_mayor_ref = float(df_todos['cu_mayorista'].iloc[0]) if not df_todos.empty else 0
        cu_min_prom  = float(df[col_activa].mean())            if not df.empty else 0
        cu_min_max   = float(df[col_activa].max())             if not df.empty else 0
        or_mas_caro  = df.loc[df[col_activa].idxmax(), 'or_codigo'] if not df.empty else '-'
        brecha       = cu_min_prom - cu_mayor_ref

        label_modo_g = "G mensual" if modo_g == 'mensual' else "G diario"
        kpis = crear_kpi_row([
            {
                "titulo": f"{icono_fuente} {label_modo_g} LAC{fecha_g_str}",
                "valor": f"{cu_mayor_ref:,.1f}",
                "unidad": "COP/kWh",
                "icono": "fas fa-industry",
                "color": "red",
            },
            {
                "titulo": f"CU {label_est} ({region_sel if region_sel != 'TODAS' else 'Nacional'})",
                "valor": f"{cu_min_prom:,.1f}",
                "unidad": "COP/kWh",
                "icono": "fas fa-home",
                "color": "blue",
            },
            {
                "titulo": f"Factor estrato ({signo_delta}{pct_delta}%)",
                "valor": f"{factor_est:.2f}",
                "unidad": "× tarifa base",
                "icono": "fas fa-percent",
                "color": "green" if pct_delta < 0 else ("orange" if pct_delta > 0 else "gray"),
            },
            {
                "titulo": f"Más Caro: {or_mas_caro}",
                "valor": f"{cu_min_max:,.1f}",
                "unidad": "COP/kWh",
                "icono": "fas fa-exclamation-triangle",
                "color": "orange",
            },
        ], columnas=4)

        # ORs con datos actualizados (fuente != SSPD_2024_Q4)
        ors_frescos   = df_todos[~df_todos['fuente'].str.startswith('SSPD_2024', na=False)]['or_codigo'].tolist()
        ors_viejos    = df_todos[ df_todos['fuente'].str.startswith('SSPD_2024', na=False)]['or_codigo'].tolist()
        aviso_datos   = (
            f"✅ Datos actualizados: {', '.join(ors_frescos)}. " if ors_frescos else ""
        ) + (
            f"⚠️ Datos SSPD 2024-Q4 (desactualizados — cargar con ETL): {', '.join(ors_viejos)}."
            if ors_viejos else ""
        )

        # Nota de metodología
        texto_metodologia = (
            f"G mayorista calculado con fórmula CREG 119/2007 (G = P_c × Q_c + P_b × (1−Q_c)). "
            + (f"📅 Modo G mensual: promedio {periodo_ref} — replica tarifa facturada. " if fuente_g == 'G_MENSUAL' else "")
            + (f"⚠️ G usando solo precio de bolsa (sin contratos). " if 'BOLSA' in fuente_g else "")
            + (f"G diario spot{fecha_g_str}. " if modo_g == 'diario' and 'BOLSA' not in fuente_g and fuente_g != 'G_MENSUAL' else "")
            + f"T_STN minorista = 50.87 COP/kWh (derivado Enel Ene-2026). "
            f"Fórmula CU = (G + T_STN + T_STR + D + C + R + CS) / (1 − Pérd%). "
            f"Estrato seleccionado: {label_est} (×{factor_est:.2f}, CREG Res. 131/1998). "
            + (f"+IVA 19% incluido. " if iva_sel else "Sin IVA. ")
        )
        alerta_metodologia = dbc.Alert([
            html.Strong("ℹ️ Metodología: "),
            texto_metodologia,
            *([html.Br(), html.Small(aviso_datos, style={"color": "#666"})] if aviso_datos else []),
        ], color="light", style={"fontSize": "0.77rem", "padding": "8px 14px", "marginTop": "8px"})

        # ── TAB: Comparativa ──────────────────────────────────
        if tab_activo == "tab-mino-comparativa":
            df_plot = df.sort_values(col_activa)
            bar_colors = [REGION_COLORS.get(r, '#607D8B') for r in df_plot['region']]

            fig = go.Figure()
            fig.add_vline(
                x=cu_mayor_ref,
                line=dict(color='#E63946', width=2.5, dash='dash'),
                annotation_text=f"CU Mayorista: {cu_mayor_ref:,.1f}",
                annotation_font_color='#E63946',
                annotation_position='top right',
            )
            fig.add_vline(
                x=cu_min_prom,
                line=dict(color='#1565C0', width=1.5, dash='dot'),
                annotation_text=f"Prom. {label_est}: {cu_min_prom:,.1f}",
                annotation_font_color='#1565C0',
                annotation_position='bottom right',
            )
            fig.add_trace(go.Bar(
                y=df_plot['or_codigo'],
                x=df_plot[col_activa],
                orientation='h',
                marker=dict(color=bar_colors, opacity=0.87, line=dict(width=0.5, color='white')),
                text=[f" {v:,.1f}" for v in df_plot[col_activa]],
                textposition='outside',
                customdata=df_plot[['region', 'departamentos', 'cu_mayorista', 'cu_minorista_total', 'delta_estrato']].values,
                hovertemplate=(
                    '<b>%{y}</b><br>'
                    f'CU {label_est}: <b>%{{x:,.1f}}</b> COP/kWh<br>'
                    'CU base (E4, sin subsidio): %{customdata[3]:,.1f}<br>'
                    'Δ estrato: %{customdata[4]:+,.1f}<br>'
                    'Región: %{customdata[0]}<br>'
                    'Departamentos: %{customdata[1]}<br>'
                    'CU Mayorista: %{customdata[2]:,.1f} COP/kWh<extra></extra>'
                ),
            ))
            fig.update_layout(
                height=max(450, len(df_plot) * 30 + 80),
                plot_bgcolor='#FAFAFA', paper_bgcolor='white',
                font=dict(family='Inter, sans-serif', size=11),
                margin=dict(l=100, r=90, t=50, b=40),
                xaxis=dict(
                    title='COP/kWh', showgrid=True, gridcolor='#f0f0f0',
                    range=[0, df_plot[col_activa].max() * 1.15],
                ),
                yaxis=dict(title='', autorange='reversed'),
                showlegend=False,
            )

            # Leyenda de regiones
            leyenda = html.Div([
                html.Span([
                    html.Span("●", style={"color": c, "marginRight": "4px"}),
                    r,
                ], style={"marginRight": "16px"})
                for r, c in REGION_COLORS.items()
            ], style={"fontSize": "0.8rem", "display": "flex", "flexWrap": "wrap",
                      "gap": "4px", "marginBottom": "8px"})

            titulo_comp = f"CU Usuario Final por Distribuidora — {label_est}"
            subtit_comp = (
                f"La línea roja punteada muestra el CU mayorista (Boletín LAC XM){fecha_g_str}. "
                f"Factor estrato ×{factor_est:.2f} (CREG Res. 131/1998). "
                f"Fuente cargos OR: Boletín SSPD 2024-Q4, NT1 Baja Tensión."
                + (" IVA 19% incluido." if iva_sel else "")
            )

            return kpis, html.Div([
                alerta_metodologia,
                leyenda,
                crear_chart_card_custom(
                    titulo_comp,
                    dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False}),
                    subtitulo=subtit_comp,
                ),
            ])

        # ── TAB: Desglose Componentes ─────────────────────────
        elif tab_activo == "tab-mino-desglose":
            df_plot = df.sort_values('cu_minorista_total', ascending=False)

            fig_stack = go.Figure()
            comps = ['g_mayorista', 't_stn', 't_str', 'd', 'c', 'r_restricciones', 'cargos_sociales']
            for comp in comps:
                if comp in df_plot.columns:
                    fig_stack.add_trace(go.Bar(
                        name=COMP_LABELS_MIN[comp],
                        y=df_plot['or_codigo'],
                        x=df_plot[comp],
                        orientation='h',
                        marker=dict(color=COMP_COLORS_MIN[comp], opacity=0.88),
                        hovertemplate=f'%{{y}}<br>{COMP_LABELS_MIN[comp]}: %{{x:,.1f}} COP/kWh<extra></extra>',
                    ))

            fig_stack.update_layout(
                barmode='stack',
                height=max(450, len(df_plot) * 30 + 100),
                plot_bgcolor='#FAFAFA', paper_bgcolor='white',
                font=dict(family='Inter, sans-serif', size=11),
                margin=dict(l=100, r=30, t=40, b=40),
                xaxis=dict(title='COP/kWh', showgrid=True, gridcolor='#f0f0f0'),
                yaxis=dict(title='', autorange='reversed'),
                legend=dict(orientation='h', yanchor='top', y=-0.08, xanchor='center', x=0.5, font=dict(size=10)),
            )

            # Tabla resumen de OR seleccionado o todos
            if or_para_historial and or_para_historial != 'TODOS':
                row_or = df[df['or_codigo'] == or_para_historial]
                if not row_or.empty:
                    r = row_or.iloc[0]
                    cu_base_denominador = r['cu_minorista_total'] if r['cu_minorista_total'] else 1
                    tabla_detalle = html.Div([
                        html.H6(f"Detalle: {r['or_codigo']} — {r['or_nombre']}", className="fw-bold mb-3"),
                        html.Table([
                            html.Tbody([
                                html.Tr([
                                    html.Td(COMP_LABELS_MIN.get(k, k), style={"fontWeight": "500", "width": "250px"}),
                                    html.Td(f"{r.get(k, 0):,.2f} COP/kWh", style={"textAlign": "right", "fontFamily": "monospace"}),
                                    html.Td(f"{r.get(k, 0)/cu_base_denominador*100:.1f}%", style={"textAlign": "right", "color": "#555"}),
                                ])
                                for k in comps if k in r.index
                            ] + [
                                html.Tr([
                                    html.Td(html.Strong("CU base total (G+T+D+C+R+CS)"), style={"fontWeight": "700"}),
                                    html.Td(html.Strong(f"{sum(r.get(k, 0) for k in comps):,.2f} COP/kWh"), style={"textAlign": "right", "fontFamily": "monospace"}),
                                    html.Td(""),
                                ]),
                                html.Tr([
                                    html.Td(f"Factor pérdidas NT1 ({r.get('perdidas_reconocidas_pct', 0):.1f}%)", style={"fontStyle": "italic", "color": "#666"}),
                                    html.Td(f"× {r.get('factor_perdidas', 1):.4f}", style={"textAlign": "right", "fontFamily": "monospace", "color": "#666"}),
                                    html.Td(""),
                                ]),
                                html.Tr([
                                    html.Td(html.Strong("CU Tarifa Base (E4)"), style={"fontWeight": "700"}),
                                    html.Td(html.Strong(f"{r['cu_minorista_total']:,.2f} COP/kWh"), style={"textAlign": "right", "fontFamily": "monospace"}),
                                    html.Td("100%", style={"textAlign": "right"}),
                                ]),
                                html.Tr([
                                    html.Td(f"Factor estrato: {label_est} (×{factor_est:.2f})", style={"fontStyle": "italic", "color": "#1565C0"}),
                                    html.Td(f"→ {r['cu_con_estrato']:,.2f} COP/kWh", style={"textAlign": "right", "fontFamily": "monospace", "color": "#1565C0", "fontWeight": "bold"}),
                                    html.Td(f"{factor_est*100:.0f}%", style={"textAlign": "right", "color": "#1565C0"}),
                                ]),
                            ] + ([
                                html.Tr([
                                    html.Td("+ IVA 19%", style={"fontStyle": "italic", "color": "#7B1FA2"}),
                                    html.Td(f"→ {r['cu_con_iva']:,.2f} COP/kWh", style={"textAlign": "right", "fontFamily": "monospace", "color": "#7B1FA2", "fontWeight": "bold"}),
                                    html.Td("", style={"textAlign": "right"}),
                                ]),
                            ] if iva_sel and r.get('aplica_iva') else []))
                        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.88rem"}),
                    ])
                else:
                    tabla_detalle = html.Div()
            else:
                tabla_detalle = html.Div()

            return kpis, html.Div([
                alerta_metodologia,
                crear_chart_card_custom(
                    f"Desglose Componentes CU — {label_est} (base sin estrato)",
                    dcc.Graph(figure=fig_stack, config={'displayModeBar': True, 'displaylogo': False}),
                    subtitulo="El stacked muestra los componentes base (E4). El factor de estrato se aplica sobre el total.",
                ),
                html.Div(tabla_detalle, style={"marginTop": "16px"}) if tabla_detalle.children else html.Div(),
            ])

        # ── TAB: Serie Histórica por OR ───────────────────────
        elif tab_activo == "tab-mino-historico":
            dias = int(rango_dias or 90)
            fi = date.today() - timedelta(days=dias)
            ff = date.today()

            # Si se seleccionó un OR específico, mostrar su historia
            if or_para_historial:
                df_hist = _svc.get_cu_minorista_historico_or(or_para_historial, fi, ff)
                if df_hist.empty:
                    return kpis, dbc.Alert("Sin datos históricos para el OR seleccionado.", color="warning")

                df_hist['fecha'] = pd.to_datetime(df_hist['fecha'])

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_hist['fecha'], y=df_hist['cu_mayorista'],
                    name='CU Mayorista LAC', mode='lines',
                    line=dict(color='#E63946', width=1.8, dash='dash'),
                    hovertemplate='%{x|%Y-%m-%d}<br>Mayorista: %{y:,.1f}<extra></extra>',
                ))
                fig.add_trace(go.Scatter(
                    x=df_hist['fecha'], y=df_hist['cu_minorista_total'],
                    name=f'CU Usuario Final ({or_para_historial})', mode='lines',
                    line=dict(color='#1565C0', width=2.5),
                    fill='tonexty', fillcolor='rgba(21,101,192,0.08)',
                    hovertemplate='%{x|%Y-%m-%d}<br>Usuario Final: %{y:,.1f}<extra></extra>',
                ))

                titulo_hist = f"Evolución CU — {or_para_historial} (últimos {dias} días)"

            else:
                # Mostrar promedio nacional + rango min-max
                registros = []
                for _, _or_r in _svc.get_tarifas_or().iterrows():
                    _df = _svc.get_cu_minorista_historico_or(_or_r['or_codigo'], fi, ff)
                    if not _df.empty:
                        _df['or_codigo'] = _or_r['or_codigo']
                        registros.append(_df[['fecha', 'or_codigo', 'cu_minorista_total', 'cu_mayorista']])

                if not registros:
                    return kpis, dbc.Alert("Sin datos históricos.", color="warning")

                df_all = pd.concat(registros, ignore_index=True)
                df_all['fecha'] = pd.to_datetime(df_all['fecha'])
                df_prom = df_all.groupby('fecha').agg(
                    cu_prom=('cu_minorista_total', 'mean'),
                    cu_min =('cu_minorista_total', 'min'),
                    cu_max =('cu_minorista_total', 'max'),
                    cu_mayor =('cu_mayorista', 'first'),
                ).reset_index().sort_values('fecha')

                fig = go.Figure()
                # Banda min-max
                fig.add_trace(go.Scatter(
                    x=pd.concat([df_prom['fecha'], df_prom['fecha'][::-1]]),
                    y=pd.concat([df_prom['cu_max'], df_prom['cu_min'][::-1]]),
                    fill='toself', fillcolor='rgba(21,101,192,0.1)',
                    line=dict(color='rgba(255,255,255,0)'),
                    name='Rango (min-max)', hoverinfo='skip',
                ))
                fig.add_trace(go.Scatter(
                    x=df_prom['fecha'], y=df_prom['cu_mayor'],
                    name='CU Mayorista LAC', mode='lines',
                    line=dict(color='#E63946', width=1.8, dash='dash'),
                ))
                fig.add_trace(go.Scatter(
                    x=df_prom['fecha'], y=df_prom['cu_prom'],
                    name='CU Prom. Usuario Final', mode='lines',
                    line=dict(color='#1565C0', width=2.5),
                ))
                titulo_hist = f"Evolución CU Promedio Nacional (últimos {dias} días)"

            fig.update_layout(
                height=460,
                hovermode='x unified',
                plot_bgcolor='#FAFAFA', paper_bgcolor='white',
                font=dict(family='Inter, sans-serif', size=12),
                margin=dict(l=60, r=20, t=40, b=60),
                xaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='Fecha'),
                yaxis=dict(showgrid=True, gridcolor='#f0f0f0', title='COP/kWh'),
                legend=dict(orientation='h', yanchor='top', y=-0.15, xanchor='center', x=0.5),
            )

            return kpis, crear_chart_card_custom(
                titulo_hist,
                dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False}),
                subtitulo="G mayorista varía diariamente (mercado). T_STR, D, C y pérdidas son constantes (referencia SSPD 2024-Q4).",
            )

        # ── TAB: Mapa por Región ──────────────────────────────
        elif tab_activo == "tab-mino-mapa":
            # Agrupar por región usando la columna ajustada por estrato
            df_region = df_todos.groupby('region').agg(
                cu_prom=(col_activa, 'mean'),
                cu_min =(col_activa, 'min'),
                cu_max =(col_activa, 'max'),
                n_or   =('or_codigo', 'count'),
            ).reset_index()

            fig_reg = go.Figure()
            for _, row in df_region.iterrows():
                c = REGION_COLORS.get(row['region'], '#607D8B')
                fig_reg.add_trace(go.Bar(
                    name=row['region'],
                    x=[row['region']],
                    y=[row['cu_prom']],
                    error_y=dict(
                        type='data',
                        symmetric=False,
                        array=[row['cu_max'] - row['cu_prom']],
                        arrayminus=[row['cu_prom'] - row['cu_min']],
                        color=c, thickness=3,
                    ),
                    marker=dict(color=c, opacity=0.88),
                    text=[f"{row['cu_prom']:,.1f}"],
                    textposition='outside',
                    hovertemplate=(
                        f"<b>{row['region']}</b><br>"
                        f"Promedio: {row['cu_prom']:,.1f} COP/kWh<br>"
                        f"Mínimo: {row['cu_min']:,.1f}<br>"
                        f"Máximo: {row['cu_max']:,.1f}<br>"
                        f"Nº OR: {row['n_or']}<extra></extra>"
                    ),
                ))

            # Línea de referencia mayorista
            fig_reg.add_hline(
                y=float(df_todos['cu_mayorista'].iloc[0]),
                line=dict(color='#E63946', width=2, dash='dash'),
                annotation_text="CU Mayorista LAC",
                annotation_font_color='#E63946',
            )

            fig_reg.update_layout(
                height=400,
                plot_bgcolor='#FAFAFA', paper_bgcolor='white',
                font=dict(family='Inter, sans-serif', size=12),
                margin=dict(l=40, r=40, t=50, b=40),
                yaxis=dict(title='COP/kWh', showgrid=True, gridcolor='#f0f0f0'),
                xaxis=dict(title=''),
                showlegend=False,
                bargap=0.35,
            )

            # ── Mapa choropleth Colombia ───────────────────────
            fig_mapa_col = None
            if _GEOJSON_COL is not None:
                cu_region_dict = dict(zip(df_region['region'], df_region['cu_prom']))
                dept_names, dept_z, dept_text = [], [], []
                for _feat in _GEOJSON_COL['features']:
                    nombre = _feat['properties']['NOMBRE_DPT']
                    region = _DEPT_REGION_MAP.get(nombre, '')
                    cu_val = cu_region_dict.get(region, 0.0)
                    dept_names.append(nombre)
                    dept_z.append(cu_val)
                    dept_text.append(
                        f"<b>{nombre}</b><br>Región: {region}<br>"
                        f"CU {label_est}: {cu_val:,.1f} COP/kWh"
                    )

                z_min = min(dept_z) * 0.95 if dept_z else 0
                z_max = max(dept_z) * 1.05 if dept_z else 1

                fig_mapa_col = go.Figure(go.Choroplethmapbox(
                    geojson=_GEOJSON_COL,
                    locations=dept_names,
                    z=dept_z,
                    colorscale='RdYlGn_r',
                    zmin=z_min,
                    zmax=z_max,
                    marker_opacity=0.82,
                    marker_line_width=0.6,
                    marker_line_color='white',
                    text=dept_text,
                    hovertemplate='%{text}<extra></extra>',
                    colorbar=dict(title='COP/kWh', x=1.01, thickness=14, len=0.75),
                ))
                fig_mapa_col.update_layout(
                    mapbox_style='carto-positron',
                    mapbox_zoom=4.3,
                    mapbox_center={"lat": 4.5, "lon": -74.2},
                    height=470,
                    margin={"r": 0, "t": 35, "l": 0, "b": 0},
                    title=dict(
                        text=f"Colombia — CU {label_est} por Región (COP/kWh)",
                        font=dict(size=12),
                        x=0.5,
                    ),
                )
            tabla_reg_rows = []
            for _, row in df_region.sort_values('cu_prom').iterrows():
                c = REGION_COLORS.get(row['region'], '#607D8B')
                tabla_reg_rows.append(html.Tr([
                    html.Td(html.Span("●", style={"color": c, "fontSize": "1.2rem"})),
                    html.Td(html.Strong(row['region'])),
                    html.Td(str(int(row['n_or'])), style={"textAlign": "center"}),
                    html.Td(f"{row['cu_min']:,.1f}", style={"textAlign": "right", "fontFamily": "monospace", "color": "#2E7D32"}),
                    html.Td(f"{row['cu_prom']:,.1f}", style={"textAlign": "right", "fontFamily": "monospace", "fontWeight": "bold"}),
                    html.Td(f"{row['cu_max']:,.1f}", style={"textAlign": "right", "fontFamily": "monospace", "color": "#C62828"}),
                ]))

            tabla_reg = html.Table([
                html.Thead(html.Tr([
                    html.Th(""),
                    html.Th("Región"),
                    html.Th("N° OR", style={"textAlign": "center"}),
                    html.Th("Mínimo", style={"textAlign": "right"}),
                    html.Th("Promedio", style={"textAlign": "right"}),
                    html.Th("Máximo", style={"textAlign": "right"}),
                ], style={"fontSize": "0.8rem", "color": "#666", "backgroundColor": "#f8f9fa"})),
                html.Tbody(tabla_reg_rows),
            ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.88rem"})

            nota_mapa = dbc.Alert([
                html.I(className="fas fa-map-marked-alt me-2"),
                "Nota: Las barras muestran el promedio regional con barras de error indicando el rango (mín–máx). "
                "La brecha entre regiones refleja diferencias en pérdidas técnicas, distancia a la red troncal y cargos sociales (FAZNI, FAER, PRONE) "
                "que se aplican en zonas de frontera, no interconectadas y rurales.",
            ], color="light", style={"fontSize": "0.8rem", "marginTop": "12px"})

            return kpis, html.Div([
                alerta_metodologia,
                dbc.Row([
                    dbc.Col(
                        crear_chart_card_custom(
                            f"CU {label_est} por Región",
                            dcc.Graph(figure=fig_reg, config={'displayModeBar': True, 'displaylogo': False}),
                            subtitulo="Barras de error: rango min–máx entre distribuidoras",
                        ),
                        width=5,
                    ),
                    dbc.Col(
                        crear_chart_card_custom(
                            "Mapa Colombia — CU por Región",
                            dcc.Graph(figure=fig_mapa_col, config={'displayModeBar': True, 'displaylogo': False})
                            if fig_mapa_col is not None
                            else dbc.Alert("GeoJSON no disponible.", color="secondary"),
                        ),
                        width=7,
                    ),
                ], className="g-3"),
                html.Div(style={"marginTop": "16px"}),
                crear_chart_card_custom(
                    "Resumen por Región (COP/kWh)",
                    tabla_reg,
                ),
                nota_mapa,
            ])

        return kpis, html.Div()

    except Exception as e:
        logger.error("Error tablero usuario final: %s\n%s", e, traceback.format_exc())
        return html.Div(), dbc.Alert(f"Error al cargar el tablero: {e}", color="danger")


# ── PDF — helper + callback ────────────────────────────────────

def _generar_html_para_pdf(df_todos: pd.DataFrame, g_info_str: str,
                            estrato: str, iva: bool,
                            label_est: str, factor_est: float) -> str:
    """Genera HTML con estilo científico para weasyprint → PDF."""
    from datetime import datetime
    fecha_gen = datetime.now().strftime('%d de %B de %Y, %H:%M')
    col = 'cu_con_iva' if iva else 'cu_con_estrato'
    iva_nota = "+IVA 19% incluido" if iva else "Sin IVA"

    filas = ""
    for _, row in df_todos.sort_values(col).iterrows():
        cu_val = row.get(col, 0)
        d_val  = row.get('d', 0)
        c_val  = row.get('c', 0)
        perd   = row.get('perdidas_reconocidas_pct', 0)
        region = row.get('region', '')
        c_color = {
            'Andina': '#1565C0', 'Caribe': '#E65100', 'Pacifico': '#2E7D32',
            'Orinoquia': '#6A1B9A', 'Amazonia': '#C62828',
        }.get(region, '#607D8B')
        filas += (
            f"<tr>"
            f"<td><strong>{row['or_codigo']}</strong></td>"
            f"<td>{row['or_nombre'][:42]}</td>"
            f"<td style='color:{c_color};font-weight:bold'>{region}</td>"
            f"<td style='text-align:right;font-family:monospace'>{d_val:.2f}</td>"
            f"<td style='text-align:right;font-family:monospace'>{c_val:.2f}</td>"
            f"<td style='text-align:right;font-family:monospace'>{perd:.1f}%</td>"
            f"<td style='text-align:right;font-family:monospace;font-weight:bold'>{cu_val:.1f}</td>"
            f"</tr>\n"
        )

    # Resumen regional
    df_reg = df_todos.groupby('region')[col].mean().reset_index()
    filas_reg = ""
    for _, r in df_reg.sort_values(col).iterrows():
        c_color = {
            'Andina': '#1565C0', 'Caribe': '#E65100', 'Pacifico': '#2E7D32',
            'Orinoquia': '#6A1B9A', 'Amazonia': '#C62828',
        }.get(r['region'], '#607D8B')
        filas_reg += (
            f"<tr>"
            f"<td style='color:{c_color};font-weight:bold'>{r['region']}</td>"
            f"<td style='text-align:right;font-family:monospace'>{r[col]:.1f}</td>"
            f"</tr>\n"
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><style>
  @page {{size: A4; margin: 2cm 1.8cm 2cm 1.8cm;}}
  body {{font-family: 'Georgia', 'Times New Roman', serif; font-size: 10pt; color: #1a1a1a; line-height: 1.55;}}
  h1 {{font-size: 15pt; font-weight: bold; text-align: center; color: #0d2b6e; margin: 0 0 4px 0;}}
  h2 {{font-size: 12pt; font-weight: bold; color: #1565C0; margin: 20px 0 6px 0;
       border-bottom: 1.5px solid #1565C0; padding-bottom: 3px;}}
  h3 {{font-size: 10.5pt; font-weight: bold; color: #37474F; margin: 14px 0 5px 0;}}
  .center {{text-align: center;}}
  .subtitle {{text-align:center; font-size:9.5pt; color:#555; margin:0 0 18px 0;}}
  .abstract {{background:#f0f4ff; border-left:4px solid #1565C0; padding:10px 14px;
              font-style:italic; margin:14px 0; font-size:9.5pt;}}
  table {{width:100%; border-collapse:collapse; font-size:8.8pt; margin:12px 0;}}
  th {{background:#1565C0; color:white; padding:5px 7px; text-align:left; font-weight:bold;}}
  td {{padding:3px 7px; border-bottom:1px solid #e8e8e8;}}
  tr:nth-child(even) td {{background:#f9fafb;}}
  .formula {{background:#fff8e1; border:1px solid #f9a825; border-radius:3px;
             padding:8px 14px; font-family:'Courier New',monospace; font-size:9.5pt; margin:10px 0;}}
  .footer {{text-align:center; font-size:7.5pt; color:#888; margin-top:28px;
            border-top:1px solid #ccc; padding-top:7px;}}
  .badge {{display:inline-block; padding:2px 8px; border-radius:3px; font-size:8pt;
           font-weight:bold; color:white; background:#1565C0; margin:0 3px;}}
</style></head>
<body>

<h1>Metodología de Cálculo del Costo Unitario de Energía</h1>
<h1 style="font-size:12.5pt; margin:2px 0 0 0; color:#1565C0;">
  Tarifa al Usuario Final por Operador de Red — Sistema Interconectado Nacional (SIN)
</h1>
<div class="subtitle">
  Portal Energético — Ministerio de Minas y Energía (MME) &nbsp;|&nbsp;
  Generado: {fecha_gen}<br>
  Estrato/Tipo: <strong>{label_est}</strong> (×{factor_est:.2f}) &nbsp;|&nbsp; {iva_nota}
</div>

<div class="abstract">
  <strong>Resumen.</strong> Este documento describe la metodología de cálculo del Costo Unitario (CU)
  de energía eléctrica al usuario final en Colombia, conforme a las resoluciones CREG 119/2007,
  CREG 082/2002 y 101–103/2023 (distribución), CREG 015/2018 (comercialización) y
  CREG 131/1998 (subsidios). Se presentan la formulación tarifaria, los componentes de costo
  (generación, transmisión STN/STR, distribución, comercialización, cargos sociales),
  los factores de estrato socioeconómico y los resultados actuales para los 20 Operadores de Red,
  con referencia {g_info_str}.
</div>

<h2>1. Marco Regulatorio</h2>
<p>El mercado de energía eléctrica colombiano opera bajo un esquema de libre competencia en
generación y un régimen regulado de red (transmisión, distribución y comercialización). La
Comisión de Regulación de Energía y Gas (CREG) fija las metodologías tarifarias:</p>
<ul>
  <li><strong>CREG 119/2007:</strong> Metodología CU mayorista (componente G, mercado LAC).</li>
  <li><strong>CREG 082/2002 y 101–103/2023:</strong> Cargos por uso del SDL — Distribución (D).</li>
  <li><strong>CREG 015/2018:</strong> Cargo de Comercialización (C).</li>
  <li><strong>CREG 131/1998:</strong> Régimen de subsidios y contribuciones de solidaridad.</li>
  <li><strong>Leyes 142 y 143 de 1994:</strong> Servicios públicos y sector eléctrico.</li>
</ul>

<h2>2. Formulación del CU Mayorista — Componente G</h2>
<p>El componente G (Generación) se calcula con la fórmula de la CREG 119/2007 aplicada
al Boletín LAC del mercado mayorista operado por XM S.A. E.S.P.:</p>
<div class="formula">G = P_c × Q_c + P_b × (1 − Q_c)</div>
<p>donde P_c = precio promedio de contratos vigentes (COP/kWh), P_b = precio de bolsa
(COP/kWh) y Q_c = fracción de la demanda cubierta por contratos. El CU mayorista total:</p>
<div class="formula">CU_mayorista = (G + T_STN + D + C + R) / (1 − p_t%)</div>

<h2>3. Formulación del CU al Usuario Final — Tarifa Minorista</h2>
<p>La tarifa facturada al usuario incorpora cargos del Sistema de Distribución Local (SDL)
y cargos sociales obligatorios definidos para cada nivel de tensión:</p>
<div class="formula">CU_usuario_final = (G + T_STN + T_STR + D + C + CS) / (1 − Pérd_NT1%)</div>
<p>Componentes:</p>
<ul>
  <li><strong>G</strong>: Generación (Boletín LAC, CREG 119/2007) — {g_info_str}.</li>
  <li><strong>T_STN</strong>: Transmisión Sistema de Transmisión Nacional.</li>
  <li><strong>T_STR</strong>: Transmisión Sistema de Transmisión Regional.</li>
  <li><strong>D</strong>: Distribución en SDL nivel tensión NT1 (baja tensión residencial).</li>
  <li><strong>C</strong>: Comercialización, cargo regulado por OR (CREG 015/2018).</li>
  <li><strong>CS</strong>: Cargos Sociales (FAZNI + FAER + PRONE).</li>
  <li><strong>Pérd_NT1%</strong>: Pérdidas técnicas reconocidas por CREG para NT1 de cada OR.</li>
</ul>

<h2>4. Régimen de Estratificación Socioeconómica (CREG 131/1998)</h2>
<table>
  <tr><th>Estrato / Tipo</th><th>Factor</th><th>Δ vs E4</th><th>IVA 19%</th><th>Base legal</th></tr>
  <tr><td>Estrato 1</td><td>0.40</td><td>−60% (subsidio máx.)</td><td>No</td><td>Art. 8 CREG 131/98</td></tr>
  <tr><td>Estrato 2</td><td>0.50</td><td>−50%</td><td>No</td><td>Ley 142/94 Art. 99</td></tr>
  <tr><td>Estrato 3</td><td>0.85</td><td>−15%</td><td>No</td><td>Ley 142/94 Art. 99</td></tr>
  <tr><td>Estrato 4</td><td>1.00</td><td>Tarifa plena</td><td>No</td><td>Referencia base</td></tr>
  <tr><td>Estrato 5</td><td>1.20</td><td>+20% (contribución)</td><td>Sí</td><td>Art. 11 CREG 131/98</td></tr>
  <tr><td>Estrato 6</td><td>1.20</td><td>+20%</td><td>Sí</td><td>Ley 142/94 Art. 89</td></tr>
  <tr><td>Industrial</td><td>1.20</td><td>+20%</td><td>Sí</td><td>Dto. 847/2001</td></tr>
  <tr><td>Comercial</td><td>1.20</td><td>+20%</td><td>Sí</td><td>Dto. 847/2001</td></tr>
</table>

<h2>5. Fuentes de Datos</h2>
<ul>
  <li><strong>Componente G:</strong> ETL diario del Boletín LAC de XM — tabla <code>cu_daily</code>.</li>
  <li><strong>Cargos D, C, T_STR, Pérdidas:</strong> Boletín Tarifario SSPD 2024-Q4, tabla <code>cu_tarifas_or</code>, NT1.</li>
  <li><strong>Cargos Sociales:</strong> Ministerio de Minas y Energía, vigentes 2024.</li>
</ul>

<h2>6. Resultados — CU por Operador de Red</h2>
<p>Resultados con G vigente ({g_info_str});
estrato: <strong>{label_est}</strong> (×{factor_est:.2f}); {iva_nota}.
Valores en COP/kWh.</p>
<table>
  <tr>
    <th>Código</th><th>Operador de Red</th><th>Región</th>
    <th>D</th><th>C</th><th>Pérd NT1</th>
    <th>CU {label_est}</th>
  </tr>
  {filas}
</table>

<h2>7. Análisis Regional</h2>
<table>
  <tr><th>Región</th><th>CU Prom. {label_est} (COP/kWh)</th></tr>
  {filas_reg}
</table>

<h2>8. Referencias</h2>
<ol style="font-size:8.8pt; line-height:1.6;">
  <li>CREG. <em>Resolución CREG 119 de 2007 — Metodología CU mayorista.</em> Bogotá: CREG, 2007.</li>
  <li>CREG. <em>Resoluciones 101, 102 y 103 de 2023 — Metodología tarifaria SDL.</em> Bogotá: CREG, 2023.</li>
  <li>CREG. <em>Resolución CREG 015 de 2018 — Cargo de Comercialización.</em> Bogotá: CREG, 2018.</li>
  <li>CREG. <em>Resolución CREG 131 de 1998 — Subsidios y contribuciones.</em> Bogotá: CREG, 1998.</li>
  <li>Congreso de Colombia. <em>Ley 142 de 1994 — Régimen Servicios Públicos.</em></li>
  <li>SSPD. <em>Boletín Tarifario de Energía Eléctrica 2024-Q4.</em> Bogotá: SSPD, 2024.</li>
</ol>

<div class="footer">
  Portal Energético MME — Sistema de Análisis del Mercado de Energía Eléctrica<br>
  Documento generado automáticamente. Para uso interno y análisis de política pública.<br>
  Verifique con fuentes oficiales antes de tomar decisiones regulatorias.
</div>

</body></html>"""


@callback(
    Output("download-pdf-cu", "data"),
    Input("btn-download-pdf-cu", "n_clicks"),
    [dash.dependencies.State("filtro-estrato-mino", "value"),
     dash.dependencies.State("toggle-iva-mino", "value")],
    prevent_initial_call=True,
)
def descargar_pdf_cu(n_clicks, estrato_sel, iva_sel):
    """Genera y descarga el artículo metodológico en PDF (weasyprint)."""
    try:
        from weasyprint import HTML as WeasyprintHTML
        from domain.services.cu_minorista_service import FACTOR_ESTRATO, LABELS_ESTRATO

        estrato_sel = estrato_sel or 'E4'
        iva_sel     = bool(iva_sel)

        df_todos = _svc.get_cu_minorista_todos_or(estrato=estrato_sel, incluir_iva=iva_sel)
        if df_todos.empty:
            return dash.no_update

        factor_est = FACTOR_ESTRATO.get(estrato_sel, 1.0)
        label_est  = LABELS_ESTRATO.get(estrato_sel, estrato_sel)

        fecha_g     = df_todos['fecha_g'].iloc[0]
        fuente_g    = df_todos.get('fuente_g', pd.Series([''])).iloc[0]
        fecha_g_str = fecha_g.strftime('%d/%m/%Y') if hasattr(fecha_g, 'strftime') else str(fecha_g)
        g_info_str  = f"G={float(df_todos['g_mayorista'].iloc[0]):.2f} COP/kWh ({fecha_g_str})"

        html_str = _generar_html_para_pdf(
            df_todos, g_info_str, estrato_sel, iva_sel, label_est, factor_est
        )
        pdf_bytes = WeasyprintHTML(string=html_str).write_pdf()
        nombre_archivo = f"Metodologia_CU_UsuarioFinal_{estrato_sel}_{fecha_g_str.replace('/', '-')}.pdf"
        return dcc.send_bytes(pdf_bytes, nombre_archivo)

    except Exception as e:
        logger.error("Error generando PDF CU: %s\n%s", e, traceback.format_exc())
        return dash.no_update

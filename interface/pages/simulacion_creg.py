"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║              PÁGINA SIMULACIÓN CREG — Portal Energético MME                   ║
║                                                                               ║
║  Motor de simulación paramétrica que permite evaluar el impacto de           ║
║  cambios regulatorios CREG sobre el CU y la factura de hogares.              ║
║                                                                               ║
║  FASE 6 — Motor de Simulación CREG                                           ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import dash
from dash import html, dcc, callback, Input, Output, State, no_update
import dash_bootstrap_components as dbc
import logging
import traceback

from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import (
    crear_chart_card_custom,
    crear_page_header,
)

logger = logging.getLogger(__name__)


def get_plotly_modules():
    """Importación diferida de Plotly."""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go


# ── Registrar la página (subpágina de Costo Unitario) ───────
dash.register_page(
    __name__,
    path="/costo-unitario/simulacion",
    name="Simulación CREG",
    title="Simulación CREG — Portal Energético MME",
    order=26,
)


# ── Paleta de colores ────────────────────────────────────────
SIM_COLORS = {
    'baseline': '#457B9D',
    'simulado': '#E63946',
    'delta_up': '#E63946',
    'delta_down': '#2A9D8F',
    'impacto': '#F5A623',
    'area_fill': 'rgba(230,57,70,0.15)',
}

# ── Escenarios predefinidos (inline para callbacks) ──────────
PRESETS = {
    '': {},
    'sequia_moderada': {
        'precio_bolsa_factor': 1.40,
        'factor_perdidas': 0.085,
        'cargo_restricciones_kw': 3.5,
        'tasa_transmision': 1.0,
        'tasa_comercializacion': 1.0,
    },
    'sequia_severa': {
        'precio_bolsa_factor': 2.20,
        'factor_perdidas': 0.085,
        'cargo_restricciones_kw': 15.0,
        'tasa_transmision': 1.0,
        'tasa_comercializacion': 1.0,
    },
    'reforma_perdidas_reduccion': {
        'precio_bolsa_factor': 1.0,
        'factor_perdidas': 0.070,
        'cargo_restricciones_kw': 0.0,
        'tasa_transmision': 1.0,
        'tasa_comercializacion': 1.0,
    },
    'expansion_renovables': {
        'precio_bolsa_factor': 0.80,
        'factor_perdidas': 0.082,
        'cargo_restricciones_kw': 0.0,
        'tasa_transmision': 1.0,
        'tasa_comercializacion': 1.0,
    },
    'antifraude_agresivo': {
        'precio_bolsa_factor': 1.0,
        'factor_perdidas': 0.072,
        'cargo_restricciones_kw': 0.0,
        'tasa_transmision': 1.0,
        'tasa_comercializacion': 1.0,
    },
    'combinado': {
        'precio_bolsa_factor': 0.88,
        'factor_perdidas': 0.077,
        'cargo_restricciones_kw': 0.0,
        'tasa_transmision': 1.0,
        'tasa_comercializacion': 1.0,
    },
    'apagon_regional': {
        'precio_bolsa_factor': 2.80,
        'factor_perdidas': 0.092,
        'cargo_restricciones_kw': 45.0,
        'tasa_transmision': 1.0,
        'tasa_comercializacion': 1.0,
    },
}


# ══════════════════════════════════════════════════════════════
# PLACEHOLDER (antes de simular)
# ══════════════════════════════════════════════════════════════

def _render_placeholder():
    """Contenido por defecto antes de simular."""
    return dbc.Alert([
        html.H5("⚡ Simulador CREG", className='mb-2'),
        html.P(
            "Ajusta los parámetros regulatorios a la izquierda y presiona "
            "▶ Simular para ver el impacto en el Costo Unitario de Energía."
        ),
        html.Hr(),
        html.Small(
            id='sim-placeholder-base',
            className='text-muted',
        ),
    ], color='light', className='mb-0')


# ══════════════════════════════════════════════════════════════
# RENDER RESULTADO
# ══════════════════════════════════════════════════════════════

def _render_resultado(resultado: dict):
    """Genera el panel derecho completo con los resultados de simulación."""
    px, go = get_plotly_modules()

    cu_sim = resultado.get('cu_simulado', 0)
    cu_base = resultado.get('cu_baseline', 0)
    delta_pct = resultado.get('delta_pct', 0)
    delta_cop = resultado.get('delta_cop_kwh', 0)
    sens = resultado.get('sensibilidad', {})
    advertencias = resultado.get('advertencias', [])
    comp_sim = resultado.get('componentes_simulados', {})
    comp_base = resultado.get('componentes_baseline', {})
    serie = resultado.get('serie_simulada', [])

    # a. KPI row
    var_dir = 'up' if delta_pct > 0 else ('down' if delta_pct < 0 else 'flat')
    delta_color = 'red' if delta_pct > 0 else ('green' if delta_pct < 0 else 'blue')
    top_sens_name = list(sens.keys())[0] if sens else "—"
    top_sens_pct = list(sens.values())[0].get('contribucion_pct', 0) if sens else 0

    # Friendly names for sensitivity
    param_names = {
        'precio_bolsa_factor': 'Precio bolsa',
        'factor_perdidas': 'Factor pérdidas',
        'tasa_transmision': 'Transmisión',
        'tasa_comercializacion': 'Comercializ.',
        'cargo_restricciones_kw': 'Restricciones',
        'demanda_factor': 'Demanda',
    }

    kpi_data = [
        {
            'titulo': 'CU Simulado',
            'valor': f'{cu_sim:.2f}',
            'unidad': ' COP/kWh',
            'icono': 'fas fa-calculator',
            'color': delta_color,
            'variacion': f'{delta_cop:+.2f} COP/kWh',
            'variacion_dir': var_dir,
        },
        {
            'titulo': 'Variación',
            'valor': f'{delta_pct:+.1f}',
            'unidad': '%',
            'icono': 'fas fa-percent',
            'color': delta_color,
            'variacion_dir': var_dir,
        },
        {
            'titulo': 'Cu Base (30d)',
            'valor': f'{cu_base:.2f}',
            'unidad': ' COP/kWh',
            'icono': 'fas fa-chart-line',
            'color': 'blue',
            'subtexto': 'Promedio últimos 30 días',
        },
        {
            'titulo': 'Mayor Impacto',
            'valor': param_names.get(top_sens_name, top_sens_name) if top_sens_name != '—' else '—',
            'unidad': '',
            'icono': 'fas fa-bullseye',
            'color': 'purple',
            'subtexto': f'{top_sens_pct:.0f}% del cambio' if top_sens_name != '—' else 'Sin cambios',
        },
    ]
    kpi_row = crear_kpi_row(kpi_data, columnas=4)

    # b. Gráfico barras agrupadas — Componentes base vs simulado
    comp_labels = {
        'g': 'Generación', 't': 'Transmisión', 'd': 'Distribución',
        'c': 'Comercializ.', 'p': 'Pérdidas', 'r': 'Restricciones',
    }
    comp_order = ['g', 't', 'd', 'c', 'p', 'r']
    cat_names = [comp_labels[k] for k in comp_order]
    base_vals = [comp_base.get(k, 0) for k in comp_order]
    sim_vals = [comp_sim.get(k, 0) for k in comp_order]

    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(
        name='Base', x=cat_names, y=base_vals,
        marker_color=SIM_COLORS['baseline'],
    ))
    fig_comp.add_trace(go.Bar(
        name='Simulado', x=cat_names, y=sim_vals,
        marker_color=SIM_COLORS['simulado'],
    ))
    fig_comp.update_layout(
        barmode='group',
        title='Desglose CU: Base vs Simulado (COP/kWh)',
        yaxis_title='COP/kWh',
        template='plotly_white',
        height=340,
        margin=dict(t=40, b=40, l=50, r=20),
        legend=dict(orientation='h', y=1.12, x=0.5, xanchor='center'),
        font=dict(family='Inter, sans-serif', size=12),
    )

    # c. Gráfico línea — Serie 30 días
    children_serie = []
    if serie:
        fechas = [s['fecha'] for s in serie]
        cu_reales = [s['cu_real'] for s in serie]
        cu_sims = [s['cu_simulado'] for s in serie]

        fig_serie = go.Figure()
        fig_serie.add_trace(go.Scatter(
            x=fechas, y=cu_reales,
            name='CU Real',
            mode='lines',
            line=dict(color=SIM_COLORS['baseline'], width=2),
        ))
        fig_serie.add_trace(go.Scatter(
            x=fechas, y=cu_sims,
            name='CU Simulado',
            mode='lines',
            line=dict(color=SIM_COLORS['simulado'], width=2, dash='dash'),
            fill='tonexty',
            fillcolor=SIM_COLORS['area_fill'],
        ))

        # Ajustar escala Y para mostrar diferencia claramente
        all_vals = cu_reales + cu_sims
        y_min = min(all_vals) * 0.95
        y_max = max(all_vals) * 1.05
        if y_max - y_min < 5:
            mid = (y_max + y_min) / 2
            y_min = mid - 5
            y_max = mid + 5

        fig_serie.update_layout(
            title='Proyección CU: Real vs Simulado (30 días)',
            yaxis_title='COP/kWh',
            yaxis_range=[y_min, y_max],
            template='plotly_white',
            height=320,
            margin=dict(t=40, b=40, l=50, r=20),
            legend=dict(orientation='h', y=1.12, x=0.5, xanchor='center'),
            font=dict(family='Inter, sans-serif', size=12),
        )
        children_serie = [
            crear_chart_card_custom(
                titulo="Proyección CU: Real vs Simulado",
                children=dcc.Graph(figure=fig_serie, config={'displayModeBar': False}),
            ),
        ]

    # d. Tarjeta impacto estrato 3 — ELIMINADA (se cal­cula en sección CU por Usuario)

    # e. Análisis de sensibilidad (barras horizontales)
    children_sens = []
    if sens:
        sens_names = [param_names.get(k, k) for k in sens.keys()]
        sens_contribs = [v['contribucion_pct'] for v in sens.values()]
        sens_deltas = [v['delta_cop_kwh'] for v in sens.values()]
        bar_colors = [SIM_COLORS['delta_up'] if d > 0 else SIM_COLORS['delta_down']
                      for d in sens_deltas]

        fig_sens = go.Figure(go.Bar(
            y=sens_names,
            x=sens_contribs,
            orientation='h',
            marker_color=bar_colors,
            text=[f'{c:.0f}%' for c in sens_contribs],
            textposition='outside',
        ))
        fig_sens.update_layout(
            title='¿Qué causó el cambio?',
            xaxis_title='% del impacto total',
            template='plotly_white',
            height=max(160, len(sens) * 50 + 80),
            margin=dict(t=40, b=30, l=120, r=40),
            font=dict(family='Inter, sans-serif', size=12),
        )
        children_sens = [
            crear_chart_card_custom(
                titulo="Análisis de Sensibilidad",
                children=dcc.Graph(figure=fig_sens, config={'displayModeBar': False}),
            ),
        ]

    # f. Advertencias
    children_adv = [
        dbc.Alert(adv, color='warning', className='py-2 mb-2')
        for adv in advertencias
    ]

    # g. Nota legal
    nota_legal = html.Small(
        "⚠️ Simulación paramétrica — no representa datos reales "
        "ni proyecciones oficiales del MME.",
        className='text-muted fst-italic d-block mt-3',
    )

    # Ensamblar todo
    return html.Div([
        kpi_row,
        crear_chart_card_custom(
            titulo="Desglose CU: Base vs Simulado",
            children=dcc.Graph(figure=fig_comp, config={'displayModeBar': False}),
        ),
        *children_serie,
        *children_sens,
        *children_adv,
        nota_legal,
    ])


# ══════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════

def layout(**kwargs):
    """Layout principal de la página de simulación CREG (subpágina de Costo Unitario)."""
    return html.Div([
        crear_page_header(
            titulo="Simulación CREG",
            breadcrumb="Inicio / Costo Unitario / Simulación CREG",
            icono="fas fa-flask",
        ),

        dbc.Row([
            # ── COLUMNA IZQUIERDA — Panel de control ──
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H6(
                        "⚙️ Parámetros CREG",
                        className='mb-0 fw-bold',
                    )),
                    dbc.CardBody([
                        # Baseline badge (actualizado dinámicamente al cargar)
                        dbc.Alert(
                            id='sim-baseline-badge',
                            color='light',
                            className='py-2 mb-3',
                            style={'borderLeft': '4px solid #F5A623'},
                        ),

                        # Dropdown escenarios predefinidos
                        html.Label(
                            "Escenario predefinido",
                            className='form-label fw-semibold mt-1',
                        ),
                        dcc.Dropdown(
                            id='sim-preset',
                            options=[
                                {'label': '— Personalizado —', 'value': ''},
                                {'label': '🌵 Sequía moderada (El Niño)',
                                 'value': 'sequia_moderada'},
                                {'label': '🔥 Sequía severa (crisis 2022-23)',
                                 'value': 'sequia_severa'},
                                {'label': '📋 Reforma factor pérdidas CREG',
                                 'value': 'reforma_perdidas_reduccion'},
                                {'label': '☀️ Expansión renovables 2GW',
                                 'value': 'expansion_renovables'},
                                {'label': '🛡️ Antifraude Agresivo (AMI)',
                                 'value': 'antifraude_agresivo'},
                                {'label': '⚡ Combinado Óptimo (Renovables+Antifraude)',
                                 'value': 'combinado'},
                                {'label': '⚠️ Apagón Regional (Extremo)',
                                 'value': 'apagon_regional'},
                            ],
                            value='',
                            clearable=False,
                            className='mb-3',
                        ),

                        html.Hr(className='my-2'),

                        # SLIDER 1: Precio bolsa
                        html.Label([
                            "Precio bolsa ",
                            dbc.Badge(id='sim-pb-val', color='secondary', pill=True),
                        ], className='form-label fw-semibold'),
                        html.Small(
                            "Afecta componente G (generación, ~60% del CU). "
                            "Factor 1.0 = sin cambio vs. hoy.",
                            className='text-muted d-block mb-1',
                        ),
                        dcc.Slider(
                            id='sim-precio-bolsa',
                            min=0.5, max=3.0, step=0.05, value=1.0,
                            marks={0.5: '0.5×', 1.0: 'Base',
                                   1.5: '+50%', 2.0: '+100%', 3.0: '+200%'},
                            tooltip={'placement': 'bottom', 'always_visible': False},
                        ),

                        # SLIDER 2: Factor pérdidas
                        html.Label([
                            "Factor pérdidas dist. ",
                            dbc.Badge(id='sim-fp-val', color='secondary', pill=True),
                        ], className='form-label fw-semibold mt-3'),
                        html.Small(
                            "Afecta componentes P y D (~29% del CU). "
                            "CREG actual reconoce 8.5% por OR. Rango histórico: 5–15%.",
                            className='text-muted d-block mb-1',
                        ),
                        dcc.Slider(
                            id='sim-factor-perdidas',
                            min=0.05, max=0.20, step=0.005, value=0.085,
                            marks={0.05: '5%', 0.085: '8.5%',
                                   0.12: '12%', 0.20: '20%'},
                        ),

                        # SLIDER 3: Restricciones
                        html.Label([
                            "Cargo restricciones ",
                            dbc.Badge(id='sim-cr-val', color='secondary', pill=True),
                        ], className='form-label fw-semibold mt-3'),
                        html.Small(
                            "Componente R (~1% del CU en condiciones normales). "
                            "Se eleva a 10–30 COP/kWh en crisis operativas del SIN.",
                            className='text-muted d-block mb-1',
                        ),
                        dcc.Slider(
                            id='sim-rest',
                            min=0.0, max=50.0, step=0.5, value=0.0,
                            marks={0: 'Base', 10: '10', 25: '25', 50: '50'},
                        ),

                        # SLIDER 4: Transmisión
                        html.Label([
                            "Tasa transmisión ",
                            dbc.Badge(id='sim-tr-val', color='secondary', pill=True),
                        ], className='form-label fw-semibold mt-3'),
                        html.Small(
                            "Componente T (~4.4% del CU). Cargo CND regulado. "
                            "Factor 1.0 = tarifa vigente aprobada por CREG.",
                            className='text-muted d-block mb-1',
                        ),
                        dcc.Slider(
                            id='sim-trans',
                            min=0.5, max=1.5, step=0.05, value=1.0,
                            marks={0.5: '0.5×', 1.0: 'Base', 1.5: '1.5×'},
                        ),

                        # SLIDER 5: Comercialización
                        html.Label([
                            "Tasa comercialización ",
                            dbc.Badge(id='sim-tc-val', color='secondary', pill=True),
                        ], className='form-label fw-semibold mt-3'),
                        html.Small(
                            "Componente C (~6.3% del CU). Margen regulado del "
                            "comercializador. Factor 1.0 = tarifa vigente.",
                            className='text-muted d-block mb-1',
                        ),
                        dcc.Slider(
                            id='sim-com',
                            min=0.5, max=1.5, step=0.05, value=1.0,
                            marks={0.5: '0.5×', 1.0: 'Base', 1.5: '1.5×'},
                        ),

                        html.Hr(className='my-3'),

                        # Nombre + botones
                        dbc.Input(
                            id='sim-nombre',
                            placeholder='Nombre del escenario...',
                            value='',
                            className='mb-2',
                            size='sm',
                        ),
                        dbc.Row([
                            dbc.Col(dbc.Button(
                                '▶ Simular',
                                id='sim-btn-run',
                                color='danger',
                                className='w-100 fw-bold',
                            ), width=6),
                            dbc.Col(dbc.Button(
                                '💾 Guardar',
                                id='sim-btn-save',
                                color='secondary',
                                className='w-100',
                                disabled=True,
                            ), width=3),
                            dbc.Col(dbc.Button(
                                '↺',
                                id='sim-btn-reset',
                                color='light',
                                className='w-100',
                            ), width=3),
                        ]),
                        html.Div(id='sim-save-status', className='mt-2'),
                        dbc.Button(
                            [html.I(className="fas fa-file-excel me-1"), "Exportar Excel"],
                            id='btn-excel-simulacion', color="success", size="sm",
                            outline=True, className='w-100 mt-2',
                        ),
                    ]),
                ], className='shadow-sm h-100'),
            ], md=4),

            # ── COLUMNA DERECHA — Resultados ──
            dbc.Col([
                html.Div(
                    id='sim-output',
                    children=_render_placeholder(),
                ),
            ], md=8),
        ], className='g-3'),

        # ── MONTE CARLO ──────────────────────────────────────
        html.Hr(className='my-4'),
        html.H5("📊 Análisis de Incertidumbre (Monte Carlo)",
                className='fw-bold'),
        html.P(
            "Modela la variabilidad natural de los factores del escenario "
            "seleccionado con distribución triangular ±15%.",
            className='text-muted small',
        ),
        dbc.Row([
            dbc.Col([
                dbc.RadioItems(
                    id='mc-n-simulations',
                    options=[
                        {'label': '100 simulaciones (rápido)', 'value': 100},
                        {'label': '500 simulaciones (balanceado)', 'value': 500},
                        {'label': '1000 simulaciones (preciso)', 'value': 1000},
                    ],
                    value=500,
                    inline=True,
                    className='mb-2',
                ),
                dbc.Button(
                    '🎲 Ejecutar Monte Carlo',
                    id='btn-monte-carlo',
                    color='primary',
                    outline=True,
                    size='sm',
                ),
            ], md=8),
        ], className='mb-3'),
        html.Div(id='mc-kpis'),
        dcc.Graph(id='mc-histogram', style={'display': 'none'}),
        html.P(id='mc-interpretacion',
               className='text-muted fst-italic small mt-2'),

        html.Hr(className='my-4'),
        html.Div([
            html.H6("📋 Historial de Simulaciones Guardadas",
                    className='fw-bold mb-0'),
            dbc.Button([
                html.I(className='fas fa-trash me-1'), "Limpiar historial"
            ], id='btn-limpiar-historial', color='danger', size='sm',
               outline=True),
        ], className='d-flex justify-content-between align-items-center mb-2'),
        html.Div(id='sim-limpiar-status'),
        html.Div(id='sim-historial'),

        # Stores
        dcc.Store(id='sim-resultado-store'),
        dcc.Download(id='download-excel-simulacion'),
        # Dispara una sola vez al cargar la página para obtener CU actual
        dcc.Interval(id='sim-init-interval', interval=500, max_intervals=1, n_intervals=0),
    ], className='container-fluid px-4 py-3')


# ══════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════

# 0. Carga inicial → llenar badge de CU base y placeholder con valores reales de BD
@callback(
    Output('sim-baseline-badge', 'children'),
    Output('sim-placeholder-base', 'children'),
    Input('sim-init-interval', 'n_intervals'),
    prevent_initial_call=False,
)
def cargar_baseline_dinamico(n_intervals):
    """Lee el CU base (últimos 30 días) de BD y actualiza los badges."""
    try:
        from core.container import container
        svc = container.simulation_service
        cu_base = svc._get_cu_base_dinamico()
    except Exception:
        cu_base = None

    if cu_base is not None:
        cu_txt = f"{cu_base:.2f} COP/kWh"
    else:
        from domain.services.simulation_service import CU_BASE_DEFAULT
        cu_txt = f"{CU_BASE_DEFAULT:.2f} COP/kWh (ref. hardcoded)"

    badge_children = [
        html.Strong("Base actual: "),
        cu_txt,
        html.Br(),
        html.Small("Promedio CU últimos 30 días", className='text-muted'),
    ]

    placeholder_children = [
        html.Strong("Base actual: "),
        f"CU = {cu_txt}",
    ]

    return badge_children, placeholder_children


# 1. Preset → poblar sliders
@callback(
    Output('sim-precio-bolsa', 'value'),
    Output('sim-factor-perdidas', 'value'),
    Output('sim-rest', 'value'),
    Output('sim-trans', 'value'),
    Output('sim-com', 'value'),
    Input('sim-preset', 'value'),
)
def preset_to_sliders(preset_id):
    """Cuando se selecciona un preset, poblar los sliders."""
    if not preset_id or preset_id not in PRESETS:
        return 1.0, 0.085, 0.0, 1.0, 1.0

    p = PRESETS[preset_id]
    return (
        p.get('precio_bolsa_factor', 1.0),
        p.get('factor_perdidas', 0.085),
        p.get('cargo_restricciones_kw', 0.0),
        p.get('tasa_transmision', 1.0),
        p.get('tasa_comercializacion', 1.0),
    )


# 2. Sliders → badges de valor en tiempo real
@callback(
    Output('sim-pb-val', 'children'),
    Output('sim-fp-val', 'children'),
    Output('sim-cr-val', 'children'),
    Output('sim-tr-val', 'children'),
    Output('sim-tc-val', 'children'),
    Input('sim-precio-bolsa', 'value'),
    Input('sim-factor-perdidas', 'value'),
    Input('sim-rest', 'value'),
    Input('sim-trans', 'value'),
    Input('sim-com', 'value'),
)
def update_badges(pb, fp, rest, trans, com):
    """Muestra el valor actual de cada slider en su badge."""
    delta_pb = (pb - 1.0) * 100
    pb_text = f'×{pb:.2f}' + (f' ({delta_pb:+.0f}%)' if abs(delta_pb) > 0.1 else '')

    delta_fp = (fp - 0.085) * 100
    fp_text = f'{fp * 100:.1f}%' + (f' ({delta_fp:+.1f}pp)' if abs(delta_fp) > 0.01 else '')

    cr_text = f'{rest:.1f} COP/kWh' if rest > 0 else 'Base'

    delta_tr = (trans - 1.0) * 100
    tr_text = f'×{trans:.2f}' + (f' ({delta_tr:+.0f}%)' if abs(delta_tr) > 0.1 else '')

    delta_tc = (com - 1.0) * 100
    tc_text = f'×{com:.2f}' + (f' ({delta_tc:+.0f}%)' if abs(delta_tc) > 0.1 else '')

    return pb_text, fp_text, cr_text, tr_text, tc_text


# 3. Botón Simular → resultado + habilitar Guardar + auto-persistir
@callback(
    Output('sim-output', 'children'),
    Output('sim-resultado-store', 'data'),
    Output('sim-btn-save', 'disabled'),
    Output('sim-historial', 'children', allow_duplicate=True),
    Input('sim-btn-run', 'n_clicks'),
    State('sim-precio-bolsa', 'value'),
    State('sim-factor-perdidas', 'value'),
    State('sim-rest', 'value'),
    State('sim-trans', 'value'),
    State('sim-com', 'value'),
    State('sim-nombre', 'value'),
    prevent_initial_call=True,
)
def run_simulation(n_clicks, pb, fp, rest, trans, com, nombre):
    """Ejecuta la simulación, la persiste automáticamente y renderiza resultados."""
    if not n_clicks:
        return no_update, no_update, no_update, no_update

    try:
        from core.container import container
        svc = container.simulation_service

        # Construir parámetros — siempre pasar todos los valores para
        # que _calcular_sensibilidad pueda filtrar los que están en su
        # valor baseline y evitar el artefacto "100% precio bolsa".
        params = {
            'precio_bolsa_factor': pb,
            'factor_perdidas': fp,
            'tasa_transmision': trans,
            'tasa_comercializacion': com,
        }
        if rest > 0:
            params['cargo_restricciones_kw'] = rest

        resultado = svc.simular_escenario(
            parametros=params,
            nombre=nombre or "Escenario personalizado",
        )

        # Auto-persistir en simulation_results cada vez que se simula
        try:
            svc.guardar_simulacion(
                nombre=nombre or "Escenario personalizado",
                parametros=params,
                resultado=resultado,
                tipo=resultado.get('tipo_escenario', 'PERSONALIZADO'),
            )
            historial_actualizado = _render_historial(svc.get_historial(limite=10))
        except Exception as e_save:
            logger.warning(f"No se pudo auto-guardar simulación: {e_save}")
            historial_actualizado = no_update

        # Validación física del CU simulado
        cu_sim = resultado.get('cu_simulado', 0)
        alertas_fisicas = []
        if cu_sim < 300:
            alertas_fisicas.append(
                dbc.Alert(
                    f"⚠️ CU simulado ({cu_sim:.1f} COP/kWh) está por debajo de 300 COP/kWh — "
                    "valor inferior al mínimo histórico del mercado colombiano (CU nunca bajó "
                    "de ~600 COP/kWh en La Niña 2023-2024). Revisar parámetros.",
                    color='warning', className='mb-2',
                )
            )
        elif cu_sim > 1_500:
            alertas_fisicas.append(
                dbc.Alert(
                    f"⚠️ CU simulado ({cu_sim:.1f} COP/kWh) supera 1,500 COP/kWh — "
                    "nivel de crisis extrema comparable a El Niño 2023. Confirmar escenario.",
                    color='warning', className='mb-2',
                )
            )

        output_children = alertas_fisicas + [_render_resultado(resultado)] if alertas_fisicas else _render_resultado(resultado)
        return output_children, resultado, False, historial_actualizado

    except Exception as e:
        logger.error(f"Error en simulación dashboard: {e}\n{traceback.format_exc()}")
        return dbc.Alert(
            f"Error en simulación: {str(e)}",
            color='danger',
        ), no_update, True, no_update


# 4. Botón Guardar → persistir + historial
@callback(
    Output('sim-save-status', 'children'),
    Output('sim-historial', 'children', allow_duplicate=True),
    Input('sim-btn-save', 'n_clicks'),
    State('sim-resultado-store', 'data'),
    State('sim-nombre', 'value'),
    prevent_initial_call=True,
)
def save_simulation(n_clicks, resultado, nombre):
    """Guarda la simulación actual en BD."""
    if not n_clicks or not resultado:
        return no_update, no_update

    try:
        from core.container import container
        svc = container.simulation_service

        row_id = svc.guardar_simulacion(
            nombre=nombre or "Escenario guardado",
            parametros=resultado.get('parametros_usados', {}),
            resultado=resultado,
            tipo=resultado.get('tipo_escenario', 'PERSONALIZADO'),
        )

        status_msg = dbc.Alert(
            f"✅ Simulación guardada (id={row_id})",
            color='success',
            className='py-1 mb-0',
            duration=4000,
        )

        historial = _render_historial(svc.get_historial(limite=10))
        return status_msg, historial

    except Exception as e:
        return dbc.Alert(
            f"Error: {str(e)}",
            color='danger',
            className='py-1 mb-0',
        ), no_update


# 5. Reset → volver sliders a base
@callback(
    Output('sim-preset', 'value'),
    Output('sim-output', 'children', allow_duplicate=True),
    Output('sim-btn-save', 'disabled', allow_duplicate=True),
    Input('sim-btn-reset', 'n_clicks'),
    prevent_initial_call=True,
)
def reset_simulation(n_clicks):
    """Resetea todos los sliders a valores base."""
    if not n_clicks:
        return no_update, no_update, no_update
    return '', _render_placeholder(), True


# 6b. Limpiar historial
@callback(
    Output('sim-historial', 'children', allow_duplicate=True),
    Output('sim-limpiar-status', 'children'),
    Input('btn-limpiar-historial', 'n_clicks'),
    prevent_initial_call=True,
)
def limpiar_historial_callback(n_clicks):
    """Elimina todo el historial de simulaciones guardadas."""
    if not n_clicks:
        return no_update, no_update
    try:
        from core.container import container
        svc = container.simulation_service
        deleted = svc.limpiar_historial()
        status = dbc.Alert(
            f"✅ {deleted} simulacion{'es' if deleted != 1 else ''} eliminada{'s' if deleted != 1 else ''}.",
            color='success', duration=4000, className='py-1 px-2 mb-0 mt-1',
        )
        return html.Small("Sin simulaciones guardadas.", className='text-muted'), status
    except Exception as e:
        return no_update, dbc.Alert(
            f"Error al limpiar: {e}", color='danger', className='py-1 px-2 mb-0 mt-1',
        )


# 6. Historial al cargar
@callback(
    Output('sim-historial', 'children'),
    Input('sim-historial', 'id'),
)
def load_historial(_):
    """Carga el historial de simulaciones al iniciar."""
    try:
        from core.container import container
        svc = container.simulation_service
        return _render_historial(svc.get_historial(limite=10))
    except Exception as e:
        return html.Small("Sin historial disponible.", className='text-muted')


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _render_historial(items: list):
    """Renderiza tabla de historial de simulaciones."""
    if not items:
        return html.Small("Sin simulaciones guardadas.", className='text-muted')

    header = html.Thead(html.Tr([
        html.Th("Nombre", style={'width': '30%'}),
        html.Th("Tipo"),
        html.Th("CU Base"),
        html.Th("CU Sim"),
        html.Th("Δ %"),
        html.Th("Fecha"),
    ]))

    rows = []
    for item in items:
        delta = item.get('impacto_pct', 0)
        delta_color = '#E63946' if delta > 0 else '#2A9D8F'
        cu_sim = item.get('cu_simulado')
        cu_base = item.get('cu_baseline')
        rows.append(html.Tr([
            html.Td(item.get('nombre', ''), style={'fontWeight': '500'}),
            html.Td(dbc.Badge(
                item.get('tipo', ''),
                color='info' if item.get('tipo') == 'SEQUIA' else 'secondary',
                pill=True,
            )),
            html.Td(f'{cu_base:.1f}' if cu_base else '—'),
            html.Td(f'{cu_sim:.1f}' if cu_sim else '—'),
            html.Td(
                f'{delta:+.1f}%',
                style={'color': delta_color, 'fontWeight': '600'},
            ),
            html.Td(
                str(item.get('fecha', ''))[:16],
                style={'fontSize': '0.85rem'},
            ),
        ]))

    return dbc.Table(
        [header, html.Tbody(rows)],
        bordered=True,
        hover=True,
        responsive=True,
        size='sm',
        className='mt-2',
    )


# ═══════════════════════════════════════════════════════════════
# CALLBACK: Monte Carlo
# ═══════════════════════════════════════════════════════════════
@callback(
    Output('mc-kpis', 'children'),
    Output('mc-histogram', 'figure'),
    Output('mc-histogram', 'style'),
    Output('mc-interpretacion', 'children'),
    Input('btn-monte-carlo', 'n_clicks'),
    State('mc-n-simulations', 'value'),
    State('sim-preset', 'value'),
    prevent_initial_call=True,
)
def run_monte_carlo_callback(n_clicks, n_simulations, preset_id):
    """Ejecuta Monte Carlo sobre el escenario preset seleccionado."""
    if not n_clicks:
        return no_update, no_update, {'display': 'none'}, ''

    escenario = preset_id if preset_id else 'expansion_renovables'
    try:
        from core.container import container
        svc = container.simulation_service
        result = svc.run_monte_carlo(
            escenario=escenario,
            n_simulations=n_simulations,
        )
    except Exception as e:
        logger.error(f"Monte Carlo error: {e}")
        return (
            dbc.Alert(f"Error ejecutando Monte Carlo: {e}", color='danger'),
            {},
            {'display': 'none'},
            '',
        )

    p10 = result['cu_p10']
    p50 = result['cu_p50']
    p90 = result['cu_p90']
    cu_base = result['cu_base']
    reduccion = result['reduccion_cu_p50']
    nombre_esc = escenario.replace('_', ' ').title()

    # KPIs
    kpis = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("P10 (optimista)", className='text-muted small mb-1'),
            html.H5(f"{p10:.1f}", className='text-success fw-bold mb-0'),
            html.Small("COP/kWh"),
        ]), className='text-center shadow-sm'), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("P50 (más probable)", className='text-muted small mb-1'),
            html.H5(f"{p50:.1f}", className='text-primary fw-bold mb-0'),
            html.Small("COP/kWh"),
        ]), className='text-center shadow-sm'), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("P90 (pesimista)", className='text-muted small mb-1'),
            html.H5(f"{p90:.1f}", className='text-danger fw-bold mb-0'),
            html.Small("COP/kWh"),
        ]), className='text-center shadow-sm'), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Reducción P50 vs base", className='text-muted small mb-1'),
            html.H5(
                f"{reduccion:+.1f}%",
                className=f"fw-bold mb-0 {'text-success' if reduccion < 0 else 'text-danger'}",
            ),
            html.Small(f"Base: {cu_base:.1f} COP/kWh"),
        ]), className='text-center shadow-sm'), md=3),
    ], className='g-2 mb-3')

    # Histograma
    import plotly.graph_objects as go
    hist_data = result['histogram_data']
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=hist_data,
        nbinsx=30,
        name='Distribución CU',
        marker_color='#4C8BF5',
        opacity=0.75,
    ))
    for val, label, color in [
        (p10, 'P10', '#2A9D8F'),
        (p50, 'P50', '#264653'),
        (p90, 'P90', '#E63946'),
    ]:
        fig.add_vline(
            x=val, line_dash='dash', line_color=color,
            annotation_text=f'{label}: {val:.1f}',
            annotation_position='top',
        )
    fig.update_layout(
        title=f'Monte Carlo — {nombre_esc} ({n_simulations} simulaciones)',
        xaxis_title='CU Simulado (COP/kWh)',
        yaxis_title='Frecuencia',
        template='plotly_white',
        height=320,
        margin={'t': 50, 'b': 40, 'l': 50, 'r': 20},
        showlegend=False,
    )

    # Texto interpretativo
    rango_80 = f"{p10:.1f} – {p90:.1f}"
    dir_txt = "reducción" if reduccion < 0 else "incremento"
    abs_red = abs(reduccion)
    texto = (
        f"Con {n_simulations} simulaciones sobre el escenario «{nombre_esc}», "
        f"hay un 80% de probabilidad de que el CU esté entre {rango_80} COP/kWh. "
        f"El valor más probable (P50) es {p50:.1f} COP/kWh, "
        f"lo que representa una {dir_txt} estimada de {abs_red:.1f}% "
        f"respecto al CU base actual de {cu_base:.1f} COP/kWh."
    )

    return kpis, fig, {'display': 'block'}, texto


# Fase G — Excel export (desde Store del resultado)
@callback(
    Output('download-excel-simulacion', 'data'),
    Input('btn-excel-simulacion', 'n_clicks'),
    State('sim-resultado-store', 'data'),
    prevent_initial_call=True,
)
def exportar_excel_simulacion(n_clicks, resultado):
    import io
    import pandas as pd
    try:
        if not resultado:
            return no_update
        # Aplanar el resultado en filas key-value y por componente
        rows = []
        for k, v in resultado.items():
            if not isinstance(v, (dict, list)):
                rows.append({'Parametro': k, 'Valor': v})
        df_resumen = pd.DataFrame(rows)

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df_resumen.to_excel(writer, sheet_name='Resultado_Simulacion', index=False)
            # Si hay desglose por componente
            componentes = resultado.get('desglose_componentes') or resultado.get('componentes')
            if isinstance(componentes, dict):
                pd.DataFrame([componentes]).to_excel(writer, sheet_name='Componentes', index=False)
        buf.seek(0)
        return dcc.send_bytes(buf.read(), "simulacion_creg.xlsx")
    except Exception as e:
        logger.error("Error Excel simulacion: %s", e)
        return no_update

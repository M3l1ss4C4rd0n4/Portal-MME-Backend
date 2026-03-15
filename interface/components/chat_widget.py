# -*- coding: utf-8 -*-
"""
Componente de Chat IA - Agente Analista Energético
Integración directa con OpenRouter usando Python
"""
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback
from datetime import datetime
import logging
import json

# Importar el agente IA Python
from domain.services.ai_service import get_agente

logger = logging.getLogger(__name__)

# Estilos del chat
CHAT_STYLES = {
    'container': {
        'position': 'fixed',
        'left': '85px',
        'bottom': '20px',
        'width': '400px',
        'height': '580px',
        'maxHeight': 'calc(100vh - 110px)',
        'backgroundColor': 'white',
        'borderRadius': '15px',
        'boxShadow': '0 8px 32px rgba(0,0,0,0.2)',
        'zIndex': '9999',
        'display': 'flex',
        'flexDirection': 'column',
        'overflow': 'hidden'
    },
    'header': {
        'background': 'linear-gradient(135deg, #1e40af 0%, #3b82f6 100%)',
        'color': 'white',
        'padding': '20px',
        'borderRadius': '15px 15px 0 0',
        'display': 'flex',
        'justifyContent': 'space-between',
        'alignItems': 'center'
    },
    'messages': {
        'flex': '1',
        'overflowY': 'auto',
        'padding': '20px',
        'backgroundColor': '#f8fafc'
    },
    'input_area': {
        'padding': '15px',
        'backgroundColor': 'white',
        'borderTop': '1px solid #e2e8f0',
        'display': 'flex',
        'gap': '10px'
    },
    'user_message': {
        'backgroundColor': '#3b82f6',
        'color': 'white',
        'padding': '12px 16px',
        'borderRadius': '15px 15px 4px 15px',
        'marginBottom': '12px',
        'maxWidth': '80%',
        'marginLeft': 'auto',
        'wordWrap': 'break-word'
    },
    'ai_message': {
        'backgroundColor': 'white',
        'color': '#1e293b',
        'padding': '12px 16px',
        'borderRadius': '15px 15px 15px 4px',
        'marginBottom': '12px',
        'maxWidth': '80%',
        'marginRight': 'auto',
        'boxShadow': '0 2px 8px rgba(0,0,0,0.05)',
        'wordWrap': 'break-word'
    },
    'timestamp': {
        'fontSize': '0.7rem',
        'color': '#94a3b8',
        'marginTop': '4px'
    },
    'button_toggle': {
        'width': '62px',
        'height': '62px',
        'borderRadius': '50%',
        'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'border': 'none',
        'boxShadow': '0 8px 24px rgba(102, 126, 234, 0.5)',
        'cursor': 'pointer',
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'center',
        'transition': 'all 0.3s ease',
        'animation': 'pulse 2s infinite',
        'position': 'relative',
    },
    'button_wrapper': {
        'position': 'fixed',
        'left': '15px',
        'top': '70%',
        'transform': 'translateY(-50%)',
        'zIndex': '99999',
    },
}


def cargar_alertas_chatbot():
    """Carga alertas críticas/alerta de las últimas 24 h para mostrarlas como notificaciones en el chat."""
    try:
        from infrastructure.database.manager import db_manager
        df = db_manager.query_df("""
            SELECT metrica, severidad, descripcion, fecha_generacion
            FROM alertas_historial
            WHERE severidad IN ('CRÍTICO', 'ALERTA')
              AND fecha_generacion >= NOW() - INTERVAL '24 hours'
            ORDER BY severidad DESC, fecha_generacion DESC
            LIMIT 5
        """)
        if df.empty:
            return []
        ICON_MAP = {
            'BALANCE_ENERGETICO': '⚖️', 'DEMANDA': '📈', 'EMBALSES': '💧',
            'PRECIO_MERCADO': '💰', 'DATOS_CONGELADOS': '🧊', 'PNT_CRÍTICA': '⚡',
        }
        mensajes = []
        for _, row in df.iterrows():
            icon = ICON_MAP.get(str(row['metrica']).split(':')[0].strip(), '🚨')
            fecha_str = str(row['fecha_generacion'])[:16]
            hora = fecha_str[-5:] if len(fecha_str) >= 5 else datetime.now().strftime("%H:%M")
            texto = f"{icon} **{row['metrica']}**\n{row['descripcion']}\n\n_📅 {fecha_str}_"
            mensajes.append(crear_mensaje_notificacion(texto, str(row['severidad']), hora))
        return mensajes
    except Exception as e:
        logger.warning(f"Error cargando alertas para chatbot: {e}")
        return []


def contar_alertas_recientes():
    """Cuenta alertas CRÍTICO de las últimas 24 h para el badge del botón."""
    try:
        from infrastructure.database.manager import db_manager
        df = db_manager.query_df("""
            SELECT COUNT(*) AS cnt FROM alertas_historial
            WHERE severidad = 'CRÍTICO'
              AND fecha_generacion >= NOW() - INTERVAL '24 hours'
        """)
        return int(df.iloc[0]['cnt']) if not df.empty else 0
    except Exception:
        return 0


def crear_mensaje_notificacion(texto, severidad='CRÍTICO', timestamp=None):
    """Burbuja de notificación de alerta con estilo visual diferenciado del mensaje IA."""
    if timestamp is None:
        timestamp = datetime.now().strftime("%H:%M")
    if severidad == 'CRÍTICO':
        bg, border, icon_color, label = '#fff5f5', '#b91c1c', '#ef4444', '🔴 CRÍTICO'
    else:
        bg, border, icon_color, label = '#fffbeb', '#d97706', '#f59e0b', '🟡 ALERTA'
    return html.Div([
        html.Div([
            html.Span([
                html.I(className="fas fa-bell", style={'marginRight': '5px', 'color': icon_color}),
                html.Span(label, style={
                    'fontSize': '0.68rem', 'fontWeight': '700', 'color': icon_color,
                    'textTransform': 'uppercase', 'letterSpacing': '0.06em',
                }),
            ], style={'display': 'block', 'marginBottom': '6px'}),
            dcc.Markdown(texto, style={'width': '100%', 'lineHeight': '1.5', 'margin': '0'},
                         dangerously_allow_html=False),
        ], style={'marginBottom': '4px'}),
        html.Div(timestamp, style=CHAT_STYLES['timestamp']),
    ], style={
        'backgroundColor': bg, 'color': '#1c1917',
        'padding': '12px 16px', 'borderRadius': '10px',
        'borderLeft': f'4px solid {border}',
        'marginBottom': '12px', 'maxWidth': '98%', 'marginRight': 'auto',
        'boxShadow': '0 2px 8px rgba(185,28,28,0.1)', 'wordWrap': 'break-word',
    })


def _api_key() -> str:
    """Devuelve la API Key del orquestador definida en settings."""
    try:
        from core.config import settings
        return settings.API_KEY
    except Exception:
        import os
        return os.getenv('API_KEY', 'mme-portal-energetico-2026-secret-key')


def obtener_noticias_chatbot():
    """
    Llama al orquestador con intent noticias_sector y retorna burbujas de chat estructuradas.
    Mismo patrón que cargar_alertas_chatbot(), sin pasar por la IA de OpenRouter.
    """
    try:
        import requests as req
        resp = req.post(
            'http://localhost:8000/v1/chatbot/orchestrator',
            json={'sessionId': 'dashboard_noticias', 'intent': 'noticias_sector', 'parameters': {}},
            headers={'Content-Type': 'application/json', 'X-API-Key': _api_key()},
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get('data', {})
        noticias = data.get('noticias', [])

        if not noticias:
            nota = data.get('nota', 'No se encontraron noticias relevantes del sector hoy.')
            return [crear_mensaje_ia(f"📰 {nota}")]

        mensajes = []

        # Resumen IA si está disponible
        resumen = data.get('resumen_general')
        if resumen:
            mensajes.append(crear_mensaje_ia(f"📡 **Resumen del sector hoy:**\n\n{resumen}"))

        # Una burbuja por noticia
        for i, n in enumerate(noticias, 1):
            titulo = n.get('titulo', 'Sin título')
            resumen_corto = n.get('resumen', '')
            fuente = n.get('fuente', '')
            fecha = str(n.get('fecha', ''))[:10]
            url = n.get('url', '')

            texto = f"**{i}. {titulo}**"
            if resumen_corto:
                texto += f"\n\n{resumen_corto}"
            if fuente or fecha:
                footer = " · ".join(filter(None, [fuente, fecha]))
                texto += f"\n\n📰 _{footer}_"
            if url:
                texto += f"\n\n[🔗 Leer más]({url})"

            mensajes.append(crear_mensaje_ia(texto))

        return mensajes

    except Exception as e:
        logger.warning(f"Error obteniendo noticias del orquestador: {e}")
        return [crear_mensaje_ia("❌ No se pudo conectar con el servicio de noticias. Verifica que la API esté activa.")]


def crear_componente_chat():
    """
    Crear componente de chat flotante para el dashboard.
    Posicionado a la IZQUIERDA del dashboard, centrado verticalmente.
    """
    return html.Div([
        dcc.Interval(id='chat-notif-interval', interval=5 * 60 * 1000, n_intervals=0),

        # ── Botón flotante (izquierda, centrado vertical) con badge de alertas ──
        html.Div([
            # Badge contador de alertas críticas
            html.Span("", id='chat-notif-badge', style={
                'position': 'absolute', 'top': '-7px', 'right': '-7px',
                'backgroundColor': '#ef4444', 'color': 'white',
                'borderRadius': '50%', 'minWidth': '20px', 'height': '20px',
                'fontSize': '0.65rem', 'fontWeight': 'bold',
                'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                'zIndex': '100001', 'padding': '0 4px',
                'boxShadow': '0 2px 6px rgba(239,68,68,0.6)',
                'lineHeight': '20px',
            }),
            html.Button([
                html.I(className="fas fa-robot", style={'fontSize': '28px', 'color': 'white'}),
            ],
                id='chat-toggle-btn',
                style=CHAT_STYLES['button_toggle'],
                n_clicks=0,
                title="Asistente IA — alertas y análisis energético"
            ),
        ], style=CHAT_STYLES['button_wrapper']),

        # Contenedor del chat (inicialmente oculto)
        html.Div(
            id='chat-container',
            style={'display': 'none'},
            children=[
                # Header
                html.Div([
                    html.Div([
                        html.I(className="fas fa-brain", style={'marginRight': '10px', 'color': 'white'}),
                        html.Span("Analista Energético IA", style={'fontWeight': 'bold', 'fontSize': '1.1rem', 'color': 'white'})
                    ]),
                    html.Div([
                        html.Button(
                            html.I(className="fas fa-expand"),
                            id='chat-fullscreen-btn',
                            style={
                                'background': 'transparent',
                                'border': 'none',
                                'color': 'white',
                                'fontSize': '1.1rem',
                                'cursor': 'pointer',
                                'marginRight': '8px',
                                'padding': '4px 8px',
                                'transition': 'transform 0.2s'
                            },
                            n_clicks=0,
                            title="Pantalla completa"
                        ),
                        html.Button(
                            html.I(className="fas fa-minus"),
                            id='chat-minimize-btn',
                            style={
                                'background': 'transparent',
                                'border': 'none',
                                'color': 'white',
                                'fontSize': '1.1rem',
                                'cursor': 'pointer',
                                'marginRight': '8px',
                                'padding': '4px 8px',
                                'transition': 'transform 0.2s'
                            },
                            n_clicks=0,
                            title="Minimizar"
                        ),
                        html.Button(
                            html.I(className="fas fa-times"),
                            id='chat-close-btn',
                            style={
                                'background': 'transparent',
                                'border': 'none',
                                'color': 'white',
                                'fontSize': '1.2rem',
                                'cursor': 'pointer',
                                'padding': '4px 8px',
                                'transition': 'transform 0.2s'
                            },
                            n_clicks=0,
                            title="Cerrar"
                        )
                    ], style={'display': 'flex', 'alignItems': 'center'})
                ], style=CHAT_STYLES['header']),
                
                # Área de mensajes
                html.Div(
                    id='chat-messages',
                    style=CHAT_STYLES['messages'],
                    children=[
                        crear_mensaje_ia(
                            "¡Hola! Soy el Analista Energético IA del MME. "
                            "Puedo ayudarte con análisis del SIN, detección de anomalías, "
                            "proyecciones de demanda y más. ¿En qué puedo asistirte?"
                        )
                    ]
                ),
                
                # Loading indicator
                dcc.Loading(
                    id='chat-loading',
                    type='dot',
                    children=html.Div(id='chat-loading-output')
                ),
                
                # Área de input
                html.Div([
                    dbc.Input(
                        id='chat-input',
                        placeholder='Escribe tu pregunta aquí...',
                        type='text',
                        style={
                            'flex': '1',
                            'border': '1px solid #cbd5e1',
                            'borderRadius': '10px',
                            'padding': '10px 15px'
                        }
                    ),
                    dbc.Button(
                        html.I(className="fas fa-paper-plane", style={'color': 'white'}),
                        id='chat-send-btn',
                        color='primary',
                        style={'borderRadius': '10px', 'padding': '10px 20px'},
                        n_clicks=0
                    )
                ], style=CHAT_STYLES['input_area']),
                
                # Botones de acceso rápido
                html.Div([
                    dbc.ButtonGroup([
                        dbc.Button(
                            [html.I(className="fas fa-search-plus me-1"), "Análisis"],
                            id='chat-quick-analizar-tablero',
                            color='primary',
                            size='sm',
                            outline=True,
                            n_clicks=0,
                            title="Analiza la página que estás viendo"
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-bell me-1"), "Alertas"],
                            id='chat-quick-alertas',
                            color='danger',
                            size='sm',
                            outline=True,
                            n_clicks=0,
                            title="Ver alertas activas del sistema"
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-newspaper me-1"), "Noticias"],
                            id='chat-quick-noticias',
                            color='success',
                            size='sm',
                            outline=True,
                            n_clicks=0,
                            title="Noticias del sector eléctrico"
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-exclamation-triangle me-1"), "Anomalías"],
                            id='chat-quick-anomalias',
                            color='warning',
                            size='sm',
                            outline=True,
                            n_clicks=0
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-chart-line me-1"), "Resumen"],
                            id='chat-quick-resumen',
                            color='info',
                            size='sm',
                            outline=True,
                            n_clicks=0
                        )
                    ], size='sm', style={'flexWrap': 'wrap', 'gap': '5px'})
                ], style={'padding': '10px 15px', 'borderTop': '1px solid #e2e8f0'})
            ]
        )
    ])

def crear_mensaje_usuario(texto):
    """Crear burbuja de mensaje del usuario"""
    return html.Div([
        html.Div(texto, style={'marginBottom': '4px'}),
        html.Div(
            datetime.now().strftime("%H:%M"),
            style=CHAT_STYLES['timestamp']
        )
    ], style=CHAT_STYLES['user_message'])

def crear_mensaje_ia(texto, timestamp=None):
    """Crear burbuja de mensaje de la IA con soporte Markdown"""
    if timestamp is None:
        timestamp = datetime.now().strftime("%H:%M")
    
    return html.Div([
        html.Div([
            html.I(className="fas fa-robot", style={'marginRight': '8px', 'color': '#3b82f6'}),
            dcc.Markdown(
                texto,
                style={
                    'display': 'inline-block',
                    'width': '100%',
                    'lineHeight': '1.6',
                    'whiteSpace': 'pre-wrap'
                },
                dangerously_allow_html=False
            )
        ], style={'marginBottom': '4px'}),
        html.Div(
            timestamp,
            style=CHAT_STYLES['timestamp']
        )
    ], style=CHAT_STYLES['ai_message'])

# ========================================
# CALLBACKS
# ========================================

@callback(
    [Output('chat-container', 'style'),
     Output('chat-messages', 'children', allow_duplicate=True)],
    [Input('chat-toggle-btn', 'n_clicks'),
     Input('chat-close-btn', 'n_clicks')],
    [State('chat-container', 'style'),
     State('chat-messages', 'children')],
    prevent_initial_call=True
)
def toggle_chat(n_toggle, n_close, current_style, mensajes_actuales):
    """Mostrar/ocultar chat. En la primera apertura inyecta alertas activas como notificaciones."""
    if not current_style:
        current_style = {'display': 'none'}

    total_clicks = (n_toggle or 0) + (n_close or 0)

    if total_clicks % 2 == 1:
        mensajes = list(mensajes_actuales or [])
        # Primera apertura: cargar alertas activas como notificaciones
        if (n_toggle or 0) == 1 and not (n_close or 0):
            notifs = cargar_alertas_chatbot()
            if notifs:
                mensajes = notifs + mensajes
        return {**CHAT_STYLES['container'], 'display': 'flex'}, mensajes
    else:
        return {'display': 'none'}, mensajes_actuales or []

@callback(
    Output('chat-container', 'style', allow_duplicate=True),
    [Input('chat-minimize-btn', 'n_clicks'),
     Input('chat-fullscreen-btn', 'n_clicks')],
    [State('chat-container', 'style')],
    prevent_initial_call=True
)
def manejar_ventana(n_minimize, n_fullscreen, current_style):
    """Manejar minimizar y pantalla completa"""
    from dash import ctx
    
    if not ctx.triggered:
        return current_style
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'chat-minimize-btn':
        # Minimizar (solo mostrar header)
        return {
            **CHAT_STYLES['container'],
            'display': 'flex',
            'height': '60px',
            'maxHeight': '60px',
            'overflow': 'hidden'
        }
    elif trigger_id == 'chat-fullscreen-btn':
        # Pantalla completa
        return {
            **CHAT_STYLES['container'],
            'display': 'flex',
            'width': '90vw',
            'height': '90vh',
            'maxHeight': '90vh',
            'left': '5vw',
            'bottom': 'auto',
            'top': '5vh',
        }
    
    return current_style

@callback(
    [Output('chat-messages', 'children'),
     Output('chat-input', 'value'),
     Output('chat-loading-output', 'children')],
    [Input('chat-send-btn', 'n_clicks'),
     Input('chat-input', 'n_submit'),
     Input('chat-quick-analizar-tablero', 'n_clicks'),
     Input('chat-quick-anomalias', 'n_clicks'),
     Input('chat-quick-resumen', 'n_clicks'),
     Input('chat-quick-alertas', 'n_clicks'),
     Input('chat-quick-noticias', 'n_clicks')],
    [State('chat-input', 'value'),
     State('chat-messages', 'children'),
     State('url', 'pathname'),
     State('store-datos-chatbot-generacion', 'data')],  # Store con datos actualizados
    prevent_initial_call=True
)
def manejar_mensajes(n_send, n_submit, n_analizar, n_anomalias, n_resumen, n_alertas, n_noticias,
                     input_text, mensajes_actuales, current_pathname, datos_generacion_store):
    """
    Manejar envío de mensajes y respuestas del agente IA
    """
    from dash import ctx
    
    if not ctx.triggered:
        return mensajes_actuales, '', ''
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Determinar la pregunta según el trigger
    pregunta = None
    
    if trigger_id == 'chat-send-btn' or trigger_id == 'chat-input':
        if input_text and input_text.strip():
            pregunta = input_text.strip()
    elif trigger_id == 'chat-quick-analizar-tablero':
        # Analizar la página actual que el usuario está viendo
        pagina_info = {
            '/': 'Página de inicio',
            '/generacion': 'Generación Eléctrica',
            '/generacion-fuentes': 'Generación por Fuentes',
            '/generacion/hidraulica/hidrologia': 'Hidrología y Aportes Hídricos',
            '/demanda': 'Demanda Eléctrica',
            '/distribucion': 'Distribución',
            '/perdidas': 'Pérdidas de Energía',
            '/transmision': 'Transmisión',
            '/disponibilidad': 'Disponibilidad',
            '/restricciones': 'Restricciones Operativas'
        }
        pagina_actual = pagina_info.get(current_pathname, 'esta página')
        
        # Mensaje visible para el usuario (corto y limpio)
        pregunta_visible = f"🔍 Analizar tablero de {pagina_actual}"
        
        # Obtener datos del Store si hay datos disponibles (para cualquier página)
        if datos_generacion_store and datos_generacion_store.get('pagina'):
            # Usar datos del store si están disponibles y coinciden con la página actual
            datos_contexto = datos_generacion_store
            print(f"✅ Chatbot usando datos del STORE para página: {datos_generacion_store.get('pagina')}")
            print(f"   Datos disponibles: {list(datos_generacion_store.keys())}")
        else:
            # Si el store está vacío o no tiene datos, usar el método de consulta directa
            agente = get_agente()
            datos_contexto = agente.obtener_datos_contexto_pagina(current_pathname)
            print(f"⚠️ Chatbot usando consulta DIRECTA para: {current_pathname} (store vacío o sin datos)")
        
        # Pregunta completa con datos para la IA (no se muestra al usuario)
        pregunta = f"""Analiza profundamente el tablero de {pagina_actual} que estoy viendo. 

EXPLICA EN DETALLE:
1. 📊 **Fichas/KPIs**: Qué significan los valores mostrados y qué indican sobre el sistema
2. 📈 **Gráficas**: Qué tendencias y patrones se observan
3. 📋 **Tablas**: Qué información clave muestran los datos
4. 💡 **Implicaciones**: Cómo estos datos afectan el Costo Unitario (CU) y la tarifa de energía
5. ⚠️ **Alertas**: Identifica cualquier situación atípica o que requiera atención

DATOS DE LA PÁGINA ACTUAL:
{json.dumps(datos_contexto, indent=2, default=str, ensure_ascii=False)}"""
    elif trigger_id == 'chat-quick-anomalias':
        # Obtener datos del store o consulta directa
        if datos_generacion_store and datos_generacion_store.get('pagina'):
            datos_contexto = datos_generacion_store
            print(f"✅ Anomalías usando datos del STORE para: {datos_generacion_store.get('pagina')}")
        else:
            agente = get_agente()
            datos_contexto = agente.obtener_datos_contexto_pagina(current_pathname)
            print(f"⚠️ Anomalías usando consulta DIRECTA para: {current_pathname}")
        
        pregunta = f"""Detecta y analiza anomalías en los datos que estoy viendo actualmente.

Analiza estos datos y detecta:
1. ⚠️ Valores anormales o fuera de rango
2. 📉 Tendencias preocupantes
3. 🚨 Situaciones críticas que requieran atención

DATOS ACTUALES:
{json.dumps(datos_contexto, indent=2, default=str, ensure_ascii=False)}"""
        
    elif trigger_id == 'chat-quick-resumen':
        # Obtener datos del store o consulta directa
        if datos_generacion_store and datos_generacion_store.get('pagina'):
            datos_contexto = datos_generacion_store
            print(f"✅ Resumen usando datos del STORE para: {datos_generacion_store.get('pagina')}")
        else:
            agente = get_agente()
            datos_contexto = agente.obtener_datos_contexto_pagina(current_pathname)
            print(f"⚠️ Resumen usando consulta DIRECTA para: {current_pathname}")
        
        pregunta = f"""Dame un resumen ejecutivo de los datos que estoy viendo actualmente.

Incluye:
1. 📊 Indicadores clave (KPIs)
2. 📈 Estado general
3. 💡 Puntos importantes a destacar

DATOS ACTUALES:
{json.dumps(datos_contexto, indent=2, default=str, ensure_ascii=False)}"""
    elif trigger_id == 'chat-quick-alertas':
        # Mostrar alertas directamente como notificaciones (sin pasar por IA)
        mensajes = list(mensajes_actuales or [])
        mensajes.append(crear_mensaje_usuario("🔔 Ver alertas activas"))
        notifs = cargar_alertas_chatbot()
        if notifs:
            mensajes.extend(notifs)
        else:
            mensajes.append(crear_mensaje_ia("✅ Sin alertas críticas activas en las últimas 24 h. El sistema opera con normalidad."))
        return mensajes, '', ''
    elif trigger_id == 'chat-quick-noticias':
        # Mostrar noticias directamente desde el orquestador (sin pasar por IA)
        mensajes = list(mensajes_actuales or [])
        mensajes.append(crear_mensaje_usuario("📰 Últimas noticias del sector energético"))
        notifs = obtener_noticias_chatbot()
        mensajes.extend(notifs)
        return mensajes, '', ''
    
    if not pregunta:
        return mensajes_actuales, input_text or '', ''
    
    # Agregar mensaje del usuario
    # Para "Analizar tablero" mostrar versión corta, para otros mostrar la pregunta completa
    if trigger_id == 'chat-quick-analizar-tablero':
        mensaje_para_mostrar = pregunta_visible
    elif trigger_id == 'chat-quick-anomalias':
        mensaje_para_mostrar = "🚨 Detectar anomalías"
    elif trigger_id == 'chat-quick-resumen':
        mensaje_para_mostrar = "📊 Resumen ejecutivo"
    else:
        mensaje_para_mostrar = pregunta
    
    mensajes_actuales.append(crear_mensaje_usuario(mensaje_para_mostrar))
    
    try:
        # Obtener instancia del agente IA
        agente = get_agente()
        
        # Todos los botones ahora usan chat_interactivo con los datos del contexto
        respuesta_ia = agente.chat_interactivo(pregunta)
        
        # Agregar mensaje de la IA
        mensajes_actuales.append(crear_mensaje_ia(respuesta_ia))
        
    except Exception as e:
        logger.error(f"Error en chat IA: {e}")
        mensajes_actuales.append(
            crear_mensaje_ia(f"❌ Error procesando solicitud: {str(e)}")
        )
    
    return mensajes_actuales, '', ''

# ========================================
# FUNCIONES DE UTILIDAD
# ========================================

@callback(
    Output('chat-notif-badge', 'children'),
    Input('chat-notif-interval', 'n_intervals'),
)
def actualizar_badge_notif(n):
    """Actualiza el contador de alertas críticas activas en el badge del botón."""
    count = contar_alertas_recientes()
    return str(min(count, 99)) if count > 0 else ""


def obtener_estado_api():
    """Verificar si el agente IA está disponible"""
    try:
        agente = get_agente()
        return agente is not None
    except Exception as e:
        return False

def obtener_estadisticas_ia():
    """Obtener estadísticas del agente IA"""
    try:
        agente = get_agente()
        return {
            'estado': 'activo',
            'modelo': agente.modelo,
            'base_url': 'https://openrouter.ai/api/v1'
        }
    except Exception as e:
        return None

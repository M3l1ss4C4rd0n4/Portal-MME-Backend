import dash
from dash import html, dcc, Input, Output, State, callback
import logging
# from interface.components.layout import crear_navbar_horizontal

logger = logging.getLogger(__name__)

# Metadata para Dash Pages (auto-discovery)
dash.register_page(
    __name__,
    path="/",
    name="Inicio",
    title="Portal Energético",
    order=0
)

# Configuración de módulos con nuevos componentes PNG
# POSICIONES ESTRATÉGICAS: Sin tapar ilustraciones isométricas
MODULES = [
    {
        "id": "generacion", 
        "path": "/generacion", 
        "image": "portada_Boton generacion.png", 
        "left": "8%",    # Más alejado del centro, esquina izquierda
        "top": "75%",    # Muy abajo
        "width": "12.5%", 
        "title": "G — Generación", 
        "description": "Costo de producir/comprar la energía (contratos + bolsa). Es el componente más variable del CU.",
        "modal_description": "G refleja el precio promedio de la energía adquirida a generadores vía contratos bilaterales y bolsa del MEM (XM). Su dinámica depende de hidrología, combustibles y oferta/demanda; la CREG y XM reportan explícitamente la relación entre precios de bolsa/contratos y el componente G del CU.",
        "formula": "G = Σ(Eᵢ · Pᵢ) / Σ(Eᵢ)",
        "formula_description": "Precio promedio ponderado de la energía comprada; XM/CREG lo analizan como promedio entre contratos y bolsa."
    },
    {
        "id": "transmision", 
        "path": "/transmision", 
        "image": "portada_Boton transmision.png", 
        "left": "5%",    # Mucho más a la izquierda
        "top": "38%",    # Altura media-baja
        "width": "12.9%",
        "title": "T — Transmisión", 
        "description": "Peaje del STN (líneas de alta tensión). Cargo regulado y relativamente estable en $/kWh.",
        "modal_description": "T remunera los activos del Sistema de Transmisión Nacional (STN) y su operación. La SSPD y la CREG describen que es un cargo por uso regulado que XM incorpora al CU.",
        "formula": "T = C_uso_STN / E_entregada",
        "formula_description": "Costo total de transmisión por unidad de energía entregada; se publica como cargo unitario."
    },
    {
        "id": "distribucion", 
        "path": "/distribucion", 
        "image": "portada_Boton distribucion.png", 
        "left": "30%",   # Más a la izquierda, sin tapar edificios
        "top": "12%",    # Ajustado para no ser tapado por navbar
        "width": "13.1%",
        "title": "D — Distribución", 
        "description": "Peaje del SDL (redes locales: media/baja tensión). Cargo regulado por zona/nivel de tensión.",
        "modal_description": "D remunera redes locales (postes, transformadores, operación y expansión). La CREG define los cargos por uso del SDL y XM publica los cargos de distribución que alimentan el CU.",
        "formula": "D = C_SDL / E_entregada",
        "formula_description": "Cargo unitario de distribución aplicado al mercado/nivel de tensión."
    },
    {
        "id": "comercializacion", 
        "path": "/comercializacion", 
        "image": "portada_Boton comercializacion.png", 
        "left": "73%",   # Más a la derecha, encima de la plataforma
        "top": "15%",    # Ajustado para no ser tapado por navbar
        "width": "12.5%", 
        "title": "Cv — Comercialización", 
        "description": "Costo variable por kWh de gestión comercial (medición, facturación, atención). Definido en la fórmula tarifaria.",
        "modal_description": "El costo de comercialización tiene parte fija (Cf) y variable (Cv). Para el CU, XM utiliza el término variable regulado por CREG (fórmula tarifaria vigente), aplicado en $/kWh sobre la energía del usuario.",
        "formula": "C_comercialización = Cf + Cv · Eu",
        "formula_description": "En CU se incorpora (Cv) como cargo unitario."
    },
    {
        "id": "restricciones", 
        "path": "/restricciones", 
        "image": "portada_Boton restricciones.png", 
        "left": "42%",   # Centrado horizontal
        "top": "75%",    # Mucho más abajo, lejos del centro
        "width": "12.5%", 
        "title": "R — Restricciones", 
        "description": "Costo por congestiones/limitaciones de red que obligan al CND (XM) a redespachar generación más cara localmente.",
        "modal_description": "Cuando la red se congestiona o hay condiciones operativas, el CND (XM) realiza redespacho y se incurre en costos de restricciones. XM publica que el costo unitario de restricciones es la razón entre el costo total de restricciones y la generación real del sistema en el periodo.",
        "formula": "R = C_restricciones(periodo) / E_generación_real(periodo)",
        "formula_description": "Definición 'costo unitario de restricciones' publicada por XM."
    },
    {
        "id": "perdidas", 
        "path": "/perdidas", 
        "image": "portada_Boton perdidas.png", 
        "left": "78%",   # Ajustado más a la izquierda
        "top": "60%",    # Altura media-baja
        "width": "10.5%", # Más pequeño que los demás 
        "title": "PR — Pérdidas", 
        "description": "Energía adicional que se compra para cubrir pérdidas técnicas/no técnicas reconocidas por CREG. La metodología la aplica ASIC/XM.",
        "modal_description": "En redes hay pérdidas; la regulación reconoce un porcentaje (por mercado/nivel) que el ASIC (en XM) aplica para la liquidación. Esto se traduce en un cargo unitario en el CU asociado a comprar kWh extra para que al medidor llegue lo que el usuario consume.",
        "formula": "PR ≈ G · (1/(1-Lp) - 1)",
        "formula_description": "Si Lp es el porcentaje de pérdidas reconocidas, entonces la energía a comprar es Eu/(1-Lp). La aplicación y series oficiales de pérdidas son calculadas por el ASIC conforme a la CREG 015 de 2018."
    },
]

def layout():
    return html.Div([
        # Contenedor principal con padding para el navbar
        html.Div([
            # CAPA 1: Fondo base adaptable (sin animación)
            html.Img(
                src="/assets/portada_fondo.png",
                id="background-base",
                style={
                    "position": "fixed",
                    "top": "0",
                    "left": "0", 
                    "width": "100%",
                    "height": "100vh",
                    "objectFit": "cover",
                    "zIndex": "1",
                    "pointerEvents": "none"
                }
            ),
        
        # CAPA 2: Ilustración del sistema energético (CON flotación, SIN oscurecimiento)
        html.Img(
            src="/assets/portada_secciones.png",
            id="background-sections",
            className="floating-sections",
            style={
                "position": "fixed",
                "top": "calc(50% + 35px)",
                "left": "50%",
                "transform": "translate(-50%, -50%)",
                "width": "78%",    # Reducido para hacerla más pequeña
                "height": "80%",   # Reducido proporcionalmente
                "objectFit": "contain",
                "zIndex": "2",
                "pointerEvents": "none",
                "animation": "gentle-float 4s ease-in-out infinite"
            }
        ),
        
        # CAPA 3: Título cerca del centro (junto al botón ℹ)
        html.Img(
            src="/assets/portada_titulo.png",
            id="portada-titulo",
            style={
                "position": "fixed",
                "top": "calc(50% + 50px)",  # Bajado un poco más (de +35px a +50px)
                "left": "50%",
                "transform": "translate(-50%, -50%)",
                "width": "31.2%",  # 599/1920 = 31.2%
                "height": "auto",
                "zIndex": "5",
                "pointerEvents": "none"
            }
        ),
        
        # Logo "La Energía de Nuestra Gente" (259x111) - Esquina inferior derecha
        html.Img(
            src="/assets/portada_Logo de las manos.png",
            id="logo-manos",
            style={
                "position": "fixed",
                "bottom": "2%",   # Abajo
                "right": "2%",    # Derecha
                "width": "13.5%",  # 259/1920 = 13.5%
                "height": "auto",
                "zIndex": "5",
                "pointerEvents": "none"
            }
        ),

        # (Alertas críticas se muestran en el chatbot, no en banner)

        # ── FASE 3: Widget CU actual ────────────────────────
        html.Div(id="cu-kpi-home", style={
            "position": "fixed",
            "top": "85px",
            "right": "20px",
            "zIndex": "15",
            "pointerEvents": "auto",
        }),

        # ── FASE 4: Widget noticias KPI (carrusel auto-rotante, esquina superior izquierda) ──
        dcc.Store(id='store-noticias-kpi', data={'noticias': [], 'idx': 0}),
        dcc.Interval(id='interval-noticias-kpi', interval=7000, n_intervals=0),
        html.Div(id='noticias-kpi-widget', style={
            "position": "fixed",
            "top": "85px",
            "left": "10px",
            "zIndex": "15",
            "pointerEvents": "auto",
            "width": "210px",
        }),
        
        # CAPA 4: Botones interactivos (SOLO hover + tooltip, SIN flotación)
        *[
            html.A([
                html.Img(
                    src=f"/assets/{m['image']}",
                    className="button-module",
                    style={
                        "width": "100%", 
                        "height": "auto", 
                        "transition": "all 0.4s cubic-bezier(0.4, 0, 0.2, 1)",
                        "border": "none",
                        "outline": "none",
                        "background": "transparent",
                        "filter": "drop-shadow(0 4px 10px rgba(0, 0, 0, 0.3))"
                    }
                )
            ],
            href=m["path"],
            id=f"module-{m['id']}",
            className="custom-module",
            style={
                "position": "fixed",
                "left": m["left"],
                "top": m["top"], 
                "width": m["width"],
                "cursor": "pointer",
                "textDecoration": "none",
                "transition": "all 0.4s cubic-bezier(0.4, 0, 0.2, 1)",
                "zIndex": "10",
                "border": "none",
                "outline": "none",
                "background": "transparent"
            }
        ) for m in MODULES
        ],
        
        # Overlays oscuros para cada viñeta (fondo opaco cuando aparece la viñeta)
        *[
            html.Div(
                id=f"overlay-{m['id']}",
                style={
                    "position": "fixed",
                    "top": "0",
                    "left": "0",
                    "width": "100%",
                    "height": "100%",
                    "backgroundColor": "rgba(0,0,0,0.7)",
                    "opacity": "0",
                    "visibility": "hidden",
                    "zIndex": "199",  # Justo debajo de las viñetas (200)
                    "backdropFilter": "blur(5px)",
                    "pointerEvents": "none",
                    "transition": "all 0.4s cubic-bezier(0.68, -0.55, 0.265, 1.55)"
                }
            ) for m in MODULES
        ],
        
        # Viñetas centrales completas con toda la información detallada
        *[
            html.Div([
                html.Div([
                    html.H3(m['title'], style={
                        "color": "#ffffff", 
                        "marginBottom": "15px", 
                        "fontSize": "1.5rem", 
                        "fontWeight": "700",
                        "textAlign": "center",
                        "textShadow": "2px 2px 4px rgba(0,0,0,0.8)",
                        "borderBottom": "2px solid #ffc107",
                        "paddingBottom": "10px"
                    }),
                    
                    # Descripción corta
                    html.P(m['description'], style={
                        "color": "#ffffff", 
                        "margin": "0 0 15px 0", 
                        "fontSize": "0.95rem", 
                        "lineHeight": "1.6",
                        "textAlign": "justify",
                        "textShadow": "1px 1px 3px rgba(0,0,0,0.8)",
                        "fontWeight": "500"
                    }),
                    
                    html.Hr(style={"margin": "15px 0", "border": "none", "borderTop": "1px solid rgba(255,193,7,0.3)"}),
                    
                    # Descripción técnica ampliada
                    html.Div([
                        html.P([html.Strong("Descripción técnica:", style={"color": "#ffc107"})], 
                               style={"marginBottom": "8px", "fontSize": "0.85rem"}),
                        html.P(m.get('modal_description', ''), style={
                            "color": "#e0e0e0", 
                            "margin": "0 0 12px 0", 
                            "fontSize": "0.8rem", 
                            "lineHeight": "1.5",
                            "textAlign": "justify",
                            "textShadow": "1px 1px 2px rgba(0,0,0,0.7)"
                        })
                    ]),
                    
                    html.Hr(style={"margin": "15px 0", "border": "none", "borderTop": "1px solid rgba(255,193,7,0.3)"}),
                    
                    # Fórmula
                    html.Div([
                        html.P([html.Strong("Fórmula:", style={"color": "#ffc107"})], 
                               style={"marginBottom": "8px", "fontSize": "0.85rem"}),
                        html.Code(m.get('formula', 'No disponible'), style={
                            "display": "block",
                            "padding": "10px",
                            "backgroundColor": "rgba(255,255,255,0.15)",
                            "borderLeft": "3px solid #ffc107",
                            "marginBottom": "8px",
                            "fontSize": "0.85rem",
                            "borderRadius": "5px",
                            "fontFamily": "monospace",
                            "color": "#ffd54f",
                            "textShadow": "1px 1px 2px rgba(0,0,0,0.8)"
                        }),
                        html.P(m.get('formula_description', ''), style={
                            "color": "#d0d0d0", 
                            "fontSize": "0.75rem", 
                            "fontStyle": "italic", 
                            "margin": "0",
                            "lineHeight": "1.4",
                            "textShadow": "1px 1px 2px rgba(0,0,0,0.7)"
                        })
                    ]),
                    
                    html.Hr(style={"margin": "15px 0", "border": "none", "borderTop": "1px solid rgba(255,193,7,0.3)"}),
                    
                    html.P("✨ Haz clic para explorar el sector completo", style={
                        "color": "#ffc107",
                        "fontSize": "0.85rem",
                        "fontWeight": "600",
                        "fontStyle": "italic",
                        "margin": "0",
                        "textAlign": "center",
                        "opacity": "0.95",
                        "textShadow": "1px 1px 2px rgba(0,0,0,0.8)"
                    })
                ])
            ], 
            id=f"tooltip-{m['id']}",
            style={
                "position": "fixed",
                "top": "50%",
                "left": "50%",
                "transform": "translate(-50%, -50%) scale(0.9)",
                "background": "linear-gradient(135deg, rgba(0,0,0,0.95), rgba(20,30,50,0.95))",
                "padding": "25px 28px",
                "borderRadius": "18px",
                "minWidth": "380px",
                "maxWidth": "480px",
                "maxHeight": "85vh",
                "overflowY": "auto",
                "opacity": "0",
                "visibility": "hidden",
                "zIndex": "200",
                "boxShadow": "0 20px 60px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,193,7,0.5)",
                "border": "2px solid rgba(255,193,7,0.7)",
                "backdropFilter": "blur(20px)",
                "pointerEvents": "none",
                "transition": "all 0.4s cubic-bezier(0.68, -0.55, 0.265, 1.55)"
            }) for m in MODULES
        ],
        
        # Botón ℹ al lado derecho de la letra R en "EnergÉtico"
        html.Div([
            html.Button(
                "ℹ",
                id="info-button",
                style={
                    "position": "fixed",
                    "top": "41%",     # Mucho más arriba, a la altura de la R
                    "left": "59%",    # Al lado de la R en "Energético"
                    "transform": "translate(-50%, -50%)",
                    "width": "50px",  # Más pequeño
                    "height": "50px",
                    "borderRadius": "50%",
                    "backgroundColor": "#F2C330",
                    "color": "#2C3E50",
                    "fontSize": "28px",  # Fuente más pequeña
                    "fontWeight": "bold",
                    "border": "3px solid #2C3E50",
                    "cursor": "pointer",
                    "zIndex": "20",  # Por encima de botones (10) pero bajo tooltips (200)
                    "boxShadow": "0 8px 24px rgba(0,0,0,0.5), 0 0 0 3px rgba(242,195,48,0.4)",
                    "transition": "all 0.3s ease",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "animation": "pulse 2s ease-in-out infinite"
                },
                title="Clic para ver información sobre el Costo Unitario (CU)"
            )
        ]),
        
        # Modal de información sobre ecuación de costo unitario
        html.Div([
            html.Div([
                html.Div([
                    html.H3("¿Qué es el Costo Unitario (CU)?", style={
                        "color": "#F2C330",
                        "marginBottom": "15px",
                        "textAlign": "center",
                        "fontWeight": "600",
                        "fontSize": "20px"
                    }),
                    html.Div([
                        html.H4("CU = G + T + D + Cv + PR + R", style={
                            "color": "#1E3A8A",
                            "textAlign": "center",
                            "fontSize": "22px",
                            "fontWeight": "bold",
                            "marginBottom": "15px",
                            "padding": "12px",
                            "backgroundColor": "#F8F9FA",
                            "borderRadius": "8px",
                            "border": "2px solid #F2C330"
                        })
                    ]),
                    html.P([
                        "Es el ", html.Strong("valor por kWh"), " que paga el usuario regulado por la energía entregada, calculado con la ",
                        html.Strong("metodología de la CREG"), " e implementado/publicado por XM."
                    ], style={"marginBottom": "15px", "fontSize": "14px", "lineHeight": "1.6", "color": "#333"}),
                    
                    html.Hr(style={"margin": "20px 0", "border": "none", "borderTop": "1px solid #ddd"}),
                    
                    html.H5("Descripción ampliada:", style={"color": "#1E3A8A", "marginBottom": "10px", "fontSize": "16px"}),
                    html.P([
                        "El ", html.Strong("Costo Unitario de prestación del servicio (CU)"), " agrega, en $/kWh, los costos de ",
                        html.Strong("Generación (G)"), ", ", html.Strong("Transmisión (T)"), ", ", html.Strong("Distribución (D)"), ", ",
                        html.Strong("Comercialización variable (Cv)"), ", ", html.Strong("Pérdidas reconocidas (PR)"), " y ",
                        html.Strong("Restricciones (R)"), ". XM publica series de CU por periodo, mercado y nivel de tensión bajo la metodología ",
                        html.Strong("CREG 119 de 2007"), " (con desarrollos posteriores y opción tarifaria cuando aplica)."
                    ], style={"marginBottom": "15px", "fontSize": "13px", "lineHeight": "1.6", "color": "#555"}),
                    
                    html.Hr(style={"margin": "20px 0", "border": "none", "borderTop": "1px solid #ddd"}),
                    
                    html.H5("Relación básica:", style={"color": "#1E3A8A", "marginBottom": "10px", "fontSize": "16px"}),
                    html.Div([
                        html.Code("CU = G + T + D + Cv + PR + R", style={
                            "display": "block",
                            "padding": "8px",
                            "backgroundColor": "#f5f5f5",
                            "borderLeft": "3px solid #F2C330",
                            "marginBottom": "8px",
                            "fontSize": "13px"
                        }),
                        html.Code("Factura (energía) = CU × kWh del usuario", style={
                            "display": "block",
                            "padding": "8px",
                            "backgroundColor": "#f5f5f5",
                            "borderLeft": "3px solid #F2C330",
                            "fontSize": "13px"
                        })
                    ], style={"marginBottom": "15px"}),
                    
                    html.Hr(style={"margin": "20px 0", "border": "none", "borderTop": "1px solid #ddd"}),
                    
                    html.Div([
                        html.P([html.Strong("G:"), " Generación - Costo de producir/comprar la energía"], style={"marginBottom": "6px", "fontSize": "13px"}),
                        html.P([html.Strong("T:"), " Transmisión - Peaje del STN (líneas de alta tensión)"], style={"marginBottom": "6px", "fontSize": "13px"}),
                        html.P([html.Strong("D:"), " Distribución - Peaje del SDL (redes locales)"], style={"marginBottom": "6px", "fontSize": "13px"}),
                        html.P([html.Strong("Cv:"), " Comercialización - Costo variable por kWh"], style={"marginBottom": "6px", "fontSize": "13px"}),
                        html.P([html.Strong("PR:"), " Pérdidas Reconocidas - Energía adicional para cubrir pérdidas"], style={"marginBottom": "6px", "fontSize": "13px"}),
                        html.P([html.Strong("R:"), " Restricciones - Costo por redespacho operativo"], style={"marginBottom": "6px", "fontSize": "13px"})
                    ], style={
                        "color": "#333333",
                        "lineHeight": "1.5",
                        "marginBottom": "15px"
                    }),
                    
                    html.P([
                        html.Em("Nota: "),
                        "El CU calculado/aplicado y su evolución se documentan en informes CREG/SSPD. ",
                        "Haz clic en cada sector del mapa para ver detalles específicos y fórmulas de cada componente."
                    ], style={"fontSize": "12px", "color": "#666", "fontStyle": "italic", "marginBottom": "15px"}),
                    
                    html.Button(
                        "Cerrar",
                        id="close-info-button",
                        style={
                            "backgroundColor": "#F2C330",
                            "color": "#FFFFFF",
                            "border": "none",
                            "padding": "10px 20px",
                            "borderRadius": "5px",
                            "cursor": "pointer",
                            "fontSize": "14px",
                            "fontWeight": "bold",
                            "marginTop": "10px",
                            "width": "100%"
                        }
                    )
                ], style={
                    "backgroundColor": "#FFFFFF",
                    "padding": "30px",
                    "borderRadius": "15px",
                    "boxShadow": "0 20px 60px rgba(0,0,0,0.3)",
                    "maxWidth": "500px",
                    "width": "90%",
                    "maxHeight": "80vh",
                    "overflowY": "auto"
                })
            ], style={
                "position": "fixed",
                "top": "0",
                "left": "0",
                "width": "100%",
                "height": "100%",
                "backgroundColor": "rgba(0,0,0,0.7)",
                "display": "none",  # Inicialmente oculto
                "alignItems": "center",
                "justifyContent": "center",
                "zIndex": "1000",
                "backdropFilter": "blur(5px)"
            })
        ], id="info-modal"),
        
        # SOLUCIÓN SIMPLE: Crear las animaciones con estilos inline
        html.Div(id="custom-styles", style={"display": "none"}),
        
        # SOLUCIÓN SIMPLE: JavaScript básico sin conflictos
        html.Div(id="hover-handler", style={"display": "none"}),
        
        # CHAT IA - Agente Analista Energético (flotante en esquina inferior derecha)
        html.Div(id="chat-ia-container", children=[])
        
        ], style={
            "position": "relative",
            "paddingTop": "0",  # El navbar es fixed, no necesita padding aquí
            "zIndex": "0"
        })
    ], id="page-background", style={
        "width": "100%",
        "height": "100vh", 
        "overflow": "visible",  # Cambiar a visible para que el sidebar se vea
        "background": "#FCF3D6",  # Color EXACTO del fondo del SVG extraído del archivo
        "transition": "background 0.6s ease"  # Transición para sincronizar con SVG
    })

# ========================================
# CALLBACK: Cargar Chat IA dinámicamente
# ========================================
# El chat ahora es global en app_factory, no se necesita aquí.
# Se mantiene el contenedor por compatibilidad si existe en el layout, pero vacío.
@callback(
    Output('chat-ia-container', 'children'),
    Input('page-background', 'id')
)
def cargar_chat_ia(_):
    return html.Div()


# ========================================
# FASE 3: CU KPI en Home
# ========================================
@callback(
    Output('cu-kpi-home', 'children'),
    Input('page-background', 'id'),
)
def cargar_cu_kpi(_):
    """
    Muestra el CU mayorista y el CU minorista promedio en badges flotantes.
    Falla silenciosamente si no hay datos.
    """
    try:
        from domain.services.cu_service import CUService
        from domain.services.cu_minorista_service import CUMinoristaService
        cu_service = CUService()
        cu_min_service = CUMinoristaService()

        cu = cu_service.get_cu_current()
        if cu is None:
            return html.Div()

        cu_total = cu.get("cu_total", 0)
        fecha_cu = cu.get("fecha", "")
        confianza = cu.get("confianza", "baja")

        # Color según confianza
        badge_bg_mayor = "#C0392B" if confianza == "alta" else (
            "#E67E22" if confianza == "media" else "#E74C3C"
        )

        # Variación mayorista vs día anterior
        variacion_text = ""
        try:
            from datetime import timedelta
            if fecha_cu:
                if isinstance(fecha_cu, str):
                    import datetime as dt_mod
                    fecha_obj = dt_mod.datetime.strptime(str(fecha_cu), "%Y-%m-%d").date()
                else:
                    fecha_obj = fecha_cu
                cu_prev = cu_service.calculate_cu_for_date(fecha_obj - timedelta(days=1))
                if cu_prev and cu_prev.get("cu_total"):
                    diff = cu_total - cu_prev["cu_total"]
                    pct = (diff / cu_prev["cu_total"]) * 100 if cu_prev["cu_total"] != 0 else 0
                    arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "")
                    variacion_text = f" {arrow}{pct:+.1f}%"
        except Exception:
            pass

        # CU minorista promedio nacional
        cu_min_prom = None
        try:
            info_min = cu_min_service.get_promedio_nacional_minorista()
            if info_min:
                cu_min_prom = info_min.get('cu_minorista_promedio')
        except Exception:
            pass

        # Badge mayorista (LAC)
        badge_mayor = html.A([
            html.Div([
                html.Div([
                    html.I(className="fas fa-industry", style={"fontSize": "0.65rem", "marginRight": "4px"}),
                    html.Span("CU MAYORISTA LAC", style={"fontSize": "0.6rem", "fontWeight": "700", "letterSpacing": "0.4px"}),
                ], style={"color": "rgba(255,255,255,0.85)", "marginBottom": "3px"}),
                html.Span(f"{cu_total:,.1f}", style={
                    "fontSize": "1.4rem", "fontWeight": "bold", "color": "#FFFFFF",
                }),
                html.Span(" COP/kWh", style={"fontSize": "0.6rem", "color": "rgba(255,255,255,0.7)"}),
                html.Div(variacion_text, style={
                    "fontSize": "0.65rem", "color": "#FFE082",
                    "display": "block" if variacion_text else "none",
                }),
                html.Div(str(fecha_cu)[:10], style={"fontSize": "0.5rem", "color": "rgba(255,255,255,0.55)", "marginTop": "2px"}),
            ], style={
                "background": f"linear-gradient(135deg, {badge_bg_mayor} 0%, #2C3E50 100%)",
                "padding": "8px 14px", "borderRadius": "10px",
                "boxShadow": "0 6px 20px rgba(0,0,0,0.35)",
                "textAlign": "center", "minWidth": "145px",
                "border": f"2px solid {badge_bg_mayor}",
            }),
        ], href="/costo-unitario", style={"textDecoration": "none", "display": "block", "marginBottom": "6px"})

        # Badge minorista (usuario final)
        if cu_min_prom is not None:
            badge_min = html.A([
                html.Div([
                    html.Div([
                        html.I(className="fas fa-home", style={"fontSize": "0.65rem", "marginRight": "4px"}),
                        html.Span("CU USUARIO FINAL", style={"fontSize": "0.6rem", "fontWeight": "700", "letterSpacing": "0.4px"}),
                    ], style={"color": "rgba(255,255,255,0.85)", "marginBottom": "3px"}),
                    html.Span(f"{cu_min_prom:,.1f}", style={
                        "fontSize": "1.4rem", "fontWeight": "bold", "color": "#FFFFFF",
                    }),
                    html.Span(" COP/kWh", style={"fontSize": "0.6rem", "color": "rgba(255,255,255,0.7)"}),
                    html.Div("Promedio 20 distribuidoras", style={
                        "fontSize": "0.5rem", "color": "rgba(255,255,255,0.55)", "marginTop": "2px",
                    }),
                ], style={
                    "background": "linear-gradient(135deg, #1565C0 0%, #0D47A1 100%)",
                    "padding": "8px 14px", "borderRadius": "10px",
                    "boxShadow": "0 6px 20px rgba(0,0,0,0.35)",
                    "textAlign": "center", "minWidth": "145px",
                    "border": "2px solid #1976D2",
                }),
            ], href="/costo-usuario-final", style={"textDecoration": "none", "display": "block"})
        else:
            badge_min = html.Div()

        return html.Div([badge_mayor, badge_min])

    except Exception as e:
        logger.debug("CU KPI home no disponible: %s", e)
        return html.Div()



        ICON_MAP = {
            'BALANCE_ENERGETICO': '⚖️',
            'DEMANDA': '📈',
            'EMBALSES': '💧',
            'PRECIO_MERCADO': '💰',
            'DATOS_CONGELADOS': '🧊',
        }

        banners = []
        for metrica, severidad, descripcion, fecha in rows:
            icon = ICON_MAP.get(metrica, '🚨')
            fecha_str = fecha.strftime('%d/%m %H:%M') if fecha else ''
            banners.append(
                html.Div([
                    html.Span(f"{icon} ", style={"fontSize": "1.1rem"}),
                    html.Strong(f"[{metrica}] ", style={"color": "#7f1d1d"}),
                    html.Span(descripcion, style={"color": "#1c1917"}),
                    html.Span(f"  ·  {fecha_str}", style={
                        "color": "#78716c", "fontSize": "0.8rem", "marginLeft": "8px"
                    }),
                ], style={
                    "background": "linear-gradient(90deg, #fef2f2 0%, #fff7ed 100%)",
                    "border": "2px solid #ef4444",
                    "borderLeft": "6px solid #b91c1c",
                    "borderRadius": "8px",
                    "padding": "10px 16px",
                    "marginBottom": "6px",
                    "fontSize": "0.9rem",
                    "boxShadow": "0 4px 12px rgba(185,28,28,0.2)",
                    "backdropFilter": "blur(4px)",
                })
            )

        return html.Div(banners)

    except Exception as e:
        logger.warning("Banner alertas no disponible: %s", e)
        return html.Div()


# ========================================
# FASE 4: Noticias KPI (carrusel auto-rotante)
# ========================================

@callback(
    Output('store-noticias-kpi', 'data'),
    Input('page-background', 'id'),
)
def cargar_noticias_kpi(_):
    """Carga las noticias del sector desde el orquestador y las guarda en el store."""
    try:
        import requests as req
        try:
            from core.config import settings as _s
            _api_key = _s.API_KEY
        except Exception:
            import os
            _api_key = os.getenv('API_KEY', 'mme-portal-energetico-2026-secret-key')
        resp = req.post(
            'http://localhost:8000/v1/chatbot/orchestrator',
            json={'sessionId': 'home_noticias_kpi', 'intent': 'noticias_sector', 'parameters': {}},
            headers={'Content-Type': 'application/json', 'X-API-Key': _api_key},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json().get('data', {})
        noticias = data.get('noticias', [])
        return {'noticias': noticias}
    except Exception as e:
        logger.warning("No se pudieron cargar noticias KPI: %s", e)
        return {'noticias': []}


@callback(
    Output('noticias-kpi-widget', 'children'),
    Input('interval-noticias-kpi', 'n_intervals'),
    Input('store-noticias-kpi', 'data'),
)
def renderizar_noticia_kpi(n_intervals, store):
    """Renderiza la tarjeta de noticia actual según el intervalo de rotación.
    Se dispara tanto en cada tick del intervalo como inmediatamente cuando el
    store se puebla al cargar la página."""
    noticias = (store or {}).get('noticias', [])
    if not noticias:
        return html.Div()

    idx = (n_intervals or 0) % len(noticias)
    n = noticias[idx]

    titulo = n.get('titulo', 'Sin título')
    fuente = n.get('fuente', '')
    fecha = str(n.get('fecha', ''))[:10]
    url = n.get('url', '')

    # Indicadores de posición (puntos)
    dots = html.Div(
        [
            html.Span(style={
                "display": "inline-block",
                "width": "6px", "height": "6px",
                "borderRadius": "50%",
                "backgroundColor": "#FFFFFF" if i == idx else "rgba(255,255,255,0.35)",
                "margin": "0 3px",
                "transition": "background 0.3s",
            })
            for i in range(len(noticias))
        ],
        style={"textAlign": "center", "marginTop": "8px"},
    )

    card_content = [
        # Header
        html.Div([
            html.I(className="fas fa-newspaper", style={"fontSize": "0.6rem", "marginRight": "4px"}),
            html.Span("NOTICIAS SECTOR", style={
                "fontSize": "0.58rem", "fontWeight": "700", "letterSpacing": "0.5px",
            }),
        ], style={"color": "rgba(255,255,255,0.8)", "marginBottom": "8px"}),

        # Título (clicable si hay url)
        (
            html.A(titulo, href=url, target="_blank", style={
                "fontSize": "0.78rem", "fontWeight": "600", "color": "#FFFFFF",
                "lineHeight": "1.35", "display": "block",
                "overflow": "hidden", "display": "-webkit-box",
                "WebkitLineClamp": "3", "WebkitBoxOrient": "vertical",
                "textDecoration": "none",
            })
            if url else
            html.Span(titulo, style={
                "fontSize": "0.78rem", "fontWeight": "600", "color": "#FFFFFF",
                "lineHeight": "1.35", "display": "block",
            })
        ),

        # Fuente + fecha
        html.Div(
            " · ".join(filter(None, [fuente, fecha])),
            style={"fontSize": "0.6rem", "color": "rgba(255,255,255,0.55)", "marginTop": "6px"},
        ),

        # Puntos indicadores
        dots,
    ]

    return html.Div(
        card_content,
        style={
            "background": "linear-gradient(135deg, #1a3a6b 0%, #0f2444 100%)",
            "padding": "10px 12px",
            "borderRadius": "10px",
            "boxShadow": "0 6px 20px rgba(0,0,0,0.4)",
            "minWidth": "190px",
            "maxWidth": "210px",
            "border": "1px solid rgba(255,255,255,0.12)",
            "cursor": "pointer" if url else "default",
        },
    )

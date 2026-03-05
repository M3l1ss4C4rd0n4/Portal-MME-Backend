from dash import html, dcc
import dash_bootstrap_components as dbc

def crear_header_restaurado():
    """
    Encabezado global Portal Energético MME — estilo Tabler-MME.
    
    Características:
    - Logo oficial del Ministerio
    - Navegación con estados activos (callback en app_factory)
    - Estilo corporativo integrado con el design system Tabler-MME
    """

    nav_link_style = {
        "color": "rgba(255,255,255,0.85)",
        "fontWeight": "500",
        "fontSize": "13px",
        "padding": "6px 14px",
        "borderRadius": "6px",
        "transition": "all 0.2s ease",
        "letterSpacing": "-0.2px",
    }

    brand_component = html.Div([
        html.Img(
            src="/assets/images/logo-minenergia.png",
            height="44px",
            className="d-inline-block align-top me-3",
            style={"filter": "brightness(1.05)"}
        ),
        html.Div([
            html.Span("Portal Energético", style={
                "fontSize": "15px", "fontWeight": "700", "color": "#fff",
                "letterSpacing": "-0.3px", "lineHeight": "1.2", "display": "block"
            }),
            html.Span("Ministerio de Minas y Energía", style={
                "fontSize": "11px", "color": "rgba(255,255,255,0.6)",
                "fontWeight": "400", "display": "block"
            })
        ], className="d-flex flex-column justify-content-center")
    ], className="d-flex align-items-center")

    return html.Div([
        dcc.Location(id="url-navbar", refresh=False),

        dbc.NavbarSimple(
            children=[
                dbc.NavLink("Inicio", href="/", id="nav-link-inicio", style=nav_link_style),
                dbc.NavLink("Generación", href="/generacion", id="nav-link-generacion", style=nav_link_style),
                dbc.NavLink("Transmisión", href="/transmision", id="nav-link-transmision", style=nav_link_style),
                dbc.NavLink("Distribución", href="/distribucion", id="nav-link-distribucion", style=nav_link_style),
                dbc.NavLink("Comercialización", href="/comercializacion", id="nav-link-comercializacion", style=nav_link_style),
                dbc.NavLink("Pérdidas", href="/perdidas", id="nav-link-perdidas", style=nav_link_style),
                dbc.NavLink("Costo Unitario", href="/costo-unitario", id="nav-link-costo-unitario", style=nav_link_style),
                dbc.NavLink("Simulación", href="/simulacion-creg", id="nav-link-simulacion-creg", style=nav_link_style),
                dbc.NavLink("Pérdidas NT", href="/perdidas-nt", id="nav-link-perdidas-nt", style=nav_link_style),
                dbc.NavLink("Restricciones", href="/restricciones", id="nav-link-restricciones", style=nav_link_style),
                dbc.NavLink("Métricas", href="/metricas", id="nav-link-metricas", style=nav_link_style),
            ],
            brand=brand_component,
            brand_href="/",
            color="#1e3a8a",
            dark=True,
            fluid=True,
            fixed="top",
            className="t-global-navbar",
            style={
                "background": "linear-gradient(90deg, #1e3a8a 0%, #152e6b 100%)",
                "borderBottom": "2px solid rgba(245,158,11,0.7)",
                "padding": "4px 0",
                "zIndex": "1030",
                "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
            }
        )
    ])

from dash import html, dcc
import dash_bootstrap_components as dbc

def crear_header_restaurado():
    """
    Crea el componente de encabezado restaurado del Portal Energético MME.
    
    Características:
    - Logo oficial del Ministerio
    - Navegación completa con estados activos
    - Elementos dinámicos y estilos corporativos
    - Integración con callbacks existentes (ids compatibility)
    """
    
    # Definición de estilos inline para garantizar la apariencia sin depender solo del CSS externo
    nav_link_style = {
        "color": "white",
        "fontWeight": "500",
        "marginRight": "5px",
        "transition": "all 0.3s ease",
        "borderRadius": "4px",
        "padding": "8px 15px"
    }

    # Brand Component (Logo + Títulos)
    brand_component = html.Div([
        html.Img(
            src="/assets/images/logo-minenergia.png",
            height="55px",
            className="d-inline-block align-top me-3 animate-fade-in"
        ),
        html.Div([
            html.H3("Portal Energético", className="mb-0 text-white", style={"fontSize": "1.4rem", "fontWeight": "700", "lineHeight": "1.2"}),
            html.Small("Ministerio de Minas y Energía", className="text-white-50", style={"fontSize": "0.85rem"})
        ], className="d-flex flex-column justify-content-center")
    ], className="d-flex align-items-center hover-scale")

    return html.Div([
        # Location para tracking de navegación específico del navbar (para callbacks existentes)
        dcc.Location(id="url-navbar", refresh=False),
        
        dbc.NavbarSimple(
            children=[
                dbc.NavLink("Inicio", href="/", id="nav-link-inicio", className="navbar-link", style=nav_link_style),
                dbc.NavLink("Generación", href="/generacion", id="nav-link-generacion", className="navbar-link", style=nav_link_style),
                dbc.NavLink("Transmisión", href="/transmision", id="nav-link-transmision", className="navbar-link", style=nav_link_style),
                dbc.NavLink("Distribución", href="/distribucion", id="nav-link-distribucion", className="navbar-link", style=nav_link_style),
                dbc.NavLink("Comercialización", href="/comercializacion", id="nav-link-comercializacion", className="navbar-link", style=nav_link_style),
                dbc.NavLink("Pérdidas", href="/perdidas", id="nav-link-perdidas", className="navbar-link", style=nav_link_style),
                dbc.NavLink("Restricciones", href="/restricciones", id="nav-link-restricciones", className="navbar-link", style=nav_link_style),
                dbc.NavLink("Métricas", href="/metricas", id="nav-link-metricas", className="navbar-link", style=nav_link_style),
                
                # Elemento dinámico: Botón de Ayuda/Info
                dbc.NavItem(
                    html.Button(
                        html.I(className="fas fa-question-circle"),
                        id="btn-info-header",
                        className="btn btn-link text-white ms-2 animate-pulse",
                        title="Información del Portal",
                        style={"fontSize": "1.2rem", "opacity": "0.9", "textDecoration": "none"}
                    )
                )
            ],
            brand=brand_component,
            brand_href="/",
            color="#1e3a8a", # Color corporativo MME Primary
            dark=True,
            fluid=True,
            fixed="top",  # FIJO EN EL TOP
            className="shadow-lg", 
            style={
                "background": "linear-gradient(90deg, #1e3a8a 0%, #0f172a 100%)", 
                "borderBottom": "3px solid #f59e0b", # Borde dorado corporativo
                "paddingTop": "0.5rem", 
                "paddingBottom": "0.5rem",
                "zIndex": "1030" # Bootstrap default is 1030 but being explicit is good
            }
        )
    ])

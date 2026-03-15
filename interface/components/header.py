from dash import html, dcc, clientside_callback, Input, Output, State
import dash_bootstrap_components as dbc

_GOVCO_GOLD = "#F5A623"
_NAVY       = "#1e3a8a"
_NAVY_DARK  = "#152e6b"

def crear_header_restaurado():
    """
    Header con navegación, toggle de tema e iconos de alta calidad.
    """
    return html.Div([
        dcc.Location(id="url-navbar", refresh=False),

        # ── Navbar principal ──────────────────────────────────────────────
        dbc.Navbar(
            dbc.Container(
                [
                    # ── Toggler móvil ──────────────────────────────────────
                    dbc.NavbarToggler(id="navbar-toggler", n_clicks=0),

                    # ── Logo MME ─────────────────────────────────────────
                    dbc.NavbarBrand(
                        html.Img(
                            src="/assets/images/logo-minenergia.png",
                            style={
                                "height": "78px",
                                "width": "auto",
                                "display": "block",
                                "filter": "drop-shadow(0 1px 4px rgba(0,0,0,0.5))",
                            },
                        ),
                        href="/",
                        style={"padding": "4px 0", "marginLeft": "28px", "marginRight": "20px"},
                    ),

                    # ── Links de navegación ────────────────────────────────
                    dbc.Collapse(
                        dbc.Nav(
                            [
                                dbc.NavItem(dbc.NavLink("Inicio",            href="/",                             id="nav-link-inicio",                        active="exact")),
                                dbc.NavItem(dbc.NavLink("Generación",        href="/generacion",                   id="nav-link-generacion",                    active="exact")),
                                dbc.NavItem(dbc.NavLink("Transmisión",       href="/transmision",                  id="nav-link-transmision",                   active="exact")),
                                dbc.NavItem(dbc.NavLink("Distribución",      href="/distribucion",                 id="nav-link-distribucion",                  active="exact")),
                                dbc.NavItem(dbc.NavLink("Comercialización",  href="/comercializacion",             id="nav-link-comercializacion",              active="exact")),
                                dbc.NavItem(dbc.NavLink("Pérdidas",          href="/perdidas",                     id="nav-link-perdidas",                      active="exact")),
                                dbc.NavItem(dbc.NavLink("Pérdidas NT",       href="/perdidas-nt",                  id="nav-link-perdidas-nt",                   active="exact")),
                                dbc.NavItem(dbc.NavLink("Restricciones",     href="/restricciones",                id="nav-link-restricciones",                 active="exact")),
                                dbc.NavItem(dbc.NavLink("Costo Unitario",    href="/costo-unitario",               id="nav-link-costo-unitario",                active="partial")),
                                dbc.NavItem(dbc.NavLink("CU Usuario",        href="/costo-usuario-final",          id="nav-link-cu-usuario",                    active="partial")),
                                dbc.NavItem(dbc.NavLink("Predicciones",      href="/seguimiento-predicciones",     id="nav-link-seguimiento-predicciones",      active="exact")),
                                
                                # Icono de Inversiones (Font Awesome)
                                dbc.NavItem(
                                    dbc.NavLink(
                                        [html.I(className="fa-solid fa-lightbulb me-2"), "Inversiones"], 
                                        href="/inversiones", 
                                        id="nav-link-inversiones", 
                                        active="exact"
                                    )
                                ),
                                
                                # Icono de Base de Datos (Font Awesome)
                                dbc.NavItem(
                                    dbc.NavLink(
                                        [html.I(className="fa-solid fa-database me-2"), "Base de Datos"], 
                                        href="/metricas", 
                                        id="nav-link-metricas", 
                                        active="exact"
                                    )
                                ),

                                # Toggle claro/oscuro
                                dbc.NavItem(
                                    html.Div([
                                        html.Span("☀", style={"fontSize": "11px", "color": "rgba(255,255,255,0.7)", "marginRight": "3px"}),
                                        dbc.Switch(
                                            id="theme-switch",
                                            value=False,
                                            persistence=True,
                                            persistence_type="local",
                                            className="d-inline-block align-middle",
                                            style={"marginBottom": "0", "verticalAlign": "middle"},
                                        ),
                                        html.Span("🌙", style={"fontSize": "11px", "color": "rgba(255,255,255,0.7)", "marginLeft": "3px"}),
                                    ], className="d-flex align-items-center ms-2", style={"gap": "2px"}),
                                ),
                            ],
                            navbar=True,
                            className="ms-auto",
                        ),
                        id="navbar-collapse",
                        navbar=True,
                        is_open=False,
                    ),
                ],
                fluid=True,
                style={"padding": "0 16px"},
            ),
            color="dark",
            dark=True,
            sticky="top",
            className="t-global-navbar",
            style={
                "height": "80px",
                "minHeight": "80px",
                "padding": "0",
                "zIndex": "1030",
                "boxShadow": "0 2px 6px rgba(0,0,0,0.35)",
                "background": f"linear-gradient(90deg, {_NAVY} 0%, {_NAVY_DARK} 100%)",
                "borderBottom": f"3px solid {_GOVCO_GOLD}",
                "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
                "flexWrap": "nowrap",
                "whiteSpace": "nowrap",
            },
        ),
    ])

# ── Callback para el Toggler (Menú móvil) ──────────────────────────
clientside_callback(
    """
    function(n_clicks, is_open) {
        if (n_clicks) {
            return !is_open;
        }
        return is_open;
    }
    """,
    Output("navbar-collapse", "is_open"),
    [Input("navbar-toggler", "n_clicks")],
    [State("navbar-collapse", "is_open")],
)

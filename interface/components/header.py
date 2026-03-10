from dash import html, dcc, clientside_callback, Input, Output
import dash_bootstrap_components as dbc


def crear_header_restaurado():
    """
    Encabezado global Portal Energético MME — BUG 3 fix.

    Cambios:
    - dbc.Navbar (en lugar de NavbarSimple) para control total del layout
    - sticky="top" (en lugar de fixed) — no requiere paddingTop en el contenedor
    - Altura compacta 42px
    - Logo 28px
    - NavbarToggler para móvil
    """

    return html.Div([
        dcc.Location(id="url-navbar", refresh=False),

        dbc.Navbar(
            dbc.Container(
                [
                    # ── Logo (izquierda, sin texto) ──
                    dbc.NavbarBrand(
                        html.Img(
                            src="/assets/images/logo-minenergia.png",
                            height="34px",
                            style={
                                "verticalAlign": "middle",
                                "filter": "brightness(1.15)",
                            },
                        ),
                        href="https://portalenergetico.minenergia.gov.co/",
                        target="_blank",
                        title="Portal Energético MME",
                        style={"padding": "0", "marginRight": "16px"},
                    ),

                    # ── Toggler móvil ──
                    dbc.NavbarToggler(id="navbar-toggler", n_clicks=0),

                    # ── Links de navegación (derecha) ──
                    dbc.Collapse(
                        dbc.Nav(
                            [
                                dbc.NavItem(dbc.NavLink("Inicio", href="/", id="nav-link-inicio", active="exact")),
                                dbc.NavItem(dbc.NavLink("Generación", href="/generacion", id="nav-link-generacion", active="exact")),
                                dbc.NavItem(dbc.NavLink("Transmisión", href="/transmision", id="nav-link-transmision", active="exact")),
                                dbc.NavItem(dbc.NavLink("Distribución", href="/distribucion", id="nav-link-distribucion", active="exact")),
                                dbc.NavItem(dbc.NavLink("Comercialización", href="/comercializacion", id="nav-link-comercializacion", active="exact")),
                                dbc.NavItem(dbc.NavLink("Pérdidas", href="/perdidas", id="nav-link-perdidas", active="exact")),
                                dbc.NavItem(dbc.NavLink("Restricciones", href="/restricciones", id="nav-link-restricciones", active="exact")),
                                dbc.NavItem(dbc.NavLink("Costo Unitario", href="/costo-unitario", id="nav-link-costo-unitario", active="exact")),
                                dbc.NavItem(dbc.NavLink("Simulación", href="/simulacion-creg", id="nav-link-simulacion-creg", active="exact")),
                                dbc.NavItem(dbc.NavLink("Pérdidas NT", href="/perdidas-nt", id="nav-link-perdidas-nt", active="exact")),
                                dbc.NavItem(dbc.NavLink("💡 Inversiones", href="/inversiones", id="nav-link-inversiones", active="exact")),
                                dbc.NavItem(dbc.NavLink("Predicciones", href="/seguimiento-predicciones", id="nav-link-seguimiento-predicciones", active="exact")),
                                dbc.NavItem(dbc.NavLink("Métricas", href="/metricas", id="nav-link-metricas", active="exact")),
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
                style={"padding": "0 12px"},
            ),
            color="dark",
            dark=True,
            sticky="top",
            className="t-global-navbar",
            style={
                "height": "42px",
                "minHeight": "42px",
                "padding": "0",
                "zIndex": "1030",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.3)",
                "background": "linear-gradient(90deg, #1e3a8a 0%, #152e6b 100%)",
                "borderBottom": "2px solid rgba(245,158,11,0.7)",
                "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
                "flexWrap": "nowrap",
                "whiteSpace": "nowrap",
            },
        ),
    ])

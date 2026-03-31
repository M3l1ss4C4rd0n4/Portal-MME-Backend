"""
Componente Toggle de Tema Oscuro/Claro.

Uso:
    from interface.components.theme_toggle import theme_toggle, register_theme_callbacks
    
    # En el layout:
    layout = html.Div([
        theme_toggle(),
        # ... resto del contenido
    ])
    
    # Registrar callbacks:
    register_theme_callbacks(app)
"""
from dash import html, dcc, callback, Output, Input, State, clientside_callback
import dash_bootstrap_components as dbc


def theme_toggle(
    id: str = "theme-toggle",
    position: str = "fixed",
) -> html.Div:
    """
    Crea el toggle de tema oscuro/claro.
    
    Args:
        id: ID del componente
        position: Posición en la página (fixed, static, absolute)
    
    Returns:
        html.Div con el toggle
    """
    
    position_styles = {
        'fixed': {
            'position': 'fixed',
            'bottom': '20px',
            'right': '20px',
            'zIndex': '9999',
        },
        'static': {
            'position': 'static',
        },
        'absolute': {
            'position': 'absolute',
            'top': '10px',
            'right': '10px',
        },
    }
    
    style = position_styles.get(position, position_styles['fixed'])
    
    return html.Div(
        id=id,
        style=style,
        children=[
            # Store para persistir el tema
            dcc.Store(id="theme-store", data="light", storage_type="local"),
            
            # Botón toggle
            html.Button(
                id=f"{id}-button",
                className="theme-toggle-btn",
                children=[
                    # Icono sol (tema claro)
                    html.I(
                        id=f"{id}-icon-sun",
                        className="fas fa-sun theme-icon-sun",
                        style={'display': 'block'}
                    ),
                    # Icono luna (tema oscuro)
                    html.I(
                        id=f"{id}-icon-moon",
                        className="fas fa-moon theme-icon-moon",
                        style={'display': 'none'}
                    ),
                ],
                title="Cambiar tema",
            ),
        ]
    )


def register_theme_callbacks(app):
    """
    Registra los callbacks necesarios para el toggle de tema.
    
    Args:
        app: Instancia de la aplicación Dash
    """
    
    # Callback clientside para aplicar el tema al cargar la página
    clientside_callback(
        """
        function(theme) {
            // Aplicar tema al documento
            document.documentElement.setAttribute('data-theme', theme);
            document.documentElement.setAttribute('data-bs-theme', theme);
            
            // Actualizar meta theme-color para móviles
            var metaThemeColor = document.querySelector("meta[name='theme-color']");
            if (metaThemeColor) {
                metaThemeColor.setAttribute('content', theme === 'dark' ? '#0f172a' : '#ffffff');
            }
            
            // Guardar en localStorage
            localStorage.setItem('dashboard-theme', theme);
            
            return theme;
        }
        """,
        Output("theme-store", "data"),
        Input("theme-store", "data"),
    )
    
    # Callback para cambiar tema al hacer clic
    clientside_callback(
        """
        function(n_clicks, current_theme) {
            if (!n_clicks) {
                return window.dash_clientside.no_update;
            }
            
            // Alternar tema
            var new_theme = current_theme === 'dark' ? 'light' : 'dark';
            
            // Aplicar al documento inmediatamente
            document.documentElement.setAttribute('data-theme', new_theme);
            document.documentElement.setAttribute('data-bs-theme', new_theme);
            
            // Actualizar iconos
            var sunIcon = document.getElementById('theme-toggle-icon-sun');
            var moonIcon = document.getElementById('theme-toggle-icon-moon');
            
            if (sunIcon && moonIcon) {
                if (new_theme === 'dark') {
                    sunIcon.style.display = 'none';
                    moonIcon.style.display = 'block';
                } else {
                    sunIcon.style.display = 'block';
                    moonIcon.style.display = 'none';
                }
            }
            
            // Actualizar meta theme-color
            var metaThemeColor = document.querySelector("meta[name='theme-color']");
            if (metaThemeColor) {
                metaThemeColor.setAttribute('content', new_theme === 'dark' ? '#0f172a' : '#ffffff');
            }
            
            // Guardar en localStorage
            localStorage.setItem('dashboard-theme', new_theme);
            
            return new_theme;
        }
        """,
        Output("theme-store", "data", allow_duplicate=True),
        Input("theme-toggle-button", "n_clicks"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    
    # Callback para inicializar tema desde localStorage
    clientside_callback(
        """
        function(_) {
            // Leer tema guardado o usar preferencia del sistema
            var savedTheme = localStorage.getItem('dashboard-theme');
            var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            var theme = savedTheme || (prefersDark ? 'dark' : 'light');
            
            // Aplicar inmediatamente
            document.documentElement.setAttribute('data-theme', theme);
            document.documentElement.setAttribute('data-bs-theme', theme);
            
            // Actualizar meta theme-color
            var metaThemeColor = document.querySelector("meta[name='theme-color']");
            if (metaThemeColor) {
                metaThemeColor.setAttribute('content', theme === 'dark' ? '#0f172a' : '#ffffff');
            }
            
            // Actualizar iconos si existen
            var sunIcon = document.getElementById('theme-toggle-icon-sun');
            var moonIcon = document.getElementById('theme-toggle-icon-moon');
            
            if (sunIcon && moonIcon) {
                if (theme === 'dark') {
                    sunIcon.style.display = 'none';
                    moonIcon.style.display = 'block';
                } else {
                    sunIcon.style.display = 'block';
                    moonIcon.style.display = 'none';
                }
            }
            
            return theme;
        }
        """,
        Output("theme-store", "data", allow_duplicate=True),
        Input("_pages_location", "pathname"),
        prevent_initial_call=True,
    )


def inject_theme_styles() -> html.Style:
    """
    Inyecta estilos CSS necesarios para el toggle de tema.
    
    Returns:
        html.Style con los estilos del toggle
    """
    styles = """
    .theme-toggle-btn {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        border: none;
        background: var(--bg-elevated, #ffffff);
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .theme-toggle-btn:hover {
        transform: scale(1.1);
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    
    .theme-toggle-btn:active {
        transform: scale(0.95);
    }
    
    .theme-icon-sun {
        color: #f59e0b;
        animation: rotate-in 0.3s ease;
    }
    
    .theme-icon-moon {
        color: #6366f1;
        animation: rotate-in 0.3s ease;
    }
    
    @keyframes rotate-in {
        from {
            transform: rotate(-180deg) scale(0);
            opacity: 0;
        }
        to {
            transform: rotate(0) scale(1);
            opacity: 1;
        }
    }
    
    /* Tema oscuro - ajustes específicos del toggle */
    [data-theme="dark"] .theme-toggle-btn {
        background: #334155;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    
    [data-theme="dark"] .theme-toggle-btn:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    """
    
    return html.Style(styles)

"""
Sistema de notificaciones Toast.

Uso:
    from interface.components.feedback.toast import toast_container, show_toast
    
    # En el layout:
    layout = html.Div([
        # ... contenido ...
        toast_container()
    ])
    
    # En un callback:
    @callback(
        Output("toast-success", "is_open"),
        Output("toast-success", "children"),
        Input("btn-guardar", "n_clicks"),
    )
    def guardar_datos(n_clicks):
        if n_clicks:
            # ... guardar datos ...
            return show_toast("Datos guardados correctamente")
        return False, ""
"""
from dash import html, Output, callback, Input
import dash_bootstrap_components as dbc
from typing import Optional, Tuple, Any


def toast_container(
    position: str = "top-right",
    id: str = "toast-container",
) -> html.Div:
    """
    Contenedor fijo para toasts en la pantalla.
    
    Args:
        position: Posición en pantalla (top-right, top-left, bottom-right, bottom-left)
        id: ID del contenedor
    
    Returns:
        html.Div fijo en la pantalla
    """
    
    # Estilos según posición
    position_styles = {
        'top-right': {'top': '20px', 'right': '20px'},
        'top-left': {'top': '20px', 'left': '20px'},
        'bottom-right': {'bottom': '20px', 'right': '20px'},
        'bottom-left': {'bottom': '20px', 'left': '20px'},
    }
    
    style = {
        'position': 'fixed',
        'zIndex': '9999',
        'display': 'flex',
        'flexDirection': 'column',
        'gap': '10px',
        **position_styles.get(position, position_styles['top-right'])
    }
    
    return html.Div(
        id=id,
        style=style,
        children=[
            # Toast de éxito
            dbc.Toast(
                id="toast-success",
                header=html.Span([html.I(className="fas fa-check-circle mr-2"), "Éxito"]),
                is_open=False,
                dismissable=True,
                duration=4000,
                className="toast-success",
                style={'minWidth': '300px'}
            ),
            
            # Toast de error
            dbc.Toast(
                id="toast-error",
                header=html.Span([html.I(className="fas fa-exclamation-circle mr-2"), "Error"]),
                is_open=False,
                dismissable=True,
                duration=4000,
                className="toast-error",
                style={'minWidth': '300px'}
            ),
            
            # Toast de advertencia
            dbc.Toast(
                id="toast-warning",
                header=html.Span([html.I(className="fas fa-exclamation-triangle mr-2"), "Advertencia"]),
                is_open=False,
                dismissable=True,
                duration=5000,
                className="toast-warning",
                style={'minWidth': '300px'}
            ),
            
            # Toast de información
            dbc.Toast(
                id="toast-info",
                header=html.Span([html.I(className="fas fa-info-circle mr-2"), "Información"]),
                is_open=False,
                dismissable=True,
                duration=3000,
                className="toast-info",
                style={'minWidth': '300px'}
            ),
        ]
    )


def show_toast(
    message: str,
    type_: str = "success",
) -> Tuple[bool, str]:
    """
    Helper para mostrar un toast desde un callback.
    
    Args:
        message: Mensaje a mostrar
        type_: Tipo de toast (success, error, warning, info)
    
    Returns:
        Tupla (is_open=True, message) para el Output del toast
    
    Ejemplo:
        @callback(
            Output("toast-success", "is_open"),
            Output("toast-success", "children"),
            Input("btn-guardar", "n_clicks"),
        )
        def guardar(n_clicks):
            if n_clicks:
                return show_toast("Guardado correctamente", "success")
            return False, ""
    """
    return True, message


def create_toast(
    message: str,
    type_: str = "success",
    header: Optional[str] = None,
    duration: int = 4000,
    id: Optional[str] = None,
) -> dbc.Toast:
    """
    Crea un toast individual para usar directamente.
    
    Args:
        message: Mensaje del toast
        type_: Tipo (success, error, warning, info)
        header: Header personalizado
        duration: Duración en ms
        id: ID opcional
    
    Returns:
        dbc.Toast componente
    """
    
    # Configuración por tipo
    config = {
        'success': {
            'icon': 'fas fa-check-circle',
            'title': 'Éxito',
            'className': 'toast-success',
        },
        'error': {
            'icon': 'fas fa-exclamation-circle',
            'title': 'Error',
            'className': 'toast-error',
        },
        'warning': {
            'icon': 'fas fa-exclamation-triangle',
            'title': 'Advertencia',
            'className': 'toast-warning',
        },
        'info': {
            'icon': 'fas fa-info-circle',
            'title': 'Información',
            'className': 'toast-info',
        },
    }
    
    toast_config = config.get(type_, config['info'])
    
    header_content = header or html.Span([
        html.I(className=f"{toast_config['icon']} mr-2"),
        toast_config['title']
    ])
    
    return dbc.Toast(
        id=id,
        header=header_content,
        children=message,
        is_open=True,
        dismissable=True,
        duration=duration,
        className=toast_config['className'],
        style={'minWidth': '300px'}
    )


# Callbacks globales para manejar toasts
# Estos deben registrarse en el layout principal

def register_toast_callbacks(app):
    """
    Registra los callbacks necesarios para el sistema de toasts.
    
    Args:
        app: Instancia de la app Dash
    """
    
    @app.callback(
        Output("toast-success", "is_open", allow_duplicate=True),
        Output("toast-success", "children", allow_duplicate=True),
        Input("toast-trigger-success", "data"),
        prevent_initial_call=True
    )
    def show_success_toast(data):
        """Muestra toast de éxito."""
        if data:
            return True, data.get('message', '')
        return False, ""
    
    @app.callback(
        Output("toast-error", "is_open", allow_duplicate=True),
        Output("toast-error", "children", allow_duplicate=True),
        Input("toast-trigger-error", "data"),
        prevent_initial_call=True
    )
    def show_error_toast(data):
        """Muestra toast de error."""
        if data:
            return True, data.get('message', '')
        return False, ""


# Exportar
__all__ = [
    'toast_container',
    'show_toast',
    'create_toast',
    'register_toast_callbacks',
]

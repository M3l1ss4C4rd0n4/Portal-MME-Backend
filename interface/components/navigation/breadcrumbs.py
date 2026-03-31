"""
Componente de Breadcrumbs para navegación.

Uso:
    from interface.components.navigation.breadcrumbs import breadcrumbs
    
    # En el layout:
    layout = html.Div([
        breadcrumbs(),
        # ... resto del contenido
    ])
"""
from dash import html, callback, Output, Input, State
import dash
import dash_bootstrap_components as dbc
from typing import List, Dict, Optional, Tuple


# Mapeo de rutas a nombres legibles
ROUTE_NAMES = {
    "/": ("Inicio", "fas fa-home"),
    "/generacion": ("Generación", "fas fa-bolt"),
    "/generacion/fuentes": ("Por Fuente", "fas fa-industry"),
    "/generacion/hidrologia": ("Hidrología", "fas fa-water"),
    "/transmision": ("Transmisión", "fas fa-network-wired"),
    "/distribucion": ("Distribución", "fas fa-project-diagram"),
    "/comercializacion": ("Comercialización", "fas fa-handshake"),
    "/perdidas": ("Pérdidas", "fas fa-tachometer-alt"),
    "/restricciones": ("Restricciones", "fas fa-exclamation-triangle"),
    "/costo_unitario": ("Costo Unitario", "fas fa-calculator"),
    "/costo_usuario_final": ("Costo Usuario Final", "fas fa-file-invoice-dollar"),
    "/predicciones": ("Predicciones", "fas fa-chart-line"),
    "/metricas": ("Métricas", "fas fa-chart-bar"),
    "/inversiones": ("Inversiones", "fas fa-landmark"),
    "/simulacion_creg": ("Simulación CREG", "fas fa-cogs"),
}


def get_breadcrumb_items(current_path: str) -> List[Dict]:
    """
    Genera los items de breadcrumb basado en la ruta actual.
    
    Args:
        current_path: Ruta actual de la página
    
    Returns:
        Lista de diccionarios con los items del breadcrumb
    """
    items = [{"label": "Inicio", "href": "/", "active": current_path == "/"}]
    
    if current_path == "/":
        return items
    
    # Construir jerarquía de rutas
    parts = current_path.strip("/").split("/")
    current = ""
    
    for i, part in enumerate(parts):
        current += f"/{part}"
        
        # Buscar nombre de la ruta
        route_info = ROUTE_NAMES.get(current)
        if route_info:
            name, icon = route_info
            is_active = (i == len(parts) - 1)
            
            items.append({
                "label": html.Span([
                    html.I(className=f"{icon} mr-1") if icon else None,
                    name
                ]),
                "href": current if not is_active else None,
                "active": is_active
            })
        else:
            # Si no está en el mapeo, usar el nombre de la ruta formateado
            formatted_name = part.replace("_", " ").replace("-", " ").title()
            is_active = (i == len(parts) - 1)
            
            items.append({
                "label": formatted_name,
                "href": current if not is_active else None,
                "active": is_active
            })
    
    return items


def breadcrumbs(
    custom_items: Optional[List[Dict]] = None,
    id: str = "app-breadcrumbs",
    className: str = "",
) -> html.Div:
    """
    Crea el componente de breadcrumbs.
    
    Args:
        custom_items: Items personalizados (opcional)
        id: ID del componente
        className: Clases CSS adicionales
    
    Returns:
        html.Div con el breadcrumb
    """
    # Si se proporcionan items personalizados, usarlos
    # De lo contrario, se generarán dinámicamente vía callback
    
    if custom_items:
        return html.Div(
            dbc.Breadcrumb(
                items=custom_items,
                className=f"app-breadcrumbs {className}"
            ),
            id=id
        )
    
    # Para generación dinámica, usar un container que se actualiza vía callback
    return html.Div(
        dbc.Breadcrumb(
            id=f"{id}-inner",
            items=[{"label": "Inicio", "href": "/", "active": True}],
            className=f"app-breadcrumbs {className}"
        ),
        id=id
    )


def register_breadcrumb_callbacks(app):
    """
    Registra los callbacks para actualizar breadcrumbs dinámicamente.
    
    Args:
        app: Instancia de la app Dash
    """
    
    @app.callback(
        Output("app-breadcrumbs-inner", "items"),
        Input("url", "pathname"),
    )
    def update_breadcrumbs(pathname):
        """Actualiza el breadcrumb basado en la URL actual."""
        if not pathname:
            pathname = "/"
        
        return get_breadcrumb_items(pathname)


def breadcrumb_item(
    label: str,
    href: Optional[str] = None,
    icon: Optional[str] = None,
    active: bool = False,
) -> Dict:
    """
    Helper para crear un item de breadcrumb.
    
    Args:
        label: Texto del item
        href: URL de navegación (None si es activo)
        icon: Clase FontAwesome del icono
        active: Si es el item activo
    
    Returns:
        Diccionario con el item
    """
    item = {"label": label, "active": active}
    
    if href and not active:
        item["href"] = href
    
    if icon:
        item["label"] = html.Span([
            html.I(className=f"{icon} mr-1"),
            label
        ])
    
    return item


# Exportar
__all__ = [
    'breadcrumbs',
    'breadcrumb_item',
    'get_breadcrumb_items',
    'register_breadcrumb_callbacks',
    'ROUTE_NAMES',
]

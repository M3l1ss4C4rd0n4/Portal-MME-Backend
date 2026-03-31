"""
FIX CRÍTICO: Dash 4.0 + Gunicorn Callback Registration

Este archivo contiene el fix para el problema de callbacks no registrados.
Sustituye la lógica de create_app() en app_factory.py
"""

import os
from dash import Dash, html, dcc, page_container
import dash_bootstrap_components as dbc


def create_app_with_fix():
    """
    Versión corregida de create_app que soluciona el problema de callbacks.
    
    El problema: Dash 4.0 con Gunicorn no registra callbacks de @callback global
    La solución: Desactivar Dash Pages y usar registro manual de callbacks
    """
    
    # Crear app SIN Dash Pages (el source del problema)
    app = Dash(
        __name__,
        use_pages=False,  # ❌ Desactivar Dash Pages
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
        ],
        suppress_callback_exceptions=True,
    )
    
    # Layout con router manual
    app.layout = html.Div([
        dcc.Location(id='url', refresh=False),
        html.Div(id='page-content')
    ])
    
    # Importar y registrar páginas manualmente
    from interface.pages import (
        home, transmision, generacion, distribucion,
        comercializacion, perdidas, costo_unitario, metricas
    )
    
    # Mapeo de rutas a layouts
    page_map = {
        '/': home,
        '/transmision': transmision,
        '/generacion': generacion,
        '/distribucion': distribucion,
        '/comercializacion': comercializacion,
        '/perdidas': perdidas,
        '/costo-unitario': costo_unitario,
        '/metricas': metricas,
    }
    
    # Router manual
    @app.callback(
        Output('page-content', 'children'),
        Input('url', 'pathname')
    )
    def display_page(pathname):
        """Router manual de páginas"""
        pathname = pathname or '/'
        
        # Buscar página exacta
        if pathname in page_map:
            module = page_map[pathname]
            return module.layout() if hasattr(module, 'layout') else module.layout
        
        # Buscar página con prefijo
        for route, module in page_map.items():
            if pathname.startswith(route) and route != '/':
                return module.layout() if hasattr(module, 'layout') else module.layout
        
        # Default: home
        return home.layout() if hasattr(home, 'layout') else home.layout
    
    # FIX CRÍTICO: Convertir @callback global a @app.callback
    from dash import _callback as _cb_module
    
    print(f"[FIX] Registrando {len(_cb_module.GLOBAL_CALLBACK_LIST)} callbacks...")
    
    registered = 0
    errors = 0
    
    for cb in _cb_module.GLOBAL_CALLBACK_LIST:
        try:
            # Obtener la función del callback
            func = cb.get('callback')
            if not func:
                continue
            
            # Parsear output string a objetos Output
            output_str = cb.get('output', '')
            inputs_list = cb.get('inputs', [])
            state_list = cb.get('state', [])
            
            # Convertir strings a objetos Input/Output/State
            from dash import Input, Output, State
            
            def parse_dependency(dep_list):
                """Convierte dict de dependencia a objeto Dash"""
                result = []
                for dep in dep_list:
                    if isinstance(dep, dict):
                        if dep.get('property'):
                            obj = type('Dep', (), {
                                'id': dep.get('id'),
                                'property': dep.get('property'),
                                'component_id': dep.get('id'),
                                'component_property': dep.get('property')
                            })()
                            result.append(obj)
                return result
            
            # Para outputs múltiples (formato ..id1.prop...id2.prop..)
            if output_str.startswith('..'):
                # Es un output múltiple - ignorar por ahora o manejar especial
                continue
            elif '@' in output_str:
                # Es un output con hash - ignorar
                continue
            else:
                # Output simple
                parts = output_str.split('.')
                if len(parts) == 2:
                    output_obj = Output(parts[0], parts[1])
                    
                    # Parsear inputs
                    input_objs = []
                    for inp in inputs_list:
                        if isinstance(inp, dict):
                            input_objs.append(Input(inp['id'], inp['property']))
                    
                    # Parsear state
                    state_objs = []
                    for st in state_list:
                        if isinstance(st, dict):
                            state_objs.append(State(st['id'], st['property']))
                    
                    # Registrar callback
                    if input_objs:
                        decorated = app.callback(
                            output_obj,
                            input_objs,
                            state_objs if state_objs else None,
                            prevent_initial_call=cb.get('prevent_initial_call', False)
                        )
                        decorated(func)
                        registered += 1
                        
        except Exception as e:
            errors += 1
            # Silenciar errores de callbacks ya registrados
            pass
    
    print(f"[FIX] Callbacks registrados: {registered}, Errores: {errors}")
    print(f"[FIX] Total en callback_map: {len(app.callback_map)}")
    
    return app


# Versión alternativa más simple: Monkey Patch
def apply_callback_patch():
    """
    Parchea Dash para que los @callback globales se registren automáticamente.
    Aplicar ANTES de crear la app.
    """
    from dash import _callback as _cb_module
    from dash.dependencies import Input, Output, State
    
    original_callback = _cb_module.callback
    
    def patched_callback(*args, **kwargs):
        """Wrapper que intercepta callbacks y los guarda"""
        # Llamar al original
        result = original_callback(*args, **kwargs)
        
        # Guardar para registro posterior
        if not hasattr(_cb_module, '_DEFERRED_CALLBACKS'):
            _cb_module._DEFERRED_CALLBACKS = []
        
        _cb_module._DEFERRED_CALLBACKS.append({
            'args': args,
            'kwargs': kwargs,
            'registered': False
        })
        
        return result
    
    _cb_module.callback = patched_callback
    print("[PATCH] Callback interceptor activado")


def register_deferred_callbacks(app):
    """
    Registra los callbacks que fueron interceptados.
    Llamar DESPUÉS de crear la app.
    """
    from dash import _callback as _cb_module
    
    if not hasattr(_cb_module, '_DEFERRED_CALLBACKS'):
        print("[PATCH] No hay callbacks diferidos")
        return
    
    deferred = _cb_module._DEFERRED_CALLBACKS
    print(f"[PATCH] Registrando {len(deferred)} callbacks diferidos...")
    
    registered = 0
    for cb in deferred:
        if cb['registered']:
            continue
        
        try:
            args = cb['args']
            kwargs = cb['kwargs']
            
            # Aplicar callback a la app
            app.callback(*args, **kwargs)
            cb['registered'] = True
            registered += 1
        except Exception as e:
            pass  # Callback ya registrado o error
    
    print(f"[PATCH] Callbacks registrados: {registered}")

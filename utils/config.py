"""
Configuración para el dashboard Dash
"""

# Configuración de colores y estilos - INTEGRADA CON SVG PORTADA
COLORS = {
    # Paleta principal - EXTRAÍDA DEL SVG
    'primary': '#F2C330',        # Amarillo dorado principal del SVG
    'secondary': '#FCF3D6',      # Crema cálido de fondo SVG
    'accent': '#8BC121',         # Verde energético del SVG
    'tertiary': '#5F80AF',       # Azul institucional del SVG
    
    # Estados y acciones - ARMONIZADOS CON SVG
    'success': '#85AA13',        # Verde oliva del SVG - sostenibilidad
    'warning': '#F2C330',        # Amarillo dorado - advertencias
    'danger': '#DC2626',         # Rojo coral - alertas críticas
    'info': '#1BABEA',           # Azul cielo del SVG - información
    
    # Fondos - Paleta integrada con SVG
    'bg_main': '#FCF3D6',        # Crema del SVG como fondo principal
    'bg_card': '#FFFFFF',        # Cards blanco pristino
    'bg_sidebar': '#F4E9E9',     # Rosa pálido del SVG
    'bg_header': '#FFFFFF',      # Header blanco elegante
    'bg_section': '#EAE1DA',     # Beige suave del SVG
    'bg_gradient_start': '#FCF3D6',   # Gradientes del SVG
    'bg_gradient_end': '#EAE1DA',
    
    # Textos - Jerarquía con colores SVG
    'text_primary': '#3D3D3D',   # Gris oscuro para contraste
    'text_secondary': '#60350E', # Marrón del SVG
    'text_light': '#FFFFFF',     # Texto sobre fondos oscuros
    'text_muted': '#8C5A29',     # Marrón tierra del SVG
    'text_accent': '#8BC121',    # Verde energético del SVG
    
    # Bordes y sombras - Tonos tierra del SVG
    'border': '#E0D4CA',         # Beige del SVG
    'border_light': '#F4E9E9',   # Rosa muy claro
    'border_dark': '#AA9F99',    # Gris tierra
    'border_accent': '#F2C330',  # Amarillo dorado de acento
    
    # Sombras institucionales
    'shadow_sm': 'rgba(140, 90, 41, 0.08)',     # Sombra cálida pequeña
    'shadow_md': 'rgba(140, 90, 41, 0.12)',     # Sombra cálida mediana  
    'shadow_lg': 'rgba(140, 90, 41, 0.16)',     # Sombra cálida grande
    'shadow_accent': 'rgba(242, 195, 48, 0.25)', # Sombra dorada
    'shadow': 'rgba(140, 90, 41, 0.12)',        # Sombra por defecto
    
    # Overlays y transparencias
    'overlay_light': 'rgba(252, 243, 214, 0.95)',  # Overlay crema
    'overlay_dark': 'rgba(60, 53, 14, 0.90)',      # Overlay oscuro cálido
    'glass_effect': 'rgba(255, 255, 255, 0.25)',
    
    # Colores específicos por sector energético
    'energia_hidraulica': '#0284C7',    # Azul agua
    'energia_solar': '#F59E0B',         # Dorado solar
    'energia_eolica': '#10B981',        # Verde viento
    'energia_termica': '#EF4444',       # Rojo térmico
    'energia_biomasa': '#84CC16',       # Verde lima biomasa
    'transmision': '#6366F1',           # Índigo transmisión
    'distribucion': '#8B5CF6',          # Violeta distribución
    'demanda': '#F97316',               # Naranja demanda
    'perdidas': '#EC4899',              # Rosa pérdidas
    'restricciones': '#DC2626'          # Rojo restricciones
}

# Configuración del mapa
MAP_CONFIG = {
    'center_lat': 4.5,
    'center_lon': -74.0,
    'zoom': 6,
    'max_zoom': 15,
    'min_zoom': 4
}

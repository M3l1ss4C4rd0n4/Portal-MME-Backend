"""
Configuración para el dashboard Dash
"""

# Configuración de colores y estilos - MINISTERIO DE MINAS Y ENERGÍA
COLORS = {
    # Paleta principal institucional
    'primary': '#0F172A',        # Azul marino profundo - elegante y profesional
    'secondary': '#1E293B',      # Gris azulado oscuro - sofisticado  
    'accent': '#0D9488',         # Verde azulado - energía limpia y sostenible
    'tertiary': '#374151',       # Gris carbón - moderno
    
    # Estados y acciones
    'success': '#059669',        # Verde esmeralda - éxito y sostenibilidad
    'warning': '#D97706',        # Ámbar - advertencias energéticas
    'danger': '#DC2626',         # Rojo coral - alertas críticas
    'info': '#0284C7',           # Azul cielo - información
    
    # Fondos - Paleta ultra sofisticada
    'bg_main': '#FEFEFE',        # Blanco puro con un toque cálido
    'bg_card': '#FFFFFF',        # Cards blanco pristino
    'bg_sidebar': '#F8FAFC',     # Gris perla muy sutil
    'bg_header': '#FFFFFF',      # Header blanco elegante
    'bg_section': '#F9FAFB',     # Secciones gris hueso
    'bg_gradient_start': '#FFFFFF',   # Gradientes sutiles
    'bg_gradient_end': '#F8FAFC',
    
    # Textos - Jerarquía tipográfica profesional
    'text_primary': '#0F172A',   # Texto principal: azul marino profundo
    'text_secondary': '#475569', # Texto secundario: gris pizarra
    'text_light': '#FFFFFF',     # Texto sobre fondos oscuros
    'text_muted': '#64748B',     # Texto atenuado: gris acero
    'text_accent': '#0D9488',    # Texto de acento: verde energético
    
    # Bordes y sombras - Minimalismo elegante
    'border': '#E2E8F0',         # Bordes suaves gris plata
    'border_light': '#F1F5F9',   # Bordes muy sutiles
    'border_dark': '#CBD5E1',    # Bordes definidos
    'border_accent': '#14B8A6',  # Bordes de acento verde agua
    
    # Sombras institucionales
    'shadow_sm': 'rgba(15, 23, 42, 0.04)',     # Sombra pequeña
    'shadow_md': 'rgba(15, 23, 42, 0.08)',     # Sombra mediana  
    'shadow_lg': 'rgba(15, 23, 42, 0.12)',     # Sombra grande
    'shadow_accent': 'rgba(13, 148, 136, 0.15)', # Sombra de acento
    'shadow': 'rgba(15, 23, 42, 0.08)',        # Sombra por defecto (compatibility)
    
    # Overlays y transparencias
    'overlay_light': 'rgba(255, 255, 255, 0.95)',
    'overlay_dark': 'rgba(15, 23, 42, 0.90)',
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

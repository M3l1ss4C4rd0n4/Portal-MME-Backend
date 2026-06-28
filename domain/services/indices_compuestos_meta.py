"""
Metadatos y renderizado compartido de índices compuestos (ISH, IPM, IES, CIS).

Usado por report_service (PDF) y notification_service (email HTML).
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple

# (key, sigla, nombre_completo, subtitulo, icon_html_email)
INDICES_DEFS: List[Tuple[str, str, str, str, str]] = [
    (
        'ish',
        'ISH',
        'Índice de Sostenibilidad Hídrica',
        'Disponibilidad hídrica en embalses',
        '&#128167;',
    ),
    (
        'ipm',
        'IPM',
        'Índice de Presión de Mercado',
        'Presión alcista de precios de bolsa',
        '&#128176;',
    ),
    (
        'ies',
        'IES',
        'Índice de Estrés del Sistema',
        'Estrés operativo agregado',
        '&#9888;&#65039;',
    ),
    (
        'cis',
        'CIS',
        'Calificación Integral del Sistema',
        'Estado general del SIN',
        '&#127775;',
    ),
]

IDX_COLORS: Dict[str, str] = {
    'ÓPTIMO': '#1B5E20', 'ADECUADO': '#2E7D32', 'NORMAL': '#2E7D32', 'ESTABLE': '#2E7D32',
    'LEVE': '#7CB342', 'BAJO': '#E65100', 'MODERADO': '#E65100', 'VIGILANCIA': '#E65100',
    'PREOCUPANTE': '#BF360C', 'ALTO ESTRÉS': '#B71C1C',
    'CRÍTICO': '#B71C1C',
}

IDX_BG: Dict[str, str] = {
    'ÓPTIMO': '#C8E6C9', 'ADECUADO': '#E8F5E9', 'NORMAL': '#E8F5E9', 'ESTABLE': '#E8F5E9',
    'LEVE': '#F9FBE7', 'BAJO': '#FFF3E0', 'MODERADO': '#FFF3E0', 'VIGILANCIA': '#FFF3E0',
    'PREOCUPANTE': '#FBE9E7', 'ALTO ESTRÉS': '#FFEBEE',
    'CRÍTICO': '#FFEBEE',
}

IDX_META: Dict[str, Dict[str, Any]] = {
    'ISH': {
        'titulo': 'Disponibilidad de agua en embalses para generación eléctrica',
        'niveles': {
            'ÓPTIMO': (
                'Los embalses están en niveles históricamente altos. Hay amplia reserva hídrica.',
                'El sistema opera con gran margen de seguridad. La hidroenergía puede cubrir la demanda sin apoyos térmicos.',
                'Mantener la gestión actual. Aprovechar excedentes para optimizar costos.',
            ),
            'ADECUADO': (
                'Los embalses tienen reservas suficientes para cubrir la demanda en el corto plazo.',
                'Bajo riesgo operativo. Los precios de bolsa se mantienen estables.',
                'Monitorear la tendencia. Si los aportes hídricos bajan, revisar despacho térmico.',
            ),
            'BAJO': (
                'Los embalses están por debajo de niveles normales. La reserva hídrica es insuficiente.',
                'Presión al alza en precios de bolsa. Mayor dependencia de generación térmica costosa.',
                'Activar planes de contingencia térmica. Revisar restricciones de exportación de energía.',
            ),
            'CRÍTICO': (
                'Los embalses están en niveles críticos. Riesgo real de racionamiento.',
                'El sistema enfrenta riesgo de desabastecimiento. Los precios de bolsa pueden dispararse.',
                'Declarar alerta de escasez. Activar protocolos de emergencia y coordinación con el regulador.',
            ),
        },
    },
    'IPM': {
        'titulo': 'Presión que ejercen los precios del mercado eléctrico mayorista',
        'niveles': {
            'NORMAL': (
                'Los precios de bolsa están dentro de rangos históricos normales. No hay presión económica.',
                'Costos de generación estables. Los usuarios regulados no enfrentarán incrementos abruptos.',
                'Sin acción inmediata. Continuar monitoreo de aportes hídricos y oferta térmica.',
            ),
            'LEVE': (
                'Los precios muestran una tendencia al alza moderada, aún dentro de rangos manejables.',
                'Leve incremento en el costo de prestación del servicio. Márgenes comercializadores bajo presión.',
                'Verificar causas (déficits hídricos, mantenimientos). Preparar alertas a agentes del mercado.',
            ),
            'MODERADO': (
                'Los precios de bolsa están por encima de lo normal. El mercado muestra tensión.',
                'Efecto directo en tarifas reguladas si persiste. Riesgo de incumplimiento en contratos a precio fijo.',
                'Emitir circular a comercializadores. Revisar opciones de gestión de demanda y respuesta activa.',
            ),
            'ALTO ESTRÉS': (
                'Los precios de bolsa están en niveles excepcionalmente altos. Crisis de precios en el mercado.',
                'Impacto directo en tarifas a usuarios. Riesgo de crisis financiera en comercializadores deficitarios.',
                'Intervención regulatoria urgente. Activar mecanismos de precio límite y mesas de trabajo con CREG.',
            ),
        },
    },
    'IES': {
        'titulo': 'Nivel de estrés operativo del sistema eléctrico nacional',
        'niveles': {
            'NORMAL': (
                'El sistema opera con normalidad. No hay indicios de sobrecarga o vulnerabilidades críticas.',
                'La confiabilidad del servicio es alta. El riesgo de fallas en cascada es mínimo.',
                'Mantener vigilancia rutinaria. Sin acciones especiales requeridas.',
            ),
            'LEVE': (
                'El sistema presenta algunas señales de estrés: anomalías aisladas o márgenes ajustados.',
                'La confiabilidad se mantiene, pero con menor margen de maniobra ante imprevistos.',
                'Revisar planes de mantenimiento preventivo. Identificar los indicadores que están generando el estrés.',
            ),
            'MODERADO': (
                'El sistema acumula múltiples indicadores en estado de alerta. La presión operativa es significativa.',
                'Riesgo elevado ante eventos imprevistos (salida de una planta grande, ola de calor). Menor resiliencia.',
                'Activar coordinación operativa entre XM y generadores. Diferir mantenimientos no urgentes.',
            ),
            'ALTO ESTRÉS': (
                'El sistema está bajo estrés severo con múltiples indicadores críticos simultáneos.',
                'Alta probabilidad de fallas si ocurre cualquier contingencia adicional. Estabilidad del sistema en riesgo.',
                'Activar sala de crisis operativa. Notificar al MinMinas y a la CREG. Preparar protocolos de carga controlada.',
            ),
        },
    },
    'CIS': {
        'titulo': 'Calificación integral que resume el estado general del sistema eléctrico',
        'niveles': {
            'ESTABLE': (
                'Todos los indicadores principales están en verde. El sistema opera con condiciones óptimas.',
                'Bajo riesgo en todas las dimensiones: hídrica, económica y operativa.',
                'Sin acciones urgentes. Aprovechar la coyuntura para planear mantenimientos mayores.',
            ),
            'VIGILANCIA': (
                'El sistema es estable pero uno o más indicadores muestran tendencias a monitorear.',
                'Riesgo moderado. La situación puede evolucionar negativamente si no se gestiona.',
                'Aumentar frecuencia de monitoreo. Identificar el indicador que jala el índice hacia abajo.',
            ),
            'PREOCUPANTE': (
                'Varios indicadores están deteriorados. El sistema se acerca a condiciones de riesgo alto.',
                'El deterioro combinado puede amplificar los efectos negativos. Tarifa, confiabilidad y reservas en tensión.',
                'Escalar a nivel directivo. Convocar comité de seguimiento y preparar nota técnica para el despacho ministerial.',
            ),
            'CRÍTICO': (
                'El sistema enfrenta una crisis multidimensional con varios indicadores en rojo simultáneamente.',
                'Riesgo real de afectación masiva del servicio. Impacto económico y reputacional alto para el sector.',
                'Activar el Comité de Crisis del Sector Energético. Coordinación inmediata con Presidencia de la República.',
            ),
        },
    },
}

SCALE_FOOTNOTE = (
    'Escala 0&#8211;100 &middot; ISH y CIS: mayor valor = mejor condici&#243;n &middot; '
    'IPM e IES: mayor valor = mayor presi&#243;n/estr&#233;s'
)


def render_indice_card_html(
    key: str,
    sigla: str,
    nombre_completo: str,
    subtitulo: str,
    icon_html: str,
    entry: Dict[str, Any],
    variant: Literal['pdf', 'email'] = 'pdf',
) -> str:
    """Genera HTML de una tarjeta de índice para PDF o email."""
    valor = entry.get('valor', 0)
    nivel = str(entry.get('nivel', 'NORMAL')).upper()
    color = IDX_COLORS.get(nivel, '#555555')
    bg = IDX_BG.get(nivel, '#F5F5F5')
    meta = IDX_META.get(sigla, {})
    titulo_largo = meta.get('titulo', subtitulo)
    textos = meta.get('niveles', {}).get(nivel, ('', '', ''))
    descripcion_str, impacto_str, accion_str = textos if len(textos) == 3 else ('', '', '')

    if variant == 'email':
        icon_block = f'<div style="font-size:18px;margin-bottom:2px;">{icon_html}</div>'
        val_size = '22px'
        sigla_size = '10px'
        nombre_size = '9px'
        subt_size = '8px'
        chip_size = '9px'
        label_size = '9px'
        body_size = '9px'
        pad = '14px 10px'
        cell_pad = '5px'
        accion_label = '&#128204; Acci&#243;n: '
        situacion_label = 'Situaci&#243;n actual:'
        impacto_label = 'Impacto en el sistema:'
        que_mide_label = '&#191;Qu&#233; mide?'
    else:
        icon_block = ''
        val_size = '16pt'
        sigla_size = '8pt'
        nombre_size = '7pt'
        subt_size = '6.5pt'
        chip_size = '7pt'
        label_size = '6.5pt'
        body_size = '6.5pt'
        pad = '8px 6px'
        cell_pad = '4px'
        accion_label = 'Acci&#243;n: '
        situacion_label = 'Situaci&#243;n:'
        impacto_label = 'Impacto:'
        que_mide_label = 'Qu&#233; mide:'

    return (
        f'<td style="width:25%;padding:{cell_pad};vertical-align:top;">'
        f'<div style="background:{bg};border:2px solid {color};'
        f'border-radius:{"10px" if variant == "email" else "6px"};padding:{pad};">'
        f'<div style="text-align:center;margin-bottom:{"8px" if variant == "email" else "6px"};">'
        f'{icon_block}'
        f'<div style="font-size:{val_size};font-weight:700;color:{color};line-height:1;">{valor:.0f}</div>'
        f'<div style="font-size:{sigla_size};font-weight:700;color:#333;margin:2px 0;">{sigla}</div>'
        f'<div style="font-size:{nombre_size};font-weight:700;color:#222;line-height:1.2;margin:2px 4px;">'
        f'{nombre_completo}</div>'
        f'<div style="font-size:{subt_size};color:#666;line-height:1.2;margin:0 4px 4px;">{subtitulo}</div>'
        f'<div style="padding:{"2px 8px" if variant == "email" else "1px 5px"};border-radius:3px;'
        f'display:inline-block;background:{color};color:#fff;font-size:{chip_size};'
        f'font-weight:600;">{nivel}</div>'
        f'</div>'
        f'<div style="font-size:{label_size};font-weight:700;color:#333;'
        f'border-top:1px solid {color}{"20" if variant == "email" else "30"};'
        f'padding-top:{"6px" if variant == "email" else "4px"};'
        f'margin-top:{"2px" if variant == "email" else "0"};">{que_mide_label}</div>'
        f'<div style="font-size:{body_size};color:#444;margin-bottom:{"6px" if variant == "email" else "4px"};'
        f'line-height:1.3;">{titulo_largo}</div>'
        f'<div style="font-size:{label_size};font-weight:700;color:#333;">{situacion_label}</div>'
        f'<div style="font-size:{body_size};color:#444;margin-bottom:{"6px" if variant == "email" else "4px"};'
        f'line-height:1.3;">{descripcion_str}</div>'
        f'<div style="font-size:{label_size};font-weight:700;color:#333;">{impacto_label}</div>'
        f'<div style="font-size:{body_size};color:#444;margin-bottom:{"6px" if variant == "email" else "4px"};'
        f'line-height:1.3;">{impacto_str}</div>'
        f'<div style="font-size:{label_size};font-weight:700;color:{color};background:{color}'
        f'{"15" if variant == "email" else "18"};border-radius:3px;padding:{"4px 6px" if variant == "email" else "3px 4px"};'
        f'line-height:1.3;">{accion_label}{accion_str}</div>'
        f'</div></td>'
    )


def render_indices_row_html(
    indices_compuestos: Dict[str, Any],
    variant: Literal['pdf', 'email'] = 'pdf',
) -> str:
    """Genera la fila HTML con las 4 tarjetas de índices."""
    cells = ''
    for key, sigla, nombre_completo, subtitulo, icon_html in INDICES_DEFS:
        entry = indices_compuestos.get(key, {})
        cells += render_indice_card_html(
            key, sigla, nombre_completo, subtitulo, icon_html, entry, variant=variant,
        )
    return cells


def render_indices_footnote(
    indices_compuestos: Dict[str, Any],
    variant: Literal['pdf', 'email'] = 'pdf',
) -> str:
    """Nota al pie bajo la tabla de índices."""
    comp = indices_compuestos.get('componentes', {})
    n_crit = comp.get('anomalias_criticas', 0)
    n_alert = comp.get('anomalias_alertas', 0)
    font = '10px' if variant == 'email' else '7pt'
    margin = '8px' if variant == 'email' else '6px'
    return (
        f'<div style="font-size:{font};color:#666;margin-top:{margin};text-align:center;">'
        f'{SCALE_FOOTNOTE} &middot; '
        f'{n_crit} alerta(s) cr&#237;tica(s) + {n_alert} alerta(s) moderada(s) computadas'
        f'</div>'
    )

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
    # ISH — clasificar_visual_embalse() (Res. CREG 209/2020 + 101 112/2026)
    'NORMAL': '#2E7D32', 'SOBRE SENDA': '#2E7D32',
    'BAJO SENDA — ALERTA': '#E65100', 'BAJO SENDA — RIESGO': '#B71C1C',
    # IPM — clasificar_visual_precio_bolsa() (Res. CREG 101 066/2024)
    'CÓMODO': '#2E7D32', 'ESTRÉS MODERADO': '#E65100',
    'ALTA PRESIÓN': '#BF360C', 'TECHO REGULATORIO': '#B71C1C',
    # CIS — determinar_condicion_sistema() (Estatuto CREG 026/2014 art. 3)
    'VIGILANCIA': '#E65100', 'RIESGO': '#B71C1C',
    'SIN DATO OFICIAL': '#757575',
    # IES — compuesto interno, no una etiqueta CREG (ver nota en su tarjeta)
    'LEVE': '#7CB342', 'MODERADO': '#E65100', 'ALTO ESTRÉS': '#B71C1C',
}

IDX_BG: Dict[str, str] = {
    'NORMAL': '#E8F5E9', 'SOBRE SENDA': '#E8F5E9',
    'BAJO SENDA — ALERTA': '#FFF3E0', 'BAJO SENDA — RIESGO': '#FFEBEE',
    'CÓMODO': '#E8F5E9', 'ESTRÉS MODERADO': '#FFF3E0',
    'ALTA PRESIÓN': '#FBE9E7', 'TECHO REGULATORIO': '#FFEBEE',
    'VIGILANCIA': '#FFF3E0', 'RIESGO': '#FFEBEE',
    'SIN DATO OFICIAL': '#F5F5F5',
    'LEVE': '#F9FBE7', 'MODERADO': '#FFF3E0', 'ALTO ESTRÉS': '#FFEBEE',
}

# Textos cortos en lenguaje simple para cada estado OFICIAL de la CREG — no
# son párrafos editoriales de "impacto"/"acción" inventados, son solo una
# explicación breve de qué significa la palabra oficial. A pedido explícito
# del usuario (2026-08-25): "no quiero inventar datos que no vengan
# directamente de la normativa oficial de la CREG". El texto sí explica en
# palabras simples, la cita normativa exacta queda como nota al pie de cada
# tarjeta (ver render_indice_card_html).
IDX_META: Dict[str, Dict[str, Any]] = {
    'ISH': {
        'titulo': 'Nivel del embalse frente a la Senda de Referencia que publica la CREG',
        'niveles': {
            'NORMAL': 'El embalse supera el nivel que XM recomienda mantener ante el fenómeno de El Niño — reserva amplia.',
            'SOBRE SENDA': 'El embalse está por encima del nivel mínimo esperado para esta época del año, según la CREG.',
            'BAJO SENDA — ALERTA': 'El embalse está algo por debajo del nivel mínimo esperado para esta época — vigilancia preventiva.',
            'BAJO SENDA — RIESGO': 'El embalse está claramente por debajo del nivel mínimo esperado — riesgo de desabastecimiento según la CREG.',
            'SIN DATO OFICIAL': 'No se pudo calcular la clasificación oficial hoy — falta el dato de embalse.',
        },
    },
    'IPM': {
        'titulo': 'Precio de bolsa frente a los 3 niveles de precio de escasez que fija la CREG',
        'niveles': {
            'CÓMODO': 'El precio de la energía está por debajo del primer nivel de escasez — sin presión regulatoria.',
            'ESTRÉS MODERADO': 'El precio empieza a acercarse al nivel de precio de escasez que vigila la CREG.',
            'ALTA PRESIÓN': 'El precio superó el precio de escasez y se acerca al techo regulatorio.',
            'TECHO REGULATORIO': 'El precio alcanzó el techo regulatorio de escasez — el nivel más alto que vigila la CREG.',
            'SIN DATO OFICIAL': 'No se pudo calcular la clasificación oficial hoy — falta el dato de precio de bolsa.',
        },
    },
    'IES': {
        'titulo': 'Compuesto interno del propio informe (ISH + IPM + anomalías) — NO es una clasificación oficial de la CREG, solo un indicador de seguimiento del portal.',
        'niveles': {
            'NORMAL': 'Sin señales combinadas relevantes entre embalses, precio y anomalías detectadas.',
            'LEVE': 'Alguna señal aislada entre embalses, precio o anomalías — vale la pena monitorear.',
            'MODERADO': 'Varias señales combinadas a la vez — seguimiento más cercano recomendado.',
            'ALTO ESTRÉS': 'Múltiples señales negativas combinadas al mismo tiempo.',
        },
    },
    'CIS': {
        'titulo': 'Condición del sistema según el Estatuto CREG 026/2014 art. 3 (combina Índice NE + HSIN + PBP)',
        'niveles': {
            'NORMAL': 'El sistema está en condiciones normales según la definición oficial de la CREG.',
            'VIGILANCIA': 'Uno o más de los indicadores oficiales de la CREG (embalse, aportes o precio) salió de su rango normal — vigilancia preventiva.',
            'RIESGO': 'El sistema está en riesgo de desabastecimiento según la definición oficial de la CREG — varias señales negativas ocurren a la vez.',
            'SIN DATO OFICIAL': 'No se pudo calcular la condición oficial completa hoy — falta alguno de los 3 indicadores que la componen (embalse, aportes o precio).',
        },
    },
}

SCALE_FOOTNOTE = (
    'Escala 0&#8211;100 &middot; ISH y CIS: mayor valor = mejor condici&#243;n &middot; '
    'IPM e IES: mayor valor = mayor presi&#243;n/estr&#233;s'
)


# Cita normativa exacta por índice — mostrada como nota al pie de cada
# tarjeta, nunca como parte del texto principal (mismo patrón ya usado en
# HomeSlider: primero se explica en palabras simples, la cita normativa
# queda como referencia secundaria).
IDX_CITAS: Dict[str, str] = {
    'ISH': 'Índice NE — Res. CREG 209/2020, mod. Res. CREG 101 112/2026.',
    'IPM': 'Precios de escasez PEI/PE/PES — Res. CREG 101 066/2024.',
    'CIS': 'Condición del sistema — Estatuto CREG 026/2014, art. 3.',
    'IES': 'Indicador propio de este informe — no corresponde a ninguna resolución de la CREG.',
}

# Índices cuyo NIVEL mostrado es una etiqueta oficial de la CREG (se muestra
# el estado como texto principal). IES no está aquí porque es un compuesto
# interno sin equivalente oficial — sigue mostrando su número 0-100.
_INDICES_OFICIALES = {'ISH', 'IPM', 'CIS'}


def render_indice_card_html(
    key: str,
    sigla: str,
    nombre_completo: str,
    subtitulo: str,
    icon_html: str,
    entry: Dict[str, Any],
    variant: Literal['pdf', 'email'] = 'pdf',
) -> str:
    """Genera HTML de una tarjeta de índice para PDF o email.

    2026-08-25 (a pedido explícito del usuario — "no quiero inventar datos
    que no vengan directamente de la normativa oficial de la CREG"):
    ISH/IPM/CIS ahora muestran como elemento principal el ESTADO OFICIAL
    textual (ej. "BAJO SENDA — RIESGO"), no un número 0-100 interpolado que
    podría confundirse con un dato publicado por la CREG. Debajo, un texto
    corto en lenguaje simple explica qué significa ese estado, y al final
    queda la cita normativa exacta como referencia secundaria. IES (sin
    equivalente oficial) mantiene su número + aclaración de que es un
    indicador propio del informe.
    """
    valor = entry.get('valor', 0)
    nivel = str(entry.get('nivel', 'NORMAL')).upper()
    color = IDX_COLORS.get(nivel, '#555555')
    bg = IDX_BG.get(nivel, '#F5F5F5')
    meta = IDX_META.get(sigla, {})
    titulo_largo = meta.get('titulo', subtitulo)
    descripcion_str = meta.get('niveles', {}).get(nivel, '')
    cita_str = IDX_CITAS.get(sigla, '')
    es_oficial = sigla in _INDICES_OFICIALES

    if variant == 'email':
        icon_block = f'<div style="font-size:18px;margin-bottom:2px;">{icon_html}</div>'
        val_size = '22px'
        estado_size = '15px'
        sigla_size = '10px'
        nombre_size = '9px'
        subt_size = '8px'
        label_size = '9px'
        body_size = '9px'
        cita_size = '8px'
        pad = '14px 10px'
        cell_pad = '5px'
        que_mide_label = '&#191;Qu&#233; mide?'
        significa_label = '&#191;Qu&#233; significa?'
    else:
        icon_block = ''
        val_size = '16pt'
        estado_size = '10pt'
        sigla_size = '8pt'
        nombre_size = '7pt'
        subt_size = '6.5pt'
        label_size = '6.5pt'
        body_size = '6.5pt'
        cita_size = '6pt'
        pad = '8px 6px'
        cell_pad = '4px'
        que_mide_label = 'Qu&#233; mide:'
        significa_label = 'Qu&#233; significa:'

    # Readout principal: estado oficial (ISH/IPM/CIS) o número compuesto (IES)
    if es_oficial:
        readout_html = (
            f'<div style="font-size:{estado_size};font-weight:700;color:{color};'
            f'line-height:1.15;margin:4px 2px;">{nivel}</div>'
        )
    else:
        readout_html = (
            f'<div style="font-size:{val_size};font-weight:700;color:{color};line-height:1;">{valor:.0f}</div>'
            f'<div style="padding:{"2px 8px" if variant == "email" else "1px 5px"};border-radius:3px;'
            f'display:inline-block;background:{color};color:#fff;font-size:{label_size};'
            f'font-weight:600;margin-top:3px;">{nivel}</div>'
        )

    return (
        f'<td style="width:25%;padding:{cell_pad};vertical-align:top;">'
        f'<div style="background:{bg};border:2px solid {color};'
        f'border-radius:{"10px" if variant == "email" else "6px"};padding:{pad};">'
        f'<div style="text-align:center;margin-bottom:{"8px" if variant == "email" else "6px"};">'
        f'{icon_block}'
        f'<div style="font-size:{sigla_size};font-weight:700;color:#333;margin:2px 0;">{sigla}</div>'
        f'<div style="font-size:{nombre_size};font-weight:700;color:#222;line-height:1.2;margin:2px 4px;">'
        f'{nombre_completo}</div>'
        f'<div style="font-size:{subt_size};color:#666;line-height:1.2;margin:0 4px 4px;">{subtitulo}</div>'
        f'{readout_html}'
        f'</div>'
        f'<div style="font-size:{label_size};font-weight:700;color:#333;'
        f'border-top:1px solid {color}{"20" if variant == "email" else "30"};'
        f'padding-top:{"6px" if variant == "email" else "4px"};'
        f'margin-top:{"2px" if variant == "email" else "0"};">{que_mide_label}</div>'
        f'<div style="font-size:{body_size};color:#444;margin-bottom:{"6px" if variant == "email" else "4px"};'
        f'line-height:1.3;">{titulo_largo}</div>'
        f'<div style="font-size:{label_size};font-weight:700;color:#333;">{significa_label}</div>'
        f'<div style="font-size:{body_size};color:#444;margin-bottom:{"6px" if variant == "email" else "4px"};'
        f'line-height:1.3;">{descripcion_str}</div>'
        f'<div style="font-size:{cita_size};color:#888;font-style:italic;'
        f'border-top:1px solid #eee;padding-top:3px;line-height:1.3;">{cita_str}</div>'
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

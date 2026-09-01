"""Tests de renderizado HTML de índices compuestos."""
from domain.services.indices_compuestos_meta import (
    INDICES_DEFS,
    SCALE_FOOTNOTE,
    render_indice_card_html,
    render_indices_footnote,
    render_indices_row_html,
)


def test_render_indice_card_incluye_nombre_completo():
    # ISH ahora muestra el ESTADO OFICIAL de la CREG (clasificar_visual_
    # embalse) como texto principal, no un número interpolado — ver
    # indices_compuestos_meta.py (2026-08-25, a pedido del usuario).
    html = render_indice_card_html(
        'ish',
        'ISH',
        'Índice de Sostenibilidad Hídrica',
        'Disponibilidad hídrica en embalses',
        '&#128167;',
        {'valor': 40, 'nivel': 'BAJO SENDA — RIESGO'},
        variant='pdf',
    )
    assert 'ISH' in html
    assert 'Índice de Sostenibilidad Hídrica' in html
    assert 'Disponibilidad hídrica en embalses' in html
    assert 'BAJO SENDA — RIESGO' in html
    # La cita normativa exacta debe aparecer como referencia secundaria
    assert 'CREG 209/2020' in html


def test_render_indices_row_todos_los_nombres():
    indices = {
        'ish': {'valor': 73, 'nivel': 'SOBRE SENDA'},
        'ipm': {'valor': 0, 'nivel': 'CÓMODO'},
        'ies': {'valor': 20, 'nivel': 'NORMAL'},
        'cis': {'valor': 71, 'nivel': 'VIGILANCIA'},
    }
    html = render_indices_row_html(indices, variant='pdf')
    for _key, sigla, nombre_completo, _sub, _icon in INDICES_DEFS:
        assert sigla in html
        assert nombre_completo in html


def test_render_indices_footnote_escala_diferenciada():
    footnote = render_indices_footnote(
        {'componentes': {'anomalias_criticas': 0, 'anomalias_alertas': 2}},
        variant='pdf',
    )
    assert 'ISH y CIS' in footnote
    assert 'IPM e IES' in footnote
    assert SCALE_FOOTNOTE.split('&middot;')[0].strip() in footnote

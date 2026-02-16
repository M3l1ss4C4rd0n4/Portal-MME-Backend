"""
Política de Confianza por Fuente de Predicción — FASE 6

Módulo que centraliza las reglas de confianza para cada fuente de predicción
del Portal Energético MME. Basado en el documento:
  docs/POLITICA_CONFIANZA_PREDICCIONES.md

Generado tras FASES 1-5 de limpieza de datos y reentrenamiento de modelos
(2026-02-16). MAPE y clasificaciones provienen de validación holdout real.

Uso:
  from domain.services.confianza_politica import get_confianza_politica, obtener_disclaimer

Niveles:
  MUY_CONFIABLE  → MAPE ≤ 15%, confianza ≥ 85%
  CONFIABLE      → MAPE 15-20%, confianza 75-85%
  ACEPTABLE      → MAPE 20-30%, confianza 60-80%
  EXPERIMENTAL   → Sin holdout / datos insuficientes
  DESCONOCIDO    → Fuente no registrada en la política
"""

from typing import Dict, Any

# ═══════════════════════════════════════════════════════════
# POLÍTICA DE CONFIANZA — Fuente: POLITICA_CONFIANZA_PREDICCIONES.md
# ═══════════════════════════════════════════════════════════

POLITICA_CONFIANZA: Dict[str, Dict[str, Any]] = {
    # ── MUY CONFIABLE (MAPE ≤ 15%) ──
    'GENE_TOTAL':      {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.05, 'usar_intervalos': True,  'disclaimer': False},
    'DEMANDA':         {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.05, 'usar_intervalos': True,  'disclaimer': False},
    'PRECIO_ESCASEZ':  {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.02, 'usar_intervalos': True,  'disclaimer': False},
    'EMBALSES':        {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.01, 'usar_intervalos': True,  'disclaimer': False},
    'EMBALSES_PCT':    {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.05, 'usar_intervalos': True,  'disclaimer': False},
    'PERDIDAS':        {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.15, 'usar_intervalos': True,  'disclaimer': False},
    'Hidráulica':      {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.05, 'usar_intervalos': True,  'disclaimer': False},
    'Biomasa':         {'nivel': 'MUY_CONFIABLE',  'mape_max': 0.10, 'usar_intervalos': True,  'disclaimer': False},

    # ── CONFIABLE (MAPE 15-20%) ──
    'APORTES_HIDRICOS': {'nivel': 'CONFIABLE',     'mape_max': 0.25, 'usar_intervalos': True,  'disclaimer': True},
    'Térmica':          {'nivel': 'CONFIABLE',     'mape_max': 0.20, 'usar_intervalos': True,  'disclaimer': True},
    'Solar':            {'nivel': 'CONFIABLE',     'mape_max': 0.25, 'usar_intervalos': True,  'disclaimer': True},

    # ── ACEPTABLE (MAPE 20-30%) ──
    'Eólica':           {'nivel': 'ACEPTABLE',     'mape_max': 0.30, 'usar_intervalos': True,  'disclaimer': True},

    # ── EXPERIMENTAL (sin holdout) ──
    'PRECIO_BOLSA':     {'nivel': 'EXPERIMENTAL',  'mape_max': None, 'usar_intervalos': False, 'disclaimer': True},
}

# Política por defecto para fuentes no registradas
_POLITICA_DESCONOCIDA: Dict[str, Any] = {
    'nivel': 'DESCONOCIDO',
    'mape_max': None,
    'usar_intervalos': False,
    'disclaimer': True,
}

# Textos de disclaimer por nivel
_DISCLAIMERS: Dict[str, str] = {
    'MUY_CONFIABLE': '',
    'CONFIABLE':     '⚠️ Predicción con precisión moderada. Usar como referencia direccional.',
    'ACEPTABLE':     '⚠️ Alta incertidumbre. Considerar el rango (intervalo) como guía principal.',
    'EXPERIMENTAL':  '🔬 Predicción experimental: pocos datos históricos, sin validación holdout. NO usar para decisiones críticas.',
    'DESCONOCIDO':   '❓ Fuente no reconocida en la política de confianza.',
}


def get_confianza_politica(fuente: str) -> Dict[str, Any]:
    """
    Devuelve la política de confianza para una fuente de predicción.

    Args:
        fuente: Nombre de la fuente (ej. 'GENE_TOTAL', 'PRECIO_BOLSA', 'Hidráulica')

    Returns:
        Dict con: nivel, mape_max, usar_intervalos, disclaimer (bool)
    """
    return POLITICA_CONFIANZA.get(fuente, _POLITICA_DESCONOCIDA.copy())


def obtener_disclaimer(fuente: str) -> str:
    """
    Genera el texto de disclaimer según el nivel de confianza de la fuente.

    Args:
        fuente: Nombre de la fuente de predicción

    Returns:
        Texto del disclaimer (vacío si MUY_CONFIABLE)
    """
    politica = get_confianza_politica(fuente)
    nivel = politica.get('nivel', 'DESCONOCIDO')
    return _DISCLAIMERS.get(nivel, _DISCLAIMERS['DESCONOCIDO'])


def enriquecer_ficha_con_confianza(ficha: dict, fuente_pred: str) -> dict:
    """
    Añade campos de confianza a una ficha de predicción ya construida.
    NO modifica campos existentes; solo agrega campos nuevos opcionales.

    Campos añadidos:
      - fuente_prediccion: str
      - nivel_confianza: str (MUY_CONFIABLE|CONFIABLE|ACEPTABLE|EXPERIMENTAL|DESCONOCIDO)
      - aplicar_disclaimer: bool
      - usar_intervalos: bool
      - disclaimer_confianza: str (texto del disclaimer, vacío si no aplica)

    Args:
        ficha: Dict con la ficha de predicción (se modifica in-place y se retorna)
        fuente_pred: Nombre de la fuente en tabla predictions (ej. 'GENE_TOTAL')

    Returns:
        La misma ficha enriquecida
    """
    politica = get_confianza_politica(fuente_pred)
    ficha['fuente_prediccion'] = fuente_pred
    ficha['nivel_confianza'] = politica['nivel']
    ficha['aplicar_disclaimer'] = politica['disclaimer']
    ficha['usar_intervalos'] = politica['usar_intervalos']
    ficha['disclaimer_confianza'] = obtener_disclaimer(fuente_pred)
    return ficha

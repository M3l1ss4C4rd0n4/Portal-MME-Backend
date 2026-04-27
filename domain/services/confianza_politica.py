"""
Política de Confianza por Fuente de Predicción — FASE 6 (dinámica desde v2)

Módulo que centraliza las reglas de confianza para cada fuente de predicción
del Portal Energético MME.

Clasificación dinámica: cada llamada a get_confianza_politica() consulta el
último mape_expost real de predictions_quality_history (caché TTL 30 min).
La política estática sirve únicamente como fallback cuando no hay datos en BD
(métrica nueva, sin conexión, etc.).

Niveles (basados en mape_expost de producción):
  MUY_CONFIABLE  → mape_expost ≤ 10%
  CONFIABLE      → mape_expost 10–20%
  ACEPTABLE      → mape_expost 20–35%
  EXPERIMENTAL   → mape_expost > 35%  OR  sin datos ex-post en BD
  DESCONOCIDO    → Fuente no registrada y sin datos en BD
"""

import time
import threading
from typing import Dict, Any

# ═══════════════════════════════════════════════════════════
# POLÍTICA ESTÁTICA — fallback cuando no hay datos ex-post
# ═══════════════════════════════════════════════════════════

POLITICA_CONFIANZA: Dict[str, Dict[str, Any]] = {
    # usar_intervalos: si el modelo genera IC fiables para mostrar al usuario
    # disclaimer: si se debe mostrar aviso de incertidumbre por defecto
    'GENE_TOTAL':       {'nivel': 'MUY_CONFIABLE', 'usar_intervalos': True,  'disclaimer': False},
    'DEMANDA':          {'nivel': 'MUY_CONFIABLE', 'usar_intervalos': True,  'disclaimer': False},
    'PRECIO_ESCASEZ':   {'nivel': 'MUY_CONFIABLE', 'usar_intervalos': True,  'disclaimer': False},
    'EMBALSES':         {'nivel': 'MUY_CONFIABLE', 'usar_intervalos': True,  'disclaimer': False},
    'EMBALSES_PCT':     {'nivel': 'MUY_CONFIABLE', 'usar_intervalos': True,  'disclaimer': False},
    'PERDIDAS':         {'nivel': 'MUY_CONFIABLE', 'usar_intervalos': True,  'disclaimer': False},
    'Hidráulica':       {'nivel': 'ACEPTABLE',     'usar_intervalos': True,  'disclaimer': True},
    # Biomasa usa PROPHET_LARGO_PLAZO entrenado con datos sintéticos → MAPE real ~3000%
    # Se mantiene EXPERIMENTAL hasta que P3 corrija la fuente de histórico
    'Biomasa':          {'nivel': 'EXPERIMENTAL',  'usar_intervalos': False, 'disclaimer': True},
    'APORTES_HIDRICOS': {'nivel': 'CONFIABLE',     'usar_intervalos': True,  'disclaimer': True},
    'Térmica':          {'nivel': 'CONFIABLE',     'usar_intervalos': True,  'disclaimer': True},
    'Solar':            {'nivel': 'CONFIABLE',     'usar_intervalos': True,  'disclaimer': True},
    'Eólica':           {'nivel': 'ACEPTABLE',     'usar_intervalos': True,  'disclaimer': True},
    'PRECIO_BOLSA':     {'nivel': 'EXPERIMENTAL',  'usar_intervalos': False, 'disclaimer': True},
}

# Política por defecto para fuentes no registradas
_POLITICA_DESCONOCIDA: Dict[str, Any] = {
    'nivel': 'DESCONOCIDO',
    'usar_intervalos': False,
    'disclaimer': True,
}

# Textos de disclaimer por nivel
_DISCLAIMERS: Dict[str, str] = {
    'MUY_CONFIABLE': '',
    'CONFIABLE':     '⚠️ Predicción con precisión moderada. Usar como referencia direccional.',
    'ACEPTABLE':     '⚠️ Alta incertidumbre. Considerar el rango (intervalo) como guía principal.',
    'EXPERIMENTAL':  '🔬 Modelo con error > 35% en producción real. Usar solo como referencia direccional.',
    'DESCONOCIDO':   '❓ Fuente no reconocida en la política de confianza.',
}

# ═══════════════════════════════════════════════════════════
# CLASIFICACIÓN DINÁMICA — basada en mape_expost real
# ═══════════════════════════════════════════════════════════

# Umbrales (sobre mape_expost en escala 0.0–1.0)
_UMBRAL_MUY_CONFIABLE = 0.10   # ≤ 10%
_UMBRAL_CONFIABLE     = 0.20   # 10–20%
_UMBRAL_ACEPTABLE     = 0.35   # 20–35%
                                # > 35% → EXPERIMENTAL

# Caché en memoria: {fuente: nivel} con TTL de 30 minutos
_cache_lock = threading.Lock()
_cache_niveles: Dict[str, str] = {}
_cache_mapes: Dict[str, float] = {}   # mape_expost real por fuente (para info)
_cache_ts: float = 0.0
_CACHE_TTL_SEG = 1800  # 30 minutos


def _clasificar_por_mape(mape_expost: float) -> str:
    """Devuelve el nivel de confianza según el mape_expost real de producción."""
    if mape_expost <= _UMBRAL_MUY_CONFIABLE:
        return 'MUY_CONFIABLE'
    elif mape_expost <= _UMBRAL_CONFIABLE:
        return 'CONFIABLE'
    elif mape_expost <= _UMBRAL_ACEPTABLE:
        return 'ACEPTABLE'
    else:
        return 'EXPERIMENTAL'


def _cargar_desde_bd() -> Dict[str, Dict[str, float]]:
    """
    Consulta el último mape_expost por fuente desde predictions_quality_history.
    Devuelve {fuente: {'nivel': str, 'mape_expost': float}} o {} si falla.
    """
    try:
        from infrastructure.database.manager import db_manager
        df = db_manager.query_df("""
            SELECT DISTINCT ON (fuente)
                fuente,
                mape_expost
            FROM predictions_quality_history
            WHERE mape_expost IS NOT NULL
            ORDER BY fuente, fecha_evaluacion DESC
        """)
        if df is None or df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            mape = float(row['mape_expost'])
            result[str(row['fuente'])] = {
                'nivel': _clasificar_por_mape(mape),
                'mape_expost': mape,
            }
        return result
    except Exception:
        return {}


def _refrescar_cache_si_necesario() -> None:
    """Recarga el caché desde BD si han pasado más de 30 min o está vacío."""
    global _cache_niveles, _cache_mapes, _cache_ts
    now = time.monotonic()
    with _cache_lock:
        if now - _cache_ts < _CACHE_TTL_SEG and _cache_niveles:
            return
        datos = _cargar_desde_bd()
        if datos:  # solo actualizar si BD respondió correctamente
            _cache_niveles = {f: v['nivel'] for f, v in datos.items()}
            _cache_mapes   = {f: v['mape_expost'] for f, v in datos.items()}
            _cache_ts = now


def get_mape_expost_actual(fuente: str) -> float | None:
    """Devuelve el último mape_expost conocido para la fuente (0.0–N.0, escala ratio)."""
    _refrescar_cache_si_necesario()
    return _cache_mapes.get(fuente)


def get_confianza_politica(fuente: str) -> Dict[str, Any]:
    """
    Devuelve la política de confianza para una fuente de predicción.
    El nivel se calcula dinámicamente desde el mape_expost real en BD.
    Si no hay datos ex-post (métrica nueva, BD no disponible), usa el fallback estático.

    Args:
        fuente: Nombre de la fuente (ej. 'GENE_TOTAL', 'PRECIO_BOLSA', 'Hidráulica')

    Returns:
        Dict con: nivel, usar_intervalos, disclaimer (bool), mape_expost_actual (float|None)
    """
    _refrescar_cache_si_necesario()

    # Base estática (define usar_intervalos y disclaimer de diseño)
    base = POLITICA_CONFIANZA.get(fuente, _POLITICA_DESCONOCIDA.copy()).copy()

    # Sobrescribir nivel con clasificación dinámica si hay dato ex-post real
    if fuente in _cache_niveles:
        nivel_real = _cache_niveles[fuente]
        base['nivel'] = nivel_real
        # Si el modelo degradó en producción, forzar disclaimer
        if nivel_real in ('ACEPTABLE', 'EXPERIMENTAL'):
            base['disclaimer'] = True

    base['mape_expost_actual'] = _cache_mapes.get(fuente)
    # Compatibilidad con callers que usan pol['mape_max']
    base.setdefault('mape_max', base.get('mape_expost_actual'))
    return base


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

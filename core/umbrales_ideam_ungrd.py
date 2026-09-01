"""
Umbrales oficiales IDEAM/UNGRD para riesgo de UN embalse individual, por
nivel de volumen útil — seguridad de presas / riesgo de desborde y sequía.

Fuente: IDEAM (Instituto de Hidrología, Meteorología y Estudios Ambientales)
y UNGRD (Unidad Nacional para la Gestión del Riesgo de Desastres).

MARCO DISTINTO del Estatuto CREG (core/umbrales_oficiales.py): este módulo
clasifica el riesgo de UN embalse individual por seguridad de presa
(desborde/sequía puntual), no la condición regulatoria de desabastecimiento
eléctrico del SIN agregado (Índice NE vs. senda de referencia). Un mismo %
de embalse puede ser "favorable" en el marco CREG y "vigilancia" en este
marco IDEAM/UNGRD — nunca se fusionan bajo una sola etiqueta.

Unificado 2026-08-26 a pedido explícito del usuario: antes existían 5
implementaciones independientes de este mismo concepto, cada una con
umbrales propios e inconsistentes entre sí, ninguna citada:
  - domain/services/orchestrator/handlers/anomalias_handler.py (la única
    con cita real — origen de los umbrales de este módulo)
  - interface/pages/hidrologia/utils.py::calcular_semaforo_embalse()
  - interface/pages/hidrologia/utils.py::clasificar_riesgo_embalse()
  - interface/pages/hidrologia/data_services.py::calcular_semaforo_embalse_local()
  - interface/pages/hidrologia/data_services.py::clasificar_riesgo_embalse_local()
  - whatsapp_bot/services/informe_charts.py::_clasificar_riesgo_embalse()
Las 5 versiones anteriores también incorporaban un factor de "participación
estratégica" del embalse en el sistema nacional — sin ninguna fuente que lo
respaldara. Se retiró ese factor: este módulo clasifica únicamente por %
de volumen útil, que es exactamente lo que IDEAM/UNGRD sí publican.

Réplica en TypeScript: portal-direccion-mme/src/lib/embalse-utils.ts.
"""
from typing import Tuple


def clasificar_riesgo_embalse_ideam_ungrd(volumen_util_pct: float) -> Tuple[str, str, str, str]:
    """
    Clasifica el riesgo de UN embalse individual según su % de volumen útil.

    Args:
        volumen_util_pct: % de volumen útil del embalse (0-100).

    Returns:
        (nivel, color_hex, emoji, mensaje)
        nivel: 'CRÍTICO — RACIONAMIENTO' | 'ALERTA — NIVEL BAJO' | 'NORMAL' |
               'ALERTA — NIVEL ELEVADO' | 'ALERTA — NIVEL MUY ALTO' |
               'CRÍTICO — DESBORDAMIENTO'
    """
    v = float(volumen_util_pct)

    if v < 27:
        return (
            'CRÍTICO — RACIONAMIENTO', '#EF4444', '🔴',
            f'Nivel crítico ({v:.1f}%) — riesgo de racionamiento/apagón (IDEAM).',
        )
    if v < 40:
        return (
            'ALERTA — NIVEL BAJO', '#F97316', '🟡',
            f'Nivel bajo ({v:.1f}%) — alerta de seguimiento (IDEAM).',
        )
    if v <= 80:
        return (
            'NORMAL', '#22C55E', '🟢',
            f'Nivel dentro del rango de operación estable ({v:.1f}%).',
        )
    if v <= 90:
        return (
            'ALERTA — NIVEL ELEVADO', '#F59E0B', '🟡',
            f'Nivel elevado ({v:.1f}%) — vigilancia activa, monitorear caudales de entrada (UNGRD).',
        )
    if v <= 95:
        return (
            'ALERTA — NIVEL MUY ALTO', '#F97316', '🟠',
            f'Nivel muy alto ({v:.1f}%) — preparar descargas preventivas (UNGRD).',
        )
    return (
        'CRÍTICO — DESBORDAMIENTO', '#EF4444', '🔴',
        f'Nivel crítico ({v:.1f}%) — riesgo de desbordamiento inminente (UNGRD).',
    )

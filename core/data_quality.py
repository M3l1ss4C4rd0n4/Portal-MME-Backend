"""
Completitud de los datos de XM — punto único de verdad.

XM publica el día en curso de forma incremental y **no expone ningún
indicador de completitud**: la respuesta de `servapibi.xm.com.co` solo trae
`Id/Name/StartDate/EndDate`, sin versión ni bandera de preliminar/definitivo.
Peor, el día parcial **tiene las 24 horas presentes con valores reducidos**,
así que contar horas tampoco sirve.

La señal real es **estructural**: cuántos agentes/recursos reportaron. En los
días parciales medidos el conteo cae al 63-68 % de la mediana, mientras que un
día completo nunca baja del 92 %. El corte es nítido.

Por qué NO se usa el valor:
    Un criterio del tipo `valor < 0.5 × mediana` —el que más se repetía en el
    código— marca como "parcial" ~40 días buenos de `PPPrecBolsNaci` y 8 de
    `AporEner`, porque esas series sí caen a la mitad legítimamente. El
    criterio estructural no confunde una caída de precio con un dato faltante.

Por qué NO se usa un rezago fijo:
    `Gene` está completo en D-1 mientras `DemaReal` del mismo día está al 21 %,
    y hay parciales que duran 4 días o más. Un rezago único que cubriera
    `DemaReal` tiraría 4 días de dato bueno de `Gene`. El rezago se deriva del
    dato, no se configura.

Este módulo reemplaza los 11 criterios distintos e incompatibles que convivían
en el repositorio (umbrales 0,15× / 0,2× / 0,4× / 0,5× / 0,8×, pisos absolutos
de 60/100/150 GWh y rezagos fijos de 2 o 3 días).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Fracción del baseline por debajo de la cual el día se considera incompleto.
# Medido: días completos ≥ 92 %, días parciales ≤ 68 %. 0,8 cae en el hueco.
UMBRAL_COMPLETITUD = 0.80

# Días hacia atrás que se exploran buscando el último día completo.
MAX_RETROCESO_DIAS = 10

# La cola reciente se excluye del baseline: si se incluyera, varios días
# parciales seguidos bajarían la mediana y se volverían "normales".
DIAS_COLA_EXCLUIDOS = 5

# Ventana para estimar el baseline de recursos esperados.
DIAS_BASELINE = 30

_CACHE_TTL_SEG = 300
_cache: Dict[str, Tuple[float, object]] = {}


@dataclass(frozen=True)
class Completitud:
    """Resultado de evaluar un día. `ratio` es recursos / baseline."""
    fecha: date
    recursos: int
    baseline: float
    ratio: float
    entidad_evaluada: str

    @property
    def completo(self) -> bool:
        return self.ratio >= UMBRAL_COMPLETITUD


def _cached(clave: str, calcular):
    ahora = time.time()
    hit = _cache.get(clave)
    if hit and ahora - hit[0] < _CACHE_TTL_SEG:
        return hit[1]
    valor = calcular()
    _cache[clave] = (ahora, valor)
    return valor


def limpiar_cache() -> None:
    """Para los tests y para forzar relectura tras un ETL."""
    _cache.clear()


def entidad_desagregada(metrica: str) -> Optional[str]:
    """
    Entidad de la métrica que sirve como señal de completitud.

    Toda métrica tiene una fila agregada con `entidad='Sistema'` y un solo
    recurso, así que a ese nivel el conteo siempre vale 1 y no dice nada. La
    señal vive en la entidad desagregada de la MISMA métrica: `DemaReal/Agente`
    cae a 93 de 140 agentes el mismo día en que `DemaReal/Sistema` marca 53 GWh
    en vez de 250.

    Se descubre sola (la entidad con más recursos), en vez de mantener una
    tabla de correspondencias que se desactualizaría.
    """
    def _calcular():
        from infrastructure.database.manager import db_manager
        df = db_manager.query_df(
            """
            SELECT entidad, COUNT(DISTINCT recurso) AS n
            FROM sector_energetico.metrics
            WHERE metrica = %(m)s
              AND fecha > CURRENT_DATE - 45
              AND fecha <= CURRENT_DATE
              AND entidad <> 'Sistema'
            GROUP BY entidad
            ORDER BY n DESC
            LIMIT 1
            """,
            {"m": metrica},
        )
        if df is None or df.empty or int(df.iloc[0]["n"]) <= 1:
            return None
        return str(df.iloc[0]["entidad"])

    return _cached(f"ent:{metrica}", _calcular)


def _conteos(metrica: str, entidad: str):
    def _calcular():
        from infrastructure.database.manager import db_manager
        return db_manager.query_df(
            """
            SELECT fecha::date AS fecha, COUNT(DISTINCT recurso) AS n
            FROM sector_energetico.metrics
            WHERE metrica = %(m)s
              AND entidad = %(e)s
              AND fecha <= CURRENT_DATE
              AND fecha > CURRENT_DATE - %(v)s
            GROUP BY 1
            ORDER BY 1 DESC
            """,
            {"m": metrica, "e": entidad, "v": DIAS_BASELINE + MAX_RETROCESO_DIAS},
        )

    return _cached(f"cnt:{metrica}:{entidad}", _calcular)


def completitud_del_dia(
    metrica: str, fecha: date, entidad: Optional[str] = None
) -> Optional[Completitud]:
    """
    Evalúa qué tan completo está un día. None si no hay con qué comparar.

    `entidad` se infiere si no se pasa. Si se pasa 'Sistema', se traduce a la
    entidad desagregada, que es donde está la señal.
    """
    señal = entidad if entidad and entidad != "Sistema" else entidad_desagregada(metrica)
    if not señal:
        return None

    df = _conteos(metrica, señal)
    if df is None or df.empty:
        return None

    fila = df[df["fecha"] == fecha]
    if fila.empty:
        return Completitud(fecha, 0, 0.0, 0.0, señal)

    recursos = int(fila.iloc[0]["n"])
    base_df = df[df["fecha"] <= fecha][DIAS_COLA_EXCLUIDOS:]
    if len(base_df) < 5:
        return None
    baseline = float(base_df["n"].median())
    if baseline <= 0:
        return None

    return Completitud(fecha, recursos, baseline, recursos / baseline, señal)


def ultimo_dia_completo(
    metrica: str,
    entidad: Optional[str] = None,
    max_retroceso: int = MAX_RETROCESO_DIAS,
) -> Optional[date]:
    """
    Fecha más reciente con datos completos de esa métrica, o None.

    Es la función que no existía y que cada consumidor resolvía a su manera.
    Usarla en lugar de `MAX(fecha)` o de un rezago fijo.
    """
    señal = entidad if entidad and entidad != "Sistema" else entidad_desagregada(metrica)
    if not señal:
        # Métrica sin desagregación: no hay señal estructural disponible.
        # Se devuelve None para que quien llame decida, en vez de mentir.
        logger.debug(
            "[CALIDAD] %s no tiene entidad desagregada; no se puede evaluar "
            "completitud estructural.", metrica,
        )
        return None

    df = _conteos(metrica, señal)
    if df is None or df.empty:
        return None

    for i, fila in enumerate(df.itertuples()):
        if i >= max_retroceso:
            break
        c = completitud_del_dia(metrica, fila.fecha, señal)
        if c and c.completo:
            if i > 0:
                logger.info(
                    "[CALIDAD] %s/%s: se retrocede %d día(s) hasta %s "
                    "(los más recientes venían incompletos).",
                    metrica, señal, i, fila.fecha,
                )
            return fila.fecha

    logger.warning(
        "[CALIDAD] %s/%s: ningún día completo en los últimos %d. XM puede "
        "estar publicando con retraso.", metrica, señal, max_retroceso,
    )
    return None

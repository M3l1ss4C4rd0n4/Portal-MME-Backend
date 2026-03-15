"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║             CONFIG DYNAMIC — Configuración dinámica de cargos CREG            ║
║                                                                               ║
║  Complementa core/config.py con:                                             ║
║  - Metadatos de vigencia para cada componente regulado (CREGComponent)       ║
║  - Cache en memoria configurable (default 6 h)                               ║
║  - Validación de rangos contra valores históricos observados                 ║
║  - Obtención de TRM desde API pública de datos.gov.co                        ║
║  - Fallback graceful hacia get_settings() si la API falla                   ║
║                                                                               ║
║  Fuentes oficiales:                                                          ║
║  - Cargos T/D/C: XM S.A. E.S.P. Boletín LAC (mercado mayorista)            ║
║    https://www.xm.com.co/publicaciones/liquidaciones                         ║
║  - TRM: Banco de la República vía datos.gov.co                               ║
║    https://www.datos.gov.co/resource/32sa-8pi9.json                         ║
║  - Rangos de referencia 2025: SSPD Boletín Tarifario (minorista)            ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import requests

from core.config import get_settings

logger = logging.getLogger(__name__)

_LOG = "[CONFIG_DYNAMIC]"


# ═══════════════════════════════════════════════════════════════════════════════
# DATACLASS — Componente CREG con metadatos de vigencia
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CREGComponent:
    """
    Componente del CU con metadatos de vigencia y trazabilidad regulatoria.

    Attributes:
        value:       Valor en la unidad especificada por ``unit``.
        unit:        ``'cop_kwh'`` (COP/kWh) o ``'percentage'``.
        valid_from:  Fecha desde la que el valor está vigente.
        valid_until: Fecha de expiración (None = indefinido).
        resolution:  Resolución CREG de origen, ej. ``"CREG 119 de 2007"``.
        source:      Fuente del dato, ej. ``"XM-LAC-STN"``.
    """

    value: float
    unit: str                          # 'cop_kwh' | 'percentage'
    valid_from: datetime
    valid_until: Optional[datetime] = None
    resolution: str = ""
    source: str = ""

    def is_valid(self) -> bool:
        """True si el componente está dentro de su período de vigencia."""
        now = datetime.now()
        after_start = self.valid_from <= now
        before_end = self.valid_until is None or now <= self.valid_until
        return after_start and before_end

    def age_days(self) -> int:
        """Días transcurridos desde ``valid_from``."""
        return (datetime.now() - self.valid_from).days


# ═══════════════════════════════════════════════════════════════════════════════
# CLASE PRINCIPAL — DynamicConfig
# ═══════════════════════════════════════════════════════════════════════════════

class DynamicConfig:
    """
    Configuración dinámica con cache en memoria y fallback a get_settings().

    JERARQUÍA DE PRIORIDAD:
        1. get_settings() (Pydantic / .env) — fuente principal siempre disponible
        2. API datos.gov.co para TRM — actualiza cache cada CACHE_DURATION horas
        3. Valores por defecto (_defaults) — último recurso documentado

    VALORES DE REFERENCIA 2025 (XM Boletín LAC):
    ┌─────────┬──────────────────┬────────────────────────────────────────────┐
    │ Cargo   │ Rango histórico  │ Nota                                       │
    ├─────────┼──────────────────┼────────────────────────────────────────────┤
    │ T (STN) │  6– 12 COP/kWh  │ Solo red de transmisión nacional           │
    │ D (SDL) │ 25– 55 COP/kWh  │ Promedio nacional ponderado por energía    │
    │ C       │  8– 18 COP/kWh  │ Margen comercialización frontera mayorista │
    │ CU tot  │ 150–1800 COP/kWh│ 150 La Niña → 1800 El Niño extremo        │
    └─────────┴──────────────────┴────────────────────────────────────────────┘

    Estos son valores del MERCADO MAYORISTA (Boletín LAC).  No confundir con
    el Boletín Tarifario SSPD que publica cargos al usuario final (3-10× más
    altos porque incluyen STR, DTUN, contribuciones y márgenes minoristas).
    """

    # Duración de cache en memoria para TRM (API externa)
    CACHE_DURATION: timedelta = timedelta(hours=6)

    # URL pública TRM — datos abiertos Colombia (Banco de la República)
    TRM_API_URL: str = (
        "https://www.datos.gov.co/resource/32sa-8pi9.json"
        "?$limit=1&$order=vigenciadesde+DESC"
    )

    # Timeout seguro para API externa
    _API_TIMEOUT: int = 10

    # Rangos esperados por componente para auditoría de valores
    _VALID_RANGES: Dict[str, Tuple[float, float]] = {
        "T":        (4.0,   20.0),
        "D":        (15.0,  80.0),
        "C":        (5.0,   25.0),
        "CU_TOTAL": (150.0, 1_800.0),
        "TRM":      (3_500.0, 5_500.0),
    }

    def __init__(self) -> None:
        # Cache: clave → (valor, timestamp)
        self._cache: Dict[str, Tuple[float, datetime]] = {}

        settings = get_settings()

        # Valores por defecto construidos a partir de get_settings()
        # para garantizar coherencia con .env cuando exista
        self._defaults: Dict[str, CREGComponent] = {
            "T": CREGComponent(
                value=settings.CARGO_TRANSMISION_COP_KWH,
                unit="cop_kwh",
                valid_from=datetime(2025, 1, 1),
                resolution="CREG 011 de 2009",
                source="XM-LAC-STN",
            ),
            "D": CREGComponent(
                value=settings.CARGO_DISTRIBUCION_COP_KWH,
                unit="cop_kwh",
                valid_from=datetime(2025, 1, 1),
                resolution="CREG 015 de 2018",
                source="XM-LAC-SDL",
            ),
            "C": CREGComponent(
                value=settings.CARGO_COMERCIALIZACION_COP_KWH,
                unit="cop_kwh",
                valid_from=datetime(2025, 1, 1),
                resolution="CREG 180 de 2010",
                source="XM-LAC-COM",
            ),
        }

        self._trm_fallback: float = settings.TRM_REF_COP_USD

        logger.info(
            "%s Inicializado — T=%.2f D=%.2f C=%.2f TRM_fallback=%.0f",
            _LOG,
            self._defaults["T"].value,
            self._defaults["D"].value,
            self._defaults["C"].value,
            self._trm_fallback,
        )

    # ════════════════════════════════════════════════════════════
    # CACHE
    # ════════════════════════════════════════════════════════════

    def _cached(self, key: str) -> Optional[float]:
        """Retorna el valor del cache si no ha expirado, de lo contrario None."""
        if key in self._cache:
            value, ts = self._cache[key]
            if (datetime.now() - ts) < self.CACHE_DURATION:
                return value
        return None

    def _store(self, key: str, value: float) -> None:
        """Almacena un valor en el cache con timestamp actual."""
        self._cache[key] = (value, datetime.now())

    # ════════════════════════════════════════════════════════════
    # TRM
    # ════════════════════════════════════════════════════════════

    def get_trm(self) -> float:
        """
        Obtiene la TRM vigente desde la API pública del Banco de la República.

        Fallback secuencial:
            1. Cache en memoria (máx CACHE_DURATION h desde última consulta)
            2. API datos.gov.co (``TRM_API_URL``)
            3. ``settings.TRM_REF_COP_USD`` (valor en .env o default pydantic)

        Returns:
            TRM en COP/USD.
        """
        cached = self._cached("TRM")
        if cached is not None:
            return cached

        try:
            resp = requests.get(self.TRM_API_URL, timeout=self._API_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data:
                trm = float(data[0]["valor"])
                self._store("TRM", trm)
                logger.info("%s TRM actualizada desde API: %.2f COP/USD", _LOG, trm)
                return trm
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s No se pudo obtener TRM desde API (%s). Usando fallback.", _LOG, exc
            )

        logger.warning(
            "%s Usando TRM de referencia: %.2f COP/USD", _LOG, self._trm_fallback
        )
        return self._trm_fallback

    # ════════════════════════════════════════════════════════════
    # COMPONENTES CREG
    # ════════════════════════════════════════════════════════════

    def get_component(self, name: str) -> CREGComponent:
        """
        Obtiene un componente CREG con sus metadatos de vigencia.

        Actualmente lee desde los defaults (bindeados a get_settings()),
        lo que garantiza que los valores en .env tienen efecto inmediato.
        En versiones futuras podrá cargar desde una tabla ``creg_cargos``
        en PostgreSQL para permitir actualizaciones sin redeploy.

        Args:
            name: ``'T'``, ``'D'``  o ``'C'``.

        Returns:
            CREGComponent con el valor vigente y trazabilidad.

        Raises:
            ValueError: Si ``name`` no está en la configuración.
        """
        if name not in self._defaults:
            raise ValueError(
                f"Componente '{name}' no encontrado. Opciones: {list(self._defaults)}"
            )

        comp = self._defaults[name]
        if comp.age_days() > 365:
            logger.warning(
                "%s Componente '%s' = %.2f tiene %d días de antigüedad. "
                "Verificar Boletín LAC en xm.com.co.",
                _LOG, name, comp.value, comp.age_days(),
            )
        return comp

    # ════════════════════════════════════════════════════════════
    # VALIDACIÓN CONTRA RANGOS HISTÓRICOS
    # ════════════════════════════════════════════════════════════

    def validate_against_official(self, component_name: str, value: float) -> Dict:
        """
        Compara un valor contra los rangos históricos observados en el
        mercado mayorista colombiano.

        Útil en tareas de auditoría o al actualizar cargos desde el Boletín LAC.

        Args:
            component_name: ``'T'``, ``'D'``, ``'C'``, ``'CU_TOTAL'`` o ``'TRM'``.
            value:          Valor a validar.

        Returns:
            Dict con claves ``value``, ``range_expected`` (tuple),
            ``status`` (``'ok'`` | ``'warning'`` | ``'unknown'``) y ``message``.
        """
        if component_name not in self._VALID_RANGES:
            return {
                "value": value,
                "range_expected": None,
                "status": "unknown",
                "message": f"Sin rango de referencia para '{component_name}'.",
            }

        lo, hi = self._VALID_RANGES[component_name]
        ok = lo <= value <= hi
        return {
            "value": value,
            "range_expected": (lo, hi),
            "status": "ok" if ok else "warning",
            "message": (
                f"'{component_name}' = {value:.2f} está "
                f"{'dentro' if ok else 'FUERA'} del rango esperado "
                f"[{lo}, {hi}] para el mercado mayorista colombiano."
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_dynamic_config: Optional[DynamicConfig] = None


def get_dynamic_config() -> DynamicConfig:
    """Retorna la instancia singleton de DynamicConfig (lazy init)."""
    global _dynamic_config
    if _dynamic_config is None:
        _dynamic_config = DynamicConfig()
    return _dynamic_config

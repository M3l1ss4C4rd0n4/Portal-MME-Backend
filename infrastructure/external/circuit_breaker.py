"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                          XM API CIRCUIT BREAKER                              ║
║                                                                              ║
║  Implementa patrón Circuit Breaker para la API XM (servapibi.xm.com.co)    ║
║  Estados: CLOSED → OPEN (3 fallos) → HALF_OPEN (5 min timeout)             ║
║                                                                              ║
║  Fase 8 — Hardening & Resiliencia                                           ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import time
import threading
import logging
from enum import Enum
from typing import Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Estados del circuit breaker"""
    CLOSED = "closed"       # Normal — requests pasan
    OPEN = "open"           # Cortocircuito — requests rechazadas
    HALF_OPEN = "half_open" # Probando — un request de prueba


@dataclass
class CircuitStats:
    """Estadísticas del circuit breaker"""
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    times_opened: int = 0
    last_state_change: Optional[float] = None


class XMCircuitBreaker:
    """
    Circuit Breaker para la API XM.
    
    Protege al sistema de cascada de fallos cuando la API XM no responde.
    
    Configuración por defecto:
    - failure_threshold: 3 fallos consecutivos → abre el circuito
    - recovery_timeout: 300 segundos (5 min) → intenta HALF_OPEN
    - success_threshold: 2 éxitos en HALF_OPEN → cierra el circuito
    
    Uso:
        breaker = get_xm_circuit_breaker()
        
        if not breaker.allow_request():
            return None  # Circuit is OPEN
        
        try:
            result = call_xm_api(...)
            breaker.record_success()
            return result
        except Exception:
            breaker.record_failure()
            raise
    """
    
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 300,
        success_threshold: int = 2,
        on_open: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
    ):
        self._state = CircuitState.CLOSED
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold
        self._consecutive_failures = 0
        self._consecutive_successes_half_open = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()
        self._on_open = on_open
        self._on_close = on_close
        self.stats = CircuitStats()
        
        logger.info(
            f"[CircuitBreaker] Inicializado: "
            f"threshold={failure_threshold}, "
            f"timeout={recovery_timeout}s, "
            f"success_threshold={success_threshold}"
        )
    
    @property
    def state(self) -> CircuitState:
        """Estado actual del circuit breaker"""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed → transition to HALF_OPEN
                if self._last_failure_time and \
                   (time.time() - self._last_failure_time) >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._consecutive_successes_half_open = 0
                    self.stats.last_state_change = time.time()
                    logger.info("[CircuitBreaker] OPEN → HALF_OPEN (recovery timeout elapsed)")
            return self._state
    
    @property
    def state_name(self) -> str:
        """Nombre del estado actual (para health checks)"""
        return self.state.value
    
    def allow_request(self) -> bool:
        """
        ¿Se permite hacer una request a la API XM?
        
        Returns:
            True si el circuito permite la request (CLOSED o HALF_OPEN)
        """
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        elif current == CircuitState.HALF_OPEN:
            return True  # Allow test request
        else:
            # OPEN — block request
            logger.warning(
                f"[CircuitBreaker] Request BLOQUEADA — circuito ABIERTO "
                f"(fallos consecutivos: {self._consecutive_failures}, "
                f"reapertura en {self._seconds_until_recovery():.0f}s)"
            )
            return False
    
    def record_success(self) -> None:
        """Registra una llamada exitosa a la API XM"""
        with self._lock:
            self.stats.total_calls += 1
            self.stats.total_successes += 1
            self.stats.last_success_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                self._consecutive_successes_half_open += 1
                if self._consecutive_successes_half_open >= self._success_threshold:
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._consecutive_successes_half_open = 0
                    self.stats.last_state_change = time.time()
                    logger.info("[CircuitBreaker] HALF_OPEN → CLOSED (recuperado)")
                    if self._on_close:
                        try:
                            self._on_close()
                        except Exception:
                            pass
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0
    
    def record_failure(self, error: Optional[Exception] = None) -> None:
        """Registra una llamada fallida a la API XM"""
        with self._lock:
            self.stats.total_calls += 1
            self.stats.total_failures += 1
            self.stats.last_failure_time = time.time()
            self._consecutive_failures += 1
            self._last_failure_time = time.time()
            self.stats.consecutive_failures = self._consecutive_failures
            
            error_msg = str(error) if error else "unknown"
            
            if self._state == CircuitState.HALF_OPEN:
                # Fallo en HALF_OPEN → volver a OPEN
                self._state = CircuitState.OPEN
                self._consecutive_successes_half_open = 0
                self.stats.last_state_change = time.time()
                self.stats.times_opened += 1
                logger.warning(
                    f"[CircuitBreaker] HALF_OPEN → OPEN (fallo en prueba: {error_msg})"
                )
                self._notify_open(error_msg)
                
            elif self._state == CircuitState.CLOSED:
                if self._consecutive_failures >= self._failure_threshold:
                    self._state = CircuitState.OPEN
                    self.stats.last_state_change = time.time()
                    self.stats.times_opened += 1
                    logger.error(
                        f"[CircuitBreaker] CLOSED → OPEN "
                        f"({self._consecutive_failures} fallos consecutivos: {error_msg})"
                    )
                    self._notify_open(error_msg)
                else:
                    logger.warning(
                        f"[CircuitBreaker] Fallo {self._consecutive_failures}/"
                        f"{self._failure_threshold}: {error_msg}"
                    )
    
    def get_status(self) -> dict:
        """Devuelve estado completo para health check"""
        current = self.state
        return {
            "state": current.value,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self._failure_threshold,
            "recovery_timeout_s": self._recovery_timeout,
            "seconds_until_recovery": self._seconds_until_recovery() if current == CircuitState.OPEN else None,
            "stats": {
                "total_calls": self.stats.total_calls,
                "total_failures": self.stats.total_failures,
                "total_successes": self.stats.total_successes,
                "times_opened": self.stats.times_opened,
            }
        }
    
    def force_close(self) -> None:
        """Fuerza el cierre del circuito (uso administrativo)"""
        with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._consecutive_successes_half_open = 0
            self.stats.last_state_change = time.time()
            logger.info(f"[CircuitBreaker] FORCE CLOSE: {old_state.value} → CLOSED")
    
    def _seconds_until_recovery(self) -> float:
        """Segundos restantes hasta que intente HALF_OPEN"""
        if self._last_failure_time is None:
            return 0
        elapsed = time.time() - self._last_failure_time
        remaining = self._recovery_timeout - elapsed
        return max(0, remaining)
    
    def _notify_open(self, error_msg: str) -> None:
        """Notifica cuando el circuito se abre (Telegram alert)"""
        if self._on_open:
            try:
                self._on_open(error_msg)
            except Exception as e:
                logger.error(f"[CircuitBreaker] Error en callback on_open: {e}")
        
        # Intentar enviar alerta por Telegram
        try:
            _send_telegram_alert(
                f"🔴 CIRCUIT BREAKER ABIERTO\n\n"
                f"API XM no responde después de {self._failure_threshold} fallos.\n"
                f"Último error: {error_msg[:200]}\n"
                f"Reintento automático en {self._recovery_timeout}s.\n\n"
                f"Total aperturas: {self.stats.times_opened}"
            )
        except Exception:
            pass  # Best effort


def _send_telegram_alert(message: str) -> None:
    """Envía alerta por Telegram (best effort)"""
    try:
        import requests
        from core.config import settings
        
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
        
        if not bot_token or not chat_id:
            return
        
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=5
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════

_xm_circuit_breaker: Optional[XMCircuitBreaker] = None
_cb_lock = threading.Lock()


def get_xm_circuit_breaker() -> XMCircuitBreaker:
    """
    Obtiene el singleton del circuit breaker para la API XM.
    
    Returns:
        XMCircuitBreaker configurado con:
        - 3 fallos → OPEN
        - 5 min recovery timeout
        - 2 éxitos en HALF_OPEN → CLOSED
    """
    global _xm_circuit_breaker
    if _xm_circuit_breaker is None:
        with _cb_lock:
            if _xm_circuit_breaker is None:
                _xm_circuit_breaker = XMCircuitBreaker(
                    failure_threshold=3,
                    recovery_timeout=300,
                    success_threshold=2,
                )
    return _xm_circuit_breaker

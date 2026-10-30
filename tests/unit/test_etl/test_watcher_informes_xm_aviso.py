"""El aviso de informes XM incompletos está apagado mientras XM no publique.

XM dejó de publicar sus informes diarios (2026-10-30). Que falten dejó de ser
una anomalía, así que el aviso diario solo llenaba buzones. Lo que NO se puede
apagar es el watcher: de él dependen el catálogo del portal y su propio latido.
"""
from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit


def _watcher(monkeypatch, valor=None):
    if valor is None:
        monkeypatch.delenv("ALERTA_INFORMES_XM", raising=False)
    else:
        monkeypatch.setenv("ALERTA_INFORMES_XM", valor)
    import etl.etl_informes_diarios_watcher as w

    return importlib.reload(w)


def test_por_defecto_el_aviso_esta_apagado(monkeypatch):
    assert _watcher(monkeypatch).ALERTA_INFORMES_XM is False


@pytest.mark.parametrize("valor", ["true", "True", "1", "yes", "on"])
def test_se_puede_reactivar_cuando_xm_vuelva(monkeypatch, valor):
    assert _watcher(monkeypatch, valor).ALERTA_INFORMES_XM is True


@pytest.mark.parametrize("valor", ["false", "0", "no", "off", ""])
def test_cualquier_forma_de_apagarlo_vale(monkeypatch, valor):
    assert _watcher(monkeypatch, valor).ALERTA_INFORMES_XM is False


def test_apagado_no_manda_correo_pero_deja_constancia_en_el_log(monkeypatch):
    """Si alguien pregunta por qué no llegó el aviso, la respuesta está en el log.

    No se usa `caplog`: el logger del watcher no propaga a la raíz, así que la
    captura por defecto de pytest sale vacía aunque la línea sí se emita.
    """
    import logging

    w = _watcher(monkeypatch, "false")
    enviados = []
    monkeypatch.setattr(w, "_send_incomplete_alert", lambda p, r: enviados.append(p))

    lineas: list[str] = []

    class _Captura(logging.Handler):
        def emit(self, record):
            lineas.append(record.getMessage())

    handler = _Captura()
    w.logger.addHandler(handler)
    try:
        _correr_watcher(w, monkeypatch)
    finally:
        w.logger.removeHandler(handler)

    assert enviados == [], "no puede salir ningún correo"
    assert any("aviso está apagado" in l for l in lineas)


def test_encendido_si_manda_el_correo(monkeypatch):
    w = _watcher(monkeypatch, "true")
    enviados = []
    monkeypatch.setattr(w, "_send_incomplete_alert", lambda p, r: enviados.append(p))

    _correr_watcher(w, monkeypatch)

    assert enviados == [["Variables operativas"]]


def test_el_watcher_sigue_guardando_su_estado_con_el_aviso_apagado(monkeypatch):
    """Ese archivo es lo que vigila el latido: sin él, falso positivo."""
    w = _watcher(monkeypatch, "false")
    guardados = []
    monkeypatch.setattr(w, "_send_incomplete_alert", lambda p, r: None)
    monkeypatch.setattr(w, "_save_state", lambda s: guardados.append(s))

    _correr_watcher(w, monkeypatch, guardar_real=False)

    assert len(guardados) == 1


def _correr_watcher(w, monkeypatch, guardar_real=True):
    """Ejecuta check_informes_diarios con SharePoint y disco sustituidos."""
    from datetime import datetime

    import sys
    import types

    resumen = {
        "fechaConsulta": "2026-10-30",
        "completosDelDia": 0,
        "totalTipos": 3,
        "pendientes": ["Variables operativas"],
    }
    falso = types.ModuleType("api.v1.routes.reports")
    falso.scan_informes_diarios_status = lambda d: {
        "resumen": resumen, "fingerprint": {"x": 1}
    }
    falso.invalidate_informes_diarios_cache = lambda: None
    monkeypatch.setitem(sys.modules, "api.v1.routes.reports", falso)

    monkeypatch.setattr(w, "_load_state", lambda: {})
    if guardar_real:
        monkeypatch.setattr(w, "_save_state", lambda s: None)

    class _Ahora(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 30, 11, 0, tzinfo=tz)

    monkeypatch.setattr(w, "datetime", _Ahora)
    w.check_informes_diarios()

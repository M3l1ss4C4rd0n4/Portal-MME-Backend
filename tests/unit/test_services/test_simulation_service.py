"""
Tests unitarios para SimulationService — FASE 6.
6 tests requeridos:
  1. baseline_delta_zero: parámetros base → Δ ≈ 0
  2. precio_sube_cu_sube: precio_bolsa_factor > 1 → CU sube
  3. precio_baja_cu_baja: precio_bolsa_factor < 1 → CU baja
  4. advertencia_crisis: factor extremo → advertencia
  5. impacto_estrato3_rango: factura en rango razonable
  6. escenarios_predefinidos_ejecutan: los 4 presets corren sin error
"""

from domain.services.simulation_service import SimulationService


def _get_svc():
    return SimulationService()


# ─── 1. Delta cero con parámetros base ─────────────────────
def test_baseline_delta_zero():
    svc = _get_svc()
    resultado = svc.simular_escenario(
        parametros={'precio_bolsa_factor': 1.0},
        nombre='test_baseline',
    )
    assert abs(resultado['delta_pct']) < 0.5, (
        f"delta_pct debería ser ~0, pero es {resultado['delta_pct']}"
    )


# ─── 2. Precio sube → CU sube ──────────────────────────────
def test_precio_sube_cu_sube():
    svc = _get_svc()
    resultado = svc.simular_escenario(
        parametros={'precio_bolsa_factor': 1.5},
        nombre='test_precio_sube',
    )
    assert resultado['delta_pct'] > 0, (
        f"Con factor 1.5, CU debería subir. delta_pct={resultado['delta_pct']}"
    )
    assert resultado['cu_simulado'] > resultado['cu_baseline'], (
        "cu_simulado debe ser > cu_baseline cuando precio sube"
    )


# ─── 3. Precio baja → CU baja ──────────────────────────────
def test_precio_baja_cu_baja():
    svc = _get_svc()
    resultado = svc.simular_escenario(
        parametros={'precio_bolsa_factor': 0.7},
        nombre='test_precio_baja',
    )
    assert resultado['delta_pct'] < 0, (
        f"Con factor 0.7, CU debería bajar. delta_pct={resultado['delta_pct']}"
    )
    assert resultado['cu_simulado'] < resultado['cu_baseline'], (
        "cu_simulado debe ser < cu_baseline cuando precio baja"
    )


# ─── 4. Factor extremo → advertencia ───────────────────────
def test_advertencia_crisis():
    svc = _get_svc()
    resultado = svc.simular_escenario(
        parametros={'precio_bolsa_factor': 2.5},
        nombre='test_crisis',
    )
    assert len(resultado.get('advertencias', [])) > 0, (
        "Factor 2.5× debería generar al menos una advertencia"
    )


# ─── 5. Impacto estrato 3 en rango razonable ───────────────
def test_impacto_estrato3_rango():
    svc = _get_svc()
    resultado = svc.simular_escenario(
        parametros={'precio_bolsa_factor': 1.3},
        nombre='test_estrato3',
    )
    impacto = resultado.get('impacto_estrato3', {})
    factura = impacto.get('factura_sim_cop', 0)
    # Factura debe estar entre 10k y 100k COP/mes para 173 kWh
    assert 10_000 < factura < 100_000, (
        f"Factura estrato 3 fuera de rango: {factura} COP"
    )


# ─── 6. Los 4 escenarios predefinidos ejecutan sin error ───
def test_escenarios_predefinidos_ejecutan():
    svc = _get_svc()
    presets = svc.get_escenarios_predefinidos()
    assert len(presets) >= 4, (
        f"Se esperaban al menos 4 presets, hay {len(presets)}"
    )
    for preset in presets:
        resultado = svc.simular_escenario(
            parametros=preset['parametros'],
            nombre=f"test_{preset['id']}",
        )
        assert 'cu_simulado' in resultado, (
            f"Escenario {preset['id']} no devolvió cu_simulado"
        )
        assert resultado['cu_simulado'] > 0, (
            f"Escenario {preset['id']}: cu_simulado={resultado['cu_simulado']}"
        )

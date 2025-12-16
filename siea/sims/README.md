# Simuladores - SIEA

Simuladores de escenarios para hidrología, mercado y confiabilidad del sistema eléctrico.

## Simuladores Disponibles

### 1. Simulador Hidrológico
**Propósito**: Proyectar el impacto de escenarios climáticos en embalses

**Inputs**:
- Escenario climático: Niño, Niña, Neutro
- Fecha de inicio
- Horizonte: 3-6 meses

**Outputs**:
- Proyección % llenado de embalses
- Aportes esperados (GWh)
- Alertas de riesgo (bajo 30% o sobre 90%)

**Modelo**: Balance hídrico + histórico de aportes por escenario

```python
from sims.hydrologic import HydrologicSimulator

sim = HydrologicSimulator()
result = sim.run(scenario="Niño", start_date="2025-12-01", months=3)
```

---

### 2. Simulador de Mercado
**Propósito**: Simular precios de bolsa bajo diferentes condiciones

**Inputs**:
- Disponibilidad térmica (%)
- Disponibilidad hidráulica (%)
- Demanda proyectada (GWh)
- Precio combustibles

**Outputs**:
- Curva merit-order
- Precio marginal esperado (COP/kWh)
- Despacho por tecnología
- Riesgo de escasez

**Modelo**: Despacho económico simplificado (merit-order)

```python
from sims.market import MarketSimulator

sim = MarketSimulator()
result = sim.run(
    thermal_availability=0.85,
    hydro_availability=0.70,
    demand=200,  # GWh
    fuel_price=5000  # COP/MBTU
)
```

---

### 3. Simulador de Confiabilidad
**Propósito**: Analizar impacto de contingencias en el sistema

**Inputs**:
- Tipo de contingencia: salida de planta, línea de transmisión
- Capacidad afectada (MW)
- Fecha y hora
- Condiciones operativas

**Outputs**:
- Riesgo de desabastecimiento (%)
- Margen de reserva (MW)
- Necesidad de redespacho
- Alertas operativas

**Modelo**: Análisis N-1 (contingencia simple)

```python
from sims.reliability import ReliabilitySimulator

sim = ReliabilitySimulator()
result = sim.run(
    contingency_type="plant_outage",
    capacity_mw=300,
    datetime="2025-12-02 18:00",
    demand_mw=9500
)
```

---

## Estructura

```
sims/
├── hydrologic/
│   ├── embalses_model.py      # Modelo de balance hídrico
│   ├── scenarios.py           # Escenarios climáticos
│   └── projections.py         # Proyecciones
├── market/
│   ├── merit_order.py         # Curva de oferta
│   ├── price_simulation.py    # Simulación de precios
│   └── stress_scenarios.py    # Escenarios de estrés
├── reliability/
│   ├── contingency_analysis.py  # Análisis de contingencias
│   ├── n_minus_1.py            # N-1 analysis
│   └── risk_metrics.py         # Métricas de riesgo
└── api/
    └── simulator_endpoints.py  # Endpoints FastAPI
```

## Instalación

```bash
cd sims
pip install -r requirements.txt
```

## Datos Requeridos

Los simuladores necesitan acceso a:
- Capacidad instalada por planta (XM)
- Costos variables de generación (XM)
- Histórico de aportes hidrológicos (XM)
- Topología de red de transmisión (XM/UPME)
- Demanda histórica y proyectada

## Uso desde API

```bash
# Simulación hidrológica
curl -X POST http://localhost:8000/api/v1/simulate/hydrologic \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "Niño",
    "start_date": "2025-12-01",
    "months": 3
  }'

# Simulación de mercado
curl -X POST http://localhost:8000/api/v1/simulate/market \
  -H "Content-Type: application/json" \
  -d '{
    "thermal_availability": 0.85,
    "hydro_availability": 0.70,
    "demand": 200
  }'
```

## Validación

Todos los simuladores se validan contra:
- Datos históricos (backtesting)
- Eventos reales (validación ex-post)
- Benchmarks XM

## Tiempos de Ejecución

- Hidrológico: < 10 segundos
- Mercado: < 5 segundos
- Confiabilidad: < 15 segundos

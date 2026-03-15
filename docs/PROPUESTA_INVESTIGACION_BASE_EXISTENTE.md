# PROPUESTA DE INVESTIGACIÓN PARA TESIS DE MAESTRÍA EN FÍSICA
## Basada en el Dashboard ENERTRACE Actual

---

## RESUMEN EJECUTIVO

Esta propuesta de investigación parte de la plataforma ENERTRACE actualmente desarrollada para el Ministerio de Minas y Energía de Colombia. El objetivo es elevar el nivel científico del dashboard existente mediante la incorporación de modelado físico-computacional, transformándolo de una herramienta de monitoreo/visualización a un sistema de optimización inteligente con fundamentos físicos sólidos.

**Palabras clave:** SIN Colombia, Kuramoto-Sakaguchi, PINNs, Deep Reinforcement Learning, ENSO, eólica marina, estabilidad de frecuencia.

---

## 1. PUNTO DE PARTIDA: LO QUE YA EXISTE

### 1.1 Infraestructura Desarrollada

| Componente | Estado Actual | Calidad |
|------------|---------------|---------|
| Dashboard multipágina (14 páginas) | ✅ Funcional | Profesional |
| API REST (29 endpoints) | ✅ Funcional | Producción |
| Base de datos PostgreSQL | ✅ Funcional | 120+ métricas |
| ML/AI (6 modelos) | ✅ Funcional | MAPE 1-16% |
| Simulación paramétrica | ✅ Funcional | Monte Carlo |
| Bots Telegram/WhatsApp | ✅ Funcional | Producción |

### 1.2 Modelos ML Implementados

```
Producción:
├── Prophet → Predicción de aportes hídricos
├── LightGBM → Demanda, precio bolsa
├── RandomForest → Precio bolsa
├── ARIMA → Series temporales
└── Ensemble (Prophet+SARIMA) → Costo Unitario

Experimentos (FASE 7):
├── PatchTST → Transformer con patches
├── N-BEATS → Neural Basis Expansion
├── TCN → Temporal Convolutional Network
├── N-HiTS → Neural Hierarchical Interpolation
└── Chronos → Foundation Model zero-shot
```

### 1.3 Datos Disponibles

**API XM (Tiempo real):**
- 120+ métricas del SIN
- Generación, demanda, precios, embalses
- Pérdidas, restricciones, transmisión

**PostgreSQL (Histórico):**
- Tabla `metrics`: Datos desde 2020
- Tabla `cu_daily`: Costo Unitario diario
- Tabla `predictions`: Predicciones ML
- Tabla `predictions_quality_history`: Calidad ex-post
- Tabla `simulation_results`: Simulaciones guardadas

---

## 2. PROPUESTA DE INVESTIGACIÓN

### 2.1 Título Propuesto

> **"Despacho Óptimo del Sistema Interconectado Nacional Colombiano mediante Deep Reinforcement Learning con Restricciones Físicas: Integración de Tecnología Eólica Marina bajo Escenarios ENSO"**

### 2.2 Problema de Investigación

El SIN colombiano enfrenta tres desafíos críticos:

1. **Vulnerabilidad climática:** Dependencia del 65% de generación hidroeléctrica, altamente sensible al ENSO
2. **Transición energética:** Meta de 9 GW de ERNC para 2030, incluyendo eólica marina de tecnología china
3. **Optimización del despacho:** Los métodos actuales (SDDP) no consideran estabilidad de frecuencia con alta penetración renovable

**Pregunta central:** ¿Cómo optimizar el despacho del SIN integrando 10 GW de eólica marina china mientras se garantiza la estabilidad de frecuencia bajo escenarios ENSO?

### 2.3 Hipótesis

**H1:** Un agente DRL con restricciones físicas (PINNs) puede reducir el Costo Unitario en escenarios Niño manteniendo la estabilidad del sistema.

**H2:** El modelo Kuramoto-Sakaguchi permite identificar el umbral crítico de penetración eólica antes de una transición de fase hacia inestabilidad.

**H3:** La integración de datos ERA5-ONI mejora significativamente la predicción de aportes hídricos vs modelos estadísticos puros.

---

## 3. OBJETIVOS

### 3.1 Objetivo General

Desarrollar un sistema de despacho óptimo para el SIN colombiano basado en Deep Reinforcement Learning con restricciones físicas, integrando tecnología eólica marina china y considerando escenarios ENSO.

### 3.2 Objetivos Específicos

| # | Objetivo | Basado en | Estado Actual |
|---|----------|-----------|---------------|
| 1 | Implementar modelo Kuramoto-Sakaguchi del SIN con inercia heterogénea | Dashboard actual (no tiene) | ❌ No existe |
| 2 | Construir pipeline ERA5-ONI para La Guajira offshore | Dashboard actual (no tiene) | ❌ No existe |
| 3 | Desarrollar PINN con restricciones de Kirchhoff | Modelos ML existentes | ⚠️ Base: Prophet/LightGBM |
| 4 | Entrenar agente PPO con función de recompensa multiobjetivo | Simulación CREG existente | ⚠️ Base: Simulación paramétrica |
| 5 | Identificar umbral crítico ρc de penetración eólica | No existe | ❌ No existe |
| 6 | Validar contra SDDP en escenarios Niño | No existe | ❌ No existe |
| 7 | Integrar en dashboard ENERTRACE | Dashboard existente | ✅ Base sólida |

---

## 4. METODOLOGÍA PROPUESTA

### 4.1 Fase 1: Infraestructura de Datos (Meses 1-2)

**Partiendo de:** Dashboard con datos XM y PostgreSQL

**A agregar:**

```python
# Nuevo: etl/etl_era5.py
class ERA5Downloader:
    """Descarga datos ERA5 para La Guajira"""
    def download_wind_data(self, year, month):
        # Variables: u100, v100, SST, GHI
        # Área: 11-12.5°N, 71-73.5°W
        pass

# Nuevo: etl/etl_oni.py  
class ONIDownloader:
    """Descarga serie ONI desde NOAA"""
    def get_interpolated_oni(self, fecha):
        # Interpolación horaria de datos mensuales
        pass

# Nuevo: domain/services/climate_service.py
class ClimateService:
    """Integra ERA5 + ONI + datos XM"""
    def get_integrated_state(self, fecha):
        return {
            'viento_100m': ...,  # ERA5
            'oni': ...,          # NOAA
            'enso_phase': ...,   # NINO/NINA/NEUTRAL
            'nivel_embalse': ..., # XM
        }
```

**Tablas PostgreSQL nuevas:**
```sql
CREATE TABLE era5_data (
    id SERIAL PRIMARY KEY,
    fecha TIMESTAMP NOT NULL,
    latitud DECIMAL(8,6),
    longitud DECIMAL(9,6),
    u100 DECIMAL(8,3),
    v100 DECIMAL(8,3),
    velocidad_viento DECIMAL(8,3),
    sst DECIMAL(6,2)
);

CREATE TABLE oni_data (
    id SERIAL PRIMARY KEY,
    año INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    oni_value DECIMAL(4,2) NOT NULL,
    enso_phase VARCHAR(10)
);

CREATE TABLE weibull_params (
    id SERIAL PRIMARY KEY,
    latitud DECIMAL(8,6),
    longitud DECIMAL(9,6),
    parametro_k DECIMAL(6,4),
    parametro_c DECIMAL(8,4)
);
```

### 4.2 Fase 2: Modelo Kuramoto-Sakaguchi (Meses 3-4)

**Partiendo de:** Dashboard sin modelado físico

**A desarrollar:**

```python
# Nuevo: domain/models/kuramoto_sin.py
class SINGraph:
    """Grafo del SIN con topología de nodos y líneas"""
    def __init__(self):
        self.G = nx.Graph()
        self.generators = {}  # ~200 generadores
        
    def add_generator(self, gen_id, tipo, potencia_max, inercia):
        # tipos: 'HIDRO', 'TERMICA', 'EOLICA', 'SOLAR'
        # inercia: 6s (hidro), 4s (termica), 3s (eolica VSM)
        pass
        
    def add_transmission_line(self, gen1, gen2, reactancia, capacidad):
        # K_ij = (V_i * V_j) / X_ij
        pass
        
    def calcular_conectividad_algebraica(self):
        L = nx.laplacian_matrix(self.G)
        eigenvalues = np.linalg.eigvalsh(L)
        lambda_2 = sorted(eigenvalues)[1]
        return lambda_2

class KuramotoSINModel:
    """Modelo de osciladores acoplados para dinámica del SIN"""
    
    def dynamics(self, t, state):
        """
        Ecuaciones Kuramoto-Sakaguchi con inercia:
        M_i * d²θ_i/dt² + D_i * dθ_i/dt = 
            P_i^mec - P_i^elec + Σ_j K_ij sin(θ_j - θ_i)
        """
        n = self.n_generators
        theta = state[:n]
        omega = state[n:]
        
        dtheta = omega
        domega = np.zeros(n)
        
        for i in range(n):
            p_elec = sum(self.K[i,j] * np.sin(theta[j] - theta[i]) 
                        for j in range(n) if self.K[i,j] > 0)
            domega[i] = (self.P_mec[i] - p_elec - self.D[i] * omega[i]) / self.M[i]
        
        return np.concatenate([dtheta, domega])
    
    def simulate(self, t_span, perturbation=None):
        solution = solve_ivp(self.dynamics, t_span, y0)
        return solution
```

**Integración en dashboard:**
```python
# Nuevo: interface/pages/estabilidad.py
layout = html.Div([
    crear_page_header("Estabilidad del SIN", "fas fa-wave-square"),
    
    # KPI λ₂
    html.Div(id="kpi-lambda-2"),
    
    # Gráfico de osciladores
    dcc.Graph(id="grafico-osciladores"),
    
    # Métricas de frecuencia
    html.Div(id="metricas-frecuencia"),
    
    # Simulador de perturbaciones
    dcc.Slider(id="perturbacion-mw", min=0, max=1000, step=50),
    dbc.Button("Simular pérdida de generación", id="btn-simular")
])
```

### 4.3 Fase 3: PINNs (Meses 5-6)

**Partiendo de:** Modelos ML estadísticos (Prophet, LightGBM, RandomForest)

**A desarrollar:**

```python
# Nuevo: experiments/pinn_power_system.py
class PowerSystemPINN(nn.Module):
    """PINN con restricciones de Kirchhoff"""
    
    def __init__(self, n_buses, n_hidden=256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_buses * 3, n_hidden),  # [P, Q, V]
            nn.Tanh(),
            nn.Linear(n_hidden, n_hidden),
            nn.Tanh(),
            nn.Linear(n_hidden, n_hidden),
            nn.Tanh(),
            nn.Linear(n_hidden, n_buses * 2)   # [θ, V]
        )
    
    def physics_loss(self, x, y_pred):
        """Penaliza violaciones de ecuaciones de flujo de carga"""
        theta, V = y_pred[:, ::2], y_pred[:, 1::2]
        
        # Reconstruir P, Q desde θ, V (ecuaciones de Kirchhoff)
        P_calc, Q_calc = self.power_flow_equations(theta, V)
        
        P_input = x[:, ::3]
        Q_input = x[:, 1::3]
        
        loss_P = torch.mean((P_calc - P_input) ** 2)
        loss_Q = torch.mean((Q_calc - Q_input) ** 2)
        
        return loss_P + loss_Q
    
    def power_flow_equations(self, theta, V):
        """Ecuaciones de flujo de carga de Kirchhoff"""
        # P_i = V_i * Σ_j V_j * (G_ij * cos(θ_i - θ_j) + B_ij * sin(θ_i - θ_j))
        # Q_i = V_i * Σ_j V_j * (G_ij * sin(θ_i - θ_j) - B_ij * cos(θ_i - θ_j))
        pass

# Entrenamiento
loss = loss_data + 0.1 * loss_physics
optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
```

**Integración con predicciones existentes:**
```python
# Modificar: domain/services/predictions_service.py
def predict_with_pinn(self, metrica, horizonte):
    # Usar PINN en lugar de Prophet/LightGBM
    # Validar restricciones físicas
    # Retornar predicción con MAPE < 5%
    pass
```

### 4.4 Fase 4: Agente DRL (Meses 7-9)

**Partiendo de:** Simulación CREG paramétrica existente

**A desarrollar:**

```python
# Nuevo: experiments/gym_sin_env.py
class SINEnv(gym.Env):
    """Entorno Gymnasium del SIN para DRL"""
    
    def __init__(self, scenario='baseline'):
        # Escenarios: 'baseline', 'china_10gw', 'nino', 'nina'
        
        # Espacio de estados: 56 dimensiones
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(56,)
        )
        
        # Espacio de acciones: redespacho + inercias virtuales
        n_generadores = 200 if scenario == 'baseline' else 250
        self.action_space = spaces.Box(
            low=-1, high=1, shape=(n_generadores + 50,)
        )
    
    def _calculate_reward(self):
        """Función de recompensa multiobjetivo"""
        R = (
            100 * cobertura_demanda
            - 0.5 * cu_actual
            - 10 * valor_agua
            - 100 * varianza_frecuencia
            - 0.1 * emisiones_co2
            + 5 * penetracion_renovable
        )
        return R

# Entrenamiento PPO
# Nuevo: experiments/train_ppo.py
model = PPO(
    "MlpPolicy",
    env,
    learning_rate=3e-4,
    n_steps=2048,
    batch_size=64,
    n_epochs=10,
    gamma=0.99,
    gae_lambda=0.95,
    clip_range=0.2,
    verbose=1
)

# Curriculum Learning
model.learn(total_timesteps=1_000_000)  # Baseline
model.set_env(env_nino).learn(1_000_000)  # Niño
model.set_env(env_china).learn(2_000_000)  # +10 GW eólica
```

**Integración con simulación CREG existente:**
```python
# Modificar: domain/services/simulation_service.py
def simular_escenario_drl(self, parametros):
    # Usar agente PPO entrenado
    # Validar contra modelo Kuramoto
    # Retornar resultado optimizado
    pass
```

### 4.5 Fase 5: Transiciones de Fase (Mes 10)

**A desarrollar:**

```python
# Nuevo: experiments/phase_transitions.py
def identificar_umbral_critico():
    """Identifica ρc mediante simulaciones Monte Carlo"""
    
    for rho in np.linspace(0, 0.8, 100):  # Penetración eólica
        estabilidad_count = 0
        
        for _ in range(1000):  # Realizaciones
            resultado = simulate_kuramoto(rho, enso_phase='NINO')
            if resultado['estable']:
                estabilidad_count += 1
        
        if estabilidad_count < 500:  # < 50% estable
            rho_c = rho
            break
    
    return rho_c
```

### 4.6 Fase 6: Integración (Meses 11-12)

**Integración en dashboard existente:**

```python
# Modificar: app.py
# Agregar nuevas páginas
pages = [
    # ... páginas existentes ...
    "estabilidad",      # Nueva: Modelo Kuramoto
    "escenarios_drl",   # Nueva: Comparador SDDP vs PPO
    "transicion_fase",  # Nueva: Umbral crítico ρc
]

# Nuevo: api/v1/routers/drl.py
@router.post("/predict_dispatch")
async def predict_dispatch(state: SINState):
    """Retorna acción óptima del agente DRL"""
    action, _ = model.predict(state.to_array())
    return {"action": action.tolist()}

@router.post("/simulate_stability")
async def simulate_stability(scenario: ScenarioConfig):
    """Simula estabilidad con modelo Kuramoto"""
    kuramoto = KuramotoSINModel(cargar_grafo_sin())
    result = kuramoto.simulate(scenario.t_span)
    return {
        "lambda_2": result['lambda_2'],
        "frecuencia_min": result['frecuencia_min'],
        "estable": result['estable']
    }
```

---

## 5. CRONOGRAMA DETALLADO

| Mes | Actividad | Entregable |
|-----|-----------|------------|
| 1 | Configurar CDS API, descargar ERA5 | Pipeline ERA5 funcional |
| 2 | Integrar ONI, calibrar Weibull | Datos climáticos integrados |
| 3 | Implementar grafo SIN, nodos generadores | Grafo del SIN en NetworkX |
| 4 | Implementar Kuramoto-Sakaguchi, calcular λ₂ | Modelo de estabilidad |
| 5 | Desarrollar arquitectura PINN | PINN con restricciones |
| 6 | Entrenar PINN, validar vs modelos estadísticos | PINN con MAPE < 5% |
| 7 | Crear entorno Gymnasium SIN-v0 | Entorno baseline |
| 8 | Entrenar agente PPO baseline | Agente PPO funcional |
| 9 | Curriculum learning ENSO, benchmark SDDP | Agente validado |
| 10 | Simulaciones Monte Carlo, identificar ρc | Umbral crítico |
| 11 | Microservicio DRL, API REST | Servicio desplegado |
| 12 | Dashboard, validación, documentación | Tesis completa |

---

## 6. RECURSOS NECESARIOS

### 6.1 Computación
- GPU NVIDIA A100 o similar (entrenamiento DRL)
- Servidor 32 cores, 128GB RAM (simulaciones)
- 500GB almacenamiento (datos ERA5 + modelos)

### 6.2 Datos
- ✅ XM (ya disponible)
- 🆕 Copernicus CDS (gratuito)
- 🆕 NOAA ONI (gratuito)
- 🆕 Fichas técnicas Goldwind/Mingyang (solicitar)

### 6.3 Software
- ✅ Python 3.11+, PyTorch (ya disponible)
- 🆕 Stable-Baselines3
- 🆕 Gymnasium
- 🆕 NetCDF4, XArray (ERA5)

---

## 7. RESULTADOS ESPERADOS

### 7.1 Contribuciones Científicas

1. **Primer modelo Kuramoto-Sakaguchi del SIN** con inercia virtual programable
2. **PINN con restricciones de Kirchhoff** para sistemas de potencia
3. **Benchmark DRL vs SDDP** en sistema hidro-térmico real
4. **Umbral crítico ρc** de penetración eólica marina en sistemas latinoamericanos

### 7.2 Métricas de Éxito

| Métrica | Objetivo |
|---------|----------|
| MAPE predicción PINN | < 5% |
| Mejora DRL vs SDDP (Niño) | > 10% |
| λ₂ mínimo aceptable | > 0.2 |
| Factor de capacidad eólica La Guajira | > 45% |
| Tiempo de inferencia DRL | < 2s |

### 7.3 Productos

1. Artículo en revista indexada (Applied Energy, Physical Review Applied)
2. Repositorio GitHub con código abierto
3. Dashboard ENERTRACE integrado
4. Informe técnico para MME

---

## 8. RIESGOS Y MITIGACIÓN

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Datos ERA5 no disponibles | Baja | Alto | NASA POWER alternativo |
| Entrenamiento DRL lento | Alta | Medio | Curriculum learning, paralelizar |
| Modelo Kuramoto muy simplificado | Media | Alto | Validar contra PowerFactory |
| No conseguir curvas potencia China | Media | Alto | Usar datos de turbinas similares |

---

## 9. CONCLUSIÓN

Esta propuesta de investigación parte de una base sólida (dashboard ENERTRACE con 60% de avance) y propone un plan de 12 meses para completar una tesis de Maestría en Física con impacto científico y práctico.

**Fortalezas del punto de partida:**
- Infraestructura de datos (XM, PostgreSQL)
- ML/AI funcional (Prophet, LightGBM)
- Simulación paramétrica (Monte Carlo)
- Dashboard profesional

**Elementos a agregar:**
- Modelado físico (Kuramoto)
- PINNs con restricciones
- Agente DRL con curriculum learning
- Benchmark riguroso vs SDDP

**Impacto esperado:**
- Publicación científica Q1
- Herramienta para operadores del SIN
- Política pública para integración de ERNC

---

**Fecha:** Marzo 2026  
**Versión:** 1.0 (Basada en dashboard existente)

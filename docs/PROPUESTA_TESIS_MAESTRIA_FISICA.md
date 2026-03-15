# PROPUESTA DE TESIS DE MAESTRÍA EN FÍSICA
## "Modelado Físico-Computacional del Sistema Interconectado Nacional Colombiano: Integración de Tecnología Eólica Marina China bajo Escenarios ENSO mediante Deep Reinforcement Learning con Restricciones Físicas"

---

## RESUMEN EJECUTIVO

Esta tesis propone desarrollar un marco de modelado físico-computacional para optimizar la operación del Sistema Interconectado Nacional (SIN) colombiano, integrando 10 GW de tecnología eólica marina de origen chino bajo escenarios de variabilidad climática inducida por el Fenómeno El Niño-Oscilación del Sur (ENSO). La investigación combina cuatro metodologías de vanguardia: (1) modelado de osciladores acoplados tipo Kuramoto-Sakaguchi para estabilidad de frecuencia; (2) Physics-Informed Neural Networks (PINNs) para predicción con restricciones físicas de Kirchhoff; (3) Deep Reinforcement Learning (PPO) con restricciones físicas embebidas para despacho óptimo; y (4) análisis de transiciones de fase para identificación de umbrales críticos de penetración renovable.

**Palabras clave:** Sistema Interconectado Nacional, Kuramoto-Sakaguchi, PINNs, Deep Reinforcement Learning, ENSO, eólica marina, estabilidad de frecuencia, transiciones de fase.

---

## 1. INTRODUCCIÓN Y JUSTIFICACIÓN

### 1.1 Contexto Nacional

Colombia posee un sistema eléctrico dominado por generación hidroeléctrica (~65% de la capacidad instalada), lo que genera alta vulnerabilidad ante eventos climáticos extremos asociados al ENSO. Durante el evento El Niño 2015-2016, el Costo Unitario (CU) de electricidad alcanzó valores históricos superiores a $400 USD/MWh debido a la reducción de aportes hídricos. Simultáneamente, el país ha iniciado la transición energética con metas de 9 GW de energías renovables no convencionales (ERNC) para 2030.

### 1.2 Oportunidad Estratégica

China ha emergido como líder mundial en tecnología eólica marina, con turbinas de 16-20 MW (Goldwind GWH252-16MW, Mingyang MySE 16.0-260, MySE 18.X-20MW) que duplican la capacidad de tecnología occidental. La costa Caribe colombiana, particularmente La Guajira, presenta recursos eólicos clase mundial (8-10 m/s promedio anual) con potencial para 50+ GW offshore.

### 1.3 Problema de Investigación

La integración masiva de generación eólica marina (inercia virtual programable) en un sistema hidro-térmico dominado por máquinas sincrónicas (inercia mecánica) plantea desafíos críticos de estabilidad de frecuencia que no pueden ser abordados por métodos de optimización tradicionales (SDDP) debido a:

- **No-linealidades:** Ecuaciones swing de segundo orden con acoplamientos sinusoidales
- **Estocasticidad:** Variabilidad de viento y aportes hídricos correlacionados con ENSO
- **Alta dimensionalidad:** Espacio de estados de 56+ dimensiones
- **Restricciones físicas:** Leyes de Kirchhoff, límites de estabilidad transitoria

### 1.4 Preguntas de Investigación

1. ¿Cómo modelar el SIN como sistema de osciladores acoplados con inercia heterogénea (sincrónica + virtual)?
2. ¿Cuál es el umbral crítico de penetración eólica marina antes de una transición de fase hacia inestabilidad?
3. ¿Puede un agente DRL con restricciones físicas (PINNs) superar el desempeño de SDDP en escenarios ENSO?
4. ¿Cómo cuantificar el valor estratégico del agua embalsada bajo diferentes fases ENSO?

---

## 2. ESTADO DEL ARTE

### 2.1 Modelos Kuramoto para Redes Eléctricas

El modelo de Kuramoto, propuesto originalmente para describir sincronización en sistemas biológicos, ha sido extendido al análisis de estabilidad en redes eléctricas. Park y Kahng (2024) demostraron transiciones de sincronización discontinuas con histéresis en redes con mezcla de osciladores de primer y segundo orden, relevante para sistemas con alta penetración de renovables. Ventura Nadal et al. (2024) integraron PINNs en simulaciones de dinámica transitoria, logrando mejoras significativas en precisión para pasos de tiempo grandes.

**Gap identificado:** Ningún estudio ha aplicado el modelo Kuramoto-Sakaguchi al SIN colombiano con inercia virtual programable de tecnología china.

### 2.2 Physics-Informed Neural Networks (PINNs)

Stiasny et al. (2023, 2024) desarrollaron PINNSim, un simulador de dinámica de sistemas de potencia basado en PINNs que logra aceleraciones de 10x-1000x respecto a métodos numéricos tradicionales. Huang y Wang (2023) presentaron una revisión comprehensiva de aplicaciones de PINNs en sistemas de potencia, destacando su capacidad para aprender de modelos físicos sin requerir grandes volúmenes de datos.

**Gap identificado:** Los PINNs existentes no incorporan explícitamente las ecuaciones de flujo de carga como restricciones duras en el entrenamiento.

### 2.3 Deep Reinforcement Learning para Despacho

Ali et al. (2026) demostraron que SAC (Soft Actor-Critic) reduce costos operativos en 20% y alcanza 92.8% de integración renovable en redes con alta penetración. Sage et al. (2025) abordaron el problema de recompensas retardadas en sistemas P2G mediante técnicas de atribución de costos modificada. Ávila et al. (2023) conectaron SDDP con RL mediante batch learning, demostrando convergencia más rápida.

**Gap identificado:** Ningún estudio ha comparado sistemáticamente DRL contra SDDP en un sistema hidro-térmico real con integración de tecnología china.

### 2.4 Impacto de ENSO en Generación Hidroeléctrica

Turner et al. (2017) analizaron 1593 embalses globalmente, encontrando que 34.7% muestra anomalías significativas en producción durante eventos ENSO. Recientemente, estudios en Colombia (2025) confirmaron efectos contrastantes de ENSO en diferentes cuencas, con la región del Magdalena Medio siendo la más vulnerable.

**Gap identificado:** No existe un modelo predictivo de aportes hídricos que integre explícitamente ONI como variable de estado para optimización del despacho.

### 2.5 Tecnología Eólica Marina China

Goldwind (GWH252-16MW) y Mingyang (MySE 16.0-260, MySE 18.X-20MW) han establecido nuevos estándares con turbinas de 16-20 MW, rotores de 252-292m y resistencia a tifones (hasta 79.8 m/s). En 2024, China Three Gorges instaló la primera turbina flotante de 16 MW.

**Gap identificado:** No hay estudios de integración de estas tecnologías en sistemas eléctricos latinoamericanos con curvas de potencia reales.

### 2.6 Pérdidas No Técnicas (PNT)

Estudios recientes (2023-2025) demuestran que métodos de ensemble (CNN+LSTM, Random Forest con SMOTE) alcanzan 95-98% de precisión en detección de fraudes. Sin embargo, la mayoría usa enfoques puramente estadísticos sin fundamentación en teoría de la información.

**Gap identificado:** No se ha aplicado divergencia KL para detección de anomalías en redes de distribución colombianas.

---

## 3. OBJETIVOS

### 3.1 Objetivo General

Desarrollar un marco de modelado físico-computacional para optimizar la operación del SIN colombiano integrando 10 GW de tecnología eólica marina china bajo escenarios ENSO, utilizando Deep Reinforcement Learning con restricciones físicas embebidas.

### 3.2 Objetivos Específicos

1. **Modelado Físico:** Implementar modelo Kuramoto-Sakaguchi del SIN con inercia heterogénea y calcular conectividad algebraica λ₂ como métrica de estabilidad.

2. **Datos Climáticos:** Construir pipeline ERA5-ONI para La Guajira offshore y calibrar distribución Weibull de velocidades de viento.

3. **PINNs:** Desarrollar red neuronal con restricciones de Kirchhoff para predicción de estados del sistema con MAPE < 5%.

4. **DRL:** Entrenar agente PPO con función de recompensa multiobjetivo y validar contra SDDP en escenarios ENSO.

5. **Transiciones de Fase:** Identificar umbral crítico ρc de penetración eólica mediante simulaciones Monte Carlo con modelo físico.

6. **Dashboard:** Integrar modelo en plataforma ENERTRACE para uso del MME.

---

## 4. METODOLOGÍA

### 4.1 Fase 1: Infraestructura de Datos (Meses 1-2)

#### 4.1.1 ERA5 (Copernicus Climate Data Store)

Descarga de variables para La Guajira offshore (11-12.5°N, 71-73.5°W):
- Componentes u100, v100 (viento a 100m)
- Temperatura superficial del mar (SST)
- Radiación GHI/DNI
- Periodo: 2000-2024 (resolución horaria)

**Procesamiento:**
```
velocidad = √(u² + v²)
dirección = atan2(v, u) × 180/π
```

#### 4.1.2 ONI (NOAA)

Serie mensual 1950-2024, interpolación a resolución horaria con splines cúbicos. Estados ENSO:
- Niño: ONI > 0.5°C
- Niña: ONI < -0.5°C  
- Neutral: -0.5 ≤ ONI ≤ 0.5°C

#### 4.1.3 Curvas Guía XM

Niveles críticos por cuenca (Guavio, El Peñol, San Carlos, etc.) para cálculo de valor del agua:

```python
def valor_agua(nivel, nivel_critico, fase_enso):
    gamma = 2.0 if fase_enso == 'NINO' else 1.0
    return exp(-gamma × (nivel - nivel_critico))
```

### 4.2 Fase 2: Modelo Kuramoto-Sakaguchi (Meses 3-4)

#### 4.2.1 Grafo del SIN

- Nodos: ~200 generadores (hidro, térmico, eólico, solar)
- Aristas: Líneas 500/230/115 kV con reactancias
- Matriz de acoplamiento: K_ij = (V_i × V_j) / X_ij

#### 4.2.2 Ecuaciones de Dinámica

```
M_i × d²θ_i/dt² + D_i × dθ_i/dt = P_i^mec - P_i^elec + Σ_j K_ij sin(θ_j - θ_i)

Donde:
- M_i: Inercia (6s hidro, 4s térmica, 3s eólica VSM)
- D_i: Amortiguamiento
- P_i^mec: Potencia mecánica inyectada
- P_i^elec: Potencia eléctrica = Σ_j K_ij sin(θ_j - θ_i)
```

#### 4.2.3 Conectividad Algebraica

```python
L = nx.laplacian_matrix(G)
eigenvalues = np.linalg.eigvalsh(L)
lambda_2 = sorted(eigenvalues)[1]  # Segundo eigenvalor

if lambda_2 > 0.5: estabilidad = "ALTA"
elif lambda_2 > 0.2: estabilidad = "MEDIA"
else: estabilidad = "BAJA - RIESGO"
```

### 4.3 Fase 3: PINNs (Meses 5-6)

#### 4.3.1 Arquitectura

```python
class PowerSystemPINN(nn.Module):
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
        theta, V = y_pred[:, ::2], y_pred[:, 1::2]
        P_calc, Q_calc = power_flow_equations(theta, V)
        P_input, Q_input = x[:, ::3], x[:, 1::3]
        
        loss_P = torch.mean((P_calc - P_input) ** 2)
        loss_Q = torch.mean((Q_calc - Q_input) ** 2)
        return loss_P + loss_Q
```

#### 4.3.2 Entrenamiento

```python
loss = loss_data + 0.1 × loss_physics
optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
```

### 4.4 Fase 4: Agente DRL (Meses 7-9)

#### 4.4.1 Entorno Gymnasium

```python
class SINEnv(gym.Env):
    def __init__(self, scenario='baseline'):
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(56,)
        )
        self.action_space = spaces.Box(
            low=-1, high=1, shape=(250,)  # 200 gen + 50 inercias
        )
```

**Espacio de estados (56D):**
- 40 niveles de embalses (%)
- u100, v100, GHI, demanda, precio, ONI, frecuencia, penetración
- 8 métricas adicionales

#### 4.4.2 Función de Recompensa

```python
R = w1×Cobertura - w2×Disipación - w3×ValorAgua - w4×Estabilidad - w5×Emisiones + w6×Renovable

w1=100, w2=0.01, w3=10, w4=1000, w5=0.001, w6=5
```

#### 4.4.3 Entrenamiento PPO

```python
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

### 4.5 Fase 5: Transiciones de Fase (Meses 10)

#### 4.5.1 Simulaciones Monte Carlo

```python
for rho in np.linspace(0, 0.8, 100):  # Penetración eólica
    for _ in range(1000):  # Realizaciones
        results = simulate_kuramoto(rho, enso_phase)
        if not results['estable']:
            rho_c = rho  # Umbral crítico
            break
```

### 4.6 Fase 6: Integración (Meses 11-12)

- Microservicio Docker con API REST
- Dashboard de escenarios en ENERTRACE
- Validación contra datos históricos (hold-out 2025)

---

## 5. RESULTADOS ESPERADOS

### 5.1 Contribuciones Científicas

1. **Primer modelo Kuramoto-Sakaguchi del SIN** con inercia virtual programable
2. **PINN con restricciones de Kirchhoff** para sistemas de potencia
3. **Benchmark DRL vs SDDP** en sistema hidro-térmico real
4. **Umbral crítico ρc** de penetración eólica marina en sistemas latinoamericanos

### 5.2 Métricas de Éxito

| Métrica | Objetivo |
|---------|----------|
| MAPE predicción PINN | < 5% |
| Mejora DRL vs SDDP (Niño) | > 10% |
| λ₂ mínimo aceptable | > 0.2 |
| Factor de capacidad eólica La Guajira | > 45% |
| Tiempo de inferencia DRL | < 2s |

### 5.3 Productos

1. Artículo en revista indexada (Applied Energy, Physical Review Applied)
2. Repositorio GitHub con código abierto
3. Dashboard ENERTRACE integrado
4. Informe técnico para MME

---

## 6. CRONOGRAMA

| Fase | Actividad | Meses |
|------|-----------|-------|
| 1 | Infraestructura ERA5 + ONI | 1-2 |
| 2 | Modelo Kuramoto + λ₂ | 3-4 |
| 3 | PINNs entrenados | 5-6 |
| 4 | Entorno Gymnasium + PPO | 7-9 |
| 5 | Transiciones de fase | 10 |
| 6 | Integración + Validación | 11-12 |

---

## 7. RECURSOS

### 7.1 Computación

- GPU NVIDIA A100 (entrenamiento DRL)
- Servidor 32 cores, 128GB RAM (simulaciones)
- 500GB almacenamiento (datos ERA5 + modelos)

### 7.2 Datos

- XM (precios, generación, demanda)
- Copernicus CDS (ERA5) - gratuito
- NOAA (ONI) - gratuito
- Fichas técnicas Goldwind/Mingyang (solicitar)

### 7.3 Software

- Python 3.11+, PyTorch, Stable-Baselines3
- Gymnasium, NetworkX, SciPy
- NetCDF4, XArray (ERA5)

---

## 8. RIESGOS Y MITIGACIÓN

| Riesgo | Prob. | Impacto | Mitigación |
|--------|-------|---------|------------|
| ERA5 no disponible | Baja | Alto | NASA POWER alternativo |
| Entrenamiento DRL lento | Alta | Medio | Curriculum learning |
| Curvas potencia China no disponibles | Media | Alto | Turbinas similares |
| Benchmark SDDP complejo | Media | Medio | PyPSA existente |

---

## 9. IMPACTO ESPERADO

### 9.1 Científico

- Primera aplicación de Kuramoto-Sakaguchi con VSM en Latinoamérica
- Nuevo método PINN con restricciones físicas duras
- Contribución a teoría de transiciones de fase en redes eléctricas

### 9.2 Práctico

- Herramienta de decisión para operadores del SIN
- Política pública para integración de ERNC
- Reducción de costos por eventos ENSO

### 9.3 Social

- Mayor confiabilidad del suministro eléctrico
- Transición energética acelerada
- Mitigación de impactos económicos del Niño

---

## 10. CONCLUSIÓN

Esta propuesta representa una investigación de frontera que combina física no-lineal, machine learning físicamente informado y optimización estocástica para abordar un problema crítico de la transición energética colombiana. Los resultados tendrán impacto tanto científico (publicaciones de alto nivel) como práctico (herramienta para el MME).

---

## REFERENCIAS

1. Park, J. & Kahng, B. (2024). Hybrid synchronization with continuous varying exponent in modernized power grid. *Chaos, Solitons & Fractals*, 186, 115315.

2. Ventura Nadal, I., Stiasny, J. & Chatzivasileiadis, S. (2024). Integrating Physics-Informed Neural Networks into Power System Dynamic Simulations. *arXiv:2404.13325*.

3. Stiasny, J., Misyris, G.S. & Chatzivasileiadis, S. (2023). Physics-informed neural networks for time-domain simulations. *Electric Power Systems Research*, 224, 109748.

4. Ali, H. et al. (2026). Deep reinforcement learning for real-time energy dispatch in smart grids. *Clean Energy Science and Technology*, 4(1).

5. Sage, M., Al Handawi, K. & Zhao, Y.F. (2025). The Economic Dispatch of Power-to-Gas Systems with Deep Reinforcement Learning. *arXiv:2506.06484*.

6. Ávila, D., Papavasiliou, A. & Löhndorf, N. (2023). Batch Learning SDDP for Long-Term Hydrothermal Planning. *IEEE Transactions on Power Systems*.

7. Turner, S.W.D. et al. (2017). Influence of El Niño Southern Oscillation on global hydropower production. *Environmental Research Letters*, 12(3), 034010.

8. ENSO effects on hydropower and climate adaptation strategies in four Colombian case studies (2025). *Journal of Hydrology: Regional Studies*.

9. Goldwind achieves 'huge leap' with 16MW wind turbine installed on floating platform (2025). *Wind Power Monthly*.

10. Methodology for Detecting Non-Technical Energy Losses Using an Ensemble of Machine Learning Algorithms (2025). *CMES*.

---

**Fecha:** Marzo 2026  
**Versión:** 2.0 (Mejorada con estado del arte)

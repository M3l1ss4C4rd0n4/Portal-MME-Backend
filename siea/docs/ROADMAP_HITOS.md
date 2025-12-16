# ROADMAP SIEA - Cronograma 36 Semanas

## 📅 VISTA GENERAL DEL CRONOGRAMA

```
Semana:  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36
         │─────│────────────────│─────────────│─────────────│─────────────────────│──────────────────────────────│
HITO 0:  ■■■■
HITO 1:        ■■■■■■■■■■■■■■■■■
HITO 2:                         ■■■■■■■■■■■■■■
HITO 3:                                        ■■■■■■■■■■■■■■
HITO 4:                                                       ■■■■■■■■■■■■■■■■■■■■■■
HITO 5:                                                                              ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
```

**Leyenda:**
- ■ = Trabajo activo
- │ = Límite de hito
- Duración total: **36 semanas (9 meses)**

---

## 🎯 HITO 0: Planeación y Diseño (Semanas 1-2)

**📆 Duración:** 2 semanas  
**👥 Equipo:** Líder técnico, arquitecto, áreas TIC/Legal/Comunicaciones

### Semana 1
- [x] Lunes: Kickoff meeting con todas las áreas
- [x] Martes-Miércoles: Diseño de arquitectura técnica
- [x] Jueves: Definición de stack tecnológico
- [x] Viernes: Creación de cronograma detallado

### Semana 2
- [ ] Lunes: Plantillas legales (DPIA, convenios, NDA)
- [ ] Martes: Plan de gestión de datos (DMP)
- [ ] Miércoles: Identificación de fuentes de datos y APIs
- [ ] Jueves: Matriz de riesgos y plan de mitigación
- [ ] Viernes: Presentación y aprobación formal

### Entregables HITO 0
- ✅ Propuesta técnica completa (20 páginas)
- ✅ Diagrama de arquitectura (4 capas)
- ✅ Plan de gestión de datos
- ✅ Plantillas legales firmadas por Área Jurídica
- ✅ Cronograma 36 semanas con hitos
- ✅ Matriz de riesgos

### Criterios de Aceptación
- [ ] Aprobación arquitectura por Jefe TIC
- [ ] Aprobación plantillas por Área Jurídica
- [ ] Aprobación presupuesto por Área Financiera
- [ ] Firma de acta de inicio de proyecto

---

## 🏗️ HITO 1: Backend + ETL + Dashboard Prototipo (Semanas 3-8)

**📆 Duración:** 6 semanas  
**👥 Equipo:** 2 backend devs, 1 frontend dev, 1 data engineer

### Semana 3-4: Setup Infraestructura Base
**Semana 3:**
- [ ] Configurar repos Git (GitHub privado MME)
- [ ] Setup PostgreSQL + TimescaleDB
- [ ] Setup Redis para cache
- [ ] Configurar DuckDB para análisis
- [ ] Crear schemas de base de datos

**Semana 4:**
- [ ] Implementar FastAPI base (health, config)
- [ ] Implementar ORM models (SQLAlchemy)
- [ ] Configurar Alembic migrations
- [ ] Setup pytest + fixtures
- [ ] CI/CD básico (GitHub Actions)

### Semana 5-6: ETL y Conectores
**Semana 5:**
- [ ] Conector XM (demanda, generación, precios)
- [ ] Conector SUI (pérdidas, usuarios)
- [ ] Conector DANE (indicadores económicos)
- [ ] Transformadores (normalize, validate, clean)
- [ ] Loaders (PostgreSQL, Data Lake)

**Semana 6:**
- [ ] Scheduler básico (cron jobs)
- [ ] Validación de calidad de datos
- [ ] Alertas si ingesta falla
- [ ] Tests de integración ETL
- [ ] Cargar datos históricos (6 meses mínimo)

### Semana 7-8: Dashboard Prototipo
**Semana 7:**
- [ ] Setup Next.js + Tailwind
- [ ] Componentes base (layout, navbar, sidebar)
- [ ] Página de demanda nacional (gráfico línea)
- [ ] Página de pérdidas (mapa de calor)
- [ ] Integración con API backend

**Semana 8:**
- [ ] Mapa interactivo generación (Leaflet)
- [ ] Filtros por fecha y región
- [ ] Exportar a CSV/PDF
- [ ] Responsive design (mobile-friendly)
- [ ] Tests E2E (Playwright)

### Entregables HITO 1
- ✅ API FastAPI funcional (endpoints: health, reports, data)
- ✅ Pipeline ETL para XM, SUI, DANE (automático)
- ✅ Base de datos con 6 meses de datos históricos
- ✅ Dashboard con 3 paneles (demanda, pérdidas, generación)
- ✅ Tests unitarios (cobertura > 60%)
- ✅ CI/CD pipeline (build, test, deploy dev)

### Criterios de Aceptación
- [ ] ETL ejecuta correctamente para 1 mes de datos
- [ ] Dashboard muestra datos en tiempo real
- [ ] API responde en < 500ms
- [ ] Tests pasan al 100%
- [ ] Demo funcional ante equipo TIC

---

## 🤖 HITO 2: Modelos ML + RAG + Endpoints (Semanas 9-14)

**📆 Duración:** 6 semanas  
**👥 Equipo:** 2 ML engineers, 1 backend dev, 1 data scientist

### Semana 9-10: Preparación de Datos y Features
**Semana 9:**
- [ ] Feature engineering para demanda (lags, rolling stats)
- [ ] Feature engineering para precios (variables exógenas)
- [ ] Feature engineering para pérdidas (histórico OR)
- [ ] Split train/test temporal (80/20)
- [ ] Setup MLflow tracking

**Semana 10:**
- [ ] Exploración de datos (EDA notebooks)
- [ ] Análisis de correlaciones
- [ ] Detección de outliers
- [ ] Imputación de valores faltantes
- [ ] Normalización/escalado de features

### Semana 11-12: Entrenamiento de Modelos
**Semana 11:**
- [ ] Modelo demanda: Prophet (baseline)
- [ ] Modelo demanda: LSTM (avanzado)
- [ ] Evaluación: RMSE, MAE, MAPE
- [ ] Hyperparameter tuning (Optuna)
- [ ] Backtesting con ventana deslizante

**Semana 12:**
- [ ] Modelo precio: ARIMA + variables exógenas
- [ ] Modelo pérdidas: XGBoost classifier
- [ ] Evaluación: AUC-ROC, F1-score
- [ ] Calibración de probabilidades
- [ ] Versionado en MLflow

### Semana 13: Sistema RAG
- [ ] Setup Weaviate (vector DB)
- [ ] Indexar documentos (informes XM, resoluciones CREG)
- [ ] Embeddings con OpenAI text-embedding-ada-002
- [ ] Implementar retriever (top-k=3)
- [ ] Tests de relevancia (precision@3)

### Semana 14: Endpoints ML en API
- [ ] POST /predict/demanda (forecast 7 días)
- [ ] POST /predict/precio (precio hora siguiente)
- [ ] POST /predict/perdidas (scoring riesgo OR)
- [ ] POST /rag/query (consulta documentos)
- [ ] Registro de trazabilidad (modelo, versión, métricas)
- [ ] Dashboard actualizado con predicciones

### Entregables HITO 2
- ✅ 3 modelos entrenados y versionados (MLflow)
- ✅ Endpoints de predicción en API
- ✅ Sistema RAG funcional (vector DB + retriever)
- ✅ Dashboard con panel de predicciones
- ✅ Documentación de modelos (features, métricas)

### Criterios de Aceptación
- [ ] Modelo demanda: RMSE < 5% promedio
- [ ] Modelo precio: MAE < $10 COP/kWh
- [ ] Modelo pérdidas: AUC-ROC > 0.75
- [ ] RAG retorna 3 fuentes en < 2s
- [ ] Predicciones registradas en MLflow

---

## 💬 HITO 3: Agente + WhatsApp + Noticias (Semanas 15-20)

**📆 Duración:** 6 semanas  
**👥 Equipo:** 1 AI/LLM engineer, 1 backend dev, 1 QA, coordinación con Comunicaciones

### Semana 15-16: Agente Conversacional
**Semana 15:**
- [ ] Setup LangChain + OpenAI GPT-4
- [ ] Implementar memoria conversacional (Redis)
- [ ] Crear herramientas: SQL tool, plot tool, RAG tool
- [ ] Prompt engineering (system prompt, few-shot examples)
- [ ] Tests de calidad de respuestas

**Semana 16:**
- [ ] Integrar simuladores como tools
- [ ] Implementar router de intención
- [ ] Manejo de errores y fallbacks
- [ ] Límites de tokens y contexto
- [ ] Auditoría: log completo de interacciones

### Semana 17: Integración WhatsApp Business
- [ ] Crear cuenta Meta Business Manager
- [ ] Configurar WhatsApp Business App
- [ ] Obtener Phone Number ID y tokens
- [ ] Implementar webhook (FastAPI endpoint)
- [ ] Validación HMAC de mensajes entrantes
- [ ] Pruebas en sandbox

### Semana 18: Plantillas y Automatización
- [ ] Diseñar plantillas de mensajes (con Comunicaciones)
- [ ] Enviar para aprobación a Meta
- [ ] Implementar scheduler de resúmenes diarios (7 AM)
- [ ] Implementar alertas críticas (tiempo real)
- [ ] Whitelist de números autorizados

### Semana 19: Sistema de Noticias
- [ ] Scrapers: Portafolio, La República, MinMinas
- [ ] Extractor de titulares (BeautifulSoup)
- [ ] Sumarizador (extractive + abstractive)
- [ ] Ranking por relevancia (keywords sector)
- [ ] Scheduler: ejecutar a las 6:30 AM diario

### Semana 20: Integración y Tests
- [ ] Dashboard: módulo "Pregunta al Asistente"
- [ ] Tests end-to-end (WhatsApp → Agente → Respuesta)
- [ ] Validación de fuentes citadas
- [ ] Pruebas de carga (100 usuarios concurrentes)
- [ ] Ajustes finales

### Entregables HITO 3
- ✅ Agente conversacional con LLM + RAG
- ✅ Integración WhatsApp Business Cloud
- ✅ Resumen diario automatizado (enviado a las 7 AM)
- ✅ Top-3 noticias diarias
- ✅ Dashboard con chat integrado
- ✅ Logs de auditoría completos

### Criterios de Aceptación
- [ ] Agente responde en < 3s
- [ ] 100% respuestas citan 3 fuentes
- [ ] WhatsApp envía resumen 5 días consecutivos
- [ ] Top-3 noticias relevantes (validación manual)
- [ ] Todas las interacciones en audit log

---

## 🎮 HITO 4: Simuladores + Orquestación + Seguridad (Semanas 21-26)

**📆 Duración:** 6 semanas  
**👥 Equipo:** 1 ML engineer, 1 DevOps, 1 security specialist, 1 QA

### Semana 21-22: Simuladores
**Semana 21:**
- [ ] Simulador hidrológico (balance hídrico + aportes)
- [ ] Escenarios: Niño, Niña, Neutro
- [ ] Outputs: proyección % llenado embalses (3 meses)
- [ ] Validación con datos históricos

**Semana 22:**
- [ ] Simulador mercado (merit-order + precios)
- [ ] Inputs: disponibilidad térmica/hidro, demanda
- [ ] Outputs: curva precios, despacho por tecnología
- [ ] Simulador confiabilidad (análisis N-1)

### Semana 23: Orquestación (Airflow)
- [ ] Setup Airflow (Docker Compose)
- [ ] DAG diario: ETL → training incremental
- [ ] DAG semanal: retraining completo
- [ ] DAG mensual: backtesting + reportes
- [ ] Alertas si DAG falla

### Semana 24-25: Pruebas de Seguridad
**Semana 24:**
- [ ] Pentest básico (OWASP Top 10)
- [ ] Escaneo de vulnerabilidades (Trivy, Snyk)
- [ ] Revisión de código (SonarQube)
- [ ] Hardening de servidores (CIS Benchmarks)

**Semana 25:**
- [ ] Corrección de vulnerabilidades críticas
- [ ] Implementar WAF (Web Application Firewall)
- [ ] Configurar rate limiting
- [ ] Certificados TLS actualizados
- [ ] Informe de pentest

### Semana 26: Documentación Operativa
- [ ] Manual del operador (cómo ejecutar pipelines)
- [ ] Runbook (qué hacer en caso de fallo)
- [ ] Guía de troubleshooting
- [ ] Diagramas actualizados
- [ ] API documentation (Swagger)

### Entregables HITO 4
- ✅ 3 simuladores operativos (API endpoints)
- ✅ Orquestador Airflow con 3 DAGs
- ✅ Informe de pentest sin críticos
- ✅ Documentación operativa completa
- ✅ Checklist de seguridad completo

### Criterios de Aceptación
- [ ] Simuladores ejecutan en < 15s
- [ ] DAG diario sin fallos 7 días consecutivos
- [ ] Pentest: 0 vulnerabilidades críticas
- [ ] Documentación revisada por TIC

---

## 🚀 HITO 5: Despliegue Producción + Transferencia (Semanas 27-36)

**📆 Duración:** 10 semanas  
**👥 Equipo:** 1 DevOps, 1 SRE, 2 capacitadores, equipo ministerial

### Semana 27-29: Infraestructura Kubernetes
**Semana 27:**
- [ ] Provisionar cluster K8s (GKE/EKS/AKS)
- [ ] Configurar namespaces (dev, staging, prod)
- [ ] Setup Ingress NGINX + Cert Manager
- [ ] Configurar autoscaling (HPA)

**Semana 28:**
- [ ] Manifiestos: Deployments, Services, ConfigMaps
- [ ] Secrets con Sealed Secrets + KMS
- [ ] NetworkPolicies (deny by default)
- [ ] PodSecurityPolicies

**Semana 29:**
- [ ] Despliegue en ambiente staging
- [ ] Tests de integración staging
- [ ] Load testing (Locust, k6)
- [ ] Ajustes de performance

### Semana 30-31: CI/CD y Monitoreo
**Semana 30:**
- [ ] GitHub Actions: build → test → deploy
- [ ] Rollback automático si falla health check
- [ ] Deploy a staging (merge a develop)
- [ ] Deploy a prod (merge a main, manual approval)

**Semana 31:**
- [ ] Setup Prometheus + Grafana
- [ ] Dashboards: API, DB, ML, Agente
- [ ] Setup ELK Stack (logs centralizados)
- [ ] Alertmanager (notificaciones críticas)

### Semana 32-33: Despliegue Producción
**Semana 32:**
- [ ] Deployment a producción (domingo 2 AM)
- [ ] Monitoreo intensivo 24h
- [ ] Validación de métricas (uptime, latencia)
- [ ] Resolución de incidentes si aplica

**Semana 33:**
- [ ] Semana de estabilización
- [ ] Ajustes de configuración
- [ ] Optimización de queries lentas
- [ ] Backup y recovery tests

### Semana 34-36: Capacitación y Transferencia
**Semana 34:**
- [ ] Sesión 1: Introducción a SIEA (equipo completo)
- [ ] Sesión 2: Dashboard y reportes (analistas)
- [ ] Sesión 3: Agente WhatsApp (comunicaciones)

**Semana 35:**
- [ ] Sesión 4: Operación técnica (TIC)
- [ ] Sesión 5: Troubleshooting (TIC)
- [ ] Evaluación práctica (hands-on)
- [ ] Entrega de manuales

**Semana 36:**
- [ ] Demo final ante Ministro y directivos
- [ ] Firma de acta de entrega
- [ ] Transferencia formal al equipo MME
- [ ] Cierre administrativo del proyecto

### Entregables HITO 5
- ✅ Sistema en producción (K8s)
- ✅ CI/CD pipeline completo
- ✅ Monitoreo 24/7 (Prometheus + ELK)
- ✅ Equipo ministerial capacitado
- ✅ Demo exitosa ante autoridades
- ✅ Acta de entrega firmada

### Criterios de Aceptación
- [ ] Uptime > 99.5% durante 2 semanas
- [ ] CI/CD deploy en < 15 min
- [ ] Monitoreo registra todas las métricas
- [ ] Evaluación equipo: > 80% aprobados
- [ ] Demo exitosa (checklist cumplido)

---

## 📊 DASHBOARD DE PROGRESO

### Métricas Clave (KPIs)
| KPI | Target | Actual | Status |
|-----|--------|--------|--------|
| % Hitos completados | 100% | 60% | 🟡 En progreso |
| Cobertura tests | > 70% | 65% | 🟡 En progreso |
| Vulnerabilidades críticas | 0 | 0 | ✅ OK |
| Uptime producción | > 99.5% | - | ⏳ Pendiente |
| Equipo capacitado | 100% | 0% | ⏳ Pendiente |

### Riesgos Activos
| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Demora acceso datos privados | Media | Alto | Iniciar con datos públicos |
| Rechazo plantillas WhatsApp | Media | Alto | Pre-aprobar con Comunicaciones |
| Falta de internet en servidor | Alta | Crítico | **BLOQUEADOR ACTUAL** → Escalar a TIC |

---

**Última actualización:** 2025-12-02  
**Responsable:** [Tu Nombre] - Líder Técnico SIEA

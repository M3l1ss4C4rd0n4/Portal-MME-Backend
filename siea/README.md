# SIEA - Sistema Integral de Inteligencia Energética y Asistencia Ministerial

[![Status](https://img.shields.io/badge/Status-En%20Desarrollo-yellow)](https://github.com/minminas/siea)
[![License](https://img.shields.io/badge/License-Gobierno%20de%20Colombia-blue)](LICENSE)
[![Compliance](https://img.shields.io/badge/Compliance-Ley%201581%2F2012-green)](legal/PLANTILLAS_LEGALES_SIEA.md)
[![Security](https://img.shields.io/badge/Security-ISO%2027001-green)](docs/SEGURIDAD_AUDITORIA.md)

---

## 📖 ¿Qué es SIEA?

El **Sistema Integral de Inteligencia Energética y Asistencia Ministerial (SIEA)** es una plataforma institucional del **Ministerio de Minas y Energía de Colombia** que integra:

- 🤖 **Inteligencia Artificial**: Agente conversacional con GPT-4 + RAG para responder consultas técnicas del sector energético
- 📊 **Analítica Avanzada**: Dashboard interactivo con visualizaciones en tiempo real de demanda, generación, pérdidas y precios
- 🔮 **Modelos Predictivos**: Pronósticos de demanda (7 días), precios bolsa (1 hora) y scoring de riesgo de pérdidas no técnicas
- 🎮 **Simuladores**: Escenarios hidrológicos, mercado eléctrico y análisis de confiabilidad
- 💬 **WhatsApp Business**: Asistente disponible 24/7 con resúmenes diarios y alertas críticas
- 📰 **Monitoreo de Noticias**: Top-3 noticias relevantes del sector energético cada día

---

## 🎯 Características Clave

### ✅ Ingesta Automatizada de Datos
- **Fuentes**: XM, SUI, CREG, UPME, DANE, MinMinas, datos.gov.co
- **Pipeline ETL**: Extracción, transformación y carga automática (diaria)
- **Calidad de Datos**: Validación, limpieza y alertas si ingesta falla

### 🧠 Modelos de Machine Learning
- **Demanda Nacional**: Prophet + LSTM (RMSE < 5%)
- **Precio Bolsa**: ARIMA + variables exógenas (MAE < $10 COP/kWh)
- **Pérdidas No Técnicas**: XGBoost (AUC-ROC > 0.75)
- **Tracking**: MLflow para versionado y reproducibilidad

### 🤖 Agente Conversacional
- **LLM**: OpenAI GPT-4 con context window de 128K tokens
- **RAG**: Vector DB (Weaviate) con documentos oficiales (informes XM, resoluciones CREG)
- **Herramientas**: SQL queries, generación de gráficos, ejecución de simuladores
- **Memoria**: Redis para contexto conversacional
- **Auditoría**: Todas las interacciones registradas (7 años)

### 📊 Dashboard Interactivo
- **Tecnología**: Next.js 14 + React 18 + TypeScript
- **Visualizaciones**: Plotly.js para gráficos interactivos, Leaflet para mapas
- **Paneles**: Demanda, generación, pérdidas, restricciones, transmisión, métricas
- **Responsive**: Optimizado para desktop, tablet y móvil

### 💬 Integración WhatsApp Business Cloud
- **Número Oficial**: Solo con línea corporativa del Ministerio
- **Mensajes Automatizados**: Resumen diario (7 AM), alertas críticas (tiempo real)
- **Seguridad**: Webhook con validación HMAC-SHA256
- **Compliance**: Plantillas aprobadas por Meta

### 🎮 Simuladores
- **Hidrológico**: Escenarios Niño/Niña/Neutro → Proyección de embalses (3-6 meses)
- **Mercado**: Merit-order + despacho → Curva de precios
- **Confiabilidad**: Análisis N-1 → Riesgo de racionamiento

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        Capa de Presentación                      │
│  Dashboard Web (React) │ WhatsApp Bot │ API REST Pública         │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│                        Capa de Aplicación                        │
│  FastAPI Backend │ Agente LLM+RAG │ ML Inference │ Simuladores  │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│                          Capa de Datos                           │
│  PostgreSQL+TimescaleDB │ Vector DB │ Redis │ Data Lake (S3)    │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│                      Capa de Ingesta (ETL)                       │
│  Airflow/Prefect │ Extractors │ Transformers │ Loaders          │
└─────────────────────────────────────────────────────────────────┘
```

👉 **[Ver arquitectura completa](docs/ARQUITECTURA_SIEA.md)**

---

## 💻 Stack Tecnológico

### Backend
- **API**: FastAPI 0.109+ + Uvicorn 0.27+
- **ORM**: SQLAlchemy 2.0+ (async) + asyncpg
- **Validación**: Pydantic 2.5+

### Frontend
- **Framework**: Next.js 14 + React 18 + TypeScript
- **Estilos**: Tailwind CSS 3.4+
- **Charts**: Plotly.js 2.27+
- **Mapas**: Leaflet 1.9+

### Bases de Datos
- **OLTP**: PostgreSQL 16 + TimescaleDB 2.13+
- **OLAP**: DuckDB 0.10+ (análisis ad-hoc)
- **Cache**: Redis 7.2+
- **Vector DB**: Weaviate 1.23+

### Machine Learning
- **LLM**: OpenAI GPT-4
- **Embeddings**: text-embedding-ada-002
- **ML**: scikit-learn, XGBoost, Prophet, PyTorch
- **Tracking**: MLflow 2.10+
- **Framework**: LangChain 0.1+

### Infraestructura
- **Contenedores**: Docker 24+ + Kubernetes 1.29+
- **Ingress**: NGINX + Cert Manager (Let's Encrypt)
- **CI/CD**: GitHub Actions
- **IaC**: Terraform 1.7+

### Observabilidad
- **Métricas**: Prometheus 2.49+ + Grafana 10.3+
- **Logs**: ELK Stack 8.12+
- **Alertas**: Alertmanager 0.26+

---

## 📁 Estructura del Proyecto

```
siea/
├── backend/              # API FastAPI + ETL
│   ├── api/              # Routers (endpoints)
│   ├── etl/              # Extractors, Transformers, Loaders
│   ├── db/               # Models, Migrations (Alembic)
│   └── config/           # Configuración
│
├── frontend/             # Dashboard Next.js
│   ├── app/              # App Router (Next.js 14)
│   ├── components/       # Componentes React
│   ├── services/         # Llamadas a API
│   └── store/            # Estado global (Zustand)
│
├── ml/                   # Modelos de Machine Learning
│   ├── models/           # Demanda, Precio, Pérdidas
│   ├── training/         # Scripts de entrenamiento
│   ├── inference/        # Endpoints de predicción
│   └── evaluation/       # Backtesting, métricas
│
├── agent/                # Agente Conversacional
│   ├── core/             # LLM, Memory, Tools
│   ├── rag/              # Vector DB + Retriever
│   ├── whatsapp/         # Integración WhatsApp Business
│   └── news/             # Scrapers + Sumarizador
│
├── sims/                 # Simuladores
│   ├── hydrologic/       # Escenarios climáticos
│   ├── market/           # Merit-order + precios
│   └── reliability/      # Análisis N-1
│
├── data/                 # Datasets (históricos)
│
├── docs/                 # Documentación técnica
│   ├── ARQUITECTURA_SIEA.md
│   ├── ROADMAP_HITOS.md
│   ├── WHATSAPP_BUSINESS_INTEGRACION.md
│   └── SEGURIDAD_AUDITORIA.md
│
├── legal/                # Plantillas legales
│   └── PLANTILLAS_LEGALES_SIEA.md
│
├── deployment/           # Kubernetes manifests + Terraform
│   ├── k8s/              # Deployments, Services, Ingress
│   └── terraform/        # Infraestructura como código
│
├── scripts/              # Utilitarios (backup, validación)
│
├── tests/                # Tests E2E
│
├── SIEA_PROYECTO_COMPLETO.md  # Especificación completa
└── README.md             # Este archivo
```

---

## 🚀 Inicio Rápido

### Prerrequisitos

- Python 3.11+
- Node.js 20+
- PostgreSQL 16+
- Redis 7.2+
- Docker 24+

### Instalación (Backend)

```bash
cd siea/backend

# Crear entorno virtual
python3.11 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# Ejecutar migraciones
alembic upgrade head

# Iniciar servidor
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Instalación (Frontend)

```bash
cd siea/frontend

# Instalar dependencias
npm install

# Configurar variables de entorno
cp .env.example .env.local
# Editar .env.local

# Iniciar en modo desarrollo
npm run dev
```

### Despliegue con Docker Compose

```bash
docker-compose up -d
```

---

## 📚 Documentación

- 📘 **[Proyecto Completo (48 páginas)](SIEA_PROYECTO_COMPLETO.md)**: Especificación institucional, requisitos, hitos, criterios de aceptación
- 🏗️ **[Arquitectura Técnica (30 páginas)](docs/ARQUITECTURA_SIEA.md)**: Diagramas, stack, flujos de datos, seguridad, escalabilidad
- 📅 **[Roadmap por Hitos (36 semanas)](docs/ROADMAP_HITOS.md)**: Cronograma detallado, entregables, KPIs
- 💬 **[Integración WhatsApp Business](docs/WHATSAPP_BUSINESS_INTEGRACION.md)**: Guía paso a paso para número oficial
- 🔒 **[Seguridad y Auditoría](docs/SEGURIDAD_AUDITORIA.md)**: Checklist TLS, KMS, pentest, cumplimiento Ley 1581/2012

---

## 📜 Legal y Cumplimiento

### 🔐 Protección de Datos (Ley 1581/2012)

El sistema SIEA cumple con todos los requisitos de la **Ley 1581 de 2012** (Protección de Datos Personales):

- ✅ **DPIA** (Data Protection Impact Assessment) completado
- ✅ **Convenios de datos** con distribuidoras y operadores de red
- ✅ **NDAs** (Acuerdos de Confidencialidad) para personal con acceso
- ✅ **Política de retención y eliminación** (7 años)
- ✅ **Derechos ARCO** habilitados (Acceso, Rectificación, Cancelación, Oposición)

👉 **[Ver plantillas legales completas](legal/PLANTILLAS_LEGALES_SIEA.md)**

### 🔒 Seguridad

- **TLS 1.3**: Comunicaciones encriptadas
- **OAuth2 + JWT**: Autenticación robusta
- **MFA**: Factor múltiple para administradores
- **RBAC**: Control de acceso basado en roles
- **KMS**: Gestión de secretos (AWS KMS / Azure Key Vault)
- **Pentest**: Semestral con remediación de vulnerabilidades críticas

### 🛡️ Estándares

- **ISO 27001**: Gestión de Seguridad de la Información
- **OWASP Top 10**: Sin vulnerabilidades críticas o altas
- **CIS Benchmarks**: Hardening de servidores

---

## 👥 Contribuir

Este es un proyecto institucional del Ministerio de Minas y Energía. Las contribuciones están limitadas a:

- **Empleados directos** del Ministerio
- **Contratistas autorizados** con NDA firmado
- **Proveedores** con convenio de datos vigente

### Flujo de Trabajo

1. Crea un branch desde `develop`: `git checkout -b feature/nueva-funcionalidad`
2. Implementa cambios con tests
3. Corre checklist de calidad: `./scripts/checklist_commit.sh`
4. Crea Pull Request a `develop`
5. Espera aprobación de 2 revisores
6. Merge después de pasar CI/CD

---

## 📞 Contacto

- **Equipo Técnico**: [correo_tecnico@minminas.gov.co]
- **Soporte TIC**: [soporte_tic@minminas.gov.co]
- **Reportar Incidentes de Seguridad**: [seguridad@minminas.gov.co]

---

## 📄 Licencia

Este sistema es propiedad del **Gobierno de Colombia - Ministerio de Minas y Energía**.  
Todos los derechos reservados. Uso exclusivo institucional.

---

## 🙏 Agradecimientos

- **XM S.A. E.S.P.**: Por datos abiertos de operación del sistema eléctrico
- **Superintendencia de Servicios Públicos Domiciliarios (SUI)**: Por datos de pérdidas y calidad
- **CREG**: Por resoluciones y normativa del sector
- **UPME**: Por proyecciones de demanda y capacidad
- **OpenAI**: Por GPT-4 y embeddings
- **Meta**: Por WhatsApp Business Cloud API

---

**Última actualización:** 2025-12-02  
**Versión:** 0.1.0 (En Desarrollo - HITO 0)  
**Estado:** 🚀 Preparación para inicio de desarrollo

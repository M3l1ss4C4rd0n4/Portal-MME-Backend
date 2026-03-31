# 🎓 Guía de Onboarding - Portal Energético MME

**Fecha:** Marzo 2026  
**Versión:** 1.0  
**Tiempo estimado:** 2-3 días

Bienvenido al equipo del Portal Energético MME. Esta guía te ayudará a configurar tu entorno de desarrollo y entender la arquitectura del sistema.

---

## 📋 Checklist de Primer Día

- [ ] Acceso al servidor concedido
- [ ] Acceso a base de datos PostgreSQL
- [ ] Clonar repositorio
- [ ] Configurar entorno virtual Python
- [ ] Ejecutar tests básicos
- [ ] Leer documentación de arquitectura
- [ ] Primera ejecución del dashboard

---

## 🚀 Configuración del Entorno

### 1. Clonar Repositorio

```bash
git clone https://github.com/MelissaCardona2003/Dashboard_Multipage_MME.git
cd Dashboard_Multipage_MME
```

### 2. Configurar Entorno Virtual

```bash
# Crear entorno virtual
python3 -m venv venv

# Activar
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Configurar Variables de Entorno

```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar con tus credenciales
nano .env
```

**Variables mínimas necesarias:**
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=portal_energetico
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<tu_password>

DASH_DEBUG=True
DASH_PORT=8050

REDIS_HOST=localhost
REDIS_PORT=6379
```

---

## 🏗️ Entendiendo la Arquitectura

### Estructura del Proyecto

```
server/
├── core/               # Configuración, DI, seguridad
├── domain/             # Lógica de negocio, servicios
├── infrastructure/     # Adaptadores, bases de datos
├── interface/          # Dashboard (Dash)
├── api/                # API REST (FastAPI)
├── etl/                # Pipelines de datos
├── tasks/              # Tareas Celery
├── whatsapp_bot/       # Bot Telegram/WhatsApp
├── tests/              # Tests unitarios e integración
└── docs/               # Documentación
```

### Componentes Principales

| Componente | Tecnología | Descripción |
|------------|------------|-------------|
| Dashboard | Dash/Plotly | Interfaz visual interactiva |
| API | FastAPI | Endpoints REST |
| Base de datos | PostgreSQL | Almacenamiento de datos XM |
| Caché | Redis | Caché y broker Celery |
| ML | Prophet/ARIMA | Predicciones de series temporales |
| IA | Groq/OpenRouter | Chatbot e informes ejecutivos |

---

## 📝 Primeros Pasos

### 1. Ejecutar el Dashboard

```bash
# Asegurarte de estar en el entorno virtual
source venv/bin/activate

# Ejecutar
python3 app.py

# Abrir en navegador
http://localhost:8050
```

### 2. Ejecutar la API

```bash
# Modo desarrollo
python3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Documentación automática
http://localhost:8000/api/docs
```

### 3. Ejecutar Tests

```bash
# Tests de seguridad
python3 -m pytest tests/security/ -v

# Tests unitarios
python3 -m pytest tests/unit/ -v

# Todos los tests
python3 -m pytest tests/ -v --ignore=tests/legacy
```

---

## 📚 Documentación Obligatoria

### Lee en este orden:

1. [../README.md](../README.md) - Visión general
2. [ARQUITECTURA_E2E.md](ARQUITECTURA_E2E.md) - Arquitectura completa
3. [GUIA_USO_API.md](GUIA_USO_API.md) - Cómo usar la API
4. [DOCUMENTACION_TECNICA_ORQUESTADOR.md](DOCUMENTACION_TECNICA_ORQUESTADOR.md) - Orquestador
5. [MAPEO_COMPLETO_METRICAS.md](MAPEO_COMPLETO_METRICAS.md) - Métricas XM

---

## 🎯 Tu Primera Tarea

Para familiarizarte con el código, te sugerimos:

### Opción A: Dashboard
1. Abre `interface/pages/home.py`
2. Localiza el componente de KPIs
3. Modifica el color de un indicador
4. Reinicia y verifica el cambio

### Opción B: API
1. Abre `api/v1/routes/generation.py`
2. Agrega un nuevo endpoint simple
3. Prueba con curl o navegador
4. Documenta en Swagger

### Opción C: ETL
1. Abre `etl/etl_todas_metricas_xm.py`
2. Identifica el flujo de descarga de datos
3. Agrega una métrica nueva
4. Ejecuta y verifica

---

## 🐛 Debugging

### VS Code (recomendado)

```json
// .vscode/launch.json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Dashboard",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/app.py",
            "console": "integratedTerminal"
        },
        {
            "name": "API",
            "type": "python",
            "request": "launch",
            "module": "uvicorn",
            "args": ["api.main:app", "--reload", "--port", "8000"]
        }
    ]
}
```

### Logging

```python
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)
logger.info("Mensaje informativo")
logger.error("Error con contexto", exc_info=True)
```

---

## 🔐 Seguridad

### Buenas prácticas:

1. **Nunca** commitees archivos `.env` o `.vault_key`
2. **Siempre** usa `sql_validator` para queries dinámicas
3. **Valida** todas las entradas de usuario
4. **Revisa** tus cambios antes de hacer PR

### Pre-commit hooks:

```bash
# Instalar pre-commit
pip install pre-commit

# Configurar hooks
pre-commit install
```

---

## 📞 Obtener Ayuda

### Canales de comunicación:

| Canal | Uso |
|-------|-----|
| Issues de GitHub | Bugs, feature requests |
| Correo | Consultas generales |
| Telegram | Soporte urgente |

### Personas clave:

| Rol | Nombre | Contacto |
|-----|--------|----------|
| Tech Lead | [Nombre] | [Correo] |
| DBA | [Nombre] | [Correo] |
| DevOps | [Nombre] | [Correo] |

---

## ✅ Checklist Final (Fin de Semana 1)

- [ ] Dashboard ejecutándose localmente
- [ ] API respondiendo en puerto 8000
- [ ] Tests pasando
- [ ] Primera contribución merged
- [ ] Documentación revisada
- [ ] Entorno de staging accesible

---

## 📚 Recursos Adicionales

- [GUIA_TROUBLESHOOTING.md](GUIA_TROUBLESHOOTING.md) - Problemas comunes
- [CRON_JOB_ETL_POSTGRESQL.md](CRON_JOB_ETL_POSTGRESQL.md) - ETL automatizado
- [INVENTARIO_SERVIDOR.md](INVENTARIO_SERVIDOR.md) - Configuración del servidor

---

## 🎉 ¡Bienvenido al Equipo!

Estamos emocionados de tenerte con nosotros. Si tienes alguna pregunta, no dudes en preguntar.

**Tu primera semana es para aprender. Tómate tu tiempo y disfruta el proceso.**

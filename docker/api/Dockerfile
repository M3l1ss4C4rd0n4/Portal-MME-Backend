# ═══════════════════════════════════════════════════════════════════════════════
# Dockerfile - API REST & Dashboard Portal Energético MME
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: Base dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim as base

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    # Para PDF generation (WeasyPrint)
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libffi-dev \
    shared-mime-info \
    # Limpieza
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2: Dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM base as dependencies

# Copiar requirements e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3: Production image
# ─────────────────────────────────────────────────────────────────────────────
FROM base as production

# Copiar dependencias instaladas
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copiar código de la aplicación
COPY . .

# Crear directorios necesarios
RUN mkdir -p logs/api logs/dashboard logs/celery data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Puerto expuesto
EXPOSE 8000 8050

# Comando por defecto (puede ser sobreescrito en docker-compose)
CMD ["gunicorn", "api.main:app", \
     "--workers", "4", \
     "--threads", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "/app/logs/api/access.log", \
     "--error-logfile", "/app/logs/api/error.log", \
     "--log-level", "info"]

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4: Development image
# ─────────────────────────────────────────────────────────────────────────────
FROM dependencies as development

# Instalar dependencias de desarrollo
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    black \
    flake8 \
    mypy \
    debugpy

# Copiar código
COPY . .

# Puerto para debugging
EXPOSE 8000 8050 5678

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

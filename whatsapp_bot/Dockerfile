# ═══════════════════════════════════════════════════════════
# WhatsApp Bot - Portal Energético MME
# Multi-stage Docker build
# ═══════════════════════════════════════════════════════════

FROM python:3.11-slim as base

# Metadata
LABEL maintainer="Portal Energético MME"
LABEL description="WhatsApp Bot para consultas energéticas"

# Variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Directorio de trabajo
WORKDIR /app

# ═══════════════════════════════════════════════════════════
# Dependencies Stage
# ═══════════════════════════════════════════════════════════
FROM base as dependencies

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Instalar Playwright browsers (para scraping)
RUN playwright install chromium && \
    playwright install-deps chromium

# Descargar modelo spaCy español
RUN python -m spacy download es_core_news_sm

# ═══════════════════════════════════════════════════════════
# Production Stage
# ═══════════════════════════════════════════════════════════
FROM base as production

# Copiar dependencias instaladas
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin
COPY --from=dependencies /root/.cache/ms-playwright /root/.cache/ms-playwright

# Instalar solo runtime dependencies (más ligero)
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear directorios necesarios
RUN mkdir -p /app/logs /app/data /app/celery_data

# Copiar código de la aplicación
COPY . .

# Crear usuario no-root por seguridad
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

USER botuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Exponer puerto
EXPOSE 8001

# Comando por defecto
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]

# ═══════════════════════════════════════════════════════════════════════════════
# Dockerfile - Telegram Bot Portal Energético MME
# ═══════════════════════════════════════════════════════════════════════════════

FROM python:3.11-slim

# Instalar dependencias del sistema
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
    # Para Chrome/Puppeteer (si se usa para screenshots)
    chromium \
    chromium-driver \
    # Limpieza
    && rm -rf /var/lib/apt/lists/*

# Variables de entorno para Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements del bot
COPY whatsapp_bot/requirements.txt ./requirements-bot.txt

# Instalar dependencias del bot
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-bot.txt

# Instalar dependencias adicionales necesarias del servidor
# (El bot importa módulos del servidor)
COPY requirements.txt ./requirements-server.txt
RUN pip install --no-cache-dir -r requirements-server.txt

# Copiar código del bot
COPY whatsapp_bot/ .

# Copiar código del servidor (necesario para imports)
COPY domain/ /app/server/domain/
COPY infrastructure/ /app/server/infrastructure/
COPY core/ /app/server/core/
COPY api/ /app/server/api/
COPY tasks/ /app/server/tasks/
COPY etl/ /app/server/etl/

# Crear directorios necesarios
RUN mkdir -p logs informes data

# Configurar PYTHONPATH para encontrar los módulos del servidor
ENV PYTHONPATH=/app:/app/server

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f telegram_polling.py || exit 1

# Comando por defecto
CMD ["python", "telegram_polling.py"]

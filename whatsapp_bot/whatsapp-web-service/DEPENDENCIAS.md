# 🔧 Instalación de Dependencias para WhatsApp Web

El servicio whatsapp-web.js requiere Chrome/Chromium y sus dependencias del sistema.

## Opción 1: Instalación Completa (Requiere sudo)

```bash
sudo apt-get update
sudo apt-get install -y \
    gconf-service \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgcc1 \
    libgconf-2-4 \
    libgdk-pixbuf2.0-0 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    ca-certificates \
    fonts-liberation \
    libappindicator1 \
    libnss3 \
    lsb-release \
    xdg-utils \
    wget
```

Luego ejecuta:
```bash
cd /home/admonctrlxm/server/whatsapp_bot
./start-whatsapp-web.sh
```

## Opción 2: Sin sudo (Usar en máquina con GUI)

Si no tienes acceso a sudo, whatsapp-web.js requiere un entorno con capacidades gráficas.

**Alternativas**:

1. **Solicitar al administrador** que instale las dependencias arriba
2. **Usar en tu PC local** donde tengas permisos
3. **Usar Docker** (ver abajo)

## Opción 3: Docker (Recomendado para servidores)

Crea `/home/admonctrlxm/server/whatsapp_bot/whatsapp-web-service/Dockerfile`:

```dockerfile
FROM node:20-slim

# Instalar dependencias de Chrome
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-sandbox \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libnspr4 \
    libnss3 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Variables de entorno para Puppeteer
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["node", "server.js"]
```

Luego:
```bash
cd /home/admonctrlxm/server/whatsapp_bot/whatsapp-web-service
docker build -t whatsapp-web-service .
docker run -d -p 3000:3000 --name whatsapp-web-service whatsapp-web-service
```

## Solución Actual

**Para tu servidor actual**, necesitas que alguien con acceso sudo ejecute:

```bash
sudo apt-get install -y libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 libx11-6 libx11-xcb1 libxcb1 libnss3 libnspr4 ca-certificates fonts-liberation
```

Es una instalación rápida (~50MB) y solo se hace una vez.

## Alternativa: Seguir usando Twilio/Meta

Si no puedes instalar las dependencias:
- **Mantén Twilio** para testing ($0.005/msg)
- **Migra a Meta API** para producción (1000 msg/mes gratis)

El costo real para 10,000 mensajes/mes con Meta es solo **$18 USD**.

---

## ¿Qué hacer ahora?

1. **Si tienes acceso sudo**: Ejecuta el comando de instalación arriba
2. **Si no tienes sudo**: Solicita al admin del servidor que instale las dependencias
3. **Mientras tanto**: Usa Twilio (ya funciona) → Solo cambias `.env` cuando esté listo

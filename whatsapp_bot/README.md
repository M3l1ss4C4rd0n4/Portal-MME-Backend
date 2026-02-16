# 🤖 WhatsApp Bot - Portal Energético MME

Bot inteligente de WhatsApp para consultas del Sistema Interconectado Nacional de Colombia.

## 📋 Características

✅ **Consultas en tiempo real**
- Precio de bolsa eléctrica
- Generación por fuente (hidráulica, térmica, solar, eólica)
- Demanda del sistema
- Mix energético nacional

✅ **Análisis con IA**
- Motor Llama 3.3 70B (Groq)
- Análisis de tendencias
- Detección de anomalías
- Respuestas en lenguaje natural

✅ **Integración total**
- Base de datos del Portal Energético
- API REST existente
- AI Agent actual del dashboard

## 🚀 Quick Start

### 1. Configurar credenciales

```bash
# Copiar plantilla de entorno
cp .env.example .env

# Editar .env y configurar:
nano .env
```

Configuración mínima requerida:
```bash
# WhatsApp (usar Twilio para desarrollo)
TWILIO_ACCOUNT_SID=ACxxxxxx
TWILIO_AUTH_TOKEN=xxxxxx
TWILIO_WHATSAPP_NUMBER=+14155238886

# IA (opcional pero recomendado)
GROQ_API_KEY=gsk_xxxxxx

# Database (usar DB del portal)
DATABASE_URL=postgresql://admin:pass@localhost:5432/portal_energetico
```

### 2. Instalar dependencias

```bash
# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Descargar modelo spaCy español
python -m spacy download es_core_news_sm
```

### 3. Iniciar con Docker Compose (Recomendado)

```bash
# Levantar todos los servicios
docker-compose up -d

# Ver logs
docker-compose logs -f whatsapp-bot

# Detener
docker-compose down
```

### 4. O iniciar manualmente

```bash
# Iniciar API
uvicorn app.main:app --reload --port 8001

# En otra terminal, exponer con ngrok (para testing)
ngrok http 8001
```

## 📱 Configurar WhatsApp con Twilio

### Paso 1: Crear cuenta Twilio

1. Ir a https://www.twilio.com/console
2. Crear cuenta gratuita
3. Verificar email y teléfono

### Paso 2: Configurar Sandbox WhatsApp

1. Ir a https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
2. Seguir instrucciones para unirse al sandbox
3. Desde tu WhatsApp, enviar: `join <codigo-sandbox>`

### Paso 3: Configurar Webhook

1. En Twilio Console → Messaging → Settings → WhatsApp Sandbox Settings
2. Configurar "WHEN A MESSAGE COMES IN":
   - URL: `https://tu-dominio.com/webhook/whatsapp` (o URL ngrok)
   - Method: `POST`
3. Guardar

### Paso 4: Probar

Desde tu WhatsApp, enviar mensaje al número sandbox:
```
hola
```

Deberías recibir respuesta del bot! 🎉

## 🛠️ Desarrollo

### Estructura del Proyecto

```
whatsapp_bot/
├── app/
│   ├── main.py              # FastAPI app
│   ├── config.py            # Configuración
│   ├── webhook.py           # Handler de webhooks
│   ├── sender.py            # Envío de mensajes
│   ├── security.py          # Validación seguridad
│   └── utils/               # Utilidades
├── orchestrator/
│   └── bot.py               # Lógica central del bot
├── services/
│   ├── data_service.py      # Acceso a datos
│   └── ai_integration.py    # Integración IA
├── docker-compose.yml       # Orquestación Docker
├── Dockerfile              # Imagen Docker
└── requirements.txt        # Dependencias
```

### Testing Local

```bash
# Test endpoint de salud
curl http://localhost:8001/health

# Test envío de mensaje (reemplazar número)
curl -X POST http://localhost:8001/send \
  -H "Content-Type: application/json" \
  -d '{
    "to": "+573001234567",
    "body": "Test desde API"
  }'

# Ver estadísticas
curl http://localhost:8001/stats
```

### Logs

```bash
# Ver logs en tiempo real
tail -f logs/whatsapp_bot.log

# O con Docker
docker-compose logs -f whatsapp-bot
```

## 📊 Comandos del Bot

Una vez configurado, los usuarios pueden interactuar:

### Comandos Básicos
- `hola` - Saludo inicial
- `/help` - Ayuda completa
- `/menu` - Menú principal
- `/stats` - Estadísticas del bot

### Consultas
- `precio` - Precio de bolsa actual
- `generacion` - Generación eléctrica
- `demanda` - Demanda del sistema

### Análisis IA
- `analiza generacion` - Análisis de generación
- `analiza demanda` - Análisis de demanda
- *Cualquier pregunta en lenguaje natural*

## 🔐 Seguridad

- ✅ Validación de firmas Twilio
- ✅ Rate limiting (20 msg/min por usuario)
- ✅ Sanitización de inputs
- ✅ Logs estructurados JSON
- ✅ Variables sensibles en .env

## 📈 Monitoreo

### Prometheus Metrics

Disponible en `http://localhost:8001/metrics`:
- `whatsapp_messages_received_total`
- `whatsapp_messages_sent_total`
- `whatsapp_messages_failed_total`
- `whatsapp_processing_duration_seconds`

### Estadísticas

```bash
curl http://localhost:8001/stats
```

## 🚀 Deployment en Producción

### Con systemd

```bash
# Copiar servicio
sudo cp whatsapp-bot.service /etc/systemd/system/

# Habilitar y arrancar
sudo systemctl enable whatsapp-bot
sudo systemctl start whatsapp-bot
sudo systemctl status whatsapp-bot
```

### Con Nginx

```nginx
server {
    listen 80;
    server_name bot.portalenergetico.minenergia.gov.co;
    
    location /webhook/whatsapp {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### SSL con Certbot

```bash
sudo certbot --nginx -d bot.portalenergetico.minenergia.gov.co
```

## 🔧 Migrar a WhatsApp Business API (Producción)

Cuando estés listo para producción:

1. Crear Meta Business Account
2. Registrar WhatsApp Business App
3. Actualizar `.env`:
   ```bash
   WHATSAPP_PROVIDER=meta
   META_ACCESS_TOKEN=EAAxxxxxx
   META_PHONE_NUMBER_ID=123456789
   ```
4. Reiniciar servicio

## 📝 Próximos Features

- [ ] Generación de gráficos (Plotly)
- [ ] Screenshots de dashboards (Playwright)
- [ ] Reportes PDF personalizados
- [ ] Alertas proactivas automáticas
- [ ] Natural Language to SQL
- [ ] Conversación multi-turno con contexto

## 🐛 Troubleshooting

### Bot no responde

```bash
# Verificar que el servicio está corriendo
curl http://localhost:8001/health

# Ver logs
tail -f logs/whatsapp_bot.log

# Verificar webhook en Twilio Console
```

### Error de IA

```bash
# Verificar GROQ_API_KEY
echo $GROQ_API_KEY

# Probar API directamente
curl https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer $GROQ_API_KEY"
```

### Error de Database

```bash
# Verificar conexión a DB
psql $DATABASE_URL -c "SELECT 1"

# O para SQLite
sqlite3 portal_energetico.db "SELECT COUNT(*) FROM metrics"
```

## 📞 Soporte

- **Docs**: [ARQUITECTURA_WHATSAPP_BOT_COMPLETO.md](../docs/ARQUITECTURA_WHATSAPP_BOT_COMPLETO.md)
- **Issues**: Crear issue en el repositorio
- **Email**: soporte@portalenergetico.gov.co

## 📄 Licencia

Portal Energético - Ministerio de Minas y Energía de Colombia

---

**Desarrollado con ❤️ para democratizar el acceso a información energética** ⚡

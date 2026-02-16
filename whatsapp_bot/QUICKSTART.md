# 🎯 GUÍA DE INICIO RÁPIDO

Esta guía te llevará de **0 a Bot funcionando en 10 minutos**.

## ⚡ Opción 1: Inicio Ultra-Rápido (Recomendado)

```bash
cd /home/admonctrlxm/server/whatsapp_bot

# 1. Setup automático
./setup.sh

# 2. Editar credenciales
nano .env
# Configurar: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, GROQ_API_KEY

# 3. Iniciar bot
./start.sh
```

## 📱 Configurar WhatsApp (5 minutos)

### 1. Crear cuenta Twilio

1. Ir a: https://www.twilio.com/console
2. Sign up (gratis)
3. Ir a: Console → Account → API Keys & Tokens
4. Copiar:
   - Account SID
   - Auth Token

### 2. Activar WhatsApp Sandbox

1. Ir a: https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
2. Seguir instrucciones
3. Desde tu WhatsApp, enviar a `+1 415 523 8886`:
   ```
   join <codigo-que-te-dan>
   ```

### 3. Configurar Webhook

1. En la misma página de Sandbox Settings
2. "When a message comes in":
   - Si usas ngrok: `https://xxxx.ngrok.io/webhook/whatsapp`
   - Si tienes dominio: `https://bot.tudominio.com/webhook/whatsapp`
3. Method: `POST`
4. Guardar

### 4. Probar

Enviar mensaje al número Twilio:
```
hola
```

Deberías recibir respuesta! 🎉

## 🔑 Obtener API Keys

### Twilio (WhatsApp)
```bash
# Ir a: https://console.twilio.com
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxx
```

### Groq (IA - OPCIONAL)
```bash
# Ir a: https://console.groq.com
# Crear cuenta gratis
# Generar API Key
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxx
```

## 🌐 Exponer con ngrok (Testing)

```bash
# En otra terminal
ngrok http 8001

# Copiar URL HTTPS que te da
# Ejemplo: https://xxxx-xx-xx-xx-xx.ngrok-free.app

# Usar esa URL en Twilio webhook:
# https://xxxx-xx-xx-xx-xx.ngrok-free.app/webhook/whatsapp
```

## ✅ Verificar que Funciona

```bash
# 1. Health check
curl http://localhost:8001/health

# 2. Stats
curl http://localhost:8001/stats

# 3. Enviar mensaje de prueba
curl -X POST http://localhost:8001/send \
  -H "Content-Type: application/json" \
  -d '{
    "to": "+573001234567",
    "body": "Mensaje de prueba"
  }'
```

## 🐛 Solución de Problemas

### Bot no responde

```bash
# Ver logs
tail -f logs/whatsapp_bot.log

# Verificar webhook en Twilio Console
# Message Log → Ver si llegan mensajes
```

### Error de IA

```bash
# Si no tienes GROQ_API_KEY, el bot funcionará
# pero sin capacidades de análisis IA

# Funciones que sí funcionan sin IA:
# - precio
# - generacion
# - comandos básicos
```

### Error de Database

```bash
# Bot funciona en modo "mock" si no hay DB
# Para conectar a DB real del portal:

DATABASE_URL=postgresql://admin:pass@localhost:5432/portal_energetico

# O ruta absoluta a SQLite:
DATABASE_URL=sqlite:////home/admonctrlxm/server/portal_energetico.db
```

## 📚 Comandos del Bot

Una vez funcionando, puedes probar:

```
hola
/menu
precio
generacion
analiza demanda
/stats
```

## 🚀 Siguiente Paso: Producción

Ver [README.md](README.md) para deployment en producción con:
- Docker Compose
- Systemd
- Nginx + SSL
- WhatsApp Business API (en lugar de Twilio)

---

**¿Problemas?** Revisa los logs en `logs/whatsapp_bot.log`

# 🤖 Guía Completa: Telegram Bot - Paso a Paso

## 🎯 ¿Por qué Telegram?

### ✅ Ventajas sobre WhatsApp

| Característica | Telegram | WhatsApp (Meta) | WhatsApp (Twilio) |
|----------------|----------|-----------------|-------------------|
| **Costo** | 🎁 **100% GRATIS** | 1,000 conv/mes gratis, luego $0.002 | $0.005/mensaje |
| **Límite de mensajes** | ♾️ **ILIMITADO** | Ilimitado (paga después de 1,000) | Ilimitado (pagando) |
| **Tiempo de setup** | ⚡ **5 minutos** | 2-5 días (aprobación) | 15 minutos |
| **Verificación** | ❌ No requiere | ✅ Requiere (gubernamental) | ❌ No requiere |
| **Configuración** | 🟢 Muy fácil | 🟡 Media | 🟡 Media |
| **Multimedia** | ✅ Todo tipo | ✅ Todo tipo | ✅ Todo tipo |
| **Bots nativos** | ✅ Sí | ❌ No | ❌ No |
| **API oficial** | ✅ Sí | ✅ Sí | ⚠️ Tercero |

### 🎁 Todo GRATIS en Telegram

- ✅ Mensajes ilimitados
- ✅ Sin costo por conversación
- ✅ Sin límites de usuarios
- ✅ Sin verificación empresarial
- ✅ Setup en minutos
- ✅ API oficial y estable

---

## 📋 Tabla de Contenidos

1. [Crear Bot en Telegram](#paso-1-crear-bot-en-telegram)
2. [Obtener Token](#paso-2-obtener-token)
3. [Configurar Webhook](#paso-3-configurar-webhook)
4. [Configurar el Bot](#paso-4-configurar-bot)
5. [Probar](#paso-5-probar)
6. [Producción](#paso-6-producción)

⏰ **Tiempo total:** 15-20 minutos

---

## 🚀 Paso 1: Crear Bot en Telegram

### 1.1 Abrir Telegram

- Descarga Telegram si no lo tienes: https://telegram.org/apps
- Puedes usar la app móvil, desktop o web

### 1.2 Buscar BotFather

1. En Telegram, busca: **@BotFather**
2. Es el bot oficial de Telegram para crear bots
3. Tiene una marca de verificación azul ✓

### 1.3 Iniciar conversación

Envía el comando:
```
/start
```

Verás el menú de BotFather.

### 1.4 Crear nuevo bot

Envía el comando:
```
/newbot
```

### 1.5 Elegir nombre del bot

BotFather te preguntará: **"Alright, a new bot. How are we going to call it?"**

Responde con el nombre que quieres (puede tener espacios):
```
Portal Energético MME
```

### 1.6 Elegir username del bot

BotFather pedirá: **"Now, let's choose a username for your bot."**

**Reglas:**
- Debe terminar en `bot`
- Solo letras, números y guiones bajos
- Debe ser único

Ejemplos:
```
PortalEnergeticoMME_bot
```
o
```
MinEnergiaColombia_bot
```

### 1.7 ¡Listo! Recibir token

BotFather responderá con:
```
Done! Congratulations on your new bot...

Use this token to access the HTTP API:
1234567890:ABCdefGHIjklMNOpqrsTUVwxyz-1234567

Keep your token secure and store it safely...
```

**🔐 IMPORTANTE:** Copia y guarda ese token de forma segura. Es tu `TELEGRAM_BOT_TOKEN`.

---

## 🔧 Paso 2: Configurar el Bot (Opcional pero Recomendado)

### 2.1 Establecer descripción

Envía a BotFather:
```
/setdescription
```

Selecciona tu bot: `@PortalEnergeticoMME_bot`

Envía la descripción:
```
🔌 Bot oficial del Ministerio de Minas y Energía de Colombia

📊 Consulta información del Sistema Interconectado Nacional (SIN):
• Precio de bolsa eléctrica en tiempo real
• Generación por fuente (hidráulica, térmica, solar, eólica)
• Demanda del sistema
• Análisis con IA

🤖 Atención 24/7 automatizada
```

### 2.2 Establecer descripción corta

```
/setabouttext
```

Selecciona tu bot y envía:
```
Bot del Ministerio de Energía - Consulta datos del SIN en tiempo real 🔌⚡
```

### 2.3 Establecer foto de perfil

```
/setuserpic
```

Selecciona tu bot y sube una imagen:
- Logo del Ministerio de Minas y Energía
- O logo del Portal Energético
- Formato: JPG/PNG
- Tamaño recomendado: 512x512px

### 2.4 Configurar comandos

```
/setcommands
```

Selecciona tu bot y envía esta lista:
```
start - Iniciar bot y ver menú principal
precio - Ver precio actual de bolsa eléctrica
generacion - Ver generación por fuente energética
demanda - Ver demanda actual del sistema
mix - Ver mix energético nacional
grafico - Generar gráfico de datos
resumen - Resumen ejecutivo del día
ayuda - Ver todos los comandos disponibles
```

---

## 🌐 Paso 3: Configurar Webhook

### 3.1 Verificar que tu webhook esté accesible

```bash
curl https://portalenergetico.minenergia.gov.co/whatsapp/health
```

Debe responder con status 200.

### 3.2 Configurar webhook en Telegram

Telegram permite configurar el webhook vía API. Ejecuta:

```bash
# Reemplaza <TU_TOKEN> con el token que te dio BotFather
TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz-1234567"
WEBHOOK_URL="https://portalenergetico.minenergia.gov.co/whatsapp/webhook/telegram"

curl -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${WEBHOOK_URL}\"}"
```

Respuesta esperada:
```json
{
  "ok": true,
  "result": true,
  "description": "Webhook was set"
}
```

### 3.3 Verificar webhook configurado

```bash
curl "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"
```

Debe mostrar tu URL configurada.

---

## ⚙️ Paso 4: Configurar el Bot Python

### 4.1 Instalar librería de Telegram

```bash
cd /home/admonctrlxm/server/whatsapp_bot
source venv/bin/activate
pip install python-telegram-bot==20.7
```

### 4.2 Actualizar .env

```bash
nano .env
```

Agregar estas líneas:

```bash
# ===== TELEGRAM BOT =====
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz-1234567
TELEGRAM_ENABLED=true

# Puedes tener múltiples proveedores activos
# El bot responderá a mensajes de WhatsApp Y Telegram simultáneamente
WHATSAPP_PROVIDER=meta  # O twilio, o whatsapp-web
```

Guardar: `Ctrl+O`, `Enter`, `Ctrl+X`

### 4.3 Crear manejador de Telegram

Voy a crear el archivo para ti automáticamente. Se llamará `app/telegram_handler.py`.

---

## 🧪 Paso 5: Probar

### 5.1 Reiniciar el bot

```bash
# Detener bot actual
pkill -f "uvicorn app.main:app"

# Iniciar con nueva configuración
cd /home/admonctrlxm/server/whatsapp_bot
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 5.2 Enviar mensaje de prueba

1. Abre Telegram
2. Busca tu bot: `@PortalEnergeticoMME_bot`
3. Presiona **"Start"** o envía `/start`
4. Deberías recibir el menú del bot

### 5.3 Probar comandos

Envía:
```
precio
```

Deberías recibir el precio actual de bolsa.

Envía:
```
generacion
```

Deberías recibir datos de generación.

---

## 🚀 Paso 6: Producción

### 6.1 El bot ya funciona!

Una vez que el webhook esté configurado y el bot corriendo, ya está en producción.

**Diferencias con WhatsApp:**
- ✅ Los usuarios deben buscar y iniciar el bot (`/start`)
- ✅ El bot no puede iniciar conversaciones (los usuarios deben escribir primero)
- ✅ Puedes crear grupos y agregar el bot
- ✅ Puedes tener canales donde el bot publica información

### 6.2 Compartir el bot

**URL directa:**
```
https://t.me/PortalEnergeticoMME_bot
```

Puedes compartir este link en:
- Sitio web del ministerio
- Redes sociales
- Emails internos
- Documentos oficiales

### 6.3 Promocionar el bot

**En el sitio web:**
```html
<a href="https://t.me/PortalEnergeticoMME_bot">
  💬 Consulta vía Telegram Bot
</a>
```

**QR Code:**
Usa un generador de QR para crear código de:
```
https://t.me/PortalEnergeticoMME_bot
```

---

## 🆚 Telegram vs WhatsApp: ¿Cuál usar?

### 🎯 Usa AMBOS (Recomendado)

El bot puede funcionar simultáneamente en:
- ✅ WhatsApp (para público general)
- ✅ Telegram (para usuarios técnicos/internos)

**Ventajas de tener ambos:**
- Mayor alcance
- WhatsApp = más usuarios
- Telegram = más funciones y gratis
- Telegram = mejor para grupos internos del ministerio

### 💡 Estrategia Sugerida

```
┌─────────────────────────────────────────┐
│         PORTAL ENERGÉTICO MME            │
└─────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼────────┐    ┌────────▼───────┐
│   WHATSAPP     │    │   TELEGRAM     │
│   (Público)    │    │   (Interno)    │
└────────────────┘    └────────────────┘
        │                       │
        │                       │
┌───────▼───────────────────────▼────────┐
│        BOT UNIFICADO (FastAPI)         │
│     Orquestador + IA + Datos           │
└────────────────────────────────────────┘
```

**WhatsApp:** Para público general (más popular en Colombia)
**Telegram:** Para equipo técnico del ministerio (gratis, sin límites)

---

## 📊 Funciones Exclusivas de Telegram

Telegram soporta funciones que WhatsApp no:

### 1. Teclados Inline (Botones interactivos)

```python
# El código soportará botones como:
[Precio] [Generación] [Demanda]
[Gráfico] [Resumen] [Ayuda]
```

### 2. Grupos y Canales

- Crear canal del ministerio
- Bot publica resúmenes automáticos
- Grupos para diferentes áreas

### 3. Comandos nativos

```
/precio
/generacion
/demanda
/grafico
```

### 4. Modo inline

```
@PortalEnergeticoMME_bot precio
```

Se puede usar en cualquier chat.

### 5. Archivos grandes

- WhatsApp: max 16 MB
- Telegram: max 2 GB

Útil para reportes PDF grandes.

---

## 💰 Comparación de Costos

### Escenario: 10,000 mensajes/mes

| Proveedor | Setup | Mensajes | Costo/mes |
|-----------|-------|----------|-----------|
| **Telegram** | 5 min | ∞ | **$0** 🎁 |
| **WhatsApp Meta** | 2-5 días | ∞ | $18 |
| **WhatsApp Twilio** | 15 min | ∞ | $50 |

### Escenario: 100,000 mensajes/mes

| Proveedor | Costo/mes |
|-----------|-----------|
| **Telegram** | **$0** 🎁 |
| **WhatsApp Meta** | $198 |
| **WhatsApp Twilio** | $500 |

**Para uso interno del ministerio: Telegram es perfecto (gratis e ilimitado)**

---

## 🔧 Configuración Avanzada

### Configurar bot como privado (solo invitados)

```
/setjoingroups
```
Selecciona: "Disable"

Esto evita que el bot sea agregado a grupos sin permiso.

### Habilitar modo inline

```
/setinline
```

Envía descripción:
```
Consulta datos del SIN directamente desde cualquier chat
```

### Configurar mensajes de privacidad

```
/setprivacy
```

Selecciona: "Disable" para que el bot funcione en grupos

---

## 🆘 Solución de Problemas

### Problema 1: Bot no responde

**Verificar webhook:**
```bash
TOKEN="tu_token"
curl "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"
```

Si `last_error_message` tiene errores:
```bash
# Borrar webhook
curl -X POST "https://api.telegram.org/bot${TOKEN}/deleteWebhook"

# Volver a configurar
curl -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://portalenergetico.minenergia.gov.co/whatsapp/webhook/telegram"}'
```

### Problema 2: Error 401 Unauthorized

El token es incorrecto. Verifica:
```bash
grep TELEGRAM_BOT_TOKEN /home/admonctrlxm/server/whatsapp_bot/.env
```

### Problema 3: Webhook no verifica

1. Verifica que tu servidor sea accesible por HTTPS
2. Telegram requiere SSL válido
3. Verifica que el puerto 8001 esté abierto en nginx

---

## 📚 Recursos

### Documentación Oficial
- **Telegram Bot API:** https://core.telegram.org/bots/api
- **BotFather:** https://t.me/BotFather
- **python-telegram-bot:** https://python-telegram-bot.org/

### Ejemplos de uso

**Enviar mensaje:**
```bash
TOKEN="tu_token"
CHAT_ID="123456789"
TEXT="Hola desde el bot!"

curl -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"${CHAT_ID}\", \"text\": \"${TEXT}\"}"
```

---

## ✅ Checklist Final

Antes de considerar el bot listo:

### Configuración
- ✅ Bot creado en BotFather
- ✅ Token obtenido y guardado
- ✅ Descripción configurada
- ✅ Comandos configurados
- ✅ Foto de perfil subida
- ✅ Webhook configurado
- ✅ .env actualizado con token

### Testing
- ✅ Bot responde a `/start`
- ✅ Comando `precio` funciona
- ✅ Comando `generacion` funciona
- ✅ Comando `demanda` funciona
- ✅ Comando `ayuda` muestra menú
- ✅ Bot envía respuestas correctamente
- ✅ Gráficos se generan y envían

### Producción
- ✅ Servicio systemd configurado
- ✅ Auto-start habilitado
- ✅ Logs configurados
- ✅ URL pública compartida

---

## 🎉 ¡Listo!

Tu bot de Telegram está funcionando con:

- ✅ **100% GRATIS** - sin límites ni costos
- ✅ **Setup en minutos** - muy rápido
- ✅ **API oficial** - estable y confiable
- ✅ **Funciones avanzadas** - botones, comandos, inline
- ✅ **Mismo código** - reutiliza todo el backend del bot WhatsApp

**El bot puede estar en WhatsApp Y Telegram simultáneamente!**

---

**Fecha de creación:** Febrero 9, 2026  
**Versión:** 1.0  
**Proyecto:** Portal Energético - Ministerio de Minas y Energía

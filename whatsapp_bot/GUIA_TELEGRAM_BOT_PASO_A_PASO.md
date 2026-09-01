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

> **⚠️ Actualizado 2026-09-01**: la lista de abajo refleja los comandos REALES que el bot en producción implementa (`whatsapp_bot/telegram_polling.py` líneas 2479-2487 + `whatsapp_bot/subsidios_handler.py` líneas 1322-1331) — la lista anterior de esta guía (`precio`, `generacion`, `demanda`, `mix`, `grafico`, `resumen`) nunca existió como comandos reales, era un ejemplo genérico. Registrar esa lista vieja con BotFather le mostraría a los usuarios un menú que no coincide con lo que el bot realmente hace.

```
/setcommands
```

Selecciona tu bot y envía esta lista (comandos reales, verificados contra el código):
```
start - Iniciar bot y ver menú principal
menu - Ver menú principal
estado - Estado actual del sistema eléctrico
predicciones - Predicciones del sistema (embalses, precio, generación)
anomalias - Anomalías/alertas detectadas
noticias - Últimas noticias del sector
informe - Informe ejecutivo del día
ayuda - Ver todos los comandos disponibles
subsidios - Menú de subsidios
deuda - Deuda total de subsidios
deuda_empresa - Deuda de subsidios por empresa
deuda_fondo - Deuda de subsidios por fondo
trimestre_pagado - Pagos del trimestre
pagado_anio - Pagado en el año
porcentaje_pagado - % pagado
resoluciones - Resoluciones de subsidios
estado_resoluciones - Estado de resoluciones
buscar_empresa - Buscar empresa en subsidios
```

---

## 🌐 Paso 3: Cómo se conecta realmente el bot (long polling, NO webhook)

> **⚠️ CORRECCIÓN CRÍTICA (2026-09-01)**: esta sección antes instruía configurar un **webhook** de Telegram (`setWebhook`). **NO sigas esas instrucciones si el bot ya está en producción** — el bot real (`telegram_polling.py`, servicio `telegram-polling.service`) usa **long polling** (`app.run_polling(...)`), y Telegram **no permite tener un webhook activo y hacer polling al mismo tiempo** (si hay un webhook configurado, `getUpdates`/polling falla con error 409 "Conflict"). Configurar un webhook sobre un bot que ya usa polling **rompería el bot en producción**.

### 3.1 Por qué polling y no webhook

El propio código documenta la razón (`telegram_polling.py`, docstring): *"Modo polling: el bot se conecta A Telegram (bypassa firewall del Ministerio)"* — la red del Ministerio no permite exponer un endpoint público fácilmente, así que el bot se conecta hacia afuera (polling) en vez de esperar que Telegram le llegue (webhook).

### 3.2 Si el bot NO tiene ningún webhook configurado (instalación nueva)

No hace falta hacer nada especial — simplemente inicia el bot con polling (ver Paso 4) y funciona. Telegram usa polling por defecto si nunca se llamó a `setWebhook`.

### 3.3 Si por error se configuró un webhook alguna vez, hay que quitarlo antes de usar polling

```bash
TOKEN="<tu token real, o el valor de TELEGRAM_BOT_TOKEN en whatsapp_bot/.env>"
curl -X POST "https://api.telegram.org/bot${TOKEN}/deleteWebhook"
```

Verificar que quedó sin webhook:
```bash
curl "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"
# Debe mostrar "url": "" (vacío)
```

---

## ⚙️ Paso 4: Configurar y correr el bot real (systemd, ya construido)

### 4.1 El bot ya está instalado y corriendo

En este servidor, el bot NO se arranca manualmente — corre como servicio systemd:

```bash
systemctl status telegram-polling.service
# Debe mostrar: active (running)

# Reiniciar tras un cambio de código:
sudo systemctl restart telegram-polling.service

# Ver logs en vivo:
tail -f /home/admonctrlxm/server/whatsapp_bot/logs/telegram_polling.log
tail -f /home/admonctrlxm/server/whatsapp_bot/logs/telegram_polling_error.log
```

Configuración real del servicio (`/etc/systemd/system/telegram-polling.service`):
- `WorkingDirectory=/home/admonctrlxm/server/whatsapp_bot`
- `EnvironmentFile=/home/admonctrlxm/server/whatsapp_bot/.env` (aquí vive `TELEGRAM_BOT_TOKEN`)
- `ExecStart=.../whatsapp_bot/venv/bin/python .../whatsapp_bot/telegram_polling.py`
- `Restart=always` — si el bot se cae, systemd lo reinicia solo

### 4.2 Instalar/actualizar la librería (solo si se necesita reinstalar el venv)

```bash
cd /home/admonctrlxm/server/whatsapp_bot
source venv/bin/activate
pip install python-telegram-bot==20.7   # versión confirmada en requirements.txt
```

### 4.3 Variables de entorno reales (`whatsapp_bot/.env`)

```bash
TELEGRAM_BOT_TOKEN=<tu token real de BotFather>
```

**Nota importante, corrige una afirmación de esta guía en versiones anteriores**: Telegram (`telegram_polling.py`) y WhatsApp (`app/webhook.py` → `orchestrator/bot.py`) son **dos implementaciones de código completamente separadas**, no "el mismo código" compartido — Telegram llama a la API HTTP del backend principal (`http://localhost:8000/api/v1/chatbot/orchestrator`); WhatsApp usa un `BotOrchestrator`/`AgentIA` local dentro del propio proceso de `whatsapp_bot`. No asumas que un cambio en un canal se refleja automáticamente en el otro.

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
/estado
```

Deberías recibir el estado actual del sistema eléctrico.

Envía:
```
/predicciones
```

Deberías recibir las predicciones del sistema (embalses, precio, generación).

---

## 🚀 Paso 6: Producción

### 6.1 El bot ya funciona!

Una vez que `telegram-polling.service` esté corriendo (`systemctl status telegram-polling.service` → `active`), ya está en producción — no requiere ningún webhook ni configuración adicional en Telegram.

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

## 🆚 Telegram vs WhatsApp: estado real (2026-09-01)

> **Corrección**: la versión anterior de esta sección presentaba ambos canales como "el mismo bot unificado" corriendo en paralelo. Verificado contra logs y `systemctl` el 2026-09-01: **no es así**. Son dos servicios y dos implementaciones de código independientes.

| | Telegram (`telegram-polling.service`) | WhatsApp (`whatsapp-bot.service`, Twilio) |
|---|---|---|
| Estado del servicio | `active (running)` | `active (running)` |
| Tráfico real | ✅ Es el canal con tráfico real de producción | ⚠️ Activo pero sin tráfico real registrado en logs desde hace días |
| Mecanismo | Long polling (`telegram_polling.py`) | Webhook Twilio (`app/webhook.py`) |
| Backend usado | Llama por HTTP al orquestador del backend principal (`localhost:8000/api/v1/chatbot/orchestrator`) | Usa un `BotOrchestrator`/`AgentIA` local, en el propio proceso |
| Código compartido con el otro canal | ❌ No — implementación separada | ❌ No — implementación separada |

Además existe un tercer componente, `whatsapp_bot/whatsapp-web-service/` (integración vía `whatsapp-web.js`), que **nunca llegó a desplegarse** (sin `node_modules`, sin Chrome/Chromium instalado, ningún proceso corriendo) — no es una alternativa activa hoy.

**Conclusión práctica**: si vas a tocar o depurar el bot, **Telegram es el canal real de producción**. Cambios en el código de WhatsApp no afectan a Telegram y viceversa — no asumas que arreglar algo en un lado lo arregla en el otro.

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

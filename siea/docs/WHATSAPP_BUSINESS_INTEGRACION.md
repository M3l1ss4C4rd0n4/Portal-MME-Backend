# Guía de Integración WhatsApp Business Cloud para SIEA

## ⚠️ REQUISITO OBLIGATORIO

**El sistema SIEA DEBE usar un número oficial del Ministerio de Minas y Energía.**  
❌ **NO se permite usar números personales o de prueba en producción.**

---

## 📋 Prerrequisitos

### Documentación Requerida
- [ ] Certificado de existencia y representación legal del MinMinas
- [ ] Cédula del representante legal
- [ ] Solicitud oficial de número telefónico (desde Comunicaciones)
- [ ] Aprobación presupuestal para línea móvil

### Accesos Técnicos
- [ ] Cuenta Meta Business Manager (admin del MinMinas)
- [ ] Cuenta Facebook Business (verificada)
- [ ] Servidor con IP pública (para webhook)
- [ ] Certificado SSL válido (Let's Encrypt OK)

---

## 🚀 FASE 1: Meta Business Manager (Semana 1)

### Paso 1.1: Crear/Acceder a Business Manager

**URL:** https://business.facebook.com/

1. Ingresa con cuenta corporativa @minminas.gov.co
2. Si no existe Business Manager:
   - Click **"Crear cuenta"**
   - Nombre: **"Ministerio de Minas y Energía"**
   - País: **Colombia**
   - Categoría: **Gobierno**
3. Agregar colaboradores:
   - Settings → Business Settings → Users → Add
   - Roles: Admin (líder técnico), Employee (devs)

### Paso 1.2: Verificación Empresarial

**Duración:** 3-5 días hábiles

Meta requiere verificar que realmente eres una entidad gubernamental:

1. Settings → Business Settings → Security Center → **"Start Verification"**
2. Cargar documentos:
   - Certificado de existencia (PDF)
   - Cédula representante legal (PDF)
   - Factura de servicio público con dirección (opcional)
3. Esperar email de Meta
4. Si rechazan, responder con documentos adicionales

**⚠️ CRÍTICO:** Sin verificación NO puedes usar API de WhatsApp.

---

## 📱 FASE 2: WhatsApp Business App (Semana 2)

### Paso 2.1: Crear App en Meta for Developers

**URL:** https://developers.facebook.com/

1. Click **"My Apps"** → **"Create App"**
2. Tipo: **Business**
3. Nombre: **"SIEA - Sistema Integral Energético"**
4. Business Account: Seleccionar Business Manager del MinMinas
5. Click **"Create App"**

### Paso 2.2: Agregar Producto WhatsApp

1. En el dashboard de tu app, busca **"WhatsApp"**
2. Click **"Set up"**
3. Meta te asignará un **Test Business Phone Number** (sandbox)
4. Guarda:
   - **Phone Number ID**: (wamid.XXX...)
   - **WhatsApp Business Account ID**: (números)

### Paso 2.3: Obtener Tokens de Acceso

**Token Temporal (para pruebas):**
1. WhatsApp → API Setup → **"Temporary access token"**
2. Copiar (válido 24h)

**Token Permanente (producción):**
1. Settings → Basic → **"App Secret"** (guardar)
2. WhatsApp → Configuration → **"System User Token"**
3. Crear System User:
   - Nombre: `siea-whatsapp-bot`
   - Role: **Admin**
   - Asignar activos: WhatsApp Business Account
4. Generar token con permisos:
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`
   - Válido: **Never expires**
5. Guardar en KMS/Key Vault:
   ```bash
   export WHATSAPP_TOKEN="EAAxxxxx..."
   export WHATSAPP_PHONE_ID="1234567890"
   ```

---

## 🔒 FASE 3: Webhook Seguro (Semana 3)

### Paso 3.1: Implementar Webhook en FastAPI

**Archivo:** `siea/agent/whatsapp/webhook.py`

```python
from fastapi import APIRouter, Request, HTTPException, Header
import hmac
import hashlib

router = APIRouter()

# Configuración
VERIFY_TOKEN = "siea_webhook_secret_2025"  # Generar con: secrets.token_urlsafe(32)
APP_SECRET = "tu_app_secret_de_meta"

@router.get("/whatsapp/webhook")
async def verify_webhook(
    hub_mode: str,
    hub_verify_token: str,
    hub_challenge: str
):
    """Verificación inicial del webhook por Meta"""
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return {"challenge": hub_challenge}
    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("/whatsapp/webhook")
async def receive_message(
    request: Request,
    x_hub_signature_256: str = Header(None)
):
    """Recibir mensajes de WhatsApp con validación HMAC"""
    
    # 1. Leer body raw
    body_bytes = await request.body()
    
    # 2. Validar firma HMAC-SHA256
    expected_signature = hmac.new(
        APP_SECRET.encode(),
        body_bytes,
        hashlib.sha256
    ).hexdigest()
    
    received_signature = x_hub_signature_256.replace("sha256=", "")
    
    if not hmac.compare_digest(expected_signature, received_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # 3. Parsear mensaje
    data = await request.json()
    
    # 4. Extraer texto del usuario
    if data.get("object") == "whatsapp_business_account":
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        
        if "messages" in value:
            message = value["messages"][0]
            from_number = message["from"]
            text = message.get("text", {}).get("body", "")
            
            # 5. Procesar con agente LLM
            response = await process_with_agent(text, from_number)
            
            # 6. Enviar respuesta
            await send_whatsapp_message(from_number, response)
    
    return {"status": "ok"}
```

### Paso 3.2: Configurar Webhook en Meta

1. WhatsApp → Configuration → **"Webhook"**
2. Callback URL: `https://siea.minminas.gov.co/api/whatsapp/webhook`
3. Verify Token: Pegar el valor de `VERIFY_TOKEN`
4. Click **"Verify and Save"**
5. Meta enviará request GET para verificar
6. Si es exitoso, aparecerá ✅

### Paso 3.3: Suscribirse a Eventos

1. Webhook Fields → Seleccionar:
   - ✅ `messages` (mensajes entrantes)
   - ✅ `message_echoes` (confirmaciones de envío)
   - ✅ `message_status` (delivered, read, failed)
2. Click **"Subscribe"**

---

## 📝 FASE 4: Plantillas de Mensajes (Semana 4)

### ⚠️ Restricción de Meta

**Solo puedes iniciar conversación con plantillas pre-aprobadas.**  
(Responder a mensajes del usuario NO requiere plantilla)

### Paso 4.1: Diseñar Plantillas (con Comunicaciones)

**Plantilla 1: Resumen Diario**
- **Nombre:** `daily_summary`
- **Categoría:** UTILITY
- **Idioma:** Español
- **Texto:**
  ```
  ⚡ Resumen Energético {{1}} 
  
  📊 Demanda nacional: {{2}} GWh
  💡 Generación hidráulica: {{3}}%
  💰 Precio bolsa: {{4}} $/kWh
  
  Consulta más en: https://siea.minminas.gov.co
  ```
- **Botón (opcional):** `Ver Dashboard` → URL

**Plantilla 2: Alerta Crítica**
- **Nombre:** `critical_alert`
- **Categoría:** UTILITY
- **Idioma:** Español
- **Texto:**
  ```
  🚨 ALERTA: {{1}}
  
  Descripción: {{2}}
  Fecha/hora: {{3}}
  Acciones requeridas: {{4}}
  ```

**Plantilla 3: Respuesta a Consulta**
- **Nombre:** `query_response`
- **Categoría:** UTILITY
- **Idioma:** Español
- **Texto:**
  ```
  Hola {{1}}, aquí está la información solicitada:
  
  {{2}}
  
  ¿Algo más en lo que pueda ayudarte?
  ```

### Paso 4.2: Enviar para Aprobación

1. WhatsApp → Message Templates → **"Create Template"**
2. Llenar formulario con textos de arriba
3. Usar `{{1}}`, `{{2}}` para variables
4. Click **"Submit"**
5. Esperar 24-48h para aprobación
6. Revisar en **"Message Templates"** si aparece status **"Approved"** ✅

**⚠️ Si rechazan:** Editar y re-enviar (evitar lenguaje promocional, ser claro y útil)

---

## 💾 FASE 5: Envío de Mensajes (Código)

### Enviar Mensaje con Plantilla

**Archivo:** `siea/agent/whatsapp/sender.py`

```python
import httpx
import os

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
API_URL = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"

async def send_template_message(to: str, template_name: str, params: list):
    """Enviar mensaje usando plantilla aprobada"""
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,  # Número con código país: "573001234567"
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "es"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": p} for p in params
                    ]
                }
            ]
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

# Ejemplo de uso
await send_template_message(
    to="573001234567",
    template_name="daily_summary",
    params=["2025-12-02", "215.3", "68", "234"]
)
```

### Responder a Mensaje del Usuario

```python
async def send_reply_message(to: str, text: str):
    """Responder a mensaje (sin plantilla)"""
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
```

---

## 🔢 FASE 6: Número Oficial (Semana 5-6)

### Paso 6.1: Adquirir Número Corporativo

**Opción A: Línea Móvil Corporativa** (recomendado)
1. Comunicaciones solicita línea a Claro/Movistar/Tigo
2. Contrato corporativo (facturación a MinMinas)
3. Tipo: Pospago con SMS/Datos
4. Solicitar que NO tenga bloqueo de verificación por SMS

**Opción B: Número Fijo (menos común)**
1. Si MinMinas tiene centralita con números fijos
2. Asignar extensión dedicada para WhatsApp

### Paso 6.2: Vincular Número a WhatsApp Business

1. WhatsApp → Phone Numbers → **"Add phone number"**
2. Seleccionar: **"Use your own phone number"**
3. Ingresar número (con código país: +57XXXXXXXXXX)
4. Meta enviará código por SMS o llamada
5. Ingresar código de verificación
6. Confirmar: "This number belongs to MinMinas"

**⚠️ IMPORTANTE:**  
- El número quedará desvinculado de cualquier WhatsApp personal
- Solo se podrá usar con API (no con app móvil)

### Paso 6.3: Configurar Perfil Público

1. WhatsApp → Phone Numbers → Click en tu número
2. **Display Name:** "MinMinas - SIEA"
3. **About:** "Asistente inteligente del Ministerio de Minas y Energía"
4. **Photo:** Logo oficial MinMinas (512x512 px)
5. **Business Category:** Government Organization
6. **Website:** https://siea.minminas.gov.co
7. **Address:** Calle 43 #57-31, Bogotá

---

## 🧪 Pruebas y Validación

### Checklist de Pruebas

**Pruebas en Sandbox (Número de Prueba):**
- [ ] Webhook recibe mensajes correctamente
- [ ] Firma HMAC valida correctamente
- [ ] Agente responde en < 3 segundos
- [ ] Plantillas se envían sin errores
- [ ] Logs de auditoría registran todo

**Pruebas en Producción (Número Oficial):**
- [ ] Enviar resumen diario a 3 funcionarios
- [ ] Consultar "¿Cuál es la demanda actual?"
- [ ] Enviar alerta crítica simulada
- [ ] Verificar que respuestas citen 3 fuentes
- [ ] Confirmar que logs tienen trazabilidad completa

### Script de Prueba

```bash
# Test webhook (debe retornar el challenge)
curl -X GET "https://siea.minminas.gov.co/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=siea_webhook_secret_2025&hub.challenge=test123"

# Enviar mensaje de prueba (desde otro número)
# 1. Guarda el número oficial en tus contactos
# 2. Envía: "Hola SIEA, ¿cuál es la demanda actual?"
# 3. Debes recibir respuesta en < 5 segundos
```

---

## 📊 Límites y Cuotas

### Mensajes por Día

| Tier | Límite | Cómo Aumentar |
|------|--------|---------------|
| Tier 1 | 1,000/día | Automático tras 7 días |
| Tier 2 | 10,000/día | Automático tras 7 días |
| Tier 3 | 100,000/día | Solicitar a Meta |

### Costo Aproximado

- **Mensajes iniciados por negocio (plantillas):** ~$0.005 USD/mensaje
- **Respuestas a usuarios (24h ventana):** Gratis
- **Presupuesto estimado:** $150 USD/mes (30K mensajes)

---

## 🚨 Solución de Problemas

### Error: "Webhook verification failed"
- ✅ Verificar que `VERIFY_TOKEN` coincida en código y Meta
- ✅ Confirmar que servidor tiene SSL válido
- ✅ Revisar logs de FastAPI para ver el request

### Error: "Invalid signature"
- ✅ Verificar que `APP_SECRET` sea correcto
- ✅ Confirmar que usas `request.body()` (no `await request.json()`)
- ✅ Revisar logs: comparar firma recibida vs calculada

### Error: "Template not approved"
- ✅ Eliminar lenguaje promocional ("¡Compra ya!", "Oferta!")
- ✅ Ser claro y objetivo (gobierno no vende)
- ✅ Re-enviar con ajustes

### Mensajes no llegan
- ✅ Verificar que número receptor esté en whitelist (sandbox)
- ✅ Confirmar que número tenga formato correcto (+57...)
- ✅ Revisar logs de Meta (WhatsApp → Insights → Errors)

---

## 📚 Referencias

- [WhatsApp Business API Docs](https://developers.facebook.com/docs/whatsapp)
- [Message Templates Guide](https://developers.facebook.com/docs/whatsapp/message-templates)
- [Webhook Setup](https://developers.facebook.com/docs/graph-api/webhooks)
- [Meta Business Verification](https://www.facebook.com/business/help/2058515294227817)

---

**Última actualización:** 2025-12-02  
**Responsable:** [Líder Técnico SIEA]  
**Contacto soporte Meta:** business.facebook.com/help

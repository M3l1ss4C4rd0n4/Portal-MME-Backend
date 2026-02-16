# 🤖 Integración ChatBot WhatsApp con API Portal Energético

**Para:** Tu compañero desarrollador del bot de WhatsApp  
**Fecha:** 6 de febrero de 2026  
**API Base:** `http://portalenergetico.minenergia.gov.co/api`

---

## 📋 **RESUMEN EJECUTIVO**

Tu chatbot de WhatsApp puede:
1. ✅ **Consumir datos en tiempo real** de la API
2. ✅ **Generar gráficas** con librerías Python
3. ✅ **Compartir links** del dashboard público
4. ✅ **Usar análisis IA** del mismo modelo que el chatbot web

---

## 🔌 **1. CONSUMIR LA API DESDE WHATSAPP BOT**

### **Opción A: Python (Recomendado)**

```python
import requests
from datetime import datetime, timedelta

# Configuración
API_BASE = "http://portalenergetico.minenergia.gov.co/api"

def obtener_generacion_sistema(dias=7):
    """Obtiene generación del sistema últimos N días"""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    
    url = f"{API_BASE}/v1/generation/system"
    params = {
        "start_date": start_date,
        "end_date": end_date
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        return data['data']  # Lista de puntos con fecha, valor
    else:
        return None

def obtener_precios_bolsa(fecha=None):
    """Obtiene precios de bolsa"""
    if not fecha:
        fecha = datetime.now().strftime("%Y-%m-%d")
    
    url = f"{API_BASE}/v1/system/prices"
    params = {"start_date": fecha, "end_date": fecha}
    
    response = requests.get(url, params=params)
    return response.json()

def obtener_mix_energetico(fecha=None):
    """Obtiene mix de generación por fuente"""
    url = f"{API_BASE}/v1/generation/mix"
    params = {}
    if fecha:
        params["date"] = fecha
    
    response = requests.get(url, params=params)
    return response.json()

# Ejemplo de uso en chatbot WhatsApp
def responder_usuario(mensaje_usuario):
    """Procesa mensaje y responde con datos de API"""
    
    if "generación" in mensaje_usuario.lower():
        datos = obtener_generacion_sistema(dias=7)
        if datos:
            ultimo = datos[-1]
            respuesta = f"📊 Generación actual: {ultimo['value']:.2f} GWh\n"
            respuesta += f"Fecha: {ultimo['date']}"
            return respuesta
    
    elif "precio" in mensaje_usuario.lower():
        datos = obtener_precios_bolsa()
        # Procesar y responder
        return "💰 Precio de bolsa: ..."
    
    elif "mix" in mensaje_usuario.lower():
        datos = obtener_mix_energetico()
        # Mostrar porcentajes por fuente
        return "⚡ Mix energético: ..."
    
    return "¿En qué puedo ayudarte?"
```

### **Opción B: Node.js**

```javascript
const axios = require('axios');

const API_BASE = 'http://portalenergetico.minenergia.gov.co/api';

async function obtenerGeneracion(dias = 7) {
    const endDate = new Date().toISOString().split('T')[0];
    const startDate = new Date(Date.now() - dias * 86400000)
        .toISOString().split('T')[0];
    
    const response = await axios.get(`${API_BASE}/v1/generation/system`, {
        params: { start_date: startDate, end_date: endDate }
    });
    
    return response.data.data;
}

async function obtenerPreciosBolsa() {
    const response = await axios.get(`${API_BASE}/v1/system/prices`);
    return response.data;
}

// Integación con WhatsApp (ej: Baileys)
client.on('message', async (msg) => {
    if (msg.body.includes('generación')) {
        const datos = await obtenerGeneracion();
        const ultimo = datos[datos.length - 1];
        await msg.reply(`📊 Generación: ${ultimo.value} GWh`);
    }
});
```

---

## 📊 **2. GENERAR Y ENVIAR GRÁFICAS POR WHATSAPP**

### **Método 1: matplotlib + PIL (Python)**

```python
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from io import BytesIO
import requests

def generar_grafica_generacion(dias=30):
    """Genera gráfica de generación y devuelve buffer de imagen"""
    
    # 1. Obtener datos de la API
    url = "http://portalenergetico.minenergia.gov.co/api/v1/generation/system"
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    
    response = requests.get(url, params={
        "start_date": start_date,
        "end_date": end_date
    })
    datos = response.json()['data']
    
    # 2. Procesar datos
    fechas = [datetime.strptime(d['date'], '%Y-%m-%d') for d in datos]
    valores = [d['value'] for d in datos]
    
    # 3. Crear gráfica
    plt.figure(figsize=(12, 6))
    plt.plot(fechas, valores, linewidth=2, color='#1f77b4', marker='o')
    plt.title('Generación Eléctrica Nacional', fontsize=16, fontweight='bold')
    plt.xlabel('Fecha')
    plt.ylabel('Generación (GWh)')
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # 4. Guardar en buffer (no en disco)
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer

def generar_grafica_mix_energetico():
    """Genera gráfica circular del mix energético"""
    
    # Obtener datos
    url = "http://portalenergetico.minenergia.gov.co/api/v1/generation/mix"
    response = requests.get(url)
    datos = response.json()['data']
    
    # Extraer fuentes y porcentajes
    fuentes = [d['tipo'] for d in datos]
    porcentajes = [d['porcentaje'] for d in datos]
    
    # Colores por fuente
    colores = {
        'HIDRAULICA': '#2196F3',
        'TERMICA': '#FF5722',
        'EOLICA': '#4CAF50',
        'SOLAR': '#FFC107',
        'COGENERADOR': '#9C27B0'
    }
    
    colors = [colores.get(f, '#999999') for f in fuentes]
    
    # Crear gráfica
    plt.figure(figsize=(10, 8))
    plt.pie(porcentajes, labels=fuentes, colors=colors, autopct='%1.1f%%',
            startangle=90, textprops={'fontsize': 12})
    plt.title('Mix Energético Actual', fontsize=16, fontweight='bold')
    plt.axis('equal')
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer

# Integración con WhatsApp Bot (ej: whatsapp-web.js)
from twilio.rest import Client  # O librería que uses

def enviar_grafica_whatsapp(numero_destino, tipo_grafica='generacion'):
    """Envía gráfica por WhatsApp"""
    
    # Generar gráfica
    if tipo_grafica == 'generacion':
        buffer = generar_grafica_generacion()
    elif tipo_grafica == 'mix':
        buffer = generar_grafica_mix_energetico()
    
    # Enviar con tu librería WhatsApp
    # Ejemplo con Twilio:
    client = Client(account_sid, auth_token)
    
    message = client.messages.create(
        from_='whatsapp:+14155238886',
        to=f'whatsapp:{numero_destino}',
        body='📊 Aquí está la gráfica solicitada:',
        media_url=['data:image/png;base64,' + base64.b64encode(buffer.read()).decode()]
    )
    
    return message.sid
```

### **Ejemplo Completo con Bot**

```python
from twilio.rest import Client
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import requests
from io import BytesIO
import base64

# Configuración
API_BASE = "http://portalenergetico.minenergia.gov.co/api"
TWILIO_SID = "tu_sid"
TWILIO_TOKEN = "tu_token"

client = Client(TWILIO_SID, TWILIO_TOKEN)

def bot_responder(mensaje, numero_usuario):
    """Lógica principal del bot"""
    
    mensaje_lower = mensaje.lower()
    
    # Comando: Gráfica de generación
    if "gráfica" in mensaje_lower or "grafica" in mensaje_lower:
        if "generación" in mensaje_lower or "generacion" in mensaje_lower:
            buffer = generar_grafica_generacion(dias=30)
            
            # Enviar imagen
            client.messages.create(
                from_='whatsapp:+14155238886',
                to=f'whatsapp:{numero_usuario}',
                body='📊 Generación Eléctrica Nacional (últimos 30 días)',
                media_url=[upload_to_cloud(buffer)]  # Sube a S3/Cloudinary
            )
            return "¡Gráfica enviada!"
    
    # Comando: Datos en texto
    elif "generación" in mensaje_lower:
        datos = obtener_generacion_sistema(dias=1)
        if datos:
            ultimo = datos[-1]
            return f"📊 Generación Nacional\n\n" \
                   f"Valor: {ultimo['value']:.2f} GWh\n" \
                   f"Fecha: {ultimo['date']}\n\n" \
                   f"Escribe 'gráfica generación' para ver el histórico"
    
    # Comando: Mix energético
    elif "mix" in mensaje_lower:
        datos = obtener_mix_energetico()
        respuesta = "⚡ Mix Energético Actual:\n\n"
        for item in datos['data']:
            respuesta += f"{item['tipo']}: {item['porcentaje']:.1f}%\n"
        respuesta += "\nEscribe 'gráfica mix' para ver el gráfico"
        return respuesta
    
    # Comando: Link dashboard
    elif "dashboard" in mensaje_lower or "tablero" in mensaje_lower:
        return "🌐 Dashboard Completo:\n" \
               "http://portalenergetico.minenergia.gov.co\n\n" \
               "📚 Documentación API:\n" \
               "http://portalenergetico.minenergia.gov.co/api/docs"
    
    # Ayuda
    else:
        return "🤖 Portal Energético MME Bot\n\n" \
               "Comandos disponibles:\n" \
               "• 'generación' - Datos actuales\n" \
               "• 'gráfica generación' - Ver gráfico\n" \
               "• 'mix' - Mix energético\n" \
               "• 'gráfica mix' - Gráfico circular\n" \
               "• 'precios' - Precios de bolsa\n" \
               "• 'dashboard' - Link al dashboard\n" \
               "• 'ayuda' - Este menú"

# Webhook para recibir mensajes
from flask import Flask, request

app = Flask(__name__)

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    mensaje = request.form.get('Body', '')
    numero = request.form.get('From', '').replace('whatsapp:', '')
    
    respuesta = bot_responder(mensaje, numero)
    
    # Responder
    client.messages.create(
        from_='whatsapp:+14155238886',
        to=f'whatsapp:{numero}',
        body=respuesta
    )
    
    return 'OK', 200

if __name__ == '__main__':
    app.run(port=5000)
```

---

## 🔗 **3. COMPARTIR LINKS DEL DASHBOARD**

### **Links Útiles para el Bot**

```python
LINKS_DASHBOARD = {
    "principal": "http://portalenergetico.minenergia.gov.co",
    "generacion": "http://portalenergetico.minenergia.gov.co#generacion",
    "hidrologia": "http://portalenergetico.minenergia.gov.co#hidrologia",
    "precios": "http://portalenergetico.minenergia.gov.co#precios",
    "predicciones": "http://portalenergetico.minenergia.gov.co#predicciones",
    "api_docs": "http://portalenergetico.minenergia.gov.co/api/docs"
}

def compartir_dashboard(seccion="principal"):
    """Devuelve link del dashboard según sección"""
    link = LINKS_DASHBOARD.get(seccion, LINKS_DASHBOARD["principal"])
    
    mensaje = f"🌐 Dashboard Portal Energético MME\n\n"
    mensaje += f"Accede aquí:\n{link}\n\n"
    mensaje += "Secciones disponibles:\n"
    mensaje += "• Generación eléctrica\n"
    mensaje += "• Hidrología y embalses\n"
    mensaje += "• Precios de bolsa\n"
    mensaje += "• Predicciones ML\n"
    mensaje += "• Chat IA integrado"
    
    return mensaje
```

---

## 🤖 **4. ACCESO AL CHAT IA (MISMO DEL DASHBOARD)**

### **Endpoint Chat IA** (Si está disponible)

```python
import requests

def consultar_chat_ia(pregunta_usuario, contexto_datos=None):
    """
    Consulta al chat IA del dashboard
    
    Args:
        pregunta_usuario: Pregunta del usuario
        contexto_datos: Datos opcionales para contextualizar
    """
    
    url = "http://portalenergetico.minenergia.gov.co/api/v1/chat/query"
    
    payload = {
        "question": pregunta_usuario,
        "context": contexto_datos,
        "history": []  # Historial de conversación
    }
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        return data['response']
    else:
        return "Error al consultar IA"

# Ejemplo de uso
pregunta = "¿Cuál es la tendencia de generación hidráulica?"
respuesta_ia = consultar_chat_ia(pregunta)
```

### **Si el endpoint IA no existe, usar OpenAI/Groq directamente**

```python
import openai

openai.api_key = "tu-api-key"

def analisis_ia_con_datos(pregunta, datos_api):
    """
    Usa IA con datos de la API como contexto
    """
    
    # Formatear datos como contexto
    contexto = f"Datos actuales:\n{json.dumps(datos_api, indent=2)}"
    
    messages = [
        {
            "role": "system",
            "content": "Eres un asistente experto en energía eléctrica de Colombia. "
                       "Analiza datos del sector eléctrico y responde preguntas."
        },
        {
            "role": "user",
            "content": f"{contexto}\n\nPregunta: {pregunta}"
        }
    ]
    
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=messages,
        temperature=0.7
    )
    
    return response.choices[0].message.content

# Ejemplo
datos = obtener_generacion_sistema(dias=30)
pregunta = "¿Hay alguna tendencia preocupante en los datos?"
analisis = analisis_ia_con_datos(pregunta, datos)
```

---

## 📱 **5. EJEMPLO COMPLETO BOT WHATSAPP**

```python
#!/usr/bin/env python3
"""
ChatBot WhatsApp - Portal Energético MME
Integración completa con API REST
"""

import os
import requests
import matplotlib.pyplot as plt
from twilio.rest import Client
from flask import Flask, request
from datetime import datetime, timedelta
from io import BytesIO
import base64

# ═══════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════

API_BASE = "http://portalenergetico.minenergia.gov.co/api"
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP_NUMBER")

client = Client(TWILIO_SID, TWILIO_TOKEN)
app = Flask(__name__)

# ═══════════════════════════════════════════════════════════
# FUNCIONES DE API
# ═══════════════════════════════════════════════════════════

def api_get(endpoint, params=None):
    """Helper para llamadas GET a la API"""
    try:
        response = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error API: {e}")
        return None

def obtener_generacion(dias=7):
    """Obtiene generación del sistema"""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    
    data = api_get("/v1/generation/system", {
        "start_date": start_date,
        "end_date": end_date
    })
    
    return data['data'] if data else None

def obtener_mix():
    """Obtiene mix energético"""
    data = api_get("/v1/generation/mix")
    return data['data'] if data else None

def obtener_precios():
    """Obtiene precios de bolsa"""
    data = api_get("/v1/system/prices")
    return data['data'] if data else None

# ═══════════════════════════════════════════════════════════
# GENERACIÓN DE GRÁFICAS
# ═══════════════════════════════════════════════════════════

def crear_grafica_generacion():
    """Crea gráfica de generación"""
    datos = obtener_generacion(dias=30)
    if not datos:
        return None
    
    fechas = [datetime.strptime(d['date'], '%Y-%m-%d') for d in datos]
    valores = [d['value'] for d in datos]
    
    plt.figure(figsize=(12, 6))
    plt.plot(fechas, valores, linewidth=2, marker='o')
    plt.title('Generación Eléctrica Nacional - Últimos 30 Días', fontsize=14)
    plt.xlabel('Fecha')
    plt.ylabel('Generación (GWh)')
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=120)
    buffer.seek(0)
    plt.close()
    
    return buffer

# ═══════════════════════════════════════════════════════════
# LÓGICA DEL BOT
# ═══════════════════════════════════════════════════════════

def procesar_mensaje(mensaje, numero_usuario):
    """Procesa mensaje y genera respuesta"""
    
    mensaje = mensaje.lower().strip()
    
    # Comando: Generación
    if any(word in mensaje for word in ['generacion', 'generación']):
        if 'grafica' in mensaje or 'gráfica' in mensaje:
            # Enviar gráfica
            buffer = crear_grafica_generacion()
            if buffer:
                # Subir a servicio temporal o enviar directamente
                return {"tipo": "imagen", "datos": buffer}
        else:
            # Enviar texto
            datos = obtener_generacion(dias=1)
            if datos:
                ultimo = datos[-1]
                return {
                    "tipo": "texto",
                    "mensaje": f"📊 Generación Nacional\n\n"
                               f"💡 {ultimo['value']:.2f} GWh\n"
                               f"📅 {ultimo['date']}\n\n"
                               f"Escribe 'gráfica generación' para ver histórico"
                }
    
    # Comando: Mix
    elif 'mix' in mensaje:
        datos = obtener_mix()
        if datos:
            respuesta = "⚡ Mix Energético Actual:\n\n"
            for fuente in datos:
                emoji = {
                    'HIDRAULICA': '💧',
                    'TERMICA': '🔥',
                    'EOLICA': '💨',
                    'SOLAR': '☀️'
                }.get(fuente['tipo'], '⚡')
                respuesta += f"{emoji} {fuente['tipo']}: {fuente['porcentaje']:.1f}%\n"
            
            return {"tipo": "texto", "mensaje": respuesta}
    
    # Comando: Dashboard
    elif 'dashboard' in mensaje or 'tablero' in mensaje:
        return {
            "tipo": "texto",
            "mensaje": "🌐 Dashboard Completo:\n"
                       "http://portalenergetico.minenergia.gov.co\n\n"
                       "📚 API Docs:\n"
                       "http://portalenergetico.minenergia.gov.co/api/docs"
        }
    
    # Ayuda
    else:
        return {
            "tipo": "texto",
            "mensaje": "🤖 Portal Energético Bot\n\n"
                       "Comandos:\n"
                       "• generación\n"
                       "• gráfica generación\n"
                       "• mix energético\n"
                       "• precios\n"
                       "• dashboard\n"
                       "• ayuda"
        }

# ═══════════════════════════════════════════════════════════
# WEBHOOK WHATSAPP
# ═══════════════════════════════════════════════════════════

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Recibe mensajes de WhatsApp"""
    
    mensaje_entrante = request.form.get('Body', '')
    numero_usuario = request.form.get('From', '')
    
    # Procesar
    respuesta = procesar_mensaje(mensaje_entrante, numero_usuario)
    
    # Enviar respuesta
    if respuesta['tipo'] == 'texto':
        client.messages.create(
            from_=f'whatsapp:{TWILIO_WHATSAPP}',
            to=numero_usuario,
            body=respuesta['mensaje']
        )
    elif respuesta['tipo'] == 'imagen':
        # Implementar envío de imagen
        pass
    
    return 'OK', 200

if __name__ == '__main__':
    print("🤖 Bot WhatsApp iniciado")
    print(f"📡 API: {API_BASE}")
    app.run(host='0.0.0.0', port=5000)
```

---

## 📚 **6. TODOS LOS ENDPOINTS DISPONIBLES**

### **Generación**
```
GET /api/v1/generation/system       - Generación total
GET /api/v1/generation/by-source    - Por fuente
GET /api/v1/generation/mix          - Mix energético
GET /api/v1/generation/resources    - Catálogo recursos
```

### **Hidrología**
```
GET /api/v1/hydrology/aportes       - Aportes hídricos
GET /api/v1/hydrology/reservoirs    - Embalses
GET /api/v1/hydrology/energy        - Energía embalsada
```

### **Sistema**
```
GET /api/v1/system/demand           - Demanda nacional
GET /api/v1/system/prices           - Precios de bolsa
```

### **Transmisión**
```
GET /api/v1/transmission/lines      - Líneas transmisión
GET /api/v1/transmission/flows      - Flujos potencia
GET /api/v1/transmission/international - Intercambios
```

### **Otros**
```
GET /api/v1/commercial/prices       - Precios comerciales
GET /api/v1/losses/data             - Pérdidas energía
GET /api/v1/restrictions/data       - Restricciones
```

---

## 🚀 **7. DESPLIEGUE RÁPIDO**

### **Paso 1: Instalar dependencias**

```bash
pip install twilio flask requests matplotlib pandas
```

### **Paso 2: Variables de entorno**

```bash
export TWILIO_ACCOUNT_SID="tu_sid"
export TWILIO_AUTH_TOKEN="tu_token"
export TWILIO_WHATSAPP_NUMBER="+14155238886"
```

### **Paso 3: Ejecutar bot**

```bash
python whatsapp_bot.py
```

### **Paso 4: Exponer con ngrok**

```bash
ngrok http 5000
# Copiar URL HTTPS y configurar en Twilio Webhook
```

---

## 📞 **SOPORTE**

**API Documentation:**  
http://portalenergetico.minenergia.gov.co/api/docs

**Dashboard:**  
http://portalenergetico.minenergia.gov.co

**Contacto:**  
Portal Energético MME - Ministerio de Minas y Energía

---

## 🧠 **8. ACCESO A LA IA DEL DASHBOARD**

El Portal Energético tiene un **Asistente IA** integrado que analiza datos en tiempo real. Tu bot de WhatsApp puede usar el mismo servicio de IA.

### **8.1 Configuración del Servicio IA**

El dashboard usa **OpenRouter** o **Groq** con modelos avanzados. Para integrarlo en tu bot:

```python
from openai import OpenAI
import os

# Configuración IA (misma que el dashboard)
GROQ_API_KEY = "tu_groq_api_key"  # O usa OpenRouter
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
IA_MODEL = "llama-3.3-70b-versatile"  # Modelo recomendado

class AnalistaIA:
    """Cliente IA igual al del dashboard"""
    
    def __init__(self):
        self.client = OpenAI(
            base_url=GROQ_BASE_URL,
            api_key=GROQ_API_KEY
        )
        self.modelo = IA_MODEL
    
    def analizar_contexto(self, pregunta_usuario: str, datos_contexto: dict) -> str:
        """
        Analiza pregunta del usuario con contexto de datos energéticos
        
        Args:
            pregunta_usuario: Pregunta en lenguaje natural
            datos_contexto: Datos de la API (generación, precios, etc.)
        
        Returns:
            Respuesta analizada por IA
        """
        
        # Sistema prompt (igual al del dashboard)
        system_prompt = """
        Eres un Analista Energético experto del sector eléctrico colombiano.
        
        **Tu rol:** 
        - Analizar datos del Sistema Interconectado Nacional (SIN)
        - Explicar métricas energéticas en lenguaje claro
        - Identificar tendencias y patrones
        - Responder preguntas técnicas y normativas
        
        **Contexto disponible:**
        - Generación eléctrica por fuente (GWh)
        - Demanda nacional y regional
        - Precios de bolsa ($/kWh)
        - Hidrología (aportes, embalses)
        - Mix energético (% por fuente)
        
        **Respuestas:**
        - Concisas pero completas
        - Con números actualizados
        - En español colombiano
        - Formato WhatsApp (sin markdown complejo)
        """
        
        # Construir contexto con datos
        contexto = f"""
        Datos actualizados:
        {json.dumps(datos_contexto, indent=2, ensure_ascii=False)}
        
        Pregunta del usuario:
        {pregunta_usuario}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.modelo,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": contexto}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"❌ Error IA: {str(e)}"

# Uso en el bot de WhatsApp
analista = AnalistaIA()

def responder_con_ia(mensaje_usuario):
    """Responde pregunta usando IA + datos de API"""
    
    # 1. Obtener datos relevantes de API
    datos = {
        'generacion': obtener_generacion_sistema(dias=1),
        'precios': obtener_precios_bolsa(),
        'mix': obtener_mix_energetico()
    }
    
    # 2. Enviar a IA para análisis
    respuesta_ia = analista.analizar_contexto(mensaje_usuario, datos)
    
    # 3. Enviar por WhatsApp
    return respuesta_ia

# Ejemplo de conversación:
# Usuario: "¿Cómo está la generación hoy?"
# Bot: "🔌 La generación hoy está en 234.5 GWh, dominada por 
#       hidroeléctricas (65%). Las térmicas aportan 28% y 
#       renovables no convencionales 7%. Es un día normal para 
#       esta época del año."
```

### **8.2 API Keys Necesarias**

Para usar el mismo servicio IA del dashboard necesitas:

**Opción A: Groq (Recomendado - GRATIS)**
```bash
# Registrarse en: https://console.groq.com
export GROQ_API_KEY="gsk_..."
```

**Opción B: OpenRouter (Alternativa)**
```bash
# Registrarse en: https://openrouter.ai
export OPENROUTER_API_KEY="sk-or-v1-..."
```

### **8.3 Modelos Disponibles**

El dashboard usa estos modelos (tú puedes usar los mismos):

| Modelo | Proveedor | Características |
|--------|-----------|-----------------|
| `llama-3.3-70b-versatile` | Groq | Rápido, gratis, español excelente ⭐ |
| `mixtral-8x7b-32768` | Groq | Contexto largo, bueno para datos |
| `google/gemini-flash-1.5` | OpenRouter | OpenRouter backup |

### **8.4 Ejemplo Completo: Bot con IA**

```python
# whatsapp_bot_con_ia.py
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import requests
import json

app = Flask(__name__)

# Configuración
API_BASE = "http://portalenergetico.minenergia.gov.co/api"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Cliente IA
ia_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

@app.route("/webhook", methods=['POST'])
def webhook():
    """Webhook de Twilio WhatsApp"""
    incoming_msg = request.values.get('Body', '').lower()
    resp = MessagingResponse()
    msg = resp.message()
    
    # Obtener datos frescos de API
    datos_contexto = {
        'generacion': requests.get(f"{API_BASE}/v1/generation/system").json(),
        'precios': requests.get(f"{API_BASE}/v1/system/prices").json(),
        'mix': requests.get(f"{API_BASE}/v1/generation/mix").json()
    }
    
    # Analizar con IA
    response_ia = ia_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Eres analista energético..."},
            {"role": "user", "content": f"Pregunta: {incoming_msg}\nDatos: {json.dumps(datos_contexto)}"}
        ]
    )
    
    # Responder por WhatsApp
    msg.body(response_ia.choices[0].message.content)
    return str(resp)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

---

## 🔗 **9. COMPARTIR LINKS DE TABLEROS**

Tu bot puede compartir links directos a visualizaciones específicas del dashboard.

### **9.1 URLs de Tableros Disponibles**

```python
# Base del dashboard
DASHBOARD_BASE = "http://portalenergetico.minenergia.gov.co"

# Mapa de tableros
TABLEROS = {
    # Generación
    'generacion': f"{DASHBOARD_BASE}/generacion",
    'generacion-fuentes': f"{DASHBOARD_BASE}/generacion-fuentes",
    'hidraulica': f"{DASHBOARD_BASE}/generacion/hidraulica/hidrologia",
    
    # Sistema
    'demanda': f"{DASHBOARD_BASE}/demanda",
    'precios': f"{DASHBOARD_BASE}/precios",
    'disponibilidad': f"{DASHBOARD_BASE}/disponibilidad",
    
    # Transmisión y distribución
    'transmision': f"{DASHBOARD_BASE}/transmision",
    'distribucion': f"{DASHBOARD_BASE}/distribucion",
    'perdidas': f"{DASHBOARD_BASE}/perdidas",
    
    # Análisis avanzado
    'restricciones': f"{DASHBOARD_BASE}/restricciones",
    'predicciones': f"{DASHBOARD_BASE}/predicciones",
    
    # Principal
    'inicio': f"{DASHBOARD_BASE}/"
}

def obtener_link_tablero(tema: str) -> str:
    """
    Obtiene link de tablero según tema solicitado
    
    Args:
        tema: Tema del tablero (ej: 'generacion', 'precios')
    
    Returns:
        URL completa del tablero o None
    """
    return TABLEROS.get(tema.lower())
```

### **9.2 Integración en Respuestas**

```python
def responder_con_link(mensaje_usuario: str):
    """Responde con datos + link al tablero relevante"""
    
    mensaje = mensaje_usuario.lower()
    respuesta = ""
    link_tablero = None
    
    # Generación
    if "generación" in mensaje or "generacion" in mensaje:
        datos = obtener_generacion_sistema(dias=1)
        if datos:
            ultimo = datos[-1]
            respuesta = f"📊 *Generación Nacional*\n\n"
            respuesta += f"Actual: {ultimo['value']:.2f} GWh\n"
            respuesta += f"Fecha: {ultimo['date']}\n\n"
        link_tablero = TABLEROS['generacion']
    
    # Precios
    elif "precio" in mensaje:
        datos = obtener_precios_bolsa()
        if datos and datos['data']:
            precio = datos['data'][-1]['value']
            respuesta = f"💰 *Precio de Bolsa*\n\n"
            respuesta += f"Actual: ${precio:.2f}/kWh\n\n"
        link_tablero = TABLEROS['precios']
    
    # Mix energético
    elif "mix" in mensaje or "fuentes" in mensaje:
        datos = obtener_mix_energetico()
        if datos:
            respuesta = f"⚡ *Mix Energético*\n\n"
            for fuente in datos['mix']:
                respuesta += f"• {fuente['source']}: {fuente['percentage']:.1f}%\n"
            respuesta += "\n"
        link_tablero = TABLEROS['generacion-fuentes']
    
    # Demanda
    elif "demanda" in mensaje:
        respuesta = "📈 *Demanda Nacional de Energía*\n\n"
        link_tablero = TABLEROS['demanda']
    
    # Hidrología
    elif "hidro" in mensaje or "embalse" in mensaje or "agua" in mensaje:
        respuesta = "💧 *Hidrología y Embalses*\n\n"
        link_tablero = TABLEROS['hidraulica']
    
    # Agregar link al final
    if link_tablero:
        respuesta += f"📊 *Ver tablero interactivo:*\n{link_tablero}"
    
    return respuesta

# Ejemplo de respuesta:
"""
📊 *Generación Nacional*

Actual: 234.56 GWh
Fecha: 2026-02-06

📊 *Ver tablero interactivo:*
http://portalenergetico.minenergia.gov.co/generacion
"""
```

### **9.3 Respuestas Enriquecidas con IA + Links**

```python
def respuesta_completa(mensaje_usuario: str):
    """
    Respuesta completa: Datos API + Análisis IA + Link tablero
    """
    
    # 1. Obtener datos de API
    datos = {
        'generacion': obtener_generacion_sistema(dias=7),
        'precios': obtener_precios_bolsa(),
        'mix': obtener_mix_energetico()
    }
    
    # 2. Análisis con IA
    analisis_ia = analista.analizar_contexto(mensaje_usuario, datos)
    
    # 3. Determinar tablero relevante
    link_tablero = None
    if "generación" in mensaje_usuario.lower():
        link_tablero = TABLEROS['generacion']
    elif "precio" in mensaje_usuario.lower():
        link_tablero = TABLEROS['precios']
    elif "mix" in mensaje_usuario.lower():
        link_tablero = TABLEROS['generacion-fuentes']
    
    # 4. Construir respuesta completa
    respuesta = f"{analisis_ia}\n\n"
    
    if link_tablero:
        respuesta += f"━━━━━━━━━━━━━━━\n"
        respuesta += f"📊 *Explorar en el dashboard:*\n"
        respuesta += f"{link_tablero}\n\n"
        respuesta += f"✨ Interactivo | 📈 Tiempo real | 📱 Responsive"
    
    return respuesta

# Ejemplo de conversación:
"""
Usuario: ¿Cómo está la generación hoy?

Bot:
🔌 La generación nacional hoy está en 234.5 GWh, 
con predominio de fuentes hidráulicas (65%) seguidas 
de térmicas (28%). Las renovables no convencionales 
aportan el 7% restante.

Este nivel es típico para febrero, cuando los 
aportes hídricos son buenos gracias a la temporada 
de lluvias.

━━━━━━━━━━━━━━━
📊 *Explorar en el dashboard:*
http://portalenergetico.minenergia.gov.co/generacion

✨ Interactivo | 📈 Tiempo real | 📱 Responsive
"""
```

### **9.4 Menú de Navegación**

```python
def menu_principal():
    """Menú interactivo con todos los tableros"""
    
    menu = """
🏠 *Portal Energético MME - Menú*

Envía el número de tu consulta:

*📊 GENERACIÓN*
1️⃣ Generación nacional
2️⃣ Generación por fuentes
3️⃣ Hidrología y embalses

*⚡ SISTEMA*
4️⃣ Demanda de energía
5️⃣ Precios de bolsa
6️⃣ Disponibilidad

*🔌 RED*
7️⃣ Transmisión
8️⃣ Distribución
9️⃣ Pérdidas

*🤖 ANÁLISIS*
🔟 Restricciones
1️⃣1️⃣ Predicciones ML
1️⃣2️⃣ Chat con IA

📱 *Dashboard completo:*
http://portalenergetico.minenergia.gov.co
"""
    return menu

def procesar_menu(opcion: str):
    """Procesa opción del menú y responde"""
    
    opciones = {
        '1': ('generacion', 'Generación Nacional'),
        '2': ('generacion-fuentes', 'Generación por Fuentes'),
        '3': ('hidraulica', 'Hidrología y Embalses'),
        '4': ('demanda', 'Demanda de Energía'),
        '5': ('precios', 'Precios de Bolsa'),
        '6': ('disponibilidad', 'Disponibilidad'),
        '7': ('transmision', 'Transmisión'),
        '8': ('distribucion', 'Distribución'),
        '9': ('perdidas', 'Pérdidas'),
        '10': ('restricciones', 'Restricciones'),
        '11': ('predicciones', 'Predicciones ML'),
    }
    
    if opcion in opciones:
        tablero, nombre = opciones[opcion]
        link = TABLEROS[tablero]
        
        respuesta = f"📊 *{nombre}*\n\n"
        respuesta += f"Ver tablero interactivo:\n{link}\n\n"
        respuesta += "Escribe 'menu' para volver al menú principal"
        
        return respuesta
    
    return menu_principal()
```

---

## 🎯 **10. EJEMPLO COMPLETO: BOT PROFESIONAL**

Actualización del bot con IA + Links integrados:

```python
# Archivo: ejemplos/whatsapp_bot_completo.py
"""
Bot WhatsApp Profesional - Portal Energético MME
Características:
- Consume API REST
- Análisis con IA (Groq/OpenRouter)
- Links a tableros interactivos
- Generación de gráficas
- Menú de navegación
"""

# ... (código del bot con todas las funciones integradas)
```

Ver archivo completo en: `ejemplos/whatsapp_bot_ejemplo.py`

---

**Generado:** 6 de febrero de 2026  
**Versión API:** 1.0.0  
**Para:** Integración WhatsApp Bot

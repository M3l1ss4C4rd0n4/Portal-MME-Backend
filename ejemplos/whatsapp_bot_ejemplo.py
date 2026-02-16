#!/usr/bin/env python3
"""
Bot WhatsApp - Portal Energético MME
Ejemplo completo listo para usar

Autor: Portal Energético MME
Fecha: 6 de febrero de 2026
API: http://portalenergetico.minenergia.gov.co/api
"""

import os
import requests
import matplotlib.pyplot as plt
from twilio.rest import Client
from flask import Flask, request
from datetime import datetime, timedelta
from io import BytesIO
import json

# ═══════════════════════════════════════════════════════════
# CONFIGURACIÓN - Cambiar estos valores
# ═══════════════════════════════════════════════════════════

API_BASE = "http://portalenergetico.minenergia.gov.co/api"

# Credenciales Twilio (obtener en https://console.twilio.com)
TWILIO_SID = "TU_ACCOUNT_SID_AQUI"
TWILIO_TOKEN = "TU_AUTH_TOKEN_AQUI"  
TWILIO_WHATSAPP = "+14155238886"  # Número sandbox Twilio

# Credenciales IA (OPCIONAL - para análisis avanzado)
# Obtener gratis en: https://console.groq.com
GROQ_API_KEY = os.getenv("GROQ_API_KEY", None)  # O configurar aquí directamente

# Dashboard base URL
DASHBOARD_BASE = "http://portalenergetico.minenergia.gov.co"

# ═══════════════════════════════════════════════════════════
# INICIALIZAR SERVICIOS
# ═══════════════════════════════════════════════════════════

client = Client(TWILIO_SID, TWILIO_TOKEN)
app = Flask(__name__)

# ═══════════════════════════════════════════════════════════
# FUNCIONES PARA CONSUMIR LA API
# ═══════════════════════════════════════════════════════════

def obtener_generacion_actual():
    """Obtiene generación eléctrica más reciente"""
    try:
        response = requests.get(
            f"{API_BASE}/v1/generation/system",
            params={"start_date": datetime.now().strftime("%Y-%m-%d")},
            timeout=10
        )
        data = response.json()
        if data['data']:
            return data['data'][-1]
        return None
    except Exception as e:
        print(f"Error API: {e}")
        return None

def obtener_mix_energetico():
    """Obtiene mix energético actual"""
    try:
        response = requests.get(f"{API_BASE}/v1/generation/mix", timeout=10)
        return response.json()['data']
    except Exception as e:
        print(f"Error API: {e}")
        return None

def obtener_precios_bolsa():
    """Obtiene precios de bolsa más recientes"""
    try:
        response = requests.get(f"{API_BASE}/v1/system/prices", timeout=10)
        data = response.json()
        if data['data']:
            return data['data'][-1]
        return None
    except Exception as e:
        print(f"Error API: {e}")
        return None

def obtener_datos_historicos(dias=30):
    """Obtiene datos históricos para gráficas"""
    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{API_BASE}/v1/generation/system",
            params={"start_date": start_date, "end_date": end_date},
            timeout=15
        )
        return response.json()['data']
    except Exception as e:
        print(f"Error API: {e}")
        return None

# ═══════════════════════════════════════════════════════════
# LINKS A TABLEROS DEL DASHBOARD
# ═══════════════════════════════════════════════════════════

# Mapa de tableros disponibles
TABLEROS = {
    'generacion': f"{DASHBOARD_BASE}/generacion",
    'generacion-fuentes': f"{DASHBOARD_BASE}/generacion-fuentes",
    'hidraulica': f"{DASHBOARD_BASE}/generacion/hidraulica/hidrologia",
    'demanda': f"{DASHBOARD_BASE}/demanda",
    'precios': f"{DASHBOARD_BASE}/precios",
    'disponibilidad': f"{DASHBOARD_BASE}/disponibilidad",
    'transmision': f"{DASHBOARD_BASE}/transmision",
    'distribucion': f"{DASHBOARD_BASE}/distribucion",
    'perdidas': f"{DASHBOARD_BASE}/perdidas",
    'restricciones': f"{DASHBOARD_BASE}/restricciones",
    'predicciones': f"{DASHBOARD_BASE}/predicciones",
    'inicio': f"{DASHBOARD_BASE}/"
}

def obtener_link_tablero(mensaje: str) -> tuple:
    """
    Determina qué tablero es relevante según el mensaje
    Returns: (link, nombre_tablero)
    """
    mensaje = mensaje.lower()
    
    if "generación" in mensaje or "generacion" in mensaje:
        if "fuente" in mensaje or "mix" in mensaje:
            return TABLEROS['generacion-fuentes'], "Generación por Fuentes"
        else:
            return TABLEROS['generacion'], "Generación Nacional"
    
    elif "precio" in mensaje:
        return TABLEROS['precios'], "Precios de Bolsa"
    
    elif "demanda" in mensaje:
        return TABLEROS['demanda'], "Demanda Nacional"
    
    elif "hidro" in mensaje or "embalse" in mensaje or "agua" in mensaje:
        return TABLEROS['hidraulica'], "Hidrología y Embalses"
    
    elif "transmis" in mensaje:
        return TABLEROS['transmision'], "Transmisión"
    
    elif "distribuc" in mensaje:
        return TABLEROS['distribucion'], "Distribución"
    
    elif "pérdida" in mensaje or "perdida" in mensaje:
        return TABLEROS['perdidas'], "Pérdidas"
    
    elif "predicci" in mensaje or "pronóstico" in mensaje:
        return TABLEROS['predicciones'], "Predicciones ML"
    
    return None, None

# ═══════════════════════════════════════════════════════════
# ANÁLISIS CON IA (OPCIONAL) - Igual al del Dashboard
# ═══════════════════════════════════════════════════════════

def analizar_con_ia(pregunta: str, datos_contexto: dict) -> str:
    """
    Analiza pregunta del usuario usando IA (Groq)
    Mismo servicio que usa el dashboard web
    
    Requiere: GROQ_API_KEY configurado
    """
    if not GROQ_API_KEY:
        return None  # IA no disponible
    
    try:
        from openai import OpenAI
        
        # Cliente IA (igual al del dashboard)
        ia_client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=GROQ_API_KEY
        )
        
        # System prompt (igual al del dashboard)
        system_prompt = """
        Eres un Analista Energético experto del sector eléctrico colombiano.
        
        Tu rol: 
        - Analizar datos del Sistema Interconectado Nacional (SIN)
        - Explicar métricas energéticas en lenguaje claro
        - Identificar tendencias y patrones
        - Responder preguntas técnicas
        
        Responde de forma concisa para WhatsApp (sin markdown complejo).
        Usa emojis apropiados. Máximo 500 caracteres.
        """
        
        # Construir contexto
        contexto = f"""
        Datos actualizados:
        {json.dumps(datos_contexto, indent=2, ensure_ascii=False)}
        
        Pregunta: {pregunta}
        """
        
        # Llamar a IA
        response = ia_client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Modelo del dashboard
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": contexto}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"❌ Error IA: {e}")
        return None

# ═══════════════════════════════════════════════════════════
# GENERAR GRÁFICAS
# ═══════════════════════════════════════════════════════════

def generar_grafica_generacion():
    """Genera gráfica de generación histórica"""
    datos = obtener_datos_historicos(30)
    
    if not datos:
        return None
    
    # Extraer fechas y valores
    fechas = [datetime.strptime(d['date'], '%Y-%m-%d') for d in datos]
    valores = [d['value'] for d in datos]
    
    # Crear gráfica
    plt.figure(figsize=(12, 6))
    plt.plot(fechas, valores, linewidth=2.5, color='#2563eb', marker='o', markersize=4)
    plt.title('Generación Eléctrica Nacional - Últimos 30 Días', 
              fontsize=16, fontweight='bold', pad=20)
    plt.xlabel('Fecha', fontsize=12)
    plt.ylabel('Generación (GWh)', fontsize=12)
    plt.grid(True, alpha=0.3, linestyle='--')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Guardar en buffer
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer

def generar_grafica_mix():
    """Genera gráfica circular del mix energético"""
    datos = obtener_mix_energetico()
    
    if not datos:
        return None
    
    # Extraer tipos y porcentajes
    tipos = [d['tipo'] for d in datos]
    porcentajes = [d['porcentaje'] for d in datos]
    
    # Colores por fuente energética
    colores = {
        'HIDRAULICA': '#2196F3',
        'TERMICA': '#FF5722',
        'EOLICA': '#4CAF50',
        'SOLAR': '#FFC107',
        'COGENERADOR': '#9C27B0'
    }
    colors = [colores.get(t, '#9E9E9E') for t in tipos]
    
    # Crear gráfica
    plt.figure(figsize=(10, 8))
    wedges, texts, autotexts = plt.pie(
        porcentajes, 
        labels=tipos, 
        colors=colors,
        autopct='%1.1f%%',
        startangle=90,
        textprops={'fontsize': 12, 'weight': 'bold'}
    )
    
    plt.title('Mix Energético Actual - Colombia', 
              fontsize=16, fontweight='bold', pad=20)
    plt.axis('equal')
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer

# ═══════════════════════════════════════════════════════════
# LÓGICA DEL BOT - RESPUESTAS INTELIGENTES
# ═══════════════════════════════════════════════════════════

def procesar_comando(mensaje):
    """
    Procesa el mensaje del usuario y devuelve respuesta apropiada
    
    Args:
        mensaje: Texto del mensaje del usuario
        
    Returns:
        dict: {"tipo": "texto"|"imagen", "contenido": ...}
    """
    
    mensaje_lower = mensaje.lower().strip()
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # COMANDO: Generación actual
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if any(word in mensaje_lower for word in ['generacion', 'generación', 'cuanta energia']):
        
        # Si pide gráfica
        if any(word in mensaje_lower for word in ['grafica', 'gráfica', 'grafico', 'gráfico', 'chart']):
            buffer = generar_grafica_generacion()
            if buffer:
                return {
                    "tipo": "imagen",
                    "contenido": buffer,
                    "caption": f"📊 Generación Eléctrica Nacional - Últimos 30 días\n\n"
                               f"📊 Ver tablero interactivo:\n{TABLEROS['generacion']}"
                }
            else:
                return {
                    "tipo": "texto",
                    "contenido": "❌ Error generando gráfica. Intenta de nuevo."
                }
        
        # Solo texto
        else:
            dato = obtener_generacion_actual()
            if dato:
                respuesta = f"📊 *Generación Eléctrica Nacional*\n\n"
                respuesta += f"💡 Generación: *{dato['value']:.2f} GWh*\n"
                respuesta += f"📅 Fecha: {dato['date']}\n\n"
                
                # Agregar análisis IA si está disponible
                if GROQ_API_KEY:
                    contexto = {'generacion': dato}
                    analisis = analizar_con_ia(mensaje, contexto)
                    if analisis:
                        respuesta += f"🤖 *Análisis IA:* {analisis}\n\n"
                
                # Agregar link al tablero
                respuesta += f"💬 Escribe *'gráfica generación'* para ver el histórico\n"
                respuesta += f"\n📊 *Ver tablero interactivo:*\n{TABLEROS['generacion']}"
                
                return {"tipo": "texto", "contenido": respuesta}
            else:
                return {
                    "tipo": "texto",
                    "contenido": "❌ No se pudo obtener datos de generación"
                }
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # COMANDO: Mix energético
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    elif 'mix' in mensaje_lower or 'fuentes' in mensaje_lower:
        
        # Si pide gráfica
        if any(word in mensaje_lower for word in ['grafica', 'gráfica', 'grafico', 'gráfico']):
            buffer = generar_grafica_mix()
            if buffer:
                return {
                    "tipo": "imagen",
                    "contenido": buffer,
                    "caption": f"⚡ Mix Energético Actual - Colombia\n\n"
                               f"📊 Ver tablero interactivo:\n{TABLEROS['generacion-fuentes']}"
                }
        
        # Solo texto
        else:
            datos = obtener_mix_energetico()
            if datos:
                respuesta = "⚡ *Mix Energético Actual*\n\n"
                
                emojis = {
                    'HIDRAULICA': '💧',
                    'TERMICA': '🔥',
                    'EOLICA': '💨',
                    'SOLAR': '☀️',
                    'COGENERADOR': '⚙️'
                }
                
                for fuente in datos:
                    emoji = emojis.get(fuente['tipo'], '⚡')
                    respuesta += f"{emoji} *{fuente['tipo']}*: {fuente['porcentaje']:.1f}%\n"
                
                respuesta += f"\n💬 Escribe *'gráfica mix'* para ver el gráfico\n"
                respuesta += f"\n📊 *Ver tablero interactivo:*\n{TABLEROS['generacion-fuentes']}"
                
                return {"tipo": "texto", "contenido": respuesta}
            else:
                return {"tipo": "texto", "contenido": "❌ No se pudo obtener mix energético"}
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # COMANDO: Precios de bolsa
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    elif any(word in mensaje_lower for word in ['precio', 'bolsa', 'costo']):
        dato = obtener_precios_bolsa()
        if dato:
            respuesta = f"💰 *Precio de Bolsa Nacional*\n\n"
            respuesta += f"💵 Precio: *${dato['value']:.2f} COP/kWh*\n"
            respuesta += f"📅 Fecha: {dato['date']}\n\n"
            respuesta += f"📊 *Ver histórico de precios:*\n{TABLEROS['precios']}"
            
            return {"tipo": "texto", "contenido": respuesta}
        else:
            return {"tipo": "texto", "contenido": "❌ No se pudo obtener precios"}
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # COMANDO: Dashboard / Tableros
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    elif any(word in mensaje_lower for word in ['dashboard', 'tablero', 'portal', 'link', 'url']):
        return {
            "tipo": "texto",
            "contenido": "🌐 *Portal Energético MME*\n\n"
                         "📊 *Dashboard Completo:*\n"
                         "http://portalenergetico.minenergia.gov.co\n\n"
                         "📚 *Documentación API:*\n"
                         "http://portalenergetico.minenergia.gov.co/api/docs\n\n"
                         "✨ El dashboard incluye:\n"
                         "• Datos en tiempo real\n"
                         "• Gráficas interactivas\n"
                         "• Predicciones ML\n"
                         "• Chat IA integrado"
        }
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # COMANDO: Ayuda / Menú
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    else:
        return {
            "tipo": "texto",
            "contenido": "🤖 *Portal Energético MME - Bot*\n\n"
                         "📋 *Comandos disponibles:*\n\n"
                         "1️⃣ `generación` - Datos actuales\n"
                         "2️⃣ `gráfica generación` - Ver histórico\n"
                         "3️⃣ `mix` - Mix energético\n"
                         "4️⃣ `gráfica mix` - Gráfico circular\n"
                         "5️⃣ `precios` - Precios de bolsa\n"
                         "6️⃣ `dashboard` - Link al portal\n"
                         "7️⃣ `ayuda` - Este menú\n\n"
                         "💬 *Ejemplos de preguntas:*\n"
                         "• ¿Cuánta energía se genera?\n"
                         "• Muestra el mix energético\n"
                         "• Dame el precio de bolsa\n"
                         "• Quiero ver gráficas"
        }

# ═══════════════════════════════════════════════════════════
# ENVIAR RESPUESTAS POR WHATSAPP
# ═══════════════════════════════════════════════════════════

def enviar_respuesta(respuesta, numero_destino):
    """
    Envía respuesta por WhatsApp (texto o imagen)
    
    Args:
        respuesta: Dict con tipo y contenido
        numero_destino: Número de WhatsApp del destinatario
    """
    try:
        if respuesta["tipo"] == "texto":
            # Enviar mensaje de texto
            message = client.messages.create(
                from_=f'whatsapp:{TWILIO_WHATSAPP}',
                to=numero_destino,
                body=respuesta["contenido"]
            )
            print(f"✅ Mensaje enviado: {message.sid}")
            
        elif respuesta["tipo"] == "imagen":
            # Para enviar imagen necesitas subirla a un servidor público
            # Aquí usarías un servicio como Cloudinary, S3, etc.
            # Por simplicidad, enviamos solo el caption
            message = client.messages.create(
                from_=f'whatsapp:{TWILIO_WHATSAPP}',
                to=numero_destino,
                body=f"{respuesta.get('caption', 'Gráfica generada')}\n\n"
                     f"(Para ver gráficas completas, visita:\n"
                     f"http://portalenergetico.minenergia.gov.co)"
            )
            print(f"✅ Mensaje con gráfica enviado: {message.sid}")
            
    except Exception as e:
        print(f"❌ Error enviando mensaje: {e}")

# ═══════════════════════════════════════════════════════════
# WEBHOOK - RECIBIR MENSAJES DE WHATSAPP
# ═══════════════════════════════════════════════════════════

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """
    Endpoint que recibe mensajes de WhatsApp desde Twilio
    Configurar en: https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox
    """
    
    # Obtener datos del mensaje
    mensaje_entrante = request.form.get('Body', '')
    numero_remitente = request.form.get('From', '')
    
    print(f"📩 Mensaje recibido de {numero_remitente}: {mensaje_entrante}")
    
    # Procesar comando
    respuesta = procesar_comando(mensaje_entrante)
    
    # Enviar respuesta
    enviar_respuesta(respuesta, numero_remitente)
    
    return 'OK', 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "WhatsApp Bot Portal Energético MME"}, 200

# ═══════════════════════════════════════════════════════════
# INICIAR BOT
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print("🤖 Bot WhatsApp - Portal Energético MME")
    print("=" * 60)
    print(f"📡 API: {API_BASE}")
    print(f"📱 WhatsApp: {TWILIO_WHATSAPP}")
    print(f"🌐 Webhook: http://localhost:5000/webhook/whatsapp")
    print("=" * 60)
    print("\n⚠️  IMPORTANTE:")
    print("1. Configura las credenciales de Twilio en las variables")
    print("2. Expón el webhook con ngrok: ngrok http 5000")
    print("3. Copia la URL de ngrok a la configuración de Twilio")
    print("4. Envía un mensaje de WhatsApp al sandbox de Twilio")
    print("=" * 60)
    print("\n🚀 Bot iniciado en http://localhost:5000\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)

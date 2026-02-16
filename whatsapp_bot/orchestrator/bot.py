"""
Bot Orchestrator - Lógica central del chatbot
"""
import logging
import re
from typing import Dict, Optional
from datetime import datetime

from app.config import settings
from app.utils.stats import increment_stat
from services.data_service import DataService
from services.ai_integration import AIIntegration

logger = logging.getLogger(__name__)


class BotOrchestrator:
    """
    Orquestador central del chatbot
    Maneja la lógica de negocio y routing de intenciones
    """
    
    def __init__(self):
        self.data_service = DataService()
        self.ai_integration = AIIntegration()
    
    async def process_message(
        self,
        user_id: str,
        message: str,
        media_url: Optional[str] = None
    ) -> Dict:
        """
        Procesa mensaje y genera respuesta
        
        Args:
            user_id: ID del usuario (número WhatsApp)
            message: Texto del mensaje
            media_url: URL de media adjunta (opcional)
        
        Returns:
            Dict con 'body' y opcionalmente 'media_url'
        """
        try:
            increment_stat("messages_received")
            
            # Limpiar mensaje
            message = message.strip()
            
            # Comandos especiales
            if message.startswith("/"):
                return await self.handle_command(message, user_id)
            
            # Clasificar intención
            intent = self.classify_intent(message)
            logger.info(f"Intent detectado: {intent} para usuario {user_id}")
            
            # Routing según intent
            if intent == "GREETING":
                response = self.handle_greeting(user_id)
            
            elif intent == "HELP":
                response = self.handle_help()
            
            elif intent == "DATA_QUERY":
                response = await self.handle_data_query(message)
            
            elif intent == "AI_ANALYSIS":
                response = await self.handle_ai_analysis(message)
            
            elif intent == "PRICE_QUERY":
                response = await self.handle_price_query()
            
            elif intent == "GENERATION_QUERY":
                response = await self.handle_generation_query()
            
            else:
                # Fallback: usar IA para responder
                response = await self.handle_ai_analysis(message)
            
            increment_stat("messages_sent")
            return response
        
        except Exception as e:
            logger.error(f"Error procesando mensaje: {str(e)}", exc_info=True)
            increment_stat("messages_failed")
            
            return {
                "body": "❌ Lo siento, ocurrió un error procesando tu mensaje. "
                        "Por favor intenta de nuevo o contacta soporte."
            }
    
    def classify_intent(self, message: str) -> str:
        """
        Clasifica la intención del usuario
        """
        message_lower = message.lower()
        
        # Saludos
        if any(word in message_lower for word in ["hola", "buenos", "buenas", "hi", "hello"]):
            return "GREETING"
        
        # Ayuda
        if any(word in message_lower for word in ["ayuda", "help", "comandos", "qué puedes"]):
            return "HELP"
        
        # Precio
        if any(word in message_lower for word in ["precio", "bolsa", "cuánto cuesta"]):
            return "PRICE_QUERY"
        
        # Generación
        if any(word in message_lower for word in ["generación", "generacion", "cuánta energía", "producción"]):
            return "GENERATION_QUERY"
        
        # Análisis IA
        if any(word in message_lower for word in ["analiza", "análisis", "explica", "qué pasa", "tendencia"]):
            return "AI_ANALYSIS"
        
        # Datos generales
        if any(word in message_lower for word in ["datos", "estadísticas", "información", "mostrar"]):
            return "DATA_QUERY"
        
        return "GENERAL"
    
    def handle_greeting(self, user_id: str) -> Dict:
        """
        Responde a saludos
        """
        return {
            "body": f"""¡Hola! 👋 Soy el asistente inteligente del Portal Energético del MME.

Puedo ayudarte con:
📊 Datos del Sistema Interconectado Nacional
💡 Generación eléctrica por fuente
💰 Precios de bolsa
🤖 Análisis con IA

Prueba preguntándome:
• "¿Cuál es el precio de bolsa?"
• "Analiza la generación"
• "/menu" para ver todas las opciones

¿En qué te puedo ayudar?"""
        }
    
    def handle_help(self) -> Dict:
        """
        Muestra ayuda
        """
        return {
            "body": """🤖 **MENÚ DE AYUDA**

📊 **CONSULTAS RÁPIDAS**
• precio - Precio de bolsa actual
• generacion - Generación actual
• demanda - Demanda del sistema
• mix - Mix energético

🤖 **ANÁLISIS IA**
• analiza generacion
• analiza demanda
• explica [concepto]

⚙️ **COMANDOS**
• /menu - Menú principal
• /help - Esta ayuda
• /stats - Estadísticas del bot

También puedes hacer preguntas en lenguaje natural 😊"""
        }
    
    async def handle_command(self, command: str, user_id: str) -> Dict:
        """
        Maneja comandos especiales /comando
        """
        cmd = command.split()[0].lower()
        
        if cmd == "/menu":
            return self.handle_help()
        
        elif cmd == "/help":
            return self.handle_help()
        
        elif cmd == "/stats":
            from app.utils.stats import get_bot_stats
            stats = get_bot_stats()
            
            return {
                "body": f"""📊 **ESTADÍSTICAS DEL BOT**

Mensajes recibidos: {stats.get('messages_received', 0)}
Mensajes enviados: {stats.get('messages_sent', 0)}
Tasa de éxito: {stats.get('success_rate', 0)}%
Usuarios activos (24h): {stats.get('active_users_24h', 0)}
Uptime: {stats.get('uptime', 'N/A')}"""
            }
        
        else:
            return {
                "body": f"❓ Comando desconocido: {cmd}\n\nEnvía /help para ver comandos disponibles."
            }
    
    async def handle_data_query(self, message: str) -> Dict:
        """
        Maneja consultas de datos
        """
        try:
            # Por ahora, delegamos a IA
            return await self.handle_ai_analysis(message)
        except Exception as e:
            logger.error(f"Error en data query: {str(e)}")
            return {
                "body": "❌ Error consultando datos. Por favor intenta de nuevo."
            }
    
    async def handle_ai_analysis(self, message: str) -> Dict:
        """
        Usa IA para analizar y responder
        """
        try:
            increment_stat("ai_queries")
            
            # Llamar al AI Agent
            analysis = await self.ai_integration.analyze_question(message)
            
            return {
                "body": analysis
            }
        
        except Exception as e:
            logger.error(f"Error en AI analysis: {str(e)}")
            
            if "rate limit" in str(e).lower() or "429" in str(e):
                return {
                    "body": "⏳ El servicio de IA ha alcanzado el límite de uso. "
                            "Por favor intenta en unos minutos."
                }
            
            return {
                "body": "❌ Error procesando análisis IA. Intenta con una consulta más simple."
            }
    
    async def handle_price_query(self) -> Dict:
        """
        Consulta precio de bolsa actual
        """
        try:
            price_data = await self.data_service.get_latest_price()
            
            if price_data:
                return {
                    "body": f"""💰 **PRECIO DE BOLSA**

Precio actual: ${price_data['precio']:.2f}/kWh
Fecha: {price_data['fecha']}

Promedio mensual: ${price_data.get('promedio_mes', 0):.2f}/kWh"""
                }
            else:
                return {
                    "body": "❌ No hay datos de precio disponibles en este momento."
                }
        
        except Exception as e:
            logger.error(f"Error consultando precio: {str(e)}")
            return {
                "body": "❌ Error consultando precio de bolsa."
            }
    
    async def handle_generation_query(self) -> Dict:
        """
        Consulta generación actual
        """
        try:
            gen_data = await self.data_service.get_latest_generation()
            
            if gen_data:
                total = gen_data.get('total_gwh', 0)
                
                sources = gen_data.get('sources', {})
                sources_text = "\n".join([
                    f"• {source}: {value:.1f} GWh ({value/total*100:.1f}%)"
                    for source, value in sorted(sources.items(), key=lambda x: x[1], reverse=True)
                ])
                
                return {
                    "body": f"""⚡ **GENERACIÓN ACTUAL**

Total: {total:.1f} GWh

**Por fuente:**
{sources_text}

Fecha: {gen_data.get('fecha', 'N/A')}"""
                }
            else:
                return {
                    "body": "❌ No hay datos de generación disponibles."
                }
        
        except Exception as e:
            logger.error(f"Error consultando generación: {str(e)}")
            return {
                "body": "❌ Error consultando generación."
            }

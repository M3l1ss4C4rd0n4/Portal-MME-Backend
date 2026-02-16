"""
Telegram Handler
Maneja mensajes entrantes de Telegram y los procesa con el orquestador del bot
"""
import logging
from typing import Dict, Optional
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode

from app.config import settings
from orchestrator.bot import BotOrchestrator

logger = logging.getLogger(__name__)

# Inicializar orquestador (se auto-inicializa con DataService y AIIntegration)
bot_orchestrator = BotOrchestrator()


class TelegramHandler:
    """Manejador de mensajes de Telegram"""
    
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN no configurado")
        
        self.application = None
        self.bot = Bot(token=self.bot_token)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Maneja el comando /start
        """
        user = update.effective_user
        logger.info(f"Usuario {user.id} (@{user.username}) inició el bot")
        
        # Mensaje de bienvenida
        welcome_message = f"""
¡Hola {user.first_name}! 👋

Soy el bot del **Portal Energético** del Ministerio de Minas y Energía de Colombia 🇨🇴

📊 Puedo ayudarte a consultar información del Sistema Interconectado Nacional (SIN):

🔹 Precio de bolsa eléctrica en tiempo real
🔹 Generación por fuente energética
🔹 Demanda del sistema
🔹 Mix energético nacional
🔹 Análisis con inteligencia artificial

**¿Cómo usar el bot?**

Puedes usar comandos o simplemente escribirme en lenguaje natural.

**Comandos disponibles:**
/precio - Ver precio actual de bolsa
/generacion - Ver generación por fuente
/demanda - Ver demanda actual del sistema
/mix - Ver mix energético nacional
/grafico - Generar gráfico de datos
/resumen - Resumen ejecutivo del día
/ayuda - Ver todos los comandos

O simplemente pregunta:
• "¿Cuál es el precio actual?"
• "Muéstrame la generación hidráulica"
• "¿Cómo está la demanda?"

¡Adelante, pregúntame lo que necesites! ⚡
"""
        
        # Teclado inline con opciones rápidas
        keyboard = [
            [
                InlineKeyboardButton("💰 Precio", callback_data="precio"),
                InlineKeyboardButton("⚡ Generación", callback_data="generacion"),
            ],
            [
                InlineKeyboardButton("📊 Demanda", callback_data="demanda"),
                InlineKeyboardButton("🔋 Mix", callback_data="mix"),
            ],
            [
                InlineKeyboardButton("📈 Gráfico", callback_data="grafico"),
                InlineKeyboardButton("📋 Resumen", callback_data="resumen"),
            ],
            [
                InlineKeyboardButton("❓ Ayuda", callback_data="ayuda"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Maneja el comando /ayuda o /help
        """
        help_text = """
📚 **Guía de Uso del Bot**

**Comandos disponibles:**

💰 `/precio` - Precio actual de bolsa eléctrica
⚡ `/generacion` - Generación por fuente energética
📊 `/demanda` - Demanda actual del sistema
🔋 `/mix` - Mix energético nacional
📈 `/grafico` - Generar gráfico de datos
📋 `/resumen` - Resumen ejecutivo del día
❓ `/ayuda` - Mostrar esta ayuda

**También puedes escribir en lenguaje natural:**

Ejemplos:
• "¿Cuál es el precio de la energía ahora?"
• "Muéstrame un gráfico de generación hidráulica"
• "¿Cómo está la demanda comparada con ayer?"
• "Explícame el mix energético"

**Funciones especiales:**

🤖 **IA integrada:** El bot usa inteligencia artificial para entender tus preguntas y dar respuestas contextualizadas.

📊 **Datos en tiempo real:** Toda la información viene directamente del Sistema Interconectado Nacional.

📈 **Gráficos dinámicos:** Genera visualizaciones de los datos que necesites.

**Soporte:**
Para más información, visita: https://portalenergetico.minenergia.gov.co

¡Estoy aquí para ayudarte! 24/7 ⚡
"""
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def precio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /precio"""
        await self.process_message(update, "precio")
    
    async def generacion_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /generacion"""
        await self.process_message(update, "generacion")
    
    async def demanda_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /demanda"""
        await self.process_message(update, "demanda")
    
    async def mix_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /mix"""
        await self.process_message(update, "mix energetico")
    
    async def grafico_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /grafico"""
        await self.process_message(update, "genera un grafico de generacion")
    
    async def resumen_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /resumen"""
        await self.process_message(update, "dame un resumen del sistema")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Maneja mensajes de texto general
        """
        await self.process_message(update, update.message.text)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Maneja callbacks de botones inline
        """
        query = update.callback_query
        await query.answer()
        
        # Obtener comando del callback
        command = query.data
        
        # Procesar como si fuera un mensaje
        await self.process_callback(query, command)
    
    async def process_message(self, update: Update, message: str):
        """
        Procesa un mensaje usando el orquestador del bot
        """
        user = update.effective_user
        chat_id = str(update.effective_chat.id)
        
        logger.info(f"Mensaje de {user.id} (@{user.username}): {message}")
        
        try:
            # Enviar indicador de "escribiendo..."
            await update.effective_chat.send_action("typing")
            
            # Procesar mensaje con el orquestador
            response = await bot_orchestrator.process_message(
                user_id=chat_id,
                message=message
            )
            
            # Enviar respuesta
            if response.get("media_url"):
                # Si hay imagen, enviarla
                await update.effective_chat.send_photo(
                    photo=response["media_url"],
                    caption=response.get("body", "")[:1024] or None
                )
            else:
                # Solo texto
                # Telegram tiene límite de 4096 caracteres
                text = response.get("body", "")
                if len(text) > 4096:
                    # Dividir en múltiples mensajes
                    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
                    for chunk in chunks:
                        await update.effective_chat.send_message(chunk)
                else:
                    await update.effective_chat.send_message(text)
            
            logger.info(f"Respuesta enviada a {user.id}")
            
        except Exception as e:
            logger.error(f"Error procesando mensaje: {str(e)}", exc_info=True)
            await update.effective_chat.send_message(
                "❌ Lo siento, ocurrió un error procesando tu solicitud. "
                "Por favor intenta de nuevo en unos momentos."
            )
    
    async def process_callback(self, query, command: str):
        """
        Procesa un callback de botón inline
        """
        chat_id = str(query.message.chat.id)
        user = query.from_user
        
        logger.info(f"Callback de {user.id} (@{user.username}): {command}")
        
        try:
            # Enviar indicador de "escribiendo..."
            await query.message.chat.send_action("typing")
            
            # Procesar comando con el orquestador
            response = await bot_orchestrator.process_message(
                user_id=chat_id,
                message=command
            )
            
            # Enviar respuesta
            if response.get("media_url"):
                await query.message.chat.send_photo(
                    photo=response["media_url"],
                    caption=response.get("body", "")[:1024] or None
                )
            else:
                text = response.get("body", "")
                if len(text) > 4096:
                    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
                    for chunk in chunks:
                        await query.message.chat.send_message(chunk)
                else:
                    await query.message.chat.send_message(text)
            
            logger.info(f"Respuesta enviada a callback de {user.id}")
            
        except Exception as e:
            logger.error(f"Error procesando callback: {str(e)}", exc_info=True)
            await query.message.chat.send_message(
                "❌ Lo siento, ocurrió un error procesando tu solicitud. "
                "Por favor intenta de nuevo."
            )
    
    def setup_handlers(self):
        """
        Configura los manejadores de comandos y mensajes
        """
        # Comandos
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("ayuda", self.help_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("precio", self.precio_command))
        self.application.add_handler(CommandHandler("generacion", self.generacion_command))
        self.application.add_handler(CommandHandler("demanda", self.demanda_command))
        self.application.add_handler(CommandHandler("mix", self.mix_command))
        self.application.add_handler(CommandHandler("grafico", self.grafico_command))
        self.application.add_handler(CommandHandler("resumen", self.resumen_command))
        
        # Callbacks de botones
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Mensajes de texto
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        logger.info("Handlers de Telegram configurados")
    
    async def start_polling(self):
        """
        Inicia el bot en modo polling (para desarrollo)
        """
        self.application = Application.builder().token(self.bot_token).build()
        self.setup_handlers()
        
        logger.info("Iniciando Telegram bot en modo polling...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Telegram bot iniciado exitosamente")
    
    async def stop_polling(self):
        """
        Detiene el bot en modo polling
        """
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot detenido")


# Webhook handling
async def handle_telegram_webhook(update_data: dict) -> dict:
    """
    Maneja un update de webhook de Telegram
    
    Args:
        update_data: Datos del update de Telegram
    
    Returns:
        Respuesta para Telegram
    """
    try:
        update = Update.de_json(update_data, Bot(token=settings.TELEGRAM_BOT_TOKEN))
        
        # Crear handler temporal
        handler = TelegramHandler()
        
        # Procesar según tipo de update
        if update.message:
            if update.message.text:
                if update.message.text.startswith('/'):
                    # Es un comando
                    command = update.message.text[1:].split()[0]
                    if command == "start":
                        await handler.start_command(update, None)
                    elif command in ["ayuda", "help"]:
                        await handler.help_command(update, None)
                    elif command == "precio":
                        await handler.precio_command(update, None)
                    elif command == "generacion":
                        await handler.generacion_command(update, None)
                    elif command == "demanda":
                        await handler.demanda_command(update, None)
                    elif command == "mix":
                        await handler.mix_command(update, None)
                    elif command == "grafico":
                        await handler.grafico_command(update, None)
                    elif command == "resumen":
                        await handler.resumen_command(update, None)
                    else:
                        await handler.handle_message(update, None)
                else:
                    # Mensaje normal
                    await handler.handle_message(update, None)
        
        elif update.callback_query:
            # Callback de botón
            await handler.handle_callback(update, None)
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Error en webhook de Telegram: {str(e)}", exc_info=True)
        return {"ok": False, "error": str(e)}


# Función para iniciar bot en modo standalone (para desarrollo local)
async def run_telegram_bot():
    """
    Ejecuta el bot de Telegram en modo polling (desarrollo)
    """
    handler = TelegramHandler()
    await handler.start_polling()
    
    # Mantener el bot corriendo
    import asyncio
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await handler.stop_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_telegram_bot())

"""
WhatsApp Bot - FastAPI Application
Entry point del servicio
"""
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from datetime import datetime

from app.config import settings
from app.webhook import handle_whatsapp_webhook
from app.utils.logging_config import setup_logging

# Setup logging
logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager para la aplicación
    """
    # Startup
    logger.info("=" * 70)
    logger.info("🚀 Iniciando WhatsApp Bot - Portal Energético MME")
    logger.info("=" * 70)
    logger.info(f"Entorno: {settings.APP_ENV}")
    logger.info(f"Puerto: {settings.APP_PORT}")
    logger.info(f"Proveedor WhatsApp: {settings.WHATSAPP_PROVIDER}")
    logger.info(f"Database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'SQLite'}")
    logger.info(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    
    # Verificar configuración
    if settings.WHATSAPP_PROVIDER == "twilio":
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            logger.warning("⚠️ Credenciales Twilio no configuradas")
    
    if not settings.GROQ_API_KEY:
        logger.warning("⚠️ GROQ_API_KEY no configurado - funciones IA limitadas")
    
    logger.info("✅ WhatsApp Bot inicializado correctamente")
    logger.info("=" * 70)
    
    yield
    
    # Shutdown
    logger.info("🔴 Deteniendo WhatsApp Bot...")


# Crear aplicación FastAPI
app = FastAPI(
    title="WhatsApp Bot - Portal Energético MME",
    description="Chatbot inteligente para consultas del Sistema Interconectado Nacional",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """Endpoint raíz"""
    return {
        "service": "WhatsApp Bot - Portal Energético MME",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "checks": {
            "api": "ok",
            "database": "ok",
            "redis": "ok"
        }
    }


@app.post("/webhook/whatsapp")
async def webhook_whatsapp(
    request: Request,
    x_twilio_signature: str = Header(None)
):
    """
    Webhook para recibir mensajes de WhatsApp desde Twilio/Meta
    """
    try:
        # Log request
        logger.info(f"📩 Webhook recibido desde {request.client.host}")
        
        # Procesar webhook
        response = await handle_whatsapp_webhook(request, x_twilio_signature)
        
        return JSONResponse(content=response)
    
    except HTTPException as e:
        logger.error(f"❌ Error HTTP en webhook: {e.detail}")
        raise e
    
    except Exception as e:
        logger.error(f"❌ Error no manejado en webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/send")
async def send_message(
    to: str,
    body: str,
    media_url: str = None
):
    """
    Endpoint interno para enviar mensajes
    (Útil para testing y operaciones manuales)
    """
    from app.sender import send_whatsapp_message
    
    try:
        result = await send_whatsapp_message(to, body, media_url)
        
        return {
            "status": "sent",
            "to": to,
            "message_id": result.get("sid") or result.get("message_id"),
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/process-message")
async def process_message_api(request: Request):
    """
    Endpoint para que whatsapp-web-service envíe mensajes a procesar
    Usado cuando WHATSAPP_PROVIDER=whatsapp-web
    """
    from orchestrator.bot import BotOrchestrator
    
    try:
        data = await request.json()
        
        from_number = data.get("from_number")
        body = data.get("body", "")
        has_media = data.get("has_media", False)
        
        if not from_number or not body:
            raise HTTPException(status_code=400, detail="Missing from_number or body")
        
        logger.info(f"📱 Procesando mensaje de {from_number}: {body[:50]}...")
        
        # Procesar con el orquestador
        bot_orchestrator = BotOrchestrator()
        response = await bot_orchestrator.process_message(
            user_id=from_number,
            message=body,
            media_url=None
        )
        
        logger.info(f"✅ Mensaje procesado para {from_number}")
        
        return {
            "body": response.get("body", ""),
            "media_url": response.get("media_url"),
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"❌ Error procesando mensaje: {str(e)}", exc_info=True)
        
        # Respuesta de error amigable
        return {
            "body": "❌ Lo siento, hubo un error procesando tu mensaje. Por favor intenta nuevamente.",
            "error": str(e)
        }


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request):
    """
    Webhook para recibir mensajes de Telegram
    """
    if not settings.TELEGRAM_ENABLED:
        raise HTTPException(status_code=404, detail="Telegram bot not enabled")
    
    try:
        data = await request.json()
        logger.info(f"📱 Webhook de Telegram recibido")
        
        from app.telegram_handler import handle_telegram_webhook
        response = await handle_telegram_webhook(data)
        
        return JSONResponse(content=response)
    
    except Exception as e:
        logger.error(f"❌ Error en webhook de Telegram: {str(e)}", exc_info=True)
        return JSONResponse(content={"ok": False, "error": str(e)})


@app.get("/stats")
async def get_stats():
    """
    Estadísticas del bot
    """
    from app.utils.stats import get_bot_stats
    
    try:
        stats = get_bot_stats()
        return stats
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}")
        return {"error": str(e)}


@app.post("/api/broadcast-alert")
async def broadcast_alert(request: Request):
    """
    Endpoint para enviar alertas a TODOS los usuarios que han usado el bot.
    
    Llamado por el sistema de alertas del orquestador (Celery tasks).
    El bot conoce a todos los usuarios que alguna vez le escribieron
    porque sus números se guardan en Redis al recibir mensajes.
    
    Body JSON:
        - message: Texto de la alerta
        - severity: Severidad (CRITICAL, ALERT, WARNING, INFO)
    """
    from app.sender import send_whatsapp_message
    import redis as redis_lib
    
    try:
        data = await request.json()
        message = data.get("message", "")
        severity = data.get("severity", "INFO")
        
        if not message:
            raise HTTPException(status_code=400, detail="Missing 'message' field")
        
        logger.info(f"📢 BROADCAST ALERT | Severidad: {severity}")
        
        # Obtener todos los usuarios conocidos del bot desde Redis
        redis_client = redis_lib.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=3,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True
        )
        
        known_users = redis_client.smembers('bot:known_users')
        
        if not known_users:
            logger.warning("⚠️ No hay usuarios conocidos en el bot para enviar alerta")
            return {
                "status": "no_users",
                "message": "No hay usuarios registrados en el bot",
                "users_count": 0,
                "sent": 0,
                "timestamp": datetime.now().isoformat()
            }
        
        logger.info(f"📋 Enviando alerta a {len(known_users)} usuarios conocidos")
        
        # Enviar a cada usuario
        sent = 0
        failed = 0
        errors_list = []
        
        for phone in known_users:
            try:
                result = await send_whatsapp_message(to=phone, body=message)
                sent += 1
                logger.info(f"✅ Alerta enviada a {phone}")
            except Exception as e:
                failed += 1
                errors_list.append({"phone": phone, "error": str(e)})
                logger.error(f"❌ Error enviando alerta a {phone}: {e}")
        
        logger.info(f"📤 Broadcast completado: {sent} enviados, {failed} fallidos")
        
        # ═══ También enviar a usuarios de Telegram ═══
        telegram_sent = 0
        telegram_failed = 0
        try:
            telegram_users = redis_client.smembers('bot:known_telegram_users')
            if telegram_users:
                import httpx
                token = settings.TELEGRAM_BOT_TOKEN
                if token:
                    async with httpx.AsyncClient(timeout=10.0) as http_client:
                        for tg_user_id in telegram_users:
                            try:
                                resp = await http_client.post(
                                    f"https://api.telegram.org/bot{token}/sendMessage",
                                    json={"chat_id": int(tg_user_id), "text": message}
                                )
                                if resp.status_code == 200:
                                    telegram_sent += 1
                                else:
                                    telegram_failed += 1
                            except Exception as te:
                                telegram_failed += 1
                                logger.error(f"❌ Error Telegram {tg_user_id}: {te}")
                    logger.info(f"📤 Telegram broadcast: {telegram_sent} OK, {telegram_failed} fallidos")
        except Exception as te:
            logger.error(f"Error broadcast Telegram: {te}")
        
        return {
            "status": "completed",
            "severity": severity,
            "users_count": len(known_users),
            "sent": sent,
            "failed": failed,
            "telegram_sent": telegram_sent,
            "telegram_failed": telegram_failed,
            "errors": errors_list[:5] if errors_list else [],
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error en broadcast: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/known-users")
async def get_known_users():
    """
    Retorna la cantidad de usuarios conocidos del bot
    """
    import redis as redis_lib
    
    try:
        redis_client = redis_lib.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=3,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True
        )
        
        known_users = redis_client.smembers('bot:known_users')
        
        # También obtener usuarios de Telegram
        telegram_users = redis_client.smembers('bot:known_telegram_users')
        
        return {
            "total_users": len(known_users) + len(telegram_users),
            "whatsapp_users": list(known_users),
            "telegram_users": list(telegram_users),
            "whatsapp_count": len(known_users),
            "telegram_count": len(telegram_users),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════
# Error handlers
# ═══════════════════════════════════════════════════════════

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handler para excepciones HTTP"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handler para excepciones generales"""
    logger.error(f"Error no manejado: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )

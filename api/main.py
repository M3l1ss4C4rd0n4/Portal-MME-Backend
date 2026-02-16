"""
Aplicación FastAPI principal del Portal Energético MME

Proporciona API RESTful para:
- Métricas energéticas (generación, demanda, disponibilidad, etc.)
- Predicciones ML (Prophet, ARIMA, Ensemble)
- Análisis con IA
- Datos hidrológicos

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import logging
from typing import Dict, Any
from datetime import datetime

from core.config import settings
from api.v1 import api_router_v1

# Configurar logging
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestión del ciclo de vida de la aplicación
    
    Args:
        app: Instancia de FastAPI
        
    Yields:
        None: Control durante el tiempo de vida de la app
    """
    # Startup
    logger.info("🚀 Iniciando API RESTful del Portal Energético MME")
    logger.info(f"📊 Entorno: {settings.DASH_ENV}")
    logger.info(f"🔑 Seguridad API Key: {'Activada' if settings.API_KEY_ENABLED else 'Desactivada'}")
    
    yield
    
    # Shutdown
    logger.info("🛑 Cerrando API RESTful del Portal Energético MME")


# Crear aplicación FastAPI
app = FastAPI(
    title="Portal Energético MME - API",
    description="API RESTful para acceso a datos del sector energético colombiano",
    version="1.0.0",
    docs_url=None,  # Deshabilitamos el automático para usar uno personalizado
    redoc_url=None,  # Deshabilitamos el automático para usar uno personalizado
    openapi_url="/openapi.json",
    lifespan=lifespan,
    root_path="/api",  # Para proxy reverso nginx
)

# Forzar OpenAPI 3.0.3 para compatibilidad con Swagger UI
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.openapi.utils import get_openapi
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Forzar versión 3.0.3 en lugar de 3.1.0
    openapi_schema["openapi"] = "3.0.3"
    
    # Servidor base para que Swagger "Try it out" use /api como prefijo
    openapi_schema["servers"] = [
        {"url": "/api", "description": "Portal Energético MME - API"}
    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Agregar rate limiter al estado de la app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ═══════════════════════════════════════════════════════════
# MIDDLEWARE - CORS
# ═══════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
)

# ═══════════════════════════════════════════════════════════
# EXCEPTION HANDLERS
# ═══════════════════════════════════════════════════════════

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Maneja errores de validación de Pydantic
    
    Args:
        request: Request de FastAPI
        exc: Excepción de validación
        
    Returns:
        JSONResponse con detalles del error
    """
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Validation Error",
            "message": "Los datos proporcionados no son válidos",
            "details": errors
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Maneja excepciones no capturadas
    
    Args:
        request: Request de FastAPI
        exc: Excepción general
        
    Returns:
        JSONResponse con mensaje de error genérico
    """
    logger.error(f"Error no manejado en {request.url.path}: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "Ha ocurrido un error interno en el servidor",
            "details": str(exc) if settings.DASH_ENV == "development" else None
        }
    )


# ═══════════════════════════════════════════════════════════
# ROUTERS
# ═══════════════════════════════════════════════════════════

# Incluir router v1
# Nota: El prefix es /v1 (no /api/v1) porque nginx ya monta la app en /api/
# URL pública final: /api/v1/chatbot/orchestrator
app.include_router(api_router_v1, prefix="/v1", tags=["v1"])

# ═══════════════════════════════════════════════════════════
# ENDPOINTS RAÍZ
# ═══════════════════════════════════════════════════════════

@app.get("/", tags=["root"])
@limiter.limit("10/minute")
async def root(request: Request) -> Dict[str, Any]:
    """
    Endpoint raíz de la API
    
    Returns:
        Información básica de la API
    """
    return {
        "service": "Portal Energético MME - API",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/api/docs",
        "endpoints": {
            "health": "/api/health",
            "v1": "/api/v1",
            "chatbot_orchestrator": "/api/v1/chatbot/orchestrator",
            "swagger": "/api/docs",
            "redoc": "/api/redoc"
        }
    }


@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def custom_swagger_ui_html():
    """Swagger UI personalizado con configuración optimizada"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.11.0/swagger-ui.css">
        <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
        <title>Portal Energético MME - API Documentation</title>
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.11.0/swagger-ui-bundle.js"></script>
        <script>
        const ui = SwaggerUIBundle({
            url: '/api/openapi.json',
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout",
            syntaxHighlight: {
                theme: "monokai"
            },
            persistAuthorization: true,
            displayRequestDuration: true,
            filter: true,
            tryItOutEnabled: true
        });
        </script>
    </body>
    </html>
    """)


@app.get("/redoc", response_class=HTMLResponse, include_in_schema=False)
async def custom_redoc_html():
    """ReDoc personalizado con versión estable"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Portal Energético MME - API Documentation</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
        <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
        <style>
            body {
                margin: 0;
                padding: 0;
            }
        </style>
    </head>
    <body>
        <redoc spec-url="/api/openapi.json"></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@2.1.3/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """)


@app.get("/health", tags=["health"])
@limiter.limit("30/minute")
async def health_check(request: Request) -> Dict[str, Any]:
    """
    Health check endpoint para monitoreo
    
    Returns:
        Estado de salud de la API y servicios dependientes
    """
    from infrastructure.database.manager import db_manager
    
    # Verificar conectividad a base de datos
    db_status = "healthy"
    try:
        df = db_manager.query_df("SELECT COUNT(*) as total FROM metrics")
        db_healthy = not df.empty
        if db_healthy:
            db_status = f"healthy ({int(df.iloc[0]['total'])} metrics)"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        db_healthy = False
    
    overall_status = "healthy" if db_healthy else "degraded"
    
    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "environment": settings.DASH_ENV,
        "services": {
            "database": db_status,
            "api": "healthy"
        }
    }


# ═══════════════════════════════════════════════════════════
# MAIN - Para desarrollo local
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    from datetime import datetime
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=settings.API_PORT,
        reload=settings.DASH_ENV == "development",
        log_level="info"
    )

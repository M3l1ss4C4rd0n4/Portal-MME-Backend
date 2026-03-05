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
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import logging
from typing import Dict, Any
from datetime import datetime

from core.config import settings
from api.v1 import api_router_v1

# Configurar logging
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# SECURITY HEADERS MIDDLEWARE
# ═══════════════════════════════════════════════════════════

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware que agrega cabeceras de seguridad HTTP a todas las respuestas.
    
    Headers:
    - X-Content-Type-Options: nosniff (previene MIME-type sniffing)
    - X-Frame-Options: DENY (previene clickjacking)
    - X-XSS-Protection: 1; mode=block (previene XSS reflejado)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: deshabilita APIs sensibles del navegador
    - Cache-Control: no-store para endpoints sensibles
    """
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        # No cachear endpoints de API por defecto
        if "/health" not in request.url.path and "/docs" not in request.url.path:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

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
# MIDDLEWARE - SECURITY HEADERS
# ═══════════════════════════════════════════════════════════

app.add_middleware(SecurityHeadersMiddleware)

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
    Health check completo: DB, Redis, XM API, frescura de datos, predicciones.
    
    Devuelve status: healthy / degraded / unhealthy con HTTP 200 / 503.
    """
    import time as _time
    from infrastructure.database.manager import db_manager
    from infrastructure.cache.redis_client import get_redis_client
    from infrastructure.external.circuit_breaker import get_xm_circuit_breaker
    
    checks = {}
    degraded = False
    unhealthy = False
    
    # ── 1. PostgreSQL ──
    try:
        t0 = _time.time()
        df = db_manager.query_df("SELECT COUNT(*) as total FROM metrics")
        db_latency_ms = round((_time.time() - t0) * 1000, 1)
        if not df.empty:
            total = int(df.iloc[0]['total'])
            checks["database"] = {
                "status": "healthy",
                "latency_ms": db_latency_ms,
                "rows": total,
            }
        else:
            checks["database"] = {"status": "unhealthy", "detail": "empty result"}
            unhealthy = True
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)[:200]}
        unhealthy = True
    
    # ── 2. Redis ──
    try:
        t0 = _time.time()
        client = get_redis_client()
        pong = client.ping()
        redis_latency_ms = round((_time.time() - t0) * 1000, 1)
        checks["redis"] = {
            "status": "healthy" if pong else "unhealthy",
            "latency_ms": redis_latency_ms,
        }
        if not pong:
            degraded = True
    except Exception as e:
        checks["redis"] = {"status": "degraded", "error": str(e)[:200]}
        degraded = True
    
    # ── 3. XM API (circuit breaker state) ──
    try:
        breaker = get_xm_circuit_breaker()
        cb_status = breaker.get_status()
        xm_state = cb_status["state"]
        checks["xm_api"] = {
            "status": "healthy" if xm_state == "closed" else (
                "degraded" if xm_state == "half_open" else "unhealthy"
            ),
            "circuit_state": xm_state,
            "consecutive_failures": cb_status["consecutive_failures"],
            "times_opened": cb_status["stats"]["times_opened"],
        }
        if xm_state == "open":
            checks["xm_api"]["seconds_until_recovery"] = cb_status["seconds_until_recovery"]
            degraded = True
    except Exception as e:
        checks["xm_api"] = {"status": "unknown", "error": str(e)[:200]}
    
    # ── 4. Data freshness ──
    try:
        df_fresh = db_manager.query_df(
            "SELECT MAX(fecha) as ultima FROM metrics"
        )
        if not df_fresh.empty and df_fresh.iloc[0]['ultima'] is not None:
            from datetime import datetime as _dt
            ultima = df_fresh.iloc[0]['ultima']
            if isinstance(ultima, str):
                ultima = _dt.strptime(ultima[:10], '%Y-%m-%d')
            hours_since = round((_dt.now() - _dt.combine(ultima, _dt.min.time())).total_seconds() / 3600, 1) \
                if not isinstance(ultima, _dt) else round((_dt.now() - ultima).total_seconds() / 3600, 1)
            checks["data_freshness"] = {
                "status": "healthy" if hours_since < 48 else "degraded",
                "last_date": str(ultima)[:10],
                "hours_since_update": hours_since,
            }
            if hours_since >= 48:
                degraded = True
        else:
            checks["data_freshness"] = {"status": "unknown"}
    except Exception as e:
        checks["data_freshness"] = {"status": "unknown", "error": str(e)[:200]}
    
    # ── 5. Predictions ──
    try:
        df_pred = db_manager.query_df(
            "SELECT COUNT(*) as total FROM predictions"
        )
        if not df_pred.empty:
            checks["predictions"] = {
                "status": "healthy",
                "total": int(df_pred.iloc[0]['total']),
            }
        else:
            checks["predictions"] = {"status": "unknown"}
    except Exception:
        checks["predictions"] = {"status": "not_available"}
    
    # ── Overall ──
    if unhealthy:
        overall = "unhealthy"
        http_code = 503
    elif degraded:
        overall = "degraded"
        http_code = 200
    else:
        overall = "healthy"
        http_code = 200
    
    result = {
        "status": overall,
        "timestamp": datetime.now().isoformat(),
        "environment": settings.DASH_ENV,
        "version": "1.0.0",
        "services": checks,
    }
    
    return JSONResponse(content=result, status_code=http_code)


@app.get("/health/live", tags=["health"])
@limiter.limit("60/minute")
async def health_live(request: Request) -> Dict[str, str]:
    """Liveness probe — la API está viva"""
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
@limiter.limit("30/minute")
async def health_ready(request: Request) -> JSONResponse:
    """Readiness probe — DB y Redis conectados"""
    from infrastructure.database.manager import db_manager
    from infrastructure.cache.redis_client import get_redis_client
    
    ready = True
    details = {}
    
    try:
        db_manager.query_df("SELECT 1")
        details["database"] = "ok"
    except Exception as e:
        details["database"] = f"error: {str(e)[:100]}"
        ready = False
    
    try:
        get_redis_client().ping()
        details["redis"] = "ok"
    except Exception as e:
        details["redis"] = f"error: {str(e)[:100]}"
        ready = False
    
    return JSONResponse(
        content={"ready": ready, "checks": details},
        status_code=200 if ready else 503
    )


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

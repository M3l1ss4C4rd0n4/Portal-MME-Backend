"""
SIEA Backend API - FastAPI Application
Sistema Integrado de Energía y Análisis
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
from dotenv import load_dotenv

from database import get_db, test_connection

# Cargar variables de entorno
load_dotenv()

# Crear aplicación FastAPI
app = FastAPI(
    title="SIEA API",
    description="Sistema Integrado de Energía y Análisis - API Backend",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configurar CORS
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8050").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Evento al iniciar la aplicación"""
    print("🚀 Iniciando SIEA Backend...")
    test_connection()
    print("✅ SIEA Backend listo")

@app.get("/")
async def root():
    """Endpoint raíz"""
    return {
        "message": "SIEA API - Sistema Integrado de Energía y Análisis",
        "version": "0.1.0",
        "status": "operacional",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Verificación de salud del sistema"""
    try:
        # Probar conexión a base de datos
        result = db.execute(text("SELECT 1"))
        result.fetchone()
        
        # Verificar schemas
        schemas_result = db.execute(text("""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name IN ('xm', 'sui', 'creg', 'dane', 'upme', 'analytics')
            ORDER BY schema_name
        """))
        schemas = [row[0] for row in schemas_result.fetchall()]
        
        return {
            "status": "healthy",
            "database": "connected",
            "schemas": schemas,
            "schemas_count": len(schemas)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }

@app.get("/api/v1/info")
async def api_info():
    """Información de la API"""
    return {
        "api": "SIEA",
        "version": "0.1.0",
        "modules": {
            "xm": "Datos de mercado eléctrico (XM)",
            "sui": "Datos de servicios públicos (SUI)",
            "creg": "Datos de regulación (CREG)",
            "dane": "Datos estadísticos (DANE)",
            "upme": "Datos de planificación energética (UPME)",
            "analytics": "Análisis y métricas calculadas"
        },
        "features": {
            "etl": "Extracción, transformación y carga de datos",
            "api": "API RESTful para acceso a datos",
            "dashboard": "Dashboard interactivo (Dash/Plotly)",
            "ia": "Agente de IA conversacional (próximamente)",
            "whatsapp": "Integración con WhatsApp (próximamente)"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

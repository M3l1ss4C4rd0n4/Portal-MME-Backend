"""
API v1 del Portal Energético MME

Agrupa todos los routers de la versión 1 de la API:
- Generación eléctrica
- Hidrología y embalses
- Transmisión
- Distribución
- Sistema (demanda, precios)
- Comercial
- Pérdidas de energía
- Restricciones operativas
- Métricas energéticas
- Predicciones ML

Autor: Arquitectura Dashboard MME
Fecha: 5 de febrero de 2026
"""

from fastapi import APIRouter

from api.v1.routes import (
    generation,
    hydrology,
    transmission,
    distribution,
    system,
    commercial,
    losses,
    restrictions,
    metrics,
    predictions,
    chatbot,
    whatsapp_alerts,
    cu,
    simulation,
)

# Router principal de v1
api_router_v1 = APIRouter()

# Incluir sub-routers - Endpoints principales del sistema

# 1. Generación eléctrica
api_router_v1.include_router(
    generation.router,
    prefix="/generation",
    tags=["🔌 Generación Eléctrica"]
)

# 2. Hidrología y embalses
api_router_v1.include_router(
    hydrology.router,
    prefix="/hydrology",
    tags=["💧 Hidrología"]
)

# 3. Sistema (demanda, precios bolsa)
api_router_v1.include_router(
    system.router,
    prefix="/system",
    tags=["⚡ Sistema Eléctrico"]
)

# 4. Transmisión
api_router_v1.include_router(
    transmission.router,
    prefix="/transmission",
    tags=["🔌 Transmisión"]
)

# 5. Distribución
api_router_v1.include_router(
    distribution.router,
    prefix="/distribution",
    tags=["🏘️ Distribución"]
)

# 6. Comercial (precios contratos)
api_router_v1.include_router(
    commercial.router,
    prefix="/commercial",
    tags=["💰 Comercial"]
)

# 7. Pérdidas de energía
api_router_v1.include_router(
    losses.router,
    prefix="/losses",
    tags=["📉 Pérdidas"]
)

# 8. Restricciones operativas
api_router_v1.include_router(
    restrictions.router,
    prefix="/restrictions",
    tags=["⚠️ Restricciones"]
)

# 9. Métricas generales (legacy)
api_router_v1.include_router(
    metrics.router,
    prefix="/metrics",
    tags=["📊 Métricas"]
)

# 10. Predicciones ML
api_router_v1.include_router(
    predictions.router,
    prefix="/predictions",
    tags=["🤖 Predicciones ML"]
)

# 11. Chatbot Orquestador
api_router_v1.include_router(
    chatbot.router,
    prefix="/chatbot",
    tags=["🤖 Chatbot"]
)

# 12. WhatsApp Alerts (integración con bot de Oscar)
api_router_v1.include_router(
    whatsapp_alerts.router,
    prefix="/whatsapp",
    tags=["📱 WhatsApp Alerts"]
)

# 13. Costo Unitario (CU) de energía eléctrica
api_router_v1.include_router(
    cu.router,
    prefix="/cu",
    tags=["💰 Costo Unitario"]
)

# 14. Motor de Simulación CREG
api_router_v1.include_router(
    simulation.router,
    prefix="/simulation",
    tags=["🔬 Simulación CREG"]
)

__all__ = ["api_router_v1"]

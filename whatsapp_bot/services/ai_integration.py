"""
AI Integration - Integración con el AI Agent del portal
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

# Agregar el directorio padre al path
server_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(server_path))

logger = logging.getLogger(__name__)


class AIIntegration:
    """
    Wrapper del AI Agent actual del portal para uso en WhatsApp bot
    """
    
    def __init__(self):
        """Inicializa la integración con el AI Agent"""
        try:
            # Importar el AgentIA del proyecto principal
            from domain.services.ai_service import AgentIA
            self.agent = AgentIA()
            logger.info("✅ AIIntegration inicializado con AgentIA del portal")
        except ImportError as e:
            logger.warning(f"⚠️ No se pudo importar AgentIA: {e}")
            logger.warning("⚠️ AIIntegration funcionará en modo mock")
            self.agent = None
    
    async def analyze_question(
        self,
        question: str,
        context: Optional[Dict] = None
    ) -> str:
        """
        Analiza pregunta usando el AI Agent del portal
        
        Args:
            question: Pregunta del usuario
            context: Contexto adicional (opcional)
        
        Returns:
            Respuesta del análisis IA
        """
        if not self.agent:
            return self._mock_ai_response(question)
        
        try:
            # AgentIA usa chat_interactivo (no analizar_pregunta_usuario).
            # AgentIA.completar() usa el SDK openai síncrono internamente
            # (con failover real Gemini→Groq desde 2026-08-22, ver
            # infrastructure/ml/llm_failover.py) — se despacha en un
            # hilo aparte (asyncio.to_thread) para no bloquear el event loop
            # de este worker mientras la IA responde (mismo bug ya corregido
            # en el Asistente IA del portal principal, ver asistente_ia_service.py).
            response = await asyncio.to_thread(
                self.agent.chat_interactivo,
                pregunta=question,
            )

            return response
        
        except Exception as e:
            logger.error(f"Error en análisis IA: {str(e)}")
            
            # Si es error de rate limit
            if "429" in str(e) or "rate limit" in str(e).lower():
                raise Exception("Rate limit exceeded")
            
            return "❌ Error procesando análisis con IA. Por favor intenta de nuevo."
    
    async def analyze_demand(self, period: str = "última semana") -> str:
        """
        Analiza patrones de demanda
        """
        if not self.agent:
            return self._mock_demand_analysis()
        
        try:
            return await asyncio.to_thread(self.agent.analizar_demanda, periodo=period)
        except Exception as e:
            logger.error(f"Error analizando demanda: {str(e)}")
            return "❌ Error analizando demanda."
    
    async def analyze_generation(self) -> str:
        """
        Analiza generación actual
        """
        if not self.agent:
            return self._mock_generation_analysis()
        
        try:
            return await asyncio.to_thread(self.agent.analizar_generacion)
        except Exception as e:
            logger.error(f"Error analizando generación: {str(e)}")
            return "❌ Error analizando generación."
    
    async def detect_anomalies(self) -> Dict:
        """
        Detecta anomalías en el sistema
        """
        if not self.agent:
            return {"has_anomalies": False, "description": "Mock mode"}
        
        try:
            # AgentIA expone detectar_alertas() (no detectar_anomalias, que
            # nunca existió en esa clase — AttributeError silencioso en cada
            # llamada, absorbido por este except; corregido de paso, aunque
            # hoy nada en el bot invoca detect_anomalies()).
            return await asyncio.to_thread(self.agent.detectar_alertas)
        except Exception as e:
            logger.error(f"Error detectando anomalías: {str(e)}")
            return {
                "has_anomalies": False,
                "error": str(e)
            }
    
    # ═══════════════════════════════════════════════════════════
    # Mock Responses (cuando no hay AI Agent disponible)
    # ═══════════════════════════════════════════════════════════
    
    def _mock_ai_response(self, question: str) -> str:
        """Respuesta mock cuando no hay AI disponible"""
        return f"""🤖 **Análisis IA** (modo demo)

Tu pregunta: "{question}"

El servicio de IA no está configurado. Para habilitar análisis inteligentes:

1. Configura GROQ_API_KEY en .env
2. Reinicia el servicio

Mientras tanto, puedes consultar datos directos con:
• "precio" - Precio de bolsa
• "generacion" - Generación actual"""
    
    def _mock_demand_analysis(self) -> str:
        """Análisis mock de demanda"""
        return """📊 **Análisis de Demanda** (modo demo)

La demanda eléctrica muestra un comportamiento estable con picos durante horas valle.

*Este es un análisis de ejemplo. Configura GROQ_API_KEY para análisis reales.*"""
    
    def _mock_generation_analysis(self) -> str:
        """Análisis mock de generación"""
        return """⚡ **Análisis de Generación** (modo demo)

La generación hidráulica domina el mix energético nacional.

*Este es un análisis de ejemplo. Configura GROQ_API_KEY para análisis reales.*"""

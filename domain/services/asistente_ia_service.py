"""
Asistente IA de página completa — Fase 9 (Palantir-IA).

Chat libre real: el usuario escribe cualquier pregunta y un LLM con tool-calling
(Groq, mismo modelo que ya usa domain/services/ai_service.py) decide qué
herramienta(s) del orquestador invocar según la pregunta real — en vez de la
cascada fija de palabras clave que usa domain/services/orchestrator/handlers/
libre_noticias_handler.py::_handle_pregunta_libre.

No reimplementa ninguna lógica de negocio: cada herramienta es un intent que
YA EXISTE en el orquestador (domain/services/orchestrator/orchestrator_service.py),
ejecutado tal cual mediante orchestrate(). Esta capa solo traduce entre el
formato de tool-calling del LLM y el formato {sessionId, intent, parameters}
del orquestador, y transmite la respuesta final en streaming.

100% lectura/análisis — ninguna tool expone escritura sobre contratos u otros
datos de negocio.
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List
from uuid import uuid4

from core.config import settings
from domain.schemas.orchestrator import OrchestratorRequest

logger = logging.getLogger(__name__)

MAX_ITERACIONES_TOOLS = 4
MAX_TURNOS_HISTORIAL = 10  # últimos N mensajes del historial enviado por el cliente

SYSTEM_PROMPT = (
    "Eres el Asistente IA del Portal del Ministerio de Minas y Energía de Colombia. "
    "Respondes preguntas en lenguaje natural usando EXCLUSIVAMENTE los datos que "
    "obtienes llamando a las herramientas disponibles — nunca inventes cifras, "
    "nombres de contratos, empresas ni fechas que no vengan de una herramienta.\n"
    "Si una pregunta requiere datos que ninguna herramienta puede darte, dilo "
    "explícitamente en vez de adivinar.\n"
    "Responde en español, de forma clara y concisa, citando la fuente cuando "
    "corresponda (ej. 'según el informe de seguimiento de PMO...', "
    "'según el contrato con NIT...').\n"
    "Este es un sistema 100% de análisis/consulta — nunca sugieras que puedes "
    "aprobar, rechazar, modificar o ejecutar ninguna acción sobre contratos.\n"
    "Llama las herramientas que necesites (puedes llamar varias en cadena, "
    "usando el resultado de una para armar los parámetros de la siguiente) "
    "hasta tener todo lo necesario para responder — nunca describas en texto "
    "un plan de qué herramienta llamarías, llámala directamente. Nunca "
    "menciones el nombre de una herramienta que no te haya sido dada."
)

# Catálogo de tools — cada una mapea 1:1 a un intent que ya existe en
# ChatbotOrchestratorService._get_intent_handler(). Ver domain/services/
# orchestrator/orchestrator_service.py:188 para la lista completa de intents;
# este catálogo expone un subconjunto curado, útil para preguntas abiertas.
TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "resumen_departamento",
            "description": (
                "Vista 360 de un departamento colombiano: cruza comunidades "
                "energéticas, contratos OR, FENOGE, Colombia Solar, subsidios y "
                "supervisión. Úsala cuando la pregunta mencione un departamento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "departamento": {"type": "string", "description": "Nombre del departamento, ej. 'Chocó'"},
                },
                "required": ["departamento"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_texto_rag",
            "description": (
                "Búsqueda semántica sobre observaciones/objeto de contratos de "
                "supervisión Y sobre informes reales (PDF/PPTX/DOCX) de SharePoint: "
                "seguimiento de Comunidades Energéticas, actas de ELECTROCAQUETA, "
                "alertas del sector eléctrico, boletín e informes diarios de XM. "
                "Úsala para preguntas sobre contenido narrativo/informes, no para "
                "conteos o KPIs estructurados."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Consulta en lenguaje natural"},
                    "top_k": {"type": "integer", "description": "Máximo de resultados (default 5)"},
                },
                "required": ["consulta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_empresa",
            "description": "Busca una empresa/prestador/ejecutor por NIT o nombre/sigla.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre o sigla, ej. 'GENSA'"},
                    "nit": {"type": "string", "description": "NIT exacto"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vecindario_empresa",
            "description": (
                "Grafo de relaciones de una empresa: contratos verificados, proyectos, "
                "geografía donde opera, y otras empresas en las mismas zonas. Requiere "
                "primero obtener el empresa_id con buscar_empresa."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "empresa_id": {"type": "integer", "description": "Id obtenido con buscar_empresa"},
                },
                "required": ["empresa_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "riesgo_atraso_contratos_or",
            "description": "Ranking de contratos OR por riesgo de atraso, mayor riesgo primero.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Máximo de contratos (default 10)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_proyectos",
            "description": "Lista proyectos de contratos OR, Colombia Solar o FENOGE.",
            "parameters": {
                "type": "object",
                "properties": {
                    "programa": {
                        "type": "string",
                        "enum": ["contratos_or", "colombia_solar", "fenoge"],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generacion_electrica",
            "description": "Datos de generación eléctrica del sistema colombiano.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hidrologia",
            "description": "Niveles de embalses e hidrología del sistema eléctrico.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "demanda_sistema",
            "description": "Demanda eléctrica del sistema colombiano.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "precio_bolsa",
            "description": "Precio de bolsa de energía eléctrica.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cu_actual",
            "description": "Costo unitario (CU) actual de energía.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "perdidas_nt",
            "description": "Estadísticas de pérdidas no técnicas (PNT) de energía.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comunidades_implementadas",
            "description": "KPIs de Comunidades Energéticas implementadas (conteos, capacidad, inversión).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "contratos_or_menu",
            "description": "Resumen de contratos OR (Operadores de Red).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fenoge_menu",
            "description": "Resumen del programa FENOGE (1.0 y 1.1).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "colombia_solar_menu",
            "description": "Resumen del programa Colombia Solar.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "supervision_menu",
            "description": "Resumen de supervisión de contratos.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "presupuesto_menu",
            "description": "Resumen de ejecución presupuestal.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_menu",
            "description": "Resumen de subsidios (déficit, pagos, validaciones).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "anomalias_detectadas",
            "description": "Anomalías/alertas detectadas actualmente en el sector eléctrico.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _get_groq_client():
    from openai import OpenAI
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY no configurada — el Asistente IA requiere un proveedor de IA")
    return OpenAI(base_url=settings.GROQ_BASE_URL, api_key=settings.GROQ_API_KEY)


async def _ejecutar_tool(nombre: str, argumentos: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce una tool-call del LLM a un intent existente del orquestador y lo ejecuta."""
    from core.container import container

    orchestrator = container.get_orchestrator_service()
    request = OrchestratorRequest(
        sessionId=f"asistente-{uuid4().hex[:16]}",
        intent=nombre,
        parameters=argumentos or {},
    )
    response = await orchestrator.orchestrate(request)
    if response.status == "ERROR":
        return {"error": response.message, "detalle": [e.message for e in response.errors]}
    return response.data


def _sse(evento: Dict[str, Any]) -> str:
    return f"data: {json.dumps(evento, ensure_ascii=False, default=str)}\n\n"


async def responder_stream(mensaje: str, historial: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    """
    Genera la respuesta del Asistente en streaming (formato SSE).

    historial: lista de {role: 'user'|'assistant', content: str} de turnos previos,
    enviada completa por el cliente en cada request (sin memoria server-side —
    mismo patrón stateless que domain/services/ai_service.py::AgentIA).
    """
    client = _get_groq_client()

    mensajes: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    mensajes.extend(historial[-MAX_TURNOS_HISTORIAL:])
    mensajes.append({"role": "user", "content": mensaje})

    try:
        for _ in range(MAX_ITERACIONES_TOOLS):
            try:
                resp = client.chat.completions.create(
                    model=settings.AI_MODEL,
                    messages=mensajes,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.2,  # decisión de qué tool llamar debe ser consistente, no creativa
                )
            except Exception as e:
                # Groq/Llama a veces emite una sintaxis de tool-call mal formada
                # como texto plano en vez de la estructura nativa esperada, y la
                # API responde 400 ("tool_use_failed") en vez de un mensaje normal.
                # Degradación con gracia: se trata como "sin más tools" y se
                # sintetiza la respuesta final con los datos ya obtenidos, en vez
                # de tumbar toda la conversación por una falla intermitente del
                # parser de function-calling.
                logger.warning(f"[ASISTENTE] Llamada de tool-calling falló, se corta el loop: {e}")
                break
            msg = resp.choices[0].message

            if not msg.tool_calls:
                # No pide más tools: no se agrega este content (generado sin
                # streaming) — se descarta a propósito y se re-genera la
                # respuesta final abajo CON streaming, para que el usuario la
                # vea aparecer palabra por palabra. Agregarlo aquí produciría
                # dos mensajes "assistant" consecutivos sin turno de usuario
                # entre ellos, confundiendo al modelo en la llamada siguiente.
                break

            mensajes.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                nombre = tc.function.name
                try:
                    argumentos = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    argumentos = {}
                yield _sse({"tool": nombre})
                try:
                    resultado = await _ejecutar_tool(nombre, argumentos)
                except Exception as e:
                    logger.error(f"[ASISTENTE] Tool '{nombre}' falló: {e}")
                    resultado = {"error": f"La herramienta '{nombre}' falló: {e}"}
                mensajes.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(resultado, ensure_ascii=False, default=str)[:8000],
                })
        else:
            logger.warning("[ASISTENTE] Se alcanzó el tope de iteraciones de tool-calling")

        # Síntesis final en streaming — sin tools, para forzar texto en lenguaje natural.
        stream = client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=mensajes,
            stream=True,
            temperature=0.3,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse({"delta": delta})

        yield _sse({"done": True})

    except Exception as e:
        logger.error(f"[ASISTENTE] Error generando respuesta: {e}")
        yield _sse({"error": "Ocurrió un error generando la respuesta. Intenta de nuevo."})
        yield _sse({"done": True})

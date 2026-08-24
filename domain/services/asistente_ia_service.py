"""
Asistente IA de página completa — Fase 9 (Palantir-IA).

Chat libre real: el usuario escribe cualquier pregunta y un LLM con tool-calling
(Gemini, vía su endpoint compatible con el SDK openai — ver _get_llm_client())
decide qué herramienta(s) del orquestador invocar según la pregunta real — en
vez de la cascada fija de palabras clave que usa domain/services/orchestrator/
handlers/libre_noticias_handler.py::_handle_pregunta_libre.

No reimplementa ninguna lógica de negocio: cada herramienta es un intent que
YA EXISTE en el orquestador (domain/services/orchestrator/orchestrator_service.py),
ejecutado tal cual mediante orchestrate(). Esta capa solo traduce entre el
formato de tool-calling del LLM y el formato {sessionId, intent, parameters}
del orquestador, y transmite la respuesta final en streaming.

100% lectura/análisis — ninguna tool expone escritura sobre contratos u otros
datos de negocio.
"""

import asyncio
import json
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from uuid import uuid4

import openai

from core.config import settings
from domain.schemas.orchestrator import OrchestratorRequest
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

MAX_ITERACIONES_TOOLS = 4
MAX_TURNOS_HISTORIAL = 10  # últimos N mensajes del historial enviado por el cliente

# Fase 38 (2026-08-22): presupuesto dinámico de `buscar_texto_rag` dentro de
# un mismo turno — reproducido en vivo que 2-3 llamadas sucesivas a esta tool
# en el mismo turno hacían crecer el prompt hasta chocar con el tope de
# 8.000 TPM de la cuenta gratuita de Groq (en AMBOS modelos del failover,
# confirmando que es un límite de cuenta, no de modelo). En vez de recortar
# de menos información en general, se aprieta solo cuando el turno ya
# acumuló mucho Y el proveedor activo es Groq — Gemini tiene ~20x más
# margen (Fase 10) y no necesita este freno.
#
# CHARS_POR_TOKEN_TOOL_RESULT calibrado con datos reales, no con el chars/4
# genérico: un presupuesto de 5.500 caracteres de 'contenido' produce un
# JSON real de ~8.100 caracteres (claves/comillas/similitud/nombre_archivo/
# chunk_index/tema/fecha_documento por resultado, ~48% de overhead sobre el
# texto puro) que a su vez se suma como ~2.230 tokens al prompt de la
# siguiente llamada (medido: 4.939→7.168) — la relación real es ~2,5
# caracteres de PRESUPUESTO por cada token que termina sumándose al turno,
# no los 4 que asumiría una cuenta ingenua de caracteres del propio texto.
TECHO_TOKENS_TURNO_GROQ = 6500
# 2026-08-22, hallazgo en producción real (reportado por el usuario): el
# botón "Predicciones del portal y simulaciones de XM" necesita 2 búsquedas
# RAG distintas (corto plazo + mediano/largo plazo) y agotaba los 3
# proveedores de forma consistente mientras la red a Gemini seguía
# bloqueada. Causa raíz: 'groq_backup' (qwen/qwen3.6-27b) tokeniza el MISMO
# texto (system prompt + catálogo de tools + pregunta) ~33% más grande que
# 'groq' (gpt-oss-120b) — reproducido en vivo 3 veces: 6.000-6.125 tokens de
# línea base contra 4.522-4.690 de gpt-oss-120b para contenido idéntico. Eso
# le deja a groq_backup solo ~1.875-2.000 tokens reales de margen bajo el
# mismo tope de 8.000 ANTES de la primera tool, contra ~3.300-3.500 de
# gpt-oss-120b — ni el piso mínimo (antes 1200 chars) alcanzaba a caber ahí
# una vez sumado el overhead de JSON. Techo específico y más bajo para
# groq_backup, y piso general bajado — un techo único no puede servir a la
# vez a un modelo con casi el doble de margen real que el otro.
TECHO_TOKENS_TURNO_GROQ_BACKUP = 5200
CHARS_POR_TOKEN_TOOL_RESULT = 2.5
PRESUPUESTO_CHARS_PISO = 700
PRESUPUESTO_CHARS_TECHO = 5500  # = comportamiento actual (sin este mecanismo)

# Estado por turno (turno_id -> {"tokens_acumulados", "proveedor", "chunks_vistos"}),
# usado solo por `_resolver_tool_calls()`/`_ejecutar_una()` para calcular el
# presupuesto dinámico y deduplicar chunks repetidos entre llamadas
# sucesivas de `buscar_texto_rag` en el mismo turno. Se limpia al final de
# cada turno (éxito o error) en responder_stream()/responder_completo() —
# cada turno_id es único (uuid4), sin riesgo de colisión entre requests
# concurrentes del mismo proceso.
_estado_turno: Dict[str, Dict[str, Any]] = {}

SYSTEM_PROMPT = (
    "Eres el Asistente IA del Portal del Ministerio de Minas y Energía de Colombia. "
    "Respondes preguntas en lenguaje natural usando EXCLUSIVAMENTE los datos que "
    "obtienes llamando a las herramientas disponibles — nunca inventes cifras, "
    "nombres de contratos, empresas ni fechas que no vengan de una herramienta.\n"
    "Si el usuario adjunta una imagen o un PDF, SÍ puedes verlo y describirlo "
    "directamente (tienes visión nativa) — analízalo tú mismo, sin necesitar "
    "ninguna herramienta para eso. La restricción de 'solo datos de herramientas' "
    "aplica a cifras/nombres/fechas del negocio del ministerio, no al contenido "
    "de un archivo que el usuario mismo adjuntó.\n"
    "Si una pregunta requiere datos que ninguna herramienta puede darte, dilo "
    "explícitamente en vez de adivinar.\n"
    "Responde en español, de forma clara y concisa, citando la fuente cuando "
    "corresponda (ej. 'según el informe de seguimiento de PMO...', "
    "'según el contrato con NIT...') — SIEMPRE en prosa normal, nunca con "
    "marcadores de cita especiales entre símbolos como 【0†L35-L45】 o "
    "similares (algunos modelos los generan por costumbre de otras "
    "plataformas; aquí no se procesan y aparecen como texto roto para el "
    "usuario).\n"
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
            "name": "resumen_municipio",
            "description": (
                "Vista 360 de un municipio colombiano (Fase 13): mismo cruce que "
                "resumen_departamento pero al grano de municipio. Úsala cuando la "
                "pregunta mencione un municipio específico, no solo un departamento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "municipio": {"type": "string", "description": "Nombre del municipio, ej. 'Quibdó'"},
                    "departamento": {
                        "type": "string",
                        "description": "Opcional — nombre del departamento, para desambiguar municipios homónimos",
                    },
                },
                "required": ["municipio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_texto_rag",
            "description": (
                "Búsqueda semántica sobre observaciones/objeto de contratos de "
                "supervisión Y sobre informes reales (PDF/PPTX/DOCX) de SharePoint "
                "y del repositorio público de XM: seguimiento de Comunidades "
                "Energéticas, actas de ELECTROCAQUETA, alertas del sector eléctrico, "
                "boletín e informes diarios de XM, y estudios de planeación de XM "
                "(corto/mediano/largo plazo, flexibilidad del SIN, senda de "
                "referencia). Úsala para preguntas sobre contenido narrativo/"
                "informes, no para conteos o KPIs estructurados. Si la pregunta "
                "encaja claramente en un tipo de informe conocido, usa el parámetro "
                "'tema' para garantizar que ese documento aparezca (en vez de "
                "depender solo de similitud)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {
                        "type": "string",
                        "description": (
                            "Consulta en lenguaje natural, como si le preguntaras a una "
                            "persona (ej. '¿qué plantas están indisponibles por "
                            "mantenimiento?'). NUNCA una lista de palabras sueltas "
                            "(ej. 'mantenimiento plantas indisponibles fuera servicio') "
                            "— degrada la calidad de la búsqueda."
                        ),
                    },
                    "top_k": {"type": "integer", "description": "Máximo de resultados (default 5)"},
                    "tema": {
                        "type": "string",
                        "enum": [
                            "despacho", "hidrologia", "operativas", "panorama_climatico",
                            "metodologia_alertas", "comunidades", "pmo_interno",
                            "colombia_solar", "subsidios", "proyectos_estrategicos",
                            "informe_empalme", "planeacion_xm", "boletin_energetico_xm",
                            "creg_normativa", "normativa_upme_mme", "publicaciones_upme",
                            "publicaciones_mme", "creg_proyectos_resolucion",
                            "mme_conceptos_juridicos",
                        ],
                        "description": (
                            # Fase 38 (2026-08-22): comprimido de 4.279 a ~2.440
                            # caracteres (formato "tema: cobertura — distinción",
                            # sin prosa conectiva) preservando cada regla de
                            # desambiguación real ya agregada tras bugs
                            # encontrados en producción (Fase 35: corto vs.
                            # mediano/largo plazo; Fase 37: proyecto en consulta
                            # ≠ norma vigente) — este bloque se reenvía completo
                            # en cada iteración del loop de tool-calling dentro
                            # de un mismo turno, así que su tamaño se paga
                            # varias veces por pregunta, no una sola.
                            "Filtro opcional por tipo de informe (usa el que mejor calce; si no calza ninguno, omite el filtro):\n"
                            "despacho: disponibilidad de plantas, precio de predespacho\n"
                            "hidrologia: aportes, embalses, vertimientos\n"
                            "operativas: importaciones/exportaciones, combustibles, FNCER\n"
                            "panorama_climatico: pronóstico El Niño/La Niña (NOAA-IDEAM)\n"
                            "metodologia_alertas: cómo se calculan los índices/umbrales del portal\n"
                            "comunidades: Comunidades Energéticas, sostenibilidad, resoluciones CE, actas ELECTROCAQUETA, esquemas de comercialización\n"
                            "pmo_interno: estructura organizacional/administrativa (rara vez relevante)\n"
                            "colombia_solar: justificación, decretos/marco regulatorio, contrato interadministrativo 2026\n"
                            "subsidios: conciliaciones Fondo SIN, exentos de contribución, focalización/STM\n"
                            "proyectos_estrategicos: interconexiones eléctricas internacionales (ej. Colombia-Panamá, Chocó)\n"
                            "informe_empalme: informe de empalme MME (mismo del botón de descarga del portal)\n"
                            "planeacion_xm: análisis energético CORTO plazo semanal de XM — AQUÍ está la simulación de embalses de corto plazo con cifra exacta; sus estudios de mediano/largo plazo son de RED/transmisión (restricciones, congestión), no de embalses\n"
                            "boletin_energetico_xm: Boletín de XM (semanal + especiales) — AQUÍ está la simulación estocástica de embalses de MEDIANO plazo con cifra exacta (aportes, HSIN, senda, riesgos). XM no publica una simulación de embalses de 'largo plazo' separada: si preguntan por largo plazo, usa este tema igual pero acláralo como mediano plazo (el mayor horizonte que XM publica), sin relabelarlo\n"
                            "creg_normativa: texto legal vigente de resoluciones/circulares CREG (incluye las que sustentan NE/HSIN/PBP/Condición del Sistema) — para contenido exacto o si una norma fue modificada/derogada\n"
                            "normativa_upme_mme: texto legal vigente de resoluciones/circulares de UPME y del Ministerio\n"
                            "publicaciones_upme: informes técnicos UPME (Plan Energético Nacional, Boletín Estadístico, estudios sectoriales) — analítico, NO normativo\n"
                            "publicaciones_mme: contenido misional del Ministerio, en particular el Plan de Expansión Generación-Transmisión\n"
                            "creg_proyectos_resolucion: proyectos de resolución CREG EN CONSULTA PÚBLICA — NO vigentes; si citas esto, acláralo como proyecto, nunca como norma vigente (para lo vigente usa creg_normativa)\n"
                            "mme_conceptos_juridicos: memorandos/interpretaciones jurídicas del Ministerio, no son norma en sí — explican el porqué de un cambio regulatorio en trámite"
                        ),
                    },
                    "campo_contrato": {
                        "type": "string",
                        "enum": [
                            "objeto_del_contrato",
                            "observaciones_dificultades_y_gestion_por_parte_del_juridico",
                            "observaciones_dificultades_y_gestion_por_parte_del_tecnico",
                            "observaciones_estado_del_inventario",
                            "observacion_juridica_frente_al_ep",
                            "observacion_alerta_de_incumplimiento",
                            "observacion_estado_de_incumplimiento",
                        ],
                        "description": (
                            "Filtro opcional equivalente a 'tema' pero para preguntas sobre "
                            "contratos de supervisión (esquema supervision.contratos): usa "
                            "'objeto_del_contrato' para qué contrata cada contrato, "
                            "'observacion_alerta_de_incumplimiento'/'observacion_estado_de_"
                            "incumplimiento' para riesgos de incumplimiento, o las variantes "
                            "'observaciones_dificultades_y_gestion_por_parte_del_juridico/tecnico' "
                            "para dificultades reportadas. No lo combines con 'tema' — cada uno "
                            "filtra un corpus distinto (informes de SharePoint vs. contratos)."
                        ),
                    },
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
                "geografía donde opera, otras empresas en las mismas zonas, y firmas de "
                "interventoría que han fiscalizado sus contratos (quién audita/interventora "
                "a quién, y cuántos contratos). Usar para preguntas sobre interventoría, "
                "fiscalización o auditoría de contratos de una empresa. Requiere primero "
                "obtener el empresa_id con buscar_empresa."
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
            "description": (
                "Lista proyectos de contratos OR, Colombia Solar o FENOGE, opcionalmente "
                "filtrados por departamento (ej. 'qué proyectos hay en La Guajira')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "programa": {
                        "type": "string",
                        "enum": ["contratos_or", "colombia_solar", "fenoge"],
                    },
                    "departamento": {
                        "type": "string",
                        "description": "Nombre del departamento, ej. 'La Guajira' (opcional)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_metrica",
            "description": (
                "Busca en el catálogo de métricas/variables del sector eléctrico "
                "(ej. 'NE', 'HSIN', 'PBP', 'embalse', 'precio de bolsa') y devuelve su "
                "definición, unidad, fuente y de qué otras métricas depende o a cuáles "
                "alimenta, con la Resolución CREG citada cuando aplica. Úsala para "
                "preguntas de tipo '¿qué es X?' o '¿de qué depende X?' sobre índices o "
                "variables del sector energético, no para consultar su valor actual."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Nombre o código técnico, ej. 'NE' o 'embalse'"},
                },
                "required": ["consulta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calidad_datos_ontologia",
            "description": (
                "Qué tan completa/confiable está la información cruzada del portal: "
                "deuda de resolución de geografía/empresas sin resolver, y si el "
                "pipeline diario de actualización de la ontología tuvo corridas con "
                "error recientemente. Úsala para preguntas de tipo '¿qué tan completos "
                "están los datos?' o '¿hay problemas actualizando la información?'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detalle_recurso",
            "description": (
                "Detalle de una planta/recurso específico del sistema eléctrico por "
                "nombre (ej. 'Cartagena 1', 'Chivor', 'Guavio'): tipo, región, "
                "capacidad, y menciones recientes reales en los informes diarios de "
                "despacho de XM (ej. si aparece indisponible/en mantenimiento). Úsala "
                "cuando la pregunta mencione una planta específica por nombre."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre o parte del nombre de la planta, ej. 'Cartagena'"},
                },
                "required": ["nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detalle_contrato",
            "description": (
                "Detalle completo de UN contrato de supervisión específico por su id "
                "(valor, avance, interventoría, geografía, estado, desembolsos). "
                "Usa el 'id' que ya aparece en los nodos de contrato devueltos por "
                "vecindario_empresa — no un código de contrato en texto libre. Úsala "
                "cuando el usuario pregunte por un contrato específico ya mencionado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contrato_id": {"type": "integer", "description": "Id del contrato (ver vecindario_empresa)"},
                },
                "required": ["contrato_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resumen_portal",
            "description": (
                "Catálogo de TODOS los tableros/páginas que tiene el portal (18 en total) "
                "y cómo se relacionan entre sí — úsala cuando la pregunta sea sobre la "
                "ESTRUCTURA del portal en general (ej. 'qué tableros hay', 'qué información "
                "maneja el portal', 'resumen de cada tablero', 'cómo se relacionan los "
                "dominios/tableros entre sí'), NUNCA para preguntas sobre datos concretos de "
                "un solo dominio (para eso usa la tool específica de ese dominio, ej. "
                "estado_actual, subsidios_deficit_historico, etc.)."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predicciones_sector",
            "description": (
                "Predicciones/proyecciones a futuro (modelo Prophet/ARIMA/Ensemble ya "
                "entrenado) de los 3 indicadores clave del sistema: generación total, "
                "precio de bolsa nacional, y porcentaje de embalses — con nivel de "
                "confianza, comparación contra el promedio real de los últimos 30 días, "
                "y tendencia. Úsala para CUALQUIER pregunta sobre el futuro: '¿qué se "
                "proyecta...?', '¿cómo estarán los embalses/precio/generación en X "
                "tiempo?', '¿hay riesgo de...?' — nunca inventes una proyección sin "
                "llamar esta herramienta primero."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "horizonte": {
                        "type": "string",
                        "enum": ["1_semana", "1_mes", "6_meses", "1_ano", "personalizado"],
                        "description": "Horizonte de la proyección (default '1_semana' si no se especifica)",
                    },
                    "fecha_personalizada": {
                        "type": "string",
                        "description": (
                            "Solo si horizonte='personalizado': fecha futura en formato "
                            "YYYY-MM-DD o DD-MM-AAAA"
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "panorama_climatico",
            "description": (
                "Índices climáticos oficiales (NOAA/NASA) que explican el riesgo "
                "hidrológico del sistema: ONI (El Niño/La Niña, actual + pronóstico "
                "mensual), PDO (ciclo oceánico de largo plazo), SOI (presión "
                "atmosférica) y GMST (anomalía de temperatura media global). Úsala "
                "para preguntas sobre El Niño/La Niña, fenómenos climáticos, o el "
                "contexto climático detrás de una proyección de embalses/hidrología "
                "— no para el valor de embalses en sí (usa predicciones_sector o "
                "hidrologia para eso)."
            ),
            "parameters": {"type": "object", "properties": {}},
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
            "name": "cu_evolucion",
            "description": (
                "Evolución histórica y pronóstico del Costo Unitario (tarifa, "
                "COP/kWh): promedio/mínimo/máximo y tendencia en un periodo pasado, "
                "más una proyección a futuro con nivel de confianza. Úsala para "
                "'¿cómo ha evolucionado la tarifa?' o '¿qué se proyecta para el CU?' "
                "— para el valor de HOY exclusivamente, usa cu_actual en su lugar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dias_historico": {"type": "integer", "description": "Días hacia atrás a resumir (default 30)"},
                    "dias_pronostico": {"type": "integer", "description": "Días hacia adelante a proyectar (default 30)"},
                },
            },
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
            "name": "subsidios_deficit_historico",
            "description": (
                "Déficit histórico del fondo de subsidios (FSSRI/FOES) de los últimos "
                "8 años: subsidios otorgados, contribuciones recaudadas, déficit anual "
                "y acumulado, apropiación PGN."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_deuda_total",
            "description": "Deuda total pendiente de pago en subsidios de energía, desglosada por fondo (FSSRI/FOES) y área (SIN/ZNI).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_deuda_empresa",
            "description": "Top empresas/prestadores con mayor deuda pendiente de subsidios.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_deuda_fondo",
            "description": "Deuda pendiente de subsidios comparada entre el fondo FSSRI y el fondo FOES, con las mayores deudas empresa×fondo.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_trimestre",
            "description": "Estado de pago de subsidios por trimestre (pagadas vs. pendientes), desglosado por fondo/área.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_pagado_anio",
            "description": "Valor pagado de subsidios por año, acumulado por fondo/área.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_pct_pagado",
            "description": "Porcentaje pagado de subsidios (global y por fondo/área), con las empresas con menor porcentaje pagado.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_resoluciones",
            "description": "Cantidad y valor de resoluciones de subsidios por año de expedición.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_estado",
            "description": "Estado global de resoluciones de subsidios (pagadas vs. pendientes), con detalle por fondo/área.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subsidios_validaciones",
            "description": (
                "Estado de validación de cuentas de subsidios DEE (SIN/ZNI): conteo de "
                "registros y prestadores por estado de validación, con fecha de corte. "
                "Usar cuando pregunten cuántas validaciones hay, en qué estado están, o "
                "cuántos prestadores tienen cuentas validadas/pendientes."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hidrocarburos_presupuesto",
            "description": (
                "Ejecución presupuestal de la Dirección de Hidrocarburos: apropiación "
                "vigente, compromisos, obligaciones y por comprometer, con detalle por "
                "proyecto. El dato tiene un corte mensual (no diario) — siempre cita la "
                "fecha de corte que trae la herramienta, puede tener varias semanas."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hidrocarburos_produccion",
            "description": (
                "Producción diaria de petróleo y gas (fiscalizado/comercializado, con la "
                "brecha entre ambos), precios de referencia WTI/Brent, y ranking de "
                "campos productores. WTI/Brent se actualiza a diario; producción tiene "
                "un corte de varios días — cita ambas fechas por separado, no las mezcles."
            ),
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
    {
        "type": "function",
        "function": {
            "name": "estado_actual",
            "description": (
                "Estado general del sistema eléctrico AHORA MISMO: los 3 KPIs clave "
                "(generación total, precio de bolsa, % de embalses) con su tendencia "
                "frente al promedio de los últimos 7 días. Úsala para preguntas "
                "genéricas de 'cómo está el sistema/sector' cuando no apunten a un "
                "indicador específico — es el punto de partida más natural."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "noticias_sector",
            "description": (
                "Noticias RECIENTES/ACTUALES del sector energético colombiano "
                "(multi-fuente: prensa, medios especializados; con resumen). "
                "Úsala para preguntas sobre QUÉ ESTÁ PASANDO AHORA o eventos "
                "recientes — ej. 'por qué está pasando X', 'qué se dijo sobre Y "
                "esta semana', exportaciones/decisiones/anuncios recientes. "
                "DIFERENTE de 'buscar_texto_rag': esa es para el contenido de "
                "informes/documentos ya archivados (técnicos, regulatorios), "
                "no para noticias de actualidad/prensa del día."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "noticias_hidrocarburos",
            "description": (
                "Noticias RECIENTES/ACTUALES de hidrocarburos (petróleo, gas, "
                "carbón, minería) en Colombia. Úsala para preguntas sobre QUÉ "
                "ESTÁ PASANDO AHORA o eventos recientes en ese sector — mismo "
                "criterio que 'noticias_sector' pero para hidrocarburos. "
                "DIFERENTE de 'buscar_texto_rag': esa es para informes/documentos "
                "archivados, no para noticias de actualidad."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulacion",
            "description": (
                "Simula el impacto de un escenario regulatorio/operativo sobre el "
                "Costo Unitario (CU) — ej. una sequía, expansión de renovables, o "
                "reducción de pérdidas técnicas. Úsala para preguntas tipo '¿qué "
                "pasaría con la tarifa si...?'. Si la pregunta no especifica un "
                "escenario claro, la herramienta devuelve los escenarios disponibles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pregunta": {
                        "type": "string",
                        "description": "La pregunta del usuario tal cual, ej. '¿qué pasa con la tarifa si hay una sequía fuerte?'",
                    },
                },
                "required": ["pregunta"],
            },
        },
    },
]


def _get_llm_client(base_url: str, api_key: str):
    """
    Cliente ASÍNCRONO (AsyncOpenAI) a propósito, no el sync `OpenAI` que se
    usaba antes: portal-api.service corre un solo worker uvicorn, y una llamada
    síncrona bloqueante dentro de una función async congela el event loop
    completo — afecta a TODO el portal, no solo al Asistente. Se confirmó en
    vivo durante la verificación de la Fase 20 (2026-08-05): una llamada lenta
    por rate-limit de Gemini coincidió con un reinicio abrupto de
    portal-api.service sin secuencia de apagado ordenada. Mismo patrón ya
    usado correctamente en energia_app.py::_narrar_para_audio y
    tasks/push_tasks.py.
    """
    from openai import AsyncOpenAI
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def _proveedores_disponibles() -> List[Tuple[str, str, str, str]]:
    """Fase 28 — lista (nombre, base_url, api_key, modelo) en orden de
    prioridad para el failover real ante rate-limit. Gemini primero (Fase 10:
    20x más TPM que Groq, sin tope diario aparte); Groq solo se agrega si hay
    key configurada — es el mismo modelo/loop que ya corrió en producción
    antes de la Fase 10 (ver comentario sobre el bug de tool-calling mal
    formado de Groq/Llama más abajo), así que reactivarlo como respaldo no es
    territorio nuevo, solo dejó de usarse como primario.

    A diferencia de `AgentIA` (ai_service.py), que elige proveedor UNA SOLA
    VEZ al construirse y nunca reintenta con otro si el elegido falla en
    tiempo de ejecución (falso "fallback" — solo mejora el mensaje de error),
    aquí la lista se recorre en cada turno hasta que uno responda o se agoten
    todos.

    2026-08-22: se agrega un 3er escalón, Groq con un segundo modelo
    (GROQ_MODEL_BACKUP) — protege contra que Groq descontinúe/tenga una
    caída puntual del modelo principal. NO resuelve el tope de 8.000 TPM de
    la cuenta gratuita para preguntas con contexto RAG pesado (verificado en
    vivo que gpt-oss-120b y qwen3.6-27b comparten el mismo tope con el mismo
    prompt) — para eso, el respaldo real es el presupuesto dinámico/guardia
    de `buscar_texto_rag` (ver constantes al inicio del módulo).

    2026-08-22 (mismo día, tras un caso real en producción): se agrega un
    4to escalón, OpenRouter (OPENROUTER_BACKUP_MODEL) — el mismo día en que
    se diseñaron los escalones 2-3, ambos modelos de Groq se quedaron sin
    cupo DIARIO (no solo por minuto) a la vez, dejando el Asistente sin
    ningún proveedor disponible. OpenRouter tiene cuota totalmente
    independiente de Groq. Verificado en vivo que el modelo configurado
    (nvidia/nemotron-3-super-120b-a12b:free) hace tool-calling correcto con
    el catálogo real de 44 tools. Limitación real, no oculta: el tier
    gratuito de OpenRouter sin créditos comprados permite solo 50
    requests/día compartidas entre todos los modelos ':free' (no es un
    límite de tokens) — un solo turno con varias iteraciones de tool-calling
    puede consumir varias de esas 50, así que es un último recurso genuino,
    no un reemplazo sostenido de Groq."""
    candidatos = [
        ("gemini", settings.GEMINI_BASE_URL, settings.GEMINI_API_KEY, settings.GEMINI_MODEL),
        ("groq", settings.GROQ_BASE_URL, settings.GROQ_API_KEY, settings.AI_MODEL),
        ("groq_backup", settings.GROQ_BASE_URL, settings.GROQ_API_KEY, settings.GROQ_MODEL_BACKUP),
        ("openrouter", settings.OPENROUTER_BASE_URL, settings.OPENROUTER_API_KEY, settings.OPENROUTER_BACKUP_MODEL),
    ]
    disponibles = [p for p in candidatos if p[2]]
    if not disponibles:
        raise RuntimeError(
            "Ningún proveedor de IA configurado (GEMINI_API_KEY/GROQ_API_KEY) "
            "— el Asistente IA requiere al menos uno"
        )
    return disponibles


def _es_error_de_disponibilidad(e: Exception) -> bool:
    """True si el error indica que ESE proveedor/modelo no está disponible
    ahora mismo (cuota agotada, red, modelo descontinuado, o prompt más
    grande que el TPM de la cuenta) — amerita reintentar con el siguiente
    proveedor. Cualquier otro error (ej. 400 por tool-call mal formada) se
    deja para el manejo existente (degradar el turno actual), no dispara
    failover de proveedor. Duplicado (no importado) desde
    infrastructure/ml/llm_failover.py a propósito — mismo criterio ya
    documentado ahí de no acoplar este módulo, que ya tiene su propio
    failover verificado en producción."""
    if isinstance(e, (openai.RateLimitError, openai.APIConnectionError, openai.NotFoundError)):
        return True
    if isinstance(e, openai.APIStatusError) and getattr(e, "status_code", None) == 413:
        return True
    return False


async def _ejecutar_tool(
    nombre: str, argumentos: Dict[str, Any], turno_id: Optional[str] = None
) -> Dict[str, Any]:
    """Traduce una tool-call del LLM a un intent existente del orquestador y lo ejecuta.

    turno_id: identificador compartido por TODAS las tools de una misma
    pregunta del usuario (generado una vez en responder_stream/
    responder_completo) — antes cada llamada generaba su propio sessionId
    aleatorio, así que no había forma de correlacionar "esta pregunta causó
    este fallo" en los logs salvo adivinando por cercanía de timestamp. Se
    reusa como sessionId del orquestador (que ya lo loguea en cada línea
    [ORCHESTRATOR]), así el mismo id aparece en ambos lados."""
    from core.container import container

    sesion = turno_id or uuid4().hex[:16]
    t0 = time.perf_counter()
    orchestrator = container.get_orchestrator_service()
    request = OrchestratorRequest(
        sessionId=f"asistente-{sesion}",
        intent=nombre,
        parameters=argumentos or {},
    )
    response = await orchestrator.orchestrate(request)
    duracion_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(
        f"[ASISTENTE] Tool '{nombre}' turno={sesion} status={response.status} "
        f"duracion_ms={duracion_ms}"
    )
    if response.status == "ERROR":
        return {"error": response.message, "detalle": [e.message for e in response.errors]}
    return response.data


def _sse(evento: Dict[str, Any]) -> str:
    return f"data: {json.dumps(evento, ensure_ascii=False, default=str)}\n\n"


async def _resolver_tool_calls(
    client, mensajes: List[Dict[str, Any]], turno_id: str, modelo: str, nombre_proveedor: str = "gemini"
) -> AsyncGenerator[Tuple[str, Optional[Dict[str, Any]]], None]:
    """Bucle de tool-calling (hasta MAX_ITERACIONES_TOOLS), muta `mensajes` in
    place agregando los turnos assistant/tool, y va emitiendo (yield) el
    nombre de cada herramienta en el momento en que se invoca — para que
    responder_stream() pueda seguir mostrando "consultando X..." en tiempo
    real como ya hacía antes de este refactor. Extraído para que
    responder_stream() y responder_completo() (Fase 19) compartan exactamente
    la misma lógica de decisión/ejecución de herramientas — solo difieren en
    cómo generan la respuesta final (streaming vs. no) y en si les importa el
    progreso intermedio.

    Cada iteración yieldea `(nombre_tool, resultado)`: `resultado` es `None`
    en el yield "de inicio" (antes de ejecutar, para el indicador en vivo) y
    solo se vuelve a yieldear con el resultado real para `vecindario_empresa`
    — es la única tool cuyo JSON crudo (nodos/aristas) le sirve al frontend
    para pintar un grafo; las demás tools solo emiten el yield de inicio,
    igual que antes de este cambio.

    nombre_proveedor (Fase 38): usado solo para calcular el presupuesto
    dinámico de `buscar_texto_rag` — ver `_estado_turno`/`TECHO_TOKENS_TURNO_GROQ`.
    Se resetea (no `setdefault`) en cada llamada: si un proveedor falla y
    responder_stream()/responder_completo() reintentan el turno con el
    siguiente proveedor, `mensajes` se reconstruye desde cero también — el
    estado de tokens/chunks-vistos del intento fallido no debe arrastrarse."""
    _estado_turno[turno_id] = {"tokens_acumulados": 0, "proveedor": nombre_proveedor, "chunks_vistos": set()}
    for _ in range(MAX_ITERACIONES_TOOLS):
        try:
            resp = await client.chat.completions.create(
                model=modelo,
                messages=mensajes,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,  # decisión de qué tool llamar debe ser consistente, no creativa
            )
            if resp.usage:
                logger.info(
                    f"[ASISTENTE] tokens (decisión de tools): prompt={resp.usage.prompt_tokens} "
                    f"completion={resp.usage.completion_tokens} total={resp.usage.total_tokens}"
                )
                # Fase 38: snapshot de cuántos tokens ya lleva el turno,
                # usado por _ejecutar_una() para acotar la SIGUIENTE llamada
                # a buscar_texto_rag (si el modelo pide otra en esta misma
                # iteración) — no la que ya se acaba de decidir.
                _estado_turno[turno_id]["tokens_acumulados"] = resp.usage.prompt_tokens
                _estado_turno[turno_id]["proveedor"] = nombre_proveedor
        except Exception as e:
            if _es_error_de_disponibilidad(e):
                # Fase 28 (ampliado 2026-08-22: bloqueo de red real hacia
                # generativelanguage.googleapis.com, y también 2026-08-22
                # para cubrir 404/413 — modelo descontinuado o prompt más
                # grande que el TPM de la cuenta, no solo 429/timeout): NO
                # degradar en silencio — se deja propagar para que
                # responder_stream()/responder_completo() puedan reintentar
                # el turno completo con el siguiente proveedor disponible
                # (failover real), en vez de sintetizar una respuesta pobre
                # con los datos parciales ya obtenidos.
                raise
            # Groq/Llama a veces emite una sintaxis de tool-call mal formada
            # como texto plano en vez de la estructura nativa esperada, y la
            # API responde 400 ("tool_use_failed") en vez de un mensaje normal.
            # Degradación con gracia: se trata como "sin más tools" y se
            # sintetiza la respuesta final con los datos ya obtenidos, en vez
            # de tumbar toda la conversación por una falla intermitente del
            # parser de function-calling.
            logger.warning(f"[ASISTENTE] Llamada de tool-calling falló turno={turno_id}, se corta el loop: {e}")
            break
        msg = resp.choices[0].message

        if not msg.tool_calls:
            # No pide más tools: no se agrega este content (generado sin
            # streaming) — se descarta a propósito y se re-genera la
            # respuesta final abajo, para que responder_stream() la muestre
            # palabra por palabra. Agregarlo aquí produciría dos mensajes
            # "assistant" consecutivos sin turno de usuario entre ellos,
            # confundiendo al modelo en la llamada siguiente.
            break

        mensajes.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    # Gemini exige reenviar thought_signature en el siguiente
                    # turno o responde 400 ("Function call is missing a
                    # thought_signature") — no está en el contrato genérico
                    # de OpenAI, viene en extra_content.google en la respuesta.
                    **({"extra_content": tc.extra_content} if getattr(tc, "extra_content", None) else {}),
                }
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            yield (tc.function.name, None)

        async def _ejecutar_una(tc) -> Tuple[str, Dict[str, Any]]:
            nombre = tc.function.name
            try:
                argumentos = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                # Falla silenciosa histórica: antes se sustituía por {} sin
                # ningún rastro, así que una tool podía llamarse con argumentos
                # vacíos sin que quedara log de por qué — mismo principio de
                # observabilidad que el warning de truncado más abajo.
                logger.warning(
                    f"[ASISTENTE] Argumentos JSON inválidos para tool '{nombre}' "
                    f"turno={turno_id}: {tc.function.arguments!r}"
                )
                argumentos = {}
            if nombre == "buscar_texto_rag":
                # Fase 38: presupuesto dinámico + dedup, ver constantes al
                # inicio del módulo. Claves con prefijo "_" — no están en el
                # schema visible del tool, el LLM nunca las ve ni las controla.
                estado = _estado_turno[turno_id]
                proveedor_activo = estado.get("proveedor", "gemini")
                if proveedor_activo == "groq_backup":
                    techo = TECHO_TOKENS_TURNO_GROQ_BACKUP
                elif proveedor_activo.startswith("groq"):
                    techo = TECHO_TOKENS_TURNO_GROQ
                else:
                    techo = 100_000
                restante_tokens = max(techo - estado.get("tokens_acumulados", 0), 0)
                presupuesto_natural = int(restante_tokens * CHARS_POR_TOKEN_TOOL_RESULT)
                if proveedor_activo.startswith("groq") and presupuesto_natural < PRESUPUESTO_CHARS_PISO:
                    # 2026-08-22, hallazgo en producción real: el modelo a
                    # veces reintenta buscar_texto_rag con otra redacción
                    # cuando la primera búsqueda no le da una cifra exacta
                    # (mismo comportamiento ya visto en Fase 26) — ningún
                    # ajuste de presupuesto por sí solo evita ese reintento,
                    # y buscar de nuevo con un presupuesto ya en el piso solo
                    # gasta el poco margen restante en overhead de JSON sin
                    # aportar contenido útil. En vez de forzar una búsqueda
                    # recortada al mínimo, se salta la búsqueda por completo
                    # y se le pide al modelo responder honestamente con lo
                    # que ya tiene — evita el 413 duro que antes tumbaba
                    # todo el turno sin ninguna respuesta.
                    argumentos["_limite_alcanzado"] = True
                else:
                    argumentos["_presupuesto_chars"] = max(
                        PRESUPUESTO_CHARS_PISO, min(PRESUPUESTO_CHARS_TECHO, presupuesto_natural)
                    )
                argumentos["_chunks_vistos"] = list(estado["chunks_vistos"])
            try:
                resultado = await _ejecutar_tool(nombre, argumentos, turno_id)
            except Exception as e:
                logger.error(f"[ASISTENTE] Tool '{nombre}' turno={turno_id} falló: {e}")
                resultado = {"error": f"La herramienta '{nombre}' falló: {e}"}
            if nombre == "buscar_texto_rag" and isinstance(resultado, dict):
                claves_nuevas = resultado.pop("_claves_vistas", None)
                if claves_nuevas:
                    _estado_turno[turno_id]["chunks_vistos"].update(claves_nuevas)
            return nombre, resultado

        # Ejecutar todas las tool_calls de este turno en paralelo (antes
        # secuencial, un await tras otro) — mismo patrón ya soportado por
        # OpenAI/Anthropic/Google: las tools son de solo lectura e
        # independientes entre sí, no hay razón para serializarlas.
        resultados = await asyncio.gather(*[_ejecutar_una(tc) for tc in msg.tool_calls])

        for tc, (nombre, resultado) in zip(msg.tool_calls, resultados):
            if nombre == "vecindario_empresa" and "error" not in resultado:
                yield (nombre, resultado)
            # 'nodos'/'aristas' de vecindario_empresa son solo para que el
            # frontend pinte el grafo (ya enviados completos al SSE arriba) —
            # incluirlos en el mensaje para el LLM desperdicia casi todo el
            # límite de 8000 chars antes de llegar a campos que sí importan
            # para redactar una respuesta (ej. 'interventorias' quedaba
            # truncado fuera del payload en empresas con muchos contratos).
            # El handler del orquestador anida el dict real bajo la clave
            # "vecindario" (ver ontologia_handler.py::_handle_vecindario_empresa).
            resultado_para_llm = resultado
            if nombre == "vecindario_empresa" and isinstance(resultado, dict):
                vecindario = resultado.get("vecindario")
                if isinstance(vecindario, dict):
                    resultado_para_llm = {
                        **{k: v for k, v in resultado.items() if k != "vecindario"},
                        "vecindario": {
                            k: v for k, v in vecindario.items() if k not in ("nodos", "aristas")
                        },
                    }
            contenido_json = json.dumps(resultado_para_llm, ensure_ascii=False, default=str)
            if len(contenido_json) > 8000:
                # Truncado silencioso histórico: así se perdió 'interventorias'
                # del payload de vecindario_empresa (Fase 23 Bloque 2, item 11)
                # sin que ningún log lo advirtiera. Este warning no cambia el
                # comportamiento (se sigue recortando igual) — solo deja rastro
                # para detectar el próximo caso por log en vez de por prueba
                # manual exhaustiva.
                logger.warning(
                    f"[ASISTENTE] Resultado de tool '{nombre}' truncado: "
                    f"{len(contenido_json)} -> 8000 chars turno={turno_id}"
                )
            mensajes.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": contenido_json[:8000],
            })
    else:
        logger.warning("[ASISTENTE] Se alcanzó el tope de iteraciones de tool-calling")

    # Gemini, a diferencia de Groq/OpenAI, no deja de pedir tool_calls solo
    # porque se omita `tools` en esta llamada — infiere del historial (el
    # último mensaje es de rol "tool") que debe seguir usando herramientas,
    # y responde con tool_calls vacíos/None en vez de texto (probado en vivo:
    # ni omitir `tools` ni `tool_choice="none"` lo evitan). Un turno de
    # usuario explícito pidiendo la respuesta en texto sí funciona.
    if mensajes and mensajes[-1].get("role") == "tool":
        mensajes.append({
            "role": "user",
            "content": "Con la información que ya obtuviste, responde ahora la pregunta en texto, sin llamar más herramientas.",
        })


_PATRON_CIFRA = re.compile(r"\d+[.,]\d+%?|\d{3,}%?")


def _verificar_grounding_numerico(texto_final: str, mensajes: List[Dict[str, Any]], turno_id: str) -> None:
    """Grounding ligero (Fase 25) — sin llamada LLM adicional (el RPM=15 de
    Gemini ya se satura en esta sesión, agregar una llamada de verificación
    por turno empeoraría eso). Heurística basada en reglas: cada cifra
    "significativa" (con decimales, o 3+ dígitos, o con %) que aparece en la
    respuesta final debería poder rastrearse en el texto crudo que devolvieron
    las tools de ese turno — si no aparece, puede ser una cifra alucinada.
    Solo observabilidad (logging): nunca bloquea ni reescribe la respuesta,
    porque la heurística tiene falsos positivos esperables (formato de miles/
    decimales distinto entre la cifra cruda y cómo la redacta el LLM)."""
    cifras = set(_PATRON_CIFRA.findall(texto_final))
    if not cifras:
        return
    texto_tools = " ".join(
        m["content"] for m in mensajes
        if m.get("role") == "tool" and isinstance(m.get("content"), str)
    )

    def _aparece(cifra: str) -> bool:
        # Los datos crudos de las tools son JSON (ej. "variacion_pct": 2.3) —
        # nunca traen el '%' literal aunque el texto final sí lo redacte
        # ("2.3%"), así que se compara también sin el signo para no generar
        # una falsa alarma en CADA porcentaje citado.
        return cifra in texto_tools or cifra.rstrip("%") in texto_tools

    no_verificadas = sorted(c for c in cifras if not _aparece(c))
    if no_verificadas:
        logger.warning(
            f"[ASISTENTE] Posibles cifras no verificadas en turno={turno_id}: {no_verificadas}"
        )


def _construir_contenido_usuario(mensaje: str, archivos: Optional[List[Dict[str, str]]]) -> Any:
    """Arma el `content` del mensaje de usuario — string simple si no hay
    archivos (idéntico al comportamiento de siempre), o una lista de content
    parts (texto + cada archivo como image_url con su mime_type real) si los
    hay. Verificado en vivo (Fase 20) que el endpoint compatible con OpenAI de
    Gemini acepta tanto imágenes como PDFs por esta vía — no es solo para
    imágenes pese al nombre "image_url", es como Gemini expone archivos
    binarios en general en este endpoint."""
    if not archivos:
        return mensaje
    partes: List[Dict[str, Any]] = [{"type": "text", "text": mensaje}]
    for archivo in archivos:
        partes.append({
            "type": "image_url",
            "image_url": {"url": f"data:{archivo['mime_type']};base64,{archivo['data_base64']}"},
        })
    return partes


async def responder_stream(
    mensaje: str,
    historial: List[Dict[str, str]],
    archivos: Optional[List[Dict[str, str]]] = None,
) -> AsyncGenerator[str, None]:
    """
    Genera la respuesta del Asistente en streaming (formato SSE).

    historial: lista de {role: 'user'|'assistant', content: str} de turnos previos,
    enviada completa por el cliente en cada request (sin memoria server-side —
    mismo patrón stateless que domain/services/ai_service.py::AgentIA).
    archivos: lista opcional de {mime_type, data_base64} (Fase 20) — imágenes o
    PDFs adjuntos al mensaje, ya validados (tipo/tamaño) por el endpoint que
    llama a esta función.

    Fase 28 — failover real: si el rate-limit de Gemini ocurre ANTES de emitir
    el primer `delta` (lo más común: durante la resolución de tools, o al
    abrir el stream de síntesis), se reintenta el turno completo con el
    siguiente proveedor. Si ocurre DESPUÉS de que ya se le mostró texto
    parcial al usuario, no se reintenta — reintentar duplicaría/reemplazaría
    contenido que el usuario ya vio.
    """
    turno_id = uuid4().hex[:12]
    t0_turno = time.perf_counter()
    proveedores = _proveedores_disponibles()

    for i, (nombre_proveedor, base_url, api_key, modelo) in enumerate(proveedores):
        client = _get_llm_client(base_url, api_key)
        mensajes: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        mensajes.extend(historial[-MAX_TURNOS_HISTORIAL:])
        mensajes.append({"role": "user", "content": _construir_contenido_usuario(mensaje, archivos)})
        ya_emitio_delta = False

        try:
            async for nombre_tool, resultado_tool in _resolver_tool_calls(client, mensajes, turno_id, modelo, nombre_proveedor):
                yield _sse({"tool": nombre_tool})
                if resultado_tool is not None:
                    yield _sse({"grafo": resultado_tool})

            # Síntesis final en streaming — para forzar texto en lenguaje natural.
            stream = await client.chat.completions.create(
                model=modelo,
                messages=mensajes,
                stream=True,
                temperature=0.3,
                stream_options={"include_usage": True},
            )
            ultimo_usage = None
            texto_acumulado = []
            async for chunk in stream:
                if chunk.usage:
                    ultimo_usage = chunk.usage  # Gemini manda usage acumulado en cada chunk, no solo al final
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        ya_emitio_delta = True
                        texto_acumulado.append(delta)
                        yield _sse({"delta": delta})

            if ultimo_usage:
                logger.info(
                    f"[ASISTENTE] tokens (síntesis streaming): prompt={ultimo_usage.prompt_tokens} "
                    f"completion={ultimo_usage.completion_tokens} total={ultimo_usage.total_tokens}"
                )
            _verificar_grounding_numerico("".join(texto_acumulado), mensajes, turno_id)

            duracion_turno_ms = round((time.perf_counter() - t0_turno) * 1000)
            if nombre_proveedor != "gemini":
                logger.warning(
                    f"[ASISTENTE] Turno {turno_id} servido por fallback '{nombre_proveedor}' (Gemini no disponible)"
                )
            logger.info(
                f"[ASISTENTE] Turno {turno_id} completo en {duracion_turno_ms}ms (proveedor={nombre_proveedor})"
            )
            yield _sse({"done": True, "turno_id": turno_id})
            _estado_turno.pop(turno_id, None)  # Fase 38: liberar estado del turno
            return

        except Exception as e:
            if not _es_error_de_disponibilidad(e):
                duracion_turno_ms = round((time.perf_counter() - t0_turno) * 1000)
                logger.error(f"[ASISTENTE] Error generando respuesta turno={turno_id} ({duracion_turno_ms}ms): {e}")
                yield _sse({"error": "Ocurrió un error generando la respuesta. Intenta de nuevo."})
                yield _sse({"done": True, "turno_id": turno_id})
                _estado_turno.pop(turno_id, None)
                return
            hay_siguiente = i + 1 < len(proveedores)
            if not ya_emitio_delta and hay_siguiente:
                logger.warning(
                    f"[ASISTENTE] Proveedor '{nombre_proveedor}' no disponible turno={turno_id} "
                    f"({type(e).__name__}), probando siguiente..."
                )
                continue
            duracion_turno_ms = round((time.perf_counter() - t0_turno) * 1000)
            logger.error(
                f"[ASISTENTE] Sin proveedores disponibles turno={turno_id} "
                f"({duracion_turno_ms}ms, contenido_parcial={ya_emitio_delta}): {e}"
            )
            yield _sse({"error": "El servicio de IA no está disponible en este momento. Intenta de nuevo en unos minutos."})
            yield _sse({"done": True, "turno_id": turno_id})
            _estado_turno.pop(turno_id, None)
            return


async def responder_completo(
    mensaje: str,
    historial: List[Dict[str, str]],
    archivos: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Fase 19: misma lógica de decisión/ejecución de herramientas que
    responder_stream(), pero devuelve el texto final completo en una sola
    llamada (no streaming) — para flujos que necesitan el texto entero antes
    de seguir (ej. sintetizar audio en energia_app.py::post_consulta_audio,
    o el asistente de voz en tiempo real, que narra la respuesta completa).
    archivos: ver _construir_contenido_usuario (Fase 20).

    Fase 28 — failover real: si Gemini responde 429 (rate limit), reintenta
    el turno COMPLETO desde cero con el siguiente proveedor disponible
    (Groq, si hay GROQ_API_KEY) en vez de fallar — ver _proveedores_disponibles().
    """
    turno_id = uuid4().hex[:12]
    t0_turno = time.perf_counter()
    proveedores = _proveedores_disponibles()

    for i, (nombre_proveedor, base_url, api_key, modelo) in enumerate(proveedores):
        client = _get_llm_client(base_url, api_key)
        mensajes: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        mensajes.extend(historial[-MAX_TURNOS_HISTORIAL:])
        mensajes.append({"role": "user", "content": _construir_contenido_usuario(mensaje, archivos)})

        try:
            async for _ in _resolver_tool_calls(client, mensajes, turno_id, modelo, nombre_proveedor):
                pass  # sin consumidor de progreso intermedio en el flujo no-streaming
            resp = await client.chat.completions.create(
                model=modelo,
                messages=mensajes,
                temperature=0.3,
            )
            if resp.usage:
                logger.info(
                    f"[ASISTENTE] tokens (respuesta completa): prompt={resp.usage.prompt_tokens} "
                    f"completion={resp.usage.completion_tokens} total={resp.usage.total_tokens}"
                )
            texto_final = resp.choices[0].message.content or ""
            _verificar_grounding_numerico(texto_final, mensajes, turno_id)
            duracion_turno_ms = round((time.perf_counter() - t0_turno) * 1000)
            if nombre_proveedor != "gemini":
                logger.warning(
                    f"[ASISTENTE] Turno {turno_id} servido por fallback '{nombre_proveedor}' (Gemini no disponible)"
                )
            logger.info(
                f"[ASISTENTE] Turno {turno_id} completo en {duracion_turno_ms}ms (proveedor={nombre_proveedor})"
            )
            _estado_turno.pop(turno_id, None)  # Fase 38: liberar estado del turno
            return texto_final
        except Exception as e:
            if not _es_error_de_disponibilidad(e):
                duracion_turno_ms = round((time.perf_counter() - t0_turno) * 1000)
                logger.error(f"[ASISTENTE] Error generando respuesta completa turno={turno_id} ({duracion_turno_ms}ms): {e}")
                _estado_turno.pop(turno_id, None)
                return "Ocurrió un error generando la respuesta. Intenta de nuevo."
            hay_siguiente = i + 1 < len(proveedores)
            logger.warning(
                f"[ASISTENTE] Proveedor '{nombre_proveedor}' no disponible turno={turno_id} "
                f"({type(e).__name__})"
                + (", probando siguiente..." if hay_siguiente else ", sin más proveedores.")
            )
            if hay_siguiente:
                continue
            duracion_turno_ms = round((time.perf_counter() - t0_turno) * 1000)
            logger.error(f"[ASISTENTE] Todos los proveedores agotados turno={turno_id} ({duracion_turno_ms}ms): {e}")
            _estado_turno.pop(turno_id, None)
            return "El servicio de IA no está disponible en este momento. Intenta de nuevo en unos minutos."
    _estado_turno.pop(turno_id, None)
    return "Ocurrió un error generando la respuesta. Intenta de nuevo."

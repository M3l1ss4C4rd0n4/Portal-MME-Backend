"""
Golden dataset del Asistente IA (Fase 24 — Fase 23 Bloque 3 #golden dataset).

Set fijo de preguntas de referencia, de alcance deliberadamente ligero: sin
infraestructura de CI, sin score exacto — solo aserciones laxas (palabras
clave que deberían aparecer en la respuesta) y qué tool se espera que dispare.
Motivo: no existe ningún test end-to-end del Asistente IA ni del orquestador
(confirmado por búsqueda exhaustiva, 2026-08-06), y esta sesión encontró
varios bugs reales (thought_signature, descripción de tool faltante, truncado
silencioso a 8000 chars) que solo se detectaron probando preguntas reales a
mano — un set de referencia reduce el riesgo de que un cambio futuro de
prompt/modelo rompa en silencio algo que ya funcionaba.

No se corre en CI. Ver run_golden_dataset.py.
"""

from typing import Any, Dict, List, Optional, TypedDict


class PreguntaGolden(TypedDict):
    pregunta: str
    tool_esperada: Optional[str]
    palabras_clave_esperadas: List[str]


PREGUNTAS: List[Dict[str, Any]] = [
    {
        "pregunta": "¿Cuántas comunidades energéticas hay en el Chocó?",
        "tool_esperada": "resumen_departamento",
        "palabras_clave_esperadas": ["Chocó", "comunidad"],
    },
    {
        "pregunta": "¿Qué firmas de interventoría han fiscalizado contratos de GENSA y cuántos contratos tiene cada una?",
        "tool_esperada": "vecindario_empresa",
        "palabras_clave_esperadas": ["GENSA", "interventor"],
    },
    {
        "pregunta": "¿Cuál es el marco regulatorio o los decretos relacionados con Colombia Solar?",
        "tool_esperada": "buscar_texto_rag",
        "palabras_clave_esperadas": ["Decreto", "solar"],
    },
    {
        "pregunta": "Dame el ranking de contratos OR con mayor riesgo de atraso.",
        "tool_esperada": "riesgo_atraso_contratos_or",
        "palabras_clave_esperadas": ["riesgo", "contrato"],
    },
    {
        "pregunta": "¿Qué es el índice HSIN y de qué depende? Cita la resolución CREG.",
        "tool_esperada": "buscar_metrica",
        "palabras_clave_esperadas": ["HSIN", "CREG"],
    },
    {
        "pregunta": "¿Cuál es el déficit histórico de subsidios?",
        "tool_esperada": "subsidios_deficit_historico",
        "palabras_clave_esperadas": ["déficit", "subsidio"],
    },
    {
        "pregunta": "¿Qué se proyecta para los embalses del SIN en los próximos 6 meses?",
        "tool_esperada": "predicciones_sector",
        "palabras_clave_esperadas": ["embalse"],
    },
    {
        "pregunta": "¿Cómo está el fenómeno de El Niño? Dame ONI, PDO, SOI y GMST.",
        "tool_esperada": "panorama_climatico",
        "palabras_clave_esperadas": ["ONI"],
    },
    {
        "pregunta": "¿Cuál es la capacidad de la planta Cartagena 1?",
        "tool_esperada": "detalle_recurso",
        "palabras_clave_esperadas": ["MW", "Cartagena"],
    },
    {
        "pregunta": "¿Cómo ha evolucionado el Costo Unitario en los últimos 30 días y qué se proyecta?",
        "tool_esperada": "cu_evolucion",
        "palabras_clave_esperadas": ["Costo Unitario", "tendencia"],
    },
    {
        "pregunta": "¿Cómo está la salud de los datos de la ontología? ¿Cuánto backlog de alias sin resolver hay?",
        "tool_esperada": "calidad_datos_ontologia",
        "palabras_clave_esperadas": ["alias"],
    },
    {
        "pregunta": "¿Cómo está la generación eléctrica del sistema hoy?",
        "tool_esperada": "estado_actual",
        "palabras_clave_esperadas": ["generación", "GWh"],
    },
    {
        "pregunta": "Dame el detalle completo del contrato con id 1321: valor, avance, interventoría y estado.",
        "tool_esperada": "detalle_contrato",
        "palabras_clave_esperadas": ["1321"],
    },
    {
        "pregunta": "dame un resumen de cada uno de los tableros que hay en este portal y como se relacionan entre si",
        "tool_esperada": "resumen_portal",
        "palabras_clave_esperadas": ["FENOGE", "geografía"],
    },
    {
        "pregunta": "¿por qué Colombia le está vendiendo energía a Ecuador? ¿no debería guardar las reservas por el fenómeno del niño?",
        "tool_esperada": "noticias_sector",
        "palabras_clave_esperadas": ["Ecuador"],
    },
    {
        "pregunta": "¿Cuál es el objetivo del estudio de análisis energético de corto plazo de XM?",
        "tool_esperada": "buscar_texto_rag",
        "palabras_clave_esperadas": ["corto plazo"],
    },
    {
        "pregunta": "¿Cuál es el color favorito de un gato?",
        "tool_esperada": None,
        "palabras_clave_esperadas": [],
    },
    {
        # Fase 43 (2026-09-08): supervision_menu estaba roto (columna "contrato"
        # que no existe) y no había ninguna tool para desglosar por etapa —
        # caso real reportado por el usuario, ahora corregido.
        "pregunta": "¿Cuántos contratos se encuentran en ejecución en Supervisión?",
        "tool_esperada": "supervision_contratos_por_estado",
        "palabras_clave_esperadas": ["307", "ejecución"],
    },
    {
        # Caso adversarial de datos: "suspendido" no existe como estado_del_contrato
        # (solo FINALIZADO/VIGENTE/POR INICIAR) — la respuesta debe ser honesta,
        # no inventar una cifra de "0 suspendidos" ni mezclarla con la actividad AOM.
        "pregunta": "¿Cuántos contratos están suspendidos a la fecha en Supervisión?",
        "tool_esperada": "supervision_contratos_por_estado",
        "palabras_clave_esperadas": ["no existe"],
    },
    {
        # Auditoría de los 18 tableros (2026-09-09): contratos_or_menu fallaba
        # en el 100% de las invocaciones (tabla contratos_or.seguimiento
        # inexistente, mismo patrón que Supervisión) — ahora corregido.
        "pregunta": "¿Cuántos contratos OR hay y cuál es su avance documental y físico?",
        "tool_esperada": "contratos_or_menu",
        "palabras_clave_esperadas": ["18"],
    },
    {
        # Validaciones mezclaba 19 cortes mensuales históricos en vez del mes
        # vigente — ahora filtra correctamente al último fecha_actualizacion.
        "pregunta": "¿Cuántas validaciones de subsidios hay en el mes vigente para SIN y ZNI?",
        "tool_esperada": "subsidios_validaciones",
        "palabras_clave_esperadas": ["vigente"],
    },
    {
        # Bug de escala 1.000.000x: deficit_historico ya viene en millones de
        # pesos, no en pesos crudos — antes decía "$3.68 millones" en vez de
        # "$3.68 billones" para el déficit acumulado 2025.
        "pregunta": "¿Cuál es el déficit acumulado de subsidios del último año registrado?",
        "tool_esperada": "subsidios_deficit_historico",
        "palabras_clave_esperadas": ["billones"],
    },
    {
        # Brecha de cobertura: FENOGE no tenía ninguna tool de avance real vs.
        # programado, pese a que el propio catálogo de tableros lo describe así.
        "pregunta": "¿Cómo va el avance real vs. programado de los contratos de FENOGE?",
        "tool_esperada": "fenoge_seguimiento",
        "palabras_clave_esperadas": ["programado"],
    },
]

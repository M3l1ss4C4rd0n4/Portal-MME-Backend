"""
Re-ranking de candidatos RAG con cross-encoder (Fase 24 — Fase 23 Bloque 3 #10).

Motivo: la similitud coseno de embeddings bi-encoder (paraphrase-multilingual-
MiniLM-L12-v2, ver embeddings.py) compara la consulta y cada texto por
separado — es rápida pero aproximada. Reproducido en vivo (2026-08-06): la
consulta "cuál es el color favorito de un gato" obtiene 0.33-0.38 de similitud
contra fragmentos de contratos de electrificación veredal sin relación
semántica real, superando el umbral_similitud=0.3 de semantic_search_repository.py.

Un cross-encoder compara consulta y texto JUNTOS en una sola pasada por el
modelo — mucho más preciso, a costa de más cómputo (por eso se aplica solo
sobre un pool acotado de candidatos ya preseleccionados por el bi-encoder,
nunca sobre todo el corpus).

Calibración del umbral (evidencia real, 2026-08-06, contra el corpus real en
producción, no textos sintéticos — mismo modelo). Historial de 2 rondas:

Ronda 1 (solo fraseo natural): el caso "gato" reproducido puntúa -2.23 (mejor)
a -7.79; 3 consultas RAG genuinas ya verificadas exitosas en fases anteriores
(Colombia Solar, subsidios, plantas fuera de servicio), su mejor candidato
real: +6.02, -1.85, -1.34. UMBRAL_RERANK=-2.0 separaba ambos grupos ahí.

Ronda 2 (hallazgo real en producción, mismo día): al conectar la búsqueda
híbrida (Fase 25) se reprodujo que el LLM a veces llama a buscar_texto_rag
con una consulta tipo "sopa de palabras" (ej. "mantenimiento plantas
indisponibles fuera de servicio") en vez de una pregunta en lenguaje natural,
pese a que el schema del tool ya lo pide explícitamente — el cross-encoder es
MUY sensible a ese estilo: el mismo chunk relevante (plantas indisponibles)
que puntuaba +1.70 con fraseo natural cayó a -2.74/-1.75 con fraseo tipo
palabras sueltas, y con UMBRAL_RERANK=-2.0 los 11 candidatos reales de esa
consulta quedaron TODOS descartados — una regresión real (0 resultados para
una pregunta que sí tenía respuesta), no solo teórica.

No existe un umbral único que separe limpio "irrelevante" de "relevante" bajo
AMBOS estilos de consulta con los datos disponibles (el mejor caso de "gato"
con sopa de palabras, -2.88, queda muy cerca del peor caso legítimo con sopa
de palabras, -2.74 — un margen de apenas 0.14). Ante esa ambigüedad se
prioriza NO rechazar contenido real (un falso "no tengo esa información"
es peor que ocasionalmente dejar pasar un fragmento marginal, que la síntesis
final del LLM ya ha demostrado saber tratar con cautela — Fase 21) sobre
filtrar cada caso irrelevante con precisión perfecta. UMBRAL_RERANK=-3.0
mantiene con margen los 3 casos legítimos vistos en ambos estilos de fraseo,
a costa de dejar pasar ocasionalmente el mejor candidato de una consulta
irrelevante. Calibración de mejor esfuerzo con pocos puntos de datos, sujeta
a revisión si producción muestra más falsos negativos o falsos positivos.
"""

import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

MODEL_NAME = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
UMBRAL_RERANK = -3.0

# Fase 35 — bono de recencia: reproducido en vivo (2026-08-12) que el corpus
# de Planeación XM (Fase 33) contiene ~250 informes semanales casi idénticos
# entre sí (mismo formato "Conclusiones... las reservas esperadas al final de
# dicha semana oscilarían entre X% y Y%") — para una pregunta sobre "el último
# informe", el cross-encoder no tiene ninguna noción de fecha y a veces
# prefiere un informe de 2024 sobre el de la semana actual, solo por azar de
# fraseo. Peor aún: el redactor de XM cambió la frase estándar de
# "Conclusiones" entre 2024 y 2026 — el chunk real de la semana actual
# ("las reservas del sistema podrían alcanzar valores de embalse agregado del
# SIN entre X% y Y%") puntúa -0.11 contra la misma consulta, mientras un
# informe de 2024 con la frase vieja puntúa 2.35 — una brecha real de ~2.47,
# mayor de lo esperado.
#
# VENTANA_RECENCIA_DIAS ampliada de 21 a 100 (mismo día, tras verificar el
# caso de Largo Plazo): el mismo tema 'planeacion_xm' mezcla cadencias muy
# distintas — informes SEMANALES (Corto Plazo) y TRIMESTRALES (Largo/
# Mediano Plazo, ~90 días entre publicaciones). Con la ventana original de
# 21 días, el informe trimestral de restricciones más reciente (T2 2026,
# publicado 21-jul-2026, 22 días antes de esta prueba) quedaba FUERA de la
# ventana — bono = 0 — y perdía contra un informe de 2024 pese a que la
# brecha real ahí es mucho menor (0.54, no 2.47). 100 días cubre con margen
# un ciclo trimestral completo sin diluir el caso semanal (a 5 días de
# antigüedad, el bono real SUBE de 2.67 a 3.33 con la ventana más ancha,
# porque la pendiente de decaimiento es más suave). Decae linealmente a 0
# en VENTANA_RECENCIA_DIAS.
#
# BONO_RECENCIA_MAX subido de 3.5 a 7.0 (mismo día, tras reproducir 2 fallos
# reales en producción, no solo teóricos): el LLM del Asistente a veces
# genera una consulta tipo "reservas esperadas al final de la semana
# conclusiones analisis energetico corto plazo" — un estilo intermedio,
# ni la frase exacta de un informe viejo ni una pregunta completamente
# natural, que resultó tener una brecha real de ~3.80 (mayor que el peor
# caso medido antes, 2.47) porque casualmente incluye varias palabras
# ancla ("reservas esperadas al final de... semana") del formato viejo de
# "Conclusiones". Con BONO_RECENCIA_MAX=3.5 esto seguía perdiendo contra
# 2024 incluso con la ventana ya ampliada. Se sube a 7.0 (a 5 días de
# antigüedad, bono ≈6.65, suficiente margen sobre la brecha de 3.80 medida)
# — segunda calibración de mejor esfuerzo, ahora basada en 3 casos reales
# reproducidos (no 1), sujeta a revisión si aparecen casos con brechas aún
# mayores.
BONO_RECENCIA_MAX = 7.0
VENTANA_RECENCIA_DIAS = 100

# Fase 29 — bono de prioridad por fuente: documentos que YA tienen botón de
# descarga en el portal (Boletín XM, informes diarios, actas, informe de
# empalme) deben ganar frente a carpetas genéricas de SharePoint cuando la
# relevancia es comparable — sin este bono, todo competía en igualdad de
# condiciones pese a que unos son claramente más importantes que otros.
# Magnitud moderada a propósito: alcanza para romper empates o acercar un
# candidato justo debajo del umbral, pero no fuerza contenido irrelevante de
# una fuente prioritaria por encima de contenido genuinamente más relevante
# de otra (una brecha grande de score sigue ganando).
BONO_PRIORIDAD_FUENTE = 1.5

_RE_ANIO = re.compile(r"\b(19|20)\d{2}\b")


def _consulta_pide_anio_historico(consulta: str) -> bool:
    """Fase 35 (continuación) — si la consulta ya menciona explícitamente un
    año pasado (ej. "semana 40 de 2024"), el bono de recencia debe apagarse:
    reproducido en vivo que, con el bono ya subido a 7.0 para arreglar el
    caso de 'el último informe', esa misma consulta le devolvía contenido de
    2026 a una pregunta que pedía 2024 explícitamente — el bono terminaba
    pisando la intención real del usuario. Heurística simple (año de 4
    dígitos != año actual) en vez de NLP de fechas: cubre el caso real
    encontrado sin necesitar entender toda variación de fraseo temporal."""
    anio_actual = datetime.now(timezone.utc).year
    for match in _RE_ANIO.finditer(consulta):
        if int(match.group(0)) != anio_actual:
            return True
    return False


_model = None
_model_lock = threading.Lock()


def _get_model():
    """Mismo patrón de singleton-con-lock que embeddings.py::_get_model() —
    carga una sola vez por proceso, offline tras la primera descarga (el
    modelo debe descargarse una vez con red habilitada antes de que el
    proceso de producción, que corre con HF_HUB_OFFLINE=1, lo necesite)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                import os
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                from sentence_transformers import CrossEncoder
                logger.info(f"[RERANKING] Cargando modelo {MODEL_NAME} (offline)...")
                _model = CrossEncoder(MODEL_NAME)
                logger.info("[RERANKING] Modelo cargado")
    return _model


def rerank(
    consulta: str,
    candidatos: List[Dict[str, Any]],
    top_k: int,
    campo_texto: str = "contenido",
    umbral: float = UMBRAL_RERANK,
    temas_prioritarios: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Reordena `candidatos` por relevancia real consulta-texto (cross-encoder)
    y descarta los que caigan por debajo de `umbral` — a diferencia de la
    similitud de embeddings, este score sí distingue "tema relacionado" de
    "responde la pregunta". Agrega el campo `score_rerank` a cada dict.
    Retorna como máximo `top_k`, puede retornar una lista vacía o más corta
    si ningún candidato supera `umbral` (comportamiento correcto: mejor no
    citar nada que citar contenido irrelevante).

    `temas_prioritarios` (Fase 29): si un candidato trae `tema` (columna
    `informes_documentos.tema`) dentro de este conjunto, se le suma
    BONO_PRIORIDAD_FUENTE antes de filtrar/ordenar — ver constante arriba.

    Bono de recencia (Fase 35): si un candidato trae `fecha_documento` (columna
    `informes_documentos.modificado_en_sharepoint`, propagada por
    semantic_search_repository.py), los documentos más recientes reciben un
    bono que decae linealmente a 0 en VENTANA_RECENCIA_DIAS — corrige que el
    cross-encoder no tenga ninguna noción de fecha entre decenas de informes
    periódicos casi idénticos entre sí (ver constantes arriba). El bono se
    desactiva por completo si `consulta` menciona explícitamente un año
    distinto al actual (ver `_consulta_pide_anio_historico`) — evita que la
    preferencia por lo reciente pise una pregunta genuinamente histórica."""
    if not candidatos:
        return []
    modelo = _get_model()
    pares = [(consulta, c[campo_texto]) for c in candidatos]
    scores = modelo.predict(pares)
    ahora = datetime.now(timezone.utc)
    pide_anio_historico = _consulta_pide_anio_historico(consulta)
    for candidato, score in zip(candidatos, scores):
        score = float(score)
        if temas_prioritarios and candidato.get("tema") in temas_prioritarios:
            score += BONO_PRIORIDAD_FUENTE
        fecha_doc = candidato.get("fecha_documento")
        if fecha_doc and not pide_anio_historico:
            if fecha_doc.tzinfo is None:
                fecha_doc = fecha_doc.replace(tzinfo=timezone.utc)
            dias = (ahora - fecha_doc).total_seconds() / 86400
            if 0 <= dias < VENTANA_RECENCIA_DIAS:
                score += BONO_RECENCIA_MAX * (1 - dias / VENTANA_RECENCIA_DIAS)
        candidato["score_rerank"] = score
    descartados = sum(1 for c in candidatos if c["score_rerank"] < umbral)
    if descartados:
        logger.info(
            f"[RERANKING] {descartados}/{len(candidatos)} candidatos descartados "
            f"por score_rerank < {umbral} para consulta='{consulta[:60]}'"
        )
    aprobados = [c for c in candidatos if c["score_rerank"] >= umbral]
    aprobados.sort(key=lambda c: c["score_rerank"], reverse=True)
    return aprobados[:top_k]

"""
Embeddings locales para búsqueda semántica (RAG sobre texto libre — ontologia.*).

Modelo: paraphrase-multilingual-MiniLM-L12-v2 (384 dims, sentence-transformers).
Local/CPU, sin API externa — Groq no ofrece endpoint de embeddings y no hay
OPENAI_API_KEY configurada. Singleton: el modelo (~470MB) se carga una sola vez por
proceso, nunca por request (cargar por request tomaría ~15s c/u).
"""

import threading
from typing import List

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

_model = None
_model_lock = threading.Lock()


def _get_model():
    """
    Carga el modelo en modo offline (HF_HUB_OFFLINE=1) — una vez descargado a la
    caché local (~/.cache/huggingface), no debe depender de la disponibilidad de
    Hugging Face Hub para arrancar. Sin esto, cada arranque del proceso hace ~20
    llamadas HTTP de verificación aunque el modelo ya esté en disco.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                import os
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                from sentence_transformers import SentenceTransformer
                logger.info(f"[EMBEDDINGS] Cargando modelo {MODEL_NAME} (offline)...")
                _model = SentenceTransformer(MODEL_NAME)
                logger.info("[EMBEDDINGS] Modelo cargado")
    return _model


def embed(texto: str) -> List[float]:
    """Genera el embedding de un solo texto (ej. la pregunta del usuario)."""
    return _get_model().encode(texto, normalize_embeddings=True).tolist()


def embed_batch(textos: List[str]) -> List[List[float]]:
    """Genera embeddings en lote (ej. indexación masiva de contratos)."""
    if not textos:
        return []
    vectores = _get_model().encode(
        textos, normalize_embeddings=True, show_progress_bar=False, batch_size=32
    )
    return [v.tolist() for v in vectores]

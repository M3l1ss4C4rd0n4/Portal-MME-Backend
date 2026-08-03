"""
Extracción de texto de documentos PDF/PPTX para RAG (ontologia.informes_texto_embeddings).

Chunking natural: 1 chunk = 1 página (PDF) o 1 diapositiva (PPTX) — evita la
complejidad de un splitter genérico de tokens para un corpus inicial pequeño
(~10 documentos). Cada chunk conserva su número de página/diapositiva (1-indexed)
como chunk_index, útil para citar la fuente exacta en una respuesta del chatbot.
"""

from typing import List

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

LONGITUD_MINIMA_CHUNK = 30


def extraer_paginas_pdf(contenido: bytes) -> List[str]:
    """Texto por página de un PDF. Páginas con menos de LONGITUD_MINIMA_CHUNK
    caracteres (portadas, separadores) se omiten — no aportan a la búsqueda."""
    import pdfplumber
    import io

    paginas: List[str] = []
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        for page in pdf.pages:
            texto = (page.extract_text() or "").strip()
            if len(texto) >= LONGITUD_MINIMA_CHUNK:
                paginas.append(texto)
    return paginas


def extraer_slides_pptx(contenido: bytes) -> List[str]:
    """
    Texto por diapositiva de un PPTX: concatena todos los text frames (títulos,
    cuerpos, tablas) más las notas del orador. Gráficos/imágenes sin texto
    vectorial no se extraen (no hay OCR) — limitación conocida, no todo el
    contenido visual de una diapositiva queda indexado.
    """
    from pptx import Presentation
    import io

    slides: List[str] = []
    prs = Presentation(io.BytesIO(contenido))
    for slide in prs.slides:
        partes: List[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                partes.append(shape.text_frame.text.strip())
            if shape.has_table:
                for row in shape.table.rows:
                    fila = " | ".join(cell.text.strip() for cell in row.cells)
                    if fila.strip(" |"):
                        partes.append(fila)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notas = slide.notes_slide.notes_text_frame.text.strip()
            if notas:
                partes.append(notas)
        texto = "\n".join(partes).strip()
        if len(texto) >= LONGITUD_MINIMA_CHUNK:
            slides.append(texto)
    return slides


def extraer_parrafos_docx(contenido: bytes) -> List[str]:
    """
    Texto de un DOCX agrupado en chunks de ~15 párrafos (un DOCX no tiene páginas
    reales hasta que se renderiza — a diferencia de PDF/PPTX no hay una unidad
    natural de página/diapositiva, así que se agrupa por cantidad de párrafos).
    """
    from docx import Document
    import io

    PARRAFOS_POR_CHUNK = 15
    doc = Document(io.BytesIO(contenido))
    parrafos = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    chunks: List[str] = []
    for i in range(0, len(parrafos), PARRAFOS_POR_CHUNK):
        texto = "\n".join(parrafos[i : i + PARRAFOS_POR_CHUNK])
        if len(texto) >= LONGITUD_MINIMA_CHUNK:
            chunks.append(texto)
    return chunks


def extraer_chunks(contenido: bytes, tipo_archivo: str) -> List[str]:
    """Despacha a la función de extracción según tipo_archivo ('pdf' | 'pptx' | 'docx')."""
    if tipo_archivo == "pdf":
        return extraer_paginas_pdf(contenido)
    if tipo_archivo == "pptx":
        return extraer_slides_pptx(contenido)
    if tipo_archivo == "docx":
        return extraer_parrafos_docx(contenido)
    raise ValueError(f"Tipo de archivo no soportado para extracción: {tipo_archivo!r}")

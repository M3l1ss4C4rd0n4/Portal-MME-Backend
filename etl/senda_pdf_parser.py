"""
═══════════════════════════════════════════════════════════════════════════════
Extracción de la Senda de Referencia desde el gráfico del informe diario
"Variables Hidrológicas" de XM (PDF ya sincronizado vía OneDrive/SharePoint).

La gráfica ("Nivel del embalse agregado [%]") se entrega como una imagen
rasterizada dentro del PDF — no hay texto vectorial ni en los ejes ni en las
curvas, así que NO se puede leer con extracción de texto ni con calibración
por etiquetas de eje (eso requeriría OCR).

En su lugar, este módulo calibra ambos ejes usando dos anclas EXACTAS que sí
vienen como texto real y seleccionable en la misma página del PDF:
    "Para <día> el nivel de embalse del SIN llegó al X%"            (curva azul)
    "... una diferencia de Y puntos entre el volumen útil y la senda" (curva roja)

Con esas dos anclas (misma columna de píxeles, dos valores conocidos: X y X−Y)
se calibra el eje Y por regresión lineal de 2 puntos. El eje X se calibra con
el espaciado de las marcas de graduación (asumiendo periodicidad semanal, fija
en esta plantilla de XM) partiendo del punto ancla ya fechado exactamente.
No se depende de leer ninguna etiqueta rotada de fecha ni de valor.
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import numpy as np

ROJO_SENDA = (255, 0, 0)
AZUL_REAL = (0, 0, 255)
DIAS_POR_TICK = 7  # periodicidad semanal fija de esta plantilla de XM

_MESES_ABR = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

_RE_ANCLA_FECHA = re.compile(r"[Pp]ara ([a-z]{3})-(\d{2}) el nivel de embalse")
_RE_ANCLA_NIVEL = re.compile(r"nivel de embalse del SIN lleg[oó] al ([\d.]+)%")
_RE_ANCLA_DIFERENCIA = re.compile(
    r"diferencia de (-?[\d.]+) puntos entre el volumen [uú]til y la senda",
    re.IGNORECASE,
)


class ExtraccionSendaError(Exception):
    """Fallo al extraer o calibrar la gráfica de senda — no escribir datos derivados."""


@dataclass
class AnclaTextual:
    fecha: date
    valor_real: float
    valor_senda: float


def extraer_ancla_textual(texto_pagina: str, fecha_referencia: date) -> Optional[AnclaTextual]:
    """Ancla exacta (fecha, valor real, valor senda) desde el texto real del PDF.

    Devuelve None (no excepción) si el patrón no matchea — un cambio menor de
    redacción de XM no debe tumbar toda la corrida, solo esa parte.
    """
    m_fecha = _RE_ANCLA_FECHA.search(texto_pagina)
    m_nivel = _RE_ANCLA_NIVEL.search(texto_pagina)
    m_dif = _RE_ANCLA_DIFERENCIA.search(texto_pagina)
    if not (m_fecha and m_nivel and m_dif):
        return None

    mes_abr, dia_str = m_fecha.group(1).lower(), m_fecha.group(2)
    mes = _MESES_ABR.get(mes_abr)
    if mes is None:
        return None

    anio = fecha_referencia.year
    # La fecha ancla es "ayer" respecto a la publicación; si el mes descrito es
    # diciembre pero el informe se publicó en enero, la ancla es del año anterior.
    if mes == 12 and fecha_referencia.month == 1:
        anio -= 1

    try:
        fecha = date(anio, mes, int(dia_str))
    except ValueError:
        return None

    real = float(m_nivel.group(1))
    diferencia = float(m_dif.group(1))
    return AnclaTextual(fecha=fecha, valor_real=real, valor_senda=real - diferencia)


def extraer_grafica_y_texto(pdf_bytes: bytes) -> tuple[np.ndarray, str]:
    """Ubica la gráfica de senda y devuelve (imagen RGB, texto completo del PDF).

    La gráfica se identifica por contenido (presencia simultánea de rojo y azul
    puros en cantidad significativa), no por número de página ni de xref —
    ambos pueden cambiar de un informe a otro. El ancla textual ("nivel de
    embalse llegó a X%" y "diferencia de Y puntos...") puede estar en una
    página distinta a la de la gráfica, así que se busca sobre el texto
    completo del documento, no solo el de la página del gráfico.
    """
    import fitz
    from PIL import Image

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        texto_completo = "\n".join(page.get_text() for page in doc)
        for page in doc:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                base = doc.extract_image(xref)
                if base["ext"] != "png":
                    continue
                arr = np.array(Image.open(io.BytesIO(base["image"])).convert("RGB"))
                n_rojo = np.all(np.abs(arr.astype(int) - ROJO_SENDA) < 20, axis=-1).sum()
                n_azul = np.all(np.abs(arr.astype(int) - AZUL_REAL) < 20, axis=-1).sum()
                if n_rojo > 100 and n_azul > 100:
                    return arr, texto_completo
    finally:
        doc.close()
    raise ExtraccionSendaError("No se encontró la gráfica de senda de referencia en el PDF")


def _localizar_pixel_color(
    arr: np.ndarray, col: int, color: tuple[int, int, int],
    tolerancia: int = 30, busqueda_max: int = 6,
) -> Optional[float]:
    """Fila (float, promedio si hay varias) donde aparece `color` cerca de `col`.

    Busca en columnas vecinas porque la línea es punteada y puede no tener
    píxel exactamente en la columna pedida.
    """
    h, w, _ = arr.shape
    objetivo = np.array(color)
    for despl in range(busqueda_max):
        for c in {col - despl, col + despl}:
            if 0 <= c < w:
                mask = np.all(np.abs(arr[:, c].astype(int) - objetivo) < tolerancia, axis=-1)
                filas = np.where(mask)[0]
                if len(filas):
                    return float(filas.mean())
    return None


def _columna_mas_a_la_derecha_con_color(
    arr: np.ndarray, color: tuple[int, int, int], tolerancia: int = 30,
) -> Optional[int]:
    objetivo = np.array(color)
    mask = np.all(np.abs(arr.astype(int) - objetivo) < tolerancia, axis=-1)
    cols = np.where(mask.any(axis=0))[0]
    return int(cols.max()) if len(cols) else None


def _espaciado_ticks_eje_x(arr: np.ndarray) -> Optional[float]:
    """Espaciado mediano en píxeles entre marcas de graduación del eje X.

    Busca, en TODA la altura de la imagen, la fila cuyo patrón de píxeles
    negros forma entre 20 y 40 grupos evenly-spaced (el número esperado de
    marcas semanales para el rango de fechas típico de esta plantilla) con la
    menor variación relativa de espaciado — así se distingue de filas de texto
    rotado (muchos grupos pequeños e irregulares) sin depender de coordenadas
    fijas, que pueden variar entre imágenes.
    """
    h, w, _ = arr.shape
    negro = np.all(arr < [50, 50, 50], axis=-1)
    mejor: Optional[tuple[float, float]] = None
    for fila in range(h):
        cols = np.where(negro[fila])[0]
        if len(cols) < 15:
            continue
        grupos = []
        actual = [cols[0]]
        for c in cols[1:]:
            if c - actual[-1] <= 2:
                actual.append(c)
            else:
                grupos.append(sum(actual) / len(actual))
                actual = [c]
        grupos.append(sum(actual) / len(actual))
        if not (20 <= len(grupos) <= 40):
            continue
        diffs = np.diff(grupos)
        mediana = float(np.median(diffs))
        if not (15 <= mediana <= 60):
            continue
        regularidad = float(np.std(diffs) / (mediana + 1e-6))
        if mejor is None or regularidad < mejor[0]:
            mejor = (regularidad, mediana)
    return mejor[1] if mejor else None


def extraer_curva_senda(
    arr: np.ndarray, ancla: AnclaTextual,
) -> dict[date, float]:
    """Curva completa {fecha: porcentaje} de la línea roja "Senda referencia".

    Calibra usando SOLO la ancla textual (2 puntos conocidos: real y senda en
    la misma columna) + el espaciado de ticks del eje X — sin leer ninguna
    etiqueta de eje. Lanza ExtraccionSendaError si la calibración no es
    confiable (evita escribir valores basura).
    """
    h, w, _ = arr.shape

    col_ancla = _columna_mas_a_la_derecha_con_color(arr, AZUL_REAL)
    if col_ancla is None:
        raise ExtraccionSendaError("No se encontró la curva azul (volumen útil real) en la gráfica")

    fila_azul = _localizar_pixel_color(arr, col_ancla, AZUL_REAL)
    fila_roja = _localizar_pixel_color(arr, col_ancla, ROJO_SENDA)
    if fila_azul is None or fila_roja is None:
        raise ExtraccionSendaError("No se pudo ubicar azul/rojo en la columna ancla")
    if abs(fila_roja - fila_azul) < 2:
        raise ExtraccionSendaError(
            "Calibración de eje Y no confiable: curvas real y senda coinciden en píxeles"
        )

    # Calibración eje Y: 2 puntos conocidos (fila, valor) -> value = m*fila + b
    m = (ancla.valor_senda - ancla.valor_real) / (fila_roja - fila_azul)
    b = ancla.valor_real - m * fila_azul

    espaciado_px = _espaciado_ticks_eje_x(arr)
    if espaciado_px is None:
        raise ExtraccionSendaError("No se pudo calibrar el espaciado del eje X (marcas de fecha)")
    px_por_dia = espaciado_px / DIAS_POR_TICK
    if not (2.0 <= px_por_dia <= 15.0):
        raise ExtraccionSendaError(f"Escala de eje X fuera de rango plausible: {px_por_dia:.2f} px/día")

    curva: dict[date, float] = {}
    dia_min = -int(col_ancla / px_por_dia) - 1
    dia_max = int((w - col_ancla) / px_por_dia) + 1
    for offset_dias in range(dia_min, dia_max + 1):
        col = int(round(col_ancla + offset_dias * px_por_dia))
        if col < 0 or col >= w:
            continue
        fila = _localizar_pixel_color(arr, col, ROJO_SENDA)
        if fila is None:
            continue
        fecha = ancla.fecha + timedelta(days=offset_dias)
        curva[fecha] = round(m * fila + b, 2)

    # La ancla siempre se fija con el valor exacto de texto (más preciso que píxeles)
    curva[ancla.fecha] = ancla.valor_senda
    return curva

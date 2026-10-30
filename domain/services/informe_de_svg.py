"""Primitivas SVG del Informe Semanal de Dirección de Energía.

Por qué SVG escrito a mano y no una librería de gráficas: el mismo informe se
sirve como HTML interactivo y se imprime a PDF con WeasyPrint, que NO ejecuta
JavaScript. Una gráfica hecha con Plotly/Nivo saldría en blanco en el PDF. SVG
en línea se renderiza idéntico en los dos destinos, sin red y sin CDN.

Paleta: rampas secuenciales de un solo tono, validadas con el script de la
habilidad dataviz (monotonía de luminosidad, salto mínimo entre pasos, contraste
del extremo claro contra la superficie) en modo claro y oscuro por separado.
El ciclo de contratos y los estados de validación son ETAPAS ORDENADAS, no
categorías sueltas: por eso rampa y no arcoíris.
"""
from __future__ import annotations

import html
from dataclasses import dataclass

# ── Rampas validadas ──────────────────────────────────────────────────────────
# node scripts/validate_palette.js "<rampa>" --ordinal --mode <modo> --surface <sup>
RAMPA_AZUL_OSCURO = ("#1e40af", "#2563eb", "#3b82f6", "#60a5fa")
RAMPA_AZUL_CLARO = ("#1e3a8a", "#1d4ed8", "#3b82f6", "#60a5fa")
RAMPA_ORO_OSCURO = ("#b45309", "#d97706", "#f59e0b", "#fbbf24")
RAMPA_ORO_CLARO = ("#78350f", "#b45309", "#d97706", "#f59e0b")

# Colores de estado: reservados, nunca reutilizados como "serie 4". Siempre
# acompañados de etiqueta de texto, jamás color a secas.
ESTADO_BIEN = "#10B981"
ESTADO_ALERTA = "#F59E0B"
ESTADO_CRITICO = "#EF4444"
NEUTRO = "#64748B"

_ESCAPE = html.escape


@dataclass(frozen=True)
class Barra:
    etiqueta: str
    valor: float
    color: str
    # Texto que se dibuja al final de la barra. La etiqueta directa es la
    # codificación secundaria que hace que la identidad nunca dependa del color.
    valor_texto: str
    nota: str = ""


def _ruta_barra_redondeada(x: float, y: float, ancho: float, alto: float, radio: float = 4.0) -> str:
    """Rectángulo con solo el extremo de dato (derecha) redondeado.

    `rx` en un <rect> redondea las cuatro esquinas y despega la barra de su
    línea base; aquí el origen queda a escuadra y solo se redondea la punta.
    """
    r = max(0.0, min(radio, ancho, alto / 2))
    if ancho <= 0:
        return ""
    if r <= 0:
        return f"M{x},{y} h{ancho} v{alto} h{-ancho} Z"
    return (
        f"M{x},{y} "
        f"h{ancho - r} a{r},{r} 0 0 1 {r},{r} "
        f"v{alto - 2 * r} a{r},{r} 0 0 1 {-r},{r} "
        f"h{-(ancho - r)} Z"
    )


def medidor(
    pct: float | None,
    etiqueta: str,
    texto_valor: str,
    *,
    color: str = "#3b82f6",
    pista: str = "var(--pista)",
    tinta: str = "var(--tinta)",
    tinta_suave: str = "var(--tinta-3)",
    ancho: int = 190,
) -> str:
    """Medidor semicircular: una razón contra su límite.

    Es la forma correcta para "un solo ratio contra un tope" — no un pastel de
    dos porciones. El valor va escrito en el centro: el arco acompaña, no sustituye.
    """
    if pct is None:
        pct = 0.0
    acotado = max(0.0, min(100.0, pct))
    radio = ancho / 2 - 14
    cx, cy = ancho / 2, radio + 14
    largo_arco = 3.14159265 * radio
    avance = largo_arco * acotado / 100.0
    alto = int(cy + 30)

    arco = f"M{cx - radio},{cy} A{radio},{radio} 0 0 1 {cx + radio},{cy}"
    return f"""
<svg class="medidor" viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" role="img"
     aria-label="{_ESCAPE(etiqueta)}: {_ESCAPE(texto_valor)}">
  <path d="{arco}" fill="none" stroke="{pista}" stroke-width="11" stroke-linecap="round"/>
  <path d="{arco}" fill="none" stroke="{color}" stroke-width="11" stroke-linecap="round"
        stroke-dasharray="{avance:.2f} {largo_arco:.2f}"/>
  <text x="{cx}" y="{cy - 4}" text-anchor="middle" class="medidor-valor"
        fill="{tinta}">{_ESCAPE(texto_valor)}</text>
  <text x="{cx}" y="{cy + 20}" text-anchor="middle" class="medidor-etiqueta"
        fill="{tinta_suave}">{_ESCAPE(etiqueta)}</text>
</svg>"""


def barras_horizontales(
    barras: tuple[Barra, ...],
    *,
    ancho: int = 560,
    pista: str = "var(--pista)",
    tinta: str = "var(--tinta)",
    tinta_suave: str = "var(--tinta-2)",
) -> str:
    """Barras horizontales con etiqueta y valor escritos en cada fila.

    Horizontal porque los nombres de categoría son largos ("Pérdida de
    competencia", "Validación inicial saldo pendiente"): en vertical se giran
    y dejan de leerse.
    """
    barras = tuple(b for b in barras if b.valor is not None)
    if not barras:
        return ""

    alto_fila, espacio = 26, 10
    # La columna de etiquetas se dimensiona para la etiqueta más larga que usa
    # este informe ("Validación pendiente (VP)", "Pérdida de competencia"). El
    # texto escala con el viewBox, así que una columna justa se desborda en
    # cuanto el SVG se dibuja a ancho completo —como pasa en el PDF.
    ancho_etiqueta = 204
    ancho_valor = 78
    ancho_pista = ancho - ancho_etiqueta - ancho_valor
    maximo = max((b.valor for b in barras), default=0) or 1
    alto = len(barras) * (alto_fila + espacio)

    filas: list[str] = []
    for i, b in enumerate(barras):
        y = i * (alto_fila + espacio)
        largo = max(0.0, (b.valor / maximo) * ancho_pista)
        titulo = f"{b.etiqueta}: {b.valor_texto}" + (f" · {b.nota}" if b.nota else "")
        filas.append(f"""
  <g class="fila-barra">
    <title>{_ESCAPE(titulo)}</title>
    <text x="0" y="{y + alto_fila * 0.72}" class="barra-etiqueta"
          fill="{tinta_suave}">{_ESCAPE(b.etiqueta)}</text>
    <rect x="{ancho_etiqueta}" y="{y + 4}" width="{ancho_pista}" height="{alto_fila - 8}"
          rx="3" fill="{pista}"/>
    <path d="{_ruta_barra_redondeada(ancho_etiqueta, y + 4, largo, alto_fila - 8)}" fill="{b.color}"/>
    <text x="{ancho}" y="{y + alto_fila * 0.72}" text-anchor="end"
          class="barra-valor" fill="{tinta}">{_ESCAPE(b.valor_texto)}</text>
  </g>""")

    return (
        f'<svg class="barras" viewBox="0 0 {ancho} {alto}" width="100%" height="{alto}" '
        f'preserveAspectRatio="xMinYMin meet" role="img">{"".join(filas)}</svg>'
    )


def barra_apilada(segmentos: tuple[Barra, ...], *, ancho: int = 560, alto: int = 34) -> str:
    """Una sola barra apilada: reparto de un total entre partes que suman 100%.

    Entre segmentos se deja un hueco de 2px del color de la superficie, para que
    dos tonos contiguos no se lean como un bloque continuo.
    """
    segmentos = tuple(s for s in segmentos if s.valor and s.valor > 0)
    if not segmentos:
        return ""
    total = sum(s.valor for s in segmentos) or 1
    hueco = 2.0

    piezas: list[str] = []
    x = 0.0
    for i, s in enumerate(segmentos):
        bruto = (s.valor / total) * ancho
        es_ultimo = i == len(segmentos) - 1
        w = max(0.0, bruto - (0 if es_ultimo else hueco))
        pct = s.valor / total * 100
        piezas.append(f"""
  <g class="segmento">
    <title>{_ESCAPE(s.etiqueta)}: {_ESCAPE(s.valor_texto)} ({pct:.1f}%)</title>
    <rect x="{x:.2f}" y="0" width="{w:.2f}" height="{alto}" fill="{s.color}"
          rx="{3 if (i == 0 or es_ultimo) else 0}"/>
  </g>""")
        x += bruto

    return (
        f'<svg class="apilada" viewBox="0 0 {ancho} {alto}" width="100%" height="{alto}" '
        f'preserveAspectRatio="none" role="img">{"".join(piezas)}</svg>'
    )


def leyenda(segmentos: tuple[Barra, ...]) -> str:
    """Leyenda siempre presente desde 2 series. El texto va en tinta normal,
    nunca pintado del color de la serie."""
    segmentos = tuple(s for s in segmentos if s.valor)
    if len(segmentos) < 2:
        return ""
    chips = "".join(
        f'<span class="chip-leyenda"><i style="background:{s.color}"></i>'
        f"{_ESCAPE(s.etiqueta)} <b>{_ESCAPE(s.valor_texto)}</b></span>"
        for s in segmentos
    )
    return f'<div class="leyenda">{chips}</div>'

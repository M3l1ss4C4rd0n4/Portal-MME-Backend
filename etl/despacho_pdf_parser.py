"""
═══════════════════════════════════════════════════════════════════════════════
Extracción de disponibilidad de plantas y precio de predespacho ideal desde el
informe diario "Seguimiento de Despacho" de XM (PDF ya sincronizado vía
OneDrive/SharePoint).

A diferencia de la gráfica de Senda de Referencia (ver senda_pdf_parser.py),
aquí NO hace falta procesar ninguna imagen: la narrativa relevante es texto
vectorial real y seleccionable en el PDF, con un patrón estable día a día:

    "Para mañana jul-07 hay 51 recursos despachados centralmente con
     disponibilidad menor a 100%. De ellos, los siguientes 7 recursos no
     tendrán disponibilidad: -> Indisponible por mantenimiento CARTAGENA 1,
     ... -> Indisponible sin mantenimiento registrado SALTO II."

    "Para los días jul-05, jul-06 y jul-07, el promedio de los precios de
     oferta de los recursos marginales del predespacho ideal es:
     809.64COP/kWh, 991.226COP/kWh y 753.526COP/kWh respectivamente."

La tabla detallada de disponibilidad por agente y la tabla horaria de precios
SÍ son imágenes rasterizadas, pero no se necesitan: el resumen narrativo ya es
el dato operativo útil (conteo, nombres y motivo de indisponibilidad; precio
promedio por día, incluido el día siguiente).
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

_MESES_ABR = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

_RE_RESUMEN = re.compile(
    r"Para \w+ ([a-z]{3})-(\d{2}) hay (\d+) recursos despachados centralmente "
    r"con disponibilidad menor a 100%",
    re.IGNORECASE,
)
_RE_NO_TENDRAN = re.compile(
    r"los siguientes \d+ recursos no tendr[aá]n disponibilidad:\s*(.+?)(?=Nota:|$)",
    re.IGNORECASE | re.DOTALL,
)
_RE_POR_MANTENIMIENTO = re.compile(
    r"->\s*Indisponible por mantenimiento\s+([^.]+)\.", re.IGNORECASE
)
_RE_SIN_REGISTRAR = re.compile(
    r"->\s*Indisponible sin mantenimiento registrado\s+([^.]+)\.", re.IGNORECASE
)

_RE_PREDESPACHO = re.compile(
    r"Para los d[ií]as ([a-z]{3})-(\d{2}),\s*([a-z]{3})-(\d{2}) y ([a-z]{3})-(\d{2}),"
    r".*?predespacho ideal es:\s*([\d.]+)COP/kWh,\s*([\d.]+)COP/kWh y ([\d.]+)COP/kWh",
    re.IGNORECASE | re.DOTALL,
)


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def _fecha_desde_abrev(mes_abr: str, dia_str: str, fecha_referencia: date) -> Optional[date]:
    mes = _MESES_ABR.get(mes_abr.lower())
    if mes is None:
        return None
    anio = fecha_referencia.year
    # Si el mes descrito es diciembre pero el informe se publicó en enero,
    # la fecha descrita es del año anterior (o viceversa para el caso opuesto).
    if mes == 12 and fecha_referencia.month == 1:
        anio -= 1
    elif mes == 1 and fecha_referencia.month == 12:
        anio += 1
    try:
        return date(anio, mes, int(dia_str))
    except ValueError:
        return None


@dataclass
class Indisponibilidades:
    fecha: date
    total_recursos_disp_menor_100: int
    recursos: list[tuple[str, str]]  # (nombre_recurso, 'MANTENIMIENTO' | 'SIN_REGISTRAR')


def extraer_indisponibilidades(
    texto_pdf: str, fecha_publicacion: date
) -> Optional[Indisponibilidades]:
    """Resumen de disponibilidad de plantas desde el texto real del PDF.

    Devuelve None (no excepción) si el patrón no matchea — un cambio menor de
    redacción de XM no debe tumbar toda la corrida, solo esa parte.
    """
    texto = _normalizar(texto_pdf)

    m_resumen = _RE_RESUMEN.search(texto)
    if not m_resumen:
        return None
    fecha = _fecha_desde_abrev(m_resumen.group(1), m_resumen.group(2), fecha_publicacion)
    if fecha is None:
        return None
    total = int(m_resumen.group(3))

    m_bloque = _RE_NO_TENDRAN.search(texto)
    if not m_bloque:
        return Indisponibilidades(fecha=fecha, total_recursos_disp_menor_100=total, recursos=[])

    bloque = m_bloque.group(1)
    recursos: list[tuple[str, str]] = []
    for m in _RE_POR_MANTENIMIENTO.finditer(bloque):
        for nombre in m.group(1).split(","):
            nombre = nombre.strip()
            if nombre:
                recursos.append((nombre, "MANTENIMIENTO"))
    for m in _RE_SIN_REGISTRAR.finditer(bloque):
        for nombre in m.group(1).split(","):
            nombre = nombre.strip()
            if nombre:
                recursos.append((nombre, "SIN_REGISTRAR"))

    return Indisponibilidades(fecha=fecha, total_recursos_disp_menor_100=total, recursos=recursos)


def extraer_precios_predespacho(
    texto_pdf: str, fecha_publicacion: date
) -> list[tuple[date, float]]:
    """Precio promedio de oferta del recurso marginal del predespacho ideal,
    por día (incluye el día siguiente — señal de precio a futuro).

    Devuelve lista vacía (no excepción) si el patrón no matchea ese día.
    """
    texto = _normalizar(texto_pdf)
    m = _RE_PREDESPACHO.search(texto)
    if not m:
        return []

    pares_fecha = [(m.group(1), m.group(2)), (m.group(3), m.group(4)), (m.group(5), m.group(6))]
    valores = [float(m.group(7)), float(m.group(8)), float(m.group(9))]

    resultado: list[tuple[date, float]] = []
    for (mes_abr, dia_str), valor in zip(pares_fecha, valores):
        fecha = _fecha_desde_abrev(mes_abr, dia_str, fecha_publicacion)
        if fecha is not None:
            resultado.append((fecha, valor))
    return resultado

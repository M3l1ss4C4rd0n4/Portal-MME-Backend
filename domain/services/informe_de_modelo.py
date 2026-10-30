"""Modelo de datos del Informe Semanal de Dirección de Energía.

Separado del recolector y del render para que los tres se puedan probar sueltos.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

# Formatos de presentación. El valor se guarda SIEMPRE crudo; el formato se
# aplica al renderizar, para que el snapshot semanal sea comparable entre semanas.
Formato = Literal["cop", "cop_corto", "pct", "num", "num1", "texto"]


@dataclass(frozen=True)
class Kpi:
    """Un indicador del informe.

    `clave` es el identificador estable que viaja al snapshot: cambiarla rompe
    la serie histórica de ese indicador. `etiqueta` es lo que lee la persona y
    se puede reescribir sin consecuencias.
    """

    clave: str
    etiqueta: str
    valor: float | None
    formato: Formato = "num"
    unidad: str = ""
    detalle: str = ""
    # Si subir es bueno (↑ verde) o malo (↑ rojo). None = neutro, sin color.
    sentido: Literal["mas_es_mejor", "menos_es_mejor", "neutro"] = "neutro"
    # Delta contra la foto anterior. Lo llena el recolector, no la fuente.
    delta: float | None = None
    dias_delta: int | None = None

    def con_delta(self, anterior: float | None, dias: int | None) -> "Kpi":
        """Devuelve una copia con el delta calculado. No muta el original."""
        if anterior is None or self.valor is None:
            return self
        return replace(self, delta=self.valor - anterior, dias_delta=dias)


@dataclass(frozen=True)
class Punto:
    """Un dato de una serie. `rol` dice QUÉ ES, no de qué color va.

    El color lo decide el render según el modo (claro para el PDF, oscuro para
    el HTML), así que aquí nunca se guarda un hex.
    """

    etiqueta: str
    valor: float | None
    # "paso-0".."paso-3" = escalón de la rampa secuencial (etapa ordenada).
    # "neutro" = resto sin significado propio. "critico"/"alerta"/"bien" = estado.
    rol: str = "paso-0"
    valor_texto: str = ""
    nota: str = ""


@dataclass(frozen=True)
class Serie:
    """Datos de una gráfica, SIN pintar."""

    clave: str
    titulo: str
    tipo: Literal["barras", "apilada", "medidores"]
    puntos: tuple[Punto, ...]
    rampa: Literal["azul", "oro"] = "azul"
    nota: str = ""


@dataclass(frozen=True)
class Grafica:
    """Una gráfica ya renderizada como SVG, lista para HTML y para PDF."""

    titulo: str
    svg: str
    nota: str = ""


@dataclass(frozen=True)
class Seccion:
    clave: str
    titulo: str
    subtitulo: str
    corte: str
    kpis: tuple[Kpi, ...]
    # Nombre breve para la tarjeta de portada, donde cinco títulos largos
    # desalinean la fila. Vacío = se usa `titulo`.
    titulo_corto: str = ""
    series: tuple[Serie, ...] = ()
    # Frase de lectura: qué hay que mirar en esta sección. Se calcula en código
    # a partir de los números, nunca se redacta a mano con valores quemados.
    lectura: str = ""
    # Tableros del portal que esta sección resume, para la trazabilidad.
    tableros: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class Informe:
    fecha: str
    generado_en: str
    secciones: tuple[Seccion, ...]

    @property
    def secciones_ok(self) -> tuple[Seccion, ...]:
        return tuple(s for s in self.secciones if not s.error)

    @property
    def fallidas(self) -> tuple[Seccion, ...]:
        return tuple(s for s in self.secciones if s.error)


def kpis_planos(secciones: Sequence[Seccion]) -> list[tuple[str, Kpi]]:
    """Aplana (sección, kpi) para escribir el snapshot en un solo INSERT."""
    return [
        (seccion.clave, kpi)
        for seccion in secciones
        if not seccion.error
        for kpi in seccion.kpis
        if kpi.valor is not None
    ]

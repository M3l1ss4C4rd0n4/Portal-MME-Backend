"""Foto semanal de los KPI del informe y cálculo de la variación.

Los tableros del portal solo exponen el estado vigente: ninguno guarda el valor
de la semana pasada. Sin esta foto, el informe sería la misma pantalla repetida.

Por eso la generación corre UNA vez por semana y no todos los días: la foto
anterior tiene que ser la del viernes pasado. Si la tarea corriera a diario, la
foto más reciente sería la de ayer y la variación "semanal" valdría un día.

La comparación de fechas se hace aquí, en código y en SQL — nunca se delega a un
juicio probabilístico: decidir si una fecha es anterior a otra es aritmética.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Sequence

from psycopg2.extras import execute_values

from dataclasses import replace

from domain.services.informe_de_modelo import Seccion, kpis_planos

logger = logging.getLogger(__name__)

_TABLA = "public.informe_de_snapshot"


def _conexion():
    from infrastructure.database.connection import PostgreSQLConnectionManager

    return PostgreSQLConnectionManager().get_connection()


def guardar_snapshot(fecha: date, secciones: Sequence[Seccion]) -> int:
    """Escribe (o reescribe) la foto de la semana. Devuelve cuántas filas guardó.

    Borra e inserta dentro de una sola transacción en vez de hacer upsert. El
    upsert dejaba huérfana para siempre la fila de un indicador renombrado o
    retirado: ninguna lectura la reclamaba y ningún `ON CONFLICT` la tocaba.
    Así la foto queda idéntica al informe que la acompaña, ni una fila de más.

    Es idempotente: correr la tarea dos veces el mismo día deja el mismo estado.
    """
    filas = [
        (fecha, seccion_clave, kpi.clave, kpi.valor, kpi.unidad or kpi.formato, kpi.etiqueta)
        for seccion_clave, kpi in kpis_planos(secciones)
    ]
    if not filas:
        # Sin esta guarda, un viernes en que TODAS las fuentes fallan borraría
        # la foto y dejaría al informe siguiente sin nada con que comparar.
        logger.warning(
            "[INFORME DE] Ningún KPI que guardar para %s: se conserva la foto previa",
            fecha,
        )
        return 0

    with _conexion() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {_TABLA} WHERE fecha = %s", (fecha,))
            execute_values(
                cur,
                f"""
                INSERT INTO {_TABLA} (fecha, seccion, kpi, valor, unidad, etiqueta)
                VALUES %s
                """,
                filas,
            )
        # El gestor de conexiones hace reset() en el finally, y reset() revierte
        # cualquier transacción abierta. Sin este commit explícito el borrado y
        # el INSERT se perderían en silencio.
        conn.commit()

    logger.info("[INFORME DE] Snapshot %s guardado: %d indicadores", fecha, len(filas))
    return len(filas)


def leer_snapshot_anterior(fecha: date) -> tuple[date | None, dict[tuple[str, str], float]]:
    """Devuelve la foto completa más reciente ANTERIOR a `fecha`.

    Se toma la fecha más reciente previa en vez de "hace 7 días" a secas: si un
    viernes festivo la tarea no corrió, se compara contra el viernes anterior y
    el informe dice explícitamente cuántas semanas cubre el delta.
    """
    with _conexion() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT MAX(fecha) FROM {_TABLA} WHERE fecha < %s",
                (fecha,),
            )
            fila = cur.fetchone()
            anterior = fila[0] if fila else None
            if anterior is None:
                return None, {}

            cur.execute(
                f"SELECT seccion, kpi, valor FROM {_TABLA} WHERE fecha = %s",
                (anterior,),
            )
            valores = {
                (seccion, kpi): float(valor)
                for seccion, kpi, valor in cur.fetchall()
                if valor is not None
            }

    return anterior, valores


def aplicar_deltas(
    secciones: Iterable[Seccion],
    fecha: date,
    anterior: date | None,
    valores: dict[tuple[str, str], float],
) -> tuple[Seccion, ...]:
    """Devuelve secciones NUEVAS con el delta puesto. No muta las originales."""
    dias = (fecha - anterior).days if anterior else None

    resultado: list[Seccion] = []
    for seccion in secciones:
        if seccion.error:
            resultado.append(seccion)
            continue
        kpis_con_delta = tuple(
            kpi.con_delta(valores.get((seccion.clave, kpi.clave)), dias)
            for kpi in seccion.kpis
        )
        # replace() copia el resto de campos tal cual: añadir un campo nuevo a
        # Seccion no obliga a tocar esta función.
        resultado.append(replace(seccion, kpis=kpis_con_delta))
    return tuple(resultado)


def historico_kpi(seccion: str, kpi: str, dias: int = 30) -> list[tuple[date, float]]:
    """Serie de un indicador para dibujar su minigráfica de tendencia."""
    with _conexion() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT fecha, valor
                  FROM {_TABLA}
                 WHERE seccion = %s AND kpi = %s AND valor IS NOT NULL
                   AND fecha >= CURRENT_DATE - %s::int
                 ORDER BY fecha
                """,
                (seccion, kpi, dias),
            )
            return [(f, float(v)) for f, v in cur.fetchall()]

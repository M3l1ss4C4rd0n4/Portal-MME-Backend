"""
Repositorio de datos para el tablero Balance Oferta-Demanda del SIN.

Notas de calidad de datos verificadas directamente contra la base real
(2026-09-23), y backfill histórico ejecutado el mismo día tras confirmar
contra la API de XM (pydataxm.ReadDB) que la falta de historia anterior a
2020/2026 NO era una limitación de XM sino simplemente ETL nunca
backfillado — ver scripts/backfill_historico_xm_2000_2020.py:

- `DispoDeclarada` (MW, entidad='Recurso'): cobertura diaria completa desde
  2000-01-01 (backfill 2000-2019 corrido el 2026-09-23; 2020+ ya existía).
  Es la métrica usada como "oferta operativa" histórica.
- `DemaReal` (GWh/día, entidad='Sistema'): cobertura diaria completa (0 días
  faltantes verificado) desde 2000-01-01.
- `Gene` (GWh/día, entidad='Sistema'): cobertura desde 2000-01-01, expuesta
  como serie de contexto adicional (generación real, no oferta potencial).
- `CapEfecNeta` (Recurso): documentada como MW en etl/config_metricas.py
  pero el valor crudo de XM está en kW (verificado: Guavio/GVIO = 1 250 000
  = 1250 MW) — de ahí el `/ 1000.0` en get_capacidad_instalada_actual_mw().
  Además se encontró un bug de datos real: un puñado de filas de 2021
  habían quedado con el valor dividido por 1 000 000 (de una implementación
  de ETL anterior) y luego un vacío casi total 2021-2026. El backfill
  2026-09-23 re-descargó TODO el rango 2000-hoy y el upsert corrigió esas
  filas viejas — pero este repositorio sigue exponiendo solo el snapshot
  más reciente (no una serie), porque un margen de capacidad NOMINAL
  (instalada) es una lectura distinta de un margen OPERATIVO (disponible
  hoy) y añadir esa tercera serie queda fuera del alcance actual.
- `ENFICC`/`ObligEnerFirme` (Recurso, GWh/día): el mecanismo OFICIAL de
  adecuación de oferta de la CREG (Cargo por Confiabilidad, Res. 071/2006)
  — energía firme certificada vs. obligación de energía firme (que escala
  con demanda proyectada). Backfill 2026-09-23 desde 2007-01-01 (antes:
  solo 8 meses en la base). A diferencia del margen operativo de
  DispoDeclarada (cálculo propio), este SÍ es un indicador regulado —
  ver la nota que expone el servicio de dominio.
- No existe desagregación regional para generación/capacidad/disponibilidad
  (catalogos.region y ontologia.dim_recurso.region están vacíos en toda la
  base). La única serie con desagregación por área operativa es demanda no
  atendida (DemaNoAtenProg/DemaNoAtenNoProg, entidad='Area').
"""

from datetime import date
from typing import Any, Dict, List, Optional

from infrastructure.database.repositories.base_repository import BaseRepository

FECHA_INICIO_DISPO_CONFIABLE = date(2000, 1, 1)
FECHA_INICIO_DEMANDA_CONFIABLE = date(2000, 1, 1)
FECHA_INICIO_GENERACION = date(2000, 1, 1)
FECHA_INICIO_ENFICC_CONFIABLE = date(2007, 1, 1)


class BalanceOfertaDemandaRepository(BaseRepository):
    """Solo lectura sobre sector_energetico.metrics para el balance oferta-demanda."""

    def get_serie_diaria_oferta_demanda(
        self, fecha_inicio: date, fecha_fin: date
    ) -> List[Dict[str, Any]]:
        """
        Serie diaria nacional: oferta declarada (MW), demanda real (GWh),
        generación real (GWh) y el margen regulatorio oficial ENFICC/OEF
        (GWh, entidad='Recurso' agregada) — cada columna puede tener NULL
        si esa fecha está fuera de la cobertura de esa métrica en particular
        (ENFICC/OEF: desde 2007-01-01, ver FECHA_INICIO_ENFICC_CONFIABLE).

        FILTRO DE DÍAS PARCIALES (2026-09-23): XM publica sus datos de forma
        incremental durante el día — si el ETL corre antes de que termine de
        publicarse el día completo, demanda_real_gwh/enficc_gwh/oef_gwh
        quedan con una fracción del valor real (visto en vivo: 2026-09-19/20
        con ~43 GWh de demanda vs. ~250 GWh normales), lo que dispara un
        pico artificial en el margen (oferta casi normal ÷ demanda
        artificialmente baja). Se descartan como NULL los valores por debajo
        de un piso físicamente imposible para un día completo — 100 GWh de
        demanda nacional (el mínimo real histórico son los ~94-99 GWh de
        festivos de 2001-2003, nunca por debajo de eso desde entonces) y
        0 GWh exacto para ENFICC/OEF (la obligación nunca es legítimamente
        cero). Mismo criterio que ya usa api/v1/routes/sector_snapshot.py
        para descartar lecturas parciales del día corriente.
        """
        # NOTA DE RENDIMIENTO (2026-09-23, tras el backfill que llevó
        # sector_energetico.metrics a 49.6M filas): agregar esto EN VIVO
        # sobre metrics tomaba 4-9s por request (Parallel Seq Scan — el
        # rango completo 2000-hoy toca ~40M de las 49.6M filas, así que
        # ningún índice evita el escaneo). Suficiente para agotar el
        # timeout de 15s del BFF cuando el frontend dispara varias consultas
        # en paralelo, dejando el tablero sin datos. Se movió a la tabla
        # precalculada sector_energetico.balance_oferta_demanda_diario
        # (migración 044, ~9800 filas) — repoblar con
        # scripts/refrescar_balance_oferta_demanda_diario.py tras un nuevo
        # backfill o periódicamente (cron) para los días nuevos.
        query = """
            SELECT fecha, oferta_declarada_mw,
                   CASE WHEN demanda_real_gwh >= 100 THEN demanda_real_gwh END AS demanda_real_gwh,
                   generacion_real_gwh,
                   CASE WHEN enficc_gwh > 0 THEN enficc_gwh END AS enficc_gwh,
                   CASE WHEN oef_gwh > 0 THEN oef_gwh END AS oef_gwh
            FROM sector_energetico.balance_oferta_demanda_diario
            WHERE fecha BETWEEN %(inicio)s AND %(fin)s
            ORDER BY fecha
        """
        return self.execute_query(query, {"inicio": fecha_inicio, "fin": fecha_fin})

    def get_capacidad_instalada_actual_mw(self) -> Optional[Dict[str, Any]]:
        """
        Capacidad efectiva neta nominal (MW) en la fecha más reciente con
        datos — snapshot puntual, no serie histórica (aunque la BD ya tiene
        historia completa desde 2000 tras el backfill del 2026-09-23; no se
        expone como serie porque es una lectura de "capacidad instalada",
        distinta del margen operativo/regulatorio ya cubiertos). Corrige la
        unidad real almacenada (kW) dividiendo entre 1000.
        """
        query = """
            SELECT fecha::date AS fecha, SUM(valor_gwh) / 1000.0 AS capacidad_mw
            FROM sector_energetico.metrics
            WHERE metrica = 'CapEfecNeta' AND entidad = 'Recurso'
              AND fecha = (
                  SELECT MAX(fecha) FROM sector_energetico.metrics
                  WHERE metrica = 'CapEfecNeta' AND entidad = 'Recurso'
              )
            GROUP BY fecha::date
        """
        return self.execute_query_one(query)

    def get_demanda_no_atendida_diaria_por_area(
        self, fecha_inicio: date, fecha_fin: date
    ) -> List[Dict[str, Any]]:
        """
        Único desagregado regional disponible hoy: demanda no atendida
        (programada + no programada) por área operativa, GWh/día.

        BUG DE DATOS encontrado y corregido aquí (2026-09-23): el valor
        crudo que XM devuelve para DemaNoAtenProg/NoProg está en kWh. Hasta
        el 2026-02-28 la ETL nunca aplicó la conversión a GWh que su propia
        configuración documenta (etl/config_metricas.py: "Suma 24 horas →
        GWh") — verificado contra la API de XM (AREA NORDESTE 2024-09-17 =
        6 678 540 crudo = 6.68 GWh reales, no 6.68 millones de GWh). Desde
        el 2026-03-01 la ETL SÍ convierte correctamente (verificado: valores
        ya en el rango físico esperado, ~0.0-0.7 GWh/día) — dividir de nuevo
        esas filas por error las dejaba ~1 millón de veces más pequeñas de
        lo real (se veían como una línea plana en cero). La frontera exacta
        entre ambos períodos se confirmó fila por fila: 2026-02-28 (crudo,
        sin convertir) → 2026-03-01 (ya convertido). Se corrige aquí, según
        la fecha, no en el dato almacenado.
        """
        query = """
            SELECT fecha::date AS fecha,
                   recurso AS area_operativa,
                   SUM(CASE WHEN metrica = 'DemaNoAtenProg'
                            THEN valor_gwh / (CASE WHEN fecha < '2026-03-01' THEN 1000000.0 ELSE 1.0 END)
                            ELSE 0 END) AS no_atendida_programada_gwh,
                   SUM(CASE WHEN metrica = 'DemaNoAtenNoProg'
                            THEN valor_gwh / (CASE WHEN fecha < '2026-03-01' THEN 1000000.0 ELSE 1.0 END)
                            ELSE 0 END) AS no_atendida_no_programada_gwh
            FROM sector_energetico.metrics
            WHERE entidad = 'Area'
              AND metrica IN ('DemaNoAtenProg', 'DemaNoAtenNoProg')
              AND fecha::date BETWEEN %(inicio)s AND %(fin)s
            GROUP BY fecha::date, recurso
            ORDER BY fecha::date, recurso
        """
        return self.execute_query(query, {"inicio": fecha_inicio, "fin": fecha_fin})

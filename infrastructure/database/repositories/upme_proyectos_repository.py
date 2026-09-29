"""
Repositorio de datos para sector_energetico.upme_proyectos_expansion.

Ver sql/migrations/043_upme_proyectos_expansion.sql para el contexto: no
existe una API estructurada de UPME, así que estos datos son curados
manualmente (script server/scripts/seed_upme_proyectos_expansion.py) a
partir del Plan de Expansión de Referencia Generación-Transmisión y
seguimiento público — cada fila trae su `fuente`.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from infrastructure.database.repositories.base_repository import BaseRepository

# Únicos donde se definen — api/v1/routes/balance_oferta_demanda.py los importa
# de aquí en vez de redefinirlos, para no tener el mismo enum en dos lugares
# (además del CHECK constraint de la migración 043, que es la tercera fuente
# de verdad y solo cambia si se migra la tabla).
ESTADOS_VALIDOS = {"PLANEADO", "EN_CONSTRUCCION", "RETRASADO", "OPERANDO", "CANCELADO"}
TIPOS_VALIDOS = {"GENERACION", "TRANSMISION"}


class UpmeProyectosRepository(BaseRepository):
    def get_proyectos(
        self,
        tipo: Optional[str] = None,
        tecnologia: Optional[str] = None,
        estado: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filtros = []
        params: Dict[str, Any] = {}
        if tipo:
            filtros.append("tipo = %(tipo)s")
            params["tipo"] = tipo
        if tecnologia:
            filtros.append("tecnologia = %(tecnologia)s")
            params["tecnologia"] = tecnologia
        if estado:
            filtros.append("estado = %(estado)s")
            params["estado"] = estado
        where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
        query = f"""
            SELECT id, nombre_proyecto, tipo, tecnologia, capacidad_mw,
                   departamento, area_operativa,
                   fecha_entrada_planeada_original, fecha_entrada_planeada_vigente,
                   fecha_entrada_real, estado, fuente, notas
            FROM sector_energetico.upme_proyectos_expansion
            {where}
            ORDER BY capacidad_mw DESC NULLS LAST, nombre_proyecto
        """
        return self.execute_query(query, params)

    def upsert_proyecto(self, proyecto: Dict[str, Any]) -> None:
        """
        Inserta o actualiza (por nombre_proyecto, tipo — ver índice único
        uq_upme_proyectos_nombre_tipo en la migración 043) un proyecto —
        usado por el script de siembra de datos reales, no por el tablero.
        Volver a correr el script con datos corregidos actualiza la fila
        existente en vez de duplicarla o no hacer nada.
        """
        if proyecto.get("tipo") not in TIPOS_VALIDOS:
            raise ValueError(f"tipo inválido: {proyecto.get('tipo')!r}")
        if proyecto.get("estado", "PLANEADO") not in ESTADOS_VALIDOS:
            raise ValueError(f"estado inválido: {proyecto.get('estado')!r}")

        query = """
            INSERT INTO sector_energetico.upme_proyectos_expansion (
                nombre_proyecto, tipo, tecnologia, capacidad_mw, departamento,
                area_operativa, fecha_entrada_planeada_original,
                fecha_entrada_planeada_vigente, fecha_entrada_real, estado,
                fuente, notas, actualizado_en
            ) VALUES (
                %(nombre_proyecto)s, %(tipo)s, %(tecnologia)s, %(capacidad_mw)s,
                %(departamento)s, %(area_operativa)s,
                %(fecha_entrada_planeada_original)s, %(fecha_entrada_planeada_vigente)s,
                %(fecha_entrada_real)s, %(estado)s, %(fuente)s, %(notas)s, NOW()
            )
            ON CONFLICT (nombre_proyecto, tipo) DO UPDATE SET
                tecnologia = EXCLUDED.tecnologia,
                capacidad_mw = EXCLUDED.capacidad_mw,
                departamento = EXCLUDED.departamento,
                area_operativa = EXCLUDED.area_operativa,
                fecha_entrada_planeada_original = EXCLUDED.fecha_entrada_planeada_original,
                fecha_entrada_planeada_vigente = EXCLUDED.fecha_entrada_planeada_vigente,
                fecha_entrada_real = EXCLUDED.fecha_entrada_real,
                estado = EXCLUDED.estado,
                fuente = EXCLUDED.fuente,
                notas = EXCLUDED.notas,
                actualizado_en = NOW()
        """
        self.execute_non_query(query, proyecto)

    def get_serie_mensual_mw_retrasado(self, fecha_inicio: date, fecha_fin: date) -> List[Dict[str, Any]]:
        """
        Para cada mes del rango, MW acumulados de proyectos que a esa fecha ya
        habían superado su fecha_entrada_planeada_original sin haber entrado
        en operación real (base del panel de correlación retraso-déficit).
        """
        query = """
            WITH meses AS (
                SELECT generate_series(
                    date_trunc('month', %(inicio)s::date),
                    date_trunc('month', %(fin)s::date),
                    interval '1 month'
                )::date AS mes
            )
            SELECT m.mes,
                   COALESCE(SUM(p.capacidad_mw), 0) AS mw_retrasado_acumulado,
                   COUNT(p.id) AS n_proyectos_retrasados
            FROM meses m
            LEFT JOIN sector_energetico.upme_proyectos_expansion p
              ON p.fecha_entrada_planeada_original IS NOT NULL
             AND p.capacidad_mw IS NOT NULL
             AND p.fecha_entrada_planeada_original <= (m.mes + interval '1 month - 1 day')
             AND (p.fecha_entrada_real IS NULL
                  OR p.fecha_entrada_real > (m.mes + interval '1 month - 1 day'))
            GROUP BY m.mes
            ORDER BY m.mes
        """
        return self.execute_query(query, {"inicio": fecha_inicio, "fin": fecha_fin})

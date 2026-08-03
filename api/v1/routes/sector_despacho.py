"""
Endpoint despacho diario — Portal Dirección EE
GET /v1/sector/despacho → disponibilidad de plantas y precio de predespacho ideal
(sector_energetico.disponibilidad_plantas / precio_predespacho_ideal)
"""

import logging
from fastapi import APIRouter, Depends

from api.dependencies import get_api_key
from infrastructure.database.connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()

_cm = PostgreSQLConnectionManager()


@router.get("/despacho")
async def get_sector_despacho(api_key: str = Depends(get_api_key)):
    with _cm.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT fecha, total_recursos_disp_menor_100, fecha_publicacion
                FROM sector_energetico.disponibilidad_plantas
                WHERE fecha = (SELECT MAX(fecha) FROM sector_energetico.disponibilidad_plantas)
                LIMIT 1
            """)
            row_resumen = cur.fetchone()

            plantas = []
            if row_resumen:
                fecha_plantas = row_resumen[0]
                cur.execute("""
                    SELECT recurso, tipo_indisponibilidad
                    FROM sector_energetico.disponibilidad_plantas
                    WHERE fecha = %s
                    ORDER BY tipo_indisponibilidad, recurso
                """, (fecha_plantas,))
                plantas = [{"recurso": r[0], "tipo": r[1]} for r in cur.fetchall()]

            cur.execute("""
                SELECT fecha, precio_cop_kwh, fecha_publicacion
                FROM sector_energetico.precio_predespacho_ideal
                ORDER BY fecha DESC
                LIMIT 3
            """)
            precios = [
                {"fecha": r[0].isoformat(), "precioCopKwh": float(r[1])}
                for r in cur.fetchall()
            ]
            precios.reverse()  # cronológico ascendente para graficar

    return {
        "disponibilidad": {
            "fecha": row_resumen[0].isoformat() if row_resumen else None,
            "totalRecursosDispMenor100": row_resumen[1] if row_resumen else None,
            "fechaPublicacion": row_resumen[2].isoformat() if row_resumen and row_resumen[2] else None,
            "plantas": plantas,
        },
        "precioPredespachoIdeal": precios,
    }

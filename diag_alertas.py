#!/usr/bin/env python3
"""Diagnóstico de alertas_historial - ejecutar directamente"""
import sys
sys.path.insert(0, '/home/admonctrlxm/server')
from core.config import settings
import psycopg2

conn = psycopg2.connect(
    host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
    database=settings.POSTGRES_DB, user=settings.POSTGRES_USER,
    password=settings.POSTGRES_PASSWORD
)
cur = conn.cursor()

print('=== ALERTAS DE HOY ===')
cur.execute("""
    SELECT id, to_char(fecha_generacion,'HH24:MI'), metrica, severidad,
           LEFT(descripcion,70), notificacion_whatsapp_enviada
    FROM alertas_historial WHERE fecha_evaluacion = CURRENT_DATE
    ORDER BY fecha_generacion DESC LIMIT 20
""")
for r in cur.fetchall():
    print(r)

print()
print('=== COOLDOWN CHECK (demanda excesiva, ultimas 6h) ===')
cur.execute("""
    SELECT COUNT(*) FROM alertas_historial 
    WHERE descripcion ILIKE '%demanda excesiva%'
    AND fecha_generacion >= NOW() - INTERVAL '6 hours'
""")
print('Count encontrado:', cur.fetchone()[0])

print()
print('=== EJEMPLO: busqueda exacta del titulo ===')
cur.execute("""
    SELECT descripcion FROM alertas_historial
    WHERE fecha_evaluacion = CURRENT_DATE AND metrica = 'DEMANDA'
""")
rows = cur.fetchall()
for r in rows:
    print(repr(r[0]))

conn.close()
print('DONE')

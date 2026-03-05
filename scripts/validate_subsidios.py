#!/usr/bin/env python3
"""Quick validation of subsidios data in PostgreSQL."""
import psycopg2

conn = psycopg2.connect(dbname='portal_energetico', user='postgres', host='localhost', port=5432)
cur = conn.cursor()

for t in ['subsidios_pagos', 'subsidios_empresas', 'subsidios_mapa', 'subsidios_import_log']:
    cur.execute('SELECT COUNT(*) FROM ' + t)
    print(t + ': ' + str(cur.fetchone()[0]))

cur.execute("""
    SELECT SUM(valor_resolucion), SUM(valor_pagado), SUM(saldo_pendiente),
           COUNT(DISTINCT nombre_prestador), COUNT(DISTINCT no_resolucion)
    FROM subsidios_pagos
""")
r = cur.fetchone()
print('\nTotal resolucion: ' + str(r[0]))
print('Total pagado: ' + str(r[1]))
print('Total deuda: ' + str(r[2]))
print('Empresas unicas: ' + str(r[3]))
print('Resoluciones unicas: ' + str(r[4]))

cur.execute("SELECT estado_pago, COUNT(*), SUM(saldo_pendiente) FROM subsidios_pagos GROUP BY estado_pago ORDER BY 3 DESC NULLS LAST")
print('\nEstado pago:')
for row in cur.fetchall():
    print('  ' + str(row[0]) + ': ' + str(row[1]) + ' filas, deuda=' + str(row[2]))

conn.close()

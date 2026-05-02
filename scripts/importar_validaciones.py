#!/usr/bin/env python3
"""
Importar hoja 'Validacion' del Excel Base_Subsidios_DDE.xlsx
a subsidios.subsidios_validaciones en portal_energetico.
"""
import sys
import psycopg2
import psycopg2.extras
import openpyxl
from datetime import datetime

EXCEL_PATH = "/home/admonctrlxm/portal-direccion-mme/excels/Base_Subsidios_DDE.xlsx"

def get_conn():
    return psycopg2.connect(
        dbname='portal_energetico',
        user='postgres',
        host='localhost',
        port=5432,
    )

def crear_tabla(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subsidios.subsidios_validaciones (
            id                           SERIAL PRIMARY KEY,
            fecha_actualizacion          TIMESTAMP,
            persona_actualiza            VARCHAR(100),
            fondo                        VARCHAR(10),
            area                         VARCHAR(5),
            anio                         INTEGER,
            trimestre                    INTEGER,
            codigo_sui                   VARCHAR(30),
            nombre_prestador             VARCHAR(250),
            estado_validacion            VARCHAR(20),
            justificacion                TEXT,
            radicado                     VARCHAR(100),
            fecha_radicado               DATE,
            observaciones                TEXT,
            estado_validacion_organizado VARCHAR(20),
            cod_general                  VARCHAR(50),
            fecha_importacion            TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sv_area       ON subsidios.subsidios_validaciones(area)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sv_anio_trim  ON subsidios.subsidios_validaciones(anio, trimestre)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sv_fondo      ON subsidios.subsidios_validaciones(fondo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sv_estado_org ON subsidios.subsidios_validaciones(estado_validacion_organizado)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sv_nombre     ON subsidios.subsidios_validaciones(nombre_prestador)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sv_codigo     ON subsidios.subsidios_validaciones(codigo_sui)")
    cur.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON subsidios.subsidios_validaciones TO mme_user")
    cur.execute("GRANT USAGE, SELECT ON SEQUENCE subsidios.subsidios_validaciones_id_seq TO mme_user")
    print("Tabla subsidios.subsidios_validaciones creada/verificada.")

def normalizar_estado(val):
    """Normaliza variantes de escritura al valor canónico."""
    if val is None:
        return None
    v = str(val).strip()
    mapping = {
        'vf': 'VF', 'Vf': 'VF',
        'vp': 'VP',
        'vi': 'VI', 'Vi': 'VI',
        'vi sp': 'VI SP',
        'n.a.': 'NA', 'n/a': 'NA',
        'r': 'CONSULTAR',
    }
    return mapping.get(v, v.upper() if v else None)

def safe_str(val, max_len=None):
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', 'nat'):
        return None
    return s[:max_len] if max_len else s

def safe_int(val):
    if val is None:
        return None
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return None

def safe_date(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    try:
        from datetime import date
        if isinstance(val, date):
            return val
    except Exception:
        pass
    return None

def importar(cur):
    print(f"Leyendo Excel: {EXCEL_PATH}")
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb['Validacion']
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    data = rows[1:]
    print(f"Filas en Excel: {len(data)}")

    idx = {col: i for i, col in enumerate(header)}

    registros = []
    for r in data:
        # Saltar filas completamente vacías
        if all(v is None for v in r):
            continue

        fecha_act = r[idx['Fecha actualización']]
        if isinstance(fecha_act, datetime):
            fecha_act = fecha_act
        elif fecha_act is None:
            fecha_act = None

        cod_raw = r[idx['Código\nSUI/FSSRI']]
        cod = safe_str(str(int(cod_raw)) if isinstance(cod_raw, float) and cod_raw == int(cod_raw) else cod_raw, 30)

        cod_gen = r[idx['A COD General']]
        cod_gen_str = safe_str(str(int(cod_gen)) if isinstance(cod_gen, float) and cod_gen == int(cod_gen) else cod_gen, 50)

        estado_v = normalizar_estado(r[idx['Estado de Validación']])
        estado_org = safe_str(r[idx['Estado de Validación Organizado']], 20)

        registros.append((
            fecha_act,
            safe_str(r[idx['Persona Actualiza']], 100),
            safe_str(r[idx['Fondo']], 10),
            safe_str(r[idx['Area']], 5),
            safe_int(r[idx['Año']]),
            safe_int(r[idx['Trimestre']]),
            cod,
            safe_str(r[idx['Nombre del Prestador']], 250),
            estado_v,
            safe_str(r[idx['Justificación']]),
            safe_str(r[idx['Radicado']], 100),
            safe_date(r[idx['Fecha Radicado']]),
            safe_str(r[idx['Observaciones']]),
            estado_org,
            cod_gen_str,
        ))

    print(f"Registros válidos a insertar: {len(registros)}")

    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO subsidios.subsidios_validaciones (
            fecha_actualizacion, persona_actualiza, fondo, area, anio, trimestre,
            codigo_sui, nombre_prestador, estado_validacion, justificacion,
            radicado, fecha_radicado, observaciones, estado_validacion_organizado, cod_general
        ) VALUES %s
        """,
        registros,
        page_size=500,
    )
    print(f"Inserción completada: {cur.rowcount} filas.")

def main():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # Verificar si ya hay datos
                crear_tabla(cur)

        # Verificar datos existentes en transacción separada
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM subsidios.subsidios_validaciones")
            existing = cur.fetchone()[0]

        if existing > 0:
            print(f"AVISO: La tabla ya tiene {existing} filas. Limpiando para reimportar...")
            with conn:
                with conn.cursor() as cur:
                    cur.execute("TRUNCATE subsidios.subsidios_validaciones RESTART IDENTITY")

        with conn:
            with conn.cursor() as cur:
                importar(cur)

        print("\n✓ Importación exitosa.")

        # Verificación final
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM subsidios.subsidios_validaciones")
            print(f"Total filas en BD: {cur.fetchone()[0]}")
            cur.execute("""
                SELECT estado_validacion, COUNT(*) FROM subsidios.subsidios_validaciones
                GROUP BY estado_validacion ORDER BY 2 DESC
            """)
            print("\nDistribución estado_validacion:")
            for row in cur.fetchall():
                print(f"  {row[0]}: {row[1]}")
            cur.execute("""
                SELECT estado_validacion_organizado, COUNT(*) FROM subsidios.subsidios_validaciones
                GROUP BY estado_validacion_organizado ORDER BY 2 DESC
            """)
            print("\nDistribución estado_validacion_organizado:")
            for row in cur.fetchall():
                print(f"  {row[0]}: {row[1]}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()

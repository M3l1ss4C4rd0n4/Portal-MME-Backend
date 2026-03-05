#!/usr/bin/env python3
"""
Gestionar usuarios autorizados para consultas de subsidios vía Telegram.

Uso:
    python scripts/gestionar_usuarios_subsidios.py listar
    python scripts/gestionar_usuarios_subsidios.py agregar 123456789 "Diana López" admin
    python scripts/gestionar_usuarios_subsidios.py agregar 123456789 "Oscar Pérez"
    python scripts/gestionar_usuarios_subsidios.py desactivar 123456789
    python scripts/gestionar_usuarios_subsidios.py activar 123456789
"""
import sys
import psycopg2
import psycopg2.extras


def get_conn():
    return psycopg2.connect(
        dbname='portal_energetico',
        user='postgres',
        host='localhost',
        port=5432,
    )


def listar():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM subsidios_usuarios_autorizados ORDER BY fecha_alta")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No hay usuarios autorizados.")
        return
    print(f"{'ID':>4} {'Telegram ID':>12} {'Nombre':<30} {'Rol':<10} {'Activo':<7} {'Alta'}")
    print("-" * 90)
    for r in rows:
        print(f"{r['id']:>4} {r['telegram_id']:>12} {r['nombre'] or ''::<30} {r['rol']:<10} {'Sí' if r['activo'] else 'No':<7} {r['fecha_alta']}")


def agregar(telegram_id, nombre=None, rol='consulta'):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO subsidios_usuarios_autorizados (telegram_id, nombre, rol)
        VALUES (%s, %s, %s)
        ON CONFLICT (telegram_id) DO UPDATE SET
            nombre = COALESCE(EXCLUDED.nombre, subsidios_usuarios_autorizados.nombre),
            rol = EXCLUDED.rol,
            activo = TRUE
        RETURNING id
    """, (int(telegram_id), nombre, rol))
    conn.commit()
    rid = cur.fetchone()[0]
    conn.close()
    print(f"✅ Usuario {telegram_id} ({nombre or 'sin nombre'}) autorizado con rol '{rol}' (ID: {rid})")


def desactivar(telegram_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE subsidios_usuarios_autorizados SET activo = FALSE WHERE telegram_id = %s", (int(telegram_id),))
    conn.commit()
    conn.close()
    print(f"❌ Usuario {telegram_id} desactivado")


def activar(telegram_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE subsidios_usuarios_autorizados SET activo = TRUE WHERE telegram_id = %s", (int(telegram_id),))
    conn.commit()
    conn.close()
    print(f"✅ Usuario {telegram_id} reactivado")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'listar':
        listar()
    elif cmd == 'agregar':
        if len(sys.argv) < 3:
            print("Uso: agregar <telegram_id> [nombre] [rol]")
            sys.exit(1)
        tid = sys.argv[2]
        nombre = sys.argv[3] if len(sys.argv) > 3 else None
        rol = sys.argv[4] if len(sys.argv) > 4 else 'consulta'
        agregar(tid, nombre, rol)
    elif cmd == 'desactivar':
        desactivar(sys.argv[2])
    elif cmd == 'activar':
        activar(sys.argv[2])
    else:
        print(f"Comando desconocido: {cmd}")
        print(__doc__)

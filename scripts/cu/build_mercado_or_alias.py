"""
Fase 40 (Costo Unitario) — curación mercado (XM) -> operador de red (cu_tarifas_or).

MAPEO_CURADO se reconstruyó 2026-08-26 usando la Tabla 26 ("Operadores de
Red y mercados") del Boletín Tarifario SSPD Cuarto Trimestre de 2025
(superservicios.gov.co, publicado jun-2026) — fuente OFICIAL y explícita
del LAC (XM) de qué operador de red corresponde a cada uno de los 28
mercados de comercialización con cargos calculados ese trimestre. Antes de
esta fecha, la primera versión de este mapeo se había curado a mano por
coincidencia de departamento (cu_tarifas_or.departamentos), sin esta tabla
— 3 de esas asignaciones (CAQUETA, POPAYAN-PURACE, BAJO PUTUMAYO) resultaron
INCORRECTAS al contrastarlas contra la Tabla 26 (el operador real de esos
mercados no está en cu_tarifas_or) y se corrigieron a sin_resolver.

Un mercado queda 'sin_resolver' (or_codigo NULL) cuando:
  - la Tabla 26 identifica un operador real para ese mercado, pero ese
    operador NO existe como fila en cu_tarifas_or (ej. GUAVIARE →
    ENERGUAVIARE, TULUA → CETSA, CARTAGO/PEREIRA → EEP — ninguno cargado
    en nuestra tabla, que solo tiene 26 operadores, no los 28+ reales); o
  - el mercado no es geográfico (SIN CLASIFICAR).

Hallazgo colateral de esta verificación (no relacionado con este mapeo,
corregido en la migración 036): cu_tarifas_or.or_nombre/departamentos para
EMSA y ENERCA estaban intercambiados desde antes de esta sesión — EMSA es
Electrificadora del Meta (no Casanare) y ENERCA es Empresa de Energía de
Casanare (no Caquetá/Amazonas), confirmado tanto por la Tabla 26 como por
fuentes externas (BNamericas, sitio oficial de cada empresa).

Tras sembrar el alias, calcula el promedio nacional de D/C/pérdidas
ponderado por la demanda real (DemaCome, entidad=MercadoComercializacion)
de CADA mes, usando SOLO los mercados resueltos — deja explícito qué % de
la demanda nacional real respalda el promedio (cu_componentes_nacionales_
ponderados.pct_demanda_cubierta), sin fingir cobertura del 100%.

Uso:
    python3 scripts/cu/build_mercado_or_alias.py [--dias 400]
"""
import argparse
import logging
import sys
from datetime import date, timedelta
from collections import defaultdict

sys.path.insert(0, ".")

from infrastructure.database.connection import PostgreSQLConnectionManager  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("build_mercado_or_alias")

# ─────────────────────────────────────────────────────────────────────────
# Mapeo curado — reconstruido 2026-08-26 desde la Tabla 26 del Boletín
# Tarifario SSPD 4T-2025 (ver docstring del módulo). metodo:
#   'sspd_tabla26'   → asignación operador↔mercado tomada literalmente de
#                       la Tabla 26 oficial, y el operador SÍ existe en
#                       cu_tarifas_or.
#   'sspd_tabla26_variante_nombre' → la Tabla 26 usa un nombre/código de
#                       operador ligeramente distinto al de cu_tarifas_or,
#                       pero corresponde de forma razonablemente cierta a
#                       la misma entidad real (ver nota de cada caso).
#   'sin_resolver'   → la Tabla 26 identifica el operador real, pero ese
#                       operador no está cargado en cu_tarifas_or (nuestra
#                       tabla solo tiene 26 de los 28+ operadores reales).
# ─────────────────────────────────────────────────────────────────────────
MAPEO_CURADO = {
    "ARAUCA":                    ("ENELAR", "sspd_tabla26", None),
    "BOGOTA - CUNDINAMARCA":     ("CODENSA", "sspd_tabla26_variante_nombre",
                                   "Tabla 26 lista 'ENEL COLOMBIA↔Bogotá Cundinamarca' — "
                                   "ENEL Colombia es la matriz de CODENSA, mismo operador real "
                                   "(fuente ya usada en cu_tarifas_or: ENEL_OFICIAL_2026_01)."),
    "CALDAS":                    ("CHEC", "sspd_tabla26", None),
    "CASANARE":                  ("ENERCA", "sspd_tabla26",
                                   "Corregido 2026-08-26: la Tabla 26 dice 'ENERCA↔Casanare', "
                                   "no EMSA como se había asumido antes de verificar contra la "
                                   "fuente oficial — ver migración 036 (or_nombre de EMSA/ENERCA "
                                   "estaban intercambiados en cu_tarifas_or)."),
    "CAUCA":                     ("CEDELCA", "sspd_tabla26_variante_nombre",
                                   "Tabla 26 dice 'CEO↔Cauca'. CEO (Compañía Energética de "
                                   "Occidente) opera los activos de CEDELCA desde 2010 bajo "
                                   "concesión de 25 años — CEDELCA sigue siendo el titular legal "
                                   "y el nombre bajo el que está cargado en cu_tarifas_or, mismo "
                                   "territorio real (verificado: CEDELCA, BNamericas, gestornormativo.creg.gov.co)."),
    "CHOCO":                     ("DISPAC", "sspd_tabla26", None),
    "NARIÑO":                    ("CEDENAR", "sspd_tabla26", None),
    "NORTE DE SANTANDER":        ("CENS", "sspd_tabla26", None),
    "PUTUMAYO":                  ("EEPSA", "sspd_tabla26_variante_nombre",
                                   "Tabla 26 dice 'EEPUTUMAYO↔Putumayo' — cu_tarifas_or.or_nombre "
                                   "de EEPSA es literalmente 'Empresa de Energía del Putumayo "
                                   "S.A. E.S.P.', mismo territorio, solo difiere el código corto "
                                   "que usa cada fuente."),
    "VALLE DEL SIBUNDOY":        ("EEVS", "sspd_tabla26", None),
    "QUINDIO":                   ("EDEQ", "sspd_tabla26", None),
    "RUITOQUE":                  ("RUITOQUE", "sspd_tabla26", None),
    "SANTANDER":                 ("ESSA", "sspd_tabla26", None),
    "HUILA":                     ("ELECTROHUILA", "sspd_tabla26", None),
    "CALI - YUMBO - PUERTO TEJADA": ("EMCALI", "sspd_tabla26", None),
    "BOYACA":                    ("EBSA", "sspd_tabla26", None),
    "META":                      ("EMSA", "sspd_tabla26",
                                   "Corregido 2026-08-26: la Tabla 26 dice 'EMSA↔Meta' — antes de "
                                   "verificar contra la Tabla 26 este mercado se había dejado "
                                   "sin_resolver por asumir ambigüedad EMETA/ELPICOL, que no era "
                                   "real (ninguno de los 2 es el operador oficial de este mercado)."),
    "TOLIMA":                    ("CELSIA", "sspd_tabla26",
                                   "Tabla 26 lista 'CELSIA COLOMBIA↔Tolima' explícitamente entre "
                                   "los 28 mercados con cargo calculado por el LAC — ENERTOLIMA no "
                                   "aparece en la Tabla 26 en absoluto."),
    "VALLE DEL CAUCA":           ("CELSIA", "sspd_tabla26_variante_nombre",
                                   "Tabla 26 lista 'CELSIA COLOMBIA↔Celsia Valle del Cauca' como "
                                   "mercado separado de 'EMCALI↔Cali' — corresponde al resto del "
                                   "departamento fuera de Cali/Yumbo/Cartago/Tuluá, que es "
                                   "exactamente el mercado XM 'VALLE DEL CAUCA' genérico."),
    # Sin operador identificable en cu_tarifas_or — la Tabla 26 SÍ nombra un
    # operador real para cada uno, pero ninguno de los 5 siguientes está
    # cargado en nuestra tabla de 26 operadores (nunca se sustituye por el
    # operador más parecido — sería un error real, no una aproximación):
    "CAQUETA":                   (None, "sin_resolver",
                                   "Corregido 2026-08-26: Tabla 26 dice 'ELECTROCAQUETÁ↔Caquetá' "
                                   "— un operador DISTINTO de ELECTROHUILA, no cargado en "
                                   "cu_tarifas_or. La asignación anterior (CAQUETA→ELECTROHUILA) "
                                   "era incorrecta, corregida al verificar contra la fuente oficial."),
    "POPAYAN - PURACE":          (None, "sin_resolver",
                                   "Corregido 2026-08-26: Tabla 26 dice 'EMEESA↔Popayán Puracé' "
                                   "— un operador DISTINTO de CEO/CEDELCA, no cargado en "
                                   "cu_tarifas_or. La asignación anterior (→CEDELCA) era "
                                   "incorrecta, corregida al verificar contra la fuente oficial."),
    "BAJO PUTUMAYO":             (None, "sin_resolver",
                                   "Corregido 2026-08-26: Tabla 26 dice 'EEBP↔Bajo Putumayo' — "
                                   "un operador DISTINTO de EEPSA (que cubre 'Putumayo' general), "
                                   "no cargado en cu_tarifas_or."),
    "CARTAGO":                   (None, "sin_resolver",
                                   "Tabla 26: 'EEP↔Cartago' — EEP (Empresa de Energía de "
                                   "Pereira) no está cargado en cu_tarifas_or."),
    "PEREIRA":                   (None, "sin_resolver",
                                   "Tabla 26: 'EEP↔Pereira' — mismo operador que CARTAGO, no "
                                   "cargado en cu_tarifas_or."),
    "TULUA":                     (None, "sin_resolver",
                                   "Tabla 26: 'CETSA↔Tuluá' — CETSA no está cargado en "
                                   "cu_tarifas_or."),
    "CARIBE MAR":                ("CARIBEMAR", "sspd_tabla26_variante_nombre",
                                   "Tabla 26 dice 'CARIBE MAR DE LA COSTA↔Caribe Mar' — "
                                   "cu_tarifas_or.or_nombre de CARIBEMAR es literalmente "
                                   "'Caribémar de la Costa S.A.S. E.S.P.', match exacto."),
    "CARIBE SOL":                ("AIRE", "sspd_tabla26",
                                   "Tabla 26 dice 'AIR-E↔Caribe Sol' — AIR-E = AIRE en "
                                   "cu_tarifas_or (mismo operador, código sin guion)."),
    "GUAVIARE":                  (None, "sin_resolver",
                                   "Tabla 26: 'ENERGUAVIARE↔Guaviare' — no cargado en "
                                   "cu_tarifas_or."),
    "SIN CLASIFICAR":            (None, "sin_resolver", "No es un mercado geográfico."),
}


def _mes_inicio(d: date) -> date:
    return d.replace(day=1)


def seed_alias(mgr: PostgreSQLConnectionManager) -> None:
    upsert_sql = """
        INSERT INTO cu_mercado_or_alias (mercado, or_codigo, metodo, nota)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (mercado) DO UPDATE SET
            or_codigo = EXCLUDED.or_codigo,
            metodo    = EXCLUDED.metodo,
            nota      = EXCLUDED.nota
    """
    with mgr.get_connection() as conn:
        with conn.cursor() as cur:
            for mercado, (or_codigo, metodo, nota) in MAPEO_CURADO.items():
                cur.execute(upsert_sql, (mercado, or_codigo, metodo, nota))
        conn.commit()
    resueltos = sum(1 for v in MAPEO_CURADO.values() if v[0] is not None)
    logger.info(f"Alias sembrado: {resueltos}/{len(MAPEO_CURADO)} mercados resueltos a un operador real")


def calcular_ponderado(mgr: PostgreSQLConnectionManager, dias: int) -> None:
    from pydataxm.pydataxm import ReadDB

    api = ReadDB()
    fin = date.today()
    inicio = fin - timedelta(days=dias)

    # XM limita el rango de consultas horarias multi-entidad — se pide en
    # ventanas de ~30 días y se concatena, igual que hace el resto de los
    # ETLs de este proyecto para MetricUnits horarios de muchas entidades.
    dfs = []
    cursor = inicio
    while cursor <= fin:
        ventana_fin = min(cursor + timedelta(days=29), fin)
        logger.info(f"Descargando DemaCome (MercadoComercializacion) {cursor} → {ventana_fin}")
        try:
            df_ventana = api.request_data(
                "DemaCome", "MercadoComercializacion",
                start_date=cursor.strftime("%Y-%m-%d"),
                end_date=ventana_fin.strftime("%Y-%m-%d"),
            )
            if df_ventana is not None and not df_ventana.empty:
                dfs.append(df_ventana)
        except Exception as e:
            logger.warning(f"Ventana {cursor}→{ventana_fin} falló: {e}")
        cursor = ventana_fin + timedelta(days=1)

    if not dfs:
        logger.error("Sin datos de DemaCome por mercado — abortando ponderación")
        return
    import pandas as pd
    df = pd.concat(dfs, ignore_index=True)

    hour_cols = [c for c in df.columns if c.startswith("Values_Hour")]
    df["kwh_dia"] = df[hour_cols].sum(axis=1)
    df["mes"] = df["Date"].apply(lambda d: _mes_inicio(d.date() if hasattr(d, "date") else d))

    # "Id" es solo el nombre de la entidad ("MercadoComercializacion") —
    # el mercado específico (ANTIOQUIA, ARAUCA, ...) viene en Values_code.
    # Cada mercado/día trae 2 filas (regulado/no regulado, Values_MarketType)
    # que se suman para el total diario del mercado.
    dema_total_mes = defaultdict(float)
    dema_por_mercado_mes = defaultdict(float)
    for _, row in df.iterrows():
        mes = row["mes"]
        mercado = row["Values_code"]
        kwh = float(row["kwh_dia"])
        dema_total_mes[mes] += kwh
        dema_por_mercado_mes[(mes, mercado)] += kwh

    # Datos reales de operador (D, C, pérdidas) desde cu_tarifas_or.
    with mgr.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT or_codigo, d_cop_kwh, c_cop_kwh, perdidas_reconocidas_pct FROM cu_tarifas_or")
            datos_or = {r[0]: (float(r[1]), float(r[2]), float(r[3])) for r in cur.fetchall()}

            cur.execute("SELECT mercado, or_codigo FROM cu_mercado_or_alias WHERE or_codigo IS NOT NULL")
            alias = dict(cur.fetchall())

    meses = sorted(dema_total_mes.keys())
    filas = []
    for mes in meses:
        suma_peso = 0.0
        suma_d = 0.0
        suma_c = 0.0
        suma_perd = 0.0
        n_resueltos = 0
        for mercado, or_codigo in alias.items():
            peso = dema_por_mercado_mes.get((mes, mercado))
            if not peso or or_codigo not in datos_or:
                continue
            d, c, perd = datos_or[or_codigo]
            suma_peso += peso
            suma_d += d * peso
            suma_c += c * peso
            suma_perd += perd * peso
            n_resueltos += 1

        if suma_peso <= 0:
            logger.warning(f"Mes {mes}: sin peso real disponible — se omite")
            continue

        d_pond = suma_d / suma_peso
        c_pond = suma_c / suma_peso
        perd_pond = suma_perd / suma_peso
        pct_cubierta = (suma_peso / dema_total_mes[mes]) * 100.0
        n_sin_resolver = len(MAPEO_CURADO) - len(alias)

        filas.append((mes, d_pond, c_pond, perd_pond, n_resueltos, n_sin_resolver, pct_cubierta))
        logger.info(
            f"{mes}: D={d_pond:.2f} C={c_pond:.2f} pérdidas={perd_pond:.2f}% "
            f"({n_resueltos} mercados, {pct_cubierta:.1f}% de demanda nacional cubierta)"
        )

    if not filas:
        logger.error("Ningún mes con datos suficientes para ponderar")
        return

    upsert_sql = """
        INSERT INTO cu_componentes_nacionales_ponderados
            (mes, d_pond_cop_kwh, c_pond_cop_kwh, perdidas_pond_pct,
             n_mercados_ponderados, n_mercados_sin_resolver, pct_demanda_cubierta)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (mes) DO UPDATE SET
            d_pond_cop_kwh          = EXCLUDED.d_pond_cop_kwh,
            c_pond_cop_kwh          = EXCLUDED.c_pond_cop_kwh,
            perdidas_pond_pct       = EXCLUDED.perdidas_pond_pct,
            n_mercados_ponderados   = EXCLUDED.n_mercados_ponderados,
            n_mercados_sin_resolver = EXCLUDED.n_mercados_sin_resolver,
            pct_demanda_cubierta    = EXCLUDED.pct_demanda_cubierta,
            actualizado_en          = now()
    """
    with mgr.get_connection() as conn:
        with conn.cursor() as cur:
            for fila in filas:
                cur.execute(upsert_sql, fila)
        conn.commit()
    logger.info(f"Guardados {len(filas)} meses en cu_componentes_nacionales_ponderados")

    guardar_pesos_por_or(mgr, alias, dema_por_mercado_mes, dema_total_mes)


def guardar_pesos_por_or(mgr, alias: dict, dema_por_mercado_mes: dict, dema_total_mes: dict) -> None:
    """
    Fase 40 Ronda 3 — agrega el peso de demanda de cada mercado resuelto al
    OPERADOR real que lo sirve (un operador puede cubrir varios mercados,
    ej. CELSIA = TOLIMA + VALLE DEL CAUCA), normaliza a 1.0 entre los
    operadores resueltos ese mes, y guarda en cu_pesos_demanda_or.

    Esto es lo que consume CUMinoristaService.get_promedio_nacional_minorista()
    para ponderar el CU Usuario Final por demanda real en vez de promediar
    con igual peso entre los 26 operadores — reemplaza ese valor en TODOS
    los lugares donde se muestra (home.py, costo_usuario_final.py, portal).
    """
    meses = sorted(dema_total_mes.keys())
    filas_peso = []
    for mes in meses:
        peso_por_or: dict = defaultdict(float)
        for mercado, or_codigo in alias.items():
            peso = dema_por_mercado_mes.get((mes, mercado))
            if not peso:
                continue
            peso_por_or[or_codigo] += peso

        suma_total = sum(peso_por_or.values())
        if suma_total <= 0:
            continue
        pct_cubierta = (suma_total / dema_total_mes[mes]) * 100.0
        for or_codigo, peso_kwh in peso_por_or.items():
            filas_peso.append((mes, or_codigo, peso_kwh / suma_total, peso_kwh, pct_cubierta))

    if not filas_peso:
        logger.error("Sin pesos por operador para guardar")
        return

    upsert_sql = """
        INSERT INTO cu_pesos_demanda_or
            (mes, or_codigo, peso_normalizado, demanda_kwh_mes, pct_demanda_cubierta)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (mes, or_codigo) DO UPDATE SET
            peso_normalizado     = EXCLUDED.peso_normalizado,
            demanda_kwh_mes      = EXCLUDED.demanda_kwh_mes,
            pct_demanda_cubierta = EXCLUDED.pct_demanda_cubierta,
            actualizado_en       = now()
    """
    with mgr.get_connection() as conn:
        with conn.cursor() as cur:
            # Limpiar operadores que ya no aparecen resueltos ese mes (ej. si
            # se corrige el mapeo y un operador deja de estar sin_resolver a
            # resuelto o viceversa) antes de re-insertar.
            meses_tocados = sorted({f[0] for f in filas_peso})
            cur.execute(
                "DELETE FROM cu_pesos_demanda_or WHERE mes = ANY(%s)",
                (meses_tocados,),
            )
            for fila in filas_peso:
                cur.execute(upsert_sql, fila)
        conn.commit()
    logger.info(f"Guardados pesos de {len(filas_peso)} (mes, operador) en cu_pesos_demanda_or")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=400)
    args = parser.parse_args()
    _mgr = PostgreSQLConnectionManager()
    seed_alias(_mgr)
    calcular_ponderado(_mgr, dias=args.dias)

"""
ETL Tarifas OR Mensual — Ingestión del Boletín Tarifario SSPD
=============================================================

Actualiza la tabla cu_tarifas_or con los valores oficiales publicados
mensualmente / trimestralmente por la SSPD y por cada Operador de Red (OR).

La SSPD publica el Boletín Tarifario en PDF cada trimestre:
  https://www.superservicios.gov.co/boletines-tarifarios-de-energia

Cada OR publica su tarifario antes del día 12 de cada mes en su sitio web.

Fuentes principales:
  - SSPD Boletín Tarifario (PDF) → T_STN, T_STR, D, C, pérdidas por OR
  - Enel Colombia (Codensa): tarifario-enel-enero-YYYY.pdf
  - EPM: portal COT mensual
  - Air-e / Afinia: tarifario mensual (requiere login o descarga directa)

Modos de uso
------------
1. Desde CSV (modo más confiable — exportado del PDF tras limpieza manual):
   python etl_tarifas_or_mensual.py --csv tarifas_OR_Q1_2025.csv

2. Desde PDF del Boletín SSPD (parser automático con pdfplumber):
   python etl_tarifas_or_mensual.py --pdf Boletin-tarifario-I-trimestre-2025.pdf

3. Registro manual de un OR (actualización puntual):
   python etl_tarifas_or_mensual.py --manual --or-codigo CODENSA \\
       --t-stn 50.87 --t-str 2.10 --d 292.59 --c 76.46 --r 17.79 \\
       --perdidas 7.19 --fuente ENEL_OFICIAL_2026_01 --vigente-desde 2026-01

4. Sólo actualizar T_STN nacional (mismo para todos los OR):
   python etl_tarifas_or_mensual.py --update-t-stn 52.50

Formato del CSV de entrada
---------------------------
El CSV debe tener estas columnas (nombres exactos):
  or_codigo, t_stn_cop_kwh, t_str_cop_kwh, d_cop_kwh, c_cop_kwh,
  r_restricciones_cop_kwh, perdidas_reconocidas_pct,
  fazni_cop_kwh, faer_cop_kwh, prone_cop_kwh, fuente, vigente_desde

Ejemplo de fila:
  CODENSA,50.87,2.10,292.59,76.46,17.79,7.19,1.2,0.8,0.4,ENEL_OFICIAL_2026_01,2026-01

Tabla destino: cu_tarifas_or (PostgreSQL)
Columnas actualizadas: t_stn_cop_kwh, t_str_cop_kwh, d_cop_kwh, c_cop_kwh,
                       r_restricciones_cop_kwh, perdidas_reconocidas_pct,
                       fazni_cop_kwh, faer_cop_kwh, prone_cop_kwh,
                       fuente, vigente_desde, updated_at

=============================================================================
MAPEO SSPD BOLETÍN → COLUMNAS cu_tarifas_or
=============================================================================

El Boletín Tarifario SSPD tiene secciones por nivel de tensión (NT1-NT4).
Para el usuario residencial (NT1 — Baja Tensión) buscar:

  Tabla "Cargos por uso del SDL"
    Columna "T_STN"    → t_stn_cop_kwh        (mismo para todos los OR)
    Columna "STR"      → t_str_cop_kwh        (específico por OR/AT)
    Columna "D"        → d_cop_kwh            (DTUN del OR, NT1)
    Columna "C"        → c_cop_kwh            (cargo comercialización)
    Columna "R"        → r_restricciones_cop_kwh (restricciones despacho)

  Tabla "Pérdidas reconocidas"
    NT1 por OR         → perdidas_reconocidas_pct

  Tabla "Cargos Sociales"
    FAZNI              → fazni_cop_kwh
    FAER               → faer_cop_kwh
    PRONE              → prone_cop_kwh

=============================================================================
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

# ── Setup de logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("etl_tarifas_or")

# ── Columnas actualizables en cu_tarifas_or ───────────────────────────────────
COLUMNAS_NUMERICAS = [
    "t_stn_cop_kwh",
    "t_str_cop_kwh",
    "d_cop_kwh",
    "c_cop_kwh",
    "r_restricciones_cop_kwh",
    "perdidas_reconocidas_pct",
    "fazni_cop_kwh",
    "faer_cop_kwh",
    "prone_cop_kwh",
]

COLUMNAS_REQUIRED = ["or_codigo"] + COLUMNAS_NUMERICAS + ["fuente", "vigente_desde"]

# Mapeo de alias de OR → codigo canónico en la BD
OR_ALIAS: dict[str, str] = {
    # Andina
    "ENEL": "CODENSA", "CODENSA": "CODENSA", "ENEL COLOMBIA": "CODENSA",
    "EPM": "EPM", "EMPRESAS PUBLICAS DE MEDELLIN": "EPM", "E.P.M.": "EPM",
    "ESSA": "ESSA", "ELECTRIFICADORA DE SANTANDER": "ESSA",
    "CELSIA": "CELSIA", "EPSA": "CELSIA",
    "CHEC": "CHEC", "CENTRAL HIDROELECTRICA DE CALDAS": "CHEC",
    "EBSA": "EBSA", "ELECTRIFICADORA DE BOYACA": "EBSA",
    "ELECTROHUILA": "ELECTROHUILA", "ELECTRIFICADORA DEL HUILA": "ELECTROHUILA",
    "ENERTOLIMA": "ENERTOLIMA",
    "CENS": "CENS", "CENTRALES ELECTRICAS DEL NORTE": "CENS",
    "EMCALI": "EMCALI",
    "RUITOQUE": "RUITOQUE",
    "VATIA": "VATIA",
    "EDEQ": "EDEQ", "EMPRESA DE ENERGIA DEL QUINDIO": "EDEQ",
    # Caribe
    "AIR-E": "AIRE", "AIRE": "AIRE", "AIR E": "AIRE",
    "AFINIA": "AFINIA",
    "CARIBEMAR": "CARIBEMAR", "CARIBEMAR DE LA COSTA": "CARIBEMAR", "CARIBEMAR": "CARIBEMAR",
    # Pacifico
    "CEDENAR": "CEDENAR", "CENTRALES ELECTRICAS DE NARINO": "CEDENAR",
    "CEDELCA": "CEDELCA",
    "DISPAC": "DISPAC",
    # Orinoquia
    "EMSA": "EMSA", "EMPRESA DE ENERGIA DEL CASANARE": "EMSA",
    "ELPICOL": "ELPICOL",
    "ENELAR": "ENELAR", "EMPRESA DE ENERGIA DE ARAUCA": "ENELAR",
    "EMETA": "EMETA", "ELECTRIFICADORA DEL META": "EMETA", "EMEVASI": "EMETA",
    # Amazonia
    "ENERCA": "ENERCA", "EMPRESA DE ENERGIA DEL CAQUETA": "ENERCA",
    "EEVS": "EEVS", "SIBUNDOY": "EEVS", "VALLE DE SIBUNDOY": "EEVS",
    "EEPSA": "EEPSA", "EMPRESA DE ENERGIA DEL PUTUMAYO": "EEPSA",
}


# ─────────────────────────────────────────────────────────────────────────────
# Parseo de PDF del Boletín SSPD
# ─────────────────────────────────────────────────────────────────────────────

def _parsear_pdf_boletin(pdf_path: Path) -> pd.DataFrame:
    """
    Parsea el Boletín Tarifario SSPD en PDF usando pdfplumber.

    Busca las tablas de "Cargos por uso del SDL" y "Pérdidas reconocidas"
    correspondientes a NT1 (Nivel de Tensión 1 — Baja Tensión).

    Returns DataFrame con columnas COLUMNAS_REQUIRED o vacío si el parseo falla.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber no instalado. Ejecutar: pip install pdfplumber")
        return pd.DataFrame()

    logger.info(f"Abriendo PDF: {pdf_path}")
    registros: list[dict] = []

    # Patrones de OR para identificar filas en el PDF
    patron_or = re.compile(
        r"(CODENSA|ENEL|AIR-E|AIRE|EPM|ESSA|AFINIA|CELSIA|CHEC|EBSA|"
        r"ELECTROHUILA|ENERTOLIMA|CEDENAR|CEDELCA|CENS|EMCALI|EMSA|"
        r"ELPICOL|ENELAR|ENERCA|DISPAC|RUITOQUE|"
        r"CARIBEMAR|CARIBEMAR|EDEQ|EMETA|EMEVASI|EEVS|SIBUNDOY|EEPSA|VATIA)",
        re.IGNORECASE,
    )
    patron_numero = re.compile(r"^\d+[\.,]\d+$")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Extraer todo el texto de las páginas buscando tablas NT1
            tablas_encontradas: list[list[list]] = []
            for page_num, page in enumerate(pdf.pages, 1):
                texto_pagina = page.extract_text() or ""

                # Buscar páginas relacionadas con NT1 / cargos por uso
                if any(kw in texto_pagina.upper() for kw in
                       ["NIVEL DE TENSION 1", "NT1", "BAJA TENSION", "CARGOS POR USO"]):

                    tablas = page.extract_tables()
                    for tabla in tablas:
                        if tabla and len(tabla) > 3:
                            tablas_encontradas.append((page_num, tabla))

            logger.info(f"Encontradas {len(tablas_encontradas)} tablas candidatas en el PDF")

            for page_num, tabla in tablas_encontradas:
                # Analizar encabezados para identificar la estructura
                encabezados = [str(c).upper().strip() if c else "" for c in tabla[0]]
                logger.debug(f"Página {page_num} — encabezados: {encabezados[:8]}")

                # Buscar columnas por nombre aproximado
                idx: dict[str, int] = {}
                for i, h in enumerate(encabezados):
                    if "EMPRESA" in h or "OR" == h or "OPERADOR" in h or "DISTRIBUI" in h:
                        idx.setdefault("or", i)
                    elif h in ("T_STN", "STN", "TRANSMISION NACIONAL"):
                        idx.setdefault("t_stn", i)
                    elif h in ("STR", "T_STR", "TRANSMISION REGIONAL"):
                        idx.setdefault("t_str", i)
                    elif h in ("D", "DISTRIBUCION", "DTUN"):
                        idx.setdefault("d", i)
                    elif h in ("C", "COMERCIALIZACION"):
                        idx.setdefault("c", i)
                    elif h in ("R", "RESTRICCIONES"):
                        idx.setdefault("r", i)
                    elif "PERDIDA" in h or "PÉRDIDA" in h or "PR" == h:
                        idx.setdefault("perdidas", i)

                if "or" not in idx or len(idx) < 3:
                    continue  # Esta tabla no tiene la estructura esperada

                # Extraer filas de datos
                for fila in tabla[1:]:
                    if not fila or not fila[idx["or"]]:
                        continue
                    nombre_or = str(fila[idx["or"]]).strip().upper()
                    match_or = patron_or.search(nombre_or)
                    if not match_or:
                        continue

                    or_codigo = OR_ALIAS.get(match_or.group().upper(), match_or.group().upper())

                    def _safe_float(val) -> Optional[float]:
                        if val is None:
                            return None
                        s = str(val).strip().replace(",", ".")
                        try:
                            return float(s)
                        except ValueError:
                            return None

                    rec = {
                        "or_codigo":                or_codigo,
                        "t_stn_cop_kwh":            _safe_float(fila[idx["t_stn"]]) if "t_stn" in idx else None,
                        "t_str_cop_kwh":            _safe_float(fila[idx["t_str"]]) if "t_str" in idx else None,
                        "d_cop_kwh":                _safe_float(fila[idx["d"]]) if "d" in idx else None,
                        "c_cop_kwh":                _safe_float(fila[idx["c"]]) if "c" in idx else None,
                        "r_restricciones_cop_kwh":  _safe_float(fila[idx["r"]]) if "r" in idx else None,
                        "perdidas_reconocidas_pct": _safe_float(fila[idx["perdidas"]]) if "perdidas" in idx else None,
                        "fazni_cop_kwh":            None,
                        "faer_cop_kwh":             None,
                        "prone_cop_kwh":            None,
                        "fuente":                   f"SSPD_PDF_{pdf_path.stem}",
                        "vigente_desde":            _extraer_periodo_del_nombre(pdf_path.name),
                    }
                    registros.append(rec)
                    logger.debug(f"  Extraído: {rec}")

    except Exception as e:
        logger.error(f"Error parseando PDF: {e}")
        return pd.DataFrame()

    if not registros:
        logger.warning(
            "No se extrajeron registros del PDF. La estructura de tablas puede no coincidir.\n"
            "Alternativa: exportar las tablas del PDF a CSV manualmente y usar --csv."
        )
        return pd.DataFrame()

    df = pd.DataFrame(registros).drop_duplicates(subset=["or_codigo"])
    logger.info(f"Extraídos {len(df)} ORs del PDF: {list(df['or_codigo'])}")
    return df


def _extraer_periodo_del_nombre(nombre_archivo: str) -> str:
    """Extrae YYYY-MM del nombre del archivo PDF/CSV."""
    # Ej: "Boletin-tarifario-I-trimestre-2025.pdf" → "2025-01"
    # Ej: "tarifario-enel-enero-2026.pdf" → "2026-01"
    meses = {
        "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
        "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
        "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08", "sep": "09", "oct": "10",
        "nov": "11", "dec": "12",
    }
    trimestres = {"i": "01", "ii": "04", "iii": "07", "iv": "10"}
    nombre = nombre_archivo.lower()

    # Buscar año
    m_anio = re.search(r"(20\d{2})", nombre)
    anio = m_anio.group(1) if m_anio else str(datetime.now().year)

    # Buscar mes por nombre
    for mes_str, mes_num in meses.items():
        if mes_str in nombre:
            return f"{anio}-{mes_num}"

    # Buscar trimestre
    for trim_str, mes_num in trimestres.items():
        if f"-{trim_str}-" in nombre or f"_{trim_str}_" in nombre:
            return f"{anio}-{mes_num}"

    return f"{anio}-01"


# ─────────────────────────────────────────────────────────────────────────────
# Parseo de CSV
# ─────────────────────────────────────────────────────────────────────────────

def _parsear_csv(csv_path: Path) -> pd.DataFrame:
    """
    Lee un CSV con cargos tarifarios por OR.

    Columnas requeridas (ver header de este módulo para descripción):
      or_codigo, t_stn_cop_kwh, t_str_cop_kwh, d_cop_kwh, c_cop_kwh,
      r_restricciones_cop_kwh, perdidas_reconocidas_pct,
      fazni_cop_kwh, faer_cop_kwh, prone_cop_kwh, fuente, vigente_desde
    """
    logger.info(f"Leyendo CSV: {csv_path}")
    try:
        df = pd.read_csv(csv_path, sep=None, engine="python", dtype=str)
    except Exception as e:
        logger.error(f"Error leyendo CSV: {e}")
        return pd.DataFrame()

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Normalizar codigos OR
    if "or_codigo" in df.columns:
        df["or_codigo"] = df["or_codigo"].str.strip().str.upper()
        df["or_codigo"] = df["or_codigo"].map(lambda x: OR_ALIAS.get(x, x))

    # Convertir numéricos
    for col in COLUMNAS_NUMERICAS:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].str.replace(",", ".").str.strip(), errors="coerce"
            )

    faltantes = [c for c in ["or_codigo", "d_cop_kwh", "c_cop_kwh"] if c not in df.columns]
    if faltantes:
        logger.error(f"CSV falta columnas obligatorias: {faltantes}")
        return pd.DataFrame()

    logger.info(f"CSV leído: {len(df)} filas, ORs: {list(df['or_codigo'])}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Carga a PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

def cargar_a_bd(df: pd.DataFrame, dry_run: bool = False) -> dict:
    """
    Actualiza cu_tarifas_or con los datos del DataFrame.

    Solo actualiza los campos no-nulos del DataFrame (UPDATE parcial).
    No inserta filas nuevas — los OR deben existir previamente en la tabla.

    Returns dict con {actualizados, no_encontrados, errores}.
    """
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from infrastructure.database.connection import PostgreSQLConnectionManager
    mgr = PostgreSQLConnectionManager()

    stats = {"actualizados": 0, "no_encontrados": [], "errores": []}

    with mgr.get_connection() as conn:
        cur = conn.cursor()

        # Verificar ORs que existen
        cur.execute("SELECT or_codigo FROM cu_tarifas_or")
        ors_en_bd = {r[0] for r in cur.fetchall()}

        for _, fila in df.iterrows():
            or_cod = fila["or_codigo"]
            if or_cod not in ors_en_bd:
                logger.warning(f"OR no encontrado en BD: {or_cod}")
                stats["no_encontrados"].append(or_cod)
                continue

            # Construir SET dinámico con solo los campos no-nulos
            set_parts: list[str] = []
            valores: list = []

            for col in COLUMNAS_NUMERICAS:
                if col in fila.index and pd.notna(fila[col]):
                    set_parts.append(f"{col} = %s")
                    valores.append(float(fila[col]))

            for col in ["fuente", "vigente_desde"]:
                if col in fila.index and pd.notna(fila[col]) and str(fila[col]).strip():
                    set_parts.append(f"{col} = %s")
                    valores.append(str(fila[col]).strip())

            if not set_parts:
                logger.debug(f"OR {or_cod}: sin campos para actualizar")
                continue

            set_parts.append("updated_at = now()")
            valores.append(or_cod)

            sql = f"UPDATE cu_tarifas_or SET {', '.join(set_parts)} WHERE or_codigo = %s"

            if dry_run:
                logger.info(f"[DRY-RUN] {sql} | valores: {valores}")
                stats["actualizados"] += 1
                continue

            try:
                cur.execute(sql, valores)
                rows = cur.rowcount
                if rows > 0:
                    stats["actualizados"] += 1
                    logger.info(f"  ✓ {or_cod}: {rows} fila(s) actualizada(s)")
                else:
                    logger.warning(f"  ⚠ {or_cod}: UPDATE afectó 0 filas")
            except Exception as e:
                logger.error(f"  ✗ {or_cod}: {e}")
                stats["errores"].append(or_cod)

        if not dry_run:
            conn.commit()
        cur.close()

    logger.info(
        f"\nResumen: {stats['actualizados']} actualizados | "
        f"{len(stats['no_encontrados'])} no encontrados {stats['no_encontrados']} | "
        f"{len(stats['errores'])} errores {stats['errores']}"
    )
    return stats


def actualizar_t_stn_todos(t_stn_valor: float, dry_run: bool = False) -> int:
    """
    Actualiza el T_STN para TODOS los OR. Útil cuando CREG emite nueva
    resolución de cargos por uso STN (anual, por IPC).
    """
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from infrastructure.database.connection import PostgreSQLConnectionManager
    mgr = PostgreSQLConnectionManager()
    with mgr.get_connection() as conn:
        cur = conn.cursor()
        if not dry_run:
            cur.execute(
                "UPDATE cu_tarifas_or SET t_stn_cop_kwh = %s, updated_at = now()",
                (t_stn_valor,),
            )
            conn.commit()
            rows = cur.rowcount
        else:
            cur.execute("SELECT COUNT(*) FROM cu_tarifas_or")
            rows = cur.fetchone()[0]
            logger.info(f"[DRY-RUN] Se actualizarían {rows} ORs con T_STN = {t_stn_valor}")
        cur.close()
    logger.info(f"T_STN actualizado a {t_stn_valor} COP/kWh en {rows} ORs")
    return rows


def actualizar_manual(or_codigo: str, campos: dict, dry_run: bool = False) -> bool:
    """Actualización manual de un OR específico."""
    df = pd.DataFrame([{"or_codigo": or_codigo, **campos}])
    stats = cargar_a_bd(df, dry_run=dry_run)
    return stats["actualizados"] == 1


def insertar_or(
    or_codigo: str,
    or_nombre: str,
    region: str,
    departamentos: str = "",
    campos: dict | None = None,
    dry_run: bool = False,
) -> bool:
    """
    Inserta un OR nuevo en cu_tarifas_or.

    A diferencia de cargar_a_bd() que solo hace UPDATE, esta función hace
    INSERT y falla si el OR ya existe (evita sobreescrituras accidentales).

    Args:
        or_codigo:    código canónico (ej: 'CARIBEMAR')
        or_nombre:    nombre completo oficial
        region:       'Andina' | 'Caribe' | 'Pacifico' | 'Orinoquia' | 'Amazonia'
        departamentos: lista de departamentos cubiertos
        campos:       dict con t_str_cop_kwh, d_cop_kwh, c_cop_kwh,
                      r_restricciones_cop_kwh, perdidas_reconocidas_pct,
                      fazni_cop_kwh, faer_cop_kwh, prone_cop_kwh,
                      fuente, vigente_desde, usa_cot
        dry_run:      si True, solo imprime sin escribir

    Returns True si se insertó, False si ya existía o hubo error.
    """
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from infrastructure.database.connection import PostgreSQLConnectionManager
    mgr = PostgreSQLConnectionManager()

    campos = campos or {}

    # Columnas con defaults razonables
    col_map = {
        "t_stn_cop_kwh":           campos.get("t_stn",     50.87),
        "t_str_cop_kwh":           campos.get("t_str",      0.0),
        "d_cop_kwh":               campos.get("d",           0.0),
        "c_cop_kwh":               campos.get("c",           0.0),
        "r_restricciones_cop_kwh": campos.get("r",           0.0),
        "perdidas_reconocidas_pct":campos.get("perdidas",   10.0),
        "fazni_cop_kwh":           campos.get("fazni",       0.0),
        "faer_cop_kwh":            campos.get("faer",        0.0),
        "prone_cop_kwh":           campos.get("prone",       0.0),
        "fuente":                  campos.get("fuente",  "MANUAL"),
        "vigente_desde":           campos.get("vigente_desde", datetime.now().strftime("%Y-%m")),
        "usa_cot":                 campos.get("usa_cot", False),
    }

    sql = """
        INSERT INTO cu_tarifas_or
            (or_codigo, or_nombre, region, departamentos,
             t_stn_cop_kwh, t_str_cop_kwh, d_cop_kwh, c_cop_kwh,
             r_restricciones_cop_kwh, perdidas_reconocidas_pct,
             fazni_cop_kwh, faer_cop_kwh, prone_cop_kwh,
             fuente, vigente_desde, usa_cot, c_base_cop_kwh)
        VALUES (%s,%s,%s,%s, %s,%s,%s,%s, %s,%s, %s,%s,%s, %s,%s,%s,%s)
        ON CONFLICT (or_codigo) DO NOTHING
    """
    values = (
        or_codigo.upper(), or_nombre, region, departamentos,
        col_map["t_stn_cop_kwh"], col_map["t_str_cop_kwh"],
        col_map["d_cop_kwh"], col_map["c_cop_kwh"],
        col_map["r_restricciones_cop_kwh"], col_map["perdidas_reconocidas_pct"],
        col_map["fazni_cop_kwh"], col_map["faer_cop_kwh"], col_map["prone_cop_kwh"],
        col_map["fuente"], col_map["vigente_desde"], col_map["usa_cot"],
        col_map["c_cop_kwh"],   # c_base_cop_kwh = initial C
    )

    if dry_run:
        logger.info(f"[DRY-RUN] INSERT OR: {or_codigo} — {or_nombre} ({region})")
        logger.info(f"  Campos: {col_map}")
        return True

    try:
        with mgr.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, values)
            inserted = cur.rowcount > 0
            if inserted:
                conn.commit()
                logger.info(f"✓ OR insertado: {or_codigo} — {or_nombre}")
            else:
                logger.warning(f"OR ya existe: {or_codigo} (no se sobreescribió)")
            cur.close()
        return inserted
    except Exception as e:
        logger.error(f"Error insertando OR {or_codigo}: {e}")
        return False


def actualizar_c_ipc(
    ipc_mensual_pct: float,
    solo_cot: bool = True,
    dry_run: bool = False,
) -> int:
    """
    Actualiza el cargo C (comercialización) de los ORs aplicando el IPC mensual.

    El C de los ORs acogidos al COT (Costo de Operación Tipo) se actualiza
    mensualmente por CREG usando el IPC del DANE. Esta función replica ese
    ajuste multiplicando c_cop_kwh × (1 + ipc_mensual_pct/100).

    Args:
        ipc_mensual_pct: IPC mensual publicado por el DANE (ej: 0.62 para 0.62%)
        solo_cot:        si True (default), solo actualiza ORs con usa_cot=TRUE;
                         si False, actualiza todos los ORs (úsese con cuidado)
        dry_run:         si True, solo imprime sin escribir

    Returns número de ORs actualizados.

    Ejemplo:
        # IPC enero 2026 = 0.62%
        actualizar_c_ipc(0.62, solo_cot=True)
    """
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from infrastructure.database.connection import PostgreSQLConnectionManager
    mgr = PostgreSQLConnectionManager()

    filtro_cot = "AND usa_cot = TRUE" if solo_cot else ""
    factor = 1.0 + ipc_mensual_pct / 100.0

    with mgr.get_connection() as conn:
        cur = conn.cursor()

        # Preview
        cur.execute(f"""
            SELECT or_codigo, c_cop_kwh, c_base_cop_kwh, usa_cot
            FROM cu_tarifas_or
            WHERE c_cop_kwh IS NOT NULL {filtro_cot}
            ORDER BY or_codigo
        """)
        filas = cur.fetchall()

        logger.info(f"IPC {ipc_mensual_pct}% | factor {factor:.5f} | "
                    f"solo_cot={solo_cot} | {len(filas)} ORs afectados")
        for f in filas:
            c_nuevo = round(float(f[1]) * factor, 4)
            logger.info(f"  {f[0]:12}: C {f[1]:.4f} → {c_nuevo:.4f} (COT={f[3]})")

        if dry_run:
            cur.close()
            return len(filas)

        sql_update = f"""
            UPDATE cu_tarifas_or
            SET c_cop_kwh   = ROUND(c_cop_kwh * %s, 4),
                updated_at  = now()
            WHERE c_cop_kwh IS NOT NULL {filtro_cot}
        """
        cur.execute(sql_update, (factor,))
        rows = cur.rowcount
        conn.commit()
        cur.close()

    logger.info(f"C actualizado por IPC {ipc_mensual_pct}% en {rows} ORs")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="etl_tarifas_or_mensual",
        description="ETL de tarifas OR — actualiza cu_tarifas_or desde SSPD/OR oficiales",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--csv",  metavar="ARCHIVO.CSV",  help="CSV con tarifas de todos los OR")
    src.add_argument("--pdf",  metavar="BOLETIN.PDF",  help="PDF del Boletín Tarifario SSPD")
    src.add_argument("--manual", action="store_true",  help="Actualización manual de un OR existente")
    src.add_argument("--add-or", action="store_true",  help="Insertar un OR nuevo en la BD")
    src.add_argument("--update-t-stn", metavar="VALOR", type=float,
                     help="Actualizar T_STN para todos los OR (COP/kWh)")
    src.add_argument("--ipc-c", metavar="PCT", type=float,
                     help="Aplicar IPC mensual al cargo C de ORs COT (ej: 0.62 para 0.62%%)")

    # Campos de OR (--manual, --add-or)
    p.add_argument("--or-codigo",     metavar="COD",   help="Código OR (ej: CARIBEMAR)")
    p.add_argument("--nombre",        metavar="NOMBRE",help="Nombre completo del OR (requerido para --add-or)")
    p.add_argument("--region",        metavar="REG",
                   choices=["Andina","Caribe","Pacifico","Orinoquia","Amazonia"],
                   help="Región geográfica (requerido para --add-or)")
    p.add_argument("--departamentos", metavar="DEPTS", default="",
                   help="Departamentos cubiertos (texto libre)")
    p.add_argument("--t-stn",         type=float,      help="T_STN COP/kWh")
    p.add_argument("--t-str",         type=float,      help="T_STR COP/kWh")
    p.add_argument("--d",             type=float,      help="D (distribución) COP/kWh")
    p.add_argument("--c",             type=float,      help="C (comercialización) COP/kWh")
    p.add_argument("--r",             type=float,      help="R (restricciones) COP/kWh")
    p.add_argument("--perdidas",      type=float,      help="Pérdidas reconocidas NT1 (%%)")
    p.add_argument("--fazni",         type=float,      help="FAZNI COP/kWh")
    p.add_argument("--faer",          type=float,      help="FAER COP/kWh")
    p.add_argument("--prone",         type=float,      help="PRONE COP/kWh")
    p.add_argument("--usa-cot",       action="store_true",
                   help="Marcar OR como usuario del COT (C se actualiza por IPC)")
    p.add_argument("--fuente",        default="MANUAL",help="Fuente (ej: ENEL_OFICIAL_2026_01)")
    p.add_argument("--vigente-desde", dest="vigente_desde", default="",
                   help="Periodo de vigencia (ej: 2026-01)")
    p.add_argument("--solo-cot",      action="store_true", default=True,
                   help="Con --ipc-c: solo actualizar ORs COT (default=True)")
    p.add_argument("--todos-los-ors", action="store_true",
                   help="Con --ipc-c: actualizar TODOS los ORs aunque no sean COT")

    p.add_argument("--dry-run", action="store_true",
                   help="Simular sin escribir en BD")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Log detallado")
    return p


def main(argv: list[str] | None = None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.dry_run:
        logger.info("*** MODO DRY-RUN: no se escribirá en la BD ***")

    # ── Modo: actualizar T_STN global ─────────────────────────────────────
    if args.update_t_stn is not None:
        actualizar_t_stn_todos(args.update_t_stn, dry_run=args.dry_run)
        return

    # ── Modo: IPC sobre cargo C ───────────────────────────────────────────
    if args.ipc_c is not None:
        solo_cot = not args.todos_los_ors
        n = actualizar_c_ipc(args.ipc_c, solo_cot=solo_cot, dry_run=args.dry_run)
        logger.info(f"C actualizado en {n} ORs (IPC={args.ipc_c}%)")
        return

    # ── Modo: insertar OR nuevo ───────────────────────────────────────────
    if args.add_or:
        if not args.or_codigo:
            parser.error("--add-or requiere --or-codigo")
        if not args.nombre:
            parser.error("--add-or requiere --nombre")
        if not args.region:
            parser.error("--add-or requiere --region")
        campos_or: dict = {}
        if args.t_stn is not None:    campos_or["t_stn"]         = args.t_stn
        if args.t_str is not None:    campos_or["t_str"]         = args.t_str
        if args.d is not None:        campos_or["d"]             = args.d
        if args.c is not None:        campos_or["c"]             = args.c
        if args.r is not None:        campos_or["r"]             = args.r
        if args.perdidas is not None: campos_or["perdidas"]      = args.perdidas
        if args.fazni is not None:    campos_or["fazni"]         = args.fazni
        if args.faer is not None:     campos_or["faer"]          = args.faer
        if args.prone is not None:    campos_or["prone"]         = args.prone
        campos_or["usa_cot"]     = args.usa_cot
        campos_or["fuente"]      = args.fuente
        campos_or["vigente_desde"] = args.vigente_desde or datetime.now().strftime("%Y-%m")
        ok = insertar_or(
            args.or_codigo.upper(), args.nombre, args.region,
            args.departamentos, campos_or, dry_run=args.dry_run,
        )
        sys.exit(0 if ok else 1)

    # ── Modo: manual (UPDATE de un OR existente) ──────────────────────────
    if args.manual:
        if not args.or_codigo:
            parser.error("--manual requiere --or-codigo")
        campos: dict = {}
        if args.t_stn is not None:    campos["t_stn_cop_kwh"] = args.t_stn
        if args.t_str is not None:    campos["t_str_cop_kwh"] = args.t_str
        if args.d is not None:        campos["d_cop_kwh"] = args.d
        if args.c is not None:        campos["c_cop_kwh"] = args.c
        if args.r is not None:        campos["r_restricciones_cop_kwh"] = args.r
        if args.perdidas is not None: campos["perdidas_reconocidas_pct"] = args.perdidas
        if args.fazni is not None:    campos["fazni_cop_kwh"] = args.fazni
        if args.faer is not None:     campos["faer_cop_kwh"] = args.faer
        if args.prone is not None:    campos["prone_cop_kwh"] = args.prone
        campos["fuente"] = args.fuente
        campos["vigente_desde"] = args.vigente_desde or datetime.now().strftime("%Y-%m")

        ok = actualizar_manual(args.or_codigo.upper(), campos, dry_run=args.dry_run)
        sys.exit(0 if ok else 1)

    # ── Modo: CSV ─────────────────────────────────────────────────────────
    if args.csv:
        path = Path(args.csv)
        if not path.exists():
            logger.error(f"Archivo no encontrado: {path}")
            sys.exit(1)
        df = _parsear_csv(path)

    # ── Modo: PDF ─────────────────────────────────────────────────────────
    elif args.pdf:
        path = Path(args.pdf)
        if not path.exists():
            logger.error(f"Archivo no encontrado: {path}")
            sys.exit(1)
        df = _parsear_pdf_boletin(path)

    else:
        parser.print_help()
        sys.exit(0)

    if df.empty:
        logger.error("Sin datos para cargar.")
        sys.exit(1)

    # Previsuali
    print("\n=== DATOS A CARGAR ===")
    preview_cols = ["or_codigo", "t_stn_cop_kwh", "d_cop_kwh", "c_cop_kwh",
                    "r_restricciones_cop_kwh", "perdidas_reconocidas_pct", "fuente"]
    with pd.option_context("display.max_columns", 20, "display.width", 140):
        print(df[[c for c in preview_cols if c in df.columns]].to_string(index=False))

    if not args.dry_run:
        resp = input("\n¿Confirmar carga en BD? [s/N]: ").strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            logger.info("Carga cancelada por el usuario.")
            sys.exit(0)

    stats = cargar_a_bd(df, dry_run=args.dry_run)
    sys.exit(0 if not stats["errores"] else 2)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
ETL: cubos OLAP de SICOM → PostgreSQL (schema hidrocarburos, tablas sicom_olap_*).

Sustituye el paso manual descrito en el "Informe de Consolidación y Análisis de
Información de Combustibles" §10: en vez de exportar tablas dinámicas a Excel,
depurarlas a mano y subirlas a OneDrive, se consulta el cubo por programa.

Tres de los ocho pasos de depuración de §10 desaparecen por construcción —
consolidar, organizar y convertir la tabla dinámica en tabla— porque MDX ya
devuelve una tabla plana y sin fila de totales. Los que sí se implementan aquí
son los de limpieza propiamente dicha (§10.4 a §10.6), en `_limpiar`.

Qué se gana respecto a la ruta de Excel:

  · **Conciliación real.** Se compara el detalle contra el total que el propio
    cubo declara al consultarlo sin dimensiones. Eso ya demostró que el 25,4 %
    de volumen que faltaba en "Compras" era un defecto de la exportación manual.
  · **Conteo correcto de agentes.** `AGENTE CANTIDAD` es un conteo distinto:
    sumarlo sobre un cruce de atributos infla la cifra (10.665 frente a 8.907
    agentes reales). Extrayendo el CÓDIGO SICOM se cuenta sin duplicar.
  · **Códigos DANE**, que eliminan la ambigüedad de los 67 nombres de municipio
    repetidos entre departamentos.
  · **Dimensión de ciclo en capacidad**, que el Excel colapsaba sumando 17 años.
  · Sin límite de filas de Excel.

Uso:
    python etl/etl_sicom_olap.py --base agentes
    python etl/etl_sicom_olap.py --base capacidad
    python etl/etl_sicom_olap.py --base compras [--desde 2024]
    python etl/etl_sicom_olap.py --todas
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import tempfile
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg2

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from etl.sicom_olap_client import SicomOlapClient, SicomOlapError  # noqa: E402,F401

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
SCHEMA_SQL = BASE_DIR / "sql" / "hidrocarburos_sicom_olap.sql"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [ETL_SICOM_OLAP] - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "etl_sicom_olap.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

TEXTO, ENTERO, NUMERO = "texto", "entero", "numero"

# Valores que el cubo emite para "sin dato". A diferencia de la ruta de Excel,
# aquí el guion sí se normaliza a NULL: en los cubos es un relleno, y dejarlo
# haría aparecer "-" como si fuera un departamento o una bandera en los tableros.
VACIOS = {"", "-", "nan", "none", "null", "(all)", "unknown", "desconocido"}


@dataclass(frozen=True)
class Atributo:
    """Un atributo del cubo y su columna destino."""

    nivel: str      # p. ej. [AGENTE].[TIPO ESTACION].[TIPO ESTACION]
    columna: str    # p. ej. tipo_estacion
    tipo: str = TEXTO

    @property
    def alias(self) -> str:
        """Nombre con el que el cliente devuelve la jerarquía."""
        partes = [p for p in self.nivel.replace("[", "").split("]") if p.strip(". ")]
        return partes[-1].strip(". ")


@dataclass(frozen=True)
class BaseSicom:
    nombre: str
    catalogo: str
    cubo: str
    tabla: str
    atributos: tuple[Atributo, ...]
    medidas: tuple[tuple[str, str], ...]   # (medida en el cubo, columna destino)
    medida_conciliacion: str               # cuál se concilia contra el total
    identidad: str | None = None           # columna para COUNT(DISTINCT)
    # Cuando la medida es un conteo distinto, el patrón de conciliación no es
    # la suma del detalle (que infla) sino el nº de identidades distintas.
    conciliar_por_identidad: bool = False
    trocear_por_anio: bool = False
    nivel_anio: str = "[CICLO].[AÑO CICLO].[AÑO CICLO]"
    columna_anio: str = "anio_ciclo"   # destino, para recargas parciales
    notas: str = field(default="")

    @property
    def columnas(self) -> list[str]:
        return [a.columna for a in self.atributos] + [m[1] for m in self.medidas]


# ═══════════════════════════════════════════════════════════════════════════════
# Definición de las bases
# ═══════════════════════════════════════════════════════════════════════════════

AGENTES = BaseSicom(
    nombre="agentes",
    catalogo="SBI-Agentes",
    cubo="Agentes",
    tabla="hidrocarburos.sicom_olap_agentes",
    atributos=(
        Atributo("[AGENTE].[CODIGO SICOM AGENTE].[CODIGO SICOM AGENTE]", "codigo_sicom_agente"),
        Atributo("[AGENTE].[OPERADOR NOMBRE COMERCIAL].[OPERADOR NOMBRE COMERCIAL]", "operador_nombre_comercial"),
        Atributo("[TIPO AGENTE].[TIPO AGENTE].[TIPO AGENTE]", "tipo_agente"),
        Atributo("[SUBTIPO AGENTE].[SUBTIPO AGENTE].[SUBTIPO AGENTE]", "subtipo_agente"),
        Atributo("[AGENTE].[NUEVO ESTADO].[NUEVO ESTADO]", "nuevo_estado"),
        Atributo("[AGENTE].[AÑO CREACION].[AÑO CREACION]", "anio_creacion", ENTERO),
        Atributo("[BANDERA].[BANDERA].[BANDERA]", "bandera"),
        Atributo("[PROVEEDOR].[NOMBRE COMERCIAL PROVEEDOR].[NOMBRE COMERCIAL PROVEEDOR]", "nombre_comercial_proveedor"),
        Atributo("[UBICACION INSTALACION].[DEPARTAMENTO INSTALACION].[DEPARTAMENTO INSTALACION]", "departamento_instalacion"),
        Atributo("[UBICACION INSTALACION].[CODIGO DANE DEPARTAMENTO INSTALACION].[CODIGO DANE DEPARTAMENTO INSTALACION]", "codigo_dane_departamento_instalacion"),
        Atributo("[UBICACION INSTALACION].[MUNICIPIO INSTALACION].[MUNICIPIO INSTALACION]", "municipio_instalacion"),
        Atributo("[UBICACION INSTALACION].[CODIGO DANE MUNICIPIO INSTALACION].[CODIGO DANE MUNICIPIO INSTALACION]", "codigo_dane_municipio_instalacion"),
        Atributo("[AGENTE].[OPERADA POR].[OPERADA POR]", "operada_por"),
        Atributo("[AGENTE].[PRODUCTO A COMERCIALIZAR].[PRODUCTO A COMERCIALIZAR]", "producto_a_comercializar"),
        Atributo("[AGENTE].[TIPO ESTACION].[TIPO ESTACION]", "tipo_estacion"),
    ),
    medidas=(("AGENTE CANTIDAD", "agente_cantidad"),),
    medida_conciliacion="AGENTE CANTIDAD",
    identidad="codigo_sicom_agente",
    conciliar_por_identidad=True,
    notas="La suma de AGENTE CANTIDAD sobre el cruce INFLA: usar COUNT(DISTINCT codigo_sicom_agente).",
)

CAPACIDAD = BaseSicom(
    nombre="capacidad",
    catalogo="SBI-Capacidad",
    cubo="Capacidad",
    tabla="hidrocarburos.sicom_olap_capacidad",
    atributos=(
        Atributo("[CICLO].[AÑO CICLO].[AÑO CICLO]", "anio_ciclo", ENTERO),
        Atributo("[CICLO].[MES CICLO].[MES CICLO]", "mes_ciclo", ENTERO),
        Atributo("[AGENTE].[CODIGO SICOM AGENTE].[CODIGO SICOM AGENTE]", "codigo_sicom_agente"),
        Atributo("[AGENTE].[NOMBRE COMERCIAL AGENTE].[NOMBRE COMERCIAL AGENTE]", "nombre_comercial_agente"),
        Atributo("[AGENTE].[TIPO AGENTE].[TIPO AGENTE]", "tipo_agente"),
        Atributo("[AGENTE].[SUBTIPO AGENTE].[SUBTIPO AGENTE]", "subtipo_agente"),
        Atributo("[AGENTE].[DEPARTAMENTO INSTALACION].[DEPARTAMENTO INSTALACION]", "departamento_instalacion"),
        Atributo("[AGENTE].[CODIGO DANE DEPARTAMENTO INSTALACION].[CODIGO DANE DEPARTAMENTO INSTALACION]", "codigo_dane_departamento_instalacion"),
        Atributo("[AGENTE].[MUNICIPIO INSTALACION].[MUNICIPIO INSTALACION]", "municipio_instalacion"),
        Atributo("[AGENTE].[CODIGO DANE MUNICIPIO INSTALACION].[CODIGO DANE MUNICIPIO INSTALACION]", "codigo_dane_municipio_instalacion"),
        Atributo("[PRODUCTO].[PRODUCTO].[PRODUCTO]", "producto"),
        Atributo("[PRODUCTO].[DESCRIPCION PRODUCTO].[DESCRIPCION PRODUCTO]", "descripcion_producto"),
    ),
    medidas=(("CAPACIDAD OPERATIVA", "capacidad_operativa"),),
    medida_conciliacion="CAPACIDAD OPERATIVA",
    trocear_por_anio=True,
    notas="La capacidad se declara por ciclo; sumar todos los ciclos NO da capacidad instalada.",
)

COMPRAS = BaseSicom(
    nombre="compras",
    catalogo="SBI-Compras",
    cubo="Compras",
    tabla="hidrocarburos.sicom_olap_compras",
    atributos=(
        Atributo("[CICLO].[AÑO CICLO].[AÑO CICLO]", "anio_ciclo", ENTERO),
        Atributo("[CICLO].[MES CICLO].[MES CICLO]", "mes_ciclo", ENTERO),
        Atributo("[AGENTE COMPRADOR].[CODIGO SICOM AGENTE COMPRADOR].[CODIGO SICOM AGENTE COMPRADOR]", "codigo_sicom_agente_comprador"),
        Atributo("[AGENTE COMPRADOR].[NOMBRE COMERCIAL AGENTE COMPRADOR].[NOMBRE COMERCIAL AGENTE COMPRADOR]", "nombre_comercial_agente_comprador"),
        Atributo("[AGENTE COMPRADOR].[TIPO AGENTE COMPRADOR].[TIPO AGENTE COMPRADOR]", "tipo_agente_comprador"),
        Atributo("[AGENTE COMPRADOR].[SUBTIPO AGENTE COMPRADOR].[SUBTIPO AGENTE COMPRADOR]", "subtipo_agente_comprador"),
        Atributo("[AGENTE COMPRADOR].[DEPARTAMENTO AGENTE COMPRADOR].[DEPARTAMENTO AGENTE COMPRADOR]", "departamento_agente_comprador"),
        Atributo("[AGENTE COMPRADOR].[CODIGO DANE DEPARTAMENTO AGENTE COMPRADOR].[CODIGO DANE DEPARTAMENTO AGENTE COMPRADOR]", "codigo_dane_departamento_agente_comprador"),
        Atributo("[AGENTE COMPRADOR].[MUNICIPIO AGENTE COMPRADOR].[MUNICIPIO AGENTE COMPRADOR]", "municipio_agente_comprador"),
        Atributo("[AGENTE COMPRADOR].[CODIGO DANE MUNICIPIO AGENTE COMPRADOR].[CODIGO DANE MUNICIPIO AGENTE COMPRADOR]", "codigo_dane_municipio_agente_comprador"),
        # Proveedor identificado por PLANTA y no por agente. Verificado contra el
        # cubo: cruzar por cualquier atributo de [AGENTE PROVEEDOR] descarta el
        # 30,8 % del volumen, porque hay compras sin agente proveedor asociado y
        # esas filas desaparecen del producto cruzado sin aviso. Con la planta el
        # detalle concilia al 0,0000 % contra el total del cubo.
        Atributo("[PLANTA AGENTE PROVEEDOR].[PLANTA AGENTE PROVEEDOR].[PLANTA AGENTE PROVEEDOR]", "planta_agente_proveedor"),
        Atributo("[UBICACION PLANTA AGENTE PROVEEDOR].[DEPARTAMENTO PLANTA AGENTE PROVEEDOR].[DEPARTAMENTO PLANTA AGENTE PROVEEDOR]", "departamento_planta_agente_proveedor"),
        Atributo("[UBICACION PLANTA AGENTE PROVEEDOR].[CODIGO DANE DEPARTAMENTO PLANTA AGENTE PROVEEDOR].[CODIGO DANE DEPARTAMENTO PLANTA AGENTE PROVEEDOR]", "codigo_dane_departamento_planta_proveedor"),
        Atributo("[UBICACION PLANTA AGENTE PROVEEDOR].[MUNICIPIO PLANTA AGENTE PROVEEDOR].[MUNICIPIO PLANTA AGENTE PROVEEDOR]", "municipio_planta_agente_proveedor"),
        Atributo("[UBICACION PLANTA AGENTE PROVEEDOR].[CODIGO DANE MUNICIPIO PLANTA AGENTE PROVEEDOR].[CODIGO DANE MUNICIPIO PLANTA AGENTE PROVEEDOR]", "codigo_dane_municipio_planta_proveedor"),
        Atributo("[PRODUCTO].[PRODUCTO].[PRODUCTO]", "producto"),
        Atributo("[PRODUCTO].[DESCRIPCION PRODUCTO].[DESCRIPCION PRODUCTO]", "descripcion_producto"),
    ),
    medidas=(
        ("VOLUMEN COMPRADO", "volumen_comprado"),
        ("VOLUMEN TRANSITO", "volumen_transito"),
    ),
    medida_conciliacion="VOLUMEN COMPRADO",
    trocear_por_anio=True,
    notas=("Compras y Compras EDS salen de esta misma tabla (vista v_sicom_olap_compras_eds). "
           "El proveedor se identifica por planta: el 30,8 % del volumen no tiene agente proveedor."),
)

BASES = {b.nombre: b for b in (AGENTES, CAPACIDAD, COMPRAS)}


# ═══════════════════════════════════════════════════════════════════════════════
# MDX
# ═══════════════════════════════════════════════════════════════════════════════

def _jerarquia(nivel: str) -> str:
    """'[CICLO].[AÑO CICLO].[AÑO CICLO]' → '[CICLO].[AÑO CICLO]'."""
    partes = [p for p in nivel.replace("[", "").split("]") if p.strip(". ")]
    return "".join(f"[{p.strip('. ')}]." for p in partes[:2]).rstrip(".")


def _mdx(base: BaseSicom, anio: str | None = None) -> str:
    medidas = ", ".join(f"[Measures].[{m[0]}]" for m in base.medidas)
    filas = " *\n  ".join(f"{a.nivel}.MEMBERS" for a in base.atributos)

    origen = f"[{base.cubo}]"
    if anio is not None:
        # Subconsulta en vez de WHERE: así el año puede seguir apareciendo como
        # columna en el eje de filas.
        # Ojo: MEMBERS se pide sobre el NIVEL ([CICLO].[AÑO CICLO].[AÑO CICLO])
        # pero CURRENTMEMBER exige la JERARQUÍA ([CICLO].[AÑO CICLO]); mezclarlos
        # hace que SSAS rechace la consulta.
        jerarquia = _jerarquia(base.nivel_anio)
        origen = (
            f"(SELECT FILTER({base.nivel_anio}.MEMBERS, "
            f'{jerarquia}.CURRENTMEMBER.NAME = "{anio}") ON COLUMNS '
            f"FROM [{base.cubo}])"
        )

    return (
        f"SELECT NON EMPTY {{{medidas}}} ON COLUMNS,\n"
        f"NON EMPTY\n  {filas}\nON ROWS\n"
        f"FROM {origen}"
    )


def _anios(cliente: SicomOlapClient, base: BaseSicom) -> list[str]:
    """Años de ciclo con datos.

    Pide TODAS las medidas del cubo, no solo la de conciliación: un año que
    tuviera datos únicamente en otra medida no aparecería y sus filas no se
    cargarían nunca en el modo troceado.
    """
    medidas = ", ".join(f"[Measures].[{m[0]}]" for m in base.medidas)
    mdx = (
        f"SELECT NON EMPTY {{{medidas}}} ON COLUMNS,\n"
        f"NON EMPTY {base.nivel_anio}.MEMBERS ON ROWS\nFROM [{base.cubo}]"
    )
    alias = Atributo(base.nivel_anio, "x").alias
    vistos = [f.get(alias) for f in cliente.execute_mdx(mdx, base.catalogo)]
    if any(a is None or not str(a).strip() for a in vistos):
        # Un miembro de año vacío no se puede filtrar por nombre, así que sus
        # filas quedarían fuera de todos los trozos. Mejor fallar que perderlas.
        raise RuntimeError(
            f"{base.nombre}: el cubo tiene filas con año de ciclo vacío; "
            f"el troceado por año las dejaría fuera."
        )
    return sorted({str(a).strip() for a in vistos})


def _total_cubo(cliente: SicomOlapClient, base: BaseSicom) -> float | None:
    """Total que declara el cubo sin dimensiones: el patrón de conciliación."""
    mdx = f"SELECT {{[Measures].[{base.medida_conciliacion}]}} ON COLUMNS FROM [{base.cubo}]"
    for fila in cliente.execute_mdx(mdx, base.catalogo):
        valor = fila.get(base.medida_conciliacion)
        return float(valor) if valor else None
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Limpieza (metodología §10.4-§10.6)
# ═══════════════════════════════════════════════════════════════════════════════

def _limpiar(valor, tipo: str):
    """Normaliza una celda. Devuelve None para los vacíos del cubo.

    Para las medidas se conserva el **texto original** en vez de convertirlo a
    float: PostgreSQL lo guarda en NUMERIC sin pérdida, mientras que pasar por
    float recorta a ~15-17 cifras significativas y la suma de la tabla podría
    dejar de cuadrar con el total del cubo en los últimos dígitos.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto.lower() in VACIOS:
        return None
    if tipo == TEXTO:
        return texto
    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    if not numero.is_finite():
        return None
    return int(numero) if tipo == ENTERO else texto


# ═══════════════════════════════════════════════════════════════════════════════
# Carga
# ═══════════════════════════════════════════════════════════════════════════════

def get_connection():
    return psycopg2.connect(
        dbname="portal_energetico", user="postgres", host="localhost", port=5432,
        options="-c search_path=hidrocarburos,public",
    )


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()
    logger.info("✅ Schema sicom_olap verificado/creado")


def _trozos(cliente: SicomOlapClient, base: BaseSicom, desde: int | None):
    """(etiqueta, MDX) por cada trozo a descargar."""
    if not base.trocear_por_anio:
        return [(None, _mdx(base))]
    anios = _anios(cliente, base)
    if desde is not None:
        anios = [a for a in anios if _limpiar(a, ENTERO) is not None
                 and _limpiar(a, ENTERO) >= desde]
    if not anios:
        raise RuntimeError(
            f"{base.nombre}: el cubo no devolvió ningún año de ciclo a cargar"
        )
    logger.info("  troceado por año: %s", ", ".join(anios))
    return [(a, _mdx(base, a)) for a in anios]


def extraer_trozo(cliente: SicomOlapClient, base: BaseSicom, mdx: str, destino: Path):
    """Descarga un trozo del cubo a un CSV en disco, listo para COPY.

    Devuelve (nº de filas, suma de la medida de conciliación).

    Se escribe a disco y no a un buffer en memoria por dos razones: un trozo de
    compras son ~300.000 filas por 20 columnas, y además así la descarga ocurre
    **antes** de abrir la transacción de carga, que de otro modo quedaría
    abierta los veinte minutos que tarda todo y frenaría el autovacuum de la
    base entera.
    """
    archivo = destino.open("w", encoding="utf-8", newline="")
    escritor = csv.writer(archivo, lineterminator="\n")
    tipos = [a.tipo for a in base.atributos] + [NUMERO] * len(base.medidas)
    alias = [a.alias for a in base.atributos] + [m[0] for m in base.medidas]

    filas = 0
    suma = 0.0
    verificado = False
    for fila in cliente.execute_mdx(mdx, base.catalogo):
        if not verificado:
            # Si un alias no aparece, esa columna entera quedaría en NULL sin que
            # nada lo detecte: puede ser un atributo renombrado en el cubo.
            faltan = [a for a in alias if a not in fila]
            if faltan:
                raise RuntimeError(
                    f"{base.nombre}: el cubo no devolvió {faltan}. "
                    f"Claves recibidas: {sorted(fila)}"
                )
            verificado = True
        valores = [_limpiar(fila.get(a), t) for a, t in zip(alias, tipos)]
        escritor.writerow(["" if v is None else v for v in valores])
        medida = fila.get(base.medida_conciliacion)
        if medida:
            try:
                suma += float(medida)
            except ValueError:
                raise RuntimeError(
                    f"{base.nombre}: valor no numérico en "
                    f"{base.medida_conciliacion!r}: {medida!r}"
                )
        filas += 1

    archivo.close()
    return filas, suma


def copiar(conn, base: BaseSicom, ruta: Path) -> None:
    """COPY de un trozo ya descargado (sin borrar: lo hace el caller)."""
    cols = ", ".join(base.columnas)
    with ruta.open("r", encoding="utf-8") as f, conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {base.tabla} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '')", f
        )


TOLERANCIA = 1e-6  # relativa; solo para absorber el redondeo de float


def _registrar_fallo(conn, base: BaseSicom, motivo: str, segundos: float) -> None:
    """Deja constancia en el control de una corrida que no llegó a confirmar."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO hidrocarburos.sicom_olap_control
                   (base, catalogo, cubo, medida, filas_cargadas, concilia,
                    parcial, segundos, error)
                   VALUES (%s,%s,%s,%s,0,FALSE,TRUE,%s,%s)""",
                (base.nombre, base.catalogo, base.cubo, base.medida_conciliacion,
                 segundos, motivo[:1000]),
            )
    except Exception as exc:
        logger.warning("No se pudo registrar el fallo de %s: %s", base.nombre, exc)


def _comprobar(base: BaseSicom, filas, suma, total_cubo, identidades, carga_completa,
               solo_filas: bool = False) -> None:
    """Compuertas antes de confirmar. El riesgo central de este ETL es la
    pérdida silenciosa de datos, así que un desvío aborta la transacción en vez
    de quedar solo anotado en el log."""
    if filas == 0:
        raise RuntimeError(
            f"{base.nombre}: el cubo devolvió 0 filas. No se reemplaza la tabla "
            f"(un cubo en reprocesamiento o sin permisos puede responder vacío "
            f"sin dar error)."
        )
    if solo_filas or not carga_completa:
        # Antes de cargar solo se puede comprobar que hay datos: la conciliación
        # por identidad necesita la tabla ya escrita.
        return
    if total_cubo is None:
        raise RuntimeError(
            f"{base.nombre}: no se pudo leer el total del cubo, así que no hay "
            f"contra qué conciliar. Se aborta."
        )
    referencia = identidades if base.conciliar_por_identidad else suma
    desvio = abs(total_cubo - referencia) / abs(total_cubo) if total_cubo else 0.0
    if desvio > TOLERANCIA:
        que = base.identidad if base.conciliar_por_identidad else "la suma del detalle"
        raise RuntimeError(
            f"{base.nombre}: NO CONCILIA. {que} = {referencia:,.0f} frente al "
            f"total del cubo {total_cubo:,.0f} (desvío {desvio*100:.4f} %). "
            f"Se aborta para no publicar datos incompletos."
        )


def registrar(conn, base: BaseSicom, filas, suma, total_cubo, identidades, segundos,
              parcial: bool = False) -> None:
    referencia = identidades if base.conciliar_por_identidad else suma
    gap = (total_cubo - referencia) if total_cubo is not None and referencia is not None else None
    gap_pct = (gap / total_cubo * 100) if total_cubo else None
    concilia = abs(gap_pct) < 0.5 if gap_pct is not None else None
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO hidrocarburos.sicom_olap_control
               (base, catalogo, cubo, medida, filas_cargadas, suma_detalle, total_cubo,
                gap_abs, gap_pct, concilia, identidades, segundos, parcial)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (base.nombre, base.catalogo, base.cubo, base.medida_conciliacion,
             filas, suma, total_cubo, gap, gap_pct, concilia, identidades, segundos,
             parcial),
        )


def _con_linaje(paso: str, fn):
    """Envuelve la corrida en ontologia.etl_lineage; nunca tumba el ETL."""
    try:
        from infrastructure.observability.lineage import registrar_paso
    except Exception:
        return fn()
    with registrar_paso("sicom_olap", paso) as reg:
        res = fn()
        reg.filas(res.get("filas", 0))
    return res


def run_base(base: BaseSicom, desde: int | None = None) -> dict:
    return _con_linaje(base.nombre, lambda: _run_base(base, desde))


def _run_base(base: BaseSicom, desde: int | None = None) -> dict:
    logger.info("📦 %s  (%s · cubo %s)", base.nombre.upper(), base.catalogo, base.cubo)
    t0 = time.time()
    carga_completa = desde is None

    if not carga_completa and not base.trocear_por_anio:
        raise RuntimeError(
            f"{base.nombre} no se trocea por año: --desde no aplica "
            f"(la tabla no tiene columna de ciclo)."
        )

    # Candado entre corridas: evita que el cron y una ejecución a mano se pisen
    # sobre la misma tabla. Se libera solo al cerrar la conexión.
    conn_lock = get_connection()
    conn_lock.autocommit = True
    with conn_lock.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (f"sicom_olap_{base.nombre}",))
        if not cur.fetchone()[0]:
            conn_lock.close()
            raise RuntimeError(
                f"{base.nombre}: ya hay otra carga en curso sobre esta base."
            )

    cliente = SicomOlapClient()
    try:
        # El total del cubo cubre toda la historia: solo es patrón de
        # conciliación válido cuando se carga completa.
        total_cubo = _total_cubo(cliente, base) if carga_completa else None
        trozos = _trozos(cliente, base, desde)
        anios_cargados = [_limpiar(a, ENTERO) for a, _ in trozos if a]

        # ── Fase 1: descargar a disco, SIN transacción abierta ──────────────
        with tempfile.TemporaryDirectory(prefix="sicom_olap_") as tmp:
            descargas: list[Path] = []
            filas = 0
            suma = 0.0
            for etiqueta, mdx in trozos:
                t_trozo = time.time()
                ruta = Path(tmp) / f"{etiqueta or 'completo'}.csv"
                n, s_trozo = extraer_trozo(cliente, base, mdx, ruta)
                descargas.append(ruta)
                filas += n
                suma += s_trozo
                if etiqueta:
                    logger.info("    %s → %s filas en %.1fs",
                                etiqueta, f"{n:,}", time.time() - t_trozo)
                time.sleep(0.4)  # cortesía con el servidor de SICOM

            _comprobar(base, filas, suma, total_cubo, None, carga_completa, solo_filas=True)

            # ── Fase 2: una transacción corta, solo para reemplazar la tabla ──
            conn = get_connection()
            try:
                ensure_schema(conn)
                with conn.cursor() as cur:
                    # DELETE y no TRUNCATE: TRUNCATE toma un bloqueo ACCESS
                    # EXCLUSIVE que dejaría los tableros sin poder leer la tabla
                    # durante la carga. Con DELETE los lectores siguen viendo la
                    # versión anterior hasta el commit.
                    if carga_completa:
                        cur.execute(f"DELETE FROM {base.tabla}")
                    else:
                        # Borrar EXACTAMENTE los años que se reescriben: un rango
                        # podría borrar años que luego no se recargan.
                        cur.execute(
                            f"DELETE FROM {base.tabla} WHERE {base.columna_anio} = ANY(%s)",
                            (anios_cargados,),
                        )

                for ruta in descargas:
                    copiar(conn, base, ruta)

                with conn.cursor() as cur:
                    if carga_completa:
                        cur.execute(f"SELECT COUNT(*) FROM {base.tabla}")
                    else:
                        cur.execute(
                            f"SELECT COUNT(*) FROM {base.tabla} "
                            f"WHERE {base.columna_anio} = ANY(%s)",
                            (anios_cargados,),
                        )
                    n_real = cur.fetchone()[0]
                    if n_real != filas:
                        raise RuntimeError(
                            f"[{base.tabla}] COPY cargó {n_real}, se esperaban {filas}"
                        )
                    identidades = None
                    if base.identidad:
                        cur.execute(
                            f"SELECT COUNT(DISTINCT {base.identidad}) FROM {base.tabla}"
                        )
                        identidades = cur.fetchone()[0]

                _comprobar(base, filas, suma, total_cubo, identidades, carga_completa)
                registrar(conn, base, filas, suma, total_cubo, identidades,
                          time.time() - t0, parcial=not carga_completa)
                conn.commit()
            except Exception:
                logger.error("❌ %s — ROLLBACK", base.nombre, exc_info=True)
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                conn.close()

        # Fuera de la transacción y con su propio manejo: recupera el espacio del
        # DELETE y refresca las estadísticas. Si falla, los datos ya están bien.
        try:
            with conn_lock.cursor() as cur:
                cur.execute(f"VACUUM (ANALYZE) {base.tabla}")
        except Exception as exc:
            logger.warning("  ⚠️  VACUUM de %s falló (los datos sí quedaron): %s",
                           base.tabla, exc)

    except Exception as exc:
        # Una corrida fallida no deja fila en el control porque el rollback la
        # deshace; se registra aquí, fuera de la transacción, para que el fallo
        # quede en la tabla y no solo en el log.
        _registrar_fallo(conn_lock, base, str(exc), time.time() - t0)
        raise
    finally:
        cliente.close()
        conn_lock.close()

    referencia = identidades if base.conciliar_por_identidad else suma
    gap_pct = (
        (total_cubo - referencia) / total_cubo * 100
        if total_cubo and referencia is not None else None
    )
    logger.info("  filas=%s  suma del detalle=%s  total del cubo=%s",
                f"{filas:,}", f"{suma:,.0f}",
                f"{total_cubo:,.0f}" if total_cubo else "— (carga parcial)")
    if base.identidad and identidades is not None:
        logger.info("  %s distintos: %s", base.identidad, f"{identidades:,}")
    if gap_pct is not None:
        que = base.identidad if base.conciliar_por_identidad else "la suma"
        estado = "✅ concilia" if abs(gap_pct) < 0.5 else "⚠️  NO concilia"
        logger.info("  %s contra el total del cubo por %s (desvío %.3f%%)",
                    estado, que, gap_pct)
    elif not carga_completa:
        logger.info("  · carga parcial (--desde): no se concilia contra el total del cubo")
    if base.notas:
        logger.info("  nota: %s", base.notas)
    logger.info("  ✅ %s en %.1fs", base.nombre, time.time() - t0)
    return {"filas": filas, "suma": suma, "total_cubo": total_cubo,
            "identidades": identidades}


def main():
    parser = argparse.ArgumentParser(description="ETL cubos OLAP SICOM → PostgreSQL")
    parser.add_argument("--base", choices=sorted(BASES), help="Base a cargar")
    parser.add_argument("--todas", action="store_true", help="Cargar todas las bases")
    parser.add_argument("--desde", type=int, help="Año de ciclo mínimo (bases troceadas)")
    args = parser.parse_args()

    if not args.base and not args.todas:
        parser.error("Indica --base o --todas")

    objetivo = list(BASES.values()) if args.todas else [BASES[args.base]]
    fallos = 0
    for base in objetivo:
        try:
            run_base(base, args.desde)
        except Exception as exc:
            fallos += 1
            logger.error("❌ %s falló: %s", base.nombre, exc)
    logger.info("🏁 ETL SICOM OLAP terminado (%d fallo(s))", fallos)
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()

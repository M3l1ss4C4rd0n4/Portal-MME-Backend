#!/usr/bin/env python3
"""
RAG — Fase 8 (+ ronda de ampliación posterior): indexa informes PDF/PPTX/DOCX
de SharePoint en ontologia.informes_texto_embeddings — segundo corpus del
RAG, junto al de observaciones de contratos (build_texto_embeddings.py).

Fuentes (decididas tras explorar en vivo qué carpetas de SharePoint
relacionadas al portal tienen contenido real, no solo estructura vacía —
"20. Trazabilidad Convocatoria..." resultó estar 100% vacía en ambas rondas
de exploración, con y sin subcarpetas):
  1. "19. PMO" (raíz): guía y diagnóstico del sistema de alertas del sector
     eléctrico — PDF.
  2. "19. PMO/1. Contratos OR/2. Informes de Seguimiento": informes periódicos
     de seguimiento a la ejecución de Comunidades Energéticas — PPTX.
  3. Actas de seguimiento CE de ELECTROCAQUETA (misma carpeta que ya usa
     GET /v1/contratos-or/actas/* para servirlas al usuario) — PDF/DOCX.
  4. Boletín energético + informes diarios XM (mismas carpetas que ya usa
     GET /v1/reports/* para servirlos al usuario) — PDF. Los informes diarios
     son operativos y se generan a diario: se indexan solo los últimos
     DIAS_INFORMES_XM días (ventana móvil) y se PODAN los más viejos en cada
     corrida — sin esto el corpus crecería sin límite (~3 archivos/día).
  5. Comunidades Energéticas — Sostenibilidad, Seguimientos y Resoluciones
     (solo el nivel directo de "08. Resoluciones", NO las ~200 resoluciones
     individuales por CE dentro de "01/02/03 Registros..." — documentos
     casi idénticos entre sí, de bajo valor semántico por unidad frente al
     costo de embeber cientos de PDFs repetitivos; candidato a un enfoque
     estructurado (extraer metadatos) en vez de RAG crudo, si se decide
     perseguirlo más adelante).
  6. Colombia Solar — justificación del proyecto, ficha técnica, marco
     regulatorio (decretos/memorias), presentaciones y contrato
     interadministrativo 2026.
  7. Subsidios — conciliaciones SIN, exentos de contribución, diagnóstico de
     focalización (estrategia STM).
Las fuentes 5-7 llenan dashboards que hasta ahora tenían cero cobertura de
RAG (Comunidades solo tenía ACTAS_ELECTROCAQUETA; Colombia Solar y Subsidios
no tenían nada). Verificado en vivo carpeta por carpeta antes de indexar —
se descartaron explícitamente las carpetas "Soportes contratistas/
contractuales" de Supervisión/Colombia Solar/Comunidades/Fondos: son
archivos administrativos individuales por persona (cientos de MB a varios GB
cada uno), no informes narrativos, y con riesgo real de exponer datos
personales de contratistas en un corpus consultable por chat.

Fase 23 Bloque 2 (2026-08-06): se investigaron 4 carpetas más del backlog
("13. Financiero DEE", "07. Reglamentos", "05.Proyectos estratégicos y
regulación", "21. Esquemas de comercialización"). Dos resultaron ser
callejones sin salida al verificar en vivo (contrario a lo que se esperaba
por evidencia indirecta de código): "13. Financiero DEE" es papeleo de
facturación mensual por persona (mismo patrón ya descartado arriba, carpetas
"NOMBRE PERSONA/01. ENERO/.../12. DICIEMBRE"), y "07. Reglamentos" solo tiene
1 archivo sin relación con resoluciones CREG ("INFORMES DE VISITAS DE
COOPERACIÓN TÉCNICA"). Las otras 2 sí tenían contenido real:
  8. Interconexiones eléctricas internacionales (Colombia-Panamá, Chocó) —
     balances y presentaciones de proyectos estratégicos.
  9. Esquemas de comercialización para Comunidades Energéticas — lineamientos
     metodológicos de estructuración y un informe de un proyecto real
     (AFPEI Población vulnerable - FENOGE). Directamente relevante al mismo
     dominio de Comunidades ya cubierto (fuente 5) — reusa el tema
     'comunidades' existente en vez de crear uno nuevo.

Idempotente por hash de contenido: solo re-descarga/re-embebe un archivo si
cambió en SharePoint desde la última corrida.

Uso:
    venv/bin/python3 scripts/ontologia/build_informes_embeddings.py
"""

import asyncio
import hashlib
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests  # noqa: E402

from etl.etl_sharepoint_sync import _get_access_token  # noqa: E402
from api.v1.routes.reports import (  # noqa: E402
    _sp_open_folder, _graph_list_all_children, _sp_download_item,
    _parse_folder_date, BOLETINES_ENERGETICOS_FOLDER, INFORMES_DIARIOS_XM_FOLDER,
    INFORME_EMPALME_FOLDER,
)
from api.v1.routes.contratos_or import SHARE_URL_ACTAS  # noqa: E402
from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.ml.document_extraction import extraer_chunks, chunk_texto_plano  # noqa: E402
from infrastructure.ml.embeddings import embed_batch, MODEL_NAME  # noqa: E402
from infrastructure.xm.portalxm_client import (  # noqa: E402
    listar_ficheros as _xm_listar_ficheros,
    listar_todos_ficheros as _xm_listar_todos_ficheros,
    descargar_fichero as _xm_descargar_fichero,
    TIPO_CARPETA as _XM_TIPO_CARPETA,
    TIPO_PDF as _XM_TIPO_PDF,
)
from infrastructure.creg.gestor_normativo_client import (  # noqa: E402
    listar_documentos_anio as _creg_listar_documentos_anio,
    listar_documentos_entidad as _creg_listar_documentos_entidad,
    descargar_texto_documento as _creg_descargar_texto_documento,
    ENTIDAD_UPME as _ENTIDAD_UPME,
    ENTIDAD_MME as _ENTIDAD_MME,
    ENTIDAD_MME_CONCEPTOS as _ENTIDAD_MME_CONCEPTOS,
)
from infrastructure.upme.upme_wp_client import (  # noqa: E402
    listar_publicaciones_pagina as _upme_listar_publicaciones,
    descargar_pdf as _upme_descargar_pdf,
    PAGINAS_UPME as _PAGINAS_UPME,
)
from infrastructure.minenergia.minenergia_client import (  # noqa: E402
    listar_publicaciones_pagina as _mme_listar_publicaciones,
    descargar_pdf as _mme_descargar_pdf,
    PAGINAS_MISIONALES as _PAGINAS_MISIONALES_MME,
)
from infrastructure.logging.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

DRIVE_ID_PMO = "b!M630_m9dFUueVpEyFl0_UwvCmurFjcFJpoow_E1pMKHz2kCRfLELTb4uChKyhlm6"
EXTENSIONES_SOPORTADAS = {"pdf", "pptx", "docx"}
DIAS_INFORMES_XM = 14

# Carpetas a indexar dentro del drive de "Planeación estratégica - DEE" — listado
# NO recursivo (solo archivos directos de cada carpeta), para no arrastrar sin
# querer subcarpetas de "19. PMO" aún no revisadas (ej. bases de datos,
# presentaciones internas de estructura DEE).
CARPETAS_PMO = [
    "/General/19. PMO",
    "/General/19. PMO/1. Contratos OR/2. Informes de Seguimiento",
]

# Cada tupla es (carpeta_origen, ruta) — carpeta_origen es la etiqueta que
# queda en ontologia.informes_documentos.carpeta_origen, usada luego por
# clasificar_tema_informes.py para asignar tema por prefijo (ver ese script).
CARPETAS_COMUNIDADES = [
    ("COMUNIDADES_SOSTENIBILIDAD", "/General/01. Comunidades Energéticas/02. Sostenibilidad"),
    (
        "COMUNIDADES_SEGUIMIENTOS",
        "/General/01. Comunidades Energéticas/04. Documentos y presentaciones CE/SEGUIMIENTOS A C.E",
    ),
    # Solo el nivel directo — NO las subcarpetas "01/02/03 Registros..." con
    # ~200 resoluciones individuales casi idénticas cada una (ver docstring).
    ("COMUNIDADES_RESOLUCIONES", "/General/01. Comunidades Energéticas/08. Resoluciones - Registro CE"),
]

CARPETAS_COLOMBIA_SOLAR = [
    ("COLOMBIA_SOLAR_GENERAL", "/General/17. Colombia Solar 2025/COLOMBIA SOLAR 2025"),
    ("COLOMBIA_SOLAR_REGULATORIO", "/General/17. Colombia Solar 2025/COLOMBIA SOLAR 2025/Regulatorio"),
    ("COLOMBIA_SOLAR_PRESENTACIONES", "/General/17. Colombia Solar 2025/COLOMBIA SOLAR 2025/Presentaciones"),
    ("COLOMBIA_SOLAR_CONTRATO_2026", "/General/17. Colombia Solar 2025/CONTRATO INTERADMINISTRATIVO 2026"),
]

CARPETAS_SUBSIDIOS = [
    (
        "SUBSIDIOS_CONCILIACIONES_SIN",
        "/General/06. Subsidios/02. Plan de trabajo/01. Gestión operativa de los subsidios en el SIN/01. Conciliaciones SIN",
    ),
    (
        "SUBSIDIOS_EXENTOS",
        "/General/06. Subsidios/02. Plan de trabajo/06. Seguimiento y cambios/02. Exentos",
    ),
    (
        "SUBSIDIOS_DIAGNOSTICO_STM",
        "/General/06. Subsidios/02. Plan de trabajo/03. Estrategia STM/01. Diagnóstico STM",
    ),
]

CARPETAS_PROYECTOS_ESTRATEGICOS = [
    (
        "PROYECTOS_ESTRATEGICOS_INTERCONEXIONES",
        "/General/05.Proyectos estratégicos y regulación/02. Interconexiones",
    ),
]

# Reusa el tema 'comunidades' ya existente (clasificar_tema_informes.py matchea
# por prefijo COMUNIDADES_%) — es el mismo dominio que la fuente 5, solo una
# carpeta de origen distinta.
CARPETAS_COMUNIDADES_COMERCIALIZACION = [
    (
        "COMUNIDADES_ESQUEMAS_COMERCIALIZACION",
        "/General/21. Esquemas de comercialización/2. DOC. GENERAL/Sostenibilidad",
    ),
    (
        "COMUNIDADES_ESQUEMAS_COMERCIALIZACION",
        "/General/21. Esquemas de comercialización/1. PROYECTOS/AFPEI Población vulnerable - FENOGE/D. Informes oficial/Presentaciones",
    ),
]

# Fase 33 — repositorio público de XM (api-portalxm.xm.com.co, ver
# infrastructure/xm/portalxm_client.py). Verificado en vivo que
# "PlaneacionOperacion" es el único corpus narrativo real dentro de ese
# repositorio — el resto (DESPACHO, INFODESPACHO, DEMANDAS, Genminimas...)
# son datos crudos de mercado (.txt/.xlsm), no informes de texto.
#
# IMPORTANTE — la estructura NO es uniforme entre subcarpetas de
# PlaneacionOperacion (descubierto en vivo: un primer intento que recorrió
# "CortoPlazo" completo tardó 73 min; investigando por qué se confirmó que
# NO era una carpeta de datos crudos — son los mismos informes narrativos
# "Análisis Energético de CP", solo que XM reorganizó su estructura de
# carpetas en algún punto de 2024: los años 2021-2024 viven directo bajo
# "CortoPlazo/<año>/...", y desde entonces (2024 tardío en adelante) bajo
# "CortoPlazo/Informacion Energetica/<año>/<mes>/<semana>/..."). Ambas
# rutas se indexan bajo la misma etiqueta — son el mismo tipo de informe,
# solo distinta era de organización; "Informacion Energetica" se excluye
# explícitamente al recorrer la ruta vieja para no recorrerla dos veces.
#
# MedianoPlazo/InformacionEnergetica/BoletinEnergetico (356 archivos) SÍ
# se verificó como datos crudos, no narrativos — no se incluye.
#
# Ronda 2 — las otras 5 subcarpetas verificadas archivo por archivo (no
# solo por nombre de carpeta) antes de agregarse, mismo criterio aplicado
# a CortoPlazo. Cada ruta abajo fue confirmada con PDFs narrativos reales
# en al menos una muestra real. Excluidas explícitamente tras verificar
# contenido (no solo por nombre, que a veces engaña — ej.
# "Resultados_Estudios" de MedianoPlazo resultó ser 100% datos crudos
# pese al nombre prometedor):
#   - LargoPlazo: CargoporConfiabilidad (specs estáticas repetidas + datos),
#     CEE (.txt crudo), MinimosOperativos (.xlsx crudo),
#     BasesDatosPowerFactoryLP/IPOELPBaseDatos (datos por nombre),
#     InformacionEnergetica/MPODE/Resultados Estudios (0 PDF encontrados
#     en muestreo, pese al nombre).
#   - MedianoPlazo: IPOEMP (vacío en las 5 muestras revisadas),
#     InformacionEnergetica/Resultados_Estudios (0 PDF, solo .xlsx/.zip),
#     Bases de Datos/BasesDatosPowerFactoryMP (datos por nombre).
#   - MedianoyLargoPlazo: IPOEMLP (vacío), BasesDatosPowerFactoryMLP/MP
#     (datos por nombre).
#   - Senda de Referencia: carpeta completa — confirmado 100% .xlsx crudo
#     ("Supuestos_Resultados_SendaReferencia_...") en 2020 y 2026.
_RUTA_CORTOPLAZO = "/M:/InformacionAgentes/Usuarios/Publico/PlaneacionOperacion/CortoPlazo"
_RUTA_LARGOPLAZO = "/M:/InformacionAgentes/Usuarios/Publico/PlaneacionOperacion/LargoPlazo"
_RUTA_MEDIANOPLAZO = "/M:/InformacionAgentes/Usuarios/Publico/PlaneacionOperacion/MedianoPlazo"
_RUTA_MEDIANOYLARGOPLAZO = "/M:/InformacionAgentes/Usuarios/Publico/PlaneacionOperacion/MedianoyLargoPlazo"
RUTAS_PLANEACION_XM = [
    ("PLANEACION_XM_CORTOPLAZO", f"{_RUTA_CORTOPLAZO}/Informacion Energetica", frozenset()),
    ("PLANEACION_XM_CORTOPLAZO", _RUTA_CORTOPLAZO, frozenset({"Informacion Energetica"})),
    ("PLANEACION_XM_FLEXIBILIDAD", "/M:/InformacionAgentes/Usuarios/Publico/PlaneacionOperacion/Flexibilidad", frozenset()),
    ("PLANEACION_XM_LARGOPLAZO", f"{_RUTA_LARGOPLAZO}/AnalisisTrimestralRestricciones", frozenset()),
    ("PLANEACION_XM_LARGOPLAZO", f"{_RUTA_LARGOPLAZO}/InformacionEnergetica/AS/Resultados Estudios", frozenset()),
    ("PLANEACION_XM_LARGOPLAZO", f"{_RUTA_LARGOPLAZO}/IPOELP", frozenset()),
    ("PLANEACION_XM_MEDIANOPLAZO", f"{_RUTA_MEDIANOPLAZO}/EstudiosTrimestrales", frozenset()),
    ("PLANEACION_XM_MEDIANOPLAZO", f"{_RUTA_MEDIANOPLAZO}/Estudios Ecuador", frozenset()),
    ("PLANEACION_XM_MEDIANOPLAZO", f"{_RUTA_MEDIANOPLAZO}/Estudios EDAC", frozenset()),
    ("PLANEACION_XM_MEDIANOYLARGOPLAZO", f"{_RUTA_MEDIANOYLARGOPLAZO}/IPOEL", frozenset()),
]


class _Contador:
    def __init__(self):
        self.archivos = 0
        self.procesados = 0
        self.chunks = 0


def _ext(nombre: str) -> str:
    return nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""


def _vector_literal(v) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in v) + "]"


def _upsert_documento(
    carpeta: str, nombre: str, tipo: str, hash_contenido: str,
    item_id: str, tamano, modificado,
) -> int:
    row = db_manager.query_df(
        """
        INSERT INTO ontologia.informes_documentos
            (carpeta_origen, nombre_archivo, tipo_archivo, hash_contenido,
             sharepoint_item_id, tamano_bytes, modificado_en_sharepoint, indexado_en)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (carpeta_origen, nombre_archivo)
        DO UPDATE SET hash_contenido = EXCLUDED.hash_contenido,
                      sharepoint_item_id = EXCLUDED.sharepoint_item_id,
                      tamano_bytes = EXCLUDED.tamano_bytes,
                      modificado_en_sharepoint = EXCLUDED.modificado_en_sharepoint,
                      indexado_en = NOW()
        RETURNING documento_id
        """,
        (carpeta, nombre, tipo, hash_contenido, item_id, tamano, modificado),
    )
    return int(row["documento_id"].iloc[0])


def _reindexar_chunks(documento_id: int, chunks: list[str]) -> None:
    db_manager.execute_non_query(
        "DELETE FROM ontologia.informes_texto_embeddings WHERE documento_id = %s",
        (documento_id,),
    )
    if not chunks:
        return
    vectores = embed_batch(chunks)
    for idx, (texto, vector) in enumerate(zip(chunks, vectores), start=1):
        db_manager.execute_non_query(
            """
            INSERT INTO ontologia.informes_texto_embeddings
                (documento_id, chunk_index, contenido, embedding, modelo)
            VALUES (%s, %s, %s, %s::vector, %s)
            """,
            (documento_id, idx, texto, _vector_literal(vector), MODEL_NAME),
        )


def _procesar_item(
    carpeta_label: str, item: dict, headers: dict, drive_id: str,
    hash_map: dict, contador: _Contador,
) -> None:
    """Descarga (si aplica), extrae, embebe e indexa un único archivo — reutilizado
    por las 4 fuentes, sin importar si se listó por path de drive o por share link."""
    nombre = item["name"]
    tipo = _ext(nombre)
    if tipo not in EXTENSIONES_SOPORTADAS:
        return
    contador.archivos += 1

    contenido = _sp_download_item(headers, drive_id, item)
    if contenido is None:
        return
    hash_contenido = hashlib.sha256(contenido).hexdigest()

    if hash_map.get((carpeta_label, nombre)) == hash_contenido:
        return  # sin cambios desde la última corrida

    try:
        chunks = extraer_chunks(contenido, tipo)
    except Exception as e:
        logger.error(f"[INFORMES] Error extrayendo texto de {nombre}: {e}")
        return

    documento_id = _upsert_documento(
        carpeta_label, nombre, tipo, hash_contenido,
        item["id"], item.get("size"), item.get("lastModifiedDateTime"),
    )
    _reindexar_chunks(documento_id, chunks)
    contador.procesados += 1
    contador.chunks += len(chunks)
    logger.info(f"[INFORMES] {nombre}: {len(chunks)} chunks indexados")


def _indexar_carpetas_pmo(hash_map: dict, contador: _Contador) -> None:
    headers = {"Authorization": f"Bearer {_get_access_token()}"}
    for carpeta in CARPETAS_PMO:
        r = requests.get(
            f"https://graph.microsoft.com/v1.0/drives/{DRIVE_ID_PMO}/root:{carpeta}:/children",
            headers=headers, timeout=30,
        )
        if r.status_code != 200:
            logger.error(f"[INFORMES] Error listando {carpeta}: {r.status_code}")
            continue
        for item in r.json().get("value", []):
            if "file" in item:
                _procesar_item(carpeta, item, headers, DRIVE_ID_PMO, hash_map, contador)


def _indexar_carpetas_con_etiqueta(
    carpetas: list[tuple[str, str]], hash_map: dict, contador: _Contador,
) -> None:
    """Igual que _indexar_carpetas_pmo, pero cada carpeta lleva su propia
    etiqueta carpeta_origen (en vez de usar la ruta cruda) — usado por las
    fuentes de Comunidades/Colombia Solar/Subsidios, para que
    clasificar_tema_informes.py pueda matchear por prefijo simple."""
    headers = {"Authorization": f"Bearer {_get_access_token()}"}
    for etiqueta, carpeta in carpetas:
        r = requests.get(
            f"https://graph.microsoft.com/v1.0/drives/{DRIVE_ID_PMO}/root:{carpeta}:/children",
            headers=headers, timeout=30,
        )
        if r.status_code != 200:
            logger.error(f"[INFORMES] Error listando {carpeta}: {r.status_code}")
            continue
        for item in r.json().get("value", []):
            if "file" in item:
                _procesar_item(etiqueta, item, headers, DRIVE_ID_PMO, hash_map, contador)


def _indexar_actas_electrocaqueta(hash_map: dict, contador: _Contador) -> None:
    carpeta_label = "ACTAS_ELECTROCAQUETA"
    headers, drive_id, root_id = _sp_open_folder(SHARE_URL_ACTAS)
    for item in _graph_list_all_children(headers, drive_id, root_id):
        if "file" in item:
            _procesar_item(carpeta_label, item, headers, drive_id, hash_map, contador)


def _indexar_boletin_xm(hash_map: dict, contador: _Contador) -> None:
    carpeta_label = "BOLETINES_XM"
    headers, drive_id, root_id = _sp_open_folder(BOLETINES_ENERGETICOS_FOLDER)
    for item in _graph_list_all_children(headers, drive_id, root_id):
        if "file" in item:
            _procesar_item(carpeta_label, item, headers, drive_id, hash_map, contador)


def _indexar_informe_empalme(hash_map: dict, contador: _Contador) -> None:
    """Fase 29 — mismo documento que sirve GET /v1/reports/informe-empalme/latest
    (carpeta SharePoint real, no generado por IA — a diferencia del Resumen
    Ejecutivo, que sí se generó con IA y se descartó a propósito de indexar
    por circularidad). Único documento con botón de descarga real en el
    portal que quedaba sin indexar."""
    carpeta_label = "INFORME_EMPALME"
    headers, drive_id, root_id = _sp_open_folder(INFORME_EMPALME_FOLDER)
    for item in _graph_list_all_children(headers, drive_id, root_id):
        if "file" in item:
            _procesar_item(carpeta_label, item, headers, drive_id, hash_map, contador)


def _indexar_informes_diarios_xm(hash_map: dict, contador: _Contador) -> None:
    """Ventana móvil de DIAS_INFORMES_XM días: indexa carpetas recientes y PODA
    (borra documento + chunks vía ON DELETE CASCADE) las que ya salieron de la
    ventana, para que el corpus no crezca sin límite noche a noche."""
    headers, drive_id, root_id = _sp_open_folder(INFORMES_DIARIOS_XM_FOLDER)
    carpetas_fecha = _graph_list_all_children(headers, drive_id, root_id)

    limite = date.today() - timedelta(days=DIAS_INFORMES_XM)
    for folder in carpetas_fecha:
        if "folder" not in folder:
            continue
        folder_date = _parse_folder_date(folder["name"])
        if folder_date is None or folder_date < limite:
            continue
        carpeta_label = f"INFORMES_DIARIOS_XM/{folder_date.isoformat()}"
        for item in _graph_list_all_children(headers, drive_id, folder["id"]):
            if "file" in item:
                _procesar_item(carpeta_label, item, headers, drive_id, hash_map, contador)

    fuera_de_ventana = db_manager.query_df(
        """
        SELECT count(*) AS n FROM ontologia.informes_documentos
        WHERE carpeta_origen LIKE 'INFORMES_DIARIOS_XM/%%' AND carpeta_origen < %(limite)s
        """,
        {"limite": f"INFORMES_DIARIOS_XM/{limite.isoformat()}"},
    )
    n_podados = int(fuera_de_ventana["n"].iloc[0]) if not fuera_de_ventana.empty else 0
    if n_podados:
        db_manager.execute_non_query(
            """
            DELETE FROM ontologia.informes_documentos
            WHERE carpeta_origen LIKE 'INFORMES_DIARIOS_XM/%%' AND carpeta_origen < %s
            """,
            (f"INFORMES_DIARIOS_XM/{limite.isoformat()}",),
        )
        logger.info(
            f"[INFORMES] Podados {n_podados} informes diarios XM fuera de la "
            f"ventana de {DIAS_INFORMES_XM} días"
        )


_RUTA_RAIZ_PLANEACION_XM = "/M:/InformacionAgentes/Usuarios/Publico/PlaneacionOperacion/"


def _nombre_desambiguado_por_ruta(ruta_item: str, nombre: str) -> str:
    """XM reutiliza el mismo nombre de archivo en más de un lugar —
    confirmado en vivo con 2 patrones reales distintos: (1) el mismo
    número de semana se repite cada año (ej. 'Semana37' en 2024 Y 2025,
    con el mismo nombre de PDF); (2) durante la transición de estructura
    de carpetas de 2024, el mismo informe quedó publicado tanto en la
    ruta vieja como en la nueva. Un prefijo de solo el año no alcanza
    (el caso 2 colisiona dentro del mismo año). Se antepone la carpeta
    contenedora completa (relativa a PlaneacionOperacion) — única por
    construcción, ya que se deriva de `ruta_item`, que sí es único —
    para que la restricción UNIQUE(carpeta_origen, nombre_archivo) nunca
    pueda perder contenido real por una colisión de nombre corto."""
    carpeta = ruta_item.rsplit("/", 1)[0]
    if carpeta.startswith(_RUTA_RAIZ_PLANEACION_XM):
        carpeta = carpeta[len(_RUTA_RAIZ_PLANEACION_XM):]
    prefijo = carpeta.replace("/", " » ")
    if prefijo and not nombre.startswith(prefijo):
        return f"{prefijo} - {nombre}"
    return nombre


async def _procesar_item_planeacion_xm(
    ruta_item: str, item: dict, etiqueta: str, hash_map: dict, contador: _Contador,
) -> None:
    nombre = _nombre_desambiguado_por_ruta(ruta_item, item["nombre"])
    contador.archivos += 1

    contenido = await _xm_descargar_fichero(ruta_item)
    if contenido is None:
        return
    hash_contenido = hashlib.sha256(contenido).hexdigest()

    if hash_map.get((etiqueta, nombre)) == hash_contenido:
        return  # sin cambios desde la última corrida

    try:
        chunks = extraer_chunks(contenido, "pdf")
    except Exception as e:
        logger.error(f"[INFORMES] Error extrayendo texto de {nombre} (XM): {e}")
        return

    # Fase 35 (continuación) — la primera página de TODOS los informes de
    # Planeación XM (CortoPlazo/LargoPlazo/MedianoPlazo/Boletín) es una
    # portada casi vacía (solo título + rango de fechas + "Todos los
    # derechos reservados..."/contacto) — verificado sobre 15 muestras
    # aleatorias de las 4 subfuentes, 100% cover-page, nunca contenido real.
    # Reproducido en vivo que esta portada, al repetirse ~250+ veces con
    # solo la fecha cambiando, gana el re-ranking frente al contenido real
    # (Conclusiones, resultados) para cualquier consulta que mencione el
    # nombre del informe — el bono de recencia (ver reranking.py) no
    # alcanza a compensar una ventaja de score tan grande. Se descarta antes
    # de embeber (nunca menos de 3 chunks por documento en todo este corpus,
    # verificado — ningún documento queda vacío).
    if len(chunks) > 1:
        chunks = chunks[1:]

    documento_id = _upsert_documento(
        etiqueta, nombre, "pdf", hash_contenido,
        ruta_item, item.get("tamanio"), item.get("fechaModificacion") or item.get("fechaCreacion"),
    )
    _reindexar_chunks(documento_id, chunks)
    contador.procesados += 1
    contador.chunks += len(chunks)
    logger.info(f"[INFORMES] {nombre} (XM): {len(chunks)} chunks indexados")


MAX_PROFUNDIDAD_PLANEACION_XM = 4  # año→mes→semana→archivo en la ruta verificada — límite
# defensivo: si una ruta resulta tener una subestructura más profunda de la esperada,
# se corta en vez de recorrer indefinidamente (causa raíz del incidente de 73 min).

# Decisión del usuario (2026-08-12): no acumular todo el histórico de XM —
# solo mantener los últimos ANIOS_RETENCION_PLANEACION_XM años, tanto en la
# base de datos como en lo que se recorre/descarga (para no gastar tiempo ni
# llamadas al API en años que de todas formas se van a podar). Calculado en
# el momento de correr (no hardcodeado a un año fijo), para que "últimos 2
# años" siga siendo correcto sin tocar código en el futuro.
ANIOS_RETENCION_PLANEACION_XM = 2


def _anio_minimo_planeacion_xm() -> int:
    return date.today().year - ANIOS_RETENCION_PLANEACION_XM


_FILTRO_PLANEACION_XM_VIEJOS = """
    carpeta_origen LIKE 'PLANEACION_XM_%%'
    AND COALESCE(
          (substring(sharepoint_item_id from '/((?:19|20)\\d{2})(?:/|$)'))::int,
          9999
        ) < %(anio_minimo)s
"""


def _podar_planeacion_xm_historico() -> int:
    """Borra (con cascada a embeddings, ya confirmada en Fase 23) los
    documentos de Planeación XM más viejos que la ventana de retención.
    El año se extrae de `sharepoint_item_id` (la ruta completa real, ej.
    '.../CortoPlazo/Informacion Energetica/2022/...'), no del nombre
    corto — más confiable, ya la ruta siempre contiene el año real."""
    anio_minimo = _anio_minimo_planeacion_xm()
    params = {"anio_minimo": anio_minimo}
    conteo = db_manager.query_df(
        f"SELECT count(*) AS n FROM ontologia.informes_documentos WHERE {_FILTRO_PLANEACION_XM_VIEJOS}",
        params,
    )
    n_podados = int(conteo["n"].iloc[0]) if not conteo.empty else 0
    if n_podados:
        db_manager.execute_non_query(
            f"DELETE FROM ontologia.informes_documentos WHERE {_FILTRO_PLANEACION_XM_VIEJOS}",
            params,
        )
    return n_podados


_RUTA_BOLETIN_ENERGETICO_XM = f"{_RUTA_MEDIANOPLAZO}/InformacionEnergetica/BoletinEnergetico"


def _parsear_fecha_xm(valor: str):
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _indexar_boletin_energetico_xm(hash_map: dict, contador: _Contador) -> None:
    """Fase 35 — "Boletín Energético" público de XM (356 PDFs reales desde
    2014, encontrado investigando por qué el RAG no encontraba el informe
    correcto de mediano plazo que el usuario mostró en captura — ese informe
    resultó no ser indexable, ver PLANEACION_XM_MEDIANOPLAZO/Resultados_Estudios,
    pero este Boletín sí es un PDF narrativo real con datos semanales de
    reservas/aportes/HSIN/senda/generación que no se estaba aprovechando).

    A diferencia de RUTAS_PLANEACION_XM (árbol año→mes→semana, poda por año
    extraído del path), esta carpeta es PLANA — 356 archivos numerados
    secuencialmente en un solo nivel, sin subcarpeta de año — así que ni la
    recursión ni la poda por regex de path aplican aquí. Se filtra por la
    fecha real de cada archivo (`fechaModificacion`/`fechaCreacion` del API
    de XM) contra la misma ventana de ANIOS_RETENCION_PLANEACION_XM, tanto al
    decidir qué descargar como al podar de la base de datos lo que ya
    envejeció fuera de la ventana."""
    etiqueta = "PLANEACION_XM_BOLETIN"
    limite = datetime.now(timezone.utc) - timedelta(days=365 * ANIOS_RETENCION_PLANEACION_XM)

    async def _run():
        items = await _xm_listar_todos_ficheros(_RUTA_BOLETIN_ENERGETICO_XM)
        for item in items:
            if item.get("idTipoContenido") != _XM_TIPO_PDF:
                continue
            fecha = _parsear_fecha_xm(item.get("fechaModificacion") or item.get("fechaCreacion"))
            if fecha is None or fecha < limite:
                continue
            ruta_item = f"{_RUTA_BOLETIN_ENERGETICO_XM}/{item.get('nombre', '')}"
            await _procesar_item_planeacion_xm(ruta_item, item, etiqueta, hash_map, contador)

    asyncio.run(_run())

    conteo = db_manager.query_df(
        "SELECT count(*) AS n FROM ontologia.informes_documentos "
        "WHERE carpeta_origen = %(etiqueta)s AND modificado_en_sharepoint < %(limite)s",
        {"etiqueta": etiqueta, "limite": limite},
    )
    n_podados = int(conteo["n"].iloc[0]) if not conteo.empty else 0
    if n_podados:
        db_manager.execute_non_query(
            "DELETE FROM ontologia.informes_documentos "
            "WHERE carpeta_origen = %s AND modificado_en_sharepoint < %s",
            (etiqueta, limite),
        )
        logger.info(
            f"[INFORMES] Podados {n_podados} boletines energéticos XM fuera de la "
            f"ventana de {ANIOS_RETENCION_PLANEACION_XM} años"
        )


_RUTA_INFODESPACHO_XM = "/M:/InformacionAgentes/Usuarios/Publico/INFODESPACHO"

# Fase 36 — verificado en 2 muestras reales (2026-08-01: 11MB/29 páginas;
# 2026-08-05: 29MB/27 páginas) que solo las 3 primeras páginas del "Informe
# del Despacho" diario son narrativas (Resumen de generación, Novedades,
# Consideración/Indisponibilidades) — el resto son tablas horarias de
# generación por planta (SubÁrea/Elemento/G01...G24), sin valor narrativo.
PAGINAS_NARRATIVAS_INFODESPACHO = 3


async def _procesar_item_infodespacho(
    mes: str, item: dict, etiqueta: str, hash_map: dict, contador: _Contador,
) -> None:
    ruta_item = f"{_RUTA_INFODESPACHO_XM}/{mes}/{item.get('nombre', '')}"
    nombre = f"{mes} - {item.get('nombre', '')}"
    contador.archivos += 1

    contenido = await _xm_descargar_fichero(ruta_item, timeout=60.0)
    if contenido is None:
        return
    hash_contenido = hashlib.sha256(contenido).hexdigest()

    if hash_map.get((etiqueta, nombre)) == hash_contenido:
        return  # sin cambios desde la última corrida

    try:
        chunks = extraer_chunks(contenido, "pdf", max_paginas=PAGINAS_NARRATIVAS_INFODESPACHO)
    except Exception as e:
        logger.error(f"[INFORMES] Error extrayendo texto de {nombre} (INFODESPACHO XM): {e}")
        return

    documento_id = _upsert_documento(
        etiqueta, nombre, "pdf", hash_contenido,
        ruta_item, item.get("tamanio"), item.get("fechaModificacion") or item.get("fechaCreacion"),
    )
    _reindexar_chunks(documento_id, chunks)
    contador.procesados += 1
    contador.chunks += len(chunks)
    logger.info(f"[INFORMES] {nombre} (INFODESPACHO XM): {len(chunks)} chunks indexados")


def _indexar_infodespacho_xm(hash_map: dict, contador: _Contador) -> None:
    """Fase 36 — "Informe del Despacho" diario del repositorio público de XM
    (distinto del corpus 'despacho' ya indexado vía SharePoint — este es más
    detallado: novedades de consignaciones, indisponibilidades específicas
    por equipo, resoluciones CREG/CND aplicadas ese día). Archivos muy
    pesados (11-35MB/día) — se usa la misma ventana móvil de
    DIAS_INFORMES_XM días ya establecida para los informes diarios (no la
    ventana de años de Planeación XM), tanto para acotar cuántos días se
    descargan como para podar los que ya salieron de la ventana. Solo se
    revisan el mes actual y el anterior (suficiente para cubrir la ventana
    de 14 días incluso cruzando el límite de mes)."""
    etiqueta = "INFODESPACHO_XM"
    limite = datetime.now(timezone.utc) - timedelta(days=DIAS_INFORMES_XM)
    hoy = date.today()
    mes_anterior_fecha = hoy.replace(day=1) - timedelta(days=1)
    meses_a_revisar = {
        f"{hoy.year:04d}-{hoy.month:02d}",
        f"{mes_anterior_fecha.year:04d}-{mes_anterior_fecha.month:02d}",
    }

    async def _run():
        for mes in meses_a_revisar:
            items = await _xm_listar_ficheros(f"{_RUTA_INFODESPACHO_XM}/{mes}")
            for item in items:
                if item.get("idTipoContenido") != _XM_TIPO_PDF:
                    continue
                fecha = _parsear_fecha_xm(item.get("fechaModificacion") or item.get("fechaCreacion"))
                if fecha is None or fecha < limite:
                    continue
                await _procesar_item_infodespacho(mes, item, etiqueta, hash_map, contador)

    asyncio.run(_run())

    conteo = db_manager.query_df(
        "SELECT count(*) AS n FROM ontologia.informes_documentos "
        "WHERE carpeta_origen = %(etiqueta)s AND modificado_en_sharepoint < %(limite)s",
        {"etiqueta": etiqueta, "limite": limite},
    )
    n_podados = int(conteo["n"].iloc[0]) if not conteo.empty else 0
    if n_podados:
        db_manager.execute_non_query(
            "DELETE FROM ontologia.informes_documentos "
            "WHERE carpeta_origen = %s AND modificado_en_sharepoint < %s",
            (etiqueta, limite),
        )
        logger.info(
            f"[INFORMES] Podados {n_podados} informes de INFODESPACHO XM fuera de la "
            f"ventana de {DIAS_INFORMES_XM} días"
        )


# Fase 37 — Gestor Normativo Alejandría 2.0 de la CREG (gestornormativo.creg.gov.co).
# Dos partes:
#  A) Corpus general de resoluciones+circulares de los últimos ANIOS_RETENCION_CREG
#     años — le da al Asistente IA capacidad de búsqueda/cita directa sobre
#     normativa reciente de la CREG, en vez de depender de que XM la mencione
#     de pasada en sus propios informes.
#  B) Lista explícita de las 8 resoluciones "núcleo" ya citadas en
#     core/umbrales_oficiales.py (el único punto de verdad regulatorio del
#     portal) — se indexan SIEMPRE, sin importar su año, y NUNCA se podan —
#     son la base de la lógica de clasificación del sistema (Índice NE, HSIN,
#     PBP, Condición del Sistema), deben estar disponibles para consulta
#     aunque queden fuera de la ventana de años del corpus general.
ANIOS_RETENCION_CREG = 3

NUCLEO_RESOLUCIONES_CREG = [
    # (año, número — con o sin ceros a la izquierda, da igual: se normaliza
    # antes de comparar) — ver core/umbrales_oficiales.py FUENTES REGULATORIAS.
    # Verificado en vivo (2026-08-20) que el sitio de la CREG NO es consistente
    # con el padding: "Resolución 71 de 2006" y "Resolución 101_66 de 2024"
    # (sin ceros), pese a que la URL interna sí usa "0071_2006"/"101-66_2024".
    (2014, "026"),
    (2006, "071"),
    (2017, "140"),
    (2020, "125"),  # corregido de "121" (2026-08-20) — no existe ninguna Res. 121/2020
    (2020, "209"),
    (2024, "101_055"),
    (2024, "101_066"),
    (2026, "101_112"),
]


def _normalizar_segmentos_numero_creg(numero: str) -> str:
    """'101_055' o '101_55' o '026' o '26' -> forma canónica sin ceros a la
    izquierda por segmento (separados por '_') — el sitio de la CREG no es
    consistente con el padding entre el texto mostrado y la URL interna."""
    return "_".join(str(int(s)) for s in numero.split("_"))


def _normalizar_numero_creg(texto_numero: str) -> str:
    """'Resolución 101_120 de 2026 CREG' -> '101_120_2026' — para comparar
    contra NUCLEO_RESOLUCIONES_CREG sin depender del formato de visualización
    exacto (espacios/mayúsculas/sufijo 'CREG'/ceros a la izquierda)."""
    m = re.search(r"(\d[\d_]*\d|\d)\s+de\s+(\d{4})", texto_numero)
    if not m:
        return ""
    return f"{_normalizar_segmentos_numero_creg(m.group(1))}_{m.group(2)}"


async def _procesar_documento_creg(
    doc: dict, tipo: str, etiqueta: str, hash_map: dict, contador: _Contador,
) -> None:
    nombre = doc["numero"]
    contador.archivos += 1

    texto = await _creg_descargar_texto_documento(doc["url_relativa"])
    if not texto:
        return
    hash_contenido = hashlib.sha256(texto.encode("utf-8")).hexdigest()

    if hash_map.get((etiqueta, nombre)) == hash_contenido:
        return  # sin cambios desde la última corrida

    chunks = chunk_texto_plano(texto)
    if not chunks:
        return

    documento_id = _upsert_documento(
        etiqueta, nombre, "html", hash_contenido,
        doc["url_relativa"], len(texto), None,
    )
    _reindexar_chunks(documento_id, chunks)
    contador.procesados += 1
    contador.chunks += len(chunks)
    logger.info(f"[INFORMES] {nombre} (CREG {tipo}): {len(chunks)} chunks indexados")


def _indexar_creg_normativa(hash_map: dict, contador: _Contador) -> None:
    """Fase 37 — ver comentario de constantes arriba. Sin ventana por fecha
    de modificación (a diferencia de las fuentes de XM): el Gestor Normativo
    no expone una fecha de publicación individual por documento en el
    listado, así que la poda del corpus general se hace por AÑO del propio
    documento (extraído de la URL, ej. '..._2024.htm' → 2024), comparado
    contra `anio_actual - ANIOS_RETENCION_CREG`. El corpus núcleo nunca se
    poda, sin importar el año."""
    anio_actual = date.today().year
    anio_minimo_general = anio_actual - ANIOS_RETENCION_CREG + 1

    async def _indexar_general():
        for tipo, etiqueta in [
            ("resoluciones", "CREG_RESOLUCIONES"),
            ("circulares", "CREG_CIRCULARES"),
        ]:
            for anio in range(anio_minimo_general, anio_actual + 1):
                docs = await _creg_listar_documentos_anio(tipo, anio)
                for doc in docs:
                    await _procesar_documento_creg(doc, tipo, etiqueta, hash_map, contador)

    async def _indexar_nucleo():
        etiqueta = "CREG_RESOLUCIONES_NUCLEO"
        # Agrupar por año para minimizar llamadas a listar_documentos_anio.
        anios = sorted({anio for anio, _ in NUCLEO_RESOLUCIONES_CREG})
        for anio in anios:
            docs = await _creg_listar_documentos_anio("resoluciones", anio)
            objetivos = {
                f"{_normalizar_segmentos_numero_creg(num)}_{a}"
                for a, num in NUCLEO_RESOLUCIONES_CREG if a == anio
            }
            encontrados = set()
            for doc in docs:
                clave = _normalizar_numero_creg(doc["numero"])
                if clave in objetivos:
                    encontrados.add(clave)
                    await _procesar_documento_creg(doc, "resoluciones", etiqueta, hash_map, contador)
            faltantes = objetivos - encontrados
            if faltantes:
                logger.warning(f"[INFORMES] Resoluciones núcleo CREG no encontradas en {anio}: {faltantes}")

    asyncio.run(_indexar_general())
    asyncio.run(_indexar_nucleo())

    conteo = db_manager.query_df(
        """
        SELECT count(*) AS n FROM ontologia.informes_documentos
        WHERE carpeta_origen IN ('CREG_RESOLUCIONES', 'CREG_CIRCULARES')
          AND COALESCE(
                (substring(sharepoint_item_id from '_((?:19|20)\\d{2})\\.htm$'))::int,
                9999
              ) < %(anio_minimo)s
        """,
        {"anio_minimo": anio_minimo_general},
    )
    n_podados = int(conteo["n"].iloc[0]) if not conteo.empty else 0
    if n_podados:
        db_manager.execute_non_query(
            """
            DELETE FROM ontologia.informes_documentos
            WHERE carpeta_origen IN ('CREG_RESOLUCIONES', 'CREG_CIRCULARES')
              AND COALESCE(
                    (substring(sharepoint_item_id from '_((?:19|20)\\d{2})\\.htm$'))::int,
                    9999
                  ) < %(anio_minimo)s
            """,
            {"anio_minimo": anio_minimo_general},
        )
        logger.info(
            f"[INFORMES] Podados {n_podados} documentos CREG fuera de la ventana "
            f"de {ANIOS_RETENCION_CREG} años (núcleo excluido, nunca se poda)"
        )


# Fase 37 (continuación 2026-08-20) — la misma plataforma Alejandría que
# aloja la normativa de la CREG también aloja la de la UPME y del Ministerio
# de Minas y Energía (MME) — ver docstring de gestor_normativo_client.py.
# Reutiliza _procesar_documento_creg() tal cual (genérica: solo depende de
# doc["numero"]/doc["url_relativa"], nunca asume CREG específicamente) — sin
# lista "núcleo" aquí, a diferencia de la CREG: estas 2 entidades no tienen
# hoy ninguna resolución citada como fuente regulatoria en
# core/umbrales_oficiales.py, así que no hay nada que excluir de la poda por
# años todavía (si en el futuro se cita una, agregarla a una lista análoga
# a NUCLEO_RESOLUCIONES_CREG).
ENTIDADES_UPME_MME = [
    # (entidad_slug, etiqueta_resoluciones, etiqueta_circulares)
    (_ENTIDAD_UPME, "UPME_RESOLUCIONES", "UPME_CIRCULARES"),
    (_ENTIDAD_MME, "MME_RESOLUCIONES", "MME_CIRCULARES"),
]


def _indexar_upme_mme_normativa(hash_map: dict, contador: _Contador) -> None:
    """Indexa resoluciones+circulares de UPME y MME de los últimos
    ANIOS_RETENCION_CREG años (misma ventana de retención que la normativa
    CREG, mismo criterio). A diferencia de la CREG (páginas por año), estas
    2 entidades sirven TODOS los años en una sola página
    (`listar_documentos_entidad()`) — se filtra por año en memoria, sin
    poda posterior necesaria (nunca se llega a insertar lo que está fuera
    de ventana, distinto del patrón de _indexar_creg_normativa)."""
    anio_actual = date.today().year
    anio_minimo = anio_actual - ANIOS_RETENCION_CREG + 1

    async def _run():
        for entidad, etiqueta_res, etiqueta_cir in ENTIDADES_UPME_MME:
            for tipo, etiqueta in [("resoluciones", etiqueta_res), ("circulares", etiqueta_cir)]:
                docs = await _creg_listar_documentos_entidad(entidad, tipo)
                for doc in docs:
                    if doc["anio"] < anio_minimo:
                        continue
                    await _procesar_documento_creg(doc, tipo, etiqueta, hash_map, contador)

    asyncio.run(_run())


# Fase 37 (continuación 2026-08-21) — Proyectos de Resolución de la CREG:
# normativa EN TRÁMITE (consulta pública), no vigente todavía — hallazgo al
# reauditar las exclusiones documentadas en docs/FUENTES_RAG.md. Usa
# exactamente el mismo mecanismo que las resoluciones definitivas
# (`listar_documentos_anio()`, páginas por año — verificado en vivo que
# "proyectos_resolucion_por_orden_cronologico_<año>.html" existe con el
# mismo patrón de clases CSS) y el mismo `_procesar_documento_creg()`
# genérico — cero cambios de cliente. Tema propio distinto de
# 'creg_normativa' a propósito: el Asistente debe poder distinguir "esto es
# ley vigente" de "esto es un proyecto en consulta, todavía puede cambiar".
def _indexar_creg_proyectos_resolucion(hash_map: dict, contador: _Contador) -> None:
    etiqueta = "CREG_PROYECTOS_RESOLUCION"
    anio_actual = date.today().year
    anio_minimo = anio_actual - ANIOS_RETENCION_CREG + 1

    async def _run():
        for anio in range(anio_minimo, anio_actual + 1):
            docs = await _creg_listar_documentos_anio("proyectos_resolucion", anio)
            for doc in docs:
                await _procesar_documento_creg(doc, "proyectos_resolucion", etiqueta, hash_map, contador)

    asyncio.run(_run())


# Fase 37 (continuación 2026-08-21) — Conceptos jurídicos del Ministerio de
# Minas y Energía: memorandos técnicos/interpretaciones jurídicas, a menudo
# ligados a un Proyecto de Resolución en trámite (ver arriba) — mismo
# hallazgo de la reauditoría. UPME NO tiene página de Conceptos en esta
# plataforma (confirmado 404 con y sin sufijo "_upme") — solo se indexa MME.
def _indexar_mme_conceptos(hash_map: dict, contador: _Contador) -> None:
    etiqueta = "MME_CONCEPTOS"
    anio_actual = date.today().year
    anio_minimo = anio_actual - ANIOS_RETENCION_CREG + 1

    async def _run():
        docs = await _creg_listar_documentos_entidad(_ENTIDAD_MME_CONCEPTOS, "conceptos")
        for doc in docs:
            if doc["anio"] < anio_minimo:
                continue
            await _procesar_documento_creg(doc, "conceptos", etiqueta, hash_map, contador)

    asyncio.run(_run())


# Fase 37 (continuación 2026-08-20) — informes/estudios técnicos que la UPME
# publica en su propio sitio (www.upme.gov.co) — distinto de su normativa
# (ver _indexar_upme_mme_normativa arriba). Ver docstring de
# infrastructure/upme/upme_wp_client.py para el porqué de listar desde la
# portada en vez de buscar por nombre de informe.
MAX_PAGINAS_INFORME_UPME = 60  # algunos informes superan las 90MB/300 páginas


async def _procesar_publicacion_upme(
    doc: dict, hash_map: dict, contador: _Contador,
) -> None:
    nombre = doc["nombre_archivo"]
    etiqueta = "UPME_PUBLICACIONES"
    contador.archivos += 1

    contenido = await _upme_descargar_pdf(doc["url_pdf"])
    if not contenido:
        return
    hash_contenido = hashlib.sha256(contenido).hexdigest()

    if hash_map.get((etiqueta, nombre)) == hash_contenido:
        return  # sin cambios desde la última corrida

    chunks = extraer_chunks(contenido, "pdf", max_paginas=MAX_PAGINAS_INFORME_UPME)
    if not chunks:
        return

    documento_id = _upsert_documento(
        etiqueta, nombre, "pdf", hash_contenido,
        doc["url_pdf"], len(contenido), None,
    )
    _reindexar_chunks(documento_id, chunks)
    contador.procesados += 1
    contador.chunks += len(chunks)
    logger.info(f"[INFORMES] {nombre} (UPME publicaciones): {len(chunks)} chunks indexados")


def _indexar_publicaciones_upme(hash_map: dict, contador: _Contador) -> None:
    """Indexa los informes/estudios técnicos de las páginas curadas de UPME
    (ver PAGINAS_UPME — portada + estudios-y-publicaciones) — se
    autoactualiza sin mantenimiento nuestro (si UPME cambia qué muestra en
    esas páginas, la próxima corrida diaria lo refleja), excluyendo
    trámites/normativa/formularios (ver
    infrastructure/upme/upme_wp_client.py::_PATRONES_EXCLUIDOS). Sin poda
    por año — a diferencia de la normativa CREG/UPME/MME, estos son informes
    de baja cadencia (el listado típicamente tiene <35 documentos entre
    ambas páginas, todos vigentes) y las propias páginas de UPME ya hacen
    ese trabajo de curación por nosotros: cuando UPME reemplaza un informe,
    deja de aparecer en la próxima corrida, pero el documento viejo queda
    huérfano en la BD (no se borra automáticamente) — aceptable dado el
    volumen bajo, revisar manualmente si se vuelve un problema real."""
    docs: list = []
    vistos_nombres = set()
    for url_pagina in _PAGINAS_UPME:
        for doc in _upme_listar_publicaciones(url_pagina):
            if doc["nombre_archivo"] in vistos_nombres:
                continue
            vistos_nombres.add(doc["nombre_archivo"])
            docs.append(doc)
    if not docs:
        logger.warning("[INFORMES] Sin publicaciones encontradas en las páginas curadas de UPME")
        return

    async def _run():
        for doc in docs:
            await _procesar_publicacion_upme(doc, hash_map, contador)

    asyncio.run(_run())


# Fase 37 (continuación 2026-08-20) — contenido misional propio del sitio
# del Ministerio de Minas y Energía (minenergia.gov.co) — hallazgo real: el
# Plan de Expansión de Referencia Generación-Transmisión (uno de los
# documentos de planeación más importantes del sector) no estaba en ningún
# corpus ya indexado. Ver docstring de infrastructure/minenergia/minenergia_client.py.
MAX_PAGINAS_INFORME_MME = 60  # mismo criterio que MAX_PAGINAS_INFORME_UPME


async def _procesar_publicacion_mme(
    doc: dict, etiqueta: str, hash_map: dict, contador: _Contador,
) -> None:
    nombre = doc["nombre_archivo"]
    contador.archivos += 1

    contenido = await _mme_descargar_pdf(doc["url_pdf"])
    if not contenido:
        return
    hash_contenido = hashlib.sha256(contenido).hexdigest()

    if hash_map.get((etiqueta, nombre)) == hash_contenido:
        return  # sin cambios desde la última corrida

    chunks = extraer_chunks(contenido, "pdf", max_paginas=MAX_PAGINAS_INFORME_MME)
    if not chunks:
        return

    documento_id = _upsert_documento(
        etiqueta, nombre, "pdf", hash_contenido,
        doc["url_pdf"], len(contenido), None,
    )
    _reindexar_chunks(documento_id, chunks)
    contador.procesados += 1
    contador.chunks += len(chunks)
    logger.info(f"[INFORMES] {nombre} ({etiqueta}): {len(chunks)} chunks indexados")


def _indexar_publicaciones_mme(hash_map: dict, contador: _Contador) -> None:
    """Indexa los PDFs de las páginas misionales curadas del sitio del
    Ministerio (ver PAGINAS_MISIONALES) — hoy solo "Planes de Expansión",
    extensible agregando más entradas a esa lista cuando se identifiquen
    otras páginas misionales con contenido técnico real (no PQRS/trámites)."""
    async def _run():
        for etiqueta, ruta in _PAGINAS_MISIONALES_MME:
            docs = _mme_listar_publicaciones(ruta)
            if not docs:
                logger.warning(f"[INFORMES] Sin publicaciones encontradas en '{ruta}' (MME)")
                continue
            for doc in docs:
                await _procesar_publicacion_mme(doc, etiqueta, hash_map, contador)

    asyncio.run(_run())


async def _recorrer_carpeta_planeacion_xm(
    ruta: str, etiqueta: str, hash_map: dict, contador: _Contador,
    excluir_nombres: frozenset = frozenset(), profundidad: int = 0,
) -> None:
    """Recorre recursivamente el árbol año→mes→semana de una ruta ya
    verificada del repositorio público de XM hasta encontrar archivos —
    solo PDF se indexa (ver docstring de RUTAS_PLANEACION_XM); otros tipos
    (zip, xlsm) se ignoran, mismo criterio de curación por relevancia del
    resto del RAG. excluir_nombres evita recorrer dos veces una subcarpeta
    ya cubierta por otra entrada de RUTAS_PLANEACION_XM. Las carpetas de
    año anteriores a la ventana de retención (ver ANIOS_RETENCION_PLANEACION_XM)
    ni siquiera se recorren — no solo se podan después."""
    if profundidad > MAX_PROFUNDIDAD_PLANEACION_XM:
        logger.error(f"[INFORMES] Profundidad excesiva en '{ruta[:120]}' (XM) — abortando esa rama")
        return
    anio_minimo = _anio_minimo_planeacion_xm()
    items = await _xm_listar_ficheros(ruta)
    for item in items:
        nombre = item.get("nombre", "")
        if not nombre or nombre in excluir_nombres:
            continue
        if nombre.isdigit() and len(nombre) == 4 and int(nombre) < anio_minimo:
            continue  # carpeta de año fuera de la ventana de retención
        ruta_item = f"{ruta}/{nombre}"
        tipo = item.get("idTipoContenido")
        if tipo == _XM_TIPO_CARPETA:
            await _recorrer_carpeta_planeacion_xm(
                ruta_item, etiqueta, hash_map, contador, excluir_nombres, profundidad + 1
            )
        elif tipo == _XM_TIPO_PDF:
            await _procesar_item_planeacion_xm(ruta_item, item, etiqueta, hash_map, contador)


def _indexar_planeacion_xm(hash_map: dict, contador: _Contador) -> None:
    async def _run():
        for etiqueta, ruta, excluir in RUTAS_PLANEACION_XM:
            await _recorrer_carpeta_planeacion_xm(ruta, etiqueta, hash_map, contador, excluir)

    asyncio.run(_run())
    n_podados = _podar_planeacion_xm_historico()
    if n_podados:
        logger.info(
            f"[INFORMES] Podados {n_podados} informes de Planeación XM fuera de la "
            f"ventana de {ANIOS_RETENCION_PLANEACION_XM} años"
        )


def main() -> None:
    hashes_existentes = db_manager.query_df(
        "SELECT carpeta_origen, nombre_archivo, hash_contenido FROM ontologia.informes_documentos"
    )
    hash_map = {
        (row["carpeta_origen"], row["nombre_archivo"]): row["hash_contenido"]
        for _, row in hashes_existentes.iterrows()
    } if not hashes_existentes.empty else {}

    contador = _Contador()

    for fuente, fn in [
        ("PMO", _indexar_carpetas_pmo),
        ("Actas ELECTROCAQUETA", _indexar_actas_electrocaqueta),
        ("Boletín XM", _indexar_boletin_xm),
        ("Informe de Empalme", _indexar_informe_empalme),
        ("Informes diarios XM", _indexar_informes_diarios_xm),
        ("Comunidades Energéticas", lambda hm, c: _indexar_carpetas_con_etiqueta(CARPETAS_COMUNIDADES, hm, c)),
        ("Colombia Solar", lambda hm, c: _indexar_carpetas_con_etiqueta(CARPETAS_COLOMBIA_SOLAR, hm, c)),
        ("Subsidios", lambda hm, c: _indexar_carpetas_con_etiqueta(CARPETAS_SUBSIDIOS, hm, c)),
        (
            "Proyectos estratégicos",
            lambda hm, c: _indexar_carpetas_con_etiqueta(CARPETAS_PROYECTOS_ESTRATEGICOS, hm, c),
        ),
        (
            "Comunidades — esquemas de comercialización",
            lambda hm, c: _indexar_carpetas_con_etiqueta(CARPETAS_COMUNIDADES_COMERCIALIZACION, hm, c),
        ),
        ("Planeación XM", _indexar_planeacion_xm),
        ("Boletín Energético XM", _indexar_boletin_energetico_xm),
        ("Informe del Despacho diario XM", _indexar_infodespacho_xm),
        ("Normativa CREG", _indexar_creg_normativa),
        ("Normativa UPME/MME", _indexar_upme_mme_normativa),
        ("Proyectos de Resolución CREG", _indexar_creg_proyectos_resolucion),
        ("Conceptos jurídicos MME", _indexar_mme_conceptos),
        ("Publicaciones técnicas UPME", _indexar_publicaciones_upme),
        ("Publicaciones misionales MME", _indexar_publicaciones_mme),
    ]:
        try:
            fn(hash_map, contador)
        except Exception as e:
            logger.error(f"[INFORMES] Fuente '{fuente}' falló: {e}")

    logger.info(
        f"[INFORMES] {contador.procesados}/{contador.archivos} documentos nuevos/actualizados, "
        f"{contador.chunks} chunks — resto sin cambios desde la última corrida"
    )


if __name__ == "__main__":
    main()

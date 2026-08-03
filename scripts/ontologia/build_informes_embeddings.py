#!/usr/bin/env python3
"""
RAG — Fase 8: indexa informes PDF/PPTX/DOCX de SharePoint en
ontologia.informes_texto_embeddings — segundo corpus del RAG, junto al de
observaciones de contratos (build_texto_embeddings.py).

Cuatro fuentes (decididas tras explorar en vivo qué carpetas de SharePoint
relacionadas al portal tienen contenido real, no solo estructura vacía —
"20. Trazabilidad Convocatoria..." resultó estar 100% vacía, 38 carpetas sin
un solo archivo):
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

Idempotente por hash de contenido: solo re-descarga/re-embebe un archivo si
cambió en SharePoint desde la última corrida.

Uso:
    venv/bin/python3 scripts/ontologia/build_informes_embeddings.py
"""

import hashlib
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests  # noqa: E402

from etl.etl_sharepoint_sync import _get_access_token  # noqa: E402
from api.v1.routes.reports import (  # noqa: E402
    _sp_open_folder, _graph_list_all_children, _sp_download_item,
    _parse_folder_date, BOLETINES_ENERGETICOS_FOLDER, INFORMES_DIARIOS_XM_FOLDER,
)
from api.v1.routes.contratos_or import SHARE_URL_ACTAS  # noqa: E402
from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.ml.document_extraction import extraer_chunks  # noqa: E402
from infrastructure.ml.embeddings import embed_batch, MODEL_NAME  # noqa: E402
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
        ("Informes diarios XM", _indexar_informes_diarios_xm),
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

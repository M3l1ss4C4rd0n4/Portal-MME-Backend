#!/usr/bin/env python3
"""
Ontología — Fase 37 Parte B: vigilancia dirigida de las 8 resoluciones CREG
"núcleo" que sustentan la lógica regulatoria central del portal
(core/umbrales_oficiales.py — Índice NE, HSIN, PBP, Condición del Sistema).

Motivo (hallazgo real, 2026-08-19): la Resolución CREG 101 112 de 2026 derogó
una regla del Índice NE que el portal siguió aplicando 2 meses después de su
derogación, sin que nadie lo notara — se encontró por casualidad al revisar
manualmente el listado cronológico de la CREG, no por ningún mecanismo
automático. Este script busca cerrar exactamente ese hueco hacia adelante.

El panel "MODIFICACIONES" del visor de la CREG NO tiene datos poblados en
esta plataforma (ver docstring de infrastructure/creg/gestor_normativo_client.py)
— no sirve como fuente de "qué modificó a esta resolución".

Dos niveles de detección, complementarios (ronda 2026-08-20, tras auditar a
mano los 32 hallazgos de NIVEL 2 de la ronda anterior sin encontrar ningún
bug nuevo, pero descubriendo que el propio texto consolidado de la CREG ya
trae el dato preciso):

NIVEL 1 (alta confianza) — el texto consolidado de cada resolución núcleo,
tal como lo publica el Gestor Normativo de la CREG, incrusta anotaciones de
vigencia del tipo "<Numeral modificado por el artículo 1 de la Resolución
101 112 de 2026. El nuevo texto es el siguiente:>", indicando con precisión
qué elemento fue modificado, por qué artículo, y de qué resolución — sin
depender de que otro documento mencione a la núcleo con una palabra de
modificación cerca. Es el registro legislativo oficial de la norma. Su
limitación: depende de que el Gestor Normativo ya haya incorporado la
modificación al texto consolidado — puede haber rezago entre la publicación
de una resolución nueva y su reflejo aquí.

NIVEL 2 (mejor esfuerzo) — el mecanismo original: busca, DENTRO del texto ya
indexado de resoluciones y circulares recientes
(build_informes_embeddings.py::_indexar_creg_normativa), menciones literales
a cualquiera de las 8 resoluciones núcleo combinadas con una palabra de
modificación regulatoria ("modifica", "deroga", "sustituye", "adiciona",
"subroga") — el mismo patrón textual que habría delatado la Res. 101
112/2026 si se hubiera podido buscar automáticamente en su momento. Se
mantiene como red adicional: puede detectar una mención antes de que el
Gestor Normativo actualice el texto consolidado de NIVEL 1.

Ninguno de los dos reemplaza una revisión jurídica periódica — solo reducen
el riesgo de que un cambio pase inadvertido durante meses, como ya ocurrió
una vez con la Res. 101 112/2026.

Uso:
    venv/bin/python3 scripts/ontologia/vigilancia_normativa_creg.py
"""

import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402
from scripts.ontologia.build_informes_embeddings import (  # noqa: E402
    ANIOS_RETENCION_CREG,
    NUCLEO_RESOLUCIONES_CREG,
    _normalizar_segmentos_numero_creg,
)
from domain.services.notification_service import broadcast_alert  # noqa: E402

logger = get_logger(__name__)

PALABRAS_MODIFICACION = ("modifica", "deroga", "sustituye", "adiciona", "subroga")

# NIVEL 1 (alta confianza) — el propio texto consolidado de cada resolución
# núcleo, tal como lo publica el Gestor Normativo de la CREG, incrusta
# anotaciones de vigencia del tipo:
#   <Numeral modificado por el artículo 1 de la Resolución 101 112 de 2026.
#   El nuevo texto es el siguiente:>
# indicando exactamente qué elemento (artículo/literal/numeral/definición/
# anexo/parágrafo/...) fue modificado/derogado/adicionado/sustituido, por
# qué artículo, y de qué resolución — sin depender de que otra resolución
# mencione a la núcleo con una palabra de modificación cerca (NIVEL 2, ver
# _patrones_busqueda_nucleo). Verificado en vivo (2026-08-20): 138
# anotaciones reales encontradas en las 8 resoluciones núcleo, incluida la
# misma Resolución CREG 101 112 de 2026 que motivó todo este mecanismo.
RE_NOTA_VIGENCIA = re.compile(
    r'<\s*([A-Za-zÁÉÍÓÚáéíóúÑñ]+(?:\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+)?)\s+'
    r'(modificad[oa]|derogad[oa]|adicionad[oa]|sustituid[oa]|subrogad[oa])\s+'
    r'por\s+el\s+art[ií]culo\s+(\d+[A-Za-z]?)\s+'
    r'de\s+la\s+Resoluci[oó]n\s+(\d[\d\s]*\d|\d)\s+de\s+(\d{4})',
    re.IGNORECASE,
)


def _patrones_busqueda_nucleo() -> list:
    """Genera, por cada resolución núcleo, las variantes de texto con las que
    podría aparecer citada dentro de otro documento (con y sin ceros a la
    izquierda — ver hallazgo de formato inconsistente en gestor_normativo_client.py)."""
    patrones = []
    for anio, numero in NUCLEO_RESOLUCIONES_CREG:
        canonico = _normalizar_segmentos_numero_creg(numero)
        variantes = {numero.replace("_", " "), canonico.replace("_", " ")}
        for variante in variantes:
            patrones.append((anio, numero, f"{variante} de {anio}"))
    return patrones


def _detectar_modificaciones_via_notas_vigencia() -> list:
    """
    Escanea el texto ya indexado de las 8 resoluciones núcleo (carpeta
    CREG_RESOLUCIONES_NUCLEO) en busca de anotaciones de vigencia (ver
    RE_NOTA_VIGENCIA arriba) — el registro legislativo oficial de cada norma,
    tal como lo mantiene el Gestor Normativo de la CREG.

    Limitación conocida (por eso NIVEL 2 se mantiene como red adicional, no
    se reemplaza): depende de que el Gestor Normativo ya haya incorporado la
    modificación al texto consolidado de la resolución núcleo — puede haber
    un rezago entre la publicación de una resolución nueva y su reflejo aquí.

    Se filtra a modificaciones realizadas por resoluciones de los últimos
    ANIOS_RETENCION_CREG años (mismo criterio de retención que el corpus
    general) — sin este filtro, cada corrida repetiría decenas de
    anotaciones históricas ya incorporadas desde hace años (verificado: hay
    anotaciones reales desde 2006) que no requieren revisión semanal.
    """
    anio_minimo = date.today().year - ANIOS_RETENCION_CREG + 1
    df = db_manager.query_df(
        """
        SELECT d.nombre_archivo, e.contenido
        FROM ontologia.informes_texto_embeddings e
        JOIN ontologia.informes_documentos d ON d.documento_id = e.documento_id
        WHERE d.carpeta_origen = 'CREG_RESOLUCIONES_NUCLEO'
        """
    )

    hallazgos = []
    vistos = set()
    for _, row in df.iterrows():
        for m in RE_NOTA_VIGENCIA.finditer(row["contenido"]):
            elemento, accion, articulo, num_res, anio_res = m.groups()
            anio_res_int = int(anio_res)
            if anio_res_int < anio_minimo:
                continue
            clave = (
                row["nombre_archivo"], elemento.strip().lower(), accion.lower(),
                articulo.strip(), num_res.strip(), anio_res_int,
            )
            if clave in vistos:
                continue
            vistos.add(clave)
            hallazgos.append({
                "resolucion_nucleo": row["nombre_archivo"],
                "elemento": elemento.strip(),
                "accion": accion.lower(),
                "articulo_modificador": articulo.strip(),
                "resolucion_modificadora": f"{num_res.strip()} de {anio_res_int}",
            })
    return hallazgos


def main() -> None:
    hallazgos_nivel1 = _detectar_modificaciones_via_notas_vigencia()
    if hallazgos_nivel1:
        logger.warning(
            f"[VIGILANCIA_NORMATIVA_CREG] NIVEL 1 (alta confianza, notas de "
            f"vigencia): {len(hallazgos_nivel1)} modificación(es) real(es) a "
            f"resoluciones núcleo en los últimos {ANIOS_RETENCION_CREG} años:"
        )
        for h in hallazgos_nivel1:
            logger.warning(
                f"[VIGILANCIA_NORMATIVA_CREG]   {h['resolucion_nucleo']}: "
                f"{h['elemento']} {h['accion']} por el artículo "
                f"{h['articulo_modificador']} de la Resolución CREG "
                f"{h['resolucion_modificadora']}"
            )

        # De silencioso a notificado (Fase 39, ítem C.1): un hallazgo de
        # NIVEL 1 (alta confianza) es exactamente el tipo de cambio que
        # tardó 2 meses en detectarse la vez pasada porque nadie leía el
        # log proactivamente. Se envía por el mismo canal ya usado para
        # alertas críticas (Telegram/email) — nunca los de NIVEL 2 (mejor
        # esfuerzo, más ruidoso, no se notifica activamente).
        try:
            texto = (
                f"🏛️ *Vigilancia normativa CREG* — posible cambio en una "
                f"resolución núcleo del portal:\n\n"
                + "\n".join(
                    f"• *{h['resolucion_nucleo']}*: {h['elemento']} "
                    f"{h['accion']} por el artículo {h['articulo_modificador']} "
                    f"de la Resolución CREG {h['resolucion_modificadora']}"
                    for h in hallazgos_nivel1
                )
                + "\n\nRevisar si `core/umbrales_oficiales.py` (Índice NE/HSIN/PBP) "
                "sigue reflejando la regla vigente."
            )
            broadcast_alert(texto, severity="WARNING")
        except Exception as e:
            logger.error(f"[VIGILANCIA_NORMATIVA_CREG] Error notificando hallazgo NIVEL 1: {e}")
    else:
        logger.info(
            f"[VIGILANCIA_NORMATIVA_CREG] NIVEL 1 — sin modificaciones nuevas "
            f"en los últimos {ANIOS_RETENCION_CREG} años según notas de "
            f"vigencia del texto consolidado."
        )

    hallazgos = []
    for anio, numero_original, patron in _patrones_busqueda_nucleo():
        df = db_manager.query_df(
            """
            SELECT DISTINCT d.nombre_archivo, d.carpeta_origen
            FROM ontologia.informes_texto_embeddings e
            JOIN ontologia.informes_documentos d ON d.documento_id = e.documento_id
            WHERE d.carpeta_origen IN ('CREG_RESOLUCIONES', 'CREG_CIRCULARES')
              AND e.contenido ILIKE %(patron)s
              AND (""" + " OR ".join(
                "e.contenido ILIKE %(kw{})s".format(i) for i in range(len(PALABRAS_MODIFICACION))
            ) + ")",
            {
                "patron": f"%{patron}%",
                **{f"kw{i}": f"%{kw}%" for i, kw in enumerate(PALABRAS_MODIFICACION)},
            },
        )
        for _, row in df.iterrows():
            hallazgos.append({
                "resolucion_nucleo": f"{numero_original} de {anio}",
                "documento_encontrado": row["nombre_archivo"],
                "carpeta": row["carpeta_origen"],
            })

    if hallazgos:
        logger.warning(
            f"[VIGILANCIA_NORMATIVA_CREG] NIVEL 2 (mejor esfuerzo, mención externa): "
            f"{len(hallazgos)} mención(es) de modificación potencial a resoluciones "
            f"núcleo — revisar manualmente:"
        )
        for h in hallazgos:
            logger.warning(
                f"[VIGILANCIA_NORMATIVA_CREG]   '{h['documento_encontrado']}' "
                f"({h['carpeta']}) menciona y podría modificar la "
                f"Resolución CREG {h['resolucion_nucleo']}"
            )
    else:
        logger.info("[VIGILANCIA_NORMATIVA_CREG] NIVEL 2 — sin hallazgos, ninguna "
                     "resolución/circular reciente menciona modificar alguna de las "
                     "8 resoluciones núcleo.")


if __name__ == "__main__":
    main()

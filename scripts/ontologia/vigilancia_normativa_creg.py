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

Fase 44 (2026-09) — de spam diario a notificación inteligente + mapa de
impacto: hasta esta ronda, NIVEL 1 notificaba (Telegram/email) de forma
INCONDICIONAL cada vez que `hallazgos_nivel1` no estaba vacío, sin ninguna
tabla que recordara "esto ya se notificó" (`vistos = set()` es local a cada
ejecución) — el mismo ~25 hallazgos se reenviaban idénticos todos los días
desde al menos el 31-ago-2026, incluida la propia Res. 101 112/2026 que ya
se había corregido en el código semanas antes. Se agregan 2 cosas:

  1. Persistencia en `ontologia.vigilancia_normativa_notificado` — un
     hallazgo de NIVEL 1 solo se notifica la PRIMERA vez que se ve (mismo
     `clave` que ya deduplicaba en memoria, ahora hasheado y guardado). Sin
     recordatorio periódico: mientras la anotación de vigencia siga dentro
     de la ventana de retención, seguirá siendo un hallazgo real, pero ya
     no hace falta que el sistema lo repita cada día — distinguir
     "pendiente de aplicar" de "ya aplicado" requeriría un flujo humano de
     revisión explícito, fuera de esta ronda.
  2. Mapa de impacto (`MAPA_IMPACTO_RESOLUCIONES`) — el mensaje ya no es un
     recordatorio genérico: cita el/los archivo(s)+función(es) Python real
     afectados, si tienen espejo TypeScript, y si están cubiertos por
     `scripts/verificar_sincronia_umbrales.py` (invocado en vivo cuando
     aplica, embebiendo su resultado real — SINCRONIZADO/DESINCRONIZADO/no
     cubierto — en vez de fingir una comprobación que no ocurrió).

Uso:
    venv/bin/python3 scripts/ontologia/vigilancia_normativa_creg.py
"""

import hashlib
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
    _normalizar_numero_creg,
    _normalizar_segmentos_numero_creg,
)
from domain.services.notification_service import broadcast_alert, _plain_to_html  # noqa: E402

logger = get_logger(__name__)

PALABRAS_MODIFICACION = ("modifica", "deroga", "sustituye", "adiciona", "subroga")

# Alerta técnica dirigida SOLO al desarrollador del portal (decisión
# explícita del usuario, 2026-09): a diferencia de las alertas operativas
# del sector (embalses, precio de bolsa, etc.), esta notificación es sobre
# impacto en CÓDIGO (qué función Python/TS revisar) — el resto de
# destinatarios de sector_energetico.alert_recipients/telegram_users
# (Viceministro, Despacho, Mesa de Ayuda) no tienen relación con el
# desarrollo específico del portal, así que nunca deben recibirla.
DESARROLLADOR_TELEGRAM_CHAT_ID = 5084190952  # Melissa Cardona
DESARROLLADOR_EMAIL = "mjcardona@minenergia.gov.co"  # Melissa Cardona

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
                "clave": clave,
                "resolucion_nucleo": row["nombre_archivo"],
                "elemento": elemento.strip(),
                "accion": accion.lower(),
                "articulo_modificador": articulo.strip(),
                "resolucion_modificadora": f"{num_res.strip()} de {anio_res_int}",
            })
    return hallazgos


# ─────────────────────────────────────────────────────────────────────────
# Mapa de impacto (Fase 44) — verificado línea por línea contra
# core/umbrales_oficiales.py y umbralesOficiales.ts antes de fijarlo aquí.
# Claves: "{numero_normalizado}_{año}" vía _normalizar_numero_creg(), mismo
# formato que produce el nombre_archivo real de CREG_RESOLUCIONES_NUCLEO
# (ej. "Resolución 101_112 de 2026 CREG" -> "101_112_2026").
#
# `cubierto_por_verificador_sincronia=True` solo para las 2 resoluciones
# cuyas funciones YA están dentro de los CASOS de
# scripts/verificar_sincronia_umbrales.py (clasificar_indice_ne/
# clasificarIndiceNE, clasificar_visual_embalse/clasificarVisualEmbalse) —
# 071/2006, 140/2017 y 101_066/2024 SÍ tienen espejo TS pero NO están
# cubiertas por ese verificador; decirlo explícitamente en el mensaje evita
# fingir una comprobación automática que no ocurre.
# ─────────────────────────────────────────────────────────────────────────
MAPA_IMPACTO_RESOLUCIONES = {
    "26_2014": {
        "descripcion": "Estatuto para Situaciones de Riesgo de Desabastecimiento",
        "funciones_python": [
            "core/umbrales_oficiales.py::clasificar_indice_ne()",
            "core/umbrales_oficiales.py::clasificar_hsin()",
            "core/umbrales_oficiales.py::clasificar_visual_embalse()",
            "core/umbrales_oficiales.py::clasificar_visual_aportes()",
            "core/umbrales_oficiales.py::determinar_condicion_sistema()",
        ],
        "espejo_ts": [
            "umbralesOficiales.ts::clasificarIndiceNE()",
            "umbralesOficiales.ts::clasificarVisualEmbalse()",
            "umbralesOficiales.ts::clasificarVisualAportes()",
        ],
        "cubierto_por_verificador_sincronia": True,
    },
    "71_2006": {
        "descripcion": "Cargo por Confiabilidad y precio de escasez",
        "funciones_python": [
            "core/umbrales_oficiales.py::obtener_precios_escasez_vigentes()",
        ],
        "espejo_ts": [],
        "cubierto_por_verificador_sincronia": False,
    },
    "140_2017": {
        "descripcion": "Metodología de cálculo del Precio de Escasez Superior (PES)",
        "funciones_python": [
            "core/umbrales_oficiales.py::obtener_precios_escasez_vigentes()",
            "core/umbrales_oficiales.py::clasificar_indice_pbp()",
        ],
        "espejo_ts": [
            "umbralesOficiales.ts::clasificarVisualPrecioBolsa()",
        ],
        "cubierto_por_verificador_sincronia": False,
    },
    "125_2020": {
        "descripcion": (
            "Deroga las normas del Capítulo II (Inicio y Finalización del "
            "Período de Riesgo de Desabastecimiento) de la Res. CREG 026/2014"
        ),
        "funciones_python": [],
        "espejo_ts": [],
        "cubierto_por_verificador_sincronia": False,
        "nota": "Sin función dedicada en ningún lado — solo mencionada en el docstring del módulo.",
    },
    "209_2020": {
        "descripcion": "Senda de Referencia del embalse agregado del SIN",
        "funciones_python": [
            "core/umbrales_oficiales.py::obtener_senda_referencia()",
            "core/umbrales_oficiales.py::clasificar_indice_ne()",
        ],
        "espejo_ts": [
            "umbralesOficiales.ts::obtenerSendaReferencia()",
            "umbralesOficiales.ts::clasificarIndiceNE()",
        ],
        "cubierto_por_verificador_sincronia": True,
    },
    "101_55_2024": {
        "descripcion": "Complemento al Estatuto de Desabastecimiento",
        "funciones_python": [],
        "espejo_ts": [],
        "cubierto_por_verificador_sincronia": False,
        "nota": "Sin función dedicada en ningún lado — solo mencionada en el docstring del módulo.",
    },
    "101_66_2024": {
        "descripcion": "Tres niveles de precio de escasez (PEI/PE/PES)",
        "funciones_python": [
            "core/umbrales_oficiales.py::obtener_precios_escasez_vigentes()",
            "core/umbrales_oficiales.py::clasificar_indice_pbp()",
            "core/umbrales_oficiales.py::clasificar_visual_precio_bolsa()",
        ],
        "espejo_ts": [
            "umbralesOficiales.ts::clasificarVisualPrecioBolsa()",
        ],
        "cubierto_por_verificador_sincronia": False,
    },
    "101_112_2026": {
        "descripcion": (
            "Deroga la regla alternativa del 70% absoluto del Índice NE "
            "(Res. CREG 210/2021) — desde el 17-jun-2026 el NE se determina "
            "exclusivamente contra la senda de referencia"
        ),
        "funciones_python": [
            "core/umbrales_oficiales.py::clasificar_indice_ne()",
        ],
        "espejo_ts": [
            "umbralesOficiales.ts::clasificarIndiceNE()",
        ],
        "cubierto_por_verificador_sincronia": True,
    },
}


def _impacto_de_hallazgo(resolucion_nucleo_nombre_archivo: str) -> dict:
    """Resuelve el nombre_archivo real de la núcleo (ej. 'Resolución 101_112
    de 2026 CREG') a su entrada en MAPA_IMPACTO_RESOLUCIONES."""
    clave = _normalizar_numero_creg(resolucion_nucleo_nombre_archivo)
    return MAPA_IMPACTO_RESOLUCIONES.get(clave, {
        "descripcion": "",
        "funciones_python": [],
        "espejo_ts": [],
        "cubierto_por_verificador_sincronia": False,
    })


def _clave_hash(clave: tuple) -> str:
    """SHA-256 de la misma tupla `clave` que ya usa
    _detectar_modificaciones_via_notas_vigencia() para deduplicar en
    memoria — usada aquí como clave primaria persistente en
    ontologia.vigilancia_normativa_notificado."""
    texto = "|".join(str(x) for x in clave)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _filtrar_hallazgos_nuevos(hallazgos: list) -> list:
    """Filtra los hallazgos de NIVEL 1 que YA fueron notificados alguna vez
    (persistencia real en BD, no el `vistos` en memoria local a cada
    ejecución) — decisión de diseño: notificación única, sin recordatorio
    periódico mientras la anotación de vigencia siga dentro de la ventana
    de retención."""
    if not hallazgos:
        return []
    hashes = [_clave_hash(h["clave"]) for h in hallazgos]
    try:
        df = db_manager.query_df(
            "SELECT clave_hash FROM ontologia.vigilancia_normativa_notificado "
            "WHERE clave_hash = ANY(%(hashes)s)",
            {"hashes": hashes},
        )
        ya_notificados = set(df["clave_hash"]) if not df.empty else set()
    except Exception as e:
        # Si la tabla aún no existe (migración 041 pendiente de aplicar) o
        # falla la consulta, degradar a "nada filtrado" — mejor repetir un
        # aviso que perder uno real por un error de infraestructura.
        logger.error(
            f"[VIGILANCIA_NORMATIVA_CREG] No se pudo consultar hallazgos ya "
            f"notificados (¿falta aplicar la migración 041?): {e}"
        )
        return hallazgos

    return [h for h, hh in zip(hallazgos, hashes) if hh not in ya_notificados]


def _marcar_notificados(hallazgos: list) -> None:
    """Registra en BD los hallazgos que SÍ se acaban de notificar con éxito
    (solo se llama tras confirmar que broadcast_alert() entregó por algún
    canal) — para que la próxima corrida ya no los reenvíe."""
    for h in hallazgos:
        try:
            db_manager.execute_non_query(
                """
                INSERT INTO ontologia.vigilancia_normativa_notificado
                    (clave_hash, resolucion_nucleo, elemento, accion,
                     articulo_modificador, resolucion_modificadora)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (clave_hash) DO UPDATE SET
                    ultima_notificacion_en = now(),
                    veces_notificado = ontologia.vigilancia_normativa_notificado.veces_notificado + 1
                """,
                (
                    _clave_hash(h["clave"]), h["resolucion_nucleo"], h["elemento"],
                    h["accion"], h["articulo_modificador"], h["resolucion_modificadora"],
                ),
            )
        except Exception as e:
            logger.error(
                f"[VIGILANCIA_NORMATIVA_CREG] No se pudo registrar el hallazgo ya "
                f"notificado ({h['resolucion_nucleo']}): {e}"
            )


_CACHE_SINCRONIA = None


def _resultado_sincronia_texto() -> str:
    """Invoca scripts/verificar_sincronia_umbrales.py::evaluar_sincronia()
    UNA sola vez por corrida (memoizado) y lo formatea como una frase corta,
    para embeber en el mensaje de notificación de un hallazgo cubierto."""
    global _CACHE_SINCRONIA
    if _CACHE_SINCRONIA is None:
        try:
            from scripts.verificar_sincronia_umbrales import evaluar_sincronia
            sincronizado, discrepancias, error = evaluar_sincronia()
            if sincronizado is None:
                _CACHE_SINCRONIA = f"no se pudo verificar automáticamente ({error})"
            elif sincronizado:
                _CACHE_SINCRONIA = "SINCRONIZADO ✅ — Python y TypeScript coinciden en los casos de prueba"
            else:
                _CACHE_SINCRONIA = (
                    f"DESINCRONIZADO ⚠️ — {len(discrepancias)} discrepancia(s), "
                    f"ej.: {discrepancias[0]}"
                )
        except Exception as e:
            _CACHE_SINCRONIA = f"no se pudo verificar automáticamente (error: {e})"
    return _CACHE_SINCRONIA


# Límite real de Telegram es 4096 caracteres por mensaje (confirmado en
# vivo: la primera corrida de este mecanismo, con 25 hallazgos reales y el
# mapa de impacto completo por cada uno, superó el límite y Telegram
# respondió "400 Bad Request: message is too long" para TODOS los
# destinatarios — el email SÍ se entregó, sin este límite). Margen bajo el
# límite real para dejar espacio al encabezado/pie.
TELEGRAM_LIMITE_CARACTERES = 3800


def _construir_texto_notificacion(hallazgos: list, resumido: bool = False) -> str:
    """Arma el mensaje real de notificación, con el mapa de impacto (archivo/
    función Python y TS reales) y el resultado del verificador de sincronía
    cuando la resolución modificada está cubierta por él — en vez del
    recordatorio genérico anterior.

    `resumido=True` (usado para Telegram, que tiene límite duro de 4096
    caracteres) omite el mapa de impacto y deja solo 1 línea por hallazgo,
    con una nota final invitando a revisar el correo para el detalle
    completo. `resumido=False` (usado para el cuerpo del email, sin límite
    de longitud real) trae el mapa de impacto completo por cada hallazgo.
    """
    lineas = ["🏛️ *Vigilancia normativa CREG* — cambio nuevo en una resolución "
              "núcleo del portal:\n"]

    if resumido:
        for h in hallazgos:
            lineas.append(
                f"• {h['resolucion_nucleo']}: {h['elemento']} {h['accion']} por "
                f"el artículo {h['articulo_modificador']} de la Resolución CREG "
                f"{h['resolucion_modificadora']}"
            )
        lineas.append("")
        lineas.append(
            "Ver el correo para el detalle completo (archivo/función Python y "
            "TypeScript afectados + estado de sincronía)."
        )
        texto = "\n".join(lineas)
        if len(texto) > TELEGRAM_LIMITE_CARACTERES:
            # Defensa adicional si el backlog crece más de lo ya visto —
            # nunca dejar que Telegram rechace el mensaje completo por unos
            # pocos hallazgos de más; el correo siempre trae el detalle total.
            recorte = lineas[:1]
            acumulado = len(recorte[0])
            n_incluidos = 0
            for linea in lineas[1:-2]:
                if acumulado + len(linea) + 1 > TELEGRAM_LIMITE_CARACTERES - 150:
                    break
                recorte.append(linea)
                acumulado += len(linea) + 1
                n_incluidos += 1
            restantes = len(hallazgos) - n_incluidos
            recorte.append("")
            recorte.append(
                f"…y {restantes} hallazgo(s) más — ver el correo para el "
                f"detalle completo."
            )
            texto = "\n".join(recorte)
        return texto

    for h in hallazgos:
        impacto = _impacto_de_hallazgo(h["resolucion_nucleo"])
        lineas.append(
            f"• *{h['resolucion_nucleo']}*: {h['elemento']} {h['accion']} por "
            f"el artículo {h['articulo_modificador']} de la Resolución CREG "
            f"{h['resolucion_modificadora']}"
        )
        if impacto.get("descripcion"):
            lineas.append(f"  _{impacto['descripcion']}_")
        if impacto["funciones_python"]:
            lineas.append("  Python: " + ", ".join(impacto["funciones_python"]))
        else:
            lineas.append("  Python: sin función dedicada — revisar manualmente si aplica.")
        if impacto["espejo_ts"]:
            lineas.append("  TypeScript: " + ", ".join(impacto["espejo_ts"]))
        else:
            lineas.append("  TypeScript: sin espejo (solo backend).")
        if impacto["cubierto_por_verificador_sincronia"]:
            lineas.append(f"  Sincronía Python↔TS: {_resultado_sincronia_texto()}")
        else:
            lineas.append(
                "  Sincronía Python↔TS: no cubierto por el verificador automático "
                "— revisar manualmente."
            )
        lineas.append("")

    lineas.append(
        "Revisar si core/umbrales_oficiales.py (y su espejo TS, si aplica) "
        "siguen reflejando la regla vigente."
    )
    return "\n".join(lineas)


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

        # Fase 44: solo se notifica lo que NUNCA se notificó antes (persistencia
        # real en BD) — corrige el spam diario de reenviar el mismo hallazgo.
        nuevos = _filtrar_hallazgos_nuevos(hallazgos_nivel1)
        if not nuevos:
            logger.info(
                f"[VIGILANCIA_NORMATIVA_CREG] NIVEL 1 — los {len(hallazgos_nivel1)} "
                f"hallazgo(s) ya habían sido notificados en una corrida anterior; "
                f"no se reenvía."
            )
        else:
            logger.warning(
                f"[VIGILANCIA_NORMATIVA_CREG] NIVEL 1 — {len(nuevos)}/{len(hallazgos_nivel1)} "
                f"hallazgo(s) son NUEVOS (nunca notificados) — notificando."
            )
            try:
                texto_telegram = _construir_texto_notificacion(nuevos, resumido=True)
                texto_email = _construir_texto_notificacion(nuevos, resumido=False)
                resultado = broadcast_alert(
                    texto_telegram,
                    severity="WARNING",
                    email_subject="🏛️ Vigilancia normativa CREG — cambio nuevo en resolución núcleo",
                    email_body_html=_plain_to_html(texto_email),
                    telegram_chat_ids=[DESARROLLADOR_TELEGRAM_CHAT_ID],
                    email_override=[DESARROLLADOR_EMAIL],
                )
                entregado = (
                    resultado.get("telegram", {}).get("sent", 0) > 0
                    or resultado.get("email", {}).get("sent", 0) > 0
                )
                if entregado:
                    _marcar_notificados(nuevos)
                else:
                    logger.error(
                        "[VIGILANCIA_NORMATIVA_CREG] broadcast_alert() no entregó "
                        "por ningún canal — NO se marca como notificado, para "
                        "reintentar en la próxima corrida."
                    )
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

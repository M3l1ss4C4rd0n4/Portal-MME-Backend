"""
Tarea Celery — Fase 11: diagnósticos de HomeSlider generados por IA, 1 vez al día.

Genera, en una sola llamada a Gemini, el texto narrativo de los 3 slides ya
corregidos de HomeSlider (Reservas Hídricas, Precio y Generación, Térmica),
combinando:
  1. Datos estructurados y ya validados de sector_snapshot.py (precio, embalses,
     aportes, umbrales regulatorios NE/HSIN/PBP/condición del sistema).
  2. Los índices regulatorios y sus relaciones de derivación con cita normativa,
     desde ontologia.dim_metrica / metrica_relacion (Fase 12).
  3. Contexto narrativo real recuperado por RAG (ontologia.informes_texto_embeddings)
     — informes diarios de XM y la guía de alertas del sector, que documenta la
     regla de persistencia usada para no sobre-alertar por un solo día atípico.

El resultado se cachea en sector_energetico.diagnosticos_ia — nunca se genera
más de una vez por día, todos los visitantes del portal leen el mismo texto.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

from tasks import app as celery_app

logger = logging.getLogger(__name__)

SLIDE_IDS = ("reservas", "precio_generacion", "termica")

# Queries de RAG dirigidas por slide — cada una apunta al contenido narrativo
# real que ese slide necesita (no una lista genérica compartida), para que el
# contexto recuperado sea relevante a lo que cada texto va a explicar.
RAG_QUERIES_POR_SLIDE: Dict[str, List[str]] = {
    "reservas": [
        "vertimientos senda de referencia balance hídrico embalses",
        "objetivo XM ante El Niño composición de la matriz energética",
    ],
    "precio_generacion": [
        "composición de la matriz energética generación por fuente",
        "despacho precio de bolsa reglas de persistencia CREG",
    ],
    "termica": [
        "generación térmica despacho consumo de combustible carbón gas",
    ],
}

# Búsquedas con `tema` explícito (Fase 11 Ronda 5) — garantizan que un tipo de
# documento conocido y valioso aparezca siempre, en vez de depender de que la
# similitud semántica lo encuentre por casualidad (verificado: sin esto,
# InformeDiario_*_SeguimientoDespacho.pdf y el boletín de El Niño casi nunca
# salían en el top-k pese a estar indexados).
RAG_QUERIES_POR_TEMA_POR_SLIDE: Dict[str, List[tuple]] = {
    "reservas": [("pronóstico El Niño intensidad probabilidad", "panorama_climatico")],
    "precio_generacion": [("disponibilidad de plantas y precio de predespacho", "despacho")],
    "termica": [("plantas indisponibles mantenimiento generación térmica", "despacho")],
}


def _fetch_snapshot() -> Dict[str, Any]:
    """Datos estructurados y ya validados de sector_snapshot.py vía llamada HTTP interna."""
    import requests
    from core.config import settings

    url = f"{settings.API_BASE_URL.rstrip('/')}/v1/sector/snapshot"
    resp = requests.get(url, headers={"X-API-Key": settings.API_KEY}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _fetch_termica() -> Optional[Dict[str, Any]]:
    """
    Participación térmica de hoy (1 día) vs. promedio de los últimos días — misma
    lógica SQL que portal-direccion-mme/src/app/api/sector/{termica,detalle}/route.ts,
    replicada aquí en Python porque esos endpoints viven en el BFF de Next.js, no
    en este backend. Ventanas deliberadamente distintas entre hoy (1 día) y el
    promedio (8 días, BETWEEN fecha-7 AND fecha) — es la misma discrepancia de
    ventana que ya se le pide reconciliar al modelo en el prompt.
    """
    from infrastructure.database.manager import db_manager

    fecha_row = db_manager.query_df(
        "SELECT MAX(fecha) AS fecha FROM sector_energetico.metrics WHERE metrica='Gene' AND entidad='Sistema'"
    )
    if fecha_row.empty or fecha_row["fecha"].iloc[0] is None:
        return None
    fecha = fecha_row["fecha"].iloc[0]

    hoy = db_manager.query_df(
        """
        WITH termica_dia AS (
            SELECT SUM(m.valor_gwh) AS gwh
            FROM sector_energetico.metrics m
            JOIN sector_energetico.catalogos c
              ON m.recurso = c.codigo AND c.catalogo = 'ListadoRecursos' AND c.tipo = 'TERMICA'
            WHERE m.metrica = 'Gene' AND m.entidad = 'Recurso' AND m.fecha = %(fecha)s
        ),
        total_dia AS (
            SELECT SUM(valor_gwh) AS gwh
            FROM sector_energetico.metrics
            WHERE metrica = 'Gene' AND entidad = 'Sistema' AND recurso = 'Sistema' AND fecha = %(fecha)s
        )
        SELECT ROUND((t.gwh / NULLIF(td.gwh, 0) * 100)::numeric, 1) AS pct_termica_hoy
        FROM termica_dia t, total_dia td
        """,
        {"fecha": fecha},
    )

    promedio_7d = db_manager.query_df(
        """
        WITH generacion_recursos AS (
            SELECT c.tipo, SUM(m.valor_gwh) AS total_gwh
            FROM sector_energetico.metrics m
            JOIN sector_energetico.catalogos c ON m.recurso = c.codigo AND c.catalogo = 'ListadoRecursos'
            WHERE m.metrica = 'Gene' AND m.fecha BETWEEN %(fecha)s::date - INTERVAL '7 days' AND %(fecha)s::date
              AND c.tipo IS NOT NULL
            GROUP BY c.tipo
        ),
        total AS (SELECT SUM(total_gwh) AS suma_total FROM generacion_recursos)
        SELECT ROUND((total_gwh / NULLIF((SELECT suma_total FROM total), 0) * 100)::numeric, 1) AS pct
        FROM generacion_recursos WHERE tipo = 'TERMICA'
        """,
        {"fecha": fecha},
    )

    pct_hoy = hoy["pct_termica_hoy"].iloc[0] if not hoy.empty else None
    pct_7d = promedio_7d["pct"].iloc[0] if not promedio_7d.empty else None
    if pct_hoy is None:
        return None
    return {
        "fecha": str(fecha),
        "participacion_pct_hoy": float(pct_hoy),
        "participacion_pct_promedio_8d": float(pct_7d) if pct_7d is not None else None,
    }


def _fetch_prediccion_embalses() -> Optional[Dict[str, Any]]:
    """
    Pico proyectado de embalses (fecha, valor, MAPE, confianza) y si alcanza la
    meta del 80% — mismo endpoint que ya consume el frontend (`/api/predicciones/`
    → `GET /v1/predictions/dashboard`) para la tarjeta "Proyección Embalses" de
    `diagnosticoReservas()`. Sin este fetch, el texto de IA queda estructuralmente
    más pobre que la plantilla determinística en esa tarjeta (bug real de la
    Ronda 2: la tarjeta "Proyección Embalses" quedaba sin mencionar).
    """
    import requests
    from core.config import settings

    url = f"{settings.API_BASE_URL.rstrip('/')}/v1/predictions/dashboard"
    try:
        resp = requests.get(url, headers={"X-API-Key": settings.API_KEY}, timeout=20)
        resp.raise_for_status()
        embalses = resp.json().get("embalses")
    except Exception as e:
        logger.warning(f"[DIAGNOSTICOS_IA] Predicciones de embalses no disponibles: {e}")
        return None
    if not embalses or not embalses.get("pico"):
        return None

    actual_pct = embalses.get("actual", {}).get("valor")
    pico = embalses["pico"]
    meta80 = next(
        (p["fecha"] for p in embalses.get("prediccion", []) if p.get("valor", 0) >= 80),
        None,
    )
    return {
        "picoPct": pico["valor"],
        "picoFecha": pico["fecha"],
        "meta80Fecha": meta80,
        "mape": embalses.get("mape"),
        "confianza": embalses.get("confianza"),
        "sinRecuperacionProyectada": actual_pct is not None and pico["valor"] <= actual_pct,
    }


def _fetch_indices_regulatorios() -> List[Dict[str, Any]]:
    """Índices NE/HSIN/PBP/Condición del Sistema con sus relaciones y cita normativa (Fase 12)."""
    from core.container import get_ontologia_service

    service = get_ontologia_service()
    metricas = service.listar_metricas(dominio="sector_energetico", estado="catalogado")
    indices = [m for m in metricas if m.get("es_indice_regulatorio")]
    for indice in indices:
        indice["relaciones"] = service.metrica_repo.relaciones_de_metrica(indice["metrica_id"])
    return indices


def _fetch_contexto_rag_por_slide() -> Dict[str, List[Dict[str, Any]]]:
    """
    Fragmentos narrativos reales (informes diarios XM + guía de alertas — Fase 8),
    con una búsqueda por cada query dirigida de RAG_QUERIES_POR_SLIDE, para que el
    contexto que llega a cada slide sea relevante a lo que ese texto trata.
    """
    from core.container import get_ontologia_service

    service = get_ontologia_service()
    resultado: Dict[str, List[Dict[str, Any]]] = {}
    for slide_id in SLIDE_IDS:
        vistos = set()
        fragmentos: List[Dict[str, Any]] = []

        for consulta in RAG_QUERIES_POR_SLIDE.get(slide_id, []):
            try:
                encontrados = service.buscar_texto(consulta, top_k=3)
            except Exception as e:
                logger.warning(f"[DIAGNOSTICOS_IA] Búsqueda RAG falló para '{consulta}': {e}")
                continue
            for r in encontrados:
                clave = r.get("contenido", "")[:80]
                if clave in vistos:
                    continue
                vistos.add(clave)
                fragmentos.append(r)

        # Búsquedas con tema explícito garantizado (Fase 11 Ronda 5).
        for consulta, tema in RAG_QUERIES_POR_TEMA_POR_SLIDE.get(slide_id, []):
            try:
                encontrados = service.buscar_texto(consulta, top_k=2, tema=tema)
            except Exception as e:
                logger.warning(f"[DIAGNOSTICOS_IA] Búsqueda RAG (tema='{tema}') falló para '{consulta}': {e}")
                continue
            for r in encontrados:
                clave = r.get("contenido", "")[:80]
                if clave in vistos:
                    continue
                vistos.add(clave)
                fragmentos.append(r)

        resultado[slide_id] = fragmentos
    return resultado


def _seccion_rag(titulo: str, chunks: List[Dict[str, Any]]) -> List[str]:
    if not chunks:
        return []
    lineas = [f"--- Contexto narrativo real para '{titulo}' (informes XM / guía de alertas) ---"]
    for c in chunks[:4]:
        fuente = c.get("nombre_archivo") or c.get("fuente", "informe")
        lineas.append(f"- ({fuente}): {c.get('contenido', '')[:700]}")
    return lineas


def _construir_prompt(
    snapshot: Dict[str, Any],
    termica: Optional[Dict[str, Any]],
    prediccion_embalses: Optional[Dict[str, Any]],
    indices: List[Dict[str, Any]],
    rag_por_slide: Dict[str, List[Dict[str, Any]]],
) -> str:
    partes = [
        "Eres el redactor del Portal de Dirección del Ministerio de Minas y Energía. "
        "Escribe el diagnóstico de 3 slides de la página principal para un público "
        "GENERAL, no especializado — cualquier persona sin conocimiento técnico del "
        "sector eléctrico debe entender qué significa cada valor y cada estado del "
        "sistema al leerlo. Cada slide tiene varias tarjetas de KPI visibles junto "
        "al texto — tu texto debe dar una lectura de CADA una de esas tarjetas, sin "
        "omitir ninguna (el checklist de qué tarjetas cubrir está en FORMATO DE RESPUESTA).",
        "",
        "=== ESTILO — PRIORIDAD #1: QUE SE ENTIENDA, NO QUE SUENE TÉCNICO ===",
        "Explica qué SIGNIFICA cada término técnico la primera vez que aparece, en "
        "palabras simples — nunca asumas que el lector sabe qué es 'senda de "
        "referencia', 'Índice HSIN/NE/PBP', 'precio de escasez', etc. Por ejemplo, "
        "en vez de 'por debajo de la senda de referencia CREG del 82%', escribe algo "
        "como 'por debajo del nivel que se espera para esta época del año (82%)'. "
        "En vez de nombrar un índice por su sigla sin más, di lo que mide en la "
        "misma frase (ej. 'los aportes de los ríos están al 75.8% de lo normal').",
        "NO uses 'Índice NE', 'Índice HSIN', 'Índice PBP' como si fueran nombres "
        "conocidos — o los explicas en la misma frase o simplemente no los nombres "
        "y describes directamente la situación con sus propias palabras.",
        "NUNCA cites resoluciones CREG en este texto (ej. 'Resolución CREG 209 de "
        "2020', 'art. 2.8.2.1.3') — ese detalle normativo ya está disponible en los "
        "tooltips de cada tarjeta KPI. Aquí solo va la explicación en palabras "
        "simples, sin ninguna cita entre paréntesis o corchetes.",
        "Frases CORTAS y directas — una idea por frase, sin encadenar varias "
        "cláusulas con comas/paréntesis. Máximo 4-5 oraciones cortas por texto (no "
        "párrafos densos): hay más de una tarjeta que cubrir, así que cada tarjeta "
        "se resume en 1 frase breve, no se profundiza en ninguna.",
        "Empieza SIEMPRE con una valoración en lenguaje simple del estado general "
        "('condiciones normales' / 'en vigilancia' / 'presenta estrés'), igual que "
        "un semáforo, antes de dar cifras.",
        "",
        "REGLA DE RECONCILIACIÓN (en una frase corta, no un párrafo): si dos cifras "
        "sobre el mismo tema parecen contradictorias porque cubren ventanas de "
        "tiempo distintas (ej. HOY vs. un promedio de varios días), acláralo "
        "brevemente citando ambas cifras — nunca las dejes sin reconciliar.",
        "",
        "=== EJEMPLO DE TONO A IMITAR (no copies el contenido, solo el estilo — nota "
        "que explica qué es cada cosa en vez de solo nombrarla o citar la norma) ===",
        '"Las reservas de agua y los ríos que las alimentan están en vigilancia. '
        'Los ríos están trayendo menos agua de lo normal (75.8% de lo esperado), '
        'aunque las represas todavía están en un nivel estable (79.5% de su '
        'capacidad). El modelo no espera que esto mejore antes de diciembre. '
        'El Fenómeno de El Niño está activo, lo que reduce las lluvias."',
        "",
        "=== DATOS ESTRUCTURADOS (sector_snapshot) ===",
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
    ]
    if termica:
        partes += [
            "",
            "=== GENERACIÓN TÉRMICA (hoy vs. promedio de los últimos días) ===",
            json.dumps(termica, ensure_ascii=False, indent=2),
        ]
    if prediccion_embalses:
        partes += [
            "",
            "=== PROYECCIÓN DE EMBALSES (modelo predictivo, tarjeta 'Proyección Embalses') ===",
            json.dumps(prediccion_embalses, ensure_ascii=False, indent=2),
            "Si sinRecuperacionProyectada es true, el mejor escenario esperado sigue "
            "en el nivel actual o por debajo — di 'no se proyecta recuperación', "
            "NUNCA 'se proyecta un pico' como si fuera buena noticia.",
        ]
    if indices:
        partes += [
            "",
            "=== ÍNDICES REGULATORIOS Y SUS RELACIONES (contexto interno para que "
            "entiendas CÓMO se relacionan las métricas — NO repitas la referencia "
            "normativa entre corchetes en el texto final, eso ya no aplica) ===",
        ]
        for ix in indices:
            partes.append(
                f"- {ix['codigo_tecnico']} ({ix['nombre_display']}): {ix['descripcion']} "
                f"[{ix.get('referencia_normativa', '')}]"
            )
            for rel in ix.get("relaciones", []):
                partes.append(f"    · {rel['descripcion']} [{rel.get('referencia_normativa', '')}]")

    partes += _seccion_rag("reservas", rag_por_slide.get("reservas", []))
    partes += _seccion_rag("precio_generacion", rag_por_slide.get("precio_generacion", []))
    partes += _seccion_rag("termica", rag_por_slide.get("termica", []))

    partes += [
        "",
        "=== FORMATO DE RESPUESTA ===",
        "Responde ÚNICAMENTE un objeto JSON válido, sin markdown ni texto adicional, "
        "con exactamente estas 3 claves. Checklist de tarjetas KPI a cubrir por slide "
        "(ninguna se omite):",
        '{"reservas": "...", "precio_generacion": "...", "termica": "..."}',
        "- reservas (3 tarjetas, en palabras simples): (1) Reservas Hídricas — pctEmbalses "
        "explicado como 'las represas están al X% de su capacidad'; si el nivel es SUPERIOR pero "
        "pctEmbalses < sendaReferenciaPct, dilo como 'está bien, aunque un poco por debajo de lo "
        "que se espera para esta época del año (sendaReferenciaPct%)' — nunca digas solo 'por "
        "encima de lo esperado' cuando en realidad está por debajo. (2) Aportes Hídricos — "
        "hsinPct explicado como 'los ríos están trayendo X% del agua que traen normalmente', "
        "reconciliado con Reservas en una frase si aplica. (3) Proyección Embalses — el pico "
        "proyectado/fecha o 'no se proyecta recuperación' en palabras simples ('el modelo no "
        "espera que mejore antes de...'). Si el contexto narrativo aporta un dato nuevo relevante "
        "(vertimientos, balance hídrico, objetivo XM), añádelo explicando qué significa. OBLIGATORIO "
        "si el contexto narrativo trae un pronóstico de El Niño (probabilidad/intensidad de NOAA o "
        "IDEAM): dedica una de tus 4-5 oraciones a resumirlo en palabras simples con la probabilidad "
        "citada (ej. 'la NOAA estima más de 90% de probabilidad de que El Niño se intensifique hacia "
        "fin de año, lo que puede seguir reduciendo las lluvias') — es información sobre el riesgo "
        "futuro que el ONI por sí solo no transmite, y el usuario pidió explícitamente que se use.",
        "- precio_generacion (2 tarjetas, en palabras simples): (1) Precio de Bolsa — explica que "
        "es el precio al que se compra/vende la energía, y si está cerca de volverse caro (di qué "
        "significa cruzar el precio de escasez: 'la energía se pone más cara y hay riesgo de "
        "desabastecimiento', no solo nombrar 'PEI/PE/PES'). (2) Energía Generada — composición "
        "hidráulica/térmica de la ventana de 7 días, explicando qué implica (más térmica = más "
        "caro y menos limpio). Si el contexto narrativo aporta la composición de la matriz "
        "energética u otro dato relevante, añádelo brevemente. OBLIGATORIO si el contexto narrativo "
        "menciona plantas específicas fuera de servicio (mantenimiento o falla): dedica una frase a "
        "resumirlo en palabras simples (ej. 'varias plantas térmicas están fuera de servicio por "
        "mantenimiento, lo que reduce la capacidad disponible') — el usuario pidió explícitamente "
        "que se use este dato cuando el informe de despacho lo reporte.",
        "- termica (3 tarjetas, en palabras simples): (1) Energía Térmica — participación de HOY "
        "reconciliada contra el promedio de 7-8 días citado en GENERACIÓN TÉRMICA, explicando que "
        "más térmica significa que el sistema depende más de plantas a gas/carbón en vez de agua. "
        "(2) Precio Escasez Superior (PES) y (3) PPP Diario — si el PPP superó el PES, explica qué "
        "significa ('se activan mecanismos de respaldo del mercado'), no solo dar los números. Si "
        "el contexto narrativo aporta el combustible predominante o menciona plantas térmicas "
        "específicas fuera de servicio, añádelo brevemente (solo si el informe lo reporta).",
    ]
    return "\n".join(partes)


def _llamar_ia(prompt: str) -> tuple:
    """Genera los 3 textos de diagnóstico — failover real Gemini→Groq (ver
    infrastructure/ml/llm_failover.py, agregado 2026-08-22 tras un bloqueo
    de red real hacia Gemini que dejó esta tarea fallando en cada corrida
    diaria — reintentaba en 600s vía Celery, pero siempre contra el mismo
    proveedor caído, nunca con un respaldo real). Retorna
    (textos_por_slide, "proveedor/modelo" real usado)."""
    from infrastructure.ml.llm_failover import completar_chat

    contenido, proveedor, modelo = completar_chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1200,
        etiqueta_log="DIAGNOSTICOS_IA",
    )
    contenido = re.sub(r"^```(json)?|```$", "", (contenido or "").strip(), flags=re.MULTILINE).strip()
    textos = json.loads(contenido)
    faltantes = [s for s in SLIDE_IDS if not textos.get(s)]
    if faltantes:
        raise ValueError(f"Respuesta de IA sin las claves esperadas: {faltantes}")
    return {s: str(textos[s]).strip() for s in SLIDE_IDS}, f"{proveedor}/{modelo}"


def _guardar_diagnosticos(fecha: date, textos: Dict[str, str], modelo: str) -> None:
    from infrastructure.database.connection import get_connection

    with get_connection() as conn:
        cur = conn.cursor()
        for slide_id, texto in textos.items():
            cur.execute(
                """
                INSERT INTO sector_energetico.diagnosticos_ia (fecha, slide_id, texto, generado_en, modelo)
                VALUES (%s, %s, %s, NOW(), %s)
                ON CONFLICT (fecha, slide_id) DO UPDATE SET
                    texto = EXCLUDED.texto,
                    generado_en = EXCLUDED.generado_en,
                    modelo = EXCLUDED.modelo
                """,
                (fecha, slide_id, texto, modelo),
            )
        conn.commit()


@celery_app.task(
    name="tasks.homeslider_diagnosticos_tasks.generar_diagnosticos_homeslider",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def generar_diagnosticos_homeslider(self):
    """
    Tarea diaria: genera y cachea los 3 diagnósticos de HomeSlider. Si algo falla
    (Gemini, RAG, snapshot incompleto), no escribe nada — el frontend cae al texto
    determinístico existente como respaldo, nunca queda un diagnóstico roto.
    """
    logger.info("[DIAGNOSTICOS_IA] ▶ Iniciando generación diaria de diagnósticos HomeSlider…")
    try:
        snapshot = _fetch_snapshot()
        termica = _fetch_termica()
        prediccion_embalses = _fetch_prediccion_embalses()
        indices = _fetch_indices_regulatorios()
        rag_por_slide = _fetch_contexto_rag_por_slide()

        prompt = _construir_prompt(snapshot, termica, prediccion_embalses, indices, rag_por_slide)
        textos, modelo_usado = _llamar_ia(prompt)

        _guardar_diagnosticos(date.today(), textos, modelo_usado)

        logger.info(f"[DIAGNOSTICOS_IA] ✅ {len(textos)} diagnósticos generados y cacheados para {date.today()}")
        return {"status": "ok", "fecha": str(date.today()), "slides": list(textos.keys())}
    except Exception as exc:
        logger.error(f"[DIAGNOSTICOS_IA] ❌ Error generando diagnósticos: {exc}", exc_info=True)
        raise self.retry(exc=exc)

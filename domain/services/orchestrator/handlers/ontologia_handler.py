"""
Mixin: Ontología unificada — geografía DANE + empresas/prestadores (Fase 1/2 del
roadmap "Palantir-IA"). Cruza comunidades, contratos OR, FENOGE, Colombia Solar,
subsidios y supervisión por departamento vía ontologia.mv_resumen_departamento.

Capa 100% analítica/de solo lectura — ninguna acción sobre contratos.
"""
import asyncio
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_REGRESAR_MENU = {"id": "menu", "titulo": "🔙 Menú principal"}


def _normalizar(texto: str) -> str:
    """Quita tildes y pasa a mayúsculas — para comparar nombres de departamento en texto libre."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.upper().strip()


def _clave_chunk_rag(r: Dict[str, Any]) -> str:
    """Clave estable para un resultado de buscar_texto_rag — Fase 38, usada
    para detectar chunks repetidos entre llamadas sucesivas del mismo turno.
    Fuente 'informe': nombre_archivo+chunk_index identifica el fragmento
    exacto. Fuente 'contrato': no tiene esos campos (son NULL), se usa la
    tupla tabla_origen+fila_id+campo. Si ninguno está disponible, hash corto
    del inicio del contenido — nunca falla, solo degrada a un poco menos de
    precisión en la deduplicación."""
    if r.get("nombre_archivo") is not None and r.get("chunk_index") is not None:
        return f"informe:{r['nombre_archivo']}#{r['chunk_index']}"
    if r.get("fila_id") is not None and r.get("campo"):
        return f"contrato:{r.get('tabla_origen')}:{r['fila_id']}:{r['campo']}"
    import hashlib
    return "hash:" + hashlib.md5((r.get("contenido") or "")[:150].encode("utf-8")).hexdigest()[:12]


def resolver_departamento_en_texto(
    texto: str, departamentos: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Busca el nombre de un departamento DANE mencionado dentro de un texto libre.
    Compara los nombres más largos primero para que "Valle del Cauca" no pierda
    frente a una coincidencia parcial de "Valle".
    """
    texto_norm = _normalizar(texto)
    for depto in sorted(departamentos, key=lambda d: -len(d["nombre_departamento"])):
        if _normalizar(depto["nombre_departamento"]) in texto_norm:
            return depto
    return None


class OntologiaHandlerMixin:
    """
    Mixin que agrupa:
    - _handle_resumen_departamento (handler, intent explícito)
    - _handle_buscar_texto_rag, _handle_buscar_empresa, _handle_vecindario_empresa,
      _handle_riesgo_atraso_or, _handle_listar_proyectos (Fase 9 — tools del
      Asistente IA; envuelven capacidades de Fase 1/5/7/8 que antes solo se
      exponían como endpoints REST, nunca al orquestador/chatbot)
    """

    @handle_service_error
    async def _handle_resumen_departamento(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: vista 360 de un departamento — cruza comunidades energéticas,
        contratos OR, FENOGE, Colombia Solar, subsidios y supervisión.

        parameters:
            departamento: nombre en texto libre (ej. "Chocó"), o
            codigo_dane_departamento: código DANE de 2 dígitos (ej. "27")
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        from core.container import get_ontologia_service
        service = get_ontologia_service()

        codigo = parameters.get("codigo_dane_departamento")
        nombre = parameters.get("departamento")

        departamentos = await asyncio.to_thread(service.listar_departamentos)

        if not codigo and nombre:
            match = resolver_departamento_en_texto(nombre, departamentos)
            if match:
                codigo = match["codigo_dane_departamento"]

        if not codigo:
            errors.append(ErrorDetail(
                code="MISSING_DEPARTAMENTO",
                message="Debes indicar 'departamento' (nombre) o 'codigo_dane_departamento'",
            ))
            data["departamentos_disponibles"] = [d["nombre_departamento"] for d in departamentos]
            return data, errors

        resumen = await asyncio.to_thread(service.resumen_departamento, codigo)
        if resumen is None:
            errors.append(ErrorDetail(
                code="DEPARTAMENTO_NO_ENCONTRADO",
                message="No se encontró información DANE para el departamento indicado",
            ))
            return data, errors

        data["resumen_departamento"] = resumen
        data["nota"] = (
            "Cruce de comunidades energéticas, contratos OR, FENOGE, Colombia Solar, "
            "subsidios y supervisión para este departamento. Cobertura geográfica en "
            "curación progresiva — ver GET /v1/ontologia/alias/pendientes."
        )
        data["opcion_regresar"] = _REGRESAR_MENU
        return data, errors

    @handle_service_error
    async def _handle_resumen_municipio(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: vista 360 de un municipio (Fase 13) — mismo cruce que
        resumen_departamento, pero al grano de municipio DANE.

        parameters:
            municipio: nombre en texto libre (ej. "Quibdó"), o
            codigo_dane_municipio: código DANE de 5 dígitos (ej. "27001")
            departamento: nombre opcional para desambiguar (varios municipios
                          comparten nombre en departamentos distintos)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        from core.container import get_ontologia_service
        service = get_ontologia_service()

        codigo = parameters.get("codigo_dane_municipio")
        nombre = parameters.get("municipio")
        nombre_depto = parameters.get("departamento")

        if not codigo and nombre:
            codigo_depto = None
            if nombre_depto:
                departamentos = await asyncio.to_thread(service.listar_departamentos)
                match_depto = resolver_departamento_en_texto(nombre_depto, departamentos)
                if match_depto:
                    codigo_depto = match_depto["codigo_dane_departamento"]

            municipios = await asyncio.to_thread(service.listar_municipios, codigo_depto)
            nombre_norm = _normalizar(nombre)
            match = next(
                (m for m in municipios if _normalizar(m["nombre_municipio"]) == nombre_norm), None
            )
            if match:
                codigo = match["codigo_dane_municipio"]

        if not codigo:
            errors.append(ErrorDetail(
                code="MISSING_MUNICIPIO",
                message="Debes indicar 'municipio' (nombre, opcionalmente con 'departamento' "
                        "para desambiguar) o 'codigo_dane_municipio'",
            ))
            return data, errors

        resumen = await asyncio.to_thread(service.resumen_municipio, codigo)
        if resumen is None:
            errors.append(ErrorDetail(
                code="MUNICIPIO_NO_ENCONTRADO",
                message="No se encontró información DANE para el municipio indicado",
            ))
            return data, errors

        data["resumen_municipio"] = resumen
        data["nota"] = (
            "Cruce de comunidades energéticas, contratos OR, FENOGE, Colombia Solar, "
            "subsidios y supervisión para este municipio."
        )
        return data, errors

    @handle_service_error
    async def _handle_buscar_texto_rag(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: búsqueda semántica (RAG) sobre observaciones/objeto de contratos
        de supervisión E informes PDF/PPTX/DOCX de SharePoint (PMO, actas
        ELECTROCAQUETA, boletín XM, informes diarios XM).

        parameters:
            consulta: texto de búsqueda en lenguaje natural (requerido)
            top_k: máximo de resultados (default 5)
            tema: filtro opcional determinístico por tipo de informe (Fase 11 Ronda 5) —
                  'despacho' | 'hidrologia' | 'operativas' | 'panorama_climatico' | 'metodologia_alertas'
            campo_contrato: filtro opcional equivalente para el corpus de contratos (Fase 13) —
                  ej. 'objeto_del_contrato' | 'observacion_alerta_de_incumplimiento'
            _presupuesto_chars: (Fase 38, interno — inyectado solo por
                  asistente_ia_service.py, nunca por el LLM) presupuesto total de
                  caracteres para repartir entre los resultados NO duplicados de
                  esta llamada; reemplaza el presupuesto fijo de 5.500 cuando viene
                  presente. Otros llamadores (orquestador directo, golden dataset)
                  no lo pasan y conservan el comportamiento de siempre.
            _chunks_vistos: (Fase 38, interno) lista de claves de chunks ya
                  entregados en llamadas anteriores de ESTE turno — los resultados
                  que coincidan se reemplazan por una referencia corta en vez de
                  repetir el texto completo.
            _limite_alcanzado: (Fase 38, interno) si viene en `True`, esta llamada
                  ni siquiera ejecuta la búsqueda — el turno ya está tan cerca del
                  tope de tokens del proveedor activo (Groq) que una búsqueda más,
                  aunque venga recortada al piso, arriesga tumbar todo el turno sin
                  respuesta. Se le devuelve al LLM una nota pidiéndole responder con
                  lo que ya tiene, en vez de intentar la búsqueda y fallar duro.
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        consulta = parameters.get("consulta", "").strip()
        if not consulta:
            errors.append(ErrorDetail(
                code="MISSING_CONSULTA",
                message="Debes indicar 'consulta'",
            ))
            return data, errors

        if parameters.get("_limite_alcanzado"):
            data["resultados"] = []
            data["nota"] = (
                "Límite de búsquedas alcanzado para este turno (recursos de IA "
                "limitados en este momento) — responde con la información que ya "
                "obtuviste en búsquedas anteriores de este turno, o indica "
                "honestamente que no encontraste la cifra exacta en vez de "
                "inventarla o intentar otra búsqueda."
            )
            return data, errors

        from core.container import get_ontologia_service
        service = get_ontologia_service()
        # Fase 38: tope duro — el schema del tool nunca declaró un máximo, y
        # un top_k grande pedido por el LLM podía inflar el JSON muy por
        # encima de cualquier presupuesto (reproducido en vivo: un top_k
        # elevado hizo que incluso el piso mínimo por resultado, multiplicado
        # por muchos resultados, sumara 12.975 caracteres).
        top_k = min(int(parameters.get("top_k", 5)), 10)
        tema = parameters.get("tema")
        campo_contrato = parameters.get("campo_contrato")

        resultados = await asyncio.to_thread(
            service.buscar_texto, consulta, top_k, 0.3, tema, campo_contrato
        )

        # Fase 38: deduplicar contra chunks ya entregados en este mismo turno
        # (ej. una 2da/3ra llamada a esta tool con una consulta relacionada) —
        # evita repetir texto completo que el modelo ya tiene, sin perder la
        # cobertura (el resultado sigue apareciendo, solo con una referencia
        # corta en vez del contenido íntegro).
        chunks_vistos_previos = set(parameters.get("_chunks_vistos") or [])
        claves_nuevas: List[str] = []
        resultados_no_dup: List[Dict[str, Any]] = []
        for r in resultados:
            clave = _clave_chunk_rag(r)
            if clave in chunks_vistos_previos:
                r["contenido"] = (
                    f"(ya se mostró este fragmento antes en este mismo turno — "
                    f"{r.get('nombre_archivo') or 'mismo documento'})"
                )
            else:
                resultados_no_dup.append(r)
                claves_nuevas.append(clave)

        # Fase 26 (presupuesto fijo) → Fase 38 (presupuesto dinámico): recortar
        # cada 'contenido' individualmente en vez de depender solo del corte
        # ciego de 8000 chars sobre el JSON completo en _resolver_tool_calls()
        # — ese corte partía a la mitad el ÚLTIMO resultado y le hacía perder
        # su metadata (fuente/nombre_archivo), visto repetido con consultas
        # reales (Fase 24 Colombia Solar, Fase 25 verificación). El presupuesto
        # total ahora puede venir acotado desde el llamador (ver
        # _presupuesto_chars arriba) cuando el turno ya acumuló muchos tokens
        # y el proveedor activo es Groq — sin este parámetro, se comporta
        # exactamente igual que antes (techo fijo de 5.500).
        presupuesto_total = int(parameters.get("_presupuesto_chars") or 5500)
        n = len(resultados_no_dup)
        limite_por_chunk = presupuesto_total // n if n else 0
        PISO_CONTENIDO_UTIL = 300  # por debajo de esto, un fragmento ya no aporta nada legible
        if limite_por_chunk >= PISO_CONTENIDO_UTIL:
            for r in resultados_no_dup:
                contenido = r.get("contenido") or ""
                if len(contenido) > limite_por_chunk:
                    r["contenido"] = contenido[:limite_por_chunk] + "…"
        else:
            # Fase 38: el presupuesto no alcanza para dar contenido útil a
            # TODOS los resultados (bug real reproducido: un `max(400, ...)`
            # como piso por resultado, multiplicado por muchos resultados,
            # ignoraba el presupuesto total y llegó a sumar 12.975 chars). En
            # vez de forzar un piso por resultado que rompe el techo total,
            # se prioriza contenido completo para los primeros (ya vienen
            # ordenados por relevancia del re-ranking) y se deja el resto
            # como referencia corta — nunca se pierde que el documento existe,
            # solo se recorta su texto cuando ya no hay presupuesto.
            n_con_contenido = max(1, presupuesto_total // PISO_CONTENIDO_UTIL)
            for idx, r in enumerate(resultados_no_dup):
                if idx < n_con_contenido:
                    contenido = r.get("contenido") or ""
                    if len(contenido) > PISO_CONTENIDO_UTIL:
                        r["contenido"] = contenido[:PISO_CONTENIDO_UTIL] + "…"
                else:
                    r["contenido"] = (
                        f"(resultado adicional omitido por presupuesto de tokens — "
                        f"{r.get('nombre_archivo') or 'ver fuente'})"
                    )

        data["resultados"] = resultados
        data["_claves_vistas"] = claves_nuevas  # leído y removido por asistente_ia_service.py antes de mostrarlo al LLM
        data["nota"] = (
            "Cada resultado indica 'fuente' ('contrato' u 'informe') y su 'similitud' "
            "(0-1) con la consulta. Cita el nombre_archivo cuando la fuente sea 'informe'."
        )
        if not resultados:
            data["nota"] += (
                " Sin resultados: si vas a reintentar, escribe 'consulta' como una "
                "pregunta completa en lenguaje natural, nunca una lista de palabras "
                "sueltas (ej. 'plantas indisponibles mantenimiento fuera servicio')."
            )
        return data, errors

    @handle_service_error
    async def _handle_buscar_empresa(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: busca una empresa/prestador/ejecutor por NIT o nombre/sigla.

        parameters:
            nombre: nombre o sigla en texto libre (ej. "GENSA"), o
            nit: NIT exacto
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        nombre = parameters.get("nombre")
        nit = parameters.get("nit")
        if not nombre and not nit:
            errors.append(ErrorDetail(
                code="MISSING_EMPRESA",
                message="Debes indicar 'nombre' o 'nit'",
            ))
            return data, errors

        from core.container import get_ontologia_service
        service = get_ontologia_service()

        empresas = await asyncio.to_thread(service.buscar_empresas, nit, nombre)
        data["empresas"] = empresas
        data["nota"] = (
            "Usa el 'empresa_id' de un resultado con este llamado para explorar su "
            "vecindario con la herramienta vecindario_empresa."
        )
        return data, errors

    @handle_service_error
    async def _handle_vecindario_empresa(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: grafo de relaciones de una empresa (solo lectura) — contratos
        verificados por NIT, proyectos por nombre difuso, geografía donde opera,
        y otras empresas con contratos en las mismas zonas.

        parameters:
            empresa_id: id numérico obtenido con buscar_empresa (requerido)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        empresa_id = parameters.get("empresa_id")
        if empresa_id is None:
            errors.append(ErrorDetail(
                code="MISSING_EMPRESA_ID",
                message="Debes indicar 'empresa_id' (usa buscar_empresa primero para obtenerlo)",
            ))
            return data, errors

        from core.container import get_graph_service
        service = get_graph_service()

        vecindario = await asyncio.to_thread(service.vecindario_empresa, int(empresa_id))
        if vecindario is None:
            errors.append(ErrorDetail(
                code="EMPRESA_NO_ENCONTRADA",
                message="No se encontró ninguna empresa con ese empresa_id",
            ))
            return data, errors

        data["vecindario"] = vecindario
        return data, errors

    @handle_service_error
    async def _handle_riesgo_atraso_or(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: ranking de contratos OR por riesgo de atraso (cronograma de obra),
        mayor riesgo primero. Puramente informativo — no cambia ningún estado.

        parameters:
            limit: máximo de contratos a devolver (default 10)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        from core.container import get_risk_service
        service = get_risk_service()
        limit = int(parameters.get("limit", 10))

        ranking = await asyncio.to_thread(service.riesgo_atraso_contratos_or)
        data["ranking"] = ranking[:limit]
        data["total_contratos_evaluados"] = len(ranking)
        data["nota"] = (
            "Score informativo de riesgo de atraso basado en el cronograma de obra. "
            "No modifica el estado de ningún contrato."
        )
        return data, errors

    @handle_service_error
    async def _handle_listar_proyectos(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: lista proyectos de la ontología (objeto de primera clase),
        opcionalmente filtrados por programa y/o departamento.

        parameters:
            programa: 'contratos_or' | 'colombia_solar' | 'fenoge' (opcional)
            departamento: nombre en texto libre (opcional, Fase 23 Bloque 2 —
                filtra por ontologia.proyecto_geografia, vínculo real)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        from core.container import get_ontologia_service
        service = get_ontologia_service()
        programa = parameters.get("programa")
        departamento = parameters.get("departamento")

        proyectos = await asyncio.to_thread(service.listar_proyectos, programa, departamento)
        data["proyectos"] = proyectos
        return data, errors

    @handle_service_error
    async def _handle_buscar_metrica(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: busca en el catálogo de métricas/variables del portal (Fase 12)
        por nombre o código técnico (ej. "embalse", "NE", "precio de bolsa").
        Cada resultado incluye sus relaciones de derivación con cita normativa,
        para responder "¿qué es X y de qué depende?" con datos estructurados
        reales en vez de que el modelo improvise.

        parameters:
            consulta: nombre o código técnico de la métrica (requerido)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        consulta = parameters.get("consulta", "").strip()
        if not consulta:
            errors.append(ErrorDetail(
                code="MISSING_CONSULTA",
                message="Debes indicar 'consulta' (nombre o código técnico de la métrica)",
            ))
            return data, errors

        from core.container import get_ontologia_service
        service = get_ontologia_service()

        metricas = await asyncio.to_thread(service.buscar_metrica, consulta)
        data["metricas"] = metricas
        data["nota"] = (
            "Cada métrica incluye 'referencia_normativa' (Resolución CREG citada) "
            "cuando aplica, y 'relaciones' con las métricas de las que depende o a "
            "las que alimenta. Cita la referencia normativa si está disponible."
        )
        return data, errors

    async def _handle_calidad_datos_ontologia(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: qué tan completa/confiable está la información cruzada de la
        ontología (Fase 6 — gobierno de datos). Envuelve
        OntologiaService.salud_datos(), sin parámetros — deuda de resolución
        de alias (geografía/empresas sin resolver) + linaje reciente del
        pipeline diario, incluyendo si hubo corridas con error.
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        from core.container import get_ontologia_service
        service = get_ontologia_service()

        try:
            salud = await asyncio.to_thread(service.salud_datos)
            data.update(salud)
        except Exception as e:
            logger.error(f"[CALIDAD_DATOS_ONTOLOGIA] Error: {e}")
            errors.append(ErrorDetail(code="SERVICE_ERROR", message="Error consultando salud de datos"))

        return data, errors

    async def _handle_detalle_recurso(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: detalle de una planta/recurso del sector eléctrico por nombre
        (ej. "Cartagena 1", "Chivor") — envuelve OntologiaService.listar_recursos()
        + obtener_recurso(), que además trae 'menciones_recientes' (Fase 14):
        cruce ya construido entre el catálogo de plantas y el RAG de informes
        diarios de despacho de XM, nunca antes expuesto al Asistente.

        parameters:
            nombre: nombre o parte del nombre de la planta (requerido)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        nombre = parameters.get("nombre", "").strip()
        if not nombre:
            errors.append(ErrorDetail(
                code="MISSING_NOMBRE",
                message="Debes indicar 'nombre' (nombre o parte del nombre de la planta/recurso)",
            ))
            return data, errors

        from core.container import get_ontologia_service
        service = get_ontologia_service()

        candidatos = await asyncio.to_thread(service.listar_recursos, None, nombre)
        if not candidatos:
            errors.append(ErrorDetail(
                code="NO_DATA",
                message=f"No se encontró ningún recurso/planta con nombre que coincida con '{nombre}'",
            ))
            return data, errors

        if len(candidatos) > 1:
            data["candidatos"] = candidatos
            data["nota"] = (
                "Hay varias plantas que coinciden con ese nombre — pídele al usuario "
                "que precise cuál, o si el contexto lo deja claro, usa la más relevante."
            )
            return data, errors

        recurso = await asyncio.to_thread(service.obtener_recurso, candidatos[0]["codigo_xm"])
        data["recurso"] = recurso
        data["nota"] = (
            "'menciones_recientes' son apariciones reales de esta planta en los "
            "informes diarios de despacho de XM indexados — úsalas para contexto "
            "operativo (ej. si aparece indisponible/en mantenimiento)."
        )
        return data, errors

    @handle_service_error
    async def _handle_detalle_contrato(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: detalle completo de UN contrato de supervisión por su id
        (Fase 28) — envuelve OntologiaService.obtener_contrato(). El 'id' es
        el mismo que ya aparece en los nodos de contrato de vecindario_empresa
        (grafo empresa→contratos), no un código de contrato en texto libre —
        evita ambigüedad de formato entre esquemas distintos.

        parameters:
            contrato_id: id numérico del contrato (requerido)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        contrato_id = parameters.get("contrato_id")
        if contrato_id is None:
            errors.append(ErrorDetail(
                code="MISSING_CONTRATO_ID",
                message="Debes indicar 'contrato_id' (ver los nodos de contrato de vecindario_empresa)",
            ))
            return data, errors

        from core.container import get_ontologia_service
        service = get_ontologia_service()

        contrato = await asyncio.to_thread(service.obtener_contrato, int(contrato_id))
        if contrato is None:
            errors.append(ErrorDetail(
                code="NO_DATA",
                message=f"No se encontró el contrato con id {contrato_id}",
            ))
            return data, errors

        data["contrato"] = contrato
        return data, errors

    @handle_service_error
    async def _handle_resumen_portal(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: catálogo curado de los 18 tableros/páginas reales del portal
        (Fase 30) — sin parámetros, sin SQL, describe la ESTRUCTURA del
        portal (qué tableros existen y qué muestran), no datos de negocio que
        cambien. Se creó porque una pregunta real de usuario ("resumen de
        cada tablero y cómo se relacionan") solo disparó `estado_actual`
        (3 indicadores del SIN) al no existir ninguna tool que diera una
        vista global — confirmado por grep exhaustivo de los ~100 intents
        del orquestador, cero resultados de algo tipo "resumen_portal".

        Contenido verificado contra títulos/subtítulos reales de cada página
        (`portal-direccion-mme/src/app/(dashboards)/**/page.tsx`) y contra
        Header.tsx para distinguir los 14 tableros en menú de los 4 solo
        accesibles por URL directa. Las relaciones descritas son las
        realmente existentes en la ontología (geografía DANE vía
        dim_geografia/mv_resumen_departamento, empresa/NIT vía dim_empresa/
        vecindario_empresa) — se aclara explícitamente qué dominios NO están
        conectados, para no inducir al LLM a inventar relaciones inexistentes.
        """
        data: Dict[str, Any] = {
            "tableros": [
                {"nombre": "Gestión del Sector", "ruta": "/energia", "dominio": "sector_energetico",
                 "que_muestra": "Estado en tiempo real del SIN: generación, precio de bolsa, embalses, demanda, índices climáticos (ONI/PDO/SOI/GMST). Fuente: XM."},
                {"nombre": "Predicciones del Sector", "ruta": "/energia/predicciones", "dominio": "sector_energetico",
                 "que_muestra": "Proyecciones de embalses, generación y precio de bolsa a 1 semana-1 año (modelos Prophet/ARIMA/Ensemble)."},
                {"nombre": "Informes y Documentos", "ruta": "/energia/informes", "dominio": "sector_energetico",
                 "que_muestra": "Descarga de boletín energético, informes diarios XM, informe de empalme MME y resumen ejecutivo diario."},
                {"nombre": "Presupuesto DEE", "ruta": "/presupuesto", "dominio": "presupuesto",
                 "que_muestra": "Ejecución presupuestal de la Dirección de Energía Eléctrica: apropiación, compromisos, obligaciones."},
                {"nombre": "Supervisión", "ruta": "/supervision", "dominio": "supervision",
                 "que_muestra": "Seguimiento de contratos de apoyos financieros a prestadores de energía: avance físico y documental, interventoría."},
                {"nombre": "Subsidios — Déficit", "ruta": "/subsidios", "dominio": "subsidios",
                 "que_muestra": "Déficit histórico del FSSRI, deuda de subsidios por empresa y por fondo."},
                {"nombre": "Pagos", "ruta": "/pagos", "dominio": "subsidios",
                 "que_muestra": "Detalle de pagos de subsidios por resolución y empresa."},
                {"nombre": "Validaciones", "ruta": "/validaciones", "dominio": "subsidios",
                 "que_muestra": "Relación de cuentas de subsidios: validaciones VF/VP/VI por departamento."},
                {"nombre": "Colombia Solar", "ruta": "/colombia-solar", "dominio": "colombia_solar",
                 "que_muestra": "Instalación de sistemas solares para estratos 1-3, avance por municipio."},
                {"nombre": "Comunidades Energéticas", "ruta": "/comunidades", "dominio": "comunidades",
                 "que_muestra": "Comunidades energéticas implementadas y en seguimiento, por departamento."},
                {"nombre": "Contratos OR", "ruta": "/contratos-or", "dominio": "contratos_or",
                 "que_muestra": "Contratos de Obras de Redes (electrificación rural): avance físico/documental, actas de seguimiento."},
                {"nombre": "FENOGE", "ruta": "/fenoge", "dominio": "fenoge",
                 "que_muestra": "Fondo de Energías No Convencionales: seguimiento financiero de proyectos (real vs. programado)."},
                {"nombre": "Hidrocarburos — Presupuesto", "ruta": "/hidrocarburos/presupuesto", "dominio": "hidrocarburos",
                 "que_muestra": "Ejecución presupuestal de la Dirección de Hidrocarburos."},
                {"nombre": "Hidrocarburos — Exploración", "ruta": "/hidrocarburos/exploracion", "dominio": "hidrocarburos",
                 "que_muestra": "Producción de petróleo y gas. Fuente: ANH."},
                {"nombre": "Catálogo de Métricas", "ruta": "/catalogo-metricas", "dominio": "ontologia", "en_menu": False,
                 "que_muestra": "Catálogo de las métricas del sector con sus relaciones de derivación y cita normativa (CREG)."},
                {"nombre": "Explorador de Red", "ruta": "/explorador-red", "dominio": "ontologia", "en_menu": False,
                 "que_muestra": "Grafo de relaciones empresa-contrato-proyecto-geografía-interventoría."},
                {"nombre": "Salud de Datos", "ruta": "/salud-datos", "dominio": "ontologia", "en_menu": False,
                 "que_muestra": "Backlog de curación de la ontología: alias de geografía/empresa sin resolver, linaje del pipeline diario."},
                {"nombre": "Vista Departamental", "ruta": "/vista-departamental", "dominio": "ontologia", "en_menu": False,
                 "que_muestra": "Resumen cruzado de comunidades, contratos OR, FENOGE, Colombia Solar, subsidios y supervisión, por departamento."},
            ],
            "relaciones": (
                "Dos ejes reales conectan los dominios entre sí: (1) geografía DANE — "
                "comunidades, contratos OR, FENOGE, Colombia Solar, subsidios y supervisión "
                "comparten departamento/municipio vía ontologia.dim_geografia, consultable en "
                "conjunto con resumen_departamento o el tablero Vista Departamental; (2) empresa/NIT "
                "— supervisión, contratos e interventorías se conectan vía ontologia.dim_empresa, "
                "explorable con vecindario_empresa o el tablero Explorador de Red. El sector "
                "eléctrico (SIN: generación, precio, embalses) es estructuralmente independiente "
                "de los programas sociales — no comparte geografía/empresa de forma directa. "
                "Hidrocarburos (presupuesto y exploración) es un dominio aparte, sin cruce "
                "estructural con el resto del portal hoy."
            ),
        }
        return data, []

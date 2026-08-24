"""
Agente IA para análisis en tiempo real del Dashboard MME
Usa OpenRouter/Groq con modelos de última generación
Conecta a PostgreSQL a través de DatabaseManager
"""
import os
from openai import OpenAI
import json
from typing import Dict, List, Optional
from core.config import settings
from infrastructure.database.manager import db_manager
from infrastructure.ml.llm_failover import completar_chat as _completar_chat

class AgentIA:
    """Agente de IA para análisis energético en tiempo real"""

    def __init__(self):
        """Inicializa el agente usando configuración centralizada.

        2026-08-22: ya NO fija un único cliente/proveedor al construirse —
        cada llamada real pasa por _completar_chat() (infrastructure/ml/
        llm_failover.py), que reintenta con Groq si Gemini falla en tiempo
        de ejecución (antes era un "fallback" falso: se elegía un
        proveedor una sola vez y nunca se reintentaba con otro).
        self.provider/self.modelo quedan como el ÚLTIMO proveedor/modelo
        que sirvió una respuesta real — solo informativo (logs, mensajes
        de error), no determinan qué proveedor se usa en la próxima llamada."""
        self.provider = None
        self.modelo = None
        if settings.OPENROUTER_API_KEY:
            # OpenRouter no forma parte del failover Gemini→Groq (backup
            # de último recurso, sin cambios de esta ronda) — solo se
            # usa si NINGUNA de las 2 keys principales está configurada.
            self._openrouter_client = OpenAI(
                base_url=settings.OPENROUTER_BASE_URL,
                api_key=settings.OPENROUTER_API_KEY,
            )
            self._openrouter_modelo = settings.OPENROUTER_BACKUP_MODEL
        else:
            self._openrouter_client = None
            self._openrouter_modelo = None
        if not settings.GEMINI_API_KEY and not settings.GROQ_API_KEY and not settings.OPENROUTER_API_KEY:
            # No levantar error aquí para permitir funcionamiento sin IA si fallan keys
            print("⚠️ Advertencia: No se encontraron keys de IA (GEMINI/GROQ/OPENROUTER)")

    @property
    def disponible(self) -> bool:
        """True si hay al menos un proveedor de IA configurado (Gemini,
        Groq u OpenRouter) — reemplaza el chequeo antiguo `if agent.client`,
        que dejó de existir porque ya no hay un único cliente comprometido
        al construirse (ver __init__)."""
        return bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)

    def completar(self, messages: list, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """Punto único de acceso al LLM — failover real Gemini→Groq vía
        infrastructure/ml/llm_failover.py, con OpenRouter como último
        recurso si ambas keys principales fallan o no están configuradas.
        Público: lo usan tanto los 5 métodos de análisis de esta clase
        como informe_handler.py/libre_noticias_handler.py, que antes
        accedían directamente a `agent.client`/`agent.modelo` (un cliente
        ya comprometido a un solo proveedor, sin reintento real)."""
        try:
            texto, proveedor, modelo = _completar_chat(messages, temperature=temperature, max_tokens=max_tokens)
            self.provider, self.modelo = proveedor, modelo
            return texto
        except Exception:
            if self._openrouter_client:
                resp = self._openrouter_client.chat.completions.create(
                    model=self._openrouter_modelo,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                self.provider, self.modelo = "OpenRouter", self._openrouter_modelo
                return resp.choices[0].message.content
            raise

    def get_db_connection(self):
        """Deprecado: Usar infrastructure.database.manager"""
        # Método mantenido por compatibilidad temporal si es necesario
    
    # Tablas permitidas para consultas directas (whitelist anti SQL-injection)
    ALLOWED_TABLES = frozenset({
        'metrics', 'metrics_hourly', 'predictions', 'catalogos',
        'lineas_transmision', 'alertas_historial', 'commercial_metrics'
    })

    def _llamar_orquestador(self, intent: str, params: Optional[Dict] = None) -> Dict:
        """Llama al orquestador local para obtener datos estructurados en tiempo real."""
        try:
            import requests
            api_key = os.getenv('API_KEY', 'mme-portal-energetico-2026-secret-key')
            response = requests.post(
                'http://localhost:8000/v1/chatbot/orchestrator',
                json={
                    'sessionId': f'chatbot_ia_{intent}',
                    'intent': intent,
                    'parameters': params or {},
                },
                headers={'Content-Type': 'application/json', 'X-API-Key': api_key},
                timeout=15,
            )
            if response.status_code == 200:
                return response.json().get('data', {})
        except Exception as e:
            print(f'⚠️ Orquestador no disponible para intent {intent}: {e}')
        return {}

    def obtener_contexto_sistema(self) -> str:
        """
        Obtiene el contexto del sistema eléctrico en tiempo real:
        estado actual, anomalías detectadas y alertas recientes.
        Retorna un texto formateado para incluir en el prompt del chatbot.
        """
        secciones = []

        # Estado actual (KPIs reales)
        estado = self._llamar_orquestador('estado_actual')
        fichas = estado.get('fichas', [])
        if fichas:
            kpis = []
            for f in fichas[:6]:
                nombre = f.get('nombre', f.get('titulo', ''))
                valor = f.get('valor_actual', f.get('valor', ''))
                unidad = f.get('unidad', '')
                estado_kpi = f.get('estado', '')
                if nombre and valor:
                    kpis.append(f'  - {nombre}: {valor} {unidad} [{estado_kpi}]'.strip())
            if kpis:
                secciones.append('ESTADO ACTUAL DEL SISTEMA (datos reales):\n' + '\n'.join(kpis))

        # Anomalías detectadas
        anomalias_data = self._llamar_orquestador('anomalias_detectadas')
        anomalias = anomalias_data.get('anomalias', [])
        if anomalias:
            items = [f"  - [{a.get('severidad','?')}] {a.get('descripcion', a.get('metrica',''))}" for a in anomalias[:5]]
            secciones.append('ANOMALÍAS DETECTADAS (sistema de monitoreo):\n' + '\n'.join(items))

        # Alertas recientes de la BD (últimas 24h)
        try:
            df_alertas = db_manager.query_df("""
                SELECT metrica, severidad, descripcion, fecha_generacion
                FROM alertas_historial
                WHERE fecha_generacion >= NOW() - INTERVAL '24 hours'
                  AND severidad IN ('CRÍTICO', 'ALERTA')
                ORDER BY fecha_generacion DESC
                LIMIT 5
            """)
            if not df_alertas.empty:
                items = []
                for _, row in df_alertas.iterrows():
                    items.append(
                        f"  - [{row['severidad']}] {row['metrica']}: {row['descripcion']} ({str(row['fecha_generacion'])[:16]})"
                    )
                secciones.append('ALERTAS RECIENTES (BD, últimas 24h):\n' + '\n'.join(items))
        except Exception:
            pass

        return '\n\n'.join(secciones) if secciones else ''

    def obtener_datos_recientes(self, tabla: str, limite: int = 100) -> List[Dict]:
        """Obtiene datos recientes de una tabla específica desde PostgreSQL"""
        try:
            # Validar nombre de tabla contra whitelist (prevenir SQL injection)
            if tabla not in self.ALLOWED_TABLES:
                print(f"⚠️ Tabla '{tabla}' no está en la whitelist de tablas permitidas")
                return []
            # tabla validada contra whitelist → seguro usar en query
            query = f"SELECT * FROM {tabla} ORDER BY fecha DESC LIMIT %s"
            df = db_manager.query_df(query, params=(limite,))
            
            if df.empty:
                return []
            return df.to_dict('records')
        except Exception as e:
            print(f"❌ Error obteniendo datos de {tabla}: {e}")
            return []
    
    def obtener_metricas(self, metric_code: str, limite: int = 100) -> List[Dict]:
        """Obtiene métricas específicas desde la tabla metrics"""
        try:
            query = """
                SELECT fecha, valor_gwh, metrica, entidad, recurso
                FROM metrics
                WHERE metrica = %s
                ORDER BY fecha DESC
                LIMIT %s
            """
            df = db_manager.query_df(query, params=(metric_code, limite))
            
            if df.empty:
                return []
            return df.to_dict('records')
        except Exception as e:
            print(f"❌ Error obteniendo métrica {metric_code}: {e}")
            return []
    
    def obtener_datos_contexto_pagina(self, ruta_pagina: str) -> Dict:
        """Obtiene datos específicos según la página del dashboard que el usuario está viendo"""
        datos_contexto = {
            'pagina': ruta_pagina,
            'metricas': {}
        }
        
        # Mapeo de páginas a métricas relevantes
        mapeo_metricas = {
            '/generacion': ['Gene'],
            '/generacion-fuentes': ['Gene'],
            '/generacion/hidraulica/hidrologia': ['AporCaudal', 'AporEner', 'PorcApor'],
            '/demanda': ['DemaReal', 'DemaCome'],
            '/distribucion': ['DemaReal'],
            '/perdidas': ['PerdReal'],
            '/transmision': ['Dispo'],
            '/disponibilidad': ['Dispo'],
            '/restricciones': ['Gene', 'DemaReal']
        }
        
        # Obtener métricas según la página
        metricas_a_consultar = mapeo_metricas.get(ruta_pagina, ['Gene', 'DemaReal'])
        
        for metrica in metricas_a_consultar:
            datos = self.obtener_metricas(metrica, limite=50)
            if datos:
                datos_contexto['metricas'][metrica] = datos
        
        return datos_contexto
    
    def analizar_demanda(self, periodo: str = "última semana") -> str:
        """Analiza patrones de demanda eléctrica"""
        # Obtener datos de demanda de la tabla metrics
        datos = self.obtener_metricas('DemaReal', 500)

        if not datos:
            return "⚠️ No hay datos disponibles para analizar demanda"

        # Fase 13: contexto adicional de RAG (informes reales, sin tema fijo —
        # la demanda no tiene un tema de informe específico) y de los índices
        # regulatorios de ontologia.dim_metrica (Fase 12).
        from domain.services.contexto_ia_enriquecido import contexto_rag_texto
        contexto_rag = contexto_rag_texto("demanda del sistema consumo eléctrico", top_k=2)

        # Preparar contexto para el modelo
        contexto = f"""
Eres un experto analista del sector eléctrico colombiano trabajando para el Ministerio de Minas y Energía.

DATOS DE DEMANDA ({periodo}):
{json.dumps(datos[:20], indent=2, default=str)}

{contexto_rag}

TAREA:
1. Identifica patrones y tendencias en la demanda eléctrica
2. Detecta anomalías o picos inusuales
3. Compara con comportamiento histórico
4. Genera alertas si es necesario
5. Proporciona recomendaciones operativas

Responde en español de forma concisa y técnica.
"""
        
        try:
            return self.completar(
                messages=[
                    {"role": "system", "content": "Eres un analista experto del sector eléctrico colombiano."},
                    {"role": "user", "content": contexto}
                ],
                temperature=0.7,
                max_tokens=1000
            )

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                return "⏳ **Límite de uso alcanzado**. El servicio de IA gratuito tiene un límite diario. Espera unas horas o contacta al administrador."
            return f"❌ Error analizando demanda: {error_msg}"
    
    def analizar_generacion(self, tipo_fuente: Optional[str] = None) -> str:
        """Analiza generación eléctrica por fuentes"""
        # Obtener datos de generación de la tabla metrics
        datos = self.obtener_metricas('Gene', 500)
        
        if not datos:
            return "⚠️ No hay datos disponibles para analizar generación"
        
        filtro = f" tipo '{tipo_fuente}'" if tipo_fuente else ""

        # Fase 13: RAG con tema='despacho' (disponibilidad de plantas, precio de
        # predespacho) + índices regulatorios de dim_metrica.
        from domain.services.contexto_ia_enriquecido import contexto_rag_texto, contexto_indices_regulatorios_texto
        contexto_rag = contexto_rag_texto(
            "generación térmica hidráulica composición de la matriz energética", tema=None, top_k=2
        )
        contexto_despacho = contexto_rag_texto("plantas indisponibles mantenimiento despacho", tema="despacho", top_k=2)
        contexto_indices = contexto_indices_regulatorios_texto()

        contexto = f"""
Eres un experto en energías renovables y generación eléctrica en Colombia.

DATOS DE GENERACIÓN{filtro}:
{json.dumps(datos[:20], indent=2, default=str)}

{contexto_rag}

{contexto_despacho}

{contexto_indices}

TAREA:
1. Analiza la composición de la matriz energética
2. Evalúa el desempeño de fuentes renovables vs no renovables
3. Identifica tendencias en la transición energética
4. Detecta problemas operativos o caídas significativas
5. Genera recomendaciones para optimización

Responde en español con enfoque técnico y datos específicos.
"""
        
        try:
            return self.completar(
                messages=[
                    {"role": "system", "content": "Eres un experto en generación eléctrica y energías renovables."},
                    {"role": "user", "content": contexto}
                ],
                temperature=0.7,
                max_tokens=1000
            )

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                return "⏳ **Límite de uso alcanzado**. El servicio de IA gratuito tiene un límite diario. Espera unas horas o contacta al administrador."
            return f"❌ Error analizando generación: {error_msg}"
    
    def detectar_alertas(self) -> Dict[str, List[str]]:
        """Detecta alertas y anomalías en tiempo real"""
        alertas = {
            "criticas": [],
            "advertencias": [],
            "informativas": []
        }
        
        # Obtener datos recientes de múltiples fuentes
        demanda = self.obtener_metricas('DemaReal', 50)
        generacion = self.obtener_metricas('Gene', 50)

        # Fase 13: los índices regulatorios reales (NE/HSIN/PBP/Condición del
        # Sistema, ontologia.dim_metrica) le dan al modelo los umbrales oficiales
        # en vez de que los infiera de memoria al clasificar severidad.
        from domain.services.contexto_ia_enriquecido import contexto_indices_regulatorios_texto
        contexto_indices = contexto_indices_regulatorios_texto()

        contexto = f"""
Eres un sistema de monitoreo automático del sector eléctrico colombiano.

DATOS RECIENTES:
Demanda: {json.dumps(demanda[:5], indent=2, default=str)}
Generación: {json.dumps(generacion[:5], indent=2, default=str)}

{contexto_indices}

TAREA:
Analiza los datos y clasifica las alertas en:

CRÍTICAS: Problemas que requieren acción inmediata
ADVERTENCIAS: Situaciones que necesitan monitoreo
INFORMATIVAS: Datos relevantes sin riesgo inmediato

Responde SOLO con JSON válido en este formato:
{{
  "criticas": ["alerta1", "alerta2"],
  "advertencias": ["alerta3"],
  "informativas": ["info1"]
}}
"""
        
        try:
            contenido = self.completar(
                messages=[
                    {"role": "system", "content": "Eres un sistema de detección de alertas. Responde SOLO con JSON válido."},
                    {"role": "user", "content": contexto}
                ],
                temperature=0.3,
                max_tokens=500
            )

            # Intentar parsear JSON de la respuesta
            # Limpiar markdown si existe
            if "```json" in contenido:
                contenido = contenido.split("```json")[1].split("```")[0]
            elif "```" in contenido:
                contenido = contenido.split("```")[1].split("```")[0]
            
            alertas = json.loads(contenido.strip())
            
        except Exception as e:
            print(f"⚠️ Error detectando alertas: {e}")
            alertas["advertencias"].append(f"Error en sistema de alertas: {str(e)}")
        
        return alertas
    
    def chat_interactivo(self, pregunta: str, contexto_dashboard: Optional[Dict] = None) -> str:
        """Chat interactivo para responder preguntas del usuario"""
        
        # Contexto en tiempo real del orquestador (estado, anomalías, alertas)
        contexto_sistema = self.obtener_contexto_sistema()
        info_contexto = ""
        if contexto_sistema:
            info_contexto += f"\n\nCONTEXTO DEL SISTEMA EN TIEMPO REAL:\n{contexto_sistema}"
        if contexto_dashboard:
            info_contexto += f"\n\nCONTEXTO ACTUAL DEL DASHBOARD:\n{json.dumps(contexto_dashboard, indent=2, default=str)}"

        # Fase 13: RAG general (sin tema fijo — la pregunta del usuario es libre)
        # sobre la pregunta misma, mismo patrón que usa el Asistente IA.
        from domain.services.contexto_ia_enriquecido import contexto_rag_texto
        contexto_rag = contexto_rag_texto(pregunta, top_k=3)
        if contexto_rag:
            info_contexto += f"\n\n{contexto_rag}"

        prompt = f"""
Eres un analista energético del sector eléctrico colombiano. Habla de forma natural, clara y amigable.

Tienes acceso a datos en tiempo real del Sistema Interconectado Nacional (SIN).
{info_contexto}

PREGUNTA DEL USUARIO:
{pregunta}

**ESTILO DE COMUNICACIÓN OBLIGATORIO:**

**1. Tono conversacional y humano**
Escribe como hablaría un analista experimentado, no como un reporte técnico rígido.

**2. Explica en contexto**
No solo digas números. Explica qué significan y por qué son importantes.

**3. Usa párrafos fluidos, no listas excesivas**
Agrupa ideas relacionadas en párrafos cortos (2-4 líneas). Usa bullets solo cuando sea realmente necesario.

**4. Interpreta valores inusuales**
Si ves picos, mínimos de 0, o datos extraños, explica por qué pueden ocurrir.

**5. Cierra con interpretación clara**
Termina con una conclusión sobre el estado del sistema: ¿está estable? ¿hay alertas? ¿funciona con normalidad?

**FORMATO VISUAL:**
- Usa **negritas** solo para cifras clave o conceptos importantes
- Incluye 1-2 emojis relevantes al inicio de párrafos (⚡🌊🔥☀️💧📊)
- Máximo 300 palabras
- Separa ideas con líneas en blanco para respirar

**EJEMPLO DE RESPUESTA IDEAL:**

"La generación hoy se mantiene en **244 GWh**, un nivel que cubre cómodamente la demanda del país. La diferencia entre generación y consumo es amplia, lo que muestra que el sistema está operando con tranquilidad.

🌊 Aunque no hay datos desagregados de renovables, por la composición usual del SIN es probable que la mayor parte provenga de hidráulicas. Esto es positivo porque reduce costos de generación térmica.

En resumen, no se observan alertas y el sistema se mantiene estable con holgura en la oferta."

**❌ EVITA:**
- Múltiples títulos con ### seguidos
- Listas largas sin conexión narrativa
- Frases como "Según los datos en tiempo real del Dashboard..."
- Bloques de emojis sin texto
- Formato de informe técnico rígido
"""
        
        try:
            return self.completar(
                messages=[
                    {"role": "system", "content": "Eres un experto asistente del sector energético colombiano."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                return "⏳ **Límite de uso alcanzado**\n\nEl servicio de IA gratuito tiene un límite de 50 preguntas por día.\n\n**¿Qué hacer?**\n- Espera hasta mañana\n- Usa el dashboard manualmente\n- Contacta al administrador para opciones de pago"
            return f"❌ Error procesando pregunta: {error_msg}"
    
    def resumen_dashboard(self) -> str:
        """Genera resumen ejecutivo del estado actual del sistema eléctrico"""
        
        # Obtener datos de todas las fuentes
        demanda = self.obtener_metricas('DemaReal', 100)
        generacion = self.obtener_metricas('Gene', 100)

        # Fase 13: RAG general (panorama del sector) para que el resumen pueda
        # citar contexto real (clima, despacho) además de los números crudos.
        from domain.services.contexto_ia_enriquecido import contexto_rag_texto
        contexto_rag = contexto_rag_texto("panorama energético estado del sistema eléctrico", top_k=2)

        contexto = f"""
Genera un resumen ejecutivo del sistema eléctrico colombiano con estilo natural y conversacional.

DATOS DISPONIBLES:
Demanda: {len(demanda)} registros recientes
Generación: {len(generacion)} registros recientes

Últimos datos de demanda:
{json.dumps(demanda[:5], indent=2, default=str)}

Últimos datos de generación:
{json.dumps(generacion[:5], indent=2, default=str)}

{contexto_rag}

🎯 **ESTILO OBLIGATORIO - LEE ESTO PRIMERO:**

Escribe como un analista senior explicando la situación a un director. Usa lenguaje natural, fluido y claro.

**ESTRUCTURA NARRATIVA:**

**Párrafo 1 - Estado general** (3-4 líneas)
Explica cómo está funcionando el sistema hoy: ¿hay suficiente generación? ¿cubre la demanda? ¿con qué margen?

**Párrafo 2 - Composición energética** (3-4 líneas)
Describe qué fuentes están generando y cuál predomina. Explica por qué es relevante.

**Párrafo 3 - Conclusión operativa** (2-3 líneas)
Resume el estado: ¿sistema estable? ¿hay alertas? ¿funciona con normalidad?

**REGLAS DE FORMATO:**
- Usa **negritas** solo para cifras importantes (no más de 5 en total)
- 1-2 emojis al inicio de cada párrafo (⚡🌊📊💡🔋)
- Máximo 400 palabras total
- Párrafos cortos separados por línea en blanco
- NO uses títulos ## ni ###
- NO hagas listas de bullets largas

**EJEMPLO DE RESPUESTA IDEAL:**

"⚡ El sistema eléctrico hoy opera con normalidad. La generación alcanza **244 GWh**, superando cómodamente la demanda nacional de **210 GWh**. Este margen del **16%** garantiza estabilidad y capacidad de respuesta ante variaciones.

🌊 La matriz energética mantiene su perfil histórico con predominio hidráulico, lo cual es favorable por los menores costos operativos. La generación térmica complementa en horas pico, mientras que las renovables no convencionales aportan gradualmente a la diversificación.

En síntesis, el Sistema Interconectado Nacional presenta condiciones normales de operación, sin alertas ni restricciones significativas. La oferta cubre la demanda con holgura suficiente."

**❌ EVITA:**
- Títulos múltiples (##, ###)
- Listas extensas sin narrativa
- "Según los datos..." o "Dashboard del Ministerio..."
- Formato de informe corporativo rígido
"""
        
        try:
            return self.completar(
                messages=[
                    {"role": "system", "content": "Eres un analista senior del sector eléctrico colombiano."},
                    {"role": "user", "content": contexto}
                ],
                temperature=0.7,
                max_tokens=2000
            )

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                return "⏳ **Límite de uso alcanzado**. El servicio de IA gratuito tiene un límite diario de 50 solicitudes.\n\n**Opciones:**\n1. Espera hasta mañana (el límite se reinicia)\n2. Usa el dashboard manualmente\n3. Contacta al administrador para configurar un modelo de pago"
            return f"❌ Error generando resumen: {error_msg}"


# Instancia global del agente
_agente_global = None

def get_agente() -> AgentIA:
    """Obtiene instancia singleton del agente IA"""
    global _agente_global
    if _agente_global is None:
        _agente_global = AgentIA()
    return _agente_global

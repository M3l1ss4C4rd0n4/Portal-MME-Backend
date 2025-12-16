# Agent - Asistente Conversacional

Agente inteligente basado en LLM + RAG para responder consultas sobre el sector energético.

## Características

- ✅ LLM: OpenAI GPT-4 o Azure OpenAI
- ✅ RAG: Retrieval-Augmented Generation con vector DB
- ✅ Herramientas: SQL, gráficos, simuladores
- ✅ Memoria conversacional con Redis
- ✅ WhatsApp Business Cloud integration
- ✅ Auditoría completa de interacciones

## Estructura

```
agent/
├── core/
│   ├── agent.py           # Agente principal (LangChain)
│   ├── memory.py          # Memoria conversacional (Redis)
│   └── tools.py           # Herramientas disponibles
├── rag/
│   ├── vectorstore.py     # Weaviate/Pinecone
│   ├── embeddings.py      # OpenAI embeddings
│   └── retriever.py       # Búsqueda y ranking
├── whatsapp/
│   ├── webhook.py         # Endpoint para WhatsApp
│   ├── sender.py          # Envío de mensajes
│   ├── templates.py       # Plantillas aprobadas
│   └── security.py        # HMAC validation
├── news/
│   ├── scrapers/          # Web scrapers
│   ├── summarizer.py      # NLP summarization
│   └── ranker.py          # Ranking por relevancia
├── scheduler/
│   ├── daily_summary.py   # Resumen diario (7 AM)
│   └── news_digest.py     # Top-3 noticias (6:30 AM)
├── audit/
│   └── logger.py          # Log de todas las interacciones
└── requirements.txt
```

## Instalación

```bash
cd agent
pip install -r requirements.txt
```

## Configuración

```env
OPENAI_API_KEY=sk-...
WEAVIATE_URL=http://localhost:8080
REDIS_URL=redis://localhost:6379
WHATSAPP_PHONE_ID=123456789
WHATSAPP_TOKEN=EAAxxxxx
WHATSAPP_VERIFY_TOKEN=mi_token_secreto
WHATSAPP_WEBHOOK_SECRET=secreto_hmac
```

## Ejecutar Agente

```bash
# Servidor de webhook
python -m whatsapp.webhook

# Scheduler (cron jobs)
python -m scheduler.daily_summary
```

## Herramientas Disponibles

### 1. SQL Tool
Permite al agente ejecutar queries SQL sobre la base de datos:
```python
tool_sql("SELECT AVG(demanda) FROM demanda_nacional WHERE fecha >= '2025-01-01'")
```

### 2. Plot Tool
Genera gráficos:
```python
tool_plot("demanda_nacional", x="fecha", y="demanda", tipo="line")
```

### 3. Simulator Tool
Ejecuta simuladores:
```python
tool_simulator("hydrologic", scenario="Niño", months=3)
```

### 4. RAG Tool
Busca información en documentos:
```python
tool_rag("¿Cuál es la resolución vigente de tarifas?")
```

## WhatsApp Business Setup

1. Crear cuenta Meta Business Manager
2. Configurar WhatsApp Business App
3. Obtener Phone Number ID y Access Token
4. Configurar webhook URL: `https://tudominio.com/whatsapp/webhook`
5. Verificar webhook con token
6. Aprobar plantillas de mensajes

## Plantillas de Mensajes

### daily_summary
```
🌅 *Resumen Diario - {fecha}*

📊 *Demanda:* {demanda} GWh
💰 *Precio promedio:* ${precio} COP/kWh
⚠️ *Alertas:* {num_alertas}

📰 *Top-3 Noticias:*
1. {noticia1}
2. {noticia2}
3. {noticia3}
```

### critical_alert
```
🚨 *Alerta Crítica*

{mensaje_alerta}

Acción requerida: {accion}
```

## Auditoría

Todas las interacciones se registran en:
- Base de datos (tabla `agent_audit`)
- Logs centralizados (ELK)
- Retención: 7 años

Campos registrados:
- Usuario
- Timestamp
- Prompt original
- Fuentes consultadas
- Respuesta generada
- Modelo y versión
- Tiempo de ejecución

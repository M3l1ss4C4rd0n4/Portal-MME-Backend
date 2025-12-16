# 🔑 Configuración de OpenRouter para Dashboard MME

## 📋 Pasos para Obtener API Key

### 1. Crear Cuenta en OpenRouter

Visita: **https://openrouter.ai/auth**

- Regístrate con email o GitHub
- Confirma tu email

### 2. Obtener API Key

1. Ve a: **https://openrouter.ai/settings/keys**
2. Haz clic en **"Create Key"**
3. Nombre sugerido: `Dashboard-MME-Energia-Colombia`
4. Límite sugerido: `$10 USD` (suficiente para ~100,000 queries con DeepSeek R1 que es GRATIS)
5. Copia la clave (formato: `sk-or-v1-...`)

### 3. Configurar en el Servidor

```bash
# Opción A: Variable de entorno global (RECOMENDADO)
echo 'export OPENROUTER_API_KEY="TU_CLAVE_AQUI"' >> ~/.bashrc
source ~/.bashrc

# Opción B: Archivo .env local (solo para esta API)
cd /home/admonctrlxm/server/api-energia
nano .env
# Editar línea 12: OPENROUTER_API_KEY=sk-or-v1-tu-clave-real-aqui
```

### 4. Verificar Configuración

```bash
# Ver si la variable está configurada
echo $OPENROUTER_API_KEY

# Debería mostrar: sk-or-v1-...
```

### 5. Reiniciar API

```bash
cd /home/admonctrlxm/server/api-energia
npm start
```

## 🧪 Probar el Agente IA

```bash
# Test básico de análisis
curl -X POST http://localhost:3000/api/ia/analizar \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "¿Cuál es el estado actual del Sistema Interconectado Nacional?"
  }'

# Detectar anomalías
curl http://localhost:3000/api/ia/anomalias

# Resumen del dashboard
curl http://localhost:3000/api/ia/resumen-dashboard
```

## 💰 Modelo Recomendado: DeepSeek R1

Ya configurado en `.env`:
```
AI_MODEL=tngtech/deepseek-r1t2-chimera:free
```

**Ventajas:**
- ✅ **GRATIS** (sin costo por token)
- ✅ Rendimiento similar a GPT-4
- ✅ 128K tokens de contexto
- ✅ Razonamiento avanzado
- ✅ Especializado en análisis técnico

## 🔄 Integración con Dashboard Dash

La API Node.js ya está lista para recibir consultas desde el dashboard Python:

```python
# En cualquier callback de Dash
import requests

# Analizar anomalías
response = requests.get('http://localhost:3000/api/ia/anomalias')
analisis = response.json()

# Proyectar demanda
response = requests.post('http://localhost:3000/api/ia/proyectar-demanda',
                        json={'horizonte': '24 horas'})
proyeccion = response.json()
```

## ⚡ Características Implementadas

### Endpoints de IA Disponibles:

1. **`POST /api/ia/analizar`** - Analizar pregunta del usuario
   - Input: `{"pregunta": "texto"}`
   - Output: Respuesta contextualizada con datos del SIN

2. **`GET /api/ia/resumen-dashboard`** - Resumen ejecutivo automático
   - Analiza: Demanda, generación, precios, restricciones
   - Identifica: Tendencias, riesgos, recomendaciones

3. **`GET /api/ia/anomalias`** - Detección de anomalías
   - Detecta: Picos inusuales, caídas, comportamientos atípicos
   - Clasifica: Severidad (crítica/alta/media/baja)

4. **`POST /api/ia/proyectar-demanda`** - Proyecciones futuras
   - Input: `{"horizonte": "24 horas"}`
   - Output: Proyección con rango de confianza

5. **`GET /api/ia/analizar-cu`** - Análisis del Costo Unitario
   - Descompone: G, T, D, Cv, R, PR
   - Identifica: Componente con mayor impacto

6. **`GET /api/ia/historico`** - Histórico de análisis
   - Consultas previas del usuario
   - Estadísticas de uso

7. **`GET /api/ia/estadisticas`** - Métricas del agente
   - Tokens usados
   - Tiempo promedio de respuesta
   - Tasa de éxito

## 🎯 Sistema Prompt del Agente

El agente está entrenado para:

- ✅ Regulación CREG
- ✅ Operación del SIN por XM
- ✅ Análisis del Costo Unitario (CU)
- ✅ Mercado mayorista
- ✅ Bolsa de energía
- ✅ Generación por tecnología
- ✅ Transmisión (STN)
- ✅ Distribución (SAIDI, SAIFI)
- ✅ Pérdidas técnicas/no técnicas
- ✅ Calidad del servicio
- ✅ Proyecciones y tendencias

## 🔐 Seguridad

- ✅ Helmet.js activado (HTTP headers seguros)
- ✅ CORS configurado (solo dashboard autorizado)
- ✅ Rate limiting (100 requests/15 min)
- ✅ Compresión gzip
- ✅ Logs con Morgan

## 📊 Base de Datos

La API usa SQLite (`energia.db`) con tablas:

- `demanda_tiempo_real`
- `generacion_tiempo_real`
- `generacion_por_tipo`
- `transmision`
- `precios_bolsa`
- `restricciones`
- `perdidas`
- `comercializacion`
- `distribucion`
- `costo_unitario`
- `alertas_sistema`
- `analisis_ia` (nuevo - historial del agente)

## 🚀 Próximos Pasos

1. ✅ Obtener API Key de OpenRouter
2. ✅ Configurar variable de entorno
3. ✅ Reiniciar API
4. ✅ Probar endpoints de IA
5. ⏳ Integrar chat en tiempo real en dashboard
6. ⏳ Agregar notificaciones de alertas
7. ⏳ Dashboard de métricas del agente IA

## 🆘 Soporte

- OpenRouter Docs: https://openrouter.ai/docs
- DeepSeek Docs: https://platform.deepseek.com/
- Issues: Tu repositorio GitHub

---

**Creado para:** Ministerio de Minas y Energía - Dashboard Portal Energético  
**Fecha:** Diciembre 2025  
**Modelo IA:** DeepSeek R1 (gratis vía OpenRouter)

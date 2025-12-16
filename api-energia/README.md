# 🌟 API Energía Colombia + Agente IA DeepSeek

Sistema completo de **Datos Energéticos** + **Analista de IA** para el Ministerio de Minas y Energía de Colombia.

## 📋 Características

✅ **API REST** con datos del Sistema Interconectado Nacional (SIN)  
✅ **Agente de IA** analista experto en el sector energético colombiano  
✅ **Cron Jobs** automáticos para actualización de datos cada 5-15 minutos  
✅ **Base de datos SQLite** con histórico de datos  
✅ **Integración con APIs de XM** (eXpertos en Mercados)  
✅ **DeepSeek R1** vía OpenRouter para análisis avanzados  
✅ **Detección automática de anomalías**  
✅ **Proyecciones de demanda y precios**  
✅ **Análisis del Costo Unitario (CU)**  
✅ **Resúmenes ejecutivos** para toma de decisiones  

---

## 🚀 Instalación Rápida

### Prerrequisitos

- Node.js 18+ 
- Ubuntu/Linux
- Cuenta en OpenRouter ([https://openrouter.ai](https://openrouter.ai))

### 1. Clonar o copiar el proyecto

```bash
cd /home/admonctrlxm/server/api-energia
```

### 2. Obtener API Key de OpenRouter

1. Ve a [https://openrouter.ai/settings/keys](https://openrouter.ai/settings/keys)
2. Crea una nueva API Key con el nombre: **"server-deepseek-production"**
3. Asegúrate de dar permisos para el modelo: **tngtech/deepseek-r1t2-chimera:free**
4. Copia la API Key

### 3. Configurar API Key

```bash
# Crear archivo de configuración
nano ~/.openrouter

# Añadir (reemplaza con tu API Key real):
export OPENROUTER_API_KEY="sk-or-v1-..."

# Guardar (Ctrl+O, Enter, Ctrl+X)

# Añadir a .bashrc
echo "" >> ~/.bashrc
echo "# OpenRouter API Key" >> ~/.bashrc
echo "source ~/.openrouter" >> ~/.bashrc

# Recargar
source ~/.bashrc

# Verificar
echo $OPENROUTER_API_KEY
```

### 4. Instalar automáticamente

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

O manualmente:

```bash
npm install
npm run db:init
```

### 5. Iniciar servidor

**Desarrollo:**
```bash
npm run dev
```

**Producción con PM2:**
```bash
pm2 start ecosystem.config.cjs
pm2 logs api-energia
pm2 monit
```

---

## 📡 Endpoints Disponibles

### 📊 Datos del Sistema

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/demanda` | Demanda en tiempo real |
| GET | `/api/generacion` | Generación por recurso |
| GET | `/api/generacion/por-tipo` | Generación agregada por tipo |
| GET | `/api/transmision` | Estado del STN |
| GET | `/api/precios` | Precios de bolsa |
| GET | `/api/restricciones` | Restricciones del sistema |
| GET | `/api/perdidas` | Pérdidas del sistema |
| GET | `/api/comercializacion` | Datos del mercado |
| GET | `/api/distribucion` | Indicadores de distribución |
| GET | `/api/costo-unitario` | Componentes del CU |
| GET | `/api/alertas` | Alertas activas |
| GET | `/api/resumen` | Resumen general del SIN |

### 🤖 Agente de IA

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/ia/analizar` | Analizar pregunta con IA |
| GET | `/api/ia/resumen-dashboard` | Resumen ejecutivo |
| GET | `/api/ia/anomalias` | Detectar anomalías |
| POST | `/api/ia/proyectar-demanda` | Proyectar demanda futura |
| GET | `/api/ia/analizar-cu` | Análisis del CU |
| GET | `/api/ia/historico` | Histórico de análisis |
| GET | `/api/ia/estadisticas` | Estadísticas de uso |

---

## 💻 Ejemplos de Uso

### Obtener demanda actual

```bash
curl http://localhost:3000/api/demanda?limit=10
```

### Obtener generación por tipo (últimas 24 horas)

```bash
curl http://localhost:3000/api/generacion/por-tipo?hours=24
```

### Analizar con IA

```bash
curl -X POST http://localhost:3000/api/ia/analizar \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "¿Cómo se comportó la demanda hoy y qué impacto tendrá mañana?"
  }'
```

### Obtener resumen ejecutivo

```bash
curl http://localhost:3000/api/ia/resumen-dashboard
```

### Detectar anomalías

```bash
curl http://localhost:3000/api/ia/anomalias
```

### Proyectar demanda

```bash
curl -X POST http://localhost:3000/api/ia/proyectar-demanda \
  -H "Content-Type: application/json" \
  -d '{
    "horizonte": "48 horas"
  }'
```

---

## 🗄️ Estructura de Base de Datos

### Tablas Principales

- **demanda** - Demanda en tiempo real por región
- **generacion** - Generación por recurso y tipo de fuente
- **transmision** - Estado de elementos del STN
- **distribucion** - Indicadores de calidad (SAIDI, SAIFI)
- **comercializacion** - Datos del mercado mayorista
- **perdidas** - Pérdidas técnicas y no técnicas
- **restricciones** - Restricciones operativas y su costo
- **precios_bolsa** - Precios spot de energía
- **costo_unitario** - Componentes del CU (G, T, D, Cv, R, PR)
- **analisis_ia** - Histórico de análisis del agente IA
- **alertas** - Anomalías detectadas automáticamente

---

## ⚙️ Configuración Avanzada

### Variables de Entorno (`.env`)

```bash
NODE_ENV=production
PORT=3000
DB_PATH=./src/db/energia.db

# OpenRouter
OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
AI_MODEL=tngtech/deepseek-r1t2-chimera:free
AI_MAX_TOKENS=4000
AI_TEMPERATURE=0.7

# Cron jobs (formato cron)
CRON_DEMANDA=*/5 * * * *      # Cada 5 minutos
CRON_GENERACION=*/5 * * * *   # Cada 5 minutos
CRON_TRANSMISION=*/10 * * * * # Cada 10 minutos
CRON_PRECIOS=*/15 * * * *     # Cada 15 minutos

# CORS
ALLOWED_ORIGINS=http://localhost:8050,http://localhost:7860
```

### Personalizar Frecuencia de Actualización

Editar `src/services/cronJobs.js`:

```javascript
// Cada 1 minuto
cron.schedule('* * * * *', async () => {
  await this.actualizarDemanda();
});
```

### Cambiar Modelo de IA

En `.env`:

```bash
# Otros modelos gratuitos de OpenRouter:
AI_MODEL=google/gemini-2.0-flash-lite:free
AI_MODEL=meta-llama/llama-3-8b-instruct:free
AI_MODEL=microsoft/phi-3-mini-128k-instruct:free
```

---

## 🔧 Comandos PM2

```bash
# Iniciar
pm2 start ecosystem.config.cjs

# Ver logs en tiempo real
pm2 logs api-energia

# Monitoreo
pm2 monit

# Reiniciar
pm2 restart api-energia

# Detener
pm2 stop api-energia

# Eliminar
pm2 delete api-energia

# Guardar configuración para inicio automático
pm2 save
pm2 startup
```

---

## 📊 Integración con Dashboard

### Desde Python (Dash):

```python
import requests

# Obtener demanda
response = requests.get('http://localhost:3000/api/demanda?limit=100')
data = response.json()['data']

# Obtener análisis de IA
response = requests.post('http://localhost:3000/api/ia/analizar', json={
    'pregunta': '¿Cuál es el estado del SIN?'
})
analisis = response.json()['respuesta']
```

### Desde JavaScript:

```javascript
// Obtener resumen
fetch('http://localhost:3000/api/resumen')
  .then(res => res.json())
  .then(data => console.log(data));

// Analizar con IA
fetch('http://localhost:3000/api/ia/analizar', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    pregunta: '¿Cómo está la demanda hoy?'
  })
})
  .then(res => res.json())
  .then(data => console.log(data.respuesta));
```

---

## 🧪 Testing

### Probar endpoint de demanda

```bash
curl http://localhost:3000/api/demanda
```

### Probar agente IA

```bash
curl -X POST http://localhost:3000/api/ia/analizar \
  -H "Content-Type: application/json" \
  -d '{"pregunta": "Explica el CU en Colombia"}'
```

### Ver logs

```bash
tail -f logs/api.log
pm2 logs api-energia
```

---

## 🤖 Capacidades del Agente IA

El agente de IA está especializado en:

### Conocimientos

- 📚 Regulación CREG (Comisión de Regulación de Energía y Gas)
- ⚡ Sistema Interconectado Nacional (SIN)
- 💰 Cálculo del Costo Unitario (CU) y sus componentes
- 📈 Análisis de mercado mayorista
- 🔌 Transmisión (STN), Distribución (SDL), Generación
- 📊 Indicadores de calidad (SAIDI, SAIFI, FMIK)
- 🌍 Demanda nacional y regional
- ⚠️ Pérdidas técnicas y no técnicas

### Análisis que Puede Realizar

1. **Tendencias** - Identificar patrones en demanda, generación, precios
2. **Anomalías** - Detectar comportamientos inusuales automáticamente
3. **Proyecciones** - Estimar demanda futura, precios de bolsa
4. **Explicaciones** - Interpretar gráficas y datos complejos
5. **Recomendaciones** - Sugerir acciones operativas o regulatorias
6. **Resúmenes Ejecutivos** - Informes listos para ministros
7. **Análisis del CU** - Descomposición y diagnóstico de costos
8. **Alertas** - Identificar riesgos o problemas críticos

---

## 📁 Estructura del Proyecto

```
api-energia/
├── src/
│   ├── config/
│   │   └── index.js          # Configuración central
│   ├── db/
│   │   └── database.js       # Manejador SQLite
│   ├── services/
│   │   ├── xmClient.js       # Cliente API de XM
│   │   ├── aiAgent.js        # Agente IA DeepSeek
│   │   └── cronJobs.js       # Tareas programadas
│   ├── controllers/
│   │   ├── dataController.js # Controlador de datos
│   │   └── aiController.js   # Controlador de IA
│   ├── routes/
│   │   ├── dataRoutes.js     # Rutas de datos
│   │   └── aiRoutes.js       # Rutas de IA
│   └── server.js             # Servidor principal
├── scripts/
│   ├── schema.sql            # Esquema de BD
│   ├── initDatabase.js       # Inicializar BD
│   └── install.sh            # Script de instalación
├── logs/                     # Logs del sistema
├── tests/                    # Tests unitarios
├── docs/                     # Documentación
├── package.json
├── ecosystem.config.cjs      # Configuración PM2
├── .env                      # Variables de entorno
└── README.md                 # Este archivo
```

---

## 🐛 Troubleshooting

### Error: "OPENROUTER_API_KEY no configurada"

```bash
# Verificar que existe
echo $OPENROUTER_API_KEY

# Si está vacío, cargar de nuevo
source ~/.openrouter

# Verificar contenido del archivo
cat ~/.openrouter
```

### Error: "Cannot find module"

```bash
# Reinstalar dependencias
rm -rf node_modules package-lock.json
npm install
```

### Error: "Database locked"

```bash
# Cerrar todas las conexiones
pm2 stop api-energia
rm -f src/db/energia.db-wal src/db/energia.db-shm
pm2 start api-energia
```

### Cron jobs no se ejecutan

```bash
# Verificar logs
pm2 logs api-energia

# Ver errores específicos
tail -f logs/api.log
```

---

## 📚 Recursos Adicionales

- [OpenRouter Documentation](https://openrouter.ai/docs)
- [DeepSeek Model](https://openrouter.ai/models/tngtech/deepseek-r1t2-chimera)
- [XM Colombia](https://www.xm.com.co/)
- [CREG](https://www.creg.gov.co/)
- [Ministerio de Minas y Energía](https://www.minenergia.gov.co/)

---

## 👤 Autor

Ministerio de Minas y Energía de Colombia  
Sistema desarrollado para el Dashboard Energético Nacional

---

## 📄 Licencia

MIT License

---

## 🆘 Soporte

Para soporte técnico o consultas:
- Email: soporte@minenergia.gov.co
- Issues: GitHub

---

**¡Sistema listo para producción!** 🚀

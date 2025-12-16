/**
 * Servidor Principal - API Energía Colombia
 */
import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import compression from 'compression';
import morgan from 'morgan';
import config from './config/index.js';
import dbManager from './db/database.js';
import cronJobs from './services/cronJobs.js';
import dataRoutes from './routes/dataRoutes.js';
import aiRoutes from './routes/aiRoutes.js';

const app = express();

// ========================================
// MIDDLEWARES
// ========================================
app.use(helmet()); // Seguridad HTTP headers
app.use(compression()); // Compresión gzip
app.use(cors({
  origin: config.cors.origins,
  credentials: true
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Logging
if (config.nodeEnv === 'development') {
  app.use(morgan('dev'));
} else {
  app.use(morgan('combined'));
}

// ========================================
// RUTAS
// ========================================

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    environment: config.nodeEnv
  });
});

// Rutas de datos
app.use('/api', dataRoutes);

// Rutas de IA
app.use('/api/ia', aiRoutes);

// Ruta de documentación
app.get('/', (req, res) => {
  res.json({
    name: 'API Energía Colombia',
    version: '1.0.0',
    description: 'API de Datos Energéticos + Agente IA',
    endpoints: {
      datos: {
        demanda: 'GET /api/demanda',
        generacion: 'GET /api/generacion',
        generacion_tipo: 'GET /api/generacion/por-tipo',
        transmision: 'GET /api/transmision',
        precios: 'GET /api/precios',
        restricciones: 'GET /api/restricciones',
        perdidas: 'GET /api/perdidas',
        comercializacion: 'GET /api/comercializacion',
        distribucion: 'GET /api/distribucion',
        costo_unitario: 'GET /api/costo-unitario',
        alertas: 'GET /api/alertas',
        resumen: 'GET /api/resumen'
      },
      ia: {
        analizar: 'POST /api/ia/analizar',
        resumen_dashboard: 'GET /api/ia/resumen-dashboard',
        anomalias: 'GET /api/ia/anomalias',
        proyectar_demanda: 'POST /api/ia/proyectar-demanda',
        analizar_cu: 'GET /api/ia/analizar-cu',
        historico: 'GET /api/ia/historico',
        estadisticas: 'GET /api/ia/estadisticas'
      }
    },
    documentation: 'https://github.com/tu-repo/api-energia'
  });
});

// 404 Handler
app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: 'Endpoint no encontrado',
    path: req.path
  });
});

// Error Handler
app.use((err, req, res, next) => {
  console.error('❌ Error:', err);
  
  res.status(err.status || 500).json({
    success: false,
    error: config.nodeEnv === 'development' ? err.message : 'Error interno del servidor',
    stack: config.nodeEnv === 'development' ? err.stack : undefined
  });
});

// ========================================
// INICIALIZACIÓN
// ========================================
async function iniciar() {
  try {
    console.log('🚀 Iniciando API Energía Colombia...');
    console.log(`📌 Entorno: ${config.nodeEnv}`);
    
    // Conectar base de datos
    dbManager.init();
    
    // Iniciar Cron Jobs
    cronJobs.start();
    
    // Ejecutar primera carga de datos
    if (config.nodeEnv === 'production') {
      console.log('🔄 Cargando datos iniciales...');
      await cronJobs.actualizarTodo();
    }
    
    // Iniciar servidor
    app.listen(config.port, () => {
      console.log(`✅ Servidor escuchando en puerto ${config.port}`);
      console.log(`📡 API: http://localhost:${config.port}`);
      console.log(`🤖 Agente IA: ${config.ai.apiKey ? 'Activo' : 'Inactivo (sin API Key)'}`);
      console.log('');
      console.log('📚 Endpoints disponibles:');
      console.log(`   GET  http://localhost:${config.port}/`);
      console.log(`   GET  http://localhost:${config.port}/health`);
      console.log(`   GET  http://localhost:${config.port}/api/demanda`);
      console.log(`   GET  http://localhost:${config.port}/api/generacion`);
      console.log(`   POST http://localhost:${config.port}/api/ia/analizar`);
      console.log(`   GET  http://localhost:${config.port}/api/ia/resumen-dashboard`);
      console.log('');
    });
    
  } catch (error) {
    console.error('❌ Error fatal al iniciar:', error);
    process.exit(1);
  }
}

// Manejo de señales de terminación
process.on('SIGINT', () => {
  console.log('\n⚠️  Señal SIGINT recibida, cerrando...');
  dbManager.close();
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('\n⚠️  Señal SIGTERM recibida, cerrando...');
  dbManager.close();
  process.exit(0);
});

// Iniciar servidor
iniciar();

export default app;

/**
 * Rutas de la API - Endpoints de IA
 */
import express from 'express';
import aiController from '../controllers/aiController.js';

const router = express.Router();

// Analizar pregunta
router.post('/analizar', aiController.analizar.bind(aiController));

// Resumen ejecutivo del dashboard
router.get('/resumen-dashboard', aiController.resumenDashboard.bind(aiController));

// Detectar anomalías
router.get('/anomalias', aiController.detectarAnomalias.bind(aiController));

// Proyectar demanda
router.post('/proyectar-demanda', aiController.proyectarDemanda.bind(aiController));

// Analizar CU
router.get('/analizar-cu', aiController.analizarCU.bind(aiController));

// Histórico de análisis
router.get('/historico', aiController.getHistoricoAnalisis.bind(aiController));

// Estadísticas del agente IA
router.get('/estadisticas', aiController.getEstadisticasIA.bind(aiController));

export default router;

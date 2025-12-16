/**
 * Rutas de la API - Endpoints de Datos
 */
import express from 'express';
import dataController from '../controllers/dataController.js';

const router = express.Router();

// Demanda
router.get('/demanda', dataController.getDemanda.bind(dataController));

// Generación
router.get('/generacion', dataController.getGeneracion.bind(dataController));
router.get('/generacion/por-tipo', dataController.getGeneracionPorTipo.bind(dataController));

// Transmisión
router.get('/transmision', dataController.getTransmision.bind(dataController));

// Precios
router.get('/precios', dataController.getPrecios.bind(dataController));

// Restricciones
router.get('/restricciones', dataController.getRestricciones.bind(dataController));

// Pérdidas
router.get('/perdidas', dataController.getPerdidas.bind(dataController));

// Comercialización
router.get('/comercializacion', dataController.getComercializacion.bind(dataController));

// Distribución
router.get('/distribucion', dataController.getDistribucion.bind(dataController));

// Costo Unitario (CU)
router.get('/costo-unitario', dataController.getCostoUnitario.bind(dataController));

// Alertas
router.get('/alertas', dataController.getAlertas.bind(dataController));

// Resumen general
router.get('/resumen', dataController.getResumenGeneral.bind(dataController));

export default router;

/**
 * Controlador de IA - Endpoints del Agente Analista
 */
import aiAgent from '../services/aiAgent.js';
import dbManager from '../db/database.js';

class AIController {
  /**
   * Analizar pregunta del usuario
   */
  async analizar(req, res) {
    try {
      const { pregunta } = req.body;

      if (!pregunta) {
        return res.status(400).json({
          success: false,
          error: 'Campo "pregunta" es requerido'
        });
      }

      const resultado = await aiAgent.analizar(pregunta);

      res.json(resultado);
    } catch (error) {
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  }

  /**
   * Generar resumen ejecutivo del dashboard
   */
  async resumenDashboard(req, res) {
    try {
      const resultado = await aiAgent.generarResumenEjecutivo();

      res.json(resultado);
    } catch (error) {
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  }

  /**
   * Detectar anomalías
   */
  async detectarAnomalias(req, res) {
    try {
      const resultado = await aiAgent.detectarAnomalias();

      res.json(resultado);
    } catch (error) {
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  }

  /**
   * Proyectar demanda futura
   */
  async proyectarDemanda(req, res) {
    try {
      const { horizonte = '24 horas' } = req.body;

      const resultado = await aiAgent.proyectarDemanda(horizonte);

      res.json(resultado);
    } catch (error) {
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  }

  /**
   * Analizar componentes del CU
   */
  async analizarCU(req, res) {
    try {
      const resultado = await aiAgent.analizarCU();

      res.json(resultado);
    } catch (error) {
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  }

  /**
   * Obtener histórico de análisis
   */
  async getHistoricoAnalisis(req, res) {
    try {
      const { limit = 50, tipo_analisis } = req.query;

      let sql = 'SELECT * FROM analisis_ia';
      const params = [];

      if (tipo_analisis) {
        sql += ' WHERE tipo_analisis = ?';
        params.push(tipo_analisis);
      }

      sql += ' ORDER BY fecha_analisis DESC LIMIT ?';
      params.push(parseInt(limit));

      const datos = dbManager.query(sql, params);

      res.json({
        success: true,
        count: datos.length,
        data: datos
      });
    } catch (error) {
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  }

  /**
   * Obtener estadísticas de uso del agente IA
   */
  async getEstadisticasIA(req, res) {
    try {
      const stats = {
        total_analisis: dbManager.queryOne('SELECT COUNT(*) as total FROM analisis_ia'),
        por_tipo: dbManager.query(`
          SELECT tipo_analisis, COUNT(*) as total 
          FROM analisis_ia 
          GROUP BY tipo_analisis 
          ORDER BY total DESC
        `),
        tokens_totales: dbManager.queryOne('SELECT SUM(tokens_usados) as total FROM analisis_ia'),
        tiempo_promedio_ms: dbManager.queryOne('SELECT AVG(tiempo_respuesta_ms) as promedio FROM analisis_ia'),
        ultimos_7_dias: dbManager.query(`
          SELECT DATE(fecha_analisis) as fecha, COUNT(*) as total
          FROM analisis_ia
          WHERE fecha_analisis >= datetime('now', '-7 days')
          GROUP BY DATE(fecha_analisis)
          ORDER BY fecha DESC
        `)
      };

      res.json({
        success: true,
        data: stats
      });
    } catch (error) {
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  }
}

export default new AIController();

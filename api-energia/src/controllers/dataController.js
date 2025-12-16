/**
 * Controlador de Datos - Endpoints para el Dashboard
 */
import dbManager from '../db/database.js';

class DataController {
  /**
   * Obtener demanda (última hora o rango)
   */
  async getDemanda(req, res) {
    try {
      const { limit = 100, start, end } = req.query;

      let datos;
      if (start && end) {
        datos = dbManager.getByDateRange('demanda', start, end);
      } else {
        datos = dbManager.getLatest('demanda', parseInt(limit));
      }

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
   * Obtener generación
   */
  async getGeneracion(req, res) {
    try {
      const { limit = 100, tipo_fuente, start, end } = req.query;

      let sql = 'SELECT * FROM generacion WHERE 1=1';
      const params = [];

      if (tipo_fuente) {
        sql += ' AND tipo_fuente = ?';
        params.push(tipo_fuente);
      }

      if (start && end) {
        sql += ' AND fecha_hora BETWEEN ? AND ?';
        params.push(start, end);
      }

      sql += ' ORDER BY fecha_hora DESC LIMIT ?';
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
   * Obtener generación agregada por tipo
   */
  async getGeneracionPorTipo(req, res) {
    try {
      const { hours = 24 } = req.query;

      const sql = `
        SELECT 
          tipo_fuente,
          SUM(generacion_mw) as total_mw,
          AVG(generacion_mw) as promedio_mw,
          COUNT(*) as registros
        FROM generacion
        WHERE fecha_hora >= datetime('now', '-${hours} hours')
        GROUP BY tipo_fuente
        ORDER BY total_mw DESC
      `;

      const datos = dbManager.query(sql);

      res.json({
        success: true,
        period_hours: hours,
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
   * Obtener transmisión
   */
  async getTransmision(req, res) {
    try {
      const { limit = 100 } = req.query;
      const datos = dbManager.getLatest('transmision', parseInt(limit));

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
   * Obtener precios de bolsa
   */
  async getPrecios(req, res) {
    try {
      const { limit = 100, start, end } = req.query;

      let datos;
      if (start && end) {
        datos = dbManager.getByDateRange('precios_bolsa', start, end);
      } else {
        datos = dbManager.getLatest('precios_bolsa', parseInt(limit));
      }

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
   * Obtener restricciones
   */
  async getRestricciones(req, res) {
    try {
      const { limit = 100, estado } = req.query;

      let sql = 'SELECT * FROM restricciones';
      const params = [];

      if (estado) {
        sql += ' WHERE estado = ?';
        params.push(estado);
      }

      sql += ' ORDER BY fecha_hora DESC LIMIT ?';
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
   * Obtener pérdidas
   */
  async getPerdidas(req, res) {
    try {
      const { limit = 100 } = req.query;
      const datos = dbManager.getLatest('perdidas', parseInt(limit), 'fecha DESC');

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
   * Obtener comercialización
   */
  async getComercializacion(req, res) {
    try {
      const { limit = 100 } = req.query;
      const datos = dbManager.getLatest('comercializacion', parseInt(limit));

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
   * Obtener distribución
   */
  async getDistribucion(req, res) {
    try {
      const { limit = 100, empresa } = req.query;

      let sql = 'SELECT * FROM distribucion';
      const params = [];

      if (empresa) {
        sql += ' WHERE empresa = ?';
        params.push(empresa);
      }

      sql += ' ORDER BY fecha DESC LIMIT ?';
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
   * Obtener Costo Unitario (CU)
   */
  async getCostoUnitario(req, res) {
    try {
      const { limit = 30 } = req.query;
      const datos = dbManager.getLatest('costo_unitario', parseInt(limit), 'fecha DESC');

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
   * Obtener alertas activas
   */
  async getAlertas(req, res) {
    try {
      const { estado = 'activa', limit = 50 } = req.query;

      const sql = `
        SELECT * FROM alertas 
        WHERE estado = ? 
        ORDER BY fecha_hora DESC 
        LIMIT ?
      `;

      const datos = dbManager.query(sql, [estado, parseInt(limit)]);

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
   * Obtener resumen general del sistema
   */
  async getResumenGeneral(req, res) {
    try {
      const resumen = {
        demanda: {
          actual: dbManager.queryOne('SELECT demanda_mw FROM demanda ORDER BY fecha_hora DESC LIMIT 1'),
          promedio_24h: dbManager.queryOne(`
            SELECT AVG(demanda_mw) as promedio 
            FROM demanda 
            WHERE fecha_hora >= datetime('now', '-24 hours')
          `),
          max_24h: dbManager.queryOne(`
            SELECT MAX(demanda_mw) as maximo 
            FROM demanda 
            WHERE fecha_hora >= datetime('now', '-24 hours')
          `)
        },
        generacion: {
          por_tipo: dbManager.query(`
            SELECT tipo_fuente, SUM(generacion_mw) as total
            FROM generacion
            WHERE fecha_hora >= datetime('now', '-1 hour')
            GROUP BY tipo_fuente
          `),
          total: dbManager.queryOne(`
            SELECT SUM(generacion_mw) as total
            FROM generacion
            WHERE fecha_hora >= datetime('now', '-1 hour')
          `)
        },
        precios: {
          actual: dbManager.queryOne('SELECT precio_bolsa_cop_kwh FROM precios_bolsa ORDER BY fecha_hora DESC LIMIT 1'),
          promedio_24h: dbManager.queryOne(`
            SELECT AVG(precio_bolsa_cop_kwh) as promedio 
            FROM precios_bolsa 
            WHERE fecha_hora >= datetime('now', '-24 hours')
          `)
        },
        restricciones: {
          activas: dbManager.queryOne(`SELECT COUNT(*) as total FROM restricciones WHERE estado = 'activa'`),
          costo_24h: dbManager.queryOne(`
            SELECT SUM(costo_restriccion_cop) as total 
            FROM restricciones 
            WHERE fecha_hora >= datetime('now', '-24 hours')
          `)
        },
        alertas: {
          activas: dbManager.queryOne(`SELECT COUNT(*) as total FROM alertas WHERE estado = 'activa'`)
        },
        timestamp: new Date().toISOString()
      };

      res.json({
        success: true,
        data: resumen
      });
    } catch (error) {
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  }
}

export default new DataController();

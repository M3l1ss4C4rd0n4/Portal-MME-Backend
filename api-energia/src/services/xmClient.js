/**
 * Cliente para APIs de XM (eXpertos en Mercados)
 * Endpoints públicos del Sistema Interconectado Nacional (SIN)
 */
import axios from 'axios';
import config from '../config/index.js';

class XMClient {
  constructor() {
    this.client = axios.create({
      baseURL: config.xm.baseUrl,
      timeout: config.xm.timeout,
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'API-Energia-MME/1.0'
      }
    });
  }

  /**
   * Obtener demanda en tiempo real
   */
  async getDemandaRealTime() {
    try {
      // XM Endpoint: Demanda tiempo real
      const response = await this.client.get('/consumos/demanda/DemandaTiempoReal');
      
      if (response.data && response.data.DemandaTiempoReal) {
        return response.data.DemandaTiempoReal.map(item => ({
          fecha_hora: item.Fecha,
          demanda_mw: parseFloat(item.Demanda || 0),
          demanda_comercial_mw: parseFloat(item.DemandaComercial || 0),
          region: item.Region || 'SIN'
        }));
      }
      
      return [];
    } catch (error) {
      console.error('❌ Error obteniendo demanda XM:', error.message);
      return [];
    }
  }

  /**
   * Obtener generación por tipo de fuente
   */
  async getGeneracionPorTipo() {
    try {
      const response = await this.client.get('/generacion/GeneracionPorTipo');
      
      if (response.data && response.data.GeneracionPorTipo) {
        return response.data.GeneracionPorTipo.map(item => ({
          fecha_hora: item.Fecha,
          tipo_fuente: item.TipoFuente || 'DESCONOCIDO',
          recurso: item.Recurso,
          generacion_mw: parseFloat(item.GeneracionReal || 0),
          capacidad_efectiva_mw: parseFloat(item.CapacidadEfectiva || 0),
          empresa: item.Empresa
        }));
      }
      
      return [];
    } catch (error) {
      console.error('❌ Error obteniendo generación XM:', error.message);
      return [];
    }
  }

  /**
   * Obtener precios de bolsa
   */
  async getPreciosBolsa() {
    try {
      const response = await this.client.get('/costos/PreciosBolsa');
      
      if (response.data && response.data.PreciosBolsa) {
        return response.data.PreciosBolsa.map(item => ({
          fecha_hora: item.Fecha,
          precio_bolsa_cop_kwh: parseFloat(item.PrecioBolsa || 0),
          precio_escasez_cop_kwh: parseFloat(item.PrecioEscasez || 0)
        }));
      }
      
      return [];
    } catch (error) {
      console.error('❌ Error obteniendo precios XM:', error.message);
      return [];
    }
  }

  /**
   * Obtener restricciones del sistema
   */
  async getRestricciones() {
    try {
      const response = await this.client.get('/restricciones/RestriccionesSIN');
      
      if (response.data && response.data.Restricciones) {
        return response.data.Restricciones.map(item => ({
          fecha_hora: item.Fecha,
          tipo_restriccion: item.TipoRestriccion,
          elemento_afectado: item.Elemento,
          causa: item.Causa,
          costo_restriccion_cop: parseFloat(item.Costo || 0),
          energia_restringida_mwh: parseFloat(item.EnergiaRestringida || 0),
          region: item.Region,
          estado: item.Estado || 'activa'
        }));
      }
      
      return [];
    } catch (error) {
      console.error('❌ Error obteniendo restricciones XM:', error.message);
      return [];
    }
  }

  /**
   * Obtener información de transmisión
   */
  async getTransmision() {
    try {
      const response = await this.client.get('/transmision/EstadoSTN');
      
      if (response.data && response.data.Transmision) {
        return response.data.Transmision.map(item => ({
          fecha_hora: item.Fecha,
          elemento: item.Elemento,
          tipo_elemento: item.Tipo,
          voltaje_kv: parseFloat(item.Voltaje || 0),
          carga_mw: parseFloat(item.Carga || 0),
          capacidad_mw: parseFloat(item.Capacidad || 0),
          utilizacion_pct: parseFloat(item.Utilizacion || 0),
          estado: item.Estado || 'normal',
          empresa: item.Propietario
        }));
      }
      
      return [];
    } catch (error) {
      console.error('❌ Error obteniendo transmisión XM:', error.message);
      return [];
    }
  }

  /**
   * Método genérico para cualquier endpoint de XM
   */
  async fetchData(endpoint) {
    try {
      const response = await this.client.get(endpoint);
      return response.data;
    } catch (error) {
      console.error(`❌ Error en endpoint ${endpoint}:`, error.message);
      return null;
    }
  }
}

export default new XMClient();

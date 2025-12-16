/**
 * Cron Jobs - Actualización automática de datos
 */
import cron from 'node-cron';
import xmClient from './xmClient.js';
import dbManager from '../db/database.js';
import aiAgent from './aiAgent.js';
import config from '../config/index.js';

class CronJobs {
  /**
   * Inicializar todos los cron jobs
   */
  start() {
    console.log('🕐 Iniciando Cron Jobs...');

    // Actualizar demanda cada 5 minutos
    cron.schedule(config.cron.demanda, async () => {
      await this.actualizarDemanda();
    });

    // Actualizar generación cada 5 minutos
    cron.schedule(config.cron.generacion, async () => {
      await this.actualizarGeneracion();
    });

    // Actualizar transmisión cada 10 minutos
    cron.schedule(config.cron.transmision, async () => {
      await this.actualizarTransmision();
    });

    // Actualizar precios cada 15 minutos
    cron.schedule(config.cron.precios, async () => {
      await this.actualizarPrecios();
      await this.actualizarRestricciones();
    });

    // Detectar anomalías cada hora
    cron.schedule('0 * * * *', async () => {
      await this.detectarAnomalias();
    });

    // Limpiar datos antiguos cada día a las 3 AM
    cron.schedule('0 3 * * *', async () => {
      await this.limpiarDatosAntiguos();
    });

    console.log('✅ Cron Jobs activos');
  }

  /**
   * Actualizar demanda desde XM
   */
  async actualizarDemanda() {
    try {
      console.log('📊 Actualizando demanda...');
      const datos = await xmClient.getDemandaRealTime();
      
      if (datos && datos.length > 0) {
        const insertados = dbManager.insertMany('demanda', datos);
        console.log(`✅ Demanda: ${insertados} nuevos registros`);
      }
    } catch (error) {
      console.error('❌ Error actualizando demanda:', error.message);
    }
  }

  /**
   * Actualizar generación desde XM
   */
  async actualizarGeneracion() {
    try {
      console.log('⚡ Actualizando generación...');
      const datos = await xmClient.getGeneracionPorTipo();
      
      if (datos && datos.length > 0) {
        const insertados = dbManager.insertMany('generacion', datos);
        console.log(`✅ Generación: ${insertados} nuevos registros`);
      }
    } catch (error) {
      console.error('❌ Error actualizando generación:', error.message);
    }
  }

  /**
   * Actualizar transmisión desde XM
   */
  async actualizarTransmision() {
    try {
      console.log('🔌 Actualizando transmisión...');
      const datos = await xmClient.getTransmision();
      
      if (datos && datos.length > 0) {
        const insertados = dbManager.insertMany('transmision', datos);
        console.log(`✅ Transmisión: ${insertados} nuevos registros`);
      }
    } catch (error) {
      console.error('❌ Error actualizando transmisión:', error.message);
    }
  }

  /**
   * Actualizar precios desde XM
   */
  async actualizarPrecios() {
    try {
      console.log('💰 Actualizando precios...');
      const datos = await xmClient.getPreciosBolsa();
      
      if (datos && datos.length > 0) {
        const insertados = dbManager.insertMany('precios_bolsa', datos);
        console.log(`✅ Precios: ${insertados} nuevos registros`);
      }
    } catch (error) {
      console.error('❌ Error actualizando precios:', error.message);
    }
  }

  /**
   * Actualizar restricciones desde XM
   */
  async actualizarRestricciones() {
    try {
      console.log('⚠️  Actualizando restricciones...');
      const datos = await xmClient.getRestricciones();
      
      if (datos && datos.length > 0) {
        const insertados = dbManager.insertMany('restricciones', datos);
        console.log(`✅ Restricciones: ${insertados} nuevos registros`);
      }
    } catch (error) {
      console.error('❌ Error actualizando restricciones:', error.message);
    }
  }

  /**
   * Detectar anomalías con IA
   */
  async detectarAnomalias() {
    try {
      console.log('🔍 Detectando anomalías...');
      const resultado = await aiAgent.detectarAnomalias();
      
      if (resultado.success) {
        // Parsear respuesta y guardar alertas si es necesario
        console.log('✅ Análisis de anomalías completado');
      }
    } catch (error) {
      console.error('❌ Error detectando anomalías:', error.message);
    }
  }

  /**
   * Limpiar datos antiguos (mantener últimos 90 días)
   */
  async limpiarDatosAntiguos() {
    try {
      console.log('🧹 Limpiando datos antiguos...');
      
      const tablas = [
        'demanda',
        'generacion',
        'transmision',
        'precios_bolsa',
        'restricciones',
        'comercializacion',
        'perdidas'
      ];

      for (const tabla of tablas) {
        dbManager.cleanOldData(tabla, 90);
      }

      console.log('✅ Limpieza completada');
    } catch (error) {
      console.error('❌ Error en limpieza:', error.message);
    }
  }

  /**
   * Ejecutar actualización manual de todos los datos
   */
  async actualizarTodo() {
    console.log('🔄 Actualización manual completa iniciada...');
    
    await this.actualizarDemanda();
    await this.actualizarGeneracion();
    await this.actualizarTransmision();
    await this.actualizarPrecios();
    await this.actualizarRestricciones();
    
    console.log('✅ Actualización manual completada');
  }
}

export default new CronJobs();

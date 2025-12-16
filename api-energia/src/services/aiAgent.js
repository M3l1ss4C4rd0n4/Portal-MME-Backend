/**
 * Agente de IA - Analista del Sector Energético Colombiano
 * Usa DeepSeek vía OpenRouter
 */
import OpenAI from 'openai';
import config from '../config/index.js';
import dbManager from '../db/database.js';

class AIAgent {
  constructor() {
    if (!config.ai.apiKey) {
      console.warn('⚠️  OPENROUTER_API_KEY no configurada. El agente IA no funcionará.');
      this.client = null;
      return;
    }

    this.client = new OpenAI({
      apiKey: config.ai.apiKey,
      baseURL: config.ai.baseUrl
    });

    this.systemPrompt = `Eres un analista experto del sector energético colombiano.

Tu especialización incluye:
- Regulación de la CREG (Comisión de Regulación de Energía y Gas)
- Sistema Interconectado Nacional (SIN) operado por XM
- Cálculo y análisis del Costo Unitario (CU) y sus componentes:
  * G: Generación (contratos + bolsa)
  * T: Transmisión (STN)
  * D: Distribución (SDL/STR)
  * Cv: Comercialización variable
  * R: Restricciones
  * PR: Pérdidas reconocidas
- Mercado mayorista de energía
- Bolsa de energía (precios spot)
- Generación por tecnología (hidráulica, térmica, eólica, solar, biomasa)
- Transmisión (líneas, subestaciones, STN)
- Distribución (indicadores SAIDI, SAIFI, FMIK)
- Demanda nacional y regional
- Pérdidas técnicas y no técnicas
- Calidad del servicio
- Proyecciones y tendencias

Debes responder de forma:
- Técnica pero clara
- Con datos específicos cuando los tengas
- Identificando riesgos y oportunidades
- Dando recomendaciones accionables
- Citando fuentes (CREG, XM, MME) cuando sea relevante

Si no tienes datos suficientes, indícalo claramente y sugiere qué información se necesita.`;
  }

  /**
   * Analizar pregunta con contexto de datos
   */
  async analizar(pregunta, contexto = null) {
    if (!this.client) {
      return {
        success: false,
        error: 'Agente IA no configurado. Verifica OPENROUTER_API_KEY.'
      };
    }

    const startTime = Date.now();

    try {
      // Obtener contexto de datos si no se proporciona
      const datosContexto = contexto || await this.obtenerContextoDatos();

      // Construir prompt con contexto
      const promptConContexto = this.construirPrompt(pregunta, datosContexto);

      // Llamar a DeepSeek
      const completion = await this.client.chat.completions.create({
        model: config.ai.model,
        messages: [
          { role: 'system', content: this.systemPrompt },
          { role: 'user', content: promptConContexto }
        ],
        temperature: config.ai.temperature,
        max_tokens: config.ai.maxTokens,
        stream: false
      });

      const respuesta = completion.choices[0]?.message?.content || 'Sin respuesta';
      const tiempoRespuesta = Date.now() - startTime;

      // Guardar análisis en BD
      await this.guardarAnalisis({
        pregunta,
        respuesta,
        contexto_datos: JSON.stringify(datosContexto),
        modelo_ia: config.ai.model,
        tokens_usados: completion.usage?.total_tokens || 0,
        tiempo_respuesta_ms: tiempoRespuesta
      });

      return {
        success: true,
        respuesta,
        tokens: completion.usage?.total_tokens || 0,
        tiempo_ms: tiempoRespuesta
      };

    } catch (error) {
      console.error('❌ Error en agente IA:', error.message);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Generar resumen ejecutivo del dashboard
   */
  async generarResumenEjecutivo() {
    const datosContexto = await this.obtenerContextoDatos();

    const pregunta = `Genera un resumen ejecutivo completo del estado actual del Sistema Interconectado Nacional (SIN) de Colombia.

Incluye:
1. Estado general del sistema
2. Indicadores clave (demanda, generación, precios)
3. Tendencias importantes
4. Riesgos identificados
5. Anomalías detectadas
6. Recomendaciones prioritarias

Formato: Profesional, conciso, accionable.`;

    return await this.analizar(pregunta, datosContexto);
  }

  /**
   * Detectar anomalías en los datos
   */
  async detectarAnomalias() {
    const datosContexto = await this.obtenerContextoDatos();

    const pregunta = `Analiza los datos recientes del SIN y detecta posibles anomalías o comportamientos inusuales.

Busca específicamente:
- Picos o caídas inusuales en demanda
- Variaciones atípicas en generación
- Precios de bolsa fuera de rangos normales
- Restricciones excesivas
- Pérdidas anormalmente altas
- Problemas de calidad del servicio

Para cada anomalía detectada, indica:
- Severidad (crítica/alta/media/baja)
- Componente afectado
- Impacto potencial
- Recomendación de acción`;

    return await this.analizar(pregunta, datosContexto);
  }

  /**
   * Proyectar demanda futura
   */
  async proyectarDemanda(horizonte = '24 horas') {
    const datosContexto = await this.obtenerContextoDatos();

    const pregunta = `Con base en los datos históricos recientes, proyecta la demanda de energía para las próximas ${horizonte}.

Considera:
- Patrones históricos
- Día de la semana
- Temporada del año
- Tendencias recientes

Entrega:
- Proyección numérica (MW)
- Rango de confianza
- Factores de riesgo
- Recomendaciones operativas`;

    return await this.analizar(pregunta, datosContexto);
  }

  /**
   * Analizar componentes del CU
   */
  async analizarCU() {
    const datosContexto = await this.obtenerContextoDatos();

    const pregunta = `Analiza los componentes del Costo Unitario (CU) actual:

Componentes del CU:
- G (Generación)
- T (Transmisión)
- D (Distribución)
- Cv (Comercialización variable)
- R (Restricciones)
- PR (Pérdidas reconocidas)

Indica:
1. Valor actual de cada componente
2. Tendencia (aumentando/estable/disminuyendo)
3. Componente con mayor impacto
4. Causas de variaciones
5. Proyección del CU total
6. Recomendaciones de optimización`;

    return await this.analizar(pregunta, datosContexto);
  }

  /**
   * Obtener contexto de datos de la BD
   */
  async obtenerContextoDatos() {
    const contexto = {
      fecha_analisis: new Date().toISOString(),
      demanda: {
        ultima: dbManager.getLatest('demanda', 1)[0] || null,
        promedio_24h: this.calcularPromedio('demanda', 'demanda_mw', 24),
        max_24h: this.calcularMax('demanda', 'demanda_mw', 24),
        min_24h: this.calcularMin('demanda', 'demanda_mw', 24)
      },
      generacion: {
        por_tipo: this.obtenerGeneracionPorTipo(),
        total_actual: this.calcularSuma('generacion', 'generacion_mw', 1)
      },
      precios: {
        bolsa_actual: dbManager.getLatest('precios_bolsa', 1)[0] || null,
        promedio_24h: this.calcularPromedio('precios_bolsa', 'precio_bolsa_cop_kwh', 24)
      },
      restricciones: {
        activas: this.contarRestriccionesActivas(),
        costo_total_24h: this.calcularSuma('restricciones', 'costo_restriccion_cop', 24)
      },
      transmision: {
        elementos: dbManager.getLatest('transmision', 5)
      },
      alertas: {
        activas: this.obtenerAlertasActivas()
      }
    };

    return contexto;
  }

  /**
   * Construir prompt con contexto
   */
  construirPrompt(pregunta, contexto) {
    return `PREGUNTA: ${pregunta}

DATOS DISPONIBLES:
${JSON.stringify(contexto, null, 2)}

Analiza los datos y responde la pregunta de forma clara y fundamentada.`;
  }

  /**
   * Guardar análisis en BD
   */
  async guardarAnalisis(data) {
    try {
      dbManager.insertOrIgnore('analisis_ia', {
        tipo_analisis: this.extraerTipoAnalisis(data.pregunta),
        ...data
      });
    } catch (error) {
      console.error('❌ Error guardando análisis:', error.message);
    }
  }

  /**
   * Utilidades de cálculo
   */
  calcularPromedio(table, column, hours) {
    const sql = `
      SELECT AVG(${column}) as promedio 
      FROM ${table} 
      WHERE fecha_hora >= datetime('now', '-${hours} hours')
    `;
    const result = dbManager.queryOne(sql);
    return result?.promedio || 0;
  }

  calcularMax(table, column, hours) {
    const sql = `
      SELECT MAX(${column}) as maximo 
      FROM ${table} 
      WHERE fecha_hora >= datetime('now', '-${hours} hours')
    `;
    const result = dbManager.queryOne(sql);
    return result?.maximo || 0;
  }

  calcularMin(table, column, hours) {
    const sql = `
      SELECT MIN(${column}) as minimo 
      FROM ${table} 
      WHERE fecha_hora >= datetime('now', '-${hours} hours')
    `;
    const result = dbManager.queryOne(sql);
    return result?.minimo || 0;
  }

  calcularSuma(table, column, hours) {
    const sql = `
      SELECT SUM(${column}) as suma 
      FROM ${table} 
      WHERE fecha_hora >= datetime('now', '-${hours} hours')
    `;
    const result = dbManager.queryOne(sql);
    return result?.suma || 0;
  }

  obtenerGeneracionPorTipo() {
    const sql = `
      SELECT tipo_fuente, SUM(generacion_mw) as total
      FROM generacion
      WHERE fecha_hora >= datetime('now', '-1 hour')
      GROUP BY tipo_fuente
    `;
    return dbManager.query(sql);
  }

  contarRestriccionesActivas() {
    const sql = `SELECT COUNT(*) as total FROM restricciones WHERE estado = 'activa'`;
    const result = dbManager.queryOne(sql);
    return result?.total || 0;
  }

  obtenerAlertasActivas() {
    return dbManager.query(`SELECT * FROM alertas WHERE estado = 'activa' ORDER BY fecha_hora DESC LIMIT 5`);
  }

  extraerTipoAnalisis(pregunta) {
    const tipos = {
      'demanda': /demanda|consumo/i,
      'generacion': /generaci[oó]n|producci[oó]n/i,
      'precios': /precio|costo|cu|bolsa/i,
      'restricciones': /restricci[oó]n|contingencia/i,
      'anomalias': /anomal[ií]a|problema|alerta/i,
      'proyeccion': /proyecci[oó]n|pron[oó]stico|predicci[oó]n/i,
      'resumen': /resumen|estado|situaci[oó]n/i
    };

    for (const [tipo, regex] of Object.entries(tipos)) {
      if (regex.test(pregunta)) return tipo;
    }

    return 'general';
  }
}

export default new AIAgent();

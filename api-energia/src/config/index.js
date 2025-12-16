/**
 * Configuración centralizada de la aplicación
 */
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config();

export default {
  // Servidor
  nodeEnv: process.env.NODE_ENV || 'development',
  port: parseInt(process.env.PORT || '3000', 10),
  
  // Base de datos
  database: {
    path: process.env.DB_PATH || path.join(__dirname, '../db/energia.db')
  },
  
  // APIs externas
  xm: {
    baseUrl: process.env.XM_BASE_URL || 'https://www.xm.com.co/ws',
    timeout: 30000
  },
  
  // OpenRouter + DeepSeek
  ai: {
    apiKey: process.env.OPENROUTER_API_KEY,
    baseUrl: process.env.OPENROUTER_BASE_URL || 'https://openrouter.ai/api/v1',
    model: process.env.AI_MODEL || 'tngtech/deepseek-r1t2-chimera:free',
    maxTokens: parseInt(process.env.AI_MAX_TOKENS || '4000', 10),
    temperature: parseFloat(process.env.AI_TEMPERATURE || '0.7')
  },
  
  // Cron jobs
  cron: {
    demanda: process.env.CRON_DEMANDA || '*/5 * * * *',
    generacion: process.env.CRON_GENERACION || '*/5 * * * *',
    transmision: process.env.CRON_TRANSMISION || '*/10 * * * *',
    precios: process.env.CRON_PRECIOS || '*/15 * * * *'
  },
  
  // Logs
  logging: {
    level: process.env.LOG_LEVEL || 'info',
    file: process.env.LOG_FILE || './logs/api.log'
  },
  
  // CORS
  cors: {
    origins: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:8050']
  },
  
  // Rate limiting
  rateLimit: {
    windowMs: parseInt(process.env.RATE_LIMIT_WINDOW || '15', 10) * 60 * 1000,
    max: parseInt(process.env.RATE_LIMIT_MAX_REQUESTS || '100', 10)
  }
};

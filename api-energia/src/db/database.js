/**
 * Manejador de Base de Datos SQLite
 */
import Database from 'better-sqlite3';
import config from '../config/index.js';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

class DatabaseManager {
  constructor() {
    this.db = null;
  }

  /**
   * Inicializar conexión a la base de datos
   */
  init() {
    try {
      // Crear directorio si no existe
      const dbDir = path.dirname(config.database.path);
      if (!fs.existsSync(dbDir)) {
        fs.mkdirSync(dbDir, { recursive: true });
      }

      // Conectar a SQLite
      this.db = new Database(config.database.path, {
        verbose: config.nodeEnv === 'development' ? console.log : null
      });

      // Configuración óptima
      this.db.pragma('journal_mode = WAL');
      this.db.pragma('synchronous = NORMAL');
      this.db.pragma('foreign_keys = ON');

      console.log(`✅ Base de datos conectada: ${config.database.path}`);
      
      // Crear tablas si no existen
      this.createTables();
      
      return this.db;
    } catch (error) {
      console.error('❌ Error al conectar con la base de datos:', error);
      throw error;
    }
  }

  /**
   * Crear todas las tablas
   */
  createTables() {
    try {
      const schemaPath = path.join(__dirname, '../../scripts/schema.sql');
      const schema = fs.readFileSync(schemaPath, 'utf-8');
      
      this.db.exec(schema);
      console.log('✅ Tablas creadas/verificadas correctamente');
    } catch (error) {
      console.error('❌ Error creando tablas:', error);
      throw error;
    }
  }

  /**
   * Insertar datos evitando duplicados
   */
  insertOrIgnore(table, data) {
    try {
      const columns = Object.keys(data).join(', ');
      const placeholders = Object.keys(data).map(() => '?').join(', ');
      const values = Object.values(data);

      const query = `INSERT OR IGNORE INTO ${table} (${columns}) VALUES (${placeholders})`;
      const stmt = this.db.prepare(query);
      const result = stmt.run(...values);

      return result.changes > 0;
    } catch (error) {
      console.error(`❌ Error insertando en ${table}:`, error.message);
      return false;
    }
  }

  /**
   * Insertar múltiples registros en transacción
   */
  insertMany(table, dataArray) {
    if (!dataArray || dataArray.length === 0) return 0;

    let inserted = 0;
    const insert = this.db.transaction((records) => {
      for (const data of records) {
        if (this.insertOrIgnore(table, data)) {
          inserted++;
        }
      }
    });

    try {
      insert(dataArray);
      return inserted;
    } catch (error) {
      console.error(`❌ Error en transacción para ${table}:`, error);
      return 0;
    }
  }

  /**
   * Consulta genérica
   */
  query(sql, params = []) {
    try {
      const stmt = this.db.prepare(sql);
      return stmt.all(...params);
    } catch (error) {
      console.error('❌ Error en consulta:', error.message);
      return [];
    }
  }

  /**
   * Obtener un solo registro
   */
  queryOne(sql, params = []) {
    try {
      const stmt = this.db.prepare(sql);
      return stmt.get(...params);
    } catch (error) {
      console.error('❌ Error en consulta:', error.message);
      return null;
    }
  }

  /**
   * Obtener últimos N registros de una tabla
   */
  getLatest(table, limit = 100, orderBy = 'fecha_hora DESC') {
    const sql = `SELECT * FROM ${table} ORDER BY ${orderBy} LIMIT ?`;
    return this.query(sql, [limit]);
  }

  /**
   * Obtener datos en rango de fechas
   */
  getByDateRange(table, startDate, endDate, dateColumn = 'fecha_hora') {
    const sql = `
      SELECT * FROM ${table} 
      WHERE ${dateColumn} BETWEEN ? AND ? 
      ORDER BY ${dateColumn} DESC
    `;
    return this.query(sql, [startDate, endDate]);
  }

  /**
   * Obtener estadísticas agregadas
   */
  getStats(table, column, groupBy = null) {
    let sql = `
      SELECT 
        COUNT(*) as count,
        AVG(${column}) as avg,
        MIN(${column}) as min,
        MAX(${column}) as max,
        SUM(${column}) as sum
      FROM ${table}
    `;
    
    if (groupBy) {
      sql += ` GROUP BY ${groupBy}`;
    }

    return this.query(sql);
  }

  /**
   * Limpiar datos antiguos
   */
  cleanOldData(table, daysToKeep = 90, dateColumn = 'fecha_hora') {
    const sql = `
      DELETE FROM ${table} 
      WHERE ${dateColumn} < datetime('now', '-${daysToKeep} days')
    `;
    const stmt = this.db.prepare(sql);
    const result = stmt.run();
    
    console.log(`🧹 Limpieza ${table}: ${result.changes} registros eliminados`);
    return result.changes;
  }

  /**
   * Cerrar conexión
   */
  close() {
    if (this.db) {
      this.db.close();
      console.log('✅ Base de datos cerrada');
    }
  }
}

// Exportar singleton
const dbManager = new DatabaseManager();
export default dbManager;

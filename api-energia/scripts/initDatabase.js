/**
 * Script de Inicialización de Base de Datos
 */
import dbManager from '../src/db/database.js';

console.log('🗄️  Inicializando base de datos...');
console.log('');

try {
  // Inicializar BD y crear tablas
  dbManager.init();
  
  console.log('');
  console.log('✅ Base de datos inicializada correctamente');
  console.log(`📁 Ubicación: ${dbManager.db.name}`);
  console.log('');
  
  // Verificar tablas creadas
  const tablas = dbManager.query(`
    SELECT name FROM sqlite_master 
    WHERE type='table' 
    ORDER BY name
  `);
  
  console.log('📋 Tablas creadas:');
  tablas.forEach(t => {
    console.log(`   - ${t.name}`);
  });
  
  console.log('');
  console.log('✅ Sistema listo para recibir datos');
  
  dbManager.close();
  process.exit(0);
  
} catch (error) {
  console.error('❌ Error:', error.message);
  process.exit(1);
}

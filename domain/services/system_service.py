"""
╔══════════════════════════════════════════════════════════════╗
║               ENDPOINT DE HEALTH CHECK                       ║
║                                                              ║
║  Endpoint para monitorear la salud del sistema ETL-PostgreSQL
║  Verifica: PostgreSQL disponible, datos actualizados, sin errores
╚══════════════════════════════════════════════════════════════╝
"""

import psycopg2
from datetime import datetime, timedelta
from typing import Dict, Any
from core.config import settings

def verificar_salud_sistema() -> Dict[str, Any]:
    """
    Verifica la salud del sistema completo conectándose a PostgreSQL
    
    Returns:
        Dict con status, checks individuales y mensaje
    """
    resultado = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'checks': {},
        'warnings': [],
        'errors': []
    }
    
    try:
        # 1. Verificar conexión a PostgreSQL
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD
        )
        cursor = conn.cursor()
        
        resultado['checks']['database_connection'] = True
        
        # 2. Verificar tamaño de la base de datos PostgreSQL
        cursor.execute("""
            SELECT pg_size_pretty(pg_database_size(current_database())) as size,
                   pg_database_size(current_database()) as size_bytes
        """)
        row = cursor.fetchone()
        resultado['checks']['database_size'] = row[0]
        
        # 3. Verificar tablas principales
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tablas = [row[0] for row in cursor.fetchall()]
        
        tablas_requeridas = ['metrics', 'catalogos']
        tablas_faltantes = [t for t in tablas_requeridas if t not in tablas]
        
        if tablas_faltantes:
            resultado['errors'].append(f'Tablas faltantes: {tablas_faltantes}')
            resultado['status'] = 'unhealthy'
        
        resultado['checks']['tables_exist'] = len(tablas_faltantes) == 0
        resultado['checks']['tables_found'] = len(tablas)
        
        # 4. Verificar cantidad de registros
        cursor.execute("SELECT COUNT(*) FROM metrics")
        total_registros = cursor.fetchone()[0]
        resultado['checks']['total_records'] = total_registros
        
        if total_registros < 100000:
            resultado['warnings'].append(f'Pocos registros: {total_registros}')
        
        # 5. Verificar frescura de los datos
        cursor.execute("""
            SELECT MAX(fecha) as fecha_max
            FROM metrics
            WHERE metrica = 'Gene' AND entidad = 'Sistema' AND recurso = 'Sistema'
        """)
        
        row = cursor.fetchone()
        if row and row[0]:
            fecha_max = row[0]
            if isinstance(fecha_max, str):
                fecha_max = datetime.strptime(fecha_max, '%Y-%m-%d')
            
            dias_antiguedad = (datetime.now() - fecha_max).days
            
            resultado['checks']['latest_data_date'] = str(fecha_max.date())
            resultado['checks']['data_age_days'] = dias_antiguedad
            
            if dias_antiguedad > 3:
                resultado['warnings'].append(f'Datos desactualizados: {dias_antiguedad} días')
                resultado['status'] = 'degraded'
            elif dias_antiguedad > 7:
                resultado['errors'].append(f'Datos muy desactualizados: {dias_antiguedad} días')
                resultado['status'] = 'unhealthy'
        else:
            resultado['errors'].append('No se encontraron datos de generación')
            resultado['status'] = 'unhealthy'
        
        # 6. Verificar duplicados
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM (
                SELECT metrica, entidad, recurso, fecha
                FROM metrics
                GROUP BY metrica, entidad, recurso, fecha
                HAVING COUNT(*) > 1
            ) sub
        """)
        
        duplicados = cursor.fetchone()[0]
        resultado['checks']['duplicate_records'] = duplicados
        
        if duplicados > 0:
            resultado['warnings'].append(f'Duplicados encontrados: {duplicados}')
        
        # 7. Verificar integridad de métricas críticas
        metricas_criticas = ['Gene', 'DemaCome', 'AporEner']
        metricas_faltantes = []
        
        for metrica in metricas_criticas:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM metrics
                WHERE metrica = %s AND entidad = 'Sistema' AND recurso = 'Sistema'
            """, (metrica,))
            
            count = cursor.fetchone()[0]
            if count == 0:
                metricas_faltantes.append(metrica)
        
        if metricas_faltantes:
            resultado['errors'].append(f'Métricas críticas sin datos: {metricas_faltantes}')
            resultado['status'] = 'unhealthy'
        
        resultado['checks']['critical_metrics_ok'] = len(metricas_faltantes) == 0
        
        conn.close()
        
        # Mensaje resumen
        if resultado['status'] == 'healthy':
            resultado['message'] = '✅ Sistema operando normalmente'
        elif resultado['status'] == 'degraded':
            resultado['message'] = f"⚠️ Sistema con advertencias: {', '.join(resultado['warnings'])}"
        else:
            resultado['message'] = f"❌ Sistema con errores: {', '.join(resultado['errors'])}"
        
    except Exception as e:
        resultado['status'] = 'unhealthy'
        resultado['errors'].append(f'Error al verificar sistema: {str(e)}')
        resultado['message'] = f'❌ Error crítico: {str(e)}'
    
    return resultado


def generar_reporte_texto(salud: Dict[str, Any]) -> str:
    """Genera un reporte legible para humanos"""
    lineas = [
        "="*60,
        "📊 HEALTH CHECK - Portal Energético MME",
        "="*60,
        f"⏰ Timestamp: {salud['timestamp']}",
        f"🏥 Status: {salud['status'].upper()}",
        "",
        "VERIFICACIONES:",
    ]
    
    for check, valor in salud['checks'].items():
        emoji = "✅" if valor else "❌"
        lineas.append(f"  {emoji} {check}: {valor}")
    
    if salud['warnings']:
        lineas.append("")
        lineas.append("⚠️ ADVERTENCIAS:")
        for warning in salud['warnings']:
            lineas.append(f"  - {warning}")
    
    if salud['errors']:
        lineas.append("")
        lineas.append("❌ ERRORES:")
        for error in salud['errors']:
            lineas.append(f"  - {error}")
    
    lineas.append("")
    lineas.append(salud['message'])
    lineas.append("="*60)
    
    return "\n".join(lineas)

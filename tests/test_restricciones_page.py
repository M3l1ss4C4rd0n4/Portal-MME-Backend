#!/usr/bin/env python3
"""
Test básico para verificar que la página de restricciones operativas
carga datos correctamente
"""

import sys
import sqlite3
from datetime import datetime, timedelta

def test_restricciones_data():
    """Verificar que hay datos de restricciones disponibles"""
    print("🔍 Verificando datos de restricciones...")
    
    try:
        conn = sqlite3.connect('/home/admonctrlxm/server/portal_energetico.db')
        cursor = conn.cursor()
        
        # Verificar RestAliv
        cursor.execute("SELECT COUNT(*), MIN(Date), MAX(Date), SUM(Value) FROM RestAliv")
        rest_aliv_count, min_date_aliv, max_date_aliv, total_aliv = cursor.fetchone()
        
        # Verificar RestSinAliv
        cursor.execute("SELECT COUNT(*), MIN(Date), MAX(Date), SUM(Value) FROM RestSinAliv")
        rest_sin_count, min_date_sin, max_date_sin, total_sin = cursor.fetchone()
        
        # Verificar RespComerAGC
        cursor.execute("SELECT COUNT(*), MIN(Date), MAX(Date), SUM(Value) FROM RespComerAGC")
        agc_count, min_date_agc, max_date_agc, total_agc = cursor.fetchone()
        
        conn.close()
        
        print("\n📊 Resultados:")
        print(f"\n1. RestAliv (Restricciones Aliviadas):")
        print(f"   ├─ Registros: {rest_aliv_count:,}")
        print(f"   ├─ Período: {min_date_aliv} a {max_date_aliv}")
        print(f"   └─ Total acumulado: ${total_aliv:,.2f} COP")
        
        print(f"\n2. RestSinAliv (Restricciones Sin Alivio):")
        print(f"   ├─ Registros: {rest_sin_count:,}")
        print(f"   ├─ Período: {min_date_sin} a {max_date_sin}")
        print(f"   └─ Total acumulado: ${total_sin:,.2f} COP")
        
        print(f"\n3. RespComerAGC (Responsabilidad Comercial AGC):")
        print(f"   ├─ Registros: {agc_count:,}")
        print(f"   ├─ Período: {min_date_agc} a {max_date_agc}")
        print(f"   └─ Total acumulado: ${total_agc:,.2f} COP")
        
        print(f"\n4. Total General:")
        total_restricciones = (total_aliv or 0) + (total_sin or 0)
        print(f"   ├─ Restricciones totales: ${total_restricciones:,.2f} COP")
        print(f"   ├─ % Aliviadas: {(total_aliv/total_restricciones*100) if total_restricciones > 0 else 0:.1f}%")
        print(f"   └─ % Sin Alivio: {(total_sin/total_restricciones*100) if total_restricciones > 0 else 0:.1f}%")
        
        # Verificación de éxito
        if rest_aliv_count > 0 or rest_sin_count > 0:
            print("\n✅ ÉXITO: La página de restricciones tiene datos disponibles")
            print(f"📍 URL: http://172.17.0.46:8050/restricciones-operativas")
            return True
        else:
            print("\n❌ ADVERTENCIA: No hay datos disponibles")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_restricciones_data()
    sys.exit(0 if success else 1)

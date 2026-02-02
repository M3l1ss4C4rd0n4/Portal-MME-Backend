#!/usr/bin/env python3
"""
Test de conectividad y calidad de datos de API XM
Verifica que los datos descargados tengan variabilidad esperada
"""
import sys
sys.path.insert(0, '/home/admonctrlxm/server')

from datetime import datetime, timedelta
import pandas as pd

try:
    from infrastructure.external.xm_service import get_objetoAPI
    from infrastructure.database.manager import db_manager
except Exception as e:
    print(f"❌ ERROR al importar módulos: {e}")
    sys.exit(1)

print("="*70)
print("🧪 TEST DE CALIDAD DE DATOS - API XM")
print("="*70)

# Inicializar API
objetoAPI = get_objetoAPI()
if not objetoAPI:
    print("❌ No se pudo inicializar API XM")
    sys.exit(1)

print("✅ API XM inicializada correctamente\n")

# Test 1: Precio Bolsa Nacional (debe variar diariamente)
print("="*70)
print("🧪 TEST 1: Precio Bolsa Nacional (últimos 7 días)")
print("="*70)
start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
end = datetime.now().strftime("%Y-%m-%d")

try:
    df = objetoAPI.request_data('PrecBolsNaci', start, end)
    if df is not None and not df.empty:
        print(f"✅ Registros obtenidos de API: {len(df)}")
        
        # Verificar estructura
        print(f"📊 Columnas: {df.columns.tolist()}")
        
        if 'Values' in df.columns:
            valores_unicos = df['Values'].nunique()
            print(f"📊 Valores únicos: {valores_unicos}")
            print(f"💰 Rango: {df['Values'].min():.2f} - {df['Values'].max():.2f}")
            print(f"📈 Media: {df['Values'].mean():.2f}")
            print(f"📉 Desviación Estándar: {df['Values'].std():.2f}")
            
            print("\nPrimeros 5 registros:")
            print(df.head())
            
            if valores_unicos == 1:
                print("❌ ERROR CRÍTICO: Todos los valores son iguales - API o transformación rota")
            elif valores_unicos < 3:
                print("⚠️ ALERTA: Muy poca variabilidad en precios (menos de 3 valores únicos)")
            else:
                print("✅ Variabilidad normal detectada")
        else:
            print(f"⚠️ Columna 'Values' no encontrada. Columnas disponibles: {df.columns.tolist()}")
    else:
        print("❌ ERROR: No se obtuvieron datos de API")
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Aportes Hídricos
print("\n" + "="*70)
print("🧪 TEST 2: Aportes Hídricos (últimos 7 días)")
print("="*70)
try:
    df_aportes = objetoAPI.request_data('AporEner', start, end)
    if df_aportes is not None and not df_aportes.empty:
        print(f"✅ Registros API: {len(df_aportes)}")
        
        if 'Values' in df_aportes.columns:
            suma_total = df_aportes['Values'].sum()
            print(f"💧 Suma total aportes: {suma_total:.2f} GWh")
            print(f"📊 Promedio diario: {df_aportes['Values'].mean():.2f} GWh")
            
            if suma_total == 0:
                print("❌ ERROR: Aportes suman cero - imposible en Colombia")
            else:
                print("✅ Datos de aportes válidos")
        
        print("\nPrimeras entradas:")
        print(df_aportes.head())
    else:
        print("❌ No se obtuvieron datos")
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Verificar datos en BD vs API
print("\n" + "="*70)
print("🧪 TEST 3: Comparación BD vs API (Precio Bolsa - último día)")
print("="*70)

try:
    # Obtener última fecha en BD
    query = """
    SELECT fecha, valor_gwh 
    FROM metrics 
    WHERE metrica = 'PrecBolsNaci' AND entidad = 'Sistema'
    ORDER BY fecha DESC 
    LIMIT 5
    """
    
    with db_manager.get_connection() as conn:
        df_bd = pd.read_sql_query(query, conn)
    
    print("📊 Últimos 5 registros en BD:")
    print(df_bd)
    
    if len(df_bd) > 0:
        ultima_fecha_bd = df_bd.iloc[0]['fecha']
        valor_bd = df_bd.iloc[0]['valor_gwh']
        
        print(f"\n📅 Última fecha en BD: {ultima_fecha_bd}")
        print(f"💰 Valor en BD: {valor_bd:.2f}")
        
        # Comparar con API
        try:
            df_api = objetoAPI.request_data('PrecBolsNaci', ultima_fecha_bd, ultima_fecha_bd)
            if df_api is not None and not df_api.empty and 'Values' in df_api.columns:
                valor_api = df_api['Values'].iloc[0]
                print(f"💰 Valor en API: {valor_api:.2f}")
                
                diferencia = abs(valor_bd - valor_api)
                if diferencia > 1:
                    print(f"⚠️ ALERTA: Diferencia significativa entre BD y API: {diferencia:.2f}")
                else:
                    print("✅ Valores consistentes entre BD y API")
        except Exception as e:
            print(f"⚠️ No se pudo comparar con API: {e}")
    
except Exception as e:
    print(f"❌ ERROR al consultar BD: {e}")

print("\n" + "="*70)
print("✅ TESTS COMPLETADOS")
print("="*70)

"""
Script de prueba para verificar datos de hidrología
"""
from utils._xm import obtener_datos_inteligente
from datetime import date, timedelta

# Parámetros de prueba
fecha_fin = date.today()
fecha_inicio = fecha_fin - timedelta(days=30)
fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')

print(f"🔍 Probando obtener_datos_inteligente()...")
print(f"   Métrica: AporEner")
print(f"   Entidad: Rio")
print(f"   Fechas: {fecha_inicio_str} a {fecha_fin_str}\n")

# Obtener datos
data, warning = obtener_datos_inteligente('AporEner', 'Rio', fecha_inicio_str, fecha_fin_str)

if warning:
    print(f"⚠️  {warning}\n")

if data is None or data.empty:
    print("❌ No se obtuvieron datos")
else:
    print(f"✅ Datos obtenidos correctamente:")
    print(f"   Registros: {len(data)}")
    print(f"   Columnas: {list(data.columns)}")
    print(f"\n📊 Primeros 10 registros:")
    print(data.head(10))
    
    # Verificar si tiene la columna Name
    if 'Name' in data.columns:
        rios_unicos = data['Name'].nunique()
        print(f"\n🏞️  Ríos únicos: {rios_unicos}")
        print(f"   Ejemplos: {list(data['Name'].unique()[:10])}")
    
    # Verificar valores
    if 'Value' in data.columns:
        print(f"\n💧 Valores:")
        print(f"   Min: {data['Value'].min():.2f} GWh")
        print(f"   Max: {data['Value'].max():.2f} GWh")
        print(f"   Promedio: {data['Value'].mean():.2f} GWh")

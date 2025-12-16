#!/usr/bin/env python3
"""Verificar qué fecha tiene los datos más recientes de aportes"""

from datetime import date, timedelta
from utils._xm import fetch_metric_data

print(f"\n{'='*70}")
print(f"VERIFICACIÓN DE FECHAS DISPONIBLES - APORTES HÍDRICOS")
print(f"{'='*70}")

# Probar últimos 7 días
fecha_base = date.today()

for dias_atras in range(7):
    fecha_prueba = fecha_base - timedelta(days=dias_atras + 1)
    fecha_str = fecha_prueba.strftime('%Y-%m-%d')
    
    # Obtener datos de un solo día
    df = fetch_metric_data('AporEner', 'Sistema', fecha_str, fecha_str)
    
    if df is not None and not df.empty:
        col_value = 'Value' if 'Value' in df.columns else 'Values_code'
        valor = df[col_value].iloc[0] if len(df) > 0 else 0
        
        print(f"\n📅 {fecha_prueba.strftime('%Y-%m-%d')} ({fecha_prueba.strftime('%d de %B')})")
        print(f"   ✅ DATOS DISPONIBLES")
        print(f"   Registros: {len(df)}")
        print(f"   Valor: {valor:.2f} GWh")
        
        # Este es el último día con datos
        print(f"\n{'='*70}")
        print(f"✅ FECHA MÁS RECIENTE CON DATOS: {fecha_prueba.strftime('%d de %B de %Y')}")
        print(f"{'='*70}")
        break
    else:
        print(f"❌ {fecha_prueba.strftime('%Y-%m-%d')} - Sin datos")

# Ahora verificar qué está usando el código actual
print(f"\n{'='*70}")
print(f"LÓGICA DEL CÓDIGO ACTUAL:")
print(f"{'='*70}")

fecha_fin = date.today() - timedelta(days=1)
fecha_inicio_mes = fecha_fin.replace(day=1)

print(f"Hoy: {date.today().strftime('%Y-%m-%d')}")
print(f"fecha_fin = hoy - 1 día = {fecha_fin.strftime('%Y-%m-%d')}")
print(f"fecha_inicio_mes = {fecha_inicio_mes.strftime('%Y-%m-%d')}")
print(f"\nPeríodo consultado: {fecha_inicio_mes.strftime('%Y-%m-%d')} a {fecha_fin.strftime('%Y-%m-%d')}")

# Obtener datos del período
df_aportes = fetch_metric_data('AporEner', 'Sistema', fecha_inicio_mes.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d'))

if df_aportes is not None and not df_aportes.empty:
    print(f"\n📊 Datos obtenidos:")
    print(f"   Registros: {len(df_aportes)}")
    if 'Date' in df_aportes.columns:
        print(f"   Primera fecha: {df_aportes['Date'].min()}")
        print(f"   Última fecha: {df_aportes['Date'].max()}")
        print(f"   Fechas únicas: {df_aportes['Date'].nunique()}")
    
    col_value = 'Value' if 'Value' in df_aportes.columns else 'Values_code'
    promedio = df_aportes[col_value].mean()
    print(f"   Promedio: {promedio:.2f} GWh")

print(f"\n{'='*70}")

#!/usr/bin/env python3
"""Test para verificar cálculo de Aportes vs XM"""

from datetime import date, timedelta
from utils._xm import fetch_metric_data

# Fecha: 10 de noviembre 2024 (según XM)
fecha_fin = date(2024, 11, 10)
fecha_inicio_mes = fecha_fin.replace(day=1)

fecha_inicio_str = fecha_inicio_mes.strftime('%Y-%m-%d')
fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')

print(f"\n{'='*70}")
print(f"VERIFICACIÓN APORTES HÍDRICOS vs XM")
print(f"{'='*70}")
print(f"Período: {fecha_inicio_str} a {fecha_fin_str} ({(fecha_fin - fecha_inicio_mes).days + 1} días)")

# Obtener datos
df_aportes = fetch_metric_data('AporEner', 'Sistema', fecha_inicio_str, fecha_fin_str)
df_media_hist = fetch_metric_data('AporEnerMediHist', 'Sistema', fecha_inicio_str, fecha_fin_str)

if df_aportes is not None and not df_aportes.empty:
    print(f"\n📊 APORTES REALES (AporEner):")
    print(f"   Registros: {len(df_aportes)}")
    print(f"   Columnas: {df_aportes.columns.tolist()}")
    
    col_value = 'Value' if 'Value' in df_aportes.columns else 'Values_code'
    total = df_aportes[col_value].sum()
    promedio = df_aportes[col_value].mean()
    
    print(f"   Total acumulado: {total:.2f} GWh")
    print(f"   Promedio diario: {promedio:.2f} GWh")
    print(f"   Primeros valores: {df_aportes[col_value].head().tolist()}")
    print(f"   Últimos valores: {df_aportes[col_value].tail().tolist()}")

if df_media_hist is not None and not df_media_hist.empty:
    print(f"\n📊 MEDIA HISTÓRICA (AporEnerMediHist):")
    print(f"   Registros: {len(df_media_hist)}")
    
    col_value = 'Value' if 'Value' in df_media_hist.columns else 'Values_code'
    total = df_media_hist[col_value].sum()
    promedio = df_media_hist[col_value].mean()
    
    print(f"   Total acumulado: {total:.2f} GWh")
    print(f"   Promedio diario: {promedio:.2f} GWh")

# Calcular porcentajes con diferentes métodos
if df_aportes is not None and df_media_hist is not None:
    col_ap = 'Value' if 'Value' in df_aportes.columns else 'Values_code'
    col_mh = 'Value' if 'Value' in df_media_hist.columns else 'Values_code'
    
    # Método 1: Total / Total
    total_ap = df_aportes[col_ap].sum()
    total_mh = df_media_hist[col_mh].sum()
    pct_total = (total_ap / total_mh) * 100 if total_mh > 0 else 0
    
    # Método 2: Promedio / Promedio
    prom_ap = df_aportes[col_ap].mean()
    prom_mh = df_media_hist[col_mh].mean()
    pct_promedio = (prom_ap / prom_mh) * 100 if prom_mh > 0 else 0
    
    print(f"\n{'='*70}")
    print(f"COMPARACIÓN CON XM:")
    print(f"{'='*70}")
    print(f"XM muestra: 74.53% - 270.61 GWh")
    print(f"\nMétodo 1 (Total/Total):")
    print(f"   Porcentaje: {pct_total:.2f}%")
    print(f"   GWh mostrados: {total_ap:.2f} GWh")
    print(f"\nMétodo 2 (Promedio/Promedio):")
    print(f"   Porcentaje: {pct_promedio:.2f}%")
    print(f"   GWh mostrados: {prom_ap:.2f} GWh")
    print(f"\n{'='*70}")

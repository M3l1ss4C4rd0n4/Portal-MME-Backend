"""
Script para explorar métricas disponibles en API XM
Enfocado en: Transmisión, Pérdidas y Restricciones

Ejecutar: python3 scripts/explorar_metricas_xm.py
"""
import sys
sys.path.append('/home/admonctrlxm/server')

from datetime import datetime, timedelta
import pandas as pd

# Métricas potenciales de XM agrupadas por categoría
METRICAS_XM = {
    "TRANSMISION": {
        "descripcion": "Métricas del Sistema de Transmisión Nacional (STN)",
        "metricas": [
            # Líneas de transmisión
            ("LineaSTN", "Sistema", "Listado de líneas del STN"),
            ("LineaSTN", "Linea", "Datos por línea específica"),
            
            # Flujos de potencia
            ("FlujoPoten", "Linea", "Flujo de potencia por línea (MW)"),
            ("FlujoPoten", "Sistema", "Flujo total del sistema"),
            
            # Capacidad de transmisión
            ("CapaTrans", "Linea", "Capacidad de transmisión por línea (MW)"),
            ("CapaTrans", "Sistema", "Capacidad total del sistema"),
            
            # Subestaciones
            ("ListadoSubestaciones", "Sistema", "Listado de subestaciones"),
            ("TensSubes", "Subestacion", "Tensión en subestaciones (kV)"),
            
            # Pérdidas en transmisión
            ("PerdidasTrans", "Sistema", "Pérdidas totales en transmisión (MWh)"),
            ("PerdidasTrans", "Linea", "Pérdidas por línea (MWh)"),
            
            # Disponibilidad
            ("DispoLinea", "Linea", "Disponibilidad de líneas (%)"),
            ("DispoSubes", "Subestacion", "Disponibilidad de subestaciones (%)"),
            
            # Congestión
            ("CongesLinea", "Linea", "Congestión en líneas (MW)"),
            ("CongesLinea", "Sistema", "Congestión total del sistema"),
            
            # Eventos
            ("EvenTrans", "Sistema", "Eventos en transmisión"),
            ("EvenTrans", "Linea", "Eventos por línea"),
        ]
    },
    
    "PERDIDAS": {
        "descripcion": "Métricas de Pérdidas de Energía",
        "metricas": [
            # Pérdidas totales
            ("Perdi", "Sistema", "Pérdidas totales del sistema (MWh)"),
            ("PerdiPorcen", "Sistema", "Porcentaje de pérdidas totales (%)"),
            
            # Pérdidas por agente
            ("Perdi", "Agente", "Pérdidas por comercializador/OR (MWh)"),
            ("PerdiPorcen", "Agente", "Porcentaje pérdidas por agente (%)"),
            
            # Pérdidas técnicas vs no técnicas
            ("PerdiTecn", "Sistema", "Pérdidas técnicas (MWh)"),
            ("PerdiNoTecn", "Sistema", "Pérdidas no técnicas (MWh)"),
            ("PerdiTecn", "Agente", "Pérdidas técnicas por agente"),
            ("PerdiNoTecn", "Agente", "Pérdidas no técnicas por agente"),
            
            # Pérdidas en transmisión (ya listadas arriba)
            ("PerdidasTrans", "Sistema", "Pérdidas en transmisión (MWh)"),
            
            # Pérdidas en distribución
            ("PerdiDist", "Sistema", "Pérdidas en distribución (MWh)"),
            ("PerdiDist", "Agente", "Pérdidas por operador de red"),
            
            # Reconocimiento de pérdidas
            ("RecoPerdi", "Sistema", "Reconocimiento de pérdidas (MWh)"),
            ("RecoPerdi", "Agente", "Reconocimiento por agente"),
            
            # Energía asociada a pérdidas
            ("EnerPerdi", "Sistema", "Energía asociada a pérdidas (MWh)"),
            ("EnerPerdi", "Agente", "Energía pérdidas por agente"),
        ]
    },
    
    "RESTRICCIONES": {
        "descripcion": "Métricas de Restricciones Operativas",
        "metricas": [
            # Restricciones operativas
            ("RestOper", "Sistema", "Restricciones operativas totales"),
            ("RestOper", "Recurso", "Restricciones por planta/recurso"),
            
            # Generación de seguridad
            ("GeneSegur", "Sistema", "Generación de seguridad (MWh)"),
            ("GeneSegur", "Recurso", "Generación seguridad por planta"),
            
            # AGC (Control Automático de Generación)
            ("AGC", "Sistema", "AGC del sistema (MW)"),
            ("AGC", "Recurso", "AGC por planta"),
            
            # Restricciones ambientales
            ("RestAmbi", "Sistema", "Restricciones ambientales"),
            ("RestAmbi", "Recurso", "Restricciones ambientales por planta"),
            
            # Restricciones hídricas
            ("RestHidri", "Sistema", "Restricciones hídricas"),
            ("RestHidri", "Embalse", "Restricciones por embalse"),
            
            # Indisponibilidades
            ("IndisRecur", "Sistema", "Indisponibilidades totales (MW)"),
            ("IndisRecur", "Recurso", "Indisponibilidad por planta"),
            ("IndisLinea", "Sistema", "Indisponibilidades de líneas"),
            ("IndisLinea", "Linea", "Indisponibilidad por línea"),
            
            # Racionamiento
            ("Racio", "Sistema", "Racionamiento total (MWh)"),
            ("Racio", "Area", "Racionamiento por área"),
            ("DemaNoAtenProg", "Area", "Demanda no atendida programada"),
            
            # Desviaciones
            ("Desvia", "Sistema", "Desviaciones del sistema"),
            ("Desvia", "Agente", "Desviaciones por agente"),
            
            # Respaldo operativo
            ("RespaOper", "Sistema", "Respaldo operativo (MW)"),
            ("RespaOper", "Recurso", "Respaldo por planta"),
        ]
    },
    
    "MERCADO": {
        "descripcion": "Métricas del Mercado de Energía (complementarias)",
        "metricas": [
            # Precios
            ("PrecBolsNaci", "Sistema", "Precio de bolsa nacional (COP/kWh)"),
            ("PrecBolsNaci", "Recurso", "Precio bolsa por recurso"),
            ("PrecEscasRegu", "Sistema", "Precio escasez de regulación"),
            
            # Liquidación
            ("LiquMerc", "Sistema", "Liquidación del mercado"),
            ("LiquMerc", "Agente", "Liquidación por agente"),
            
            # Reconciliaciones
            ("Recon", "Sistema", "Reconciliaciones del sistema"),
            ("Recon", "Agente", "Reconciliaciones por agente"),
        ]
    }
}


def probar_metrica(metric, entity, dias_atras=7):
    """Probar si una métrica existe y devuelve datos"""
    from utils._xm import get_objetoAPI
    
    objetoAPI = get_objetoAPI()
    if objetoAPI is None:
        print("❌ API XM no disponible")
        return False, None
    
    fecha_fin = datetime.now().date()
    fecha_inicio = fecha_fin - timedelta(days=dias_atras)
    
    try:
        data = objetoAPI.request_data(
            metric, 
            entity, 
            fecha_inicio.strftime('%Y-%m-%d'),
            fecha_fin.strftime('%Y-%m-%d')
        )
        
        if data is not None and not data.empty:
            return True, data
        else:
            return False, None
    except Exception as e:
        return False, str(e)


def explorar_categoria(categoria):
    """Explorar todas las métricas de una categoría"""
    print(f"\n{'='*80}")
    print(f"CATEGORÍA: {categoria}")
    print(f"{'='*80}")
    print(f"Descripción: {METRICAS_XM[categoria]['descripcion']}\n")
    
    resultados = {
        'disponibles': [],
        'no_disponibles': [],
        'errores': []
    }
    
    for metric, entity, descripcion in METRICAS_XM[categoria]['metricas']:
        print(f"🔍 Probando: {metric}/{entity} - {descripcion}...", end=" ")
        
        existe, data = probar_metrica(metric, entity, dias_atras=30)
        
        if existe:
            print(f"✅ DISPONIBLE ({len(data)} registros)")
            resultados['disponibles'].append({
                'metric': metric,
                'entity': entity,
                'descripcion': descripcion,
                'registros': len(data),
                'columnas': list(data.columns) if data is not None else []
            })
        elif data is None:
            print(f"❌ Sin datos")
            resultados['no_disponibles'].append({
                'metric': metric,
                'entity': entity,
                'descripcion': descripcion
            })
        else:
            print(f"⚠️ Error: {data}")
            resultados['errores'].append({
                'metric': metric,
                'entity': entity,
                'descripcion': descripcion,
                'error': data
            })
    
    return resultados


def generar_reporte(categoria, resultados):
    """Generar reporte en Markdown"""
    reporte = f"""# Exploración API XM - {categoria}
**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Resumen
- ✅ **Disponibles:** {len(resultados['disponibles'])}
- ❌ **Sin datos:** {len(resultados['no_disponibles'])}
- ⚠️ **Con errores:** {len(resultados['errores'])}

## Métricas Disponibles ✅

"""
    
    for m in resultados['disponibles']:
        reporte += f"""### {m['metric']} / {m['entity']}
**Descripción:** {m['descripcion']}  
**Registros encontrados:** {m['registros']}  
**Columnas:** {', '.join(m['columnas'])}

"""
    
    reporte += "\n## Métricas Sin Datos ❌\n\n"
    for m in resultados['no_disponibles']:
        reporte += f"- `{m['metric']}` / `{m['entity']}` - {m['descripcion']}\n"
    
    if resultados['errores']:
        reporte += "\n## Métricas Con Errores ⚠️\n\n"
        for m in resultados['errores']:
            reporte += f"- `{m['metric']}` / `{m['entity']}` - {m['descripcion']}\n"
            reporte += f"  Error: `{m['error']}`\n\n"
    
    return reporte


def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Explorar métricas disponibles en API XM')
    parser.add_argument(
        '--categoria',
        choices=['TRANSMISION', 'PERDIDAS', 'RESTRICCIONES', 'MERCADO', 'TODAS'],
        default='TODAS',
        help='Categoría de métricas a explorar'
    )
    parser.add_argument(
        '--output',
        default='/home/admonctrlxm/server/logs/exploracion_metricas_xm.md',
        help='Archivo de salida para el reporte'
    )
    
    args = parser.parse_args()
    
    categorias = list(METRICAS_XM.keys()) if args.categoria == 'TODAS' else [args.categoria]
    
    reporte_completo = f"""# Exploración Completa de Métricas XM
**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Objetivo:** Identificar métricas disponibles para dashboards de Transmisión, Pérdidas y Restricciones

---

"""
    
    for categoria in categorias:
        print(f"\n🔎 Explorando categoría: {categoria}")
        resultados = explorar_categoria(categoria)
        reporte = generar_reporte(categoria, resultados)
        reporte_completo += reporte + "\n---\n\n"
    
    # Guardar reporte
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(reporte_completo)
    
    print(f"\n✅ Reporte guardado en: {args.output}")
    
    # Mostrar resumen
    print("\n" + "="*80)
    print("RESUMEN FINAL")
    print("="*80)
    for categoria in categorias:
        print(f"\n{categoria}:")
        print(f"  ✅ Disponibles: {len([m for m in METRICAS_XM[categoria]['metricas'] if True])}")


if __name__ == '__main__':
    main()

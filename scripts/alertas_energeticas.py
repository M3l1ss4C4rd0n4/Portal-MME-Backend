#!/usr/bin/env python3
"""
SISTEMA DE ALERTAS AUTOMÁTICAS - SECTOR ELÉCTRICO COLOMBIANO
Viceministro de Energía - Alertas Tempranas y Notificaciones

Evalúa predicciones y genera alertas para:
- Riesgo de escasez energética
- Niveles críticos de embalses
- Precios de bolsa anormales
- Desbalance oferta-demanda
- Pérdidas excesivas del sistema

Output: JSON con alertas clasificadas por severidad
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
from datetime import datetime, timedelta
from infrastructure.database.connection import PostgreSQLConnectionManager
import json

# Importar sistema de notificaciones
from scripts.sistema_notificaciones import NotificationService, notificar_alerta

# =============================================================================
# UMBRALES DE ALERTAS (CONFIGURABLES POR POLÍTICA MINISTERIAL)
# =============================================================================

UMBRALES = {
    'DEMANDA': {
        'NORMAL': (180, 230),      # GWh/día
        'ALERTA': (230, 250),       # GWh/día
        'CRITICO': 250              # GWh/día
    },
    'APORTES_HIDRICOS': {
        'NORMAL': (400, 700),       # GWh/día
        'ALERTA': (300, 400),       # GWh/día
        'CRITICO': 300              # GWh/día (sequía severa)
    },
    'EMBALSES': {
        'NORMAL': (25000, 35000),   # GWh
        'ALERTA': (15000, 25000),   # GWh
        'CRITICO': 15000            # GWh (nivel crítico)
    },
    'PRECIO_BOLSA': {
        'NORMAL': (150, 450),       # $/kWh
        'ALERTA': (450, 800),       # $/kWh
        'CRITICO': 800              # $/kWh (mercado stress)
    },
    'PERDIDAS': {
        'NORMAL': (2, 5),           # GWh/día
        'ALERTA': (5, 7),           # GWh/día
        'CRITICO': 7                # GWh/día
    },
    'BALANCE': {
        'NORMAL': 0,                # Superávit > 0
        'ALERTA': -10,              # Déficit leve
        'CRITICO': -50              # Déficit severo (GWh/día)
    }
}


class SistemaAlertasEnergeticas:
    """Sistema de alertas automáticas para sector energético"""
    
    def __init__(self):
        self.alertas = []
        self.conn = self._get_connection()
        self.notification_service = NotificationService()
        print("✅ Sistema de notificaciones inicializado")
        
    def _get_connection(self):
        """Obtiene conexión a PostgreSQL"""
        manager = PostgreSQLConnectionManager()
        conn_params = {
            'host': manager.host,
            'port': manager.port,
            'database': manager.database,
            'user': manager.user
        }
        if manager.password:
            conn_params['password'] = manager.password
        return psycopg2.connect(**conn_params)
    
    def cargar_predicciones(self, fuente, dias=30):
        """Carga predicciones de una fuente específica"""
        query = """
            SELECT fecha_prediccion, valor_gwh_predicho, 
                   intervalo_inferior, intervalo_superior
            FROM predictions
            WHERE fuente = %s
            ORDER BY fecha_prediccion
            LIMIT %s
        """
        
        df = pd.read_sql_query(query, self.conn, params=(fuente, dias))
        return df
    
    def evaluar_demanda(self, horizonte=30):
        """Evalúa riesgo en demanda nacional"""
        print("📊 Evaluando DEMANDA nacional...")
        
        df = self.cargar_predicciones('DEMANDA', horizonte)
        
        if len(df) == 0:
            return
        
        promedio = df['valor_gwh_predicho'].mean()
        maximo = df['valor_gwh_predicho'].max()
        dias_alerta = len(df[df['valor_gwh_predicho'] > UMBRALES['DEMANDA']['ALERTA'][0]])
        dias_criticos = len(df[df['valor_gwh_predicho'] > UMBRALES['DEMANDA']['CRITICO']])
        
        if dias_criticos > 0:
            self.alertas.append({
                'categoria': 'DEMANDA',
                'severidad': 'CRÍTICO',
                'titulo': f'Demanda excesiva: {dias_criticos} días > {UMBRALES["DEMANDA"]["CRITICO"]} GWh',
                'descripcion': f'Pico máximo: {maximo:.2f} GWh/día. Riesgo de déficit.',
                'valor': maximo,
                'umbral': UMBRALES['DEMANDA']['CRITICO'],
                'dias_afectados': dias_criticos,
                'recomendacion': 'Activar generación térmica de respaldo. Evaluar importaciones.'
            })
            print(f"  🚨 CRÍTICO: {dias_criticos} días con demanda > {UMBRALES['DEMANDA']['CRITICO']} GWh")
            
        elif dias_alerta > 5:
            self.alertas.append({
                'categoria': 'DEMANDA',
                'severidad': 'ALERTA',
                'titulo': f'Demanda elevada: {dias_alerta} días en zona alerta',
                'descripcion': f'Promedio: {promedio:.2f} GWh/día. Máximo: {maximo:.2f} GWh/día.',
                'valor': promedio,
                'umbral': UMBRALES['DEMANDA']['ALERTA'][0],
                'dias_afectados': dias_alerta,
                'recomendacion': 'Monitorear de cerca. Preparar respaldos térmicos.'
            })
            print(f"  ⚠️  ALERTA: {dias_alerta} días con demanda elevada")
        else:
            print(f"  ✅ Normal: Promedio {promedio:.2f} GWh/día")
    
    def evaluar_aportes_hidricos(self, horizonte=30):
        """Evalúa riesgo hidrológico"""
        print("💧 Evaluando APORTES HÍDRICOS...")
        
        df = self.cargar_predicciones('APORTES_HIDRICOS', horizonte)
        
        if len(df) == 0:
            return
        
        promedio = df['valor_gwh_predicho'].mean()
        minimo = df['valor_gwh_predicho'].min()
        dias_criticos = len(df[df['valor_gwh_predicho'] < UMBRALES['APORTES_HIDRICOS']['CRITICO']])
        dias_alerta = len(df[df['valor_gwh_predicho'] < UMBRALES['APORTES_HIDRICOS']['ALERTA'][0]])
        
        if dias_criticos > 7:
            self.alertas.append({
                'categoria': 'HIDROLOGIA',
                'severidad': 'CRÍTICO',
                'titulo': f'Sequía severa: {dias_criticos} días con aportes < {UMBRALES["APORTES_HIDRICOS"]["CRITICO"]} GWh',
                'descripcion': f'Aportes mínimos: {minimo:.2f} GWh/día. Riesgo El Niño.',
                'valor': promedio,
                'umbral': UMBRALES['APORTES_HIDRICOS']['CRITICO'],
                'dias_afectados': dias_criticos,
                'recomendacion': 'URGENTE: Activar plan de contingencia hidrológica. Racionamiento programado.'
            })
            print(f"  🚨 CRÍTICO: Sequía severa detectada ({dias_criticos} días)")
            
        elif dias_alerta > 10:
            self.alertas.append({
                'categoria': 'HIDROLOGIA',
                'severidad': 'ALERTA',
                'titulo': f'Aportes bajos: {dias_alerta} días en zona alerta',
                'descripcion': f'Promedio: {promedio:.2f} GWh/día. Tendencia a la baja.',
                'valor': promedio,
                'umbral': UMBRALES['APORTES_HIDRICOS']['ALERTA'][0],
                'dias_afectados': dias_alerta,
                'recomendacion': 'Optimizar uso de embalses. Aumentar generación térmica.'
            })
            print(f"  ⚠️  ALERTA: Aportes por debajo de lo normal ({dias_alerta} días)")
        else:
            print(f"  ✅ Normal: Promedio {promedio:.2f} GWh/día")
    
    def evaluar_embalses(self, horizonte=30):
        """Evalúa nivel de almacenamiento en embalses"""
        print("🏞️  Evaluando CAPACIDAD DE EMBALSES...")
        
        df = self.cargar_predicciones('EMBALSES', horizonte)
        
        if len(df) == 0:
            return
        
        promedio = df['valor_gwh_predicho'].mean()
        minimo = df['valor_gwh_predicho'].min()
        nivel_final = df['valor_gwh_predicho'].iloc[-1]
        
        # Calcular porcentaje (asumiendo capacidad máxima ~35,000 GWh)
        porcentaje = (nivel_final / 35000) * 100
        
        if minimo < UMBRALES['EMBALSES']['CRITICO']:
            self.alertas.append({
                'categoria': 'EMBALSES',
                'severidad': 'CRÍTICO',
                'titulo': f'Nivel crítico de embalses: {porcentaje:.1f}%',
                'descripcion': f'Proyección: {nivel_final:.0f} GWh ({porcentaje:.1f}% capacidad). Preparar racionamiento.',
                'valor': nivel_final,
                'umbral': UMBRALES['EMBALSES']['CRITICO'],
                'dias_afectados': horizonte,
                'recomendacion': 'URGENTE: Declarar estado de emergencia energética. Activar todos los respaldos.'
            })
            print(f"  🚨 CRÍTICO: Nivel de embalses en {porcentaje:.1f}%")
            
        elif promedio < UMBRALES['EMBALSES']['ALERTA'][0]:
            self.alertas.append({
                'categoria': 'EMBALSES',
                'severidad': 'ALERTA',
                'titulo': f'Embalses por debajo de lo normal: {porcentaje:.1f}%',
                'descripcion': f'Nivel promedio proyectado: {promedio:.0f} GWh.',
                'valor': promedio,
                'umbral': UMBRALES['EMBALSES']['ALERTA'][0],
                'dias_afectados': horizonte,
                'recomendacion': 'Conservar agua. Maximizar generación térmica y renovables.'
            })
            print(f"  ⚠️  ALERTA: Nivel bajo ({porcentaje:.1f}%)")
        else:
            print(f"  ✅ Normal: {porcentaje:.1f}% capacidad")
    
    def evaluar_precio_bolsa(self, horizonte=30):
        """Evalúa comportamiento del precio de bolsa"""
        print("💰 Evaluando PRECIO DE BOLSA...")
        
        df = self.cargar_predicciones('PRECIO_BOLSA', horizonte)
        
        if len(df) == 0:
            return
        
        promedio = df['valor_gwh_predicho'].mean()
        maximo = df['valor_gwh_predicho'].max()
        dias_criticos = len(df[df['valor_gwh_predicho'] > UMBRALES['PRECIO_BOLSA']['CRITICO']])
        
        if dias_criticos > 3:
            self.alertas.append({
                'categoria': 'PRECIO_MERCADO',
                'severidad': 'CRÍTICO',
                'titulo': f'Precio de bolsa extremo: {dias_criticos} días > {UMBRALES["PRECIO_BOLSA"]["CRITICO"]} $/kWh',
                'descripcion': f'Pico: {maximo:.2f} $/kWh. Mercado en stress severo.',
                'valor': maximo,
                'umbral': UMBRALES['PRECIO_BOLSA']['CRITICO'],
                'dias_afectados': dias_criticos,
                'recomendacion': 'Intervención regulatoria. Evaluar subsidios a usuarios vulnerables.'
            })
            print(f"  🚨 CRÍTICO: Precios extremos detectados ({dias_criticos} días)")
            
        elif promedio > UMBRALES['PRECIO_BOLSA']['ALERTA'][0]:
            self.alertas.append({
                'categoria': 'PRECIO_MERCADO',
                'severidad': 'ALERTA',
                'titulo': f'Precios elevados: Promedio {promedio:.2f} $/kWh',
                'descripcion': f'Por encima del rango normal ({UMBRALES["PRECIO_BOLSA"]["NORMAL"][1]} $/kWh).',
                'valor': promedio,
                'umbral': UMBRALES['PRECIO_BOLSA']['ALERTA'][0],
                'dias_afectados': horizonte,
                'recomendacion': 'Monitorear generadores. Evaluar medidas para estabilizar precios.'
            })
            print(f"  ⚠️  ALERTA: Precios elevados (promedio {promedio:.2f} $/kWh)")
        else:
            print(f"  ✅ Normal: Promedio {promedio:.2f} $/kWh")
    
    def evaluar_balance_energetico(self, horizonte=30):
        """Evalúa balance oferta-demanda"""
        print("⚖️  Evaluando BALANCE OFERTA-DEMANDA...")
        
        # Cargar predicciones
        df_demanda = self.cargar_predicciones('DEMANDA', horizonte)
        df_gen_hidro = self.cargar_predicciones('Hidráulica', horizonte)
        df_gen_termo = self.cargar_predicciones('Térmica', horizonte)
        df_gen_solar = self.cargar_predicciones('Solar', horizonte)
        df_gen_eolica = self.cargar_predicciones('Eólica', horizonte)
        
        if len(df_demanda) == 0:
            return
        
        # Calcular balance
        generacion_total = (
            df_gen_hidro['valor_gwh_predicho'].mean() +
            df_gen_termo['valor_gwh_predicho'].mean() +
            df_gen_solar['valor_gwh_predicho'].mean() +
            df_gen_eolica['valor_gwh_predicho'].mean()
        )
        
        demanda_promedio = df_demanda['valor_gwh_predicho'].mean()
        balance = generacion_total - demanda_promedio
        
        if balance < UMBRALES['BALANCE']['CRITICO']:
            self.alertas.append({
                'categoria': 'BALANCE_ENERGETICO',
                'severidad': 'CRÍTICO',
                'titulo': f'Déficit energético severo: {balance:.2f} GWh/día',
                'descripcion': f'Generación: {generacion_total:.2f} GWh/día. Demanda: {demanda_promedio:.2f} GWh/día.',
                'valor': balance,
                'umbral': UMBRALES['BALANCE']['CRITICO'],
                'dias_afectados': horizonte,
                'recomendacion': 'EMERGENCIA: Activar todos los respaldos. Considerar racionamiento.'
            })
            print(f"  🚨 CRÍTICO: Déficit de {abs(balance):.2f} GWh/día")
            
        elif balance < UMBRALES['BALANCE']['ALERTA']:
            self.alertas.append({
                'categoria': 'BALANCE_ENERGETICO',
                'severidad': 'ALERTA',
                'titulo': f'Déficit energético moderado: {balance:.2f} GWh/día',
                'descripcion': f'Balance ajustado. Margen de seguridad reducido.',
                'valor': balance,
                'umbral': UMBRALES['BALANCE']['ALERTA'],
                'dias_afectados': horizonte,
                'recomendacion': 'Aumentar generación térmica. Evaluar importaciones.'
            })
            print(f"  ⚠️  ALERTA: Balance ajustado ({balance:.2f} GWh/día)")
        else:
            print(f"  ✅ Normal: Superávit de {balance:.2f} GWh/día")
    
    def _guardar_alertas_bd(self):
        """Guarda alertas en la base de datos (tabla alertas_historial)"""
        if not self.alertas:
            print("\n📝 No hay alertas para guardar en BD")
            return 0
        
        print(f"\n💾 Guardando {len(self.alertas)} alertas en BD...")
        cursor = self.conn.cursor()
        alertas_guardadas = 0
        
        try:
            for alerta in self.alertas:
                # Determinar fecha_evaluacion (hoy por defecto)
                fecha_evaluacion = datetime.now().date()
                
                query = """
                    INSERT INTO alertas_historial 
                    (fecha_evaluacion, metrica, severidad, valor_promedio, 
                     titulo, descripcion, recomendacion, dias_afectados,
                     umbral_alerta, umbral_critico,
                     json_completo, notificacion_email_enviada, notificacion_whatsapp_enviada)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, false)
                    RETURNING id
                """
                
                # Extraer umbral (puede ser simple valor o tupla)
                umbral = alerta.get('umbral', 0)
                umbral_critico = umbral if isinstance(umbral, (int, float)) else None
                umbral_alerta = None
                
                cursor.execute(query, (
                    fecha_evaluacion,
                    alerta['categoria'],
                    alerta['severidad'],
                    alerta.get('valor', 0),
                    alerta['titulo'],
                    alerta['descripcion'],
                    alerta.get('recomendacion', ''),
                    alerta.get('dias_afectados', 0),
                    umbral_alerta,
                    umbral_critico,
                    json.dumps(alerta, ensure_ascii=False)
                ))
                alerta_id = cursor.fetchone()[0]
                alerta['id_alerta'] = alerta_id  # Guardar ID para referencia posterior
                alertas_guardadas += 1
            
            self.conn.commit()
            print(f"  ✅ {alertas_guardadas} alertas guardadas correctamente")
            return alertas_guardadas
            
        except Exception as e:
            print(f"  ❌ Error guardando alertas: {e}")
            self.conn.rollback()
            return 0
        finally:
            cursor.close()
    
    def _enviar_notificaciones(self):
        """Envía notificaciones por email y WhatsApp para alertas críticas"""
        if not self.alertas:
            print("\n📢 No hay alertas para notificar")
            return
        
        # Filtrar solo alertas críticas para notificación
        alertas_criticas = [a for a in self.alertas if a['severidad'] == 'CRÍTICO']
        alertas_importantes = [a for a in self.alertas if a['severidad'] == 'ALERTA']
        
        if not alertas_criticas and not alertas_importantes:
            print("\n📢 No hay alertas que requieran notificación")
            return
        
        print(f"\n📢 Enviando notificaciones...")
        print(f"   🚨 Críticas: {len(alertas_criticas)}")
        print(f"   ⚠️  Importantes: {len(alertas_importantes)}")
        
        # Enviar notificaciones para alertas críticas
        for alerta in alertas_criticas:
            try:
                print(f"\n   📤 Notificando: {alerta['titulo'][:50]}...")
                
                # Preparar datos para notificar_alerta (usa el dict completo)
                alerta_para_notificacion = {
                    'severidad': alerta['severidad'],
                    'metrica': alerta['categoria'],
                    'titulo': alerta['titulo'],
                    'descripcion': alerta['descripcion'],
                    'valor': alerta.get('valor', 0),
                    'valor_promedio': alerta.get('valor', 0),
                    'umbral': alerta.get('umbral', 0),
                    'recomendacion': alerta.get('recomendacion', ''),
                    'dias_afectados': alerta.get('dias_afectados', 0)
                }
                
                resultado = notificar_alerta(
                    alerta=alerta_para_notificacion,
                    enviar_email=True,
                    enviar_whatsapp=True,
                    solo_criticas=False
                )
                
                # Actualizar estado de notificación en BD
                email_ok = resultado.get('email', {}).get('success', False)
                whatsapp_ok = resultado.get('whatsapp', {}).get('success', False)
                
                if 'id_alerta' in alerta:
                    self._actualizar_estado_notificacion(
                        alerta['id_alerta'],
                        email_ok,
                        whatsapp_ok
                    )
                
                if email_ok:
                    print(f"      ✅ Email enviado")
                if whatsapp_ok:
                    print(f"      ✅ WhatsApp enviado")
                    
            except Exception as e:
                print(f"      ❌ Error enviando notificación: {e}")
        
        # Enviar resumen diario para alertas importantes (opcional)
        if alertas_importantes:
            print(f"\n   ℹ️  Alertas importantes se incluirán en resumen diario")
    
    def _actualizar_estado_notificacion(self, id_alerta, email_enviado, whatsapp_enviado):
        """Actualiza el estado de las notificaciones enviadas en la BD"""
        try:
            cursor = self.conn.cursor()
            query = """
                UPDATE alertas_historial 
                SET notificacion_email_enviada = %s,
                    notificacion_whatsapp_enviada = %s,
                    fecha_notificacion = NOW()
                WHERE id = %s
            """
            cursor.execute(query, (email_enviado, whatsapp_enviado, id_alerta))
            self.conn.commit()
            cursor.close()
        except Exception as e:
            print(f"      ⚠️  Error actualizando estado notificación: {e}")
    
    def generar_reporte(self, output_file=None):
        """Genera reporte JSON con todas las alertas"""
        
        # 1. Guardar alertas en base de datos
        self._guardar_alertas_bd()
        
        # 2. Enviar notificaciones (email + WhatsApp)
        self._enviar_notificaciones()
        
        # 3. Generar reporte JSON
        reporte = {
            'fecha_generacion': datetime.now().isoformat(),
            'total_alertas': len(self.alertas),
            'alertas_criticas': len([a for a in self.alertas if a['severidad'] == 'CRÍTICO']),
            'alertas_importantes': len([a for a in self.alertas if a['severidad'] == 'ALERTA']),
            'alertas': self.alertas,
            'estado_general': self._determinar_estado_general()
        }
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(reporte, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Reporte JSON guardado en: {output_file}")
        
        return reporte
    
    def _determinar_estado_general(self):
        """Determina estado general del sistema"""
        if any(a['severidad'] == 'CRÍTICO' for a in self.alertas):
            return 'CRÍTICO'
        elif any(a['severidad'] == 'ALERTA' for a in self.alertas):
            return 'ALERTA'
        else:
            return 'NORMAL'
    
    def imprimir_resumen(self):
        """Imprime resumen ejecutivo de alertas"""
        print("\n" + "="*70)
        print("🇨🇴 RESUMEN DE ALERTAS - SECTOR ENERGÉTICO NACIONAL")
        print("="*70)
        
        criticas = [a for a in self.alertas if a['severidad'] == 'CRÍTICO']
        alertas = [a for a in self.alertas if a['severidad'] == 'ALERTA']
        
        print(f"\n📊 Total alertas: {len(self.alertas)}")
        print(f"   🚨 Críticas: {len(criticas)}")
        print(f"   ⚠️  Importantes: {len(alertas)}")
        
        if criticas:
            print(f"\n🚨 ALERTAS CRÍTICAS ({len(criticas)}):")
            for i, alerta in enumerate(criticas, 1):
                print(f"\n   {i}. {alerta['titulo']}")
                print(f"      {alerta['descripcion']}")
                print(f"      💡 Recomendación: {alerta['recomendacion']}")
        
        if alertas:
            print(f"\n⚠️  ALERTAS IMPORTANTES ({len(alertas)}):")
            for i, alerta in enumerate(alertas, 1):
                print(f"\n   {i}. {alerta['titulo']}")
                print(f"      {alerta['descripcion']}")
                print(f"      💡 Recomendación: {alerta['recomendacion']}")
        
        if not self.alertas:
            print("\n✅ SISTEMA OPERANDO NORMALMENTE")
            print("   No se detectaron condiciones anormales.")
        
        print("\n" + "="*70)
    
    def close(self):
        """Cierra conexión"""
        if self.conn:
            self.conn.close()


def main():
    """Función principal"""
    print("\n" + "="*70)
    print("🇨🇴 SISTEMA DE ALERTAS AUTOMÁTICAS")
    print("   Ministerio de Minas y Energía - República de Colombia")
    print("   Fecha:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("="*70)
    
    sistema = SistemaAlertasEnergeticas()
    
    try:
        # Evaluar cada categoría
        sistema.evaluar_demanda(horizonte=30)
        sistema.evaluar_aportes_hidricos(horizonte=30)
        sistema.evaluar_embalses(horizonte=30)
        sistema.evaluar_precio_bolsa(horizonte=30)
        sistema.evaluar_balance_energetico(horizonte=30)
        
        # Generar reporte
        output_path = '/home/admonctrlxm/server/logs/alertas_energeticas.json'
        reporte = sistema.generar_reporte(output_path)
        
        # Imprimir resumen
        sistema.imprimir_resumen()
        
        # Estado general
        print(f"\n🎯 ESTADO GENERAL DEL SISTEMA: {reporte['estado_general']}")
        
        if reporte['estado_general'] == 'CRÍTICO':
            print("   🚨 REQUIERE ATENCIÓN INMEDIATA DEL VICEMINISTRO")
        elif reporte['estado_general'] == 'ALERTA':
            print("   ⚠️  Monitorear de cerca. Preparar contingencias.")
        else:
            print("   ✅ Operación normal. Continuar monitoreo rutinario.")
        
        print("\n✅ Proceso completado")
        
    finally:
        sistema.close()


if __name__ == "__main__":
    main()

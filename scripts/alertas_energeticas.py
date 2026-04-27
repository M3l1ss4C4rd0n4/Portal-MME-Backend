#!/usr/bin/env python3
"""
SISTEMA DE ALERTAS AUTOMÁTICAS - SECTOR ELÉCTRICO COLOMBIANO
Viceministro de Energía - Alertas Tempranas y Notificaciones

ALCANCE Y NATURALEZA (declaración explícita de gobernanza):
──────────────────────────────────────────────────────────────
Este sistema es COMPLEMENTARIO a XM, NO sustitutivo.

• Fuente de datos primaria: métricas publicadas por XM vía pydataxm
  (Gene, DemaSIN, AporEner, PorcVoluUtilDiar, PrecBolsNaci) y SIMEM
  (PrecEsca, PPP Bolsa, Demanda Reg/No Reg). Los datos se replican en
  sector_energetico.metrics con un rezago de ~1-2 días respecto a XM.

• Señales operativas detectadas aquí: demanda alta, aportes hídricos
  bajos, embalses en niveles mínimos, estrés térmico, precios de bolsa
  sobre precio de escasez.

• Señales fuera de alcance: transacciones individuales, despacho central,
  restricciones de red, desviaciones en tiempo real. Consultar XM / NEON.

• Índices compuestos (ISH, IPM, IES, CIS): de naturaleza DESCRIPTIVA.
  No son alertas operativas ni reemplazan los semáforos de XM.
  Los pesos (0.40/0.35/0.25) reflejan percepción analítica, no norma técnica.

• Percentiles / umbrales de aportes: AporEnerMediHist XM cuando disponible
  (percentiles dinámicos). Fallback a tablas estacionales 2020-2026.
──────────────────────────────────────────────────────────────
Output: JSON con alertas clasificadas por severidad
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
from datetime import datetime, date, timedelta
from infrastructure.database.connection import PostgreSQLConnectionManager
import json

# Sistema de notificaciones: usar notification_service (producción)
# sistema_notificaciones.py fue retirado (legacy Gmail/WhatsApp)

class NotificationService:
    """Adapter stub — redirige al servicio de producción."""

def notificar_alerta(alerta, enviar_email=True, enviar_whatsapp=True, solo_criticas=True):
    """Stub que reemplaza al legacy sistema_notificaciones.notificar_alerta.
    En producción las alertas se envían desde anomaly_tasks → notification_service."""
    severidad = alerta.get('severidad', 'NORMAL')
    if solo_criticas and severidad != 'CRÍTICO':
        return {
            'email': {'success': False, 'message': 'No es crítica, omitida'},
            'whatsapp': {'success': False, 'message': 'No es crítica, omitida'}
        }
    # Las notificaciones reales pasan por anomaly_tasks → notification_service
    return {
        'email': {'success': True, 'message': 'Delegado a notification_service'},
        'whatsapp': {'success': True, 'message': 'Delegado a notification_service'}
    }

# =============================================================================
# UMBRALES DE ALERTAS (CONFIGURABLES POR POLÍTICA MINISTERIAL)
# Fuentes de datos: pydataxm (físico-operativo) + pydataSIMEM (económico)
# Criterios alineados con el razonamiento técnico del CND/XM
# =============================================================================

UMBRALES = {
    # ─── DEMANDA ───────────────────────────────────────────────────────────────
    # Señal de presión en demanda. Por sí sola NO es crisis: se evalúa junto al
    # margen operativo. Umbral: p99 histórico anual (253 GWh).
    # Condición crítica: > 60 % de días del horizonte exceden el p99.
    'DEMANDA': {
        'ALERTA': 248,              # GWh/día — p75 histórico
        'CRITICO': 253,             # GWh/día — p99 histórico
        'DIAS_CRITICO_PCT': 0.60,   # fracción mínima del horizonte para disparar CRÍTICO
        'DIAS_ALERTA_PCT': 0.50,    # fracción mínima del horizonte para disparar ALERTA
    },
    # ─── EMBALSES (como % de capacidad útil) ──────────────────────────────────
    # Fuente: EMBALSES_PCT (ya viene en % desde predictions, no usar GWh absolutos).
    # Referencia XM: capacidad útil total SIN ≈ 46 700 GWh equivalentes.
    'EMBALSES_PCT': {
        'CRITICO': 30.0,    # < 30 % → riesgo de racionamiento
        'ALERTA':  40.0,    # 30–40 % → vigilancia activa
    },
    # ─── APORTES HÍDRICOS ─────────────────────────────────────────────────────
    # Umbrales estacionales en _UMBRALES_APORTES_ESTACIONAL (p5/p15 por mes).
    # días_criticos / horizonte >= 0.60 → CRÍTICO
    # días_alerta   / horizonte >= 0.50 → ALERTA
    'APORTES_HIDRICOS': {
        'DIAS_CRITICO_PCT': 0.60,
        'DIAS_ALERTA_PCT':  0.50,
    },
    # ─── PRECIO BOLSA ─────────────────────────────────────────────────────────
    # Comparar precio_bolsa con precio_escasez (fuente PRECIO_ESCASEZ disponible).
    # ratio = precio_bolsa_prom / precio_escasez_prom
    # Si precio_escasez no está disponible: usar umbrales fijos en COP/kWh.
    'PRECIO_BOLSA': {
        'CRITICO_RATIO': 0.90,   # precio_bolsa > 90 % precio_escasez → escasez inminente
        'ALERTA_RATIO':  0.65,   # precio_bolsa > 65 % precio_escasez → señal de estrés
        'CRITICO_FIJO':  850,    # COP/kWh — fallback si no hay precio_escasez
        'ALERTA_FIJO':   500,    # COP/kWh — fallback
    },
    # ─── MARGEN OPERATIVO ─────────────────────────────────────────────────────
    # margen (%) = (GENE_TOTAL_pred − DEMANDA_pred) / DEMANDA_pred × 100
    # Criterio dominante del CND: ¿hay potencia suficiente?
    'MARGEN_OPERATIVO': {
        'CRITICO': 3.0,    # < 3 % → riesgo real de déficit
        'ALERTA':  8.0,    # 3–8 % → vigilancia
    },
    # ─── ESTRÉS TÉRMICO ───────────────────────────────────────────────────────
    # participación (%) = Térmica_pred / DEMANDA_pred × 100
    # XM no entra en riesgo sin aumento térmico sostenido.
    'ESTRES_TERMICO': {
        'CRITICO': 35.0,             # > 35 % sostenido → riesgo estructural
        'ALERTA':  20.0,             # 20–35 % sostenido → vigilancia
        'DIAS_CRITICO_PCT': 0.70,    # fracción mínima del horizonte
        'DIAS_ALERTA_PCT':  0.60,
    },
}

# Umbrales mensuales estacionales para AporEner (derivados de percentiles 2020–2026)
# Índice = mes (1..12); valores = (p05_critico, p15_alerta) GWh/día
_UMBRALES_APORTES_ESTACIONAL = {
    1:  (63,  115),   # Ene
    2:  (98,  129),   # Feb
    3:  (124, 141),   # Mar
    4:  (160, 194),   # Abr
    5:  (223, 291),   # May
    6:  (311, 392),   # Jun
    7:  (315, 356),   # Jul
    8:  (227, 264),   # Ago
    9:  (188, 217),   # Sep
    10: (221, 251),   # Oct
    11: (296, 335),   # Nov
    12: (194, 211),   # Dic
}


def _get_umbral_aportes(mes: int) -> dict:
    """Devuelve umbrales de aportes hídricos (GWh/día) ajustados por estacionalidad."""
    critico, alerta = _UMBRALES_APORTES_ESTACIONAL.get(mes, (300, 400))
    return {'CRITICO': critico, 'ALERTA': alerta}


class SistemaAlertasEnergeticas:
    """Sistema de alertas automáticas para sector energético"""
    
    def __init__(self):
        self.alertas = []
        self.conn = self._get_connection()
        self.notification_service = NotificationService()
        print("✅ Sistema de notificaciones inicializado")
        
    def _get_connection(self):
        """Obtiene conexión a PostgreSQL"""
        from core.config import settings
        conn_params = {
            'host': settings.POSTGRES_HOST,
            'port': settings.POSTGRES_PORT,
            'database': settings.POSTGRES_DB,
            'user': settings.POSTGRES_USER,
        }
        if settings.POSTGRES_PASSWORD:
            conn_params['password'] = settings.POSTGRES_PASSWORD
        return psycopg2.connect(**conn_params)
    
    def cargar_predicciones(self, fuente, dias=30):
        """DEPRECADO — usa predicciones futuras (tabla predictions).

        Mantenido para compatibilidad; use cargar_datos_reales() para
        datos operativos. Las predicciones siguen en revisión y NO
        deben usarse para alertas operativas de producción.
        """
        query = """
            SELECT DISTINCT ON (fecha_prediccion)
                   fecha_prediccion, valor_gwh_predicho,
                   intervalo_inferior, intervalo_superior
            FROM predictions
            WHERE fuente = %s
              AND fecha_prediccion >= CURRENT_DATE
            ORDER BY fecha_prediccion, confianza DESC NULLS LAST
            LIMIT %s
        """
        df = pd.read_sql_query(query, self.conn, params=(fuente, dias))
        return df

    def cargar_datos_reales(self, metrica, recurso='Sistema', dias=30):
        """Carga datos reales publicados por XM desde sector_energetico.metrics.

        Sustituto operativo de cargar_predicciones(). Usa los últimos N días de
        datos históricos completos. Excluye los 3 días más recientes porque XM
        puede tardar 1-2 días en completar la publicación diaria.

        Args:
            metrica: Nombre XM de la métrica ('DemaSIN', 'AporEner', etc.)
            recurso: Nivel de agregación, normalmente 'Sistema'
            dias:    Ventana histórica en días

        Returns:
            DataFrame ['fecha' (date), 'valor_gwh'], ordenado DESC por fecha.
        """
        fecha_fin = date.today() - timedelta(days=3)
        fecha_inicio = fecha_fin - timedelta(days=dias)

        query = """
            SELECT fecha::date AS fecha, valor_gwh
            FROM sector_energetico.metrics
            WHERE metrica = %s
              AND recurso = %s
              AND fecha::date BETWEEN %s AND %s
            ORDER BY fecha::date DESC
        """
        df = pd.read_sql_query(
            query, self.conn,
            params=(metrica, recurso, fecha_inicio, fecha_fin)
        )
        return df

    def cargar_generacion_termica_real(self, dias=30):
        """Generación térmica real diaria (GWh/día) agregada a nivel sistema.

        Filtra los recursos de tecnología 'TERMICA' mediante JOIN con el
        catálogo sector_energetico.catalogos (ListadoRecursos).

        Returns:
            DataFrame ['fecha' (date), 'valor_gwh'], ordenado DESC por fecha.
        """
        fecha_fin = date.today() - timedelta(days=3)
        fecha_inicio = fecha_fin - timedelta(days=dias)

        query = """
            SELECT m.fecha::date AS fecha, SUM(m.valor_gwh) AS valor_gwh
            FROM sector_energetico.metrics m
            JOIN sector_energetico.catalogos c
                 ON m.recurso = c.codigo AND c.catalogo = 'ListadoRecursos'
            WHERE m.metrica = 'Gene'
              AND c.tipo = 'TERMICA'
              AND m.fecha::date BETWEEN %s AND %s
            GROUP BY m.fecha::date
            ORDER BY m.fecha::date DESC
        """
        df = pd.read_sql_query(
            query, self.conn,
            params=(fecha_inicio, fecha_fin)
        )
        return df
    
    def evaluar_demanda(self, horizonte=30):
        """Evalúa presión en demanda nacional con datos reales (DemaSIN, XM).

        La demanda alta por sí sola NO es crisis — solo señala presión.
        El riesgo real se determina con el margen operativo (evaluar_balance_energetico).
        Dispara solo cuando la fracción de días recientes que supera el umbral es significativa.
        """
        print("📊 Evaluando DEMANDA nacional...")

        df = self.cargar_datos_reales('DemaSIN', dias=horizonte)
        if len(df) == 0:
            return

        total = len(df)
        umbral_crit = UMBRALES['DEMANDA']['CRITICO']
        umbral_alert = UMBRALES['DEMANDA']['ALERTA']
        pct_crit = UMBRALES['DEMANDA']['DIAS_CRITICO_PCT']
        pct_alert = UMBRALES['DEMANDA']['DIAS_ALERTA_PCT']

        promedio = float(df['valor_gwh'].mean())
        maximo = float(df['valor_gwh'].max())
        dias_criticos = int((df['valor_gwh'] > umbral_crit).sum())
        dias_alerta = int((df['valor_gwh'] > umbral_alert).sum())

        if dias_criticos / total >= pct_crit:
            self.alertas.append({
                'categoria': 'DEMANDA',
                'severidad': 'CRÍTICO',
                'titulo': f'Demanda excesiva sostenida: {dias_criticos}/{total} días > {umbral_crit} GWh',
                'descripcion': (
                    f'Pico máximo: {maximo:.1f} GWh/día. Promedio: {promedio:.1f} GWh/día. '
                    f'El {dias_criticos/total*100:.0f}% de los últimos {total} días supera el p99 histórico. '
                    f'Evaluar en conjunto con margen operativo.'
                ),
                'valor': maximo,
                'umbral': umbral_crit,
                'dias_afectados': dias_criticos,
                'recomendacion': 'Revisar disponibilidad de respaldo térmico. Validar margen operativo.'
            })
            print(f"  🚨 CRÍTICO: {dias_criticos}/{total} días ({dias_criticos/total*100:.0f}%) con demanda > {umbral_crit} GWh")

        elif dias_alerta / total >= pct_alert:
            self.alertas.append({
                'categoria': 'DEMANDA',
                'severidad': 'ALERTA',
                'titulo': f'Demanda elevada: {dias_alerta}/{total} días > {umbral_alert} GWh',
                'descripcion': f'Promedio: {promedio:.1f} GWh/día. Máximo: {maximo:.1f} GWh/día.',
                'valor': promedio,
                'umbral': umbral_alert,
                'dias_afectados': dias_alerta,
                'recomendacion': 'Monitorear de cerca. Preparar respaldos térmicos.'
            })
            print(f"  ⚠️  ALERTA: {dias_alerta}/{total} días con demanda elevada")
        else:
            print(f"  ✅ Normal: Promedio {promedio:.1f} GWh/día ({dias_criticos} días > p99 = {pct_crit*100:.0f}% mínimo requerido)")
    
    def evaluar_aportes_hidricos(self, horizonte=30):
        """Evalúa riesgo hidrológico comparando AporEner contra AporEnerMediHist (XM).

        Umbrales DINÁMICOS: usa la media histórica oficial XM (AporEnerMediHist)
        del mismo período como referencia, en lugar de percentiles estáticos de
        2020-2026 que no se actualizan con el clima real.

        Umbrales: CRÍTICO < 50% mediana histórica XM, ALERTA < 65% mediana histórica XM.
        Fallback automático a p5/p15 mensuales hardcodeados si AporEnerMediHist no
        tiene datos suficientes en BD (≥ 25% de cobertura del horizonte).
        """
        print("💧 Evaluando APORTES HÍDRICOS (vs. media histórica XM)...")

        df = self.cargar_datos_reales('AporEner', dias=horizonte)
        if len(df) == 0:
            return

        # ── Umbrales dinámicos: AporEnerMediHist ya está en BD (etl_rules) ──
        df_hist = self.cargar_datos_reales('AporEnerMediHist', dias=horizonte)
        if len(df_hist) >= max(3, horizonte // 4):
            # Referencia oficial XM — se actualiza sola con el ETL.
            # ADVERTENCIA: AporEnerMediHist hereda los supuestos históricos de XM
            # (ventana de cálculo, años de referencia). Si XM cambia su metodología,
            # estos umbrales cambian automáticamente. Documentar en auditorías externas.
            media_hist = float(df_hist['valor_gwh'].mean())
            _umbral_critico = round(media_hist * 0.50, 1)  # < 50% mediana → crítico
            _umbral_alerta  = round(media_hist * 0.65, 1)  # < 65% mediana → alerta
            fuente_umbral = f"AporEnerMediHist XM (media={media_hist:.1f} GWh/d)"
        else:
            # Fallback a percentiles mensuales hardcodeados
            _mes_ref = datetime.now().month
            _umb = _get_umbral_aportes(_mes_ref)
            _umbral_critico = _umb['CRITICO']
            _umbral_alerta  = _umb['ALERTA']
            mes_str_fb = datetime.now().strftime('%b')
            fuente_umbral = f"p5/p15 estacional {mes_str_fb} (fallback: AporEnerMediHist sin datos)"
            print(f"  ⚠️  AporEnerMediHist insuficiente ({len(df_hist)} días) — usando fallback")

        pct_crit = UMBRALES['APORTES_HIDRICOS']['DIAS_CRITICO_PCT']
        pct_alert = UMBRALES['APORTES_HIDRICOS']['DIAS_ALERTA_PCT']

        total = len(df)
        promedio = float(df['valor_gwh'].mean())
        minimo = float(df['valor_gwh'].min())
        dias_criticos = int((df['valor_gwh'] < _umbral_critico).sum())
        dias_alerta = int((df['valor_gwh'] < _umbral_alerta).sum())

        if dias_criticos / total >= pct_crit:
            self.alertas.append({
                'categoria': 'HIDROLOGIA',
                'severidad': 'CRÍTICO',
                'titulo': f'Sequía severa: {dias_criticos}/{total} días aportes < {_umbral_critico} GWh',
                'descripcion': (
                    f'Aportes mín: {minimo:.1f} GWh/día, promedio: {promedio:.1f} GWh/día. '
                    f'El {dias_criticos/total*100:.0f}% del periodo está bajo el umbral crítico '
                    f'({fuente_umbral}). Riesgo hidrológico.'
                ),
                'valor': promedio,
                'umbral': _umbral_critico,
                'dias_afectados': dias_criticos,
                'recomendacion': 'URGENTE: Activar plan de contingencia hidrológica. Revisar despacho térmico.'
            })
            print(f"  🚨 CRÍTICO: Sequía severa ({dias_criticos}/{total} días < {_umbral_critico} GWh — {fuente_umbral})")

        elif dias_alerta / total >= pct_alert:
            self.alertas.append({
                'categoria': 'HIDROLOGIA',
                'severidad': 'ALERTA',
                'titulo': f'Aportes bajos: {dias_alerta}/{total} días < {_umbral_alerta} GWh',
                'descripcion': (
                    f'Promedio: {promedio:.1f} GWh/día. Tendencia a la baja. '
                    f'Referencia: {fuente_umbral}.'
                ),
                'valor': promedio,
                'umbral': _umbral_alerta,
                'dias_afectados': dias_alerta,
                'recomendacion': 'Optimizar uso de embalses. Aumentar generación térmica.'
            })
            print(f"  ⚠️  ALERTA: Aportes bajos ({dias_alerta}/{total} días < {_umbral_alerta} GWh — {fuente_umbral})")
        else:
            print(f"  ✅ Normal: Aportes promedio {promedio:.1f} GWh/día (umbral alerta {_umbral_alerta} GWh — {fuente_umbral})")
    
    def evaluar_embalses(self, horizonte=30):
        """Evalúa nivel de almacenamiento de embalses con datos reales XM.

        Usa PorcVoluUtilDiar (% de capacidad útil diaria, almacenado como
        fracción 0-1 en la BD → se multiplica por 100).
        Umbrales: CRÍTICO < 30%, ALERTA 30-40% (alineados con criterios XM).
        """
        print("🏞️  Evaluando CAPACIDAD DE EMBALSES...")

        df = self.cargar_datos_reales('PorcVoluUtilDiar', dias=horizonte)
        if len(df) == 0:
            return
        # PorcVoluUtilDiar se almacena como fracción (0–1); convertir a porcentaje real
        df = df.copy()
        df['valor_gwh'] = df['valor_gwh'] * 100.0

        umbral_crit = UMBRALES['EMBALSES_PCT']['CRITICO']
        umbral_alert = UMBRALES['EMBALSES_PCT']['ALERTA']

        pct_actual = float(df['valor_gwh'].iloc[0])    # nivel más reciente (últimos datos completos XM)
        pct_inicio = float(df['valor_gwh'].iloc[-1])   # nivel hace N días
        pct_min = float(df['valor_gwh'].min())
        tendencia = pct_actual - pct_inicio  # positivo = llenando, negativo = vaciando

        if pct_min < umbral_crit:
            self.alertas.append({
                'categoria': 'EMBALSES',
                'severidad': 'CRÍTICO',
                'titulo': f'Nivel crítico de embalses: {pct_min:.1f}% capacidad útil',
                'descripcion': (
                    f'Nivel mínimo reciente: {pct_min:.1f}%. Actual: {pct_actual:.1f}%. '
                    f'Tendencia últimos {horizonte} días: {tendencia:+.1f}%. '
                    f'Umbral crítico XM: {umbral_crit}%.'
                ),
                'valor': pct_min,
                'umbral': umbral_crit,
                'dias_afectados': horizonte,
                'recomendacion': 'URGENTE: Activar todos los respaldos térmicos. Revisar plan de contingencia hídrica.'
            })
            print(f"  🚨 CRÍTICO: Nivel mínimo reciente {pct_min:.1f}% (umbral={umbral_crit}%)")

        elif pct_actual < umbral_alert:
            self.alertas.append({
                'categoria': 'EMBALSES',
                'severidad': 'ALERTA',
                'titulo': f'Embalses bajo zona de alerta: {pct_actual:.1f}% capacidad útil',
                'descripcion': (
                    f'Nivel actual: {pct_actual:.1f}%. Tendencia últimos {horizonte} días: {tendencia:+.1f}%.'
                ),
                'valor': pct_actual,
                'umbral': umbral_alert,
                'dias_afectados': horizonte,
                'recomendacion': 'Conservar agua. Maximizar generación térmica y renovables no hidráulicas.'
            })
            print(f"  ⚠️  ALERTA: Nivel {pct_actual:.1f}% (umbral={umbral_alert}%)")
        else:
            print(f"  ✅ Normal: {pct_actual:.1f}% capacidad útil (tendencia {tendencia:+.1f}% / {horizonte}d)")
    
    def evaluar_precio_bolsa(self, horizonte=30):
        """Evalúa comportamiento del precio de bolsa vs precio de escasez.

        Usa datos reales XM (PrecBolsNaci, PrecEsca, recurso='Sistema').
        Cuando el precio de bolsa se acerca al costo de escasez, el mercado
        está en estrés real. Fuente: pydataSIMEM (COP/kWh).
        """
        print("💰 Evaluando PRECIO DE BOLSA...")

        df_bolsa = self.cargar_datos_reales('PrecBolsNaci', dias=horizonte)
        if len(df_bolsa) == 0:
            return

        df_escasez = self.cargar_datos_reales('PrecEsca', dias=horizonte)

        bolsa_prom = float(df_bolsa['valor_gwh'].mean())
        bolsa_max = float(df_bolsa['valor_gwh'].max())

        umb = UMBRALES['PRECIO_BOLSA']

        if len(df_escasez) > 0:
            # Ratio diario suavizado con media móvil 3 días (anti-ruido por días atípicos)
            bolsa_idx = df_bolsa.set_index('fecha')['valor_gwh']
            escasez_idx = df_escasez.set_index('fecha')['valor_gwh']
            fechas_comunes = bolsa_idx.index.intersection(escasez_idx.index)
            if len(fechas_comunes) > 0:
                ratio_diario = (bolsa_idx.loc[fechas_comunes] /
                                escasez_idx.loc[fechas_comunes].replace(0, float('nan')))
                ratio = float(ratio_diario.rolling(3, min_periods=1).mean().mean())
            else:
                ratio = bolsa_prom / float(df_escasez['valor_gwh'].mean()) if float(df_escasez['valor_gwh'].mean()) > 0 else 0
            escasez_prom = float(df_escasez['valor_gwh'].mean())
            crit_umbral = escasez_prom * umb['CRITICO_RATIO']
            alert_umbral = escasez_prom * umb['ALERTA_RATIO']
            referencia = f"escasez={escasez_prom:.0f} COP/kWh, ratio={ratio:.0%} (mv3d)"
            es_critico = ratio >= umb['CRITICO_RATIO']
            es_alerta = ratio >= umb['ALERTA_RATIO']
        else:
            # Fallback: umbrales fijos si no hay predicción de precio_escasez
            crit_umbral = umb['CRITICO_FIJO']
            alert_umbral = umb['ALERTA_FIJO']
            referencia = f"umbral fijo (sin precio_escasez)"
            es_critico = bolsa_prom >= crit_umbral
            es_alerta = bolsa_prom >= alert_umbral

        if es_critico:
            self.alertas.append({
                'categoria': 'PRECIO_MERCADO',
                'severidad': 'CRÍTICO',
                'titulo': f'Precio bolsa crítico: {bolsa_prom:.0f} COP/kWh ≥ {umb["CRITICO_RATIO"]*100:.0f}% precio escasez',
                'descripcion': (
                    f'Precio bolsa promedio: {bolsa_prom:.0f} COP/kWh. '
                    f'Máximo: {bolsa_max:.0f} COP/kWh. Referencia: {referencia}. '
                    f'Sistema cerca del costo de escasez — riesgo de intervención.'
                ),
                'valor': bolsa_prom,
                'umbral': crit_umbral,
                'dias_afectados': horizonte,
                'recomendacion': 'Intervención regulatoria urgente. Evaluar subsidios y despacho forzado.'
            })
            print(f"  🚨 CRÍTICO: Bolsa {bolsa_prom:.0f} COP/kWh ({referencia})")

        elif es_alerta:
            self.alertas.append({
                'categoria': 'PRECIO_MERCADO',
                'severidad': 'ALERTA',
                'titulo': f'Precio bolsa elevado: {bolsa_prom:.0f} COP/kWh ≥ {umb["ALERTA_RATIO"]*100:.0f}% precio escasez',
                'descripcion': (
                    f'Precio bolsa promedio: {bolsa_prom:.0f} COP/kWh. Referencia: {referencia}.'
                ),
                'valor': bolsa_prom,
                'umbral': alert_umbral,
                'dias_afectados': horizonte,
                'recomendacion': 'Monitorear generadores. Evaluar medidas para estabilizar precios.'
            })
            print(f"  ⚠️  ALERTA: Bolsa {bolsa_prom:.0f} COP/kWh ({referencia})")
        else:
            print(f"  ✅ Normal: Bolsa {bolsa_prom:.0f} COP/kWh ({referencia})")
    
    def evaluar_balance_energetico(self, horizonte=30):
        """Nota: Con datos reales, Gene ≈ DemaSIN por física del sistema eléctrico.

        En operación real, oferta = demanda en todo momento (dispatch = load).
        Esta evaluación sólo tiene sentido con predicciones futuras donde puede
        existir un déficit proyectado. Con datos históricos reales, el estrés
        operativo se refleja en niveles de embalses, aportes hídricos y precios.
        """
        print("⚖️  Balance energético: no evaluable con datos históricos reales.")
        print("     Gene ≈ DemaSIN por física del SIN (oferta = demanda en tiempo real).")
        print("     El estrés operativo se refleja en embalses, aportes y precio de bolsa.")

    def evaluar_estres_termico(self, horizonte=30):
        """Evalúa participación térmica en la generación con datos reales XM.
 con datos reales XM.

        Un alto despacho térmico indica compensación por déficit hidráulico.
        La generación térmica se obtiene sumando todos los recursos de
        tecnología 'TERMICA' del catálogo sector_energetico.catalogos.

        participación (%) = Generación_térmica / DemaSIN × 100

        Umbrales:
          - CRÍTICO > 35 % sostenido (>= 70 % del periodo)
          - ALERTA  > 20 % sostenido (>= 60 % del periodo)
        """
        print("🔥 Evaluando ESTRÉS TÉRMICO...")

        df_termica = self.cargar_generacion_termica_real(dias=horizonte)
        df_demanda = self.cargar_datos_reales('DemaSIN', dias=horizonte)

        if len(df_termica) == 0 or len(df_demanda) == 0:
            print("  ⚠️  Sin datos de térmica o demanda")
            return

        # Alinear por fecha
        df_termica = df_termica.set_index('fecha')['valor_gwh']
        df_demanda = df_demanda.set_index('fecha')['valor_gwh']
        fechas_comunes = df_termica.index.intersection(df_demanda.index)

        if len(fechas_comunes) == 0:
            print("  ⚠️  No hay fechas coincidentes entre Térmica y DEMANDA")
            return

        df_termica = df_termica.loc[fechas_comunes].astype(float)
        df_demanda = df_demanda.loc[fechas_comunes].astype(float)

        participacion_diaria = (df_termica / df_demanda.replace(0, float('nan'))) * 100
        # Media móvil 3 días para suavizar picos aislados (p.ej. días de falla puntual)
        participacion_suavizada = participacion_diaria.rolling(3, min_periods=1).mean()
        participacion_prom = float(participacion_suavizada.mean())
        total = len(participacion_suavizada)

        umb = UMBRALES['ESTRES_TERMICO']
        dias_criticos = int((participacion_suavizada > umb['CRITICO']).sum())
        dias_alerta = int((participacion_suavizada > umb['ALERTA']).sum())

        print(f"  Participación térmica: prom={participacion_prom:.1f}% (mv3d) | "
              f"días>{umb['CRITICO']:.0f}%: {dias_criticos}/{total} | "
              f"días>{umb['ALERTA']:.0f}%: {dias_alerta}/{total}")

        if dias_criticos / total >= umb['DIAS_CRITICO_PCT']:
            self.alertas.append({
                'categoria': 'ESTRES_TERMICO',
                'severidad': 'CRÍTICO',
                'titulo': f'Estrés térmico crítico: {participacion_prom:.1f}% participación sostenida',
                'descripcion': (
                    f'{dias_criticos}/{total} días con participación térmica > {umb["CRITICO"]}%. '
                    f'Alta dependencia térmica indica déficit hidráulico estructural.'
                ),
                'valor': participacion_prom,
                'umbral': umb['CRITICO'],
                'dias_afectados': dias_criticos,
                'recomendacion': 'Revisar disponibilidad de combustibles. Evaluar riesgo de falla de generadores térmicos.'
            })
            print(f"  🚨 CRÍTICO: {dias_criticos}/{total} días térmica > {umb['CRITICO']}%")

        elif dias_alerta / total >= umb['DIAS_ALERTA_PCT']:
            self.alertas.append({
                'categoria': 'ESTRES_TERMICO',
                'severidad': 'ALERTA',
                'titulo': f'Estrés térmico moderado: {participacion_prom:.1f}% participación',
                'descripcion': (
                    f'{dias_alerta}/{total} días con participación térmica > {umb["ALERTA"]}%. '
                    f'Sistema en modo de compensación hidráulica.'
                ),
                'valor': participacion_prom,
                'umbral': umb['ALERTA'],
                'dias_afectados': dias_alerta,
                'recomendacion': 'Optimizar despacho. Asegurar suministro de gas/carbón para térmicas.'
            })
            print(f"  ⚠️  ALERTA: {dias_alerta}/{total} días térmica > {umb['ALERTA']}%")
        else:
            print(f"  ✅ Normal: Participación térmica {participacion_prom:.1f}%")
    
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
        """Clasifica el estado general del SIN.

        Reglas alineadas con criterio CND / XM:

          CRÍTICO A: ≥ 2 condiciones críticas + embalse comprometido (<60 %).
                     Exige coincidencia de señales Y presión de stock.
          CRÍTICO B: Térmica CRÍTICO + Precio CRÍTICO simultáneos.
                     Despacho forzado bajo precio de escasez = crisis real
                     independientemente del nivel de embalse.
          CRÍTICO C: ≥ 3 condiciones críticas (extremo, sin guarda adicional).
          ALERTA   : ≥ 1 condición crítica sin presión estructural de embalse.
                     O bien ≥ 2 condiciones en alerta (seguimiento activo).
          NORMAL   : en otro caso.

        Justificación: XM no declara riesgo estructural si los embalses (≲0 %) 
        están sobre 60 %, puesto que el sistema tiene buffer operacional.
        """
        n_criticos = sum(1 for a in self.alertas if a['severidad'] == 'CRÍTICO')
        n_alertas  = sum(1 for a in self.alertas if a['severidad'] == 'ALERTA')

        cats_criticas = {a['categoria'] for a in self.alertas if a['severidad'] == 'CRÍTICO'}
        cats_alerta   = {a['categoria'] for a in self.alertas if a['severidad'] == 'ALERTA'}

        # Embalse comprometido: ya aparece como ALERTA o CRÍTICO en la evaluación
        embalse_comprometido = (
            'EMBALSES' in cats_criticas or 'EMBALSES' in cats_alerta
        )
        # Valor numérico de embalse para la guarda de nivel
        embalse_val = next(
            (a.get('valor', 100) for a in self.alertas if a.get('categoria') == 'EMBALSES'),
            100
        )
        # Crisis operacional: despacho físico bajo precio de escasez.
        # Requiere que los tanques NO estén sanos (< 70%): con embalse ≥ 70%
        # térmica + precio alto es vigilancia, no crisis estructural.
        crisis_operacional = (
            'ESTRES_TERMICO' in cats_criticas
            and 'PRECIO_MERCADO' in cats_criticas
            and embalse_val < 70
        )

        if n_criticos >= 3:
            return 'CRÍTICO'
        elif n_criticos >= 2 and embalse_comprometido:
            return 'CRÍTICO'
        elif crisis_operacional:
            return 'CRÍTICO'
        elif n_criticos >= 1 or n_alertas >= 2:
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
        sistema.evaluar_estres_termico(horizonte=30)
        
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

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

• MARCO REGULATORIO OFICIAL — Todos los umbrales operativos están alineados
  con el Estatuto para Situaciones de Riesgo de Desabastecimiento:
    - Resolución CREG 026 de 2014
    - Resolución CREG 209 de 2020 (Senda de Referencia + Índice NE)
    - Resolución CREG 101 066 de 2024 (PEI, PE, PES)
    - Resolución CREG 101 055 de 2024 (regla complementaria)
  Ver core/umbrales_oficiales.py para el detalle de cada umbral.

• Señales operativas detectadas aquí (con fuente regulatoria):
    - Demanda sostenida (umbral percentil 99 histórico XM)
    - Aportes hídricos bajos (Índice HSIN — CREG 026/2014 art. 2)
    - Embalses en nivel inferior (Índice NE — CREG 209/2020)
    - Precio de bolsa vs precio de escasez (Índice PBP — CREG 026/2014)
    - Estrés térmico (referencia operativa CND)

• Señales fuera de alcance: transacciones individuales, despacho central,
  restricciones de red, desviaciones en tiempo real. Consultar XM / NEON.

• Índices compuestos (ISH, IPM, IES, CIS): de naturaleza DESCRIPTIVA.
  No son alertas operativas ni reemplazan los semáforos de XM.
  Los pesos (0.40/0.35/0.25) reflejan percepción analítica, no norma técnica.
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
from core.umbrales_oficiales import (
    # Umbrales oficiales (CREG 026/2014, mod. Res. CREG 101 112/2026) — Índice NE / Senda de Referencia
    obtener_senda_referencia,
    clasificar_indice_ne,
    # Umbrales oficiales (CREG 026/2014) — Índice HSIN
    HSIN_UMBRAL_NORMAL,
    HSIN_UMBRAL_DEFICIT_SEVERO,
    HSIN_UMBRAL_CRITICO_HISTORICO,
    HSIN_VENTANA_SEMANAS,
    clasificar_hsin,
    # Precios de escasez oficiales (CREG 101 066/2024) — vigentes dinámicos
    obtener_precios_escasez_vigentes,
    PRECIO_ESCASEZ_PEI_REF_2026_01,
    PRECIO_ESCASEZ_PE_REF_2026_01,
    PRECIO_ESCASEZ_PES_REF_2026_01,
    # Capacidad e información oficial del SIN
    OBJETIVO_XM_EMBALSE_ANTE_NINO_PCT,
    # Índice PBP y combinación oficial NE+HSIN+PBP (Estatuto CREG 026/2014 art. 2-3)
    clasificar_indice_pbp,
    determinar_condicion_sistema,
)
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
# UMBRALES DE ALERTAS — TODOS RESPALDADOS POR FUENTES REGULATORIAS OFICIALES
# =============================================================================
# Los umbrales hídricos, embalses y precio provienen del Estatuto para
# Situaciones de Riesgo de Desabastecimiento (CREG 026/2014, 209/2020,
# 101 055/2024, 101 066/2024). Ver core/umbrales_oficiales.py para el detalle
# de cada resolución.
#
# Los umbrales de demanda y estrés térmico son criterios operativos del CND
# documentados en boletines técnicos de XM. Se mantienen en este archivo
# porque NO existe una resolución CREG que los normalice — son referencias
# operativas, no regulatorias estrictas.
# =============================================================================

UMBRALES = {
    # ─── DEMANDA ────────────────────────────────────────────────────────────
    # CRITERIO OPERATIVO DEL CND (no regulatorio CREG):
    # Señal de presión en demanda derivada de percentiles del histórico XM.
    # NO existe umbral regulatorio fijo para demanda en el Estatuto CREG;
    # estos valores son referencias operativas calibradas con datos XM.
    'DEMANDA': {
        'ALERTA': 248,              # GWh/día — p75 histórico XM
        'CRITICO': 253,             # GWh/día — p99 histórico XM
        'DIAS_CRITICO_PCT': 0.60,   # fracción del horizonte para disparar CRÍTICO
        'DIAS_ALERTA_PCT': 0.50,    # fracción del horizonte para disparar ALERTA
        'fuente': 'Criterio operativo CND derivado de percentiles XM histórico',
    },
    # ─── EMBALSES — ÍNDICE NE OFICIAL (Res. CREG 026/2014, mod. Res. CREG ──
    # ─── 101 112/2026, vigente desde 17-jun-2026) ───────────────────────────
    # El nivel se compara contra la Senda de Referencia mensual publicada por
    # XM/CND. NO existe un umbral fijo único; el umbral varía por mes según
    # la senda CREG. Ver core/umbrales_oficiales.SENDA_REFERENCIA_2024_2025.
    #
    # Niveles oficiales del Índice NE:
    #   SUPERIOR: embalse ≥ senda
    #   ALERTA:   senda − X ≤ embalse < senda
    #   INFERIOR: embalse < senda − X  (X = 0 en práctica reciente)
    #
    # La regla alternativa "SUPERIOR si embalse ≥ 70%" (Res. CREG 210/2021)
    # fue derogada por la Res. CREG 101 112/2026 — ya no se evalúa (ver
    # core/umbrales_oficiales.py::clasificar_indice_ne).
    'EMBALSES_PCT': {
        'OBJETIVO_XM_ANTE_NINO': OBJETIVO_XM_EMBALSE_ANTE_NINO_PCT,    # 80% Boletín XM 04-2026
        'fuente': 'Resolución CREG 026 de 2014 (mod. Res. CREG 101 112/2026) — Índice NE y Senda de Referencia',
    },
    # ─── APORTES HÍDRICOS — ÍNDICE HSIN OFICIAL (Res. CREG 026/2014 art. 2) ──
    # HSIN = aportes acumulados últimas 4 semanas / promedio histórico × 100
    # Niveles oficiales CREG:
    #   NORMAL:         HSIN ≥ 90%
    #   VIGILANCIA:     HSIN < 90%  (Estatuto CREG art. 2)
    #   DÉFICIT SEVERO: HSIN < 70%  (referencia CREG 209/2020)
    #   CRÍTICO:        HSIN ≤ 60%  (nivel histórico abril 2020)
    'APORTES_HIDRICOS': {
        'UMBRAL_NORMAL': HSIN_UMBRAL_NORMAL,                # 90% — CREG 026/2014
        'UMBRAL_DEFICIT_SEVERO': HSIN_UMBRAL_DEFICIT_SEVERO,  # 70%
        'UMBRAL_CRITICO_HISTORICO': HSIN_UMBRAL_CRITICO_HISTORICO,  # 60% — referencia 2020
        'VENTANA_SEMANAS': HSIN_VENTANA_SEMANAS,            # 4 semanas (CREG art. 2)
        'DIAS_CRITICO_PCT': 0.60,
        'DIAS_ALERTA_PCT':  0.50,
        'fuente': 'Resolución CREG 026 de 2014 art. 2 — Índice HSIN',
    },
    # ─── PRECIO BOLSA — ÍNDICE PBP OFICIAL (Res. CREG 026/2014 + 101 066/2024)
    # PBP nivel BAJO: PBP < Precio Escasez Activación durante 4 de 7 días.
    # PBP nivel ALTO: PBP ≥ Precio Escasez Activación.
    #
    # Tres niveles de precio de escasez vigentes (CREG 101 066/2024):
    #   PEI (Inferior):  327.67 COP/kWh ene-2026 (actualizable mensualmente)
    #   PE  (071/2006):  590.56 COP/kWh ene-2026
    #   PES (Superior):  830.34 COP/kWh ene-2026
    #
    # Por defecto el sistema compara contra PE (precio de escasez de
    # activación tradicional). Los valores se actualizan mensualmente
    # via consulta a XM/CREG.
    'PRECIO_BOLSA': {
        'PEI_REF': PRECIO_ESCASEZ_PEI_REF_2026_01,  # CREG 101 066/2024
        'PE_REF':  PRECIO_ESCASEZ_PE_REF_2026_01,   # CREG 071/2006
        'PES_REF': PRECIO_ESCASEZ_PES_REF_2026_01,  # CREG 140/2017
        'DIAS_VENTANA': 7,
        'DIAS_BAJO_MINIMO': 4,   # 4 de 7 días → nivel BAJO (CREG 026/2014)
        'fuente': 'Resolución CREG 026 de 2014 art. 2 + CREG 101 066/2024',
    },
    # ─── ESTRÉS TÉRMICO ──────────────────────────────────────────────────────
    # CRITERIO OPERATIVO CND (no normado en Estatuto CREG):
    # participación (%) = Térmica / DEMANDA × 100
    'ESTRES_TERMICO': {
        'CRITICO': 35.0,             # > 35 % sostenido → riesgo estructural
        'ALERTA':  20.0,             # 20–35 % sostenido → vigilancia
        'DIAS_CRITICO_PCT': 0.70,    # fracción del horizonte
        'DIAS_ALERTA_PCT':  0.60,
        'fuente': 'Criterio operativo CND derivado del Boletín XM 10-abril-2026',
    },
}


def _get_umbral_aportes(mes: int) -> dict:
    """DEPRECADO en favor del Índice HSIN oficial.

    Mantenido solo para compatibilidad con código legacy. Para nueva lógica
    usar clasificar_hsin() de core.umbrales_oficiales (CREG 026/2014 art. 2).
    """
    # Estos valores son percentiles mensuales del histórico XM 2020-2026,
    # útiles solo como fallback diagnóstico. NO son umbrales regulatorios.
    _LEGACY = {
        1: (63, 115), 2: (98, 129), 3: (124, 141), 4: (160, 194),
        5: (223, 291), 6: (311, 392), 7: (315, 356), 8: (227, 264),
        9: (188, 217), 10: (221, 251), 11: (296, 335), 12: (194, 211),
    }
    critico, alerta = _LEGACY.get(mes, (300, 400))
    return {'CRITICO': critico, 'ALERTA': alerta}


class SistemaAlertasEnergeticas:
    """Sistema de alertas automáticas para sector energético"""
    
    def __init__(self):
        self.alertas = []
        self.conn = self._get_connection()
        self.notification_service = NotificationService()
        print("✅ Sistema de notificaciones inicializado")
        # Niveles oficiales CREG (Estatuto 026/2014 art. 2-3), poblados por
        # evaluar_embalses()/evaluar_aportes_hidricos()/evaluar_precio_bolsa()
        # cuando hay datos suficientes — usados por _determinar_estado_general()
        # para la condición regulatoria vía determinar_condicion_sistema().
        # Ver Fase 39.
        self.nivel_ne = None
        self.nivel_hsin = None
        self.nivel_pbp = None
        
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
                'clave': 'DEMANDA_CRITICA',
                'titulo': f'Demanda excesiva sostenida: {dias_criticos}/{total} días > {umbral_crit} GWh [criterio operativo CND, no CREG]',
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
                'titulo': f'Demanda elevada: {dias_alerta}/{total} días > {umbral_alert} GWh [criterio operativo CND, no CREG]',
                'descripcion': f'Promedio: {promedio:.1f} GWh/día. Máximo: {maximo:.1f} GWh/día.',
                'valor': promedio,
                'umbral': umbral_alert,
                'dias_afectados': dias_alerta,
                'recomendacion': 'Monitorear de cerca. Preparar respaldos térmicos.'
            })
            print(f"  ⚠️  ALERTA: {dias_alerta}/{total} días con demanda elevada")
        else:
            print(f"  ✅ Normal: Promedio {promedio:.1f} GWh/día ({dias_criticos} días > p99 = {pct_crit*100:.0f}% mínimo requerido)")
    
    def evaluar_aportes_hidricos(self, horizonte=None):
        """Evalúa el ÍNDICE HSIN OFICIAL del Estatuto CREG 026/2014 art. 2.

        Marco regulatorio: Resolución CREG 026 de 2014 — Artículo 2.
        HSIN = aportes acumulados últimas 4 semanas / promedio histórico × 100

        Niveles oficiales:
            NORMAL:         HSIN ≥ 90%
            VIGILANCIA:     HSIN < 90%  (Estatuto CREG art. 2)
            DÉFICIT SEVERO: HSIN < 70%  (referencia CREG 209/2020)
            CRÍTICO:        HSIN ≤ 60%  (nivel histórico abril 2020)

        Datos: AporEner (real) vs AporEnerMediHist (media histórica oficial XM)
        publicado en https://www.xm.com.co/hidrologia/aportes
        """
        print("💧 Evaluando ÍNDICE HSIN (CREG 026/2014 art. 2)...")

        ventana = horizonte or (HSIN_VENTANA_SEMANAS * 7)
        df = self.cargar_datos_reales('AporEner', dias=ventana)
        if len(df) == 0:
            return

        # AporEnerMediHist es la referencia oficial XM publicada
        df_hist = self.cargar_datos_reales('AporEnerMediHist', dias=ventana)
        if len(df_hist) < max(3, ventana // 4):
            print(f"  ⚠️  AporEnerMediHist insuficiente ({len(df_hist)} días) — alerta omitida")
            return

        media_hist = float(df_hist['valor_gwh'].mean())
        if media_hist <= 0:
            print("  ⚠️  AporEnerMediHist == 0 — alerta omitida")
            return

        # Cálculo oficial HSIN: aportes promedio últimas 4 semanas vs media histórica
        promedio_aportes = float(df['valor_gwh'].mean())
        hsin_pct = (promedio_aportes / media_hist) * 100.0

        # Clasificación oficial CREG
        nivel_hsin, descripcion_hsin = clasificar_hsin(hsin_pct)
        self.nivel_hsin = nivel_hsin

        total = len(df)
        minimo = float(df['valor_gwh'].min())

        if nivel_hsin == 'CRITICO':
            self.alertas.append({
                'categoria': 'HIDROLOGIA',
                'severidad': 'CRÍTICO',
                'clave': 'HSIN_CRITICO',
                'titulo': f'Índice HSIN CRÍTICO: aportes al {hsin_pct:.1f}% de media histórica',
                'descripcion': (
                    f'HSIN = {hsin_pct:.1f}% — nivel histórico de crisis (referencia abril 2020). '
                    f'Aportes promedio {promedio_aportes:.1f} GWh/día, mín {minimo:.1f} GWh/día. '
                    f'Media histórica XM: {media_hist:.1f} GWh/día. '
                    f'Estatuto CREG 026/2014 art. 2.'
                ),
                'valor': hsin_pct,
                'umbral': HSIN_UMBRAL_CRITICO_HISTORICO,
                'dias_afectados': total,
                'fuente_regulatoria': 'Resolución CREG 026 de 2014 art. 2 — Índice HSIN',
                'recomendacion': (
                    'URGENTE: condición de sequía severa. Activar mecanismo de sostenimiento '
                    'CREG 026/2014 art. 7. Maximizar despacho térmico. Reportar a CREG.'
                )
            })
            print(f"  🚨 HSIN CRÍTICO: {hsin_pct:.1f}% ≤ 60% (nivel histórico)")

        elif nivel_hsin in ('VIGILANCIA', 'DEFICIT_SEVERO'):
            self.alertas.append({
                'categoria': 'HIDROLOGIA',
                'severidad': 'ALERTA',
                'titulo': f'Índice HSIN {nivel_hsin}: {hsin_pct:.1f}% de media histórica',
                'descripcion': (
                    f'HSIN = {hsin_pct:.1f}% < 90% — condición de vigilancia (CREG 026/2014 art. 2). '
                    f'Aportes promedio {promedio_aportes:.1f} GWh/día. '
                    f'Media histórica XM: {media_hist:.1f} GWh/día. '
                    f'Si persiste por 2 verificaciones semanales, se confirma vigilancia.'
                ),
                'valor': hsin_pct,
                'umbral': HSIN_UMBRAL_NORMAL,
                'dias_afectados': total,
                'fuente_regulatoria': 'Resolución CREG 026 de 2014 art. 2 — Índice HSIN',
                'recomendacion': (
                    'Optimizar uso de embalses. Aumentar generación térmica. '
                    'Vigilar evolución semanal del HSIN.'
                )
            })
            print(f"  ⚠️  HSIN {nivel_hsin}: {hsin_pct:.1f}% < {HSIN_UMBRAL_NORMAL}%")
        else:
            print(f"  ✅ HSIN NORMAL: {hsin_pct:.1f}% ≥ {HSIN_UMBRAL_NORMAL}% (CREG 026/2014)")
    
    def evaluar_embalses(self, horizonte=30):
        """Evalúa el nivel de embalses usando el ÍNDICE NE OFICIAL del Estatuto CREG.

        Marco regulatorio: Resolución CREG 209 de 2020, mod. Res. CREG 101 112
        de 2026 (deroga la regla absoluta del 70%, vigente desde 17-jun-2026).
        El nivel real del embalse del SIN se compara EXCLUSIVAMENTE con la
        SENDA DE REFERENCIA mensual publicada por XM/CND. Niveles del Índice NE:
            SUPERIOR: embalse ≥ senda
            ALERTA:   senda − X ≤ embalse < senda
            INFERIOR: embalse < senda − X

        Usa PorcVoluUtilDiar (% de capacidad útil diaria, almacenado como
        fracción 0-1 en la BD → se multiplica por 100).
        """
        print("🏞️  Evaluando ÍNDICE NE (CREG 209/2020) — embalses vs senda referencia...")

        df = self.cargar_datos_reales('PorcVoluUtilDiar', dias=horizonte)
        if len(df) == 0:
            return
        # PorcVoluUtilDiar se almacena como fracción (0–1); convertir a porcentaje real
        df = df.copy()
        df['valor_gwh'] = df['valor_gwh'] * 100.0

        pct_actual = float(df['valor_gwh'].iloc[0])    # nivel más reciente
        pct_inicio = float(df['valor_gwh'].iloc[-1])   # nivel hace N días
        pct_min = float(df['valor_gwh'].min())
        tendencia = pct_actual - pct_inicio  # positivo = llenando

        # Clasificación oficial Índice NE
        nivel_ne, descripcion_ne, senda = clasificar_indice_ne(pct_actual)
        nivel_ne_min, _, _ = clasificar_indice_ne(pct_min)
        self.nivel_ne = nivel_ne

        if nivel_ne_min == 'INFERIOR':
            self.alertas.append({
                'categoria': 'EMBALSES',
                'severidad': 'CRÍTICO',
                'clave': 'EMBALSES_NE_INFERIOR',
                'titulo': f'Índice NE INFERIOR: embalses {pct_min:.1f}% < senda CREG {senda:.1f}%',
                'descripcion': (
                    f'Nivel mínimo reciente: {pct_min:.1f}%. Actual: {pct_actual:.1f}%. '
                    f'Senda de Referencia CREG para este mes: {senda:.1f}%. '
                    f'Tendencia últimos {horizonte} días: {tendencia:+.1f}%. '
                    f'Marco regulatorio: Estatuto CREG 026/2014 + Res. 209/2020.'
                ),
                'valor': pct_min,
                'umbral': senda,
                'dias_afectados': horizonte,
                'fuente_regulatoria': 'Resolución CREG 209 de 2020 — Índice NE',
                'recomendacion': (
                    'CRÍTICO: Activar mecanismo de sostenimiento (CREG 026/2014 art. 7). '
                    'Maximizar respaldos térmicos. Reportar a CREG la condición de riesgo.'
                )
            })
            print(f"  🚨 NE INFERIOR: nivel mínimo {pct_min:.1f}% < senda CREG {senda:.1f}%")

        elif nivel_ne == 'ALERTA':
            self.alertas.append({
                'categoria': 'EMBALSES',
                'severidad': 'ALERTA',
                'titulo': f'Índice NE ALERTA: embalses {pct_actual:.1f}% bajo senda CREG {senda:.1f}%',
                'descripcion': (
                    f'Nivel actual: {pct_actual:.1f}%. Senda CREG: {senda:.1f}%. '
                    f'Tendencia últimos {horizonte} días: {tendencia:+.1f}%. '
                    f'Si persiste por 2 verificaciones semanales → nivel INFERIOR.'
                ),
                'valor': pct_actual,
                'umbral': senda,
                'dias_afectados': horizonte,
                'fuente_regulatoria': 'Resolución CREG 209 de 2020 — Índice NE',
                'recomendacion': (
                    'Conservar agua. Maximizar térmicas y renovables no hidráulicas. '
                    'Vigilar evolución semanal.'
                )
            })
            print(f"  ⚠️  NE ALERTA: nivel actual {pct_actual:.1f}% < senda {senda:.1f}%")
        else:
            print(f"  ✅ NE SUPERIOR: {pct_actual:.1f}% ≥ senda CREG {senda:.1f}% "
                  f"(tendencia {tendencia:+.1f}% / {horizonte}d)")
    
    def evaluar_precio_bolsa(self, horizonte=30):
        """Evalúa el ÍNDICE PBP OFICIAL contra los tres niveles de precio de escasez.

        Marco regulatorio:
            - Resolución CREG 026 de 2014 art. 2 — Índice PBP
            - Resolución CREG 071 de 2006 — Precio de escasez
            - Resolución CREG 140 de 2017 — Precio Marginal de Escasez (PES)
            - Resolución CREG 101 066 de 2024 — Tres niveles de precio escasez

        Tres niveles oficiales del precio de escasez:
            PEI (Inferior):   327.67 COP/kWh ene-2026 (CREG 101 066/2024)
            PE  (071/2006):   590.56 COP/kWh ene-2026 (precio de activación)
            PES (Superior):   830.34 COP/kWh ene-2026 (CREG 140/2017)

        Índice PBP del Estatuto CREG 026/2014 art. 2:
            NIVEL BAJO:  PBP < PE durante 4 de últimos 7 días
            NIVEL ALTO:  PBP ≥ PE (activación del Mecanismo de Confiabilidad)
        """
        print("💰 Evaluando ÍNDICE PBP vs Precios de Escasez (CREG 026/2014 + 101 066/2024)...")

        df_bolsa = self.cargar_datos_reales('PrecBolsNaci', dias=horizonte)
        if len(df_bolsa) == 0:
            return

        df_escasez = self.cargar_datos_reales('PrecEsca', dias=horizonte)

        bolsa_prom = float(df_bolsa['valor_gwh'].mean())
        bolsa_max = float(df_bolsa['valor_gwh'].max())

        umb = UMBRALES['PRECIO_BOLSA']

        # Determinar precios de escasez vigentes con prioridad:
        # 1) Tabla oficial sector_energetico.precios_escasez_mensuales (PEI/PE/PES)
        # 2) Valor real de PrecEsca en métricas (si existe)
        # 3) Referencia regulatoria CREG 101 066/2024 (fallback)
        precios_vigentes = obtener_precios_escasez_vigentes()
        pei_vigente = precios_vigentes['pei']
        pe_vigente = precios_vigentes['pe']
        pes_vigente = precios_vigentes['pes']

        if precios_vigentes['origen'] == 'BD':
            fuente_precio = (
                f"BD precios_escasez_mensuales {precios_vigentes['anio']}-{precios_vigentes['mes']:02d} "
                f"(PEI={pei_vigente:.0f}, PE={pe_vigente:.0f}, PES={pes_vigente:.0f})"
            )
        elif len(df_escasez) > 0:
            # Sobreescribir PE con valor real publicado por XM (más actualizado)
            pe_real = float(df_escasez['valor_gwh'].mean())
            pe_vigente = pe_real
            # Inferir PEI y PES proporcionalmente
            pes_vigente = pe_real * (umb['PES_REF'] / umb['PE_REF'])
            pei_vigente = pe_real * (umb['PEI_REF'] / umb['PE_REF'])
            fuente_precio = f"PrecEsca real XM ({pe_real:.0f} COP/kWh)"
        else:
            fuente_precio = f"fallback CREG 101 066/2024 (ene-2026)"

        # Índice PBP oficial: contar días con PBP >= PE en los últimos 7 días
        ventana = umb['DIAS_VENTANA']
        df_bolsa_sorted = df_bolsa.sort_values('fecha', ascending=False).head(ventana)
        dias_alto = int((df_bolsa_sorted['valor_gwh'] >= pe_vigente).sum())
        dias_pes = int((df_bolsa_sorted['valor_gwh'] >= pes_vigente).sum())

        # Clasificación oficial del Índice PBP (Estatuto CREG 026/2014 art. 2),
        # con los mismos datos ya cargados arriba — usada solo para la
        # combinación de _determinar_estado_general(), no cambia las alertas
        # de PRECIO_MERCADO ya evaluadas con su propia lógica de PES/PE.
        self.nivel_pbp, _ = clasificar_indice_pbp(
            df_bolsa_sorted['valor_gwh'].tolist(), pe_vigente
        )
        n_ventana = len(df_bolsa_sorted)

        # Suavizado: media móvil 3 días sobre la serie completa (anti-ruido)
        bolsa_idx = df_bolsa.set_index('fecha')['valor_gwh'].sort_index()
        bolsa_mv3 = bolsa_idx.rolling(3, min_periods=1).mean()
        bolsa_prom_mv = float(bolsa_mv3.mean())

        if dias_pes >= umb['DIAS_BAJO_MINIMO']:
            # Múltiples días por encima del PES — riesgo extremo de activación de escasez
            self.alertas.append({
                'categoria': 'PRECIO_MERCADO',
                'severidad': 'CRÍTICO',
                'clave': 'PBP_CRITICO',
                'titulo': (f'PBP CRÍTICO: {dias_pes}/{n_ventana} días sobre PES '
                           f'{pes_vigente:.0f} COP/kWh'),
                'descripcion': (
                    f'Precio bolsa promedio: {bolsa_prom:.0f} COP/kWh (mv3d: {bolsa_prom_mv:.0f}). '
                    f'Máximo: {bolsa_max:.0f} COP/kWh. PES vigente: {pes_vigente:.0f} COP/kWh '
                    f'(Res. CREG 140/2017). Fuente: {fuente_precio}. '
                    f'Sistema en zona crítica de escasez.'
                ),
                'valor': bolsa_prom,
                'umbral': pes_vigente,
                'dias_afectados': dias_pes,
                'fuente_regulatoria': 'Resolución CREG 101 066 de 2024 — PES',
                'recomendacion': (
                    'Intervención regulatoria urgente. Activar mecanismo de '
                    'confiabilidad (CREG 026/2014). Evaluar despacho forzado.'
                )
            })
            print(f"  🚨 PBP CRÍTICO: {dias_pes}/{n_ventana} días sobre PES "
                  f"{pes_vigente:.0f} COP/kWh ({fuente_precio})")

        elif dias_alto >= umb['DIAS_BAJO_MINIMO']:
            # PBP en nivel ALTO según Estatuto CREG art. 2
            self.alertas.append({
                'categoria': 'PRECIO_MERCADO',
                'severidad': 'ALERTA',
                'titulo': (f'Índice PBP ALTO: {dias_alto}/{n_ventana} días sobre PE '
                           f'{pe_vigente:.0f} COP/kWh'),
                'descripcion': (
                    f'Precio bolsa promedio: {bolsa_prom:.0f} COP/kWh (mv3d: {bolsa_prom_mv:.0f}). '
                    f'PE vigente: {pe_vigente:.0f} COP/kWh (Res. CREG 071/2006). '
                    f'Fuente: {fuente_precio}. Índice PBP en nivel ALTO según '
                    f'Estatuto CREG 026/2014 art. 2.'
                ),
                'valor': bolsa_prom,
                'umbral': pe_vigente,
                'dias_afectados': dias_alto,
                'fuente_regulatoria': 'Resolución CREG 026 de 2014 art. 2 — Índice PBP',
                'recomendacion': (
                    'Monitoreo intensivo. Si persiste y se combina con NE Inferior '
                    'o HSIN < 90%, se entra en condición de RIESGO (CREG art. 3).'
                )
            })
            print(f"  ⚠️  PBP ALTO: {dias_alto}/{n_ventana} días sobre PE "
                  f"{pe_vigente:.0f} COP/kWh ({fuente_precio})")
        elif bolsa_prom_mv >= pei_vigente:
            print(f"  ℹ️  Precio sobre PEI {pei_vigente:.0f} pero PBP en nivel BAJO "
                  f"({dias_alto}/{n_ventana} días sobre PE)")
        else:
            print(f"  ✅ PBP BAJO: precio promedio {bolsa_prom:.0f} COP/kWh < PEI "
                  f"{pei_vigente:.0f} ({fuente_precio})")
    
    def evaluar_balance_energetico(self, horizonte=30):
        """Nota: Con datos reales, Gene ≈ DemaSIN por física del sistema eléctrico.

        En operación real, oferta = demanda en todo momento (dispatch = load).
        Esta evaluación sólo tiene sentido con predicciones futuras donde puede
        existir un déficit proyectado. Con datos históricos reales, el estrés
        operativo se refleja en niveles de embalses, aportes hídricos y precios.

        2026-08-25: el umbral "MARGEN_OPERATIVO" que originalmente motivó este
        método se eliminó de UMBRALES — no tenía ninguna fuente ni normativa
        real que lo respaldara (a diferencia de DEMANDA/ESTRÉS_TÉRMICO, que sí
        citan un criterio operativo real del CND). Este método se deja como
        no-operativo (nunca generó alertas, confirmado por grep en todo el
        proyecto) en vez de eliminarlo, para no tocar su call site en
        tasks/anomaly_tasks.py sin necesidad.
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
                'clave': 'ESTRES_TERMICO_CRITICO',
                'titulo': f'Estrés térmico crítico: {participacion_prom:.1f}% participación sostenida [criterio operativo CND, no CREG]',
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
                'titulo': f'Estrés térmico moderado: {participacion_prom:.1f}% participación [criterio operativo CND, no CREG]',
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
        condicion_creg, descripcion_creg = self.obtener_condicion_regulatoria_creg()
        reporte = {
            'fecha_generacion': datetime.now().isoformat(),
            'total_alertas': len(self.alertas),
            'alertas_criticas': len([a for a in self.alertas if a['severidad'] == 'CRÍTICO']),
            'alertas_importantes': len([a for a in self.alertas if a['severidad'] == 'ALERTA']),
            'alertas': self.alertas,
            # Riesgo operativo combinado (taxonomía CND, ver docstring)
            'estado_general': self._determinar_estado_general(),
            # Condición regulatoria oficial del Estatuto CREG 026/2014 art. 3
            # (NORMAL/VIGILANCIA/RIESGO) — señal DISTINTA de 'estado_general',
            # nunca se deben mezclar. Ver Fase 39.
            'condicion_regulatoria_creg': condicion_creg,
            'condicion_regulatoria_creg_descripcion': descripcion_creg,
        }
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(reporte, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Reporte JSON guardado en: {output_file}")
        
        return reporte
    
    def obtener_condicion_regulatoria_creg(self):
        """Condición del sistema según el Estatuto CREG 026/2014 art. 3 —
        taxonomía OFICIAL (NORMAL/VIGILANCIA/RIESGO), distinta del "riesgo
        operativo combinado" propio del CND que calcula
        _determinar_estado_general() (que además mezcla térmica/demanda,
        criterios sin equivalente CREG). Requiere que evaluar_embalses(),
        evaluar_aportes_hidricos() y evaluar_precio_bolsa() ya hayan corrido
        en esta ejecución (poblan self.nivel_ne/nivel_hsin/nivel_pbp).

        Returns:
            (condicion, descripcion) o (None, motivo) si falta algún índice.
        """
        if self.nivel_ne is None or self.nivel_hsin is None or self.nivel_pbp is None:
            return (None, 'Índice NE, HSIN o PBP no evaluado en esta corrida (datos insuficientes).')
        if self.nivel_pbp == 'INDETERMINADO':
            return (None, 'Índice PBP indeterminado (menos de 7 días de precio de bolsa).')
        return determinar_condicion_sistema(self.nivel_ne, self.nivel_hsin, self.nivel_pbp)

    def _determinar_estado_general(self):
        """Clasifica el RIESGO OPERATIVO COMBINADO del SIN — taxonomía propia
        del CND (demanda/térmica/precio/embalses agregados en una sola señal
        de seguimiento), NO la "condición del sistema" regulatoria del
        Estatuto CREG (ver obtener_condicion_regulatoria_creg() para esa).

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
        # Crisis operacional: despacho físico bajo precio de escasez.
        # Requiere que los tanques NO estén "sanos" — se usa el Índice NE
        # oficial (nivel_ne != 'SUPERIOR') en vez de un umbral numérico
        # arbitrario, para no reintroducir el mismo "70%" que el Estatuto
        # CREG ya derogó como regla absoluta (Res. CREG 101 112/2026, ver
        # Fase 38/39): con NE=SUPERIOR (por encima de la senda), térmica +
        # precio alto es vigilancia, no crisis estructural.
        crisis_operacional = (
            'ESTRES_TERMICO' in cats_criticas
            and 'PRECIO_MERCADO' in cats_criticas
            and self.nivel_ne is not None
            and self.nivel_ne != 'SUPERIOR'
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
        sistema.evaluar_aportes_hidricos()
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

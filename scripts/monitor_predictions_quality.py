#!/usr/bin/env python3
"""
FASE 4.A — Monitoreo ex‑post de calidad de predicciones
=========================================================

Compara las predicciones vigentes en BD contra datos reales (metrics),
calcula MAPE y RMSE ex‑post, guarda histórico en
`predictions_quality_history` y emite alertas.

Ejecución:
    python scripts/monitor_predictions_quality.py

Puede integrarse en cron (ej. diario a las 08:00) una vez validado.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error
import urllib.request
import urllib.parse
import warnings
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════

UMBRAL_MAPE_CRITICO = 0.50      # Alerta si MAPE ex‑post > 50%
FACTOR_DRIFT = 2.0              # Alerta si MAPE ex‑post > 2× MAPE de entrenamiento
MIN_DIAS_OVERLAP = 3            # Mínimo de días solapados para evaluar

# ── Mapeo fuente (predictions.fuente) → query de datos reales ──
# Cada entrada define cómo obtener el dato real para esa fuente.
# Para métricas sectoriales se replica la lógica de METRICAS_CONFIG.
# Para fuentes de generación (postgres.py) se usa JOIN con catalogos.

FUENTES_MAPPING = {
    # ── Métricas sectoriales (train_predictions_sector_energetico.py) ──
    'GENE_TOTAL': {
        'metrica': 'Gene',
        'agg': 'SUM',
        'entidad': 'Sistema',
    },
    'DEMANDA': {
        'metrica': 'DemaReal',
        'agg': 'SUM',
        'prefer_sistema': True,
    },
    'PRECIO_BOLSA': {
        'metrica': 'PrecBolsNaci',
        'agg': 'AVG',
        'entidad': 'Sistema',
    },
    'PRECIO_ESCASEZ': {
        'metrica': 'PrecEsca',
        'agg': 'AVG',
    },
    'APORTES_HIDRICOS': {
        'metrica': 'AporEner',
        'agg': 'SUM',
    },
    'EMBALSES': {
        'metrica': 'CapaUtilDiarEner',
        'agg': 'SUM',
        'entidad': 'Sistema',
    },
    'EMBALSES_PCT': {
        'metrica': 'PorcVoluUtilDiar',
        'agg': 'AVG',
        'entidad': 'Sistema',
        'escala': 100,
    },
    'PERDIDAS': {
        'metrica': 'PerdidasEner',
        'agg': 'SUM',
        'prefer_sistema': True,
    },

    # ── Fuentes de generación (train_predictions_postgres.py) ──
    'Hidráulica': {'tipo_catalogo': 'HIDRAULICA'},
    'Térmica':    {'tipo_catalogo': 'TERMICA'},
    'Eólica':     {'tipo_catalogo': 'EOLICA'},
    'Solar':      {'tipo_catalogo': 'SOLAR'},
    'Biomasa':    {'tipo_catalogo': 'COGENERADOR'},
}


# ═══════════════════════════════════════════════════════════════════════
# FUNCIONES
# ═══════════════════════════════════════════════════════════════════════

def get_postgres_connection():
    """Reutiliza el ConnectionManager del proyecto."""
    from infrastructure.database.connection import PostgreSQLConnectionManager
    manager = PostgreSQLConnectionManager()
    conn_params = {
        'host': manager.host,
        'port': manager.port,
        'database': manager.database,
        'user': manager.user,
    }
    if manager.password:
        conn_params['password'] = manager.password
    return psycopg2.connect(**conn_params)


def crear_tabla_si_no_existe(conn):
    """Crea la tabla predictions_quality_history si no existe."""
    ddl = """
    CREATE TABLE IF NOT EXISTS predictions_quality_history (
        id              SERIAL PRIMARY KEY,
        fuente          TEXT NOT NULL,
        fecha_evaluacion TIMESTAMP NOT NULL DEFAULT now(),
        fecha_desde     DATE NOT NULL,
        fecha_hasta     DATE NOT NULL,
        dias_overlap    INTEGER NOT NULL,
        mape_expost     DOUBLE PRECISION,
        rmse_expost     DOUBLE PRECISION,
        mape_train      DOUBLE PRECISION,
        rmse_train      DOUBLE PRECISION,
        modelo          TEXT,
        notas           TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_pqh_fuente
        ON predictions_quality_history(fuente);
    CREATE INDEX IF NOT EXISTS idx_pqh_fecha
        ON predictions_quality_history(fecha_evaluacion);
    """
    cur = conn.cursor()
    cur.execute(ddl)
    conn.commit()
    cur.close()
    print("✅ Tabla predictions_quality_history lista\n")


def cargar_predicciones(conn, fuente):
    """Carga predicciones vigentes de una fuente."""
    query = """
    SELECT fecha_prediccion AS fecha,
           valor_gwh_predicho AS predicho,
           mape, rmse, modelo
    FROM predictions
    WHERE fuente = %s
    ORDER BY fecha_prediccion
    """
    df = pd.read_sql_query(query, conn, params=(fuente,))
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df


def cargar_reales_metrica(conn, cfg, fecha_desde, fecha_hasta):
    """Carga datos reales de una métrica sectorial."""
    metrica = cfg['metrica']
    agg_fn = cfg.get('agg', 'SUM')
    entidad = cfg.get('entidad')
    prefer_sistema = cfg.get('prefer_sistema', False)
    escala = cfg.get('escala', 1)

    if entidad:
        query = f"""
        SELECT fecha, {agg_fn}(valor_gwh) AS valor
        FROM metrics
        WHERE metrica = %s AND fecha BETWEEN %s AND %s
          AND entidad = %s AND valor_gwh > 0
        GROUP BY fecha ORDER BY fecha
        """
        params = (metrica, fecha_desde, fecha_hasta, entidad)
    elif prefer_sistema:
        query = f"""
        SELECT fecha,
          CASE WHEN MAX(CASE WHEN entidad='Sistema' THEN 1 ELSE 0 END) = 1
               THEN {agg_fn}(CASE WHEN entidad='Sistema' THEN valor_gwh END)
               ELSE {agg_fn}(valor_gwh)
          END AS valor
        FROM metrics
        WHERE metrica = %s AND fecha BETWEEN %s AND %s AND valor_gwh > 0
        GROUP BY fecha ORDER BY fecha
        """
        params = (metrica, fecha_desde, fecha_hasta)
    else:
        query = f"""
        SELECT fecha, {agg_fn}(valor_gwh) AS valor
        FROM metrics
        WHERE metrica = %s AND fecha BETWEEN %s AND %s AND valor_gwh > 0
        GROUP BY fecha ORDER BY fecha
        """
        params = (metrica, fecha_desde, fecha_hasta)

    df = pd.read_sql_query(query, conn, params=params)
    df['fecha'] = pd.to_datetime(df['fecha'])
    if escala != 1:
        df['valor'] = df['valor'] * escala
    return df


def cargar_reales_generacion(conn, tipo_catalogo, fecha_desde, fecha_hasta):
    """Carga datos reales de una fuente de generación (JOIN con catalogos)."""
    query = """
    SELECT m.fecha, SUM(m.valor_gwh) AS valor
    FROM metrics m
    INNER JOIN catalogos c ON m.recurso = c.codigo
    WHERE c.tipo = %s
      AND m.metrica = 'Gene'
      AND m.fecha BETWEEN %s AND %s
      AND m.valor_gwh > 0
    GROUP BY m.fecha
    ORDER BY m.fecha
    """
    df = pd.read_sql_query(query, conn, params=(tipo_catalogo, fecha_desde, fecha_hasta))
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df


def evaluar_fuente(conn, fuente, cfg):
    """
    Evalúa la calidad ex‑post de una fuente.
    Retorna dict con métricas, o None si no hay overlap.
    """
    df_pred = cargar_predicciones(conn, fuente)
    if df_pred.empty:
        return None, "sin predicciones en BD"

    fecha_desde = df_pred['fecha'].min().date()
    fecha_hasta = df_pred['fecha'].max().date()

    # Cargar datos reales
    if 'tipo_catalogo' in cfg:
        df_real = cargar_reales_generacion(conn, cfg['tipo_catalogo'], fecha_desde, fecha_hasta)
    else:
        df_real = cargar_reales_metrica(conn, cfg, fecha_desde, fecha_hasta)

    if df_real.empty:
        return None, "sin datos reales en el rango de predicción"

    # Merge por fecha
    df_merge = pd.merge(
        df_pred[['fecha', 'predicho']],
        df_real[['fecha', 'valor']],
        on='fecha', how='inner'
    )

    # Filtrar valores reales ≤ 0 (evitar divisiones por cero en MAPE)
    df_merge = df_merge[df_merge['valor'] > 0]

    # ── Filtro de datos parciales ──
    # Los últimos 2-3 días de XM pueden llegar incompletos (ej: DemaReal=48 GWh
    # cuando lo real es ~230 GWh). Si un dato real es < 50% de la mediana de los
    # demás puntos del overlap, se descarta del cálculo ex‑post.
    if len(df_merge) > 3:
        mediana_overlap = df_merge['valor'].median()
        if mediana_overlap > 0:
            umbral_parcial = mediana_overlap * 0.5
            parciales = df_merge[df_merge['valor'] < umbral_parcial]
            if len(parciales) > 0:
                fechas_excl = parciales['fecha'].dt.date.tolist()
                df_merge = df_merge[df_merge['valor'] >= umbral_parcial]
                print(f"  ⚠️  Excluidos {len(parciales)} datos parciales: {fechas_excl}")

    if len(df_merge) < MIN_DIAS_OVERLAP:
        return None, f"solo {len(df_merge)} días de overlap (mín: {MIN_DIAS_OVERLAP})"

    y_real = df_merge['valor'].values
    y_pred = df_merge['predicho'].values

    mape_expost = mean_absolute_percentage_error(y_real, y_pred)
    rmse_expost = float(np.sqrt(mean_squared_error(y_real, y_pred)))

    # MAPE/RMSE de entrenamiento (del batch más reciente)
    mape_train = df_pred['mape'].iloc[0]
    rmse_train = df_pred['rmse'].iloc[0]
    modelo = df_pred['modelo'].iloc[0]

    mape_train = float(mape_train) if mape_train is not None and not pd.isna(mape_train) else None
    rmse_train = float(rmse_train) if rmse_train is not None and not pd.isna(rmse_train) else None

    return {
        'fuente': fuente,
        'fecha_desde': df_merge['fecha'].min().date(),
        'fecha_hasta': df_merge['fecha'].max().date(),
        'dias_overlap': len(df_merge),
        'mape_expost': float(mape_expost),
        'rmse_expost': rmse_expost,
        'mape_train': mape_train,
        'rmse_train': rmse_train,
        'modelo': modelo,
    }, None


def enviar_alerta_telegram(alertas_globales, resumen):
    """
    Envía resumen de alertas por Telegram cuando hay drift o errores críticos.
    Usa urllib (sin dependencia de requests).
    """
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID_ALERTAS', '5084190952')

    if not bot_token:
        print("⚠️  TELEGRAM_BOT_TOKEN no configurado — alerta Telegram omitida")
        return

    fecha = datetime.now().strftime('%Y-%m-%d %H:%M')
    ok_count = len([r for r in resumen if r.get('status') == 'OK'])
    alerta_count = len([r for r in resumen if r.get('status') == 'ALERTA'])
    omitidas_count = len([r for r in resumen if r.get('status') not in ('OK', 'ALERTA')])

    lines = [f"🔔 *Monitoreo Predicciones — {fecha}*"]
    lines.append(f"✅ OK: {ok_count} | ⚠️ Alertas: {alerta_count} | ⏭️ Omitidas: {omitidas_count}")
    lines.append("")

    for a in alertas_globales:
        lines.append(f"• {a}")

    # Detalle de las fuentes con alerta
    lines.append("")
    for r in resumen:
        if r.get('status') == 'ALERTA':
            mt = f"{r['mape_train']:.1%}" if r.get('mape_train') is not None else "N/A"
            lines.append(f"📊 *{r['fuente']}*: MAPE ex\\-post={r['mape_expost']:.1%} vs train={mt} \\({r['dias']}d\\)")

    text = "\n".join(lines)

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'MarkdownV2',
        }).encode('utf-8')
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                print(f"📱 Alerta Telegram enviada a chat {chat_id}")
            else:
                print(f"⚠️  Telegram respondió HTTP {resp.status}")
    except Exception as e:
        # Reintentar sin MarkdownV2 (por si hay caracteres problemáticos)
        try:
            data_plain = urllib.parse.urlencode({
                'chat_id': chat_id,
                'text': text.replace('*', '').replace('\\-', '-').replace('\\(', '(').replace('\\)', ')'),
            }).encode('utf-8')
            req2 = urllib.request.Request(url, data=data_plain)
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                print(f"📱 Alerta Telegram enviada (plain text) a chat {chat_id}")
        except Exception as e2:
            print(f"⚠️  Error enviando Telegram: {e2}")


def generar_alertas(resultado):
    """Genera alertas basadas en el resultado de evaluación."""
    alertas = []
    mape_ex = resultado['mape_expost']
    mape_tr = resultado['mape_train']

    if mape_ex > UMBRAL_MAPE_CRITICO:
        alertas.append(f"🔴 MAPE ex‑post ({mape_ex:.1%}) > umbral crítico ({UMBRAL_MAPE_CRITICO:.0%})")

    if mape_tr is not None and mape_tr > 0 and mape_ex > FACTOR_DRIFT * mape_tr:
        alertas.append(
            f"🟡 DRIFT: MAPE ex‑post ({mape_ex:.1%}) > {FACTOR_DRIFT:.0f}× MAPE entrenamiento ({mape_tr:.1%})"
        )

    return alertas


def guardar_evaluacion(conn, resultado, notas=""):
    """Inserta resultado en predictions_quality_history."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO predictions_quality_history
            (fuente, fecha_desde, fecha_hasta, dias_overlap,
             mape_expost, rmse_expost, mape_train, rmse_train, modelo, notas)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        resultado['fuente'],
        resultado['fecha_desde'],
        resultado['fecha_hasta'],
        resultado['dias_overlap'],
        resultado['mape_expost'],
        resultado['rmse_expost'],
        resultado['mape_train'],
        resultado['rmse_train'],
        resultado['modelo'],
        notas,
    ))
    conn.commit()
    cur.close()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("📊 MONITOREO EX‑POST DE PREDICCIONES — FASE 4.A")
    print(f"   Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Umbral crítico: {UMBRAL_MAPE_CRITICO:.0%}")
    print(f"   Factor drift: {FACTOR_DRIFT:.0f}×")
    print("=" * 70)

    conn = get_postgres_connection()
    crear_tabla_si_no_existe(conn)

    resumen = []
    alertas_globales = []

    for fuente, cfg in FUENTES_MAPPING.items():
        print(f"\n─── {fuente} ───")

        resultado, motivo = evaluar_fuente(conn, fuente, cfg)

        if resultado is None:
            print(f"  ⏭️  Omitida: {motivo}")
            resumen.append({'fuente': fuente, 'status': motivo})
            continue

        # Mostrar resultados
        mape_tr_str = f"{resultado['mape_train']:.2%}" if resultado['mape_train'] is not None else "N/A"
        print(f"  Overlap: {resultado['dias_overlap']} días "
              f"({resultado['fecha_desde']} → {resultado['fecha_hasta']})")
        print(f"  MAPE ex‑post:  {resultado['mape_expost']:.2%}")
        print(f"  RMSE ex‑post:  {resultado['rmse_expost']:.2f}")
        print(f"  MAPE entrena:  {mape_tr_str}")

        # Alertas
        alertas = generar_alertas(resultado)
        for a in alertas:
            print(f"  {a}")
            alertas_globales.append(f"{fuente}: {a}")

        if not alertas:
            print(f"  ✅ OK")

        # Guardar en BD
        notas_str = "; ".join(alertas) if alertas else "OK"
        guardar_evaluacion(conn, resultado, notas_str)

        resumen.append({
            'fuente': fuente,
            'dias': resultado['dias_overlap'],
            'mape_expost': resultado['mape_expost'],
            'mape_train': resultado['mape_train'],
            'status': 'ALERTA' if alertas else 'OK',
        })

    # ── Resumen final ──
    print("\n" + "=" * 70)
    print("📋 RESUMEN")
    print("=" * 70)

    ok = [r for r in resumen if r.get('status') == 'OK']
    alertas_r = [r for r in resumen if r.get('status') == 'ALERTA']
    omitidas = [r for r in resumen if r.get('status') not in ('OK', 'ALERTA')]

    if ok:
        print(f"\n✅ Sin problemas ({len(ok)}):")
        for r in ok:
            mt = f", train={r['mape_train']:.2%}" if r.get('mape_train') is not None else ""
            print(f"   • {r['fuente']:25s} MAPE ex‑post={r['mape_expost']:.2%}{mt}  ({r['dias']}d)")

    if alertas_r:
        print(f"\n⚠️  Con alertas ({len(alertas_r)}):")
        for r in alertas_r:
            mt = f", train={r['mape_train']:.2%}" if r.get('mape_train') is not None else ""
            print(f"   • {r['fuente']:25s} MAPE ex‑post={r['mape_expost']:.2%}{mt}  ({r['dias']}d)")

    if omitidas:
        print(f"\n⏭️  Omitidas ({len(omitidas)}):")
        for r in omitidas:
            print(f"   • {r['fuente']:25s} {r['status']}")

    print(f"\n{'=' * 70}")
    if alertas_globales:
        print(f"🚨 ALERTAS ACTIVAS: {len(alertas_globales)}")
        for a in alertas_globales:
            print(f"   {a}")
    else:
        print("🟢 Sin alertas activas")

    print(f"\n💾 Resultados guardados en predictions_quality_history")
    print(f"{'=' * 70}\n")

    # ── Enviar alerta Telegram si hay problemas ──
    if alertas_globales:
        enviar_alerta_telegram(alertas_globales, resumen)

    conn.close()


if __name__ == "__main__":
    main()

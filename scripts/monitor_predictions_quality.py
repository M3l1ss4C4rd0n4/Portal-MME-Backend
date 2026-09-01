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

# Fase 41 (2026-08-26): este script se invoca desde 3 rutas distintas —
# cron diario (0 22 * * *), un subproceso lanzado por la tarea Celery
# regenerar_predicciones, y scripts/actualizar_predicciones.sh — y solo la
# ruta de Celery hereda TELEGRAM_BOT_TOKEN (vía EnvironmentFile de
# celery-worker.service). Confirmado en logs/etl/quality_monitor.log que la
# ejecución diaria por cron corría con el entorno vacío y descartaba
# silenciosamente alertas de drift ya calculadas correctamente. Se
# autocarga .env aquí, mismo patrón defensivo (override=True) ya usado en
# tasks/__init__.py, para que funcione sin importar quién lo invoque.
try:
    from dotenv import load_dotenv
    _env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.isfile(_env_file):
        load_dotenv(_env_file, override=True)
except ImportError:
    pass

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


def cargar_predicciones_batches(conn, fuente):
    """
    Carga TODAS las predicciones de una fuente agrupadas por batch
    (fecha_generacion), combinando la tabla viva (predictions) y el
    archivo histórico (predictions_history) poblado por el trigger
    trg_predictions_archive_on_delete. Esto permite evaluar batches ya
    reemplazados por un reentrenamiento posterior, no solo el vigente.
    """
    query = """
    SELECT fecha_prediccion AS fecha, valor_gwh_predicho AS predicho,
           mape, rmse, modelo, fecha_generacion
    FROM predictions
    WHERE fuente = %s
    UNION ALL
    SELECT fecha_prediccion AS fecha, valor_gwh_predicho AS predicho,
           mape, rmse, modelo, fecha_generacion
    FROM predictions_history
    WHERE fuente = %s
    """
    df = pd.read_sql_query(query, conn, params=(fuente, fuente))
    df['fecha'] = pd.to_datetime(df['fecha'])
    df['fecha_generacion'] = pd.to_datetime(df['fecha_generacion'])
    return df


def cargar_evaluaciones_previas(conn, fuente):
    """Overlap ya evaluado por batch (fecha_generacion) para esta fuente,
    para no reevaluar un batch cuyo overlap no creció desde la última corrida."""
    query = """
    SELECT fecha_generacion, MAX(dias_overlap) AS dias_overlap
    FROM predictions_quality_history
    WHERE fuente = %s AND fecha_generacion IS NOT NULL
    GROUP BY fecha_generacion
    """
    df = pd.read_sql_query(query, conn, params=(fuente,))
    return dict(zip(df['fecha_generacion'], df['dias_overlap']))


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


def _evaluar_batch(df_pred, df_real, fuente):
    """
    Aplica la lógica de merge/filtro/MAPE de un solo batch de predicciones
    (todas las filas comparten fecha_generacion) contra los datos reales.
    Retorna dict con métricas, o None si no hay overlap suficiente.
    """
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
                print(f"    ⚠️  Excluidos {len(parciales)} datos parciales: {fechas_excl}")

    if len(df_merge) < MIN_DIAS_OVERLAP:
        return None

    y_real = df_merge['valor'].values
    y_pred = df_merge['predicho'].values

    # ── Para Eólica: filtrar días con generación muy baja (<0.10 GWh) ──
    # En días sin viento la generación cae a 0.01-0.09 GWh. El MAPE explota
    # (ej: real=0.05, pred=0.40 → MAPE=700%) aunque el error absoluto sea
    # pequeño. μ Eólica=0.41 GWh/día → umbral 0.10 GWh = ~25% de la media.
    smape_notas = None
    if fuente == 'Eólica':
        mask_validos = y_real >= 0.10
        n_excluidos = (~mask_validos).sum()
        if n_excluidos > 0 and mask_validos.sum() >= MIN_DIAS_OVERLAP:
            y_real_mape = y_real[mask_validos]
            y_pred_mape = y_pred[mask_validos]
            print(f"    ℹ️  Eólica: {n_excluidos} días <0.10 GWh excluidos del MAPE (días sin viento)")
        else:
            y_real_mape, y_pred_mape = y_real, y_pred
        # SMAPE simétrico como métrica complementaria (rangos 0-1, no explota con ceros)
        smape_val = float(np.mean(
            2 * np.abs(y_pred - y_real) / (np.abs(y_pred) + np.abs(y_real) + 1e-8)
        ))
        smape_notas = f"SMAPE={smape_val:.3f} ({smape_val:.1%}); dias_viento_bajo_excluidos={n_excluidos}"
    else:
        y_real_mape, y_pred_mape = y_real, y_pred

    mape_expost = mean_absolute_percentage_error(y_real_mape, y_pred_mape)  # type: ignore[arg-type]
    rmse_expost = float(np.sqrt(mean_squared_error(y_real, y_pred)))  # type: ignore[arg-type]

    # MAPE/RMSE de entrenamiento (del batch evaluado)
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
        'notas': smape_notas,
    }


def evaluar_fuente(conn, fuente, cfg):
    """
    Evalúa la calidad ex‑post de una fuente, batch por batch (agrupado por
    fecha_generacion). Cada batch archivado en predictions_history se evalúa
    de forma independiente, para no depender de que siga vigente en
    `predictions` — así un reentrenamiento posterior ya no le "gana de mano"
    a la evaluación.
    Retorna (lista_de_resultados, motivo_si_nada_se_pudo_evaluar).
    """
    df_all = cargar_predicciones_batches(conn, fuente)
    if df_all.empty:
        return [], "sin predicciones en BD ni en predictions_history"

    fecha_desde_global = df_all['fecha'].min().date()
    fecha_hasta_global = df_all['fecha'].max().date()

    # Cargar datos reales (una sola vez, cubre el rango de todos los batches)
    if 'tipo_catalogo' in cfg:
        df_real = cargar_reales_generacion(conn, cfg['tipo_catalogo'], fecha_desde_global, fecha_hasta_global)
    else:
        df_real = cargar_reales_metrica(conn, cfg, fecha_desde_global, fecha_hasta_global)

    if df_real.empty:
        return [], "sin datos reales en el rango de predicción"

    ya_evaluados = cargar_evaluaciones_previas(conn, fuente)

    resultados = []
    for fecha_gen, df_pred in df_all.groupby('fecha_generacion', dropna=False):
        resultado = _evaluar_batch(df_pred, df_real, fuente)
        if resultado is None:
            continue

        prev_overlap = ya_evaluados.get(fecha_gen, -1)
        if resultado['dias_overlap'] <= prev_overlap:
            continue  # ya evaluado con igual o mejor overlap, sin novedad

        resultado['fecha_generacion'] = fecha_gen
        resultados.append(resultado)

    if not resultados:
        return [], f"sin batches nuevos con ≥{MIN_DIAS_OVERLAP} días de overlap"

    return resultados, None


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

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
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
             mape_expost, rmse_expost, mape_train, rmse_train, modelo, notas,
             fecha_generacion)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        resultado.get('fecha_generacion'),
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

        resultados, motivo = evaluar_fuente(conn, fuente, cfg)

        if not resultados:
            print(f"  ⏭️  Omitida: {motivo}")
            resumen.append({'fuente': fuente, 'status': motivo})
            continue

        # Cada batch (fecha_generacion) con overlap nuevo se evalúa por separado
        for resultado in resultados:
            fecha_gen = resultado.get('fecha_generacion')
            fecha_gen_str = (
                fecha_gen.strftime('%Y-%m-%d %H:%M')
                if fecha_gen is not None and not pd.isna(fecha_gen) else "N/A"
            )
            print(f"  · Batch fecha_generacion={fecha_gen_str}")

            mape_tr_str = f"{resultado['mape_train']:.2%}" if resultado['mape_train'] is not None else "N/A"
            print(f"    Overlap: {resultado['dias_overlap']} días "
                  f"({resultado['fecha_desde']} → {resultado['fecha_hasta']})")
            print(f"    MAPE ex‑post:  {resultado['mape_expost']:.2%}")
            print(f"    RMSE ex‑post:  {resultado['rmse_expost']:.2f}")
            print(f"    MAPE entrena:  {mape_tr_str}")

            # Alertas
            alertas = generar_alertas(resultado)
            for a in alertas:
                print(f"    {a}")
                alertas_globales.append(f"{fuente}: {a}")

            if not alertas:
                print(f"    ✅ OK")

            # Guardar en BD
            notas_str = "; ".join(alertas) if alertas else "OK"
            if resultado.get('notas'):
                notas_str = resultado['notas'] + ("; " + notas_str if notas_str != "OK" else "")
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

    # ── Verificar drift consecutivo y generar flag de retrain si procede ──
    if verificar_drift_consecutivo(conn, metrica='EMBALSES_PCT', n_dias=3):
        flag_path = '/tmp/drift_retrain_needed.flag'
        with open(flag_path, 'w') as f:
            f.write('EMBALSES_PCT')
        print(f"\n⚠️  DRIFT 3 DÍAS CONSECUTIVOS en EMBALSES_PCT — flag generado: {flag_path}")

    conn.close()


def verificar_drift_consecutivo(conn, metrica: str = 'EMBALSES_PCT', n_dias: int = 3) -> bool:
    """
    Retorna True si hubo drift (mape_expost > mape_train * 2.0) en las últimas
    n_dias evaluaciones Y todas ocurrieron dentro de la ventana reciente
    (últimos n_dias * 2 días calendario). Esto evita que drift histórico
    resuelto dispare retrains espurios.
    """
    try:
        cur = conn.cursor()
        ventana_dias = n_dias * 2  # ventana de búsqueda en calendario
        cur.execute("""
            SELECT COUNT(*) FROM (
                SELECT 1 FROM predictions_quality_history
                WHERE fuente = %s
                  AND mape_expost IS NOT NULL
                  AND mape_train  IS NOT NULL
                  AND mape_expost > mape_train * 2.0
                  AND fecha_evaluacion >= NOW() - INTERVAL '1 day' * %s
                ORDER BY fecha_evaluacion DESC
                LIMIT %s
            ) sub
        """, (metrica, ventana_dias, n_dias))
        count = cur.fetchone()[0]
        return int(count) >= n_dias
    except Exception as e:
        print(f"  ⚠️  verificar_drift_consecutivo error: {e}")
        return False


if __name__ == "__main__":
    main()

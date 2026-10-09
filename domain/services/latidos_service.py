"""
Latidos del sistema — detecta lo que deja de producir.

Este módulo existe por una lista concreta de fallas que duraron meses sin que
nadie las notara:

  * Isolation Forest / PNT: 5,5 meses con la tabla `anomalies` congelada,
    mientras el cron corría cada 6 horas y el log decía "✅".
  * ETL de ArcGIS: meses fallando con ModuleNotFoundError en cada corrida.
  * Bucle de redirecciones del Portal Energético: 29 días, con cuatro
    monitoreos que aceptaban un 301 como "el sitio responde".
  * El Dash del tablero: desde el 2026-09-30 sirviendo código viejo, 12
    commits atrás, porque su reinicio pide contraseña de sudo.
  * ETL de la senda CREG: 68 días fallando a diario por un regex roto.

Todas compartían la misma firma: **el proceso corre, el log crece, y la tabla
no**. Ninguna produjo un error que alguien pudiera ver. 30 de las 35 entradas
del crontab terminan en `>> log 2>&1`, no hay MAILTO, y 26 scripts ETL salen
con código 0 pase lo que pase.

Un latido no pregunta "¿el proceso está vivo?" sino "¿esto sigue produciendo?".
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent.parent


@dataclass
class Latido:
    """Una cosa que debería estar produciendo, y cada cuánto."""
    nombre: str
    que_vigila: str
    max_rezago_horas: float
    critico: bool = False


@dataclass
class Resultado:
    latido: Latido
    rezago_horas: Optional[float]
    detalle: str
    ok: bool
    marca: Optional[datetime] = None


# ── Tablas que deben seguir creciendo ────────────────────────────────────
# El rezago esperado sale del ritmo real de cada fuente, no de un número
# redondo. Donde XM publica con retraso, el margen lo contempla.
LATIDOS_TABLA = [
    # OJO: se vigila que el ETL CORRA Y EVALÚE, no que la tabla crezca.
    # `anomalies` solo recibe filas cuando hay anomalías materiales, así que
    # una tabla sin novedades es el estado normal y sano. Medir su frescura
    # daría una alarma permanente. La señal correcta es el registro de linaje
    # del propio ETL: si deja de escribirlo, es que dejó de correr o de poder
    # evaluar — que es lo que pasó durante 5,5 meses.
    (Latido('etl_anomalias_pnt', 'Corridas del ETL de anomalías PNT', 12, critico=True),
     "SELECT MAX(finalizado_en) FROM ontologia.etl_lineage "
     "WHERE pipeline = 'anomalies_pnt' AND estado = 'exito'"),
    (Latido('alertas_historial', 'Motor de alertas (Celery Beat cada 30 min)', 3, critico=True),
     "SELECT MAX(fecha_generacion) FROM sector_energetico.alertas_historial"),
    (Latido('metrics_xm', 'ETL de métricas de XM', 12, critico=True),
     "SELECT MAX(fecha_actualizacion) FROM sector_energetico.metrics"),
    (Latido('predictions', 'Reentrenamiento de predicciones (cada 3 días)', 96),
     "SELECT MAX(fecha_generacion) FROM sector_energetico.predictions"),
    (Latido('predictions_quality', 'Monitor ex-post de predicciones (diario 22:00)', 30),
     "SELECT MAX(fecha_evaluacion) FROM sector_energetico.predictions_quality_history"),
    # 6 días: depende de DemaReal, que medimos completo recién en D-5 (XM la
    # publica parcial hasta 4 días). Un umbral más corto daría rojo permanente
    # por un retraso que es de la fuente, no del sistema.
    (Latido('losses_detailed', 'Cálculo de pérdidas no técnicas', 144),
     "SELECT MAX(fecha)::timestamp FROM sector_energetico.losses_detailed"),
    # OJO: no se usa `actualizado_en`. La tarea semanal re-inserta 3 valores
    # semilla de 2024 y eso mantiene esa columna fresca, enmascarando que la
    # ingesta real del PDF lleva 68 días fallando. La señal honesta es la
    # fecha de PUBLICACIÓN de la curva vigente.
    (Latido('senda_referencia', 'Publicación vigente de la Senda CREG', 24 * 120, critico=True),
     "SELECT MAX(fecha_publicacion)::timestamp FROM sector_energetico.senda_referencia"),
    (Latido('cu_daily', 'Costo Unitario diario', 96),
     "SELECT MAX(fecha)::timestamp FROM sector_energetico.cu_daily"),
    (Latido('etl_lineage', 'Pipeline de ontología', 24),
     "SELECT MAX(iniciado_en) FROM ontologia.etl_lineage"),
]

# ── Logs que un cron vivo debería estar tocando ──────────────────────────
# Un cron muerto deja de escribir su log: es un latido gratis que nadie leía.
LATIDOS_LOG = [
    (Latido('etl_xm_log', 'Log del ETL de XM', 12), 'logs/etl_postgresql_cron.log'),
    (Latido('anomalies_pnt_log', 'Log del ETL de anomalías PNT', 12), 'logs/etl/anomalies_pnt_cron.log'),
    (Latido('senda_log', 'Log del ETL de la senda CREG', 36), 'logs/etl/senda_referencia_pdf_cron.log'),
    (Latido('quality_log', 'Log del monitor de predicciones', 30), 'logs/etl/quality_monitor.log'),
]

# ── Servicios que deben correr el código desplegado ──────────────────────
SERVICIOS_VIGILADOS = [
    'portal-api', 'dashboard-mme', 'celery-beat', 'celery-worker',
    'telegram-polling', 'whatsapp-bot',
]


def _consultar_marca(sql: str) -> Optional[datetime]:
    from infrastructure.database.manager import db_manager
    df = db_manager.query_df(sql)
    if df is None or df.empty:
        return None
    valor = df.iloc[0, 0]
    if valor is None:
        return None
    marca = valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))
    # Algunas columnas vienen con zona horaria y otras no; se normaliza a naive
    # local para poder restarlas entre sí sin que estalle la comparación.
    return marca.replace(tzinfo=None) if marca.tzinfo is not None else marca


def revisar_tablas() -> List[Resultado]:
    """¿Cada tabla crítica sigue recibiendo filas?"""
    out = []
    ahora = datetime.now()
    for latido, sql in LATIDOS_TABLA:
        try:
            marca = _consultar_marca(sql)
        except Exception as e:
            out.append(Resultado(latido, None, f"no se pudo consultar: {e}", False))
            continue
        if marca is None:
            out.append(Resultado(latido, None, "la tabla está vacía", False))
            continue
        rezago = (ahora - marca).total_seconds() / 3600
        ok = rezago <= latido.max_rezago_horas
        out.append(Resultado(
            latido, round(rezago, 1),
            f"último dato {marca:%Y-%m-%d %H:%M} ({rezago/24:.1f} días)",
            ok, marca,
        ))
    return out


def revisar_logs() -> List[Resultado]:
    """¿Cada cron sigue escribiendo? Un cron muerto deja de tocar su log."""
    out = []
    ahora = datetime.now()
    for latido, ruta_rel in LATIDOS_LOG:
        ruta = RAIZ / ruta_rel
        if not ruta.exists():
            out.append(Resultado(latido, None, f"no existe {ruta_rel}", False))
            continue
        marca = datetime.fromtimestamp(ruta.stat().st_mtime)
        rezago = (ahora - marca).total_seconds() / 3600
        ok = rezago <= latido.max_rezago_horas
        out.append(Resultado(
            latido, round(rezago, 1),
            f"última escritura {marca:%Y-%m-%d %H:%M}", ok, marca,
        ))
    return out


def _commit_desplegado() -> Optional[str]:
    try:
        r = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=RAIZ,
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()[:8] if r.returncode == 0 else None
    except Exception:
        return None


def revisar_servicios() -> List[Resultado]:
    """
    ¿Cada servicio arrancó DESPUÉS del último commit que lo afecta?

    Un servicio sano y un servicio sirviendo código de hace 12 commits se ven
    exactamente igual en `systemctl status`: ambos dicen "active".
    """
    out = []
    ahora = datetime.now()
    try:
        # Último commit que tocó CÓDIGO, no simplemente HEAD: un merge sin
        # cambios o un commit de documentación no deja obsoleto a nadie, y
        # compararse contra ellos produce falsos positivos que enseñan a
        # ignorar el aviso — que es como mueren los monitoreos.
        r = subprocess.run(
            ['git', 'log', '-1', '--no-merges', '--format=%cI', '--', '*.py'],
            cwd=RAIZ, capture_output=True, text=True, timeout=10,
        )
        fecha_commit = datetime.fromisoformat(r.stdout.strip()).replace(tzinfo=None)
    except Exception as e:
        return [Resultado(
            Latido('codigo_desplegado', 'Versión de código en ejecución', 0, critico=True),
            None, f"no se pudo leer git: {e}", False,
        )]

    for servicio in SERVICIOS_VIGILADOS:
        latido = Latido(f'servicio_{servicio}', f'Código en ejecución de {servicio}', 0)
        try:
            r = subprocess.run(
                ['systemctl', 'show', f'{servicio}.service', '-p',
                 'ActiveEnterTimestamp', '--value'],
                capture_output=True, text=True, timeout=10,
            )
            crudo = r.stdout.strip()
            if not crudo:
                out.append(Resultado(latido, None, "sin dato de arranque", True))
                continue
            arranque = datetime.strptime(crudo.rsplit(' ', 1)[0], '%a %Y-%m-%d %H:%M:%S')
        except Exception as e:
            out.append(Resultado(latido, None, f"no se pudo consultar: {e}", True))
            continue

        atrasado = arranque < fecha_commit
        dias = (ahora - arranque).days
        out.append(Resultado(
            latido,
            round((fecha_commit - arranque).total_seconds() / 3600, 1) if atrasado else 0.0,
            (f"arrancó {arranque:%Y-%m-%d %H:%M} ({dias}d), ANTERIOR al último "
             f"commit {_commit_desplegado()} — corre código viejo"
             if atrasado else f"al día (arrancó {arranque:%Y-%m-%d %H:%M})"),
            not atrasado, arranque,
        ))
    return out


# ── Series que se agotan hacia adelante ──────────────────────────────────
# Distinto de la frescura: aquí el riesgo es que la curva TERMINE. Cuando eso
# pasa, `obtener_senda_para_fecha` devuelve el último valor disponible para
# siempre, sin error ni warning, y la clasificación regulatoria del Índice NE
# se congela sin que nadie lo note.
COBERTURA_MINIMA_DIAS = 45

LATIDOS_COBERTURA = [
    (Latido('cobertura_senda', 'Margen restante de la Senda CREG',
            COBERTURA_MINIMA_DIAS * 24, critico=True),
     "SELECT MAX(fecha)::timestamp FROM sector_energetico.senda_referencia"),
]


def revisar_cobertura() -> List[Resultado]:
    """¿Cuánto futuro le queda a las series que se publican por adelantado?"""
    out = []
    hoy = datetime.now()
    for latido, sql in LATIDOS_COBERTURA:
        try:
            fin = _consultar_marca(sql)
        except Exception as e:
            out.append(Resultado(latido, None, f"no se pudo consultar: {e}", False))
            continue
        if fin is None:
            out.append(Resultado(latido, None, "sin datos", False))
            continue
        dias = (fin - hoy).days
        ok = dias >= COBERTURA_MINIMA_DIAS
        out.append(Resultado(
            latido, round(-dias * 24.0, 1),
            (f"la serie termina el {fin:%Y-%m-%d}: quedan {dias} días. "
             f"Al agotarse, el valor se congela en silencio."),
            ok, fin,
        ))
    return out


def revisar_todo() -> List[Resultado]:
    return (revisar_tablas() + revisar_cobertura()
            + revisar_logs() + revisar_servicios())


def construir_mensaje(resultados: List[Resultado]) -> Optional[str]:
    """Mensaje para Telegram/correo. None si todo está sano."""
    fallos = [r for r in resultados if not r.ok]
    if not fallos:
        return None

    criticos = [r for r in fallos if r.latido.critico]
    lineas = [
        "🫀 *Latidos del sistema* — algo dejó de producir",
        "",
        f"{len(fallos)} de {len(resultados)} chequeos en rojo"
        + (f", {len(criticos)} crítico(s)" if criticos else "") + ":",
        "",
    ]
    for r in sorted(fallos, key=lambda x: (not x.latido.critico, x.latido.nombre)):
        marca = "🔴" if r.latido.critico else "🟠"
        lineas.append(f"{marca} *{r.latido.que_vigila}*")
        lineas.append(f"   {r.detalle}")
    lineas += [
        "",
        "_Un proceso que corre y no produce se ve igual que uno sano en el log._",
        "_Portal Energético — Ministerio de Minas y Energía_",
    ]
    return "\n".join(lineas)

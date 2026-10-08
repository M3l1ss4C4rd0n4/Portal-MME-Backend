#!/usr/bin/env python3
"""
Fase 39, ítem C.2 — Chequeo de sincronía Python ↔ TypeScript de los
umbrales oficiales del sector eléctrico.

Motivo: `core/umbrales_oficiales.py` es la fuente única de verdad
regulatoria (senda de referencia, Índice NE, clasificación visual de
embalses). `portal-direccion-mme/src/lib/umbralesOficiales.ts` se declara a
sí mismo como "el espejo TypeScript" de ese módulo, pero es mantenido a
mano, sin ningún chequeo automatizado — exactamente el mecanismo por el que
la regla del 70% derogada (Res. CREG 101 112/2026) persistió en TypeScript
semanas después de corregirse en Python (Fase 38), y por el que este mismo
script encontró, en su primera corrida (2026-08-2X), una segunda
divergencia real: `clasificarVisualEmbalse()` en TS colapsaba su banda
"ALERTA" a un estado inalcanzable delegando en `clasificarIndiceNE().nivel`
(que con SENDA_TOLERANCIA_PP=0 nunca es 'ALERTA'), mientras Python sí
mantiene un margen independiente de 5pp para ese gradiente visual — ya
corregido en la misma ronda.

Este script evalúa un conjunto FIJO de casos de prueba (pct de embalse +
fecha) contra ambos lados, forzando a Python a usar la misma tabla mensual
ESTÁTICA de respaldo que usa TS (que no tiene acceso a la base de datos) —
comparar contra la senda EN VIVO de la BD compararía frescura de datos, no
paridad de lógica de clasificación, que es lo que este chequeo evalúa.

Uso:
    venv/bin/python3 scripts/verificar_sincronia_umbrales.py
"""
import json
import os
import subprocess
import sys
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.logging.logger import get_logger  # noqa: E402
from core import umbrales_oficiales as umb  # noqa: E402

logger = get_logger(__name__)

PORTAL_DIR = "/home/admonctrlxm/portal-direccion-mme"
RUNNER_TS = "scripts/sincronia_umbrales_runner.ts"

# Casos fijos: valores de embalse cubriendo cada frontera de clasificación
# (senda exacta, ±5pp de margen de alerta, umbral de 80% "NORMAL") para 3
# meses con senda distinta en la tabla estática (evita que un solo mes
# esconda un bug de fronteras). Fechas dentro de 2024-2025 para que ambos
# lados usen la MISMA tabla estática (SENDA_REFERENCIA_2024_2025 / TS
# equivalente), no la senda en vivo de la BD.
CASOS = [
    {"pct": pct, "fecha": f"2024-{mes:02d}-15"}
    for mes in (3, 8, 11)  # marzo=37.0, agosto=55.0, noviembre=67.8
    for pct in (0.0, 30.0, 50.0, 55.0, 60.0, 65.0, 68.0, 75.0, 80.0, 95.0)
]


def _resultados_python() -> list:
    """Evalúa los casos con Python, forzando la tabla estática de respaldo
    (misma fuente que usa el runner TS, sin acceso a BD) para una
    comparación de LÓGICA, no de frescura de datos en vivo."""
    resultados = []
    with mock.patch("etl.etl_senda_referencia.obtener_senda_para_fecha", return_value=None):
        for caso in CASOS:
            fecha = date.fromisoformat(caso["fecha"])
            nivel_ne, _, senda = umb.clasificar_indice_ne(caso["pct"], fecha)
            visual_label, _, _ = umb.clasificar_visual_embalse(caso["pct"], fecha)
            resultados.append({
                "pct": caso["pct"],
                "fecha": caso["fecha"],
                "nivel_ne": nivel_ne,
                "senda_referencia_pct": senda,
                "visual_label": visual_label,
            })
    return resultados


def _resultados_typescript() -> list:
    """Invoca el runner TS (portal-direccion-mme/scripts/sincronia_umbrales_runner.ts)
    vía ts-node, pasando los mismos casos por stdin."""
    proc = subprocess.run(
        ["npx", "ts-node", "--compiler-options", '{"module":"commonjs"}', RUNNER_TS],
        cwd=PORTAL_DIR,
        input=json.dumps(CASOS),
        capture_output=True,
        text=True,
        timeout=90,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Runner TS falló (rc={proc.returncode}): {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def evaluar_sincronia() -> "tuple[bool | None, list, str | None]":
    """Evalúa CASOS contra Python y TypeScript, sin logging ni notificación —
    extraído en la Fase 44 para que otros scripts (ej. vigilancia_normativa_creg.py)
    puedan invocarlo directamente e incluir el resultado real en su propio
    mensaje, en vez de reimplementar la comparación o asumir un estado.

    Retorna (sincronizado, discrepancias, error):
      - (True, [], None)           — sin discrepancias.
      - (False, [...], None)       — discrepancias reales encontradas.
      - (None, [], "mensaje")      — no se pudo evaluar (ej. el runner TS falló).

    `main()` sigue siendo el único punto que loguea/notifica — este contrato
    puro no cambia ningún comportamiento ya existente.
    """
    py = _resultados_python()
    try:
        ts = _resultados_typescript()
    except Exception as e:
        return None, [], str(e)

    if len(py) != len(ts):
        return None, [], (
            f"Cantidad de resultados no coincide: Python={len(py)} TS={len(ts)} "
            f"— el runner TS pudo fallar a mitad de camino."
        )

    discrepancias = []
    for p, t in zip(py, ts):
        if p["pct"] != t["pct"] or p["fecha"] != t["fecha"]:
            discrepancias.append(f"Casos desalineados: Python={p} TS={t}")
            continue
        if p["nivel_ne"] != t["nivel_ne"]:
            discrepancias.append(
                f"pct={p['pct']} fecha={p['fecha']}: nivel_ne difiere "
                f"(Python={p['nivel_ne']!r} vs TS={t['nivel_ne']!r})"
            )
        if abs(p["senda_referencia_pct"] - t["senda_referencia_pct"]) > 0.05:
            discrepancias.append(
                f"pct={p['pct']} fecha={p['fecha']}: senda_referencia_pct difiere "
                f"(Python={p['senda_referencia_pct']} vs TS={t['senda_referencia_pct']})"
            )
        # Los labels visuales tienen su propio texto por idioma/UI en cada
        # lado (ver umbralesOficiales.ts) — se compara el NIVEL de riesgo
        # implícito (normal/sobre-senda/alerta/riesgo), no el string exacto.
        orden_py = {
            "NORMAL": 0,
            "SOBRE SENDA": 1,
            # "BAJO SENDA — ALERTA" se renombró a "— VIGILANCIA" al dejar de
            # atribuir a la CREG el margen de 5pp, que es criterio propio.
            # Se acepta el nombre viejo para no romper si se revierte.
            "BAJO SENDA — ALERTA": 2,
            "BAJO SENDA — VIGILANCIA": 2,
            "BAJO SENDA — RIESGO": 3,
        }
        orden_ts = {"NORMAL": 0, "SOBRE SENDA": 1, "ALERTA — BAJO SENDA": 2, "RIESGO — DESABASTECIMIENTO": 3}
        rango_py = orden_py.get(p["visual_label"])
        rango_ts = orden_ts.get(t["visual_label"])
        if rango_py is None:
            discrepancias.append(f"pct={p['pct']} fecha={p['fecha']}: label Python desconocida {p['visual_label']!r}")
        elif rango_ts is None:
            discrepancias.append(f"pct={p['pct']} fecha={p['fecha']}: label TS desconocida {t['visual_label']!r}")
        elif rango_py != rango_ts:
            discrepancias.append(
                f"pct={p['pct']} fecha={p['fecha']}: nivel visual difiere "
                f"(Python={p['visual_label']!r} vs TS={t['visual_label']!r})"
            )

    return (len(discrepancias) == 0), discrepancias, None


def main(argv: "list[str] | None" = None) -> int:
    # El envío a Telegram/correo es OPT-IN. Antes cualquier corrida manual del
    # script (p. ej. durante una revisión de código) notificaba de verdad a los
    # destinatarios de alertas en cuanto encontraba una discrepancia. La tarea
    # agendada es la única que debe pasar --notificar.
    args = sys.argv[1:] if argv is None else argv
    notificar = '--notificar' in args

    sincronizado, discrepancias, error = evaluar_sincronia()

    if sincronizado is None:
        logger.error(f"[SINCRONIA_UMBRALES] No se pudo ejecutar el runner TS: {error}")
        return 2

    if not sincronizado:
        logger.error(
            f"[SINCRONIA_UMBRALES] {len(discrepancias)} discrepancia(s) entre "
            f"core/umbrales_oficiales.py y umbralesOficiales.ts:"
        )
        for d in discrepancias:
            logger.error(f"[SINCRONIA_UMBRALES]   {d}")

        # Automatizado a pedido del usuario (2026-08-25): igual que el
        # hallazgo NIVEL 1 de vigilancia_normativa_creg.py, una discrepancia
        # aquí es exactamente el tipo de bug (Python corregido, TS no) que
        # ya pasó desapercibido semanas — se notifica por el mismo canal
        # (Telegram/email) en vez de quedar solo en el log.
        if not notificar:
            logger.error(
                "[SINCRONIA_UMBRALES] No se notifica (sin --notificar). "
                "Use --notificar para avisar por Telegram/correo."
            )
            return 1

        try:
            from domain.services.notification_service import broadcast_alert
            texto = (
                f"🧮 *Sincronía de umbrales Python↔TypeScript* — "
                f"{len(discrepancias)} discrepancia(s) encontradas entre "
                f"core/umbrales_oficiales.py y umbralesOficiales.ts:\n\n"
                + "\n".join(f"• {d}" for d in discrepancias[:10])
                + ("\n…" if len(discrepancias) > 10 else "")
                + "\n\nRevisar si un lado se corrigió y el otro quedó desactualizado."
            )
            broadcast_alert(texto, severity="WARNING")
        except Exception as e:
            logger.error(f"[SINCRONIA_UMBRALES] Error notificando discrepancia: {e}")
        return 1

    logger.info(
        "[SINCRONIA_UMBRALES] OK — casos evaluados, sin discrepancias entre "
        "Python y TypeScript."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

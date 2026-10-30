"""Tareas Celery del Informe Semanal de Dirección de Energía.

Entradas en beat_schedule (registradas en tasks/__init__.py):

  'informe-direccion-energia-generar' → viernes 07:00 (hora Colombia)
  'informe-direccion-energia-enviar'  → viernes 08:00 (hora Colombia)

Son dos tareas y no una a propósito. La generación toca cinco grupos de
endpoints y puede tardar o fallar parcialmente; el envío manda correos y
Telegram de verdad a gente real. Separarlas deja una hora de margen para que
el informe esté en disco antes de las 8:00, y deja a la vista cuál de las dos
es la que dispara notificaciones.

Por qué semanal y no diario: la variación sale de `informe_de_snapshot`, que
guarda una foto por corrida y compara contra la foto anterior. Si la generación
corriera a diario, la foto anterior sería la de ayer y la variación "semanal"
valdría un día.

Las 07:00 no son arbitrarias: el ETL de métricas corre a las 0:00 y 6:00, así
que a esa hora los tableros ya tienen los datos del día.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime

from celery import shared_task

logger = logging.getLogger(__name__)

# Una semana y pico, para que el candado de un viernes siga puesto si alguien
# reencola la tarea el lunes, pero no bloquee el viernes siguiente.
TTL_CANDADO_SEGUNDOS = 8 * 24 * 3600

PIE_PDF_TELEGRAM = "📎 Informe Semanal de Dirección de Energía"

# Espera antes de repetir el envío a quien falló. Diez minutos: suficiente para
# que pase un corte de red de Office365, poco para que el informe siga siendo
# de la mañana del viernes.
# Esperas sucesivas del reintento dirigido. Encadenan: 10 min, 30 min y 1 h
# cubren casi dos horas de corte de Office365 sin que el informe deje de ser
# "del viernes por la mañana". Antes había un solo reintento, así que una caída
# de más de 10 minutos dejaba a ese destinatario sin informe hasta el viernes
# siguiente y nadie se enteraba.
ESPERAS_REINTENTO_SEGUNDOS = (600, 1800, 3600)
ESPERA_REINTENTO_SEGUNDOS = ESPERAS_REINTENTO_SEGUNDOS[0]  # compatibilidad

# Constancia de que el envío del viernes ocurrió de verdad. La vigila un latido
# (`informe_semanal_de` en latidos_service): si un viernes el informe no sale,
# el archivo deja de refrescarse y el latido lo canta. Sin esto, un viernes en
# blanco no lo habría notado nadie hasta que alguien preguntara.
#
# Es un archivo de estado y NO el log, por la misma razón que los watchers: el
# log se escribe aunque la tarea falle, así que su fecha siempre parece fresca.
NOMBRE_ESTADO_ENVIO = ".ultimo_envio.json"


def _envio_activo() -> bool:
    """Interruptor de apagado por .env, sin necesidad de desplegar.

    Por defecto está encendido: se pidió expresamente que el informe se envíe.
    Existe porque este repositorio ya tuvo una tanda de 12 correos y 21 mensajes
    de Telegram que nadie quiso mandar, y apagar una tarea no debería requerir
    tocar código.
    """
    return os.getenv("INFORME_DE_ENVIO_ACTIVO", "true").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _redis():
    import redis as _redis_mod

    return _redis_mod.Redis(host="localhost", port=6379, db=1, socket_timeout=2)


def _clave_candado(fecha: date) -> str:
    return f"informe_de_enviado_{fecha.isoformat()}"


def _ya_enviado(fecha: date) -> bool:
    try:
        return bool(_redis().get(_clave_candado(fecha)))
    except Exception as exc:  # noqa: BLE001
        # Redis caído no puede impedir el envío semanal; pero sí hay que
        # saberlo, porque sin candado una reejecución sí duplicaría.
        logger.warning("[INFORME DE] No se pudo leer el candado de envío: %s", exc)
        return False


def _marcar_enviado(fecha: date) -> None:
    try:
        _redis().setex(_clave_candado(fecha), TTL_CANDADO_SEGUNDOS, "enviado")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INFORME DE] No se pudo marcar el candado de envío: %s", exc)


@shared_task(
    name="tasks.informe_de_tasks.generar_informe_direccion_energia",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def generar_informe_direccion_energia(self, fecha_iso: str | None = None) -> dict:
    """Genera los artefactos de la semana. Idempotente: reescribe los del día."""
    from domain.services.informe_de_service import generar_y_guardar

    fecha = date.fromisoformat(fecha_iso) if fecha_iso else date.today()

    try:
        resultado = asyncio.run(generar_y_guardar(fecha))
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[INFORME DE] Falló la generación de %s: %s", fecha, exc, exc_info=True
        )
        raise self.retry(exc=exc)

    caidas = resultado.get("secciones_caidas") or []
    if caidas:
        # No es un fallo de la tarea: el informe sale igual y dice qué falta.
        # Pero sí tiene que quedar en el log, porque un tablero que lleva
        # semanas sin responder es un problema que nadie vería de otra forma.
        logger.warning(
            "[INFORME DE] %s generado con %d sección(es) sin datos: %s",
            fecha, len(caidas), ", ".join(caidas),
        )

    logger.info(
        "[INFORME DE] %s listo · %d secciones · %d indicadores · html=%s pdf=%s",
        fecha,
        resultado.get("secciones"),
        resultado.get("indicadores"),
        bool(resultado.get("html")),
        bool(resultado.get("pdf")),
    )
    return resultado


@shared_task(
    name="tasks.informe_de_tasks.enviar_informe_direccion_energia",
    bind=True,
    max_retries=1,
    default_retry_delay=900,
)
def enviar_informe_direccion_energia(
    self,
    fecha_iso: str | None = None,
    forzar: bool = False,
    solo_correos: list[str] | None = None,
    solo_chats: list[int] | None = None,
    simular: bool = False,
    intento: int = 0,
) -> dict:
    """Manda el informe de la semana por correo y Telegram.

    Args:
        fecha_iso: el viernes a enviar. Por defecto hoy.
        forzar: ignora el candado. Solo para reenviar a mano algo que falló.
        solo_correos: si se pasa, el correo va SOLO a esas direcciones y no
            se consulta `alert_recipients`. Sirve para dos cosas: probar sin
            escribirle a nadie, y repetir el envío a quien falló. Una lista
            vacía significa "a nadie".
        solo_chats: lo mismo para Telegram.
        intento: número de reintento automático. 0 = el envío del viernes.
            Lo pone la propia tarea al reencolarse; no se pasa a mano. Un envío
            dirigido hecho a mano (solo_correos sin `intento`) NO encadena
            reintentos: reparar algo puntual no debe disparar una cadena.
        simular: resuelve destinatarios y arma el contenido, pero NO envía y
            NO toca el candado. Es la forma segura de comprobar a quién le
            llegaría el informe del viernes. Existe porque la alternativa
            —correr la tarea de verdad con los canales sustituidos— consume
            el candado y deja el envío real del viernes cancelado en
            silencio, que es exactamente lo que pasó el 2026-10-30.

    Un reintento solo tiene sentido si NO se llegó a enviar nada: Celery no
    sabe a quién le llegó ya el correo, así que reintentar un envío parcial
    duplicaría. Por eso solo se reintenta cuando falla antes de enviar.
    """
    from domain.services import informe_de_service as servicio
    from domain.services.informe_de_correo import (
        asunto,
        cuerpo_email,
        mensaje_telegram,
    )
    from domain.services.notification_service import (
        broadcast_email_alert,
        broadcast_telegram,
    )

    fecha = date.fromisoformat(fecha_iso) if fecha_iso else date.today()
    # `is not None` y no `bool(...)`: una lista vacía significa "a nadie", y con
    # bool() se leería como "no es una prueba" y el informe saldría a todos los
    # destinatarios reales. Vacía, `broadcast_*` no manda nada, que es lo pedido.
    es_prueba = solo_correos is not None or solo_chats is not None

    if not _envio_activo():
        logger.warning(
            "[INFORME DE] Envío de %s cancelado: INFORME_DE_ENVIO_ACTIVO está apagado",
            fecha,
        )
        return {"fecha": fecha.isoformat(), "estado": "envio_desactivado"}

    # El candado no se consulta en una prueba dirigida: probar no debe gastar
    # el envío real del viernes, ni al revés.
    if not es_prueba and not forzar and _ya_enviado(fecha):
        logger.info("[INFORME DE] %s ya se había enviado; no se repite", fecha)
        return {"fecha": fecha.isoformat(), "estado": "ya_enviado"}

    if simular:
        return _simular_envio(fecha, solo_correos, solo_chats)

    informe = servicio.leer_informe_guardado(fecha)
    if informe is None:
        # Que la generación de las 07:00 no haya corrido no puede dejar el
        # viernes sin informe: se genera aquí y se envía igual.
        logger.warning(
            "[INFORME DE] No hay informe de %s en disco; se genera antes de enviar",
            fecha,
        )
        try:
            informe, _ = asyncio.run(servicio.construir_y_publicar(fecha))
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[INFORME DE] No se pudo generar %s para enviarlo: %s",
                fecha, exc, exc_info=True,
            )
            raise self.retry(exc=exc)

    ruta_pdf = servicio.ruta_pdf(fecha)
    pdf = str(ruta_pdf) if ruta_pdf.is_file() else None
    if pdf is None:
        # Se envía igual: el cuerpo del correo ya trae todos los indicadores.
        # Un informe sin el PDF de detalle sigue siendo mejor que ninguno.
        logger.warning("[INFORME DE] %s sin PDF en disco: se envía sin adjunto", fecha)

    correo = broadcast_email_alert(
        subject=asunto(informe),
        body_html=cuerpo_email(informe),
        pdf_path=pdf,
        # Reutiliza la marca `recibir_diario` de alert_recipients en vez de
        # añadir una columna propia: hoy selecciona exactamente a las mismas
        # personas, y lo que esa marca significa de verdad es "quiero los
        # informes periódicos". Una columna nueva nacería en FALSE para todos
        # y el primer viernes no le llegaría a nadie.
        diario=True,
        emails_override=solo_correos,
    )
    telegram = broadcast_telegram(
        message=mensaje_telegram(informe),
        pdf_path=pdf,
        parse_mode=None,
        chat_ids=solo_chats,
        caption=PIE_PDF_TELEGRAM,
    )

    enviados = correo.get("sent", 0) + telegram.get("sent", 0)
    if enviados and not es_prueba:
        _marcar_enviado(fecha)
        _dejar_constancia(fecha, correo, telegram)

    # Quien falló por un tropiezo de red no puede esperar al viernes siguiente.
    # El 2026-10-30 un timeout del handshake TLS dejó a un destinatario sin el
    # informe: salió "4 de 5" en el log y nadie lo vio hasta que la persona
    # avisó. Se reencola SOLO a los fallidos, y solo por correo — Telegram ya
    # había entregado. El envío repetido es dirigido, así que no toca el candado.
    fallidos = list(correo.get("failures") or [])
    # Encadena mientras sea el envío del viernes o un reintento automático. Un
    # envío dirigido a mano (intento=0 con solo_correos) no entra en la cadena.
    reintentando = bool(fallidos) and (not es_prueba or intento > 0)
    if reintentando:
        reintentando = _programar_reintento(self, fecha, fallidos, intento)

    resultado = {
        "fecha": fecha.isoformat(),
        "estado": "enviado" if enviados else "sin_destinatarios",
        "prueba": es_prueba,
        "correo": {
            "enviados": correo.get("sent", 0),
            "fallidos": correo.get("failed", 0),
            "motivo": correo.get("reason"),
        },
        "telegram": {
            "enviados": telegram.get("sent", 0),
            "fallidos": telegram.get("failed", 0),
        },
        "pdf_adjunto": bool(pdf),
        "reintento_encolado": reintentando,
        "fallidos": fallidos,
    }

    if not enviados:
        # Cero destinatarios es indistinguible de un fallo de BD: las dos cosas
        # devuelven lista vacía y dejan el resultado en "0 enviados", que un
        # llamador distraído lee como éxito.
        logger.error(
            "[INFORME DE] %s NO llegó a nadie (correo=%s, telegram=%s). "
            "Revisar sector_energetico.alert_recipients y telegram_users.",
            fecha, correo.get("reason") or correo.get("failed"), telegram.get("failed"),
        )
    else:
        logger.info(
            "[INFORME DE] %s enviado · correo %s/%s · telegram %s/%s · pdf=%s%s",
            fecha,
            correo.get("sent", 0), correo.get("sent", 0) + correo.get("failed", 0),
            telegram.get("sent", 0), telegram.get("sent", 0) + telegram.get("failed", 0),
            bool(pdf),
            " (PRUEBA)" if es_prueba else "",
        )

    return resultado


def _simular_envio(
    fecha: date,
    solo_correos: list[str] | None,
    solo_chats: list[int] | None,
) -> dict:
    """Dice a quién llegaría el informe, sin enviar ni consumir el candado."""
    from domain.services import informe_de_service as servicio
    from domain.services.informe_de_correo import (
        asunto,
        cuerpo_email,
        mensaje_telegram,
    )
    from domain.services.notification_service import (
        get_email_recipients,
        get_telegram_users,
    )

    informe = servicio.leer_informe_guardado(fecha)
    hay_informe = informe is not None

    correos = (
        solo_correos
        if solo_correos is not None
        else [r["correo"] for r in get_email_recipients(diario=True)]
    )
    chats = (
        [str(c) for c in solo_chats]
        if solo_chats is not None
        else [str(u["nombre"] or u["chat_id"]) for u in get_telegram_users()]
    )

    ruta_pdf = servicio.ruta_pdf(fecha)
    resultado = {
        "fecha": fecha.isoformat(),
        "estado": "simulado",
        "hay_informe_en_disco": hay_informe,
        "envio_activo": _envio_activo(),
        "candado_puesto": _ya_enviado(fecha),
        "correo": {"destinatarios": correos, "total": len(correos)},
        "telegram": {"destinatarios": chats, "total": len(chats)},
        "pdf_adjunto": ruta_pdf.is_file(),
    }

    if hay_informe:
        resultado["asunto"] = asunto(informe)
        resultado["bytes_cuerpo_correo"] = len(cuerpo_email(informe))
        resultado["caracteres_telegram"] = len(mensaje_telegram(informe))

    logger.info("[INFORME DE] Simulacro de %s: %s", fecha, resultado["estado"])
    return resultado


def _dejar_constancia(fecha: date, correo: dict, telegram: dict) -> None:
    """Escribe el archivo de estado que vigila el latido del informe semanal.

    Un fallo aquí no puede tumbar un envío que ya salió: lo único que se pierde
    es la señal para el latido, y eso se registra en el log.
    """
    import json

    from domain.services import informe_de_service as servicio

    try:
        servicio.DIRECTORIO.mkdir(parents=True, exist_ok=True)
        (servicio.DIRECTORIO / NOMBRE_ESTADO_ENVIO).write_text(
            json.dumps(
                {
                    "fecha": fecha.isoformat(),
                    "enviado_en": datetime.now().isoformat(timespec="seconds"),
                    "correo_enviados": correo.get("sent", 0),
                    "correo_fallidos": correo.get("failed", 0),
                    "telegram_enviados": telegram.get("sent", 0),
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[INFORME DE] No se pudo dejar constancia del envío de %s: %s "
            "(el informe SÍ salió; el latido podría dar un falso positivo)",
            fecha, exc,
        )


def _programar_reintento(tarea, fecha: date, fallidos: list[str], intento: int) -> bool:
    """Reencola el envío solo a quien falló. Devuelve si quedó programado.

    Al agotar la cadena manda un aviso TÉCNICO con los nombres. Sin él, el
    latido del informe no sirve para este caso: el latido vigila que el informe
    haya salido, y en un fallo parcial sí salió — para casi todos.
    """
    if intento < len(ESPERAS_REINTENTO_SEGUNDOS):
        espera = ESPERAS_REINTENTO_SEGUNDOS[intento]
        logger.warning(
            "[INFORME DE] %s no llegó a %s; reintento %d/%d en %d min",
            fecha, ", ".join(fallidos), intento + 1,
            len(ESPERAS_REINTENTO_SEGUNDOS), espera // 60,
        )
        try:
            tarea.apply_async(
                kwargs={
                    "fecha_iso": fecha.isoformat(),
                    "solo_correos": fallidos,
                    "solo_chats": [],
                    "intento": intento + 1,
                },
                countdown=espera,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[INFORME DE] No se pudo reencolar el reintento para %s: %s",
                ", ".join(fallidos), exc,
            )
            return False

    _avisar_entrega_incompleta(fecha, fallidos)
    return False


def _avisar_entrega_incompleta(fecha: date, fallidos: list[str]) -> None:
    """Avisa a quien desarrolla que el informe no llegó a todo el mundo."""
    logger.error(
        "[INFORME DE] %s NO llegó a %s tras %d reintentos",
        fecha, ", ".join(fallidos), len(ESPERAS_REINTENTO_SEGUNDOS),
    )
    try:
        from domain.services.notification_service import broadcast_alert

        broadcast_alert(
            message=(
                f"El Informe Semanal de Dirección de Energía del {fecha} no llegó "
                f"a {len(fallidos)} destinatario(s) tras "
                f"{len(ESPERAS_REINTENTO_SEGUNDOS)} reintentos:\n\n"
                + "\n".join(f"  - {d}" for d in fallidos)
                + "\n\nHay que reenviárselo a mano:\n"
                f"  enviar_informe_direccion_energia("
                f"fecha_iso='{fecha}', solo_correos=[...], solo_chats=[])"
            ),
            severity="CRITICO",
            is_daily=False,
            tecnica=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[INFORME DE] Tampoco se pudo avisar del fallo parcial: %s", exc)

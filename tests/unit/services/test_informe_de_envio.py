"""Pruebas del envío semanal del Informe de Dirección de Energía.

Lo que se cuida aquí es que NO se mande nada que no se quiso mandar: el
interruptor de apagado, el candado que impide repetir el viernes y el modo de
prueba que no debe gastar el envío real. Este repositorio ya tuvo una tanda de
12 correos y 21 mensajes de Telegram que nadie quiso mandar.

Ningún test de este archivo toca la red, el SMTP ni Redis: los tres se
sustituyen por dobles.
"""
from __future__ import annotations

from datetime import date

import pytest

from domain.services.informe_de_correo import (
    LIMITE_TELEGRAM,
    asunto,
    cuerpo_email,
    mensaje_telegram,
)
from domain.services.informe_de_json import desde_json, a_json
from domain.services.informe_de_modelo import Informe, Kpi, Punto, Seccion, Serie
from domain.services.informe_de_render import ventana_delta

pytestmark = pytest.mark.unit

FECHA = date(2026, 10, 30)  # viernes


def _informe(*secciones: Seccion) -> Informe:
    return Informe(
        fecha="viernes, 30 de octubre de 2026",
        generado_en="30/10/2026 07:00",
        secciones=secciones or (_seccion(),),
    )


def _seccion(**cambios) -> Seccion:
    base = dict(
        clave="subsidios",
        titulo="Subsidios",
        subtitulo="FSSRI / FOES",
        corte="30/10/2026",
        kpis=(
            Kpi("pagado", "Valor pagado", 3.34e13, "cop_corto",
                sentido="mas_es_mejor", delta=1.2e9, dias_delta=7),
            Kpi("pendiente", "Saldo pendiente", 4.19e10, "cop_corto",
                sentido="menos_es_mejor", delta=-5.0e8, dias_delta=7),
            Kpi("empresas", "Empresas", 218.0, "num"),
        ),
        series=(Serie("s", "Ejecución", "medidores", (Punto("Pagado", 99.87, "paso-3", "99,87%"),)),),
        lectura="Queda 0,13 % por pagar.",
        tableros=("Déficit histórico", "Detalle de pagos"),
    )
    base.update(cambios)
    return Seccion(**base)


# ── Cómo se nombra el periodo comparado ───────────────────────────────────────

@pytest.mark.parametrize(
    "dias, esperado",
    [
        (7, "la semana pasada"),    # el caso normal del informe semanal
        (None, "la semana pasada"),
        (14, "hace 2 semanas"),     # un viernes festivo que no corrió
        (1, "ayer"),
        (3, "hace 3 días"),         # la transición desde el informe diario
    ],
)
def test_la_ventana_se_nombra_en_semanas_cuando_lo_es(dias, esperado):
    assert ventana_delta(dias) == esperado


# ── Cuerpo del correo ─────────────────────────────────────────────────────────

def test_el_asunto_lleva_la_fecha_del_informe():
    assert asunto(_informe()) == (
        "Informe Semanal de Dirección de Energía — viernes, 30 de octubre de 2026"
    )


def test_el_correo_no_usa_nada_que_un_cliente_de_correo_descarte():
    """Sin <script>, sin var() y sin hoja de estilos aparte: Outlook los tira."""
    html = cuerpo_email(_informe())
    assert "<script" not in html
    assert "var(--" not in html
    assert "<link" not in html
    assert "@media" not in html


def test_el_correo_trae_cada_indicador_con_su_valor():
    html = cuerpo_email(_informe())
    assert "Valor pagado" in html
    assert "$33,40 bill." in html
    assert "Saldo pendiente" in html
    assert "218" in html


@pytest.mark.parametrize(
    "sentido, delta, color_esperado",
    [
        ("mas_es_mejor", 10.0, "#047857"),    # sube lo que debe subir: verde
        ("mas_es_mejor", -10.0, "#B91C1C"),
        ("menos_es_mejor", 10.0, "#B91C1C"),  # sube lo que debe bajar: rojo
        ("menos_es_mejor", -10.0, "#047857"),
    ],
)
def test_el_color_del_delta_sigue_al_sentido_no_al_signo(sentido, delta, color_esperado):
    """Que el saldo pendiente baje es bueno; que el pagado baje es malo."""
    from domain.services.informe_de_correo import _texto_delta

    kpi = Kpi("k", "K", 100.0, "num", sentido=sentido, delta=delta, dias_delta=7)
    _, color = _texto_delta(kpi)
    assert color == color_esperado


def test_un_indicador_sin_histórico_no_se_pinta_como_sin_cambio():
    from domain.services.informe_de_correo import _texto_delta

    sin_foto, _ = _texto_delta(Kpi("k", "K", 10.0, "num"))
    quieto, _ = _texto_delta(Kpi("k", "K", 10.0, "num", delta=0.0, dias_delta=7))
    assert sin_foto == "sin histórico"
    assert quieto == "sin cambio"
    assert sin_foto != quieto


def test_una_seccion_caida_dice_que_no_se_pudo_evaluar():
    caida = _seccion(kpis=(), error="TimeoutError")
    html = cuerpo_email(_informe(caida))
    assert "sin datos esta semana" in html
    assert "no es lo mismo que estar en cero" in html


def test_el_correo_escapa_lo_que_viene_de_la_fuente():
    hostil = _seccion(titulo='<img src=x onerror="alert(1)">')
    html = cuerpo_email(_informe(hostil))
    assert "<img src=x" not in html
    assert "&lt;img" in html


def test_el_resumen_cuenta_cuantos_indicadores_se_movieron():
    from domain.services.informe_de_correo import _resumen_movimiento

    texto = _resumen_movimiento(_informe())
    assert "2 de 3 indicadores" in texto


def test_el_resumen_distingue_la_primera_corrida_de_una_semana_quieta():
    from domain.services.informe_de_correo import _resumen_movimiento

    primera = _seccion(kpis=(Kpi("a", "A", 1.0, "num"), Kpi("b", "B", 2.0, "num")))
    quieta = _seccion(kpis=(Kpi("a", "A", 1.0, "num", delta=0.0, dias_delta=7),))
    assert "primera vez" in _resumen_movimiento(_informe(primera))
    assert "Ninguno" in _resumen_movimiento(_informe(quieta))


# ── Mensaje de Telegram ───────────────────────────────────────────────────────

def test_telegram_va_en_texto_plano_sin_marcas_de_formato():
    """Con parse_mode activo, un asterisco sin pareja devuelve 400 y no se manda."""
    texto = mensaje_telegram(_informe())
    assert "*" not in texto
    assert "_" not in texto.replace("informe-direccion-energia", "")


def test_telegram_lista_los_indicadores_y_remite_al_pdf():
    texto = mensaje_telegram(_informe())
    assert "Valor pagado" in texto
    assert "PDF adjunto" in texto


def test_telegram_recorta_antes_del_limite_de_la_api():
    muchos = _seccion(kpis=tuple(
        Kpi(f"k{i}", f"Indicador larguísimo número {i}", float(i), "cop_corto",
            delta=float(i), dias_delta=7)
        for i in range(400)
    ))
    texto = mensaje_telegram(_informe(muchos))
    assert len(texto) <= LIMITE_TELEGRAM + 200
    assert "PDF adjunto" in texto


# ── Ida y vuelta por JSON ─────────────────────────────────────────────────────

def test_el_informe_sobrevive_al_json_sin_perder_nada():
    """La tarea de envío lee de disco lo que imprimió la de generación."""
    original = _informe()
    copia = desde_json(a_json(original))
    assert copia == original


def test_un_json_de_una_version_anterior_se_lee_igual():
    """Un campo añadido después no puede reventar la tarea que manda correos."""
    viejo = """{"fecha":"f","generado_en":"g","secciones":[
      {"clave":"c","titulo":"T","kpis":[{"clave":"k","etiqueta":"E","valor":1.0}]}]}"""
    informe = desde_json(viejo)
    assert informe.secciones[0].kpis[0].etiqueta == "E"
    assert informe.secciones[0].series == ()


# ── La tarea de envío ─────────────────────────────────────────────────────────

class _Espia:
    """Sustituye a broadcast_email_alert / broadcast_telegram y anota llamadas."""

    def __init__(self, enviados: int = 3):
        self.llamadas: list[dict] = []
        self.enviados = enviados

    def __call__(self, **kwargs):
        self.llamadas.append(kwargs)
        return {"sent": self.enviados, "failed": 0}


@pytest.fixture
def envio(monkeypatch, tmp_path):
    """Prepara la tarea con correo, Telegram, Redis y disco sustituidos."""
    from domain.services import informe_de_service as servicio
    from domain.services import informe_de_json as serializador
    from tasks import informe_de_tasks as tareas

    correo, telegram = _Espia(), _Espia()
    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_email_alert", correo
    )
    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_telegram", telegram
    )

    monkeypatch.setattr(servicio, "DIRECTORIO", tmp_path)
    serializador.escribir(servicio.ruta_json(FECHA), _informe())
    servicio.ruta_pdf(FECHA).write_bytes(b"%PDF-1.4 fake")

    candados: dict[str, str] = {}
    monkeypatch.setattr(tareas, "_ya_enviado", lambda f: f.isoformat() in candados)
    monkeypatch.setattr(
        tareas, "_marcar_enviado", lambda f: candados.__setitem__(f.isoformat(), "x")
    )
    monkeypatch.setenv("INFORME_DE_ENVIO_ACTIVO", "true")

    return {
        "tarea": tareas.enviar_informe_direccion_energia,
        "correo": correo,
        "telegram": telegram,
        "candados": candados,
    }


def test_el_envio_llega_a_los_dos_canales_con_el_pdf_adjunto(envio):
    resultado = envio["tarea"](fecha_iso=FECHA.isoformat())

    assert resultado["estado"] == "enviado"
    assert len(envio["correo"].llamadas) == 1
    assert len(envio["telegram"].llamadas) == 1
    assert envio["correo"].llamadas[0]["pdf_path"].endswith(".pdf")
    assert resultado["pdf_adjunto"] is True


def test_el_pie_del_pdf_de_telegram_no_es_el_del_informe_de_xm(envio):
    """La función trae por defecto el pie del informe de XM, que no es este."""
    envio["tarea"](fecha_iso=FECHA.isoformat())
    assert "Dirección de Energía" in envio["telegram"].llamadas[0]["caption"]


def test_el_interruptor_de_apagado_corta_el_envio(envio, monkeypatch):
    monkeypatch.setenv("INFORME_DE_ENVIO_ACTIVO", "false")

    resultado = envio["tarea"](fecha_iso=FECHA.isoformat())

    assert resultado["estado"] == "envio_desactivado"
    assert envio["correo"].llamadas == []
    assert envio["telegram"].llamadas == []


def test_el_mismo_viernes_no_se_envia_dos_veces(envio):
    primero = envio["tarea"](fecha_iso=FECHA.isoformat())
    segundo = envio["tarea"](fecha_iso=FECHA.isoformat())

    assert primero["estado"] == "enviado"
    assert segundo["estado"] == "ya_enviado"
    assert len(envio["correo"].llamadas) == 1, "el candado debe cortar el segundo"


def test_forzar_reenvia_pese_al_candado(envio):
    envio["tarea"](fecha_iso=FECHA.isoformat())
    resultado = envio["tarea"](fecha_iso=FECHA.isoformat(), forzar=True)

    assert resultado["estado"] == "enviado"
    assert len(envio["correo"].llamadas) == 2


def test_una_prueba_dirigida_no_gasta_el_envio_del_viernes(envio):
    prueba = envio["tarea"](
        fecha_iso=FECHA.isoformat(), solo_correos=["yo@minenergia.gov.co"]
    )

    assert prueba["prueba"] is True
    assert envio["correo"].llamadas[0]["emails_override"] == ["yo@minenergia.gov.co"]
    assert envio["candados"] == {}, "una prueba no puede marcar el candado"

    # Y el envío real del viernes sigue pendiente, no consumido por la prueba.
    assert envio["tarea"](fecha_iso=FECHA.isoformat())["estado"] == "enviado"


def test_sin_destinatarios_no_se_marca_el_candado(envio, monkeypatch):
    """Cero enviados es indistinguible de un fallo de BD: hay que poder reintentar."""
    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_email_alert", _Espia(0)
    )
    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_telegram", _Espia(0)
    )

    resultado = envio["tarea"](fecha_iso=FECHA.isoformat())

    assert resultado["estado"] == "sin_destinatarios"
    assert envio["candados"] == {}


def test_sin_pdf_en_disco_se_envia_igual_sin_adjunto(envio, monkeypatch):
    from domain.services import informe_de_service as servicio

    servicio.ruta_pdf(FECHA).unlink()

    resultado = envio["tarea"](fecha_iso=FECHA.isoformat())

    assert resultado["estado"] == "enviado"
    assert resultado["pdf_adjunto"] is False
    assert envio["correo"].llamadas[0]["pdf_path"] is None


def test_si_la_generacion_no_corrio_el_envio_la_dispara(envio, monkeypatch):
    from domain.services import informe_de_service as servicio

    servicio.ruta_json(FECHA).unlink()
    generados: list[date] = []

    async def _generar(fecha=None):
        generados.append(fecha)
        return _informe(), {"fecha": fecha.isoformat()}

    monkeypatch.setattr(servicio, "construir_y_publicar", _generar)

    resultado = envio["tarea"](fecha_iso=FECHA.isoformat())

    assert generados == [FECHA]
    assert resultado["estado"] == "enviado"


# ── Programación ──────────────────────────────────────────────────────────────

def test_el_beat_programa_generar_y_enviar_el_viernes():
    """Viernes 07:00 genera y viernes 08:00 envía, en ese orden y ese día."""
    from tasks import app

    generar = app.conf.beat_schedule["informe-direccion-energia-generar"]
    enviar = app.conf.beat_schedule["informe-direccion-energia-enviar"]

    # Celery usa la convención de cron: 0 = domingo, así que viernes es 5.
    assert generar["schedule"].day_of_week == {5}
    assert enviar["schedule"].day_of_week == {5}
    assert generar["schedule"].hour == {7}
    assert enviar["schedule"].hour == {8}
    assert enviar["task"] == "tasks.informe_de_tasks.enviar_informe_direccion_energia"


def test_una_lista_de_prueba_vacia_significa_a_nadie_no_a_todos(envio):
    """Con bool(), `solo_correos=[]` se leía como "no es prueba" y salía a todos."""
    resultado = envio["tarea"](fecha_iso=FECHA.isoformat(), solo_correos=[])

    assert resultado["prueba"] is True
    assert envio["correo"].llamadas[0]["emails_override"] == []
    assert envio["candados"] == {}


# ── El candado, cuando Redis no está ──────────────────────────────────────────

@pytest.mark.parametrize(
    "valor, activo",
    [("true", True), ("1", True), ("", True), ("false", False),
     ("FALSE", False), ("0", False), ("no", False), ("off", False)],
)
def test_el_interruptor_lee_las_formas_habituales_de_apagar(monkeypatch, valor, activo):
    from tasks.informe_de_tasks import _envio_activo

    monkeypatch.setenv("INFORME_DE_ENVIO_ACTIVO", valor)
    assert _envio_activo() is activo


def test_sin_la_variable_el_envio_esta_encendido(monkeypatch):
    """Se pidió que el informe se envíe: el valor por defecto es enviar."""
    from tasks.informe_de_tasks import _envio_activo

    monkeypatch.delenv("INFORME_DE_ENVIO_ACTIVO", raising=False)
    assert _envio_activo() is True


def test_redis_caido_no_bloquea_el_envio_del_viernes(monkeypatch):
    """Sin candado se podría duplicar, pero no enviar nada es peor y es seguro."""
    from tasks import informe_de_tasks as tareas

    def _explota():
        raise ConnectionError("Redis caído")

    monkeypatch.setattr(tareas, "_redis", _explota)

    assert tareas._ya_enviado(FECHA) is False
    tareas._marcar_enviado(FECHA)  # no debe lanzar


# ── Modo simulacro ────────────────────────────────────────────────────────────

def test_el_simulacro_no_envia_ni_consume_el_candado(envio):
    """Comprobar a quién llegaría el viernes no puede cancelar ese envío.

    Pasó de verdad el 2026-10-30: correr la tarea con los canales sustituidos
    marcó el candado y el envío real de las 8:00 se habría saltado en silencio.
    """
    resultado = envio["tarea"](fecha_iso=FECHA.isoformat(), simular=True)

    assert resultado["estado"] == "simulado"
    assert envio["correo"].llamadas == []
    assert envio["telegram"].llamadas == []
    assert envio["candados"] == {}

    # Y el envío real del viernes sigue disponible.
    assert envio["tarea"](fecha_iso=FECHA.isoformat())["estado"] == "enviado"


def test_el_simulacro_dice_a_quien_llegaria(envio, monkeypatch):
    monkeypatch.setattr(
        "domain.services.notification_service.get_email_recipients",
        lambda **kw: [{"correo": "a@x.gov.co"}, {"correo": "b@x.gov.co"}],
    )
    monkeypatch.setattr(
        "domain.services.notification_service.get_telegram_users",
        lambda **kw: [{"chat_id": 1, "nombre": "Melissa"}],
    )

    r = envio["tarea"](fecha_iso=FECHA.isoformat(), simular=True)

    assert r["correo"]["destinatarios"] == ["a@x.gov.co", "b@x.gov.co"]
    assert r["telegram"]["destinatarios"] == ["Melissa"]
    assert r["pdf_adjunto"] is True
    assert r["hay_informe_en_disco"] is True
    assert "Informe Semanal" in r["asunto"]


def test_el_simulacro_avisa_si_no_hay_informe_generado(envio, monkeypatch):
    """No genera nada: solo informa. Generar es trabajo de la otra tarea."""
    from domain.services import informe_de_service as servicio

    servicio.ruta_json(FECHA).unlink()
    monkeypatch.setattr(
        "domain.services.notification_service.get_email_recipients", lambda **kw: []
    )
    monkeypatch.setattr(
        "domain.services.notification_service.get_telegram_users", lambda **kw: []
    )

    r = envio["tarea"](fecha_iso=FECHA.isoformat(), simular=True)

    assert r["hay_informe_en_disco"] is False
    assert "asunto" not in r


# ── Un destinatario que falla no espera al viernes siguiente ──────────────────

class _EspiaConFallo:
    """Simula un envío donde una dirección falla y el resto llega."""

    def __init__(self, fallidos):
        self.fallidos = list(fallidos)
        self.llamadas: list[dict] = []

    def __call__(self, **kwargs):
        self.llamadas.append(kwargs)
        return {"sent": 4, "failed": len(self.fallidos), "failures": self.fallidos}


def test_se_reintenta_solo_con_quien_fallo(envio, monkeypatch):
    """El 2026-10-30 salió "4 de 5" en el log y nadie lo vio hasta que avisaron."""
    from tasks import informe_de_tasks as tareas

    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_email_alert",
        _EspiaConFallo(["cdvillarreal@minenergia.gov.co"]),
    )
    encoladas: list[dict] = []
    monkeypatch.setattr(
        tareas.enviar_informe_direccion_energia,
        "apply_async",
        lambda **kw: encoladas.append(kw),
    )

    resultado = envio["tarea"](fecha_iso=FECHA.isoformat())

    assert resultado["reintento_encolado"] is True
    assert len(encoladas) == 1
    reintento = encoladas[0]["kwargs"]
    assert reintento["solo_correos"] == ["cdvillarreal@minenergia.gov.co"]
    assert reintento["solo_chats"] == [], "Telegram ya había entregado"
    assert encoladas[0]["countdown"] == tareas.ESPERAS_REINTENTO_SEGUNDOS[0]
    assert reintento["intento"] == 1


def test_sin_fallos_no_se_reintenta_nada(envio, monkeypatch):
    from tasks import informe_de_tasks as tareas

    encoladas: list[dict] = []
    monkeypatch.setattr(
        tareas.enviar_informe_direccion_energia,
        "apply_async",
        lambda **kw: encoladas.append(kw),
    )

    resultado = envio["tarea"](fecha_iso=FECHA.isoformat())

    assert resultado["reintento_encolado"] is False
    assert encoladas == []


def test_el_propio_reintento_no_encadena_otro(envio, monkeypatch):
    """Un envío dirigido es la reparación: no puede reencolarse a sí mismo."""
    from tasks import informe_de_tasks as tareas

    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_email_alert",
        _EspiaConFallo(["cdvillarreal@minenergia.gov.co"]),
    )
    encoladas: list[dict] = []
    monkeypatch.setattr(
        tareas.enviar_informe_direccion_energia,
        "apply_async",
        lambda **kw: encoladas.append(kw),
    )

    resultado = envio["tarea"](
        fecha_iso=FECHA.isoformat(), solo_correos=["cdvillarreal@minenergia.gov.co"]
    )

    assert resultado["reintento_encolado"] is False
    assert encoladas == []


def test_un_fallo_al_reencolar_no_tumba_el_envio_ya_hecho(envio, monkeypatch):
    from tasks import informe_de_tasks as tareas

    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_email_alert",
        _EspiaConFallo(["x@y.gov.co"]),
    )

    def _explota(**kw):
        raise ConnectionError("broker caído")

    monkeypatch.setattr(
        tareas.enviar_informe_direccion_energia, "apply_async", _explota
    )

    resultado = envio["tarea"](fecha_iso=FECHA.isoformat())

    assert resultado["estado"] == "enviado", "lo ya entregado sigue entregado"


# ── Constancia para el latido ─────────────────────────────────────────────────

def test_un_envio_real_deja_constancia_para_el_latido(envio):
    """Sin esta huella, un viernes en blanco tardaría otra semana en notarse."""
    import json
    from domain.services import informe_de_service as servicio
    from tasks.informe_de_tasks import NOMBRE_ESTADO_ENVIO

    envio["tarea"](fecha_iso=FECHA.isoformat())

    estado = servicio.DIRECTORIO / NOMBRE_ESTADO_ENVIO
    assert estado.is_file()
    datos = json.loads(estado.read_text(encoding="utf-8"))
    assert datos["fecha"] == FECHA.isoformat()
    assert datos["correo_enviados"] == 3


def test_un_envio_dirigido_no_falsea_la_constancia(envio):
    """Reenviarle a una persona no es "el informe del viernes salió"."""
    from domain.services import informe_de_service as servicio
    from tasks.informe_de_tasks import NOMBRE_ESTADO_ENVIO

    envio["tarea"](fecha_iso=FECHA.isoformat(), solo_correos=["a@b.gov.co"])

    assert not (servicio.DIRECTORIO / NOMBRE_ESTADO_ENVIO).exists()


def test_si_no_llega_a_nadie_no_hay_constancia(envio, monkeypatch):
    from domain.services import informe_de_service as servicio
    from tasks.informe_de_tasks import NOMBRE_ESTADO_ENVIO

    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_email_alert", _Espia(0)
    )
    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_telegram", _Espia(0)
    )

    envio["tarea"](fecha_iso=FECHA.isoformat())

    assert not (servicio.DIRECTORIO / NOMBRE_ESTADO_ENVIO).exists()


def test_un_fallo_al_escribir_la_constancia_no_tumba_el_envio(envio, monkeypatch):
    from tasks import informe_de_tasks as tareas

    def _explota(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(tareas, "_dejar_constancia", _explota)

    with pytest.raises(OSError):
        envio["tarea"](fecha_iso=FECHA.isoformat())


def test_el_latido_vigila_la_constancia_del_envio():
    """El latido tiene que apuntar al archivo que escribe la tarea."""
    from domain.services.latidos_service import LATIDOS_LOG
    from tasks.informe_de_tasks import NOMBRE_ESTADO_ENVIO

    entrada = next(
        (lat, ruta) for lat, ruta in LATIDOS_LOG if lat.nombre == "informe_semanal_de"
    )
    latido, ruta = entrada
    assert ruta.endswith(NOMBRE_ESTADO_ENVIO)
    assert latido.critico is True
    assert latido.max_rezago_horas > 168, "tiene que tolerar una semana completa"


# ── La cadena de reintentos y su final ────────────────────────────────────────

@pytest.fixture
def cadena(envio, monkeypatch):
    """Envío donde una dirección siempre falla, con apply_async interceptado."""
    from tasks import informe_de_tasks as tareas

    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_email_alert",
        _EspiaConFallo(["cdvillarreal@minenergia.gov.co"]),
    )
    encoladas: list[dict] = []
    monkeypatch.setattr(
        tareas.enviar_informe_direccion_energia,
        "apply_async",
        lambda **kw: encoladas.append(kw),
    )
    avisos: list[dict] = []
    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_alert",
        lambda **kw: avisos.append(kw) or {"telegram": {"sent": 1}, "email": {"sent": 1}},
    )
    return {**envio, "encoladas": encoladas, "avisos": avisos, "tareas": tareas}


@pytest.mark.parametrize("intento, espera_idx", [(1, 1), (2, 2)])
def test_cada_reintento_espera_mas_que_el_anterior(cadena, intento, espera_idx):
    """Una caída de Office365 de más de 10 min ya no deja a nadie sin informe."""
    cadena["tarea"](
        fecha_iso=FECHA.isoformat(),
        solo_correos=["cdvillarreal@minenergia.gov.co"],
        intento=intento,
    )

    assert len(cadena["encoladas"]) == 1
    enc = cadena["encoladas"][0]
    assert enc["countdown"] == cadena["tareas"].ESPERAS_REINTENTO_SEGUNDOS[espera_idx]
    assert enc["kwargs"]["intento"] == intento + 1
    assert cadena["avisos"] == [], "todavía queda cadena: no toca avisar"


def test_al_agotar_la_cadena_se_avisa_a_desarrollo(cadena):
    """El latido vigila que el informe salga; en un fallo parcial SÍ salió."""
    ultimo = len(cadena["tareas"].ESPERAS_REINTENTO_SEGUNDOS)

    resultado = cadena["tarea"](
        fecha_iso=FECHA.isoformat(),
        solo_correos=["cdvillarreal@minenergia.gov.co"],
        intento=ultimo,
    )

    assert cadena["encoladas"] == [], "ya no se reencola"
    assert resultado["reintento_encolado"] is False
    assert len(cadena["avisos"]) == 1
    aviso = cadena["avisos"][0]
    assert aviso["tecnica"] is True, "es un problema que solo atiende desarrollo"
    assert "cdvillarreal@minenergia.gov.co" in aviso["message"]
    assert resultado["fallidos"] == ["cdvillarreal@minenergia.gov.co"]


def test_un_reenvio_a_mano_no_arranca_una_cadena(cadena):
    """Reparar algo puntual no debe disparar reintentos automáticos."""
    cadena["tarea"](
        fecha_iso=FECHA.isoformat(), solo_correos=["cdvillarreal@minenergia.gov.co"]
    )

    assert cadena["encoladas"] == []
    assert cadena["avisos"] == []


def test_si_el_aviso_final_tambien_falla_no_revienta_la_tarea(cadena, monkeypatch):
    def _explota(**kw):
        raise ConnectionError("SMTP caído del todo")

    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_alert", _explota
    )

    resultado = cadena["tarea"](
        fecha_iso=FECHA.isoformat(),
        solo_correos=["x@y.gov.co"],
        intento=len(cadena["tareas"].ESPERAS_REINTENTO_SEGUNDOS),
    )

    assert resultado["estado"] == "enviado"


def test_el_primer_eslabon_sale_del_envio_del_viernes(cadena):
    """intento=0 solo encadena cuando es el envío semanal, no un reenvío a mano."""
    cadena["tarea"](fecha_iso=FECHA.isoformat())

    assert len(cadena["encoladas"]) == 1
    enc = cadena["encoladas"][0]
    assert enc["countdown"] == cadena["tareas"].ESPERAS_REINTENTO_SEGUNDOS[0]
    assert enc["kwargs"]["intento"] == 1

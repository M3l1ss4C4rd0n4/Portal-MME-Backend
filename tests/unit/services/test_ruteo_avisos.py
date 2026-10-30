"""Pruebas del reparto de avisos entre públicos y del freno a la repetición.

Dos quejas reales de los destinatarios (2026-10-29) motivan este archivo:

* Recibían avisos técnicos que no pueden atender ("celery-worker corre código
  viejo") con el mismo asunto que una alerta del SIN.
* Recibían la misma alerta varias veces al día.

Nada aquí toca SMTP, Telegram ni Redis: los tres van por dobles.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ── A quién le llega cada cosa ────────────────────────────────────────────────

class _Consultas:
    """Captura el SQL que se arma, sin tocar la base."""

    def __init__(self):
        self.sql: list[str] = []

    def __call__(self, sql, *args):
        self.sql.append(sql)


@pytest.fixture
def sql_destinatarios(monkeypatch):
    """Sustituye psycopg2.connect y devuelve el SQL que se ejecutó."""
    capturado = _Consultas()

    class _Cursor:
        def execute(self, sql, *a):
            capturado(sql, *a)

        def fetchall(self):
            return []

        def close(self):
            pass

    class _Conn:
        def cursor(self, **kw):
            return _Cursor()

        def close(self):
            pass

    monkeypatch.setattr(
        "domain.services.notification_service.psycopg2.connect",
        lambda **kw: _Conn(),
    )
    return capturado


def test_los_avisos_tecnicos_filtran_por_su_propia_marca(sql_destinatarios):
    from domain.services.notification_service import get_email_recipients

    get_email_recipients(tecnicas=True)

    assert "recibir_tecnicas = TRUE" in sql_destinatarios.sql[0]


def test_una_alerta_del_sin_no_filtra_por_la_marca_tecnica(sql_destinatarios):
    """Quien recibe alertas del SIN no tiene por qué recibir las técnicas."""
    from domain.services.notification_service import get_email_recipients

    get_email_recipients(alertas=True)

    assert "recibir_alertas = TRUE" in sql_destinatarios.sql[0]
    assert "recibir_tecnicas" not in sql_destinatarios.sql[0]


def test_telegram_tambien_separa_los_dos_publicos(sql_destinatarios):
    from domain.services.notification_service import get_telegram_users

    get_telegram_users(tecnicas=True)
    get_telegram_users()

    assert "recibir_tecnicas = TRUE" in sql_destinatarios.sql[0]
    assert "recibir_tecnicas" not in sql_destinatarios.sql[1]


# ── El asunto del correo distingue los tres casos ─────────────────────────────

@pytest.fixture
def broadcast(monkeypatch):
    """Intercepta los dos canales y devuelve con qué se les llamó."""
    registro: dict = {}

    def _email(**kw):
        registro["email"] = kw
        return {"sent": 1, "failed": 0}

    def _telegram(*a, **kw):
        registro["telegram"] = kw
        return {"sent": 1, "failed": 0}

    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_email_alert", _email
    )
    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_telegram", _telegram
    )
    return registro


def test_un_aviso_tecnico_no_se_disfraza_de_alerta_del_sector(broadcast):
    """Desde la bandeja tiene que verse cuál de los dos es."""
    from domain.services.notification_service import broadcast_alert

    broadcast_alert("algo", severity="CRITICO", tecnica=True)

    asunto = broadcast["email"]["subject"]
    assert "Aviso técnico del portal" in asunto
    assert "Alerta Energética" not in asunto


def test_una_alerta_del_sin_conserva_su_asunto_de_siempre(broadcast):
    from domain.services.notification_service import broadcast_alert

    broadcast_alert("algo", severity="CRITICO")

    assert "Alerta Energética [CRITICO]" in broadcast["email"]["subject"]


def test_el_aviso_tecnico_va_al_publico_tecnico_en_los_dos_canales(broadcast):
    from domain.services.notification_service import broadcast_alert

    broadcast_alert("algo", tecnica=True)

    assert broadcast["email"]["tecnicas"] is True
    assert broadcast["email"]["alertas"] is False, "no debe ir también al público del SIN"
    assert broadcast["telegram"]["tecnicas"] is True


def test_una_alerta_del_sin_no_llega_al_publico_tecnico(broadcast):
    from domain.services.notification_service import broadcast_alert

    broadcast_alert("algo")

    assert broadcast["email"]["alertas"] is True
    assert broadcast["email"]["tecnicas"] is False
    assert broadcast["telegram"]["tecnicas"] is False


def test_un_informe_periodico_no_es_ninguna_de_las_dos(broadcast):
    from domain.services.notification_service import broadcast_alert

    broadcast_alert("algo", is_daily=True)

    assert broadcast["email"]["diario"] is True
    assert broadcast["email"]["alertas"] is False
    assert broadcast["email"]["tecnicas"] is False


# ── Latidos: avisar cuando la foto cambia, no cada vez que corre ──────────────

class _Latido:
    def __init__(self, nombre, critico=False):
        self.nombre = nombre
        self.critico = critico


class _Resultado:
    def __init__(self, nombre, critico=False):
        self.latido = _Latido(nombre, critico)
        self.ok = False
        self.detalle = "lo que sea"


def test_la_huella_ignora_el_detalle_que_cambia_en_cada_corrida():
    """"quedan 29 días" y "quedan 30 días" son la MISMA situación."""
    from tasks.latidos_tasks import _huella

    hoy = [_Resultado("senda_creg"), _Resultado("worker", critico=True)]
    manana = [_Resultado("senda_creg"), _Resultado("worker", critico=True)]
    manana[0].detalle = "quedan 28 días en vez de 29"

    assert _huella(hoy) == _huella(manana)


def test_la_huella_no_depende_del_orden():
    from tasks.latidos_tasks import _huella

    a = [_Resultado("uno"), _Resultado("dos")]
    b = [_Resultado("dos"), _Resultado("uno")]
    assert _huella(a) == _huella(b)


def test_un_latido_nuevo_cambia_la_huella_y_rompe_el_silencio():
    from tasks.latidos_tasks import _huella

    antes = [_Resultado("senda_creg")]
    despues = [_Resultado("senda_creg"), _Resultado("etl_caido", critico=True)]
    assert _huella(antes) != _huella(despues)


def test_que_un_latido_pase_a_critico_tambien_cambia_la_huella():
    """Mismos nombres, distinta gravedad: no es la misma situación."""
    from tasks.latidos_tasks import _huella

    assert _huella([_Resultado("x")]) != _huella([_Resultado("x", critico=True)])


def test_sin_redis_los_latidos_avisan_en_vez_de_callarse(monkeypatch):
    """Perder un aviso es peor que repetirlo."""
    from tasks import latidos_tasks

    def _explota():
        raise ConnectionError("Redis caído")

    monkeypatch.setattr(latidos_tasks, "_redis", _explota)

    assert latidos_tasks._misma_situacion("abc") is False
    latidos_tasks._recordar_situacion("abc")  # no debe lanzar


# ── Anomalías: el recordatorio se espacia si la condición no se resuelve ──────

class _RedisFalso:
    def __init__(self, valores=None):
        self.valores = dict(valores or {})

    def get(self, k):
        v = self.valores.get(k)
        return str(v).encode() if v is not None else None

    def incr(self, k):
        self.valores[k] = int(self.valores.get(k, 0)) + 1

    def expire(self, k, ttl):
        pass


@pytest.fixture
def redis_falso(monkeypatch):
    falso = _RedisFalso()
    import redis

    monkeypatch.setattr(redis, "Redis", lambda **kw: falso)
    return falso


@pytest.mark.parametrize(
    "racha, horas_esperadas",
    [
        (0, 6),    # condición nueva: ventana corta, no se retrasa nada
        (1, 24),   # sigue ahí al día siguiente: una vez al día
        (2, 72),   # lleva días: cada tres
        (9, 72),   # el escalado tiene tope
    ],
)
def test_el_recordatorio_se_espacia_si_nadie_resuelve(redis_falso, racha, horas_esperadas):
    from tasks.anomaly_tasks import _horas_con_escalado, _racha_key

    clave = "ESTRES_TERMICO_CRITICO"
    if racha:
        redis_falso.valores[_racha_key(clave)] = racha

    assert _horas_con_escalado(clave, 6) == horas_esperadas


def test_una_condicion_distinta_estrena_su_propia_racha(redis_falso):
    """Una alerta nueva no hereda el castigo de otra que lleva días."""
    from tasks.anomaly_tasks import _horas_con_escalado, _incrementar_racha

    for _ in range(5):
        _incrementar_racha("VIEJA")

    assert _horas_con_escalado("VIEJA", 6) == 72
    assert _horas_con_escalado("NUEVA", 6) == 6


def test_sin_redis_se_usa_la_ventana_base(monkeypatch):
    from tasks.anomaly_tasks import _horas_con_escalado
    import redis

    def _explota(**kw):
        raise ConnectionError("Redis caído")

    monkeypatch.setattr(redis, "Redis", _explota)
    assert _horas_con_escalado("X", 6) == 6


# ── Anomalías: datos congelados es un problema del ETL, no del SIN ────────────

def test_datos_congelados_esta_clasificado_como_tecnico():
    from tasks.anomaly_tasks import CATEGORIAS_TECNICAS

    assert "DATOS_CONGELADOS" in CATEGORIAS_TECNICAS


@pytest.mark.parametrize(
    "categoria",
    ["EMBALSES", "ESTRES_TERMICO", "HIDROLOGIA", "DEMANDA",
     "PRECIO_MERCADO", "Costo Unitario", "Pérdidas No Técnicas"],
)
def test_las_alertas_del_sector_siguen_llegando_al_negocio(categoria):
    from tasks.anomaly_tasks import CATEGORIAS_TECNICAS

    assert categoria not in CATEGORIAS_TECNICAS


def test_un_lote_mixto_sale_en_dos_envios_con_publicos_distintos(monkeypatch):
    """Lo técnico y lo del SIN no pueden viajar en el mismo correo."""
    from tasks import anomaly_tasks

    envios: list[dict] = []

    def _broadcast(**kw):
        envios.append(kw)
        return {"telegram": {"sent": 1}, "email": {"sent": 1}}

    monkeypatch.setattr(
        "domain.services.notification_service.broadcast_alert", _broadcast
    )
    monkeypatch.setattr(
        "domain.services.notification_service.build_alert_email_html",
        lambda a: "<p>x</p>",
    )
    monkeypatch.setattr(anomaly_tasks, "_registrar_alerta_bd", lambda *a, **k: None)
    monkeypatch.setattr(anomaly_tasks, "_activar_cooldown_alerta", lambda *a, **k: True)
    monkeypatch.setattr(anomaly_tasks, "_incrementar_racha", lambda *a, **k: None)
    monkeypatch.setattr(anomaly_tasks, "_horas_con_escalado", lambda c, h: h)

    anomaly_tasks._notificar_lote(
        [{"categoria": "EMBALSES", "severidad": "CRÍTICO", "clave": "E"}],
        tecnica=False,
    )
    anomaly_tasks._notificar_lote(
        [{"categoria": "DATOS_CONGELADOS", "severidad": "CRÍTICO", "clave": "D"}],
        tecnica=True,
    )

    assert [e["tecnica"] for e in envios] == [False, True]
    assert "SISTEMA ELÉCTRICO" in envios[0]["message"]
    assert "AVISO TÉCNICO" in envios[1]["message"]


# ── SMTP: cuándo se reintenta y cuándo NO ─────────────────────────────────────

class _ServidorSmtpFalso:
    """Simula smtplib.SMTP. `fallos` dice en qué paso revienta cada intento."""

    intentos: list = []

    def __init__(self, fallar_en=None):
        self.fallar_en = fallar_en

    def __call__(self, server, port, timeout=None):
        _ServidorSmtpFalso.intentos.append("conexion")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        if self.fallar_en == "handshake":
            raise TimeoutError("The handshake operation timed out")

    def login(self, u, p):
        pass

    def sendmail(self, de, para, msg):
        if self.fallar_en == "sendmail":
            raise TimeoutError("timeout con el mensaje en vuelo")


@pytest.fixture
def smtp(monkeypatch):
    import domain.services.notification_service as ns

    _ServidorSmtpFalso.intentos = []
    monkeypatch.setattr(ns, "_smtp_config", lambda: {
        "server": "smtp.x", "port": 587, "user": "u", "password": "p",
        "from_name": "Portal",
    })
    monkeypatch.setattr(ns, "_acquire_smtp_send_lock", lambda: None)
    monkeypatch.setattr(ns, "_release_smtp_send_lock", lambda c: None)
    monkeypatch.setattr(ns.time, "sleep", lambda s: None)
    monkeypatch.setattr(ns, "SMTP_CONEXION_ESPERA_S", 0)
    return ns


def test_un_handshake_caido_se_reintenta(smtp, monkeypatch):
    """Es exactamente lo que dejó a un destinatario sin el informe del viernes."""
    monkeypatch.setattr(smtp.smtplib, "SMTP", _ServidorSmtpFalso("handshake"))

    ok, error, _ = smtp._send_one_email("a@b.gov.co", "asunto", "<p>x</p>")

    assert ok is False
    assert len(_ServidorSmtpFalso.intentos) == smtp.SMTP_CONEXION_MAX_REINTENTOS
    assert "timed out" in error


def test_el_reintento_entrega_cuando_la_red_se_recupera(smtp, monkeypatch):
    class _FallaUnaVez(_ServidorSmtpFalso):
        def starttls(self, context=None):
            if len(_ServidorSmtpFalso.intentos) == 1:
                raise TimeoutError("handshake timed out")

    monkeypatch.setattr(smtp.smtplib, "SMTP", _FallaUnaVez())

    ok, error, _ = smtp._send_one_email("a@b.gov.co", "asunto", "<p>x</p>")

    assert ok is True
    assert error is None
    assert len(_ServidorSmtpFalso.intentos) == 2


def test_un_mensaje_ya_entregado_NO_se_reintenta(smtp, monkeypatch):
    """En cuanto sendmail empieza, el servidor puede haberlo aceptado.

    Repetir ahí mandaría el informe dos veces a la misma persona, que es peor
    que no mandarlo: el reintento solo cubre fallos previos a la entrega.
    """
    monkeypatch.setattr(smtp.smtplib, "SMTP", _ServidorSmtpFalso("sendmail"))

    ok, error, _ = smtp._send_one_email("a@b.gov.co", "asunto", "<p>x</p>")

    assert ok is False
    assert len(_ServidorSmtpFalso.intentos) == 1, "no puede haber segundo intento"
    assert "NO se reintenta" in error

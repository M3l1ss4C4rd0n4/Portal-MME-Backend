"""Pruebas del Informe Semanal de Dirección de Energía.

Cubren la lógica pura: formato de números, signo del delta según el sentido del
indicador, validez del SVG e inmutabilidad del modelo. Nada aquí toca la red ni
la base de datos.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

import pytest

from domain.services.informe_de_modelo import Kpi, Punto, Seccion, Serie, kpis_planos
from domain.services.informe_de_recoleccion import _cop_corto, _miles, _num, _pct
from domain.services.informe_de_render import Paleta, formatear
from domain.services.informe_de_snapshot import aplicar_deltas
from domain.services.informe_de_svg import (
    Barra,
    barra_apilada,
    barras_horizontales,
    medidor,
)

pytestmark = pytest.mark.unit


# ── Formato ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "valor, formato, esperado",
    [
        (7207021650458.0, "cop_corto", "$7,21 bill."),
        (41881517103.0, "cop_corto", "$41,9 mil M"),
        (9557133, "num", "9.557.133"),
        (44570.345, "num1", "44.570,3"),
        (None, "cop_corto", "N/D"),
    ],
)
def test_formatea_con_convencion_colombiana(valor, formato, esperado):
    # Arrange / Act
    salida = formatear(valor, formato)
    # Assert
    assert salida == esperado


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (99.8747, "99,87%"),   # cerca de 100: el segundo decimal ES el dato
        (4.37, "4,37%"),       # por debajo de 10: idem
        (70.773, "70,8%"),     # rango medio: un decimal se lee mejor
        (87.18, "87,2%"),
    ],
)
def test_porcentaje_conserva_el_decimal_que_importa(valor, esperado):
    assert formatear(valor, "pct") == esperado


def test_render_y_recoleccion_formatean_el_porcentaje_igual():
    """La tarjeta y su medidor muestran la misma cifra; si las dos reglas de
    decimales se separan, se ve 4,4% en una y 4,37% en el otro."""
    for valor in (99.8747, 4.37, 70.773, 87.18, 54.39):
        decimales = 2 if (abs(valor) < 10 or abs(valor) >= 99) else 1
        assert formatear(valor, "pct") == _pct(valor, decimales)


def test_cop_corto_no_mezcla_separadores():
    # El bug original producía "$5.10 billones": punto como decimal.
    assert _cop_corto(5100632943882.43) == "$5,10 billones"
    assert "," in _cop_corto(5100632943882.43)


@pytest.mark.parametrize("entrada, esperado", [("34113.0", 34113.0), ("", None), (None, None), ("x", None), (7, 7.0)])
def test_num_tolera_basura_sin_lanzar(entrada, esperado):
    assert _num(entrada) == esperado


def test_miles_con_decimales():
    assert _miles(44570.345, 1) == "44.570,3"
    assert _miles(None) == "N/D"


# ── Delta: el signo se lee por el sentido del indicador ───────────────────────

def _seccion_con(kpi: Kpi) -> Seccion:
    return Seccion(clave="s", titulo="S", subtitulo="", corte="", kpis=(kpi,))


def test_delta_se_calcula_contra_la_foto_anterior():
    kpi = Kpi("k", "K", 70.0, "pct")
    salida = aplicar_deltas([_seccion_con(kpi)], date(2026, 10, 28), date(2026, 10, 27), {("s", "k"): 68.0})
    assert salida[0].kpis[0].delta == pytest.approx(2.0)
    assert salida[0].kpis[0].dias_delta == 1


def test_delta_informa_cuantos_dias_cubre_cuando_hay_hueco():
    """Si la tarea no corrió el fin de semana el delta compara contra el
    viernes, y el informe tiene que decirlo en vez de insinuar 'ayer'."""
    kpi = Kpi("k", "K", 10.0, "num")
    salida = aplicar_deltas([_seccion_con(kpi)], date(2026, 10, 28), date(2026, 10, 24), {("s", "k"): 8.0})
    assert salida[0].kpis[0].dias_delta == 4


def test_sin_foto_anterior_el_delta_queda_vacio_no_en_cero():
    kpi = Kpi("k", "K", 10.0, "num")
    salida = aplicar_deltas([_seccion_con(kpi)], date(2026, 10, 28), None, {})
    assert salida[0].kpis[0].delta is None, "un indicador nuevo no es uno que no cambió"


def test_aplicar_deltas_no_muta_la_seccion_original():
    kpi = Kpi("k", "K", 10.0, "num")
    original = _seccion_con(kpi)
    aplicar_deltas([original], date(2026, 10, 28), date(2026, 10, 27), {("s", "k"): 5.0})
    assert original.kpis[0].delta is None


def test_aplicar_deltas_conserva_series_y_lectura():
    seccion = Seccion(
        clave="s", titulo="S", subtitulo="", corte="",
        kpis=(Kpi("k", "K", 1.0, "num"),),
        series=(Serie("g", "G", "barras", (Punto("p", 1.0),)),),
        lectura="texto", tableros=("T",),
    )
    salida = aplicar_deltas([seccion], date(2026, 10, 28), None, {})
    assert salida[0].series == seccion.series
    assert salida[0].lectura == "texto"
    assert salida[0].tableros == ("T",)


def test_seccion_caida_pasa_sin_tocar():
    caida = Seccion(clave="s", titulo="S", subtitulo="", corte="", kpis=(), error="boom")
    salida = aplicar_deltas([caida], date(2026, 10, 28), date(2026, 10, 27), {})
    assert salida[0].error == "boom"


def test_kpis_planos_excluye_secciones_caidas_y_valores_vacios():
    buena = Seccion(clave="a", titulo="", subtitulo="", corte="",
                    kpis=(Kpi("k1", "", 1.0), Kpi("k2", "", None)))
    mala = Seccion(clave="b", titulo="", subtitulo="", corte="",
                   kpis=(Kpi("k3", "", 3.0),), error="x")
    planos = kpis_planos([buena, mala])
    assert [(s, k.clave) for s, k in planos] == [("a", "k1")]


# ── SVG ───────────────────────────────────────────────────────────────────────

def test_medidor_produce_svg_valido_con_colores_literales():
    """Con var() dentro del SVG, WeasyPrint pintaba la pista de negro."""
    svg = medidor(70.77, "Comprometido", "70,8%", color="#1d4ed8",
                  pista="#E6EBF2", tinta="#0C1726", tinta_suave="#7C8798")
    ET.fromstring(svg)
    assert "var(--" not in svg
    assert "70,8%" in svg


def test_medidor_acota_valores_fuera_de_rango():
    for valor in (-30.0, 180.0, None):
        ET.fromstring(medidor(valor, "X", "x"))


def test_barras_producen_svg_valido_y_etiquetan_cada_barra():
    """La etiqueta directa es lo que impide que la identidad dependa del color."""
    barras = (
        Barra("En ejecución", 307, "#60a5fa", "307"),
        Barra("Pérdida de competencia", 22, "#EF4444", "22"),
    )
    svg = barras_horizontales(barras, pista="#E6EBF2", tinta="#000", tinta_suave="#444")
    ET.fromstring(svg)
    assert "En ejecución" in svg and "Pérdida de competencia" in svg
    assert ">307<" in svg and ">22<" in svg


def test_barra_apilada_ignora_segmentos_vacios():
    segmentos = (Barra("A", 10, "#111", "10"), Barra("B", 0, "#222", "0"), Barra("C", None, "#333", "—"))
    svg = barra_apilada(segmentos)
    ET.fromstring(svg)
    assert svg.count("<rect") == 1


def test_series_sin_datos_no_dibujan_nada():
    assert barras_horizontales(()) == ""
    assert barra_apilada(()) == ""


# ── Paleta ────────────────────────────────────────────────────────────────────

def test_paleta_interactiva_usa_variables_y_la_impresa_no():
    viva = Paleta(modo="oscuro", usar_variables=True)
    impresa = Paleta(modo="claro", usar_variables=False)
    assert viva.color("paso-2", "azul").startswith("var(--")
    assert impresa.color("paso-2", "azul").startswith("#")
    assert viva.pista.startswith("var(--") and impresa.pista.startswith("#")


def test_paleta_acota_el_paso_fuera_de_rango():
    impresa = Paleta(modo="claro", usar_variables=False)
    assert impresa.color("paso-9", "oro") == impresa.color("paso-3", "oro")


def test_estado_critico_no_sale_de_la_rampa():
    """Los colores de estado están reservados: nunca son 'la serie 4'."""
    impresa = Paleta(modo="claro", usar_variables=False)
    critico = impresa.color("critico", "azul")
    pasos = {impresa.color(f"paso-{i}", "azul") for i in range(4)}
    assert critico not in pasos


# ── Composición del HTML ──────────────────────────────────────────────────────

from domain.services.informe_de_modelo import Informe  # noqa: E402
from domain.services.informe_de_render import (  # noqa: E402
    _chip_delta,
    _clase_delta,
    _render_seccion,
    _tarjeta_kpi,
    render,
)


@pytest.mark.parametrize(
    "sentido, delta, clase",
    [
        ("mas_es_mejor", 5.0, "delta-bien"),
        ("mas_es_mejor", -5.0, "delta-mal"),
        ("menos_es_mejor", -5.0, "delta-bien"),   # bajar el saldo pendiente es bueno
        ("menos_es_mejor", 5.0, "delta-mal"),
        ("neutro", 5.0, "delta-neutro"),
        ("mas_es_mejor", 0.0, "delta-igual"),
    ],
)
def test_color_del_delta_sigue_al_sentido_no_al_signo(sentido, delta, clase):
    """Que baje el saldo pendiente es bueno y que baje el pagado es malo:
    pintarlos por el signo diría lo contrario en uno de los dos."""
    kpi = Kpi("k", "K", 10.0, "num", sentido=sentido, delta=delta, dias_delta=1)
    assert _clase_delta(kpi) == clase


def test_chip_distingue_sin_historico_de_sin_cambio():
    sin_foto = Kpi("k", "K", 10.0, "num")
    igual = Kpi("k", "K", 10.0, "num", delta=0.0, dias_delta=1)
    assert "sin histórico" in _chip_delta(sin_foto)
    assert "sin cambio" in _chip_delta(igual)
    assert _chip_delta(sin_foto) != _chip_delta(igual)


def test_chip_nombra_la_ventana_de_comparacion():
    un_dia = Kpi("k", "K", 10.0, "num", delta=1.0, dias_delta=1)
    varios = Kpi("k", "K", 10.0, "num", delta=1.0, dias_delta=4)
    assert "vs ayer" in _chip_delta(un_dia)
    assert "hace 4 días" in _chip_delta(varios)


def test_tarjeta_marca_si_el_indicador_cambio():
    cambia = Kpi("k", "K", 10.0, "num", delta=2.0, dias_delta=1)
    quieto = Kpi("k", "K", 10.0, "num", delta=0.0, dias_delta=1)
    assert "con-cambio" in _tarjeta_kpi(cambia)
    assert "sin-cambio" in _tarjeta_kpi(quieto)


def test_el_html_escapa_lo_que_viene_de_la_fuente():
    """Las etiquetas salen de respuestas de red: no se inyectan crudas."""
    kpi = Kpi("k", "<script>alert(1)</script>", 1.0, "num")
    salida = _tarjeta_kpi(kpi)
    assert "<script>" not in salida
    assert "&lt;script&gt;" in salida


def test_seccion_caida_dice_que_no_se_pudo_evaluar():
    """'No se pudo evaluar' no es lo mismo que 'está en cero'."""
    caida = Seccion(clave="s", titulo="Subsidios", subtitulo="", corte="",
                    kpis=(), error="TimeoutError: boom")
    html = _render_seccion(caida, Paleta("claro", False), 1)
    assert "No se pudo evaluar" in html
    assert "TimeoutError" in html
    assert "0" not in html.split("TimeoutError")[0].split("kpi-valor")[-1]


def _informe_de_prueba() -> Informe:
    seccion = Seccion(
        clave="presupuesto", titulo="Presupuesto", subtitulo="sub", corte="11/09/2026",
        kpis=(Kpi("apropiacion", "Apropiación DEE", 7.2e12, "cop_corto"),),
        series=(Serie("m", "Avance", "medidores", (Punto("Comprometido", 70.8, "paso-3", "70,8%"),)),),
        lectura="Lectura.", tableros=("Presupuesto",),
    )
    return Informe(fecha="miércoles, 28 de octubre de 2026",
                   generado_en="28/10/2026 07:00", secciones=(seccion,))


def test_version_interactiva_trae_tema_oscuro_y_controles():
    html = render(_informe_de_prueba(), interactivo=True)
    assert 'data-theme="dark"' in html
    assert "btn-tema" in html and "btn-cambios" in html
    assert "<script>" in html
    assert "var(--azul-3)" in html, "las gráficas deben repintarse con el tema"


def test_version_impresa_no_lleva_javascript_ni_variables_en_el_svg():
    """WeasyPrint no ejecuta JS ni resuelve var() dentro del SVG."""
    html = render(_informe_de_prueba(), interactivo=False)
    assert "<script>" not in html
    assert 'data-theme' not in html.split("<head>")[0]
    cuerpo = html.split("</style>")[-1]
    assert "var(--" not in cuerpo


def test_el_tema_oscuro_se_declara_en_los_dos_ambitos():
    html = render(_informe_de_prueba(), interactivo=True)
    assert "@media (prefers-color-scheme:dark)" in html
    assert ':root:not([data-theme="light"])' in html
    assert ':root[data-theme="dark"]' in html


def test_la_portada_resume_una_tarjeta_por_seccion():
    html = render(_informe_de_prueba(), interactivo=True)
    assert html.count('class="titular"') == 1
    assert "$7,20 bill." in html


def test_el_informe_declara_cuantos_tableros_resume():
    html = render(_informe_de_prueba(), interactivo=True)
    assert "1 tableros" in html or "1 tablero" in html
    assert "Resume 1 tablero" in html


def test_la_unidad_se_separa_de_la_cifra():
    """Con nowrap, "44.570,3 kWp" al mismo tamaño rozaba el borde de la tarjeta."""
    kpi = Kpi("k", "Capacidad", 44570.345, "num1", unidad="kWp")
    html = _tarjeta_kpi(kpi)
    assert "44.570,3" in html
    assert 'class="kpi-unidad">kWp<' in html
    assert "44.570,3 kWp" not in html, "la unidad va en su propio span, no pegada"


def test_un_kpi_sin_unidad_no_deja_span_vacio():
    html = _tarjeta_kpi(Kpi("k", "Contratos", 842.0, "num"))
    assert "kpi-unidad" not in html


def test_la_portada_usa_el_titulo_corto_cuando_existe():
    seccion = Seccion(
        clave="programas", titulo="Colombia Solar y Contratos OR",
        titulo_corto="Colombia Solar · OR", subtitulo="", corte="",
        kpis=(Kpi("k", "Usuarios", 536.0, "num"),),
    )
    informe = Informe(fecha="f", generado_en="g", secciones=(seccion,))
    html = render(informe, interactivo=True)
    portada = html.split('class="portada"')[1].split("</div></div>")[0]
    assert "Colombia Solar · OR" in portada
    # El título largo sigue encabezando su sección.
    assert "Colombia Solar y Contratos OR" in html


def test_un_dia_sin_datos_no_borra_la_foto_anterior():
    """Guardar borra e inserta el día completo. Sin esta guarda, una jornada en
    que todas las fuentes fallan dejaría la tabla vacía y al día siguiente no
    habría nada con que comparar. Devuelve 0 antes de tocar la base."""
    from domain.services.informe_de_snapshot import guardar_snapshot

    todas_caidas = [
        Seccion(clave="a", titulo="", subtitulo="", corte="", kpis=(), error="boom"),
        Seccion(clave="b", titulo="", subtitulo="", corte="",
                kpis=(Kpi("k", "K", None, "num"),)),
    ]
    assert guardar_snapshot(date(2026, 10, 28), todas_caidas) == 0

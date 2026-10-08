"""
Tests unitarios — auditoría del informe ejecutivo diario y del motor de alertas
(octubre 2026), previa al alta de un nuevo destinatario.

El pipeline que genera el informe de las 8:30 y las alertas tenía cobertura
efectiva cero: los únicos tests que decían cubrirlo importaban
`ExecutiveReportService`, que no tiene ningún caller, y además estaban
deseleccionados por el `-m "not slow"` de pytest.ini. Estos tests cubren la
lógica pura de los defectos corregidos, sin tocar BD ni red, para que no
vuelvan en silencio.

Cada bloque referencia el comportamiento real que se observó en producción.
"""

from unittest.mock import patch

import pytest

from core.constants import normalizar_severidad
from core.umbrales_oficiales import (
    SENDA_MARGEN_VIGILANCIA_PP,
    SENDA_TOLERANCIA_PP,
    clasificar_indice_ne,
    clasificar_vigilancia_embalse,
    clasificar_visual_embalse,
    determinar_condicion_sistema,
)
from domain.services.report_service import (
    _proyeccion_tendencia_html,
    _variacion_demanda_html,
    _variacion_tarjeta_html,
)

SENDA_FIJA = 78.0


@pytest.fixture
def senda_fija():
    """Fija la senda para no depender de la BD ni de la fecha."""
    with patch("core.umbrales_oficiales.obtener_senda_referencia", return_value=SENDA_FIJA):
        yield SENDA_FIJA


# ───────────────────────────────────────────────────────────────────────
# Índice NE: la norma es binaria
# ───────────────────────────────────────────────────────────────────────

class TestIndiceNEBinario:
    def test_tolerancia_es_cero_por_norma(self):
        # El 0.0 es deliberado: CREG 026/2014 art. 2 lit. B, mod. Res. CREG
        # 101 112/2026, compara contra la senda sin banda intermedia.
        assert SENDA_TOLERANCIA_PP == 0.0

    def test_solo_devuelve_superior_o_inferior(self, senda_fija):
        niveles = {clasificar_indice_ne(p)[0] for p in (95.0, 78.1, 78.0, 77.99, 60.0, 10.0)}
        assert niveles <= {"SUPERIOR", "INFERIOR"}

    def test_en_la_senda_es_superior_y_un_pelo_abajo_es_inferior(self, senda_fija):
        assert clasificar_indice_ne(78.0)[0] == "SUPERIOR"
        assert clasificar_indice_ne(77.99)[0] == "INFERIOR"

    def test_descripcion_no_menciona_tolerancia_en_pp(self, senda_fija):
        # Antes decía "< senda 78.0% − 0.0pp", que sugería una banda que no existe.
        assert "0.0pp" not in clasificar_indice_ne(60.0)[1]


# ───────────────────────────────────────────────────────────────────────
# Gradiente de vigilancia: criterio propio, y debe decirlo
# ───────────────────────────────────────────────────────────────────────

class TestVigilanciaEsCriterioPropio:
    def test_gradua_entre_apenas_abajo_y_muy_abajo(self, senda_fija):
        # El motor de alertas trataba igual 0,1pp y 30pp bajo la senda:
        # 61 alertas CRÍTICO y ninguna intermedia en 5 meses.
        assert clasificar_vigilancia_embalse(78.5)[0] == "SOBRE_SENDA"
        assert clasificar_vigilancia_embalse(77.9)[0] == "VIGILANCIA"
        assert clasificar_vigilancia_embalse(73.5)[0] == "VIGILANCIA"
        assert clasificar_vigilancia_embalse(72.0)[0] == "DEFICIT"

    def test_el_corte_es_el_margen_declarado(self, senda_fija):
        limite = SENDA_FIJA - SENDA_MARGEN_VIGILANCIA_PP
        assert clasificar_vigilancia_embalse(limite)[0] == "VIGILANCIA"
        assert clasificar_vigilancia_embalse(limite - 0.01)[0] == "DEFICIT"

    @pytest.mark.parametrize("pct", [77.9, 60.0])
    def test_declara_que_el_margen_no_es_creg(self, senda_fija, pct):
        descripcion = clasificar_vigilancia_embalse(pct)[1]
        assert "criterio propio" in descripcion.lower()
        assert "no CREG" in descripcion

    def test_visual_no_atribuye_su_banda_a_la_creg(self, senda_fija):
        # Antes la justificación decía "NE Alerta (CREG 026/2014)", una banda
        # que la norma no contempla.
        etiqueta, _color, justificacion = clasificar_visual_embalse(75.0)
        assert etiqueta == "BAJO SENDA — VIGILANCIA"
        assert "criterio propio" in justificacion.lower()
        assert "NE Alerta" not in justificacion


# ───────────────────────────────────────────────────────────────────────
# El CIS no cambia al volver binario el NE
# ───────────────────────────────────────────────────────────────────────

class TestCondicionSistemaSinCambios:
    @pytest.mark.parametrize(
        "ne,hsin,pbp,esperado",
        [
            ("INFERIOR", "DEFICIT_SEVERO", "ALTO", "RIESGO"),
            ("INFERIOR", "NORMAL", "BAJO", "VIGILANCIA"),
            ("SUPERIOR", "VIGILANCIA", "BAJO", "VIGILANCIA"),
            ("SUPERIOR", "NORMAL", "ALTO", "VIGILANCIA"),
            ("SUPERIOR", "NORMAL", "BAJO", "NORMAL"),
        ],
    )
    def test_combinaciones_del_articulo_3(self, ne, hsin, pbp, esperado):
        assert determinar_condicion_sistema(ne, hsin, pbp)[0] == esperado


# ───────────────────────────────────────────────────────────────────────
# Severidad: 'CRÍTICO' con tilde salía como "AVISO" amarillo
# ───────────────────────────────────────────────────────────────────────

class TestNormalizacionSeveridad:
    @pytest.mark.parametrize(
        "entrada", ["CRÍTICO", "CRITICO", "crítico", "critico", "CRITICAL", "CRITICA"]
    )
    def test_todas_las_formas_de_critico(self, entrada):
        # La BD guarda 'CRÍTICO'; el dict de colores no lo tenía y la alerta
        # crítica se degradaba a badge amarillo "AVISO" en el informe diario.
        assert normalizar_severidad(entrada) == "CRITICO"

    def test_alerta_no_se_confunde_con_critico(self):
        assert normalizar_severidad("ALERTA") == "ALERTA"
        assert normalizar_severidad("alerta") == "ALERTA"


# ───────────────────────────────────────────────────────────────────────
# Proyección lineal de tendencia: "Proy: -56 %" de embalses
# ───────────────────────────────────────────────────────────────────────

class TestProyeccionTendencia:
    def _tendencia(self, **extra):
        base = {
            "proyeccion_7dias": 70.0,
            "confianza_tendencia": "alta",
            "proyeccion_acotada": False,
        }
        base.update(extra)
        return base

    def test_publica_una_proyeccion_confiable(self):
        html = _proyeccion_tendencia_html(self._tendencia(), "%")
        assert "70" in html

    def test_se_rotula_como_extrapolacion_lineal(self):
        # Para que no se confunda con la predicción del modelo ENSEMBLE, que
        # aparece en páginas contiguas con otro valor.
        assert "lineal" in _proyeccion_tendencia_html(self._tendencia(), "%").lower()

    def test_oculta_la_proyeccion_si_hubo_que_acotarla(self):
        # Si el valor crudo era imposible, recortarlo no lo vuelve informativo.
        assert _proyeccion_tendencia_html(self._tendencia(proyeccion_acotada=True), "%") == ""

    def test_oculta_la_proyeccion_con_r2_bajo(self):
        assert _proyeccion_tendencia_html(self._tendencia(confianza_tendencia="baja"), "%") == ""

    def test_tolera_ausencia_de_datos(self):
        assert _proyeccion_tendencia_html({}, "%") == ""
        assert _proyeccion_tendencia_html({"proyeccion_7dias": None}, "%") == ""


# ───────────────────────────────────────────────────────────────────────
# Variaciones de las tarjetas: la flecha ▼ roja estaba hardcodeada
# ───────────────────────────────────────────────────────────────────────

class TestVariacionesRespetanElSigno:
    def test_alza_se_dibuja_hacia_arriba(self):
        html = _variacion_tarjeta_html(64.54, "Variación Mensual")
        assert "&#9650;" in html        # ▲
        assert "64.54" in html

    def test_caida_se_dibuja_hacia_abajo(self):
        assert "&#9660;" in _variacion_tarjeta_html(-72.51, "Variación Semanal")

    def test_sin_dato_muestra_nd_en_vez_de_inventar(self):
        assert "N/D" in _variacion_tarjeta_html(None, "Variación Mensual")

    def test_demanda_al_alza_no_se_pinta_de_rojo(self):
        html = _variacion_demanda_html(3.2)
        assert "&#9650;" in html
        assert "#C62828" not in html    # el rojo que estaba fijo

    def test_demanda_sin_dato(self):
        assert "N/D" in _variacion_demanda_html(None)


# ───────────────────────────────────────────────────────────────────────
# Narrativa de la IA: se perdían "Riesgos" y "Recomendaciones" a diario
# ───────────────────────────────────────────────────────────────────────

class TestRecorteDeNarrativa:
    @staticmethod
    def _handler():
        from domain.services.orchestrator.handlers.informe_handler import (
            InformeHandlerMixin,
        )
        return InformeHandlerMixin.__new__(InformeHandlerMixin)

    @staticmethod
    def _narrativa(relleno: int) -> str:
        secciones = [
            ("1.", "Contexto general del sistema"),
            ("2.", "Señales clave y evolución"),
            ("2.1", "Proyecciones del próximo mes"),
            ("2.2", "Análisis cualitativo"),
            ("3.", "Riesgos y oportunidades"),
            ("4.", "Recomendaciones técnicas"),
            ("5.", "Calificación del sistema"),
        ]
        return "\n\n".join(
            f"## {num} {titulo}\n" + "x" * relleno for num, titulo in secciones
        )

    def test_texto_corto_no_se_toca(self):
        texto = self._narrativa(50)
        assert self._handler()._ajustar_longitud_informe(texto, len(texto)) == texto

    def test_conserva_riesgos_y_recomendaciones(self):
        # El recorte anterior era de corrido desde el principio, así que las
        # secciones 3 y 4 —lo accionable— se perdían enteras todos los días.
        texto = self._narrativa(1200)
        resultado = self._handler()._ajustar_longitud_informe(texto, len(texto))
        assert "## 3. Riesgos y oportunidades" in resultado
        assert "## 4. Recomendaciones técnicas" in resultado
        assert "## 5. Calificación del sistema" in resultado

    def test_sacrifica_primero_el_detalle_cualitativo(self):
        texto = self._narrativa(1200)
        resultado = self._handler()._ajustar_longitud_informe(texto, len(texto))
        assert "## 2.2" not in resultado

    def test_respeta_el_limite(self):
        handler = self._handler()
        texto = self._narrativa(2000)
        resultado = handler._ajustar_longitud_informe(texto, len(texto))
        assert len(resultado) <= handler.MAX_CHARS_INFORME_IA

    def test_texto_sin_secciones_reconocibles_no_revienta(self):
        texto = "párrafo suelto.\n\n" * 900
        resultado = self._handler()._ajustar_longitud_informe(texto, len(texto))
        assert 0 < len(resultado) <= self._handler().MAX_CHARS_INFORME_IA

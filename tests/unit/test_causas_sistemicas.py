"""
Tests de regresión — causas sistémicas (octubre 2026).

Cubren defectos que ya ocurrieron y que el sistema no supo detectar por sí
mismo. Cada bloque cita el caso real para que, si alguien revierte el arreglo,
el test diga exactamente qué se rompió.
"""

from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from domain.services.losses_nt_service import (
    LossesNTService,
    _PNT_MATERIALIDAD_REL,
    _PNT_Z_ROBUSTO_ALERTA,
    _STN_PARTIAL_DAY_PCT,
)


def _serie_pnt(valores):
    return pd.DataFrame({
        "fecha": pd.date_range("2026-06-01", periods=len(valores)),
        "pnt_pct": valores,
    })


def _detectar(valores):
    svc = LossesNTService()
    with patch.object(LossesNTService, "_get_series_pnt", return_value=_serie_pnt(valores)):
        return svc.detect_anomalies_isolation_forest(date(2026, 6, 1), date(2026, 10, 1))


ESTABLE = list(np.linspace(3.24, 3.37, 115))   # rango real medido de la serie


class TestSeveridadPNTNiInerteNiRuidosa:
    """
    El umbral de severidad del PNT falló en los dos extremos:

    - Primero era puramente relativo (percentiles del score de Isolation
      Forest), así que con `contamination` fija marcaba un 5% de los días como
      CRITICO aunque la serie fuera plana.
    - Luego se puso un umbral absoluto de 1,0 pp, que resultó INERTE: la serie
      real tiene un rango de 0,13 pp, así que nada podía superarlo nunca y el
      detector quedó produciendo cero inserciones, indistinguible de estar
      muerto (la tabla `anomalies` llevaba 5,5 meses congelada).

    Ahora exige z robusto (inusual para esta serie) Y materialidad relativa
    (lo bastante grande para importar). Estos tests fijan ambos extremos.
    """

    def test_serie_estable_no_genera_ninguna_alerta(self):
        df = _detectar(ESTABLE + list(np.linspace(3.30, 3.35, 5)))
        assert set(df["severidad"].unique()) == {"NORMAL"}

    def test_ruido_pequeno_no_escala(self):
        # +0,05 pp sobre una serie de 3,3%: inusual para el modelo, irrelevante
        # para el negocio. No debe alertar.
        df = _detectar(ESTABLE + [3.42] * 5)
        assert set(df["severidad"].unique()) == {"NORMAL"}

    @pytest.mark.parametrize("valor_anomalo", [4.1, 2.1])
    def test_desviacion_material_si_escala(self, valor_anomalo):
        # Saltos de +0,8 pp y −1,2 pp sobre 3,3%: deben detectarse.
        df = _detectar(ESTABLE + [valor_anomalo] * 5)
        assert (df["severidad"] != "NORMAL").any(), (
            f"Un desvío a {valor_anomalo}% debe escalar; si no, el umbral "
            f"volvió a quedar inerte."
        )

    def test_los_umbrales_son_relativos_no_absolutos(self):
        # Blindaje directo contra la regresión: un umbral en puntos
        # porcentuales fijos no puede volver.
        assert 0 < _PNT_MATERIALIDAD_REL < 1, "la materialidad debe ser una fracción del nivel"
        assert _PNT_Z_ROBUSTO_ALERTA > 0


class TestGuardaDeDiaParcial:
    """
    `losses_detailed` se escribía con el día de XM todavía parcial (demanda de
    ~50 GWh contra ~245 reales). Con esa demanda el PNT salía negativo y el
    filtro posterior descartaba el 100% de las filas, dejando al Isolation
    Forest sin datos desde abril de 2026.
    """

    def test_umbral_de_dia_parcial_es_fisicamente_imposible(self):
        # P_STN = (Gene − DemaReal)/Gene. Las pérdidas STN reales del SIN
        # rondan 1,4%; un 20% implicaría DemaReal < 80% de Gene.
        assert _STN_PARTIAL_DAY_PCT >= 10.0


class TestSeccionesDelInformeNoFallanEnSilencio:
    """
    Un NameError en `_build_embalses_regionales` borró la sección "Nivel por
    Región Hidrológica" del informe diario durante dos días: el `except` lo
    registraba como `warning(... "(no crítico)")` y dejaba la sección vacía.
    """

    @staticmethod
    def _handler():
        from domain.services.orchestrator.handlers.informe_handler import (
            InformeHandlerMixin,
        )
        return InformeHandlerMixin.__new__(InformeHandlerMixin)

    def test_una_seccion_que_falla_queda_registrada(self):
        fallidas = []
        h = self._handler()

        def revienta():
            raise NameError("name 'nivel_ne_reg' is not defined")

        resultado = h._construir_seccion("embalses_regionales", revienta, {}, fallidas)
        assert resultado == {}
        assert len(fallidas) == 1
        assert fallidas[0]["seccion"] == "embalses_regionales"
        assert "NameError" in fallidas[0]["error"]

    def test_una_seccion_sana_no_ensucia_el_registro(self):
        fallidas = []
        h = self._handler()
        resultado = h._construir_seccion("ok", lambda: {"dato": 1}, {}, fallidas)
        assert resultado == {"dato": 1}
        assert fallidas == []


class TestEmbalsesRegionalesDevuelveAmbasClasificaciones:
    """
    El semáforo regional usa el gradiente de vigilancia (criterio propio) pero
    el campo `indice_ne` debe seguir llevando el nivel OFICIAL del Estatuto
    CREG. Mezclarlos fue lo que dejó la referencia colgada.
    """

    def test_el_campo_oficial_y_el_propio_son_distintos_campos(self):
        import inspect
        from domain.services.orchestrator.handlers import estado_actual_handler

        fuente = inspect.getsource(estado_actual_handler)
        assert "'indice_ne': nivel_ne_reg" in fuente
        assert "'nivel_vigilancia': nivel_vig_reg" in fuente
        # La variable del campo oficial tiene que asignarse de verdad.
        assert "nivel_ne_reg, _desc_ne_reg, _senda_reg = clasificar_indice_ne(" in fuente

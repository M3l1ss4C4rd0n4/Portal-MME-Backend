"""
Tests unitarios — Fase 44: vigilancia normativa CREG (notificación
inteligente + mapa de impacto).

Cubre lo más frágil del mecanismo nuevo, sin tocar la BD real:
  1. Determinismo de `_clave_hash` (la clave primaria persistente en
     ontologia.vigilancia_normativa_notificado).
  2. Filtrado de hallazgos ya notificados, con la BD mockeada.
  3. Las 8 resoluciones núcleo (NUCLEO_RESOLUCIONES_CREG) tienen entrada en
     MAPA_IMPACTO_RESOLUCIONES.
  4. El mensaje resumido (Telegram, límite duro de 4096 caracteres) nunca
     excede TELEGRAM_LIMITE_CARACTERES, incluso con un backlog grande —
     regresión directa del bug real encontrado en la primera corrida en
     producción (25 hallazgos con el mapa de impacto completo superaron el
     límite y Telegram rechazó el mensaje con "400 message is too long").
"""

from unittest.mock import patch

import pandas as pd
import pytest

from scripts.ontologia import vigilancia_normativa_creg as v
from scripts.ontologia.build_informes_embeddings import NUCLEO_RESOLUCIONES_CREG, _normalizar_segmentos_numero_creg


def _hallazgo(resolucion_nucleo="Resolución 26 de 2014 CREG", elemento="Numeral",
              accion="modificado", articulo="1", num_res="101 112", anio_res=2026):
    clave = (resolucion_nucleo, elemento.lower(), accion, articulo, num_res, anio_res)
    return {
        "clave": clave,
        "resolucion_nucleo": resolucion_nucleo,
        "elemento": elemento,
        "accion": accion,
        "articulo_modificador": articulo,
        "resolucion_modificadora": f"{num_res} de {anio_res}",
    }


class TestClaveHash:
    def test_determinista(self):
        clave = ("Resolución 26 de 2014 CREG", "numeral", "modificado", "1", "101 112", 2026)
        assert v._clave_hash(clave) == v._clave_hash(clave)

    def test_distinta_clave_distinto_hash(self):
        clave_a = ("Resolución 26 de 2014 CREG", "numeral", "modificado", "1", "101 112", 2026)
        clave_b = ("Resolución 26 de 2014 CREG", "numeral", "modificado", "2", "101 112", 2026)
        assert v._clave_hash(clave_a) != v._clave_hash(clave_b)

    def test_es_sha256_hex(self):
        clave = ("x", "y", "z", "1", "1", 2026)
        h = v._clave_hash(clave)
        assert len(h) == 64
        int(h, 16)  # no lanza ValueError si es hex válido


class TestFiltrarHallazgosNuevos:
    def test_todo_nuevo_cuando_tabla_vacia(self):
        h1, h2 = _hallazgo(articulo="1"), _hallazgo(articulo="2")
        with patch.object(v.db_manager, "query_df", return_value=pd.DataFrame({"clave_hash": []})):
            nuevos = v._filtrar_hallazgos_nuevos([h1, h2])
        assert nuevos == [h1, h2]

    def test_filtra_ya_notificados(self):
        h1, h2 = _hallazgo(articulo="1"), _hallazgo(articulo="2")
        ya_notificado = v._clave_hash(h1["clave"])
        with patch.object(
            v.db_manager, "query_df",
            return_value=pd.DataFrame({"clave_hash": [ya_notificado]}),
        ):
            nuevos = v._filtrar_hallazgos_nuevos([h1, h2])
        assert nuevos == [h2]

    def test_lista_vacia_no_consulta_bd(self):
        with patch.object(v.db_manager, "query_df") as mock_query:
            nuevos = v._filtrar_hallazgos_nuevos([])
        assert nuevos == []
        mock_query.assert_not_called()

    def test_degrada_a_no_filtrar_si_falla_la_consulta(self):
        """Si la migración 041 aún no se aplicó (tabla inexistente) o la BD
        falla, se prefiere reenviar un aviso real a perderlo por un error de
        infraestructura — nunca al revés."""
        h1 = _hallazgo()
        with patch.object(v.db_manager, "query_df", side_effect=RuntimeError("tabla no existe")):
            nuevos = v._filtrar_hallazgos_nuevos([h1])
        assert nuevos == [h1]


class TestMapaImpactoResoluciones:
    @pytest.mark.parametrize("anio,numero", NUCLEO_RESOLUCIONES_CREG)
    def test_cada_resolucion_nucleo_tiene_entrada(self, anio, numero):
        clave = f"{_normalizar_segmentos_numero_creg(numero)}_{anio}"
        assert clave in v.MAPA_IMPACTO_RESOLUCIONES

    @pytest.mark.parametrize("nombre_archivo", [
        "Resolución 101_112 de 2026 CREG",
        "Resolución 101_55 de 2024 CREG",
        "Resolución 101_66 de 2024 CREG",
        "Resolución 125 de 2020 CREG",
        "Resolución 140 de 2017 CREG",
        "Resolución 209 de 2020 CREG",
        "Resolución 26 de 2014 CREG",
        "Resolución 71 de 2006 CREG",
    ])
    def test_impacto_de_hallazgo_resuelve_nombre_archivo_real(self, nombre_archivo):
        impacto = v._impacto_de_hallazgo(nombre_archivo)
        assert impacto["descripcion"], f"sin match para {nombre_archivo!r}"

    def test_nombre_archivo_desconocido_degrada_sin_lanzar(self):
        impacto = v._impacto_de_hallazgo("Resolución 999 de 2099 CREG")
        assert impacto["funciones_python"] == []
        assert impacto["espejo_ts"] == []
        assert impacto["cubierto_por_verificador_sincronia"] is False


class TestConstruirTextoNotificacion:
    def test_resumido_bajo_limite_telegram_con_backlog_grande(self):
        """Regresión directa del bug real: 25 hallazgos con el mapa de
        impacto completo (resumido=False) superaron 4096 caracteres y
        Telegram rechazó el mensaje para todos los destinatarios."""
        hallazgos = [_hallazgo(articulo=str(i)) for i in range(40)]
        texto = v._construir_texto_notificacion(hallazgos, resumido=True)
        assert len(texto) <= 4096

    def test_full_incluye_mapa_de_impacto(self):
        h = _hallazgo(resolucion_nucleo="Resolución 26 de 2014 CREG")
        with patch.object(v, "_resultado_sincronia_texto", return_value="SINCRONIZADO ✅ (mock)"):
            texto = v._construir_texto_notificacion([h], resumido=False)
        assert "core/umbrales_oficiales.py::clasificar_indice_ne()" in texto
        assert "SINCRONIZADO ✅ (mock)" in texto

    def test_resumido_no_incluye_mapa_de_impacto(self):
        h = _hallazgo(resolucion_nucleo="Resolución 26 de 2014 CREG")
        texto = v._construir_texto_notificacion([h], resumido=True)
        assert "core/umbrales_oficiales.py" not in texto
        assert "Ver el correo" in texto

"""
Tests del ETL de los cubos SICOM (etl/etl_sicom_olap.py).

Cubre las piezas puras: limpieza de celdas, construcción del MDX y las
compuertas que impiden confirmar una carga incompleta. Esas compuertas existen
porque el riesgo central de este ETL no es que falle, es que cargue datos a
medias sin que nada lo note: una respuesta vacía del cubo llegó a borrar la
tabla y registrar la corrida como exitosa.

Sin red ni base de datos.
"""

import pytest

from etl.etl_sicom_olap import (
    AGENTES,
    BASES,
    CAPACIDAD,
    COMPRAS,
    ENTERO,
    NUMERO,
    TEXTO,
    Atributo,
    _comprobar,
    _jerarquia,
    _limpiar,
    _mdx,
)


@pytest.mark.unit
class TestLimpieza:
    """Metodología §10.4-§10.6: tratamiento de vacíos y consistencia."""

    @pytest.mark.parametrize("vacio", ["", "  ", "-", "nan", "NULL", "(All)", "Unknown"])
    def test_los_centinelas_del_cubo_quedan_en_nulo(self, vacio):
        assert _limpiar(vacio, TEXTO) is None

    def test_se_recortan_los_espacios_sobrantes(self):
        # Los nombres del cubo vienen con espacios iniciales
        assert _limpiar("  CIUDAD LIMPIA BOGOTA SA. ESP  ", TEXTO) == "CIUDAD LIMPIA BOGOTA SA. ESP"

    def test_un_texto_normal_se_conserva(self):
        assert _limpiar("DISTRIBUIDOR MINORISTA", TEXTO) == "DISTRIBUIDOR MINORISTA"

    def test_cero_no_es_un_vacio(self):
        """Un 0 es un dato: capacidad cero existe y no debe perderse."""
        assert _limpiar("0", NUMERO) == "0"
        assert _limpiar(0, ENTERO) == 0

    def test_el_entero_se_convierte(self):
        assert _limpiar("2024", ENTERO) == 2024
        assert _limpiar("2024.0", ENTERO) == 2024

    def test_la_medida_conserva_su_texto_original(self):
        """Pasar por float recortaría los decimales y descuadraría la suma."""
        assert _limpiar("344931636719.3798", NUMERO) == "344931636719.3798"

    def test_notacion_cientifica_se_conserva(self):
        assert _limpiar("3.4714309748717E11", NUMERO) == "3.4714309748717E11"

    def test_un_valor_no_numerico_en_una_medida_queda_en_nulo(self):
        assert _limpiar("ENERO", NUMERO) is None

    def test_none_sigue_siendo_none(self):
        assert _limpiar(None, TEXTO) is None
        assert _limpiar(None, NUMERO) is None


@pytest.mark.unit
class TestConstruccionDeMDX:
    def test_la_jerarquia_se_deriva_del_nivel(self):
        """CURRENTMEMBER exige la jerarquía; pasarle el nivel hace fallar la consulta."""
        assert _jerarquia("[CICLO].[AÑO CICLO].[AÑO CICLO]") == "[CICLO].[AÑO CICLO]"

    def test_el_alias_de_un_atributo_es_su_ultimo_segmento(self):
        a = Atributo("[AGENTE].[TIPO ESTACION].[TIPO ESTACION]", "tipo_estacion")
        assert a.alias == "TIPO ESTACION"

    def test_sin_año_consulta_el_cubo_completo(self):
        mdx = _mdx(AGENTES)
        assert "FROM [Agentes]" in mdx
        assert "FILTER" not in mdx
        assert "NON EMPTY" in mdx

    def test_con_año_usa_subconsulta_y_la_jerarquia_correcta(self):
        mdx = _mdx(COMPRAS, "2024")
        assert "[CICLO].[AÑO CICLO].[AÑO CICLO].MEMBERS" in mdx   # nivel, para MEMBERS
        assert '[CICLO].[AÑO CICLO].CURRENTMEMBER.NAME = "2024"' in mdx  # jerarquía
        # el año debe seguir disponible como columna, por eso subconsulta y no WHERE
        assert "FROM (SELECT FILTER(" in mdx

    def test_se_piden_todas_las_medidas_de_la_base(self):
        mdx = _mdx(COMPRAS)
        assert "[Measures].[VOLUMEN COMPRADO]" in mdx
        assert "[Measures].[VOLUMEN TRANSITO]" in mdx

    def test_las_columnas_destino_cubren_atributos_y_medidas(self):
        assert COMPRAS.columnas[-2:] == ["volumen_comprado", "volumen_transito"]
        assert len(COMPRAS.columnas) == len(COMPRAS.atributos) + len(COMPRAS.medidas)


@pytest.mark.unit
class TestCompuertasDeConciliacion:
    """Si la carga no cuadra, la transacción debe abortarse, no solo anotarse."""

    def test_cero_filas_aborta(self):
        """Un cubo en reprocesamiento puede responder vacío sin dar error."""
        with pytest.raises(RuntimeError, match="0 filas"):
            _comprobar(COMPRAS, filas=0, suma=0, total_cubo=100, identidades=None,
                       carga_completa=True)

    def test_sin_total_del_cubo_aborta_una_carga_completa(self):
        with pytest.raises(RuntimeError, match="no se pudo leer el total|contra qué conciliar"):
            _comprobar(COMPRAS, filas=10, suma=100, total_cubo=None, identidades=None,
                       carga_completa=True)

    def test_un_desvio_real_aborta(self):
        with pytest.raises(RuntimeError, match="NO CONCILIA"):
            _comprobar(COMPRAS, filas=10, suma=74_000, total_cubo=100_000,
                       identidades=None, carga_completa=True)

    def test_una_suma_exacta_pasa(self):
        _comprobar(COMPRAS, filas=10, suma=100_000, total_cubo=100_000,
                   identidades=None, carga_completa=True)

    def test_el_redondeo_de_float_no_dispara_la_compuerta(self):
        _comprobar(COMPRAS, filas=10, suma=100_000.0000001, total_cubo=100_000,
                   identidades=None, carga_completa=True)

    def test_agentes_concilia_por_identidad_no_por_suma(self):
        """La suma infla por el cruce; lo que cuadra es el conteo de códigos."""
        # suma inflada (10.665) pero identidades correctas (8.907)
        _comprobar(AGENTES, filas=10_665, suma=10_665, total_cubo=8_907,
                   identidades=8_907, carga_completa=True)

    def test_agentes_con_identidades_erroneas_aborta(self):
        with pytest.raises(RuntimeError, match="NO CONCILIA"):
            _comprobar(AGENTES, filas=10_665, suma=10_665, total_cubo=8_907,
                       identidades=7_000, carga_completa=True)

    def test_una_carga_parcial_no_se_concilia(self):
        """--desde carga dos años: compararlos con el total histórico no tiene sentido."""
        _comprobar(COMPRAS, filas=10, suma=5, total_cubo=None, identidades=None,
                   carga_completa=False)

    def test_la_comprobacion_previa_solo_mira_que_haya_filas(self):
        """Antes de cargar no se puede contar identidades: la tabla aún no se escribió."""
        _comprobar(AGENTES, filas=10, suma=10, total_cubo=8_907, identidades=None,
                   carga_completa=True, solo_filas=True)
        with pytest.raises(RuntimeError, match="0 filas"):
            _comprobar(AGENTES, filas=0, suma=0, total_cubo=8_907, identidades=None,
                       carga_completa=True, solo_filas=True)


@pytest.mark.unit
class TestDefinicionDeLasBases:
    def test_las_tres_bases_estan_registradas(self):
        assert set(BASES) == {"agentes", "capacidad", "compras"}

    def test_compras_no_incluye_la_dimension_que_descarta_volumen(self):
        """Cualquier atributo de [AGENTE PROVEEDOR] descarta el 30,8 % del volumen."""
        niveles = [a.nivel for a in COMPRAS.atributos]
        assert not any("[AGENTE PROVEEDOR]" in n for n in niveles)
        # el proveedor se identifica por planta, que sí es lossless
        assert any("[PLANTA AGENTE PROVEEDOR]" in n for n in niveles)

    def test_las_bases_con_ciclo_se_trocean_por_año(self):
        assert COMPRAS.trocear_por_anio and CAPACIDAD.trocear_por_anio
        assert not AGENTES.trocear_por_anio

    def test_agentes_tiene_clave_de_identidad(self):
        assert AGENTES.identidad == "codigo_sicom_agente"
        assert AGENTES.conciliar_por_identidad

    def test_capacidad_conserva_la_dimension_de_ciclo(self):
        """El Excel la colapsaba y por eso el total no era capacidad instalada."""
        columnas = CAPACIDAD.columnas
        assert "anio_ciclo" in columnas and "mes_ciclo" in columnas

    def test_todas_las_bases_extraen_codigos_dane(self):
        for base in BASES.values():
            assert any("dane" in c for c in base.columnas), base.nombre


@pytest.mark.unit
class TestExtraccionYTroceado:
    """La extracción a disco y la lista de años que se van a reescribir.

    El troceado importa porque de él sale la lista de años que el ETL borra
    antes de recargar: si no coincidiera con lo que descarga, una recarga
    parcial destruiría histórico en silencio.
    """

    def _cliente_falso(self, filas):
        from unittest.mock import MagicMock

        c = MagicMock()
        c.execute_mdx.return_value = iter(filas)
        return c

    def test_extraer_escribe_un_csv_y_cuenta_bien(self, tmp_path):
        from etl.etl_sicom_olap import extraer_trozo

        cliente = self._cliente_falso([
            {"AÑO CICLO": "2024", "MES CICLO": "1", "CODIGO SICOM AGENTE": "100",
             "NOMBRE COMERCIAL AGENTE": "EDS UNO", "TIPO AGENTE": "MINORISTA",
             "SUBTIPO AGENTE": "EDS", "DEPARTAMENTO INSTALACION": "ANTIOQUIA",
             "CODIGO DANE DEPARTAMENTO INSTALACION": "05",
             "MUNICIPIO INSTALACION": "MEDELLIN",
             "CODIGO DANE MUNICIPIO INSTALACION": "05001",
             "PRODUCTO": "ACPM", "DESCRIPCION PRODUCTO": "DIESEL",
             "CAPACIDAD OPERATIVA": "1500.75"},
        ])
        destino = tmp_path / "t.csv"

        filas, suma = extraer_trozo(cliente, CAPACIDAD, "SELECT ...", destino)

        assert filas == 1
        assert suma == pytest.approx(1500.75)
        contenido = destino.read_text(encoding="utf-8")
        assert "EDS UNO" in contenido
        # el decimal se conserva tal cual, sin pasar por float
        assert "1500.75" in contenido

    def test_si_falta_una_columna_del_cubo_falla(self, tmp_path):
        """Un atributo renombrado dejaría esa columna entera en NULL sin avisar."""
        from etl.etl_sicom_olap import extraer_trozo

        cliente = self._cliente_falso([{"AÑO CICLO": "2024"}])  # faltan casi todas
        with pytest.raises(RuntimeError, match="no devolvió"):
            extraer_trozo(cliente, CAPACIDAD, "SELECT ...", tmp_path / "t.csv")

    def test_un_valor_no_numerico_en_la_medida_falla(self, tmp_path):
        """Antes se ignoraba en silencio y la suma quedaba corta."""
        from etl.etl_sicom_olap import extraer_trozo

        fila = {a.alias: "x" for a in CAPACIDAD.atributos}
        fila["CAPACIDAD OPERATIVA"] = "mucha"
        cliente = self._cliente_falso([fila])
        with pytest.raises(RuntimeError, match="no numérico"):
            extraer_trozo(cliente, CAPACIDAD, "SELECT ...", tmp_path / "t.csv")

    def test_los_trozos_cubren_los_años_que_devuelve_el_cubo(self):
        from unittest.mock import MagicMock, patch

        with patch("etl.etl_sicom_olap._anios", return_value=["2023", "2024", "2025"]):
            from etl.etl_sicom_olap import _trozos

            trozos = _trozos(MagicMock(), COMPRAS, None)
        assert [e for e, _ in trozos] == ["2023", "2024", "2025"]

    def test_desde_filtra_los_años_anteriores(self):
        from unittest.mock import MagicMock, patch

        with patch("etl.etl_sicom_olap._anios", return_value=["2023", "2024", "2025"]):
            from etl.etl_sicom_olap import _trozos

            trozos = _trozos(MagicMock(), COMPRAS, 2024)
        assert [e for e, _ in trozos] == ["2024", "2025"]

    def test_sin_años_no_se_borra_nada(self):
        """Si el cubo no devuelve años, hay que abortar antes del DELETE."""
        from unittest.mock import MagicMock, patch

        with patch("etl.etl_sicom_olap._anios", return_value=[]):
            from etl.etl_sicom_olap import _trozos

            with pytest.raises(RuntimeError, match="ningún año"):
                _trozos(MagicMock(), COMPRAS, None)

    def test_una_base_sin_ciclo_produce_un_solo_trozo(self):
        from unittest.mock import MagicMock

        from etl.etl_sicom_olap import _trozos

        trozos = _trozos(MagicMock(), AGENTES, None)
        assert len(trozos) == 1 and trozos[0][0] is None


@pytest.mark.unit
class TestRunBaseNoPierdeDatos:
    """Las rutas de `_run_base` que podrían borrar datos sin reponerlos.

    Se simula la base: lo que se verifica es QUÉ SQL emite, no el resultado.
    """

    @staticmethod
    def _conexion_falsa(conteo=1, identidades=1, lock=True):
        from unittest.mock import MagicMock

        cur = MagicMock()
        cur.fetchone.side_effect = lambda: ([lock] if cur.fetchone.call_count == 1
                                            else [conteo] if cur.fetchone.call_count == 2
                                            else [identidades])
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn = MagicMock()
        conn.cursor.return_value = cur
        return conn, cur

    def _parchear(self, monkeypatch, conn, filas, suma, trozos, total_cubo):
        from unittest.mock import MagicMock

        import etl.etl_sicom_olap as mod

        monkeypatch.setattr(mod, "SicomOlapClient", MagicMock())
        monkeypatch.setattr(mod, "get_connection", lambda: conn)
        monkeypatch.setattr(mod, "ensure_schema", lambda c: None)
        monkeypatch.setattr(mod, "_total_cubo", lambda c, b: total_cubo)
        monkeypatch.setattr(mod, "_trozos", lambda c, b, d: trozos)
        monkeypatch.setattr(mod, "extraer_trozo", lambda c, b, m, r: (filas, suma))
        monkeypatch.setattr(mod, "copiar", lambda c, b, r: None)
        monkeypatch.setattr(mod, "registrar", lambda *a, **k: None)
        monkeypatch.setattr(mod, "_registrar_fallo", lambda *a, **k: None)
        return mod

    def test_cero_filas_no_borra_la_tabla(self, monkeypatch):
        """Un cubo vacío llegó a borrar la tabla y registrar éxito."""
        conn, cur = self._conexion_falsa(conteo=0)
        mod = self._parchear(monkeypatch, conn, filas=0, suma=0.0,
                             trozos=[("2024", "SELECT ...")], total_cubo=100)

        with pytest.raises(RuntimeError, match="0 filas"):
            mod._run_base(COMPRAS)

        sql = " ".join(str(c) for c in cur.execute.call_args_list)
        assert "DELETE FROM" not in sql

    def test_una_recarga_parcial_borra_solo_los_años_que_reescribe(self, monkeypatch):
        # dos trozos de 10 filas cada uno → la tabla debe quedar con 20
        conn, cur = self._conexion_falsa(conteo=20, identidades=20)
        mod = self._parchear(monkeypatch, conn, filas=10, suma=5.0,
                             trozos=[("2025", "A"), ("2026", "B")], total_cubo=None)

        mod._run_base(COMPRAS, desde=2025)

        borrados = [c for c in cur.execute.call_args_list if "DELETE FROM" in str(c[0][0])]
        assert len(borrados) == 1
        sentencia, parametros = borrados[0][0][0], borrados[0][0][1]
        # por lista exacta, no por rango: un >= podría borrar años que no se recargan
        assert "= ANY(%s)" in sentencia
        assert parametros[0] == [2025, 2026]

    def test_una_carga_completa_borra_todo(self, monkeypatch):
        conn, cur = self._conexion_falsa(conteo=10, identidades=10)
        mod = self._parchear(monkeypatch, conn, filas=10, suma=100.0,
                             trozos=[(None, "A")], total_cubo=100)

        mod._run_base(COMPRAS)

        borrados = [str(c) for c in cur.execute.call_args_list if "DELETE FROM" in str(c)]
        assert len(borrados) == 1 and "WHERE" not in borrados[0]

    def test_si_el_conteo_no_cuadra_se_deshace(self, monkeypatch):
        """El COPY cargó otra cosa de lo que se descargó."""
        conn, cur = self._conexion_falsa(conteo=7)
        mod = self._parchear(monkeypatch, conn, filas=10, suma=100.0,
                             trozos=[(None, "A")], total_cubo=100)

        with pytest.raises(RuntimeError, match="se esperaban"):
            mod._run_base(COMPRAS)
        conn.rollback.assert_called()

    def test_si_otra_corrida_tiene_el_candado_no_se_toca_la_tabla(self, monkeypatch):
        conn, cur = self._conexion_falsa(lock=False)
        mod = self._parchear(monkeypatch, conn, filas=10, suma=100.0,
                             trozos=[(None, "A")], total_cubo=100)

        with pytest.raises(RuntimeError, match="otra carga en curso"):
            mod._run_base(COMPRAS)
        assert not any("DELETE" in str(c) for c in cur.execute.call_args_list)

    def test_desde_sobre_una_base_sin_ciclo_se_rechaza_antes_de_conectar(self, monkeypatch):
        from unittest.mock import MagicMock

        import etl.etl_sicom_olap as mod

        conexion = MagicMock()
        monkeypatch.setattr(mod, "get_connection", conexion)
        with pytest.raises(RuntimeError, match="no se trocea por año"):
            mod._run_base(AGENTES, desde=2025)
        conexion.assert_not_called()

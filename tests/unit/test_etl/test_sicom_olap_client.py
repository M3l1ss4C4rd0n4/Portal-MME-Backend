"""
Tests del cliente XMLA de los cubos SICOM (etl/sicom_olap_client.py).

El foco está en `_iter_mddataset`, que es donde han aparecido los fallos reales:
SSAS devuelve las celdas separadas de los ejes y de forma dispersa, y un error de
mapeo no produce ninguna excepción — produce datos silenciosamente mal. Los dos
defectos que se escaparon a la primera versión (una fila por celda en vez de por
fila lógica, y el texto técnico de los miembros nulos colándose como dato) están
cubiertos aquí para que no vuelvan.

No hay red en ninguna prueba: se alimenta el parser con XML construido a mano.
"""

import io

import pytest

from etl.sicom_olap_client import (
    SicomOlapError,
    _caption,
    _iter_mddataset,
    _nombre_corto,
)

MDD = "urn:schemas-microsoft-com:xml-analysis:mddataset"


def _miembro(jerarquia: str, caption: str | None, uname: str | None = None) -> str:
    partes = [f'<Member Hierarchy="{jerarquia}">']
    if uname is not None:
        partes.append(f"<UName>{uname}</UName>")
    if caption is not None:
        partes.append(f"<Caption>{caption}</Caption>")
    partes.append("</Member>")
    return "".join(partes)


def _dataset(medidas: list[str], filas: list[list[tuple[str, str]]], celdas: dict[int, str]) -> io.BytesIO:
    """Arma un MDDataSet como el que devuelve SSAS.

    `medidas`  → captions del eje 0
    `filas`    → por fila, lista de (jerarquía, caption) del eje 1
    `celdas`   → {CellOrdinal: valor}; las que falten simplemente no se emiten,
                 que es como SSAS representa una celda vacía.
    """
    ejes = []
    tuplas_m = "".join(
        f"<Tuple>{_miembro('[Measures]', m, f'[Measures].[{m}]')}</Tuple>" for m in medidas
    )
    ejes.append(f'<Axis name="Axis0"><Tuples>{tuplas_m}</Tuples></Axis>')

    if filas:
        tuplas_f = "".join(
            "<Tuple>" + "".join(_miembro(h, c) for h, c in fila) + "</Tuple>"
            for fila in filas
        )
        ejes.append(f'<Axis name="Axis1"><Tuples>{tuplas_f}</Tuples></Axis>')

    cuerpo_celdas = "".join(
        f'<Cell CellOrdinal="{o}"><Value>{v}</Value></Cell>' for o, v in sorted(celdas.items())
    )
    xml = (
        f'<root xmlns="{MDD}">'
        f"<Axes>{''.join(ejes)}</Axes>"
        f"<CellData>{cuerpo_celdas}</CellData>"
        f"</root>"
    )
    return io.BytesIO(xml.encode("utf-8"))


@pytest.mark.unit
class TestAplanadoDeMedidas:
    """Una consulta con varias medidas debe dar UNA fila por fila lógica."""

    def test_dos_medidas_producen_una_sola_fila_con_ambas(self):
        # Arrange — 2 filas lógicas × 2 medidas = 4 celdas
        origen = _dataset(
            medidas=["VOLUMEN COMPRADO", "VOLUMEN TRANSITO"],
            filas=[
                [("[CICLO].[AÑO CICLO]", "2024"), ("[PRODUCTO].[PRODUCTO]", "ACPM")],
                [("[CICLO].[AÑO CICLO]", "2025"), ("[PRODUCTO].[PRODUCTO]", "GASOLINA")],
            ],
            celdas={0: "100", 1: "5", 2: "200", 3: "7"},
        )

        # Act
        filas = list(_iter_mddataset(origen))

        # Assert — dos filas, no cuatro: emitir una por celda duplicaría todo
        assert len(filas) == 2
        assert filas[0] == {
            "AÑO CICLO": "2024", "PRODUCTO": "ACPM",
            "VOLUMEN COMPRADO": "100", "VOLUMEN TRANSITO": "5",
        }
        assert filas[1]["VOLUMEN COMPRADO"] == "200"
        assert filas[1]["VOLUMEN TRANSITO"] == "7"

    def test_una_medida_sin_duplicar(self):
        origen = _dataset(
            medidas=["AGENTE CANTIDAD"],
            filas=[[("[TIPO AGENTE].[TIPO AGENTE]", "MINORISTA")]],
            celdas={0: "7906"},
        )
        filas = list(_iter_mddataset(origen))
        assert filas == [{"TIPO AGENTE": "MINORISTA", "AGENTE CANTIDAD": "7906"}]

    def test_celda_ausente_queda_en_none_y_no_corre_las_demas(self):
        """Las celdas vacías no se emiten; eso no debe desalinear las filas."""
        origen = _dataset(
            medidas=["VOLUMEN COMPRADO", "VOLUMEN TRANSITO"],
            filas=[
                [("[CICLO].[AÑO CICLO]", "2024")],
                [("[CICLO].[AÑO CICLO]", "2025")],
            ],
            celdas={0: "100", 3: "7"},  # faltan la 1 y la 2
        )
        filas = list(_iter_mddataset(origen))
        assert len(filas) == 2
        assert filas[0] == {"AÑO CICLO": "2024", "VOLUMEN COMPRADO": "100"}
        assert filas[1] == {"AÑO CICLO": "2025", "VOLUMEN TRANSITO": "7"}


@pytest.mark.unit
class TestConsultaSinEjeDeFilas:
    """La consulta de conciliación pide la medida sin dimensiones."""

    def test_total_general_devuelve_una_fila(self):
        origen = _dataset(medidas=["AGENTE CANTIDAD"], filas=[], celdas={0: "8907"})
        filas = list(_iter_mddataset(origen))
        assert filas == [{"AGENTE CANTIDAD": "8907"}]


@pytest.mark.unit
class TestMiembrosVacios:
    """SSAS devuelve Caption vacío y un UName técnico para los atributos nulos."""

    def test_caption_vacio_no_cae_al_uname_tecnico(self):
        origen = _dataset(
            medidas=["AGENTE CANTIDAD"],
            filas=[[("[AGENTE].[OPERADA POR]", "")]],
            celdas={0: "1"},
        )
        filas = list(_iter_mddataset(origen))
        # Sin esta protección entraría "[AGENTE].[OPERADA POR].&[]" como si fuera un dato
        assert filas[0]["OPERADA POR"] == ""

    def test_caption_ausente_con_uname_nulo_se_descarta(self):
        from lxml import etree

        miembro = etree.fromstring(
            f'<Member xmlns="{MDD}"><UName>[AGENTE].[OPERADA POR].&amp;[]</UName></Member>'
        )
        assert _caption(miembro) == ""

    def test_caption_ausente_con_uname_real_se_conserva(self):
        from lxml import etree

        miembro = etree.fromstring(
            f'<Member xmlns="{MDD}"><UName>[TIPO AGENTE].[TIPO AGENTE].&amp;[REFINADOR]</UName></Member>'
        )
        assert _caption(miembro) == "[TIPO AGENTE].[TIPO AGENTE].&[REFINADOR]"


@pytest.mark.unit
class TestRespuestasInconsistentes:
    """Ante una respuesta rara hay que fallar, no cargar datos a medias."""

    def test_celda_fuera_del_eje_de_filas_falla(self):
        origen = _dataset(
            medidas=["X"],
            filas=[[("[D].[A]", "uno")]],
            celdas={0: "1", 99: "2"},  # la 99 no corresponde a ninguna fila
        )
        with pytest.raises(SicomOlapError, match="fuera del eje"):
            list(_iter_mddataset(origen))

    def test_celda_sin_ordinal_falla(self):
        xml = (
            f'<root xmlns="{MDD}"><Axes>'
            f'<Axis name="Axis0"><Tuples><Tuple>{_miembro("[Measures]", "X", "[Measures].[X]")}</Tuple></Tuples></Axis>'
            f'<Axis name="Axis1"><Tuples><Tuple>{_miembro("[D].[A]", "uno")}</Tuple></Tuples></Axis>'
            f"</Axes><CellData><Cell><Value>1</Value></Cell></CellData></root>"
        )
        with pytest.raises(SicomOlapError, match="CellOrdinal"):
            list(_iter_mddataset(io.BytesIO(xml.encode())))

    def test_error_incrustado_en_la_respuesta_falla(self):
        """SSAS puede devolver un error dentro de un documento bien formado."""
        xml = (
            f'<root xmlns="{MDD}"><Axes></Axes>'
            f'<Messages><Error ErrorCode="1234" Description="consulta invalida"/></Messages>'
            f"</root>"
        )
        with pytest.raises(SicomOlapError, match="error"):
            list(_iter_mddataset(io.BytesIO(xml.encode())))


@pytest.mark.unit
class TestNombres:
    def test_nombre_corto_de_una_jerarquia(self):
        assert _nombre_corto("[AGENTE].[TIPO ESTACION]") == "TIPO ESTACION"
        assert _nombre_corto("[CICLO].[AÑO CICLO]") == "AÑO CICLO"

    def test_la_medida_se_toma_del_uname_no_del_caption(self):
        """Si el servidor tradujera el caption, el ETL no encontraría la medida."""
        origen = _dataset(
            medidas=["Purchased volume"],  # caption traducido
            filas=[[("[D].[A]", "uno")]],
            celdas={0: "42"},
        )
        filas = list(_iter_mddataset(origen))
        # el UName que arma el fixture es [Measures].[Purchased volume]
        assert "Purchased volume" in filas[0]

    def test_columnas_explicitas_renombran_el_eje(self):
        origen = _dataset(
            medidas=["X"],
            filas=[[("[D].[A]", "uno"), ("[D].[B]", "dos")]],
            celdas={0: "1"},
        )
        filas = list(_iter_mddataset(origen, columnas=["col_a", "col_b"]))
        assert filas[0]["col_a"] == "uno"
        assert filas[0]["col_b"] == "dos"

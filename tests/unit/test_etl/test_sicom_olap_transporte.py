"""
Tests de la capa de transporte del cliente XMLA: autenticación, manejo de
errores HTTP y parseo de Discover.

Importan porque `msmdpump` devuelve los errores de MDX como **HTTP 500 con un
SOAP Fault dentro**: sin leer ese cuerpo, un error de consulta se pierde tras un
500 opaco. Y porque reintentar un POST que ya llegó al servidor cuadruplica el
tiempo de una consulta lenta.

Todo con HTTP simulado; no se abre ninguna conexión real.
"""

from unittest.mock import MagicMock, patch

import pytest

from etl.sicom_olap_client import NS, SicomOlapClient, SicomOlapError

ROWSET = NS["rowset"]


def _respuesta(status: int, contenido: bytes) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.content = contenido
    r.close = MagicMock()
    return r


@pytest.fixture
def cliente(tmp_path):
    """Cliente con credenciales simuladas y una cadena de CA cualquiera."""
    ca = tmp_path / "ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n")
    with patch("etl.sicom_olap_client._credenciales", return_value=("u", "p")):
        return SicomOlapClient(ca_bundle=ca)


@pytest.mark.unit
class TestCadenaDeCA:
    def test_sin_cadena_de_ca_no_arranca(self, tmp_path):
        """El servidor de SICOM no envía su intermedio: sin la cadena no hay TLS verificable."""
        with patch("etl.sicom_olap_client._credenciales", return_value=("u", "p")):
            with pytest.raises(SicomOlapError, match="certificado intermedio"):
                SicomOlapClient(ca_bundle=tmp_path / "no-existe.pem")

    def test_nunca_se_desactiva_la_verificacion(self, cliente):
        """`verify` debe apuntar al bundle, jamás a False."""
        with patch.object(cliente._sesion, "post", return_value=_respuesta(200, b"<a/>")) as post:
            cliente._post("<X/>", "Discover")
        assert post.call_args.kwargs["verify"] == cliente.ca_bundle
        assert post.call_args.kwargs["verify"] is not False


@pytest.mark.unit
class TestErroresHTTP:
    def test_401_se_traduce_a_credenciales_rechazadas(self, cliente):
        with patch.object(cliente._sesion, "post", return_value=_respuesta(401, b"")):
            with pytest.raises(SicomOlapError, match="Credenciales"):
                cliente._post("<X/>", "Discover")

    def test_el_soap_fault_de_un_500_llega_al_mensaje(self, cliente):
        """Sin esto, un MDX inválido solo se vería como un 500 sin explicación."""
        fault = (
            b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            b"<soap:Body><soap:Fault><faultstring>"
            b"La funcion CURRENTMEMBER espera una expresion de jerarquia"
            b"</faultstring></soap:Fault></soap:Body></soap:Envelope>"
        )
        with patch.object(cliente._sesion, "post", return_value=_respuesta(500, fault)):
            with pytest.raises(SicomOlapError, match="CURRENTMEMBER"):
                cliente._post("<X/>", "Execute")

    def test_un_500_sin_xml_tambien_informa(self, cliente):
        with patch.object(cliente._sesion, "post", return_value=_respuesta(500, b"fallo interno")):
            with pytest.raises(SicomOlapError, match="500"):
                cliente._post("<X/>", "Execute")

    def test_los_500_no_se_reintentan(self, cliente):
        """msmdpump usa 500 para los Fault: reintentarlos esconde el mensaje."""
        reintentos = cliente._sesion.get_adapter("https://").max_retries
        assert 500 not in reintentos.status_forcelist

    def test_las_lecturas_no_se_reintentan(self, cliente):
        """Una consulta de un año tarda ~1 min; repetirla 4 veces son 4 minutos perdidos."""
        reintentos = cliente._sesion.get_adapter("https://").max_retries
        assert reintentos.read == 0


@pytest.mark.unit
class TestDiscover:
    def test_parsea_las_filas_de_un_rowset(self, cliente):
        xml = (
            f'<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>'
            f'<root xmlns="{ROWSET}">'
            f"<row><CATALOG_NAME>SBI-Agentes</CATALOG_NAME></row>"
            f"<row><CATALOG_NAME>SBI-Compras</CATALOG_NAME></row>"
            f"</root></Body></Envelope>"
        ).encode()
        with patch.object(cliente._sesion, "post", return_value=_respuesta(200, xml)):
            filas = cliente.discover("DBSCHEMA_CATALOGS")
        assert [f["CATALOG_NAME"] for f in filas] == ["SBI-Agentes", "SBI-Compras"]

    def test_catalogos_devuelve_solo_los_nombres(self, cliente):
        xml = (
            f'<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>'
            f'<root xmlns="{ROWSET}"><row><CATALOG_NAME>SBI-Uso</CATALOG_NAME></row></root>'
            f"</Body></Envelope>"
        ).encode()
        with patch.object(cliente._sesion, "post", return_value=_respuesta(200, xml)):
            assert cliente.catalogos() == ["SBI-Uso"]

    def test_un_fault_en_un_200_tambien_falla(self, cliente):
        xml = (
            b'<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>'
            b'<Fault xmlns="http://schemas.xmlsoap.org/soap/envelope/">'
            b"<faultstring>catalogo inexistente</faultstring></Fault></Body></Envelope>"
        )
        with patch.object(cliente._sesion, "post", return_value=_respuesta(200, xml)):
            with pytest.raises(SicomOlapError, match="catalogo inexistente"):
                cliente.discover("MDSCHEMA_CUBES")

    def test_las_restricciones_se_escapan(self, cliente):
        """Un valor con & rompería el XML del sobre."""
        with patch.object(cliente._sesion, "post", return_value=_respuesta(200, b"<a/>")) as post:
            cliente.discover("X", {"CATALOG_NAME": "A & B"})
        enviado = post.call_args.kwargs["data"].decode()
        assert "A &amp; B" in enviado


@pytest.mark.unit
class TestCredenciales:
    def test_sin_credenciales_falla_con_instrucciones(self, monkeypatch):
        from etl import sicom_olap_client as mod

        monkeypatch.delenv("SICOM_XMLA_USER", raising=False)
        monkeypatch.delenv("SICOM_XMLA_PASSWORD", raising=False)
        with patch("core.secrets.get_secret", return_value=None):
            with pytest.raises(SicomOlapError, match="set_secret"):
                mod._credenciales()

    def test_se_replica_al_entorno_si_no_hay_vault(self, monkeypatch):
        from etl import sicom_olap_client as mod

        monkeypatch.setenv("SICOM_XMLA_USER", "usuario")
        monkeypatch.setenv("SICOM_XMLA_PASSWORD", "clave")
        with patch("core.secrets.get_secret", return_value=None):
            assert mod._credenciales() == ("usuario", "clave")

"""Pruebas del archivado con fecha de las fuentes de SharePoint.

Cubren `_archivar_version` y `_podar_versiones` de etl/etl_sharepoint_sync.py:
el historial que evita depender de una sola copia o de que la fuente siga
existiendo en SharePoint.
"""

import pytest

from etl import etl_sharepoint_sync as sync


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Aísla HISTORICO_DIR en un directorio temporal y devuelve un archivo fuente."""
    historico = tmp_path / "historico_fuentes"
    monkeypatch.setattr(sync, "HISTORICO_DIR", historico)
    monkeypatch.setattr(sync, "BASE_DIR", tmp_path)
    destino = tmp_path / "Fuente.xlsx"
    destino.write_bytes(b"version-1")
    return destino, historico


def test_archiva_una_copia_fechada_con_el_mismo_contenido(entorno):
    # Arrange
    destino, historico = entorno

    # Act
    copia = sync._archivar_version(destino, "Fuente")

    # Assert
    assert copia is not None
    assert copia.parent == historico / "Fuente"
    assert copia.read_bytes() == b"version-1"
    assert copia.name.startswith("Fuente_") and copia.suffix == ".xlsx"


def test_conserva_solo_las_ultimas_n_versiones(entorno):
    # Arrange
    destino, historico = entorno
    carpeta = historico / "Fuente"
    carpeta.mkdir(parents=True)
    for i in range(6):
        (carpeta / f"Fuente_2026010{i}_120000.xlsx").write_bytes(f"v{i}".encode())

    # Act
    sync._archivar_version(destino, "Fuente", conservar=3)

    # Assert
    quedan = sorted(p.name for p in carpeta.glob("Fuente_*.xlsx"))
    assert len(quedan) == 3
    assert quedan[0] == "Fuente_20260104_120000.xlsx"  # se borraron las más viejas


def test_conservar_cero_mantiene_todas_las_versiones(entorno):
    # Arrange
    destino, historico = entorno
    carpeta = historico / "Fuente"
    carpeta.mkdir(parents=True)
    for i in range(4):
        (carpeta / f"Fuente_2026010{i}_120000.xlsx").write_bytes(b"x")

    # Act
    sync._archivar_version(destino, "Fuente", conservar=0)

    # Assert
    assert len(list(carpeta.glob("Fuente_*.xlsx"))) == 5  # las 4 previas + la nueva


def test_no_toca_archivos_ajenos_al_patron(entorno):
    # Arrange
    destino, historico = entorno
    carpeta = historico / "Fuente"
    carpeta.mkdir(parents=True)
    ajeno = carpeta / "NOTAS.txt"
    ajeno.write_text("no borrar")
    for i in range(5):
        (carpeta / f"Fuente_2026010{i}_120000.xlsx").write_bytes(b"x")

    # Act
    sync._archivar_version(destino, "Fuente", conservar=2)

    # Assert
    assert ajeno.exists()
    assert len(list(carpeta.glob("Fuente_*.xlsx"))) == 2


def test_un_fallo_al_archivar_no_propaga_excepcion(entorno, monkeypatch):
    # Arrange — simula disco lleno / permisos al copiar
    destino, _ = entorno

    def _explota(*_args, **_kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(sync.shutil, "copy2", _explota)

    # Act
    copia = sync._archivar_version(destino, "Fuente")

    # Assert — devuelve None en vez de tumbar la sincronización
    assert copia is None


def test_podar_devuelve_cuantas_borro(entorno):
    # Arrange
    destino, historico = entorno
    carpeta = historico / "Fuente"
    carpeta.mkdir(parents=True)
    for i in range(5):
        (carpeta / f"Fuente_2026010{i}_120000.xlsx").write_bytes(b"x")

    # Act
    borradas = sync._podar_versiones(carpeta, destino, conservar=2)

    # Assert
    assert borradas == 3

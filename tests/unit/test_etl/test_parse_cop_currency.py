"""Pruebas de `_parse_cop_currency`: el parseo de montos en pesos del ETL.

El Excel de Supervisión trae la misma columna con texto en formato colombiano
y con números que pandas ya leyó como tales. Hasta el 2026-10-21 la función
convertía todo a texto y le quitaba el punto, con lo que un float legítimo
quedaba multiplicado por 10^(nº de decimales).
"""

import numpy as np
import pandas as pd
import pytest

from etl.etl_sharepoint_sync import _parse_cop_currency


def test_texto_en_formato_colombiano():
    # Arrange
    serie = pd.Series([" $ 6.800.000,00", "$1.234.567,89", "297.983.971,00"])

    # Act
    resultado = _parse_cop_currency(serie)

    # Assert
    assert list(resultado) == [6800000.0, 1234567.89, 297983971.00]


def test_un_float_conserva_sus_decimales():
    """La regresión concreta: 9412430990.09 se convertía en 941243099009."""
    # Arrange
    serie = pd.Series([9412430990.09, 2415451980.76, 6996979009.33])

    # Act
    resultado = _parse_cop_currency(serie)

    # Assert
    assert list(resultado) == [9412430990.09, 2415451980.76, 6996979009.33]


def test_el_factor_dependia_del_numero_de_decimales():
    # Arrange — 1, 2 y 6 decimales: antes daban ×10, ×100 y ×1.000.000
    serie = pd.Series([173924420.3, 9412430990.09, 5421313298.999996])

    # Act
    resultado = _parse_cop_currency(serie)

    # Assert
    assert resultado.iloc[0] == pytest.approx(173924420.3)
    assert resultado.iloc[1] == pytest.approx(9412430990.09)
    assert resultado.iloc[2] == pytest.approx(5421313298.999996)


def test_columna_mixta_texto_y_numeros():
    # Arrange — así llegan de verdad las columnas del Excel
    serie = pd.Series([" $ 6.800.000,00", 9412430990.09, "NO APLICA", None])

    # Act
    resultado = _parse_cop_currency(serie)

    # Assert
    assert resultado.iloc[0] == 6800000.0
    assert resultado.iloc[1] == pytest.approx(9412430990.09)
    assert pd.isna(resultado.iloc[2])
    assert pd.isna(resultado.iloc[3])


def test_enteros_de_numpy_se_respetan():
    # Arrange
    serie = pd.Series([np.int64(6800000), np.float64(1234.5)])

    # Act
    resultado = _parse_cop_currency(serie)

    # Assert
    assert list(resultado) == [6800000.0, 1234.5]


def test_los_booleanos_no_se_toman_como_monto():
    # Arrange
    serie = pd.Series([True, False], dtype=object)

    # Act
    resultado = _parse_cop_currency(serie)

    # Assert
    assert resultado.isna().all()

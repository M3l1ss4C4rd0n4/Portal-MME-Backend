"""Tests básicos para shared.utils.data_utils"""

import pandas as pd
from shared.utils.data_utils import safe_float, safe_int, clean_column_name, clean_dataframe_columns


def test_safe_float_and_int():
    assert safe_float("123.45") == 123.45
    assert safe_float("invalid", 0.0) == 0.0
    assert safe_int("42") == 42


def test_clean_column_name():
    assert clean_column_name("Valor Total (COP)") == "valor_total_cop"


def test_clean_dataframe_columns():
    df = pd.DataFrame({"Valor Total (COP)": [1, 2]})
    cleaned = clean_dataframe_columns(df)
    assert "valor_total_cop" in cleaned.columns

"""Unit test untuk modul data_validator."""

import pandas as pd
import pytest

from src.data_validator import validate_dataset


def _make_valid_df() -> pd.DataFrame:
    return pd.DataFrame({
        "sample_id": ["S01", "S02"],
        "sample_name": ["Sampel A", "Sampel B"],
        "temperature": [90.0, 45.0],
        "ph": [7.0, 6.2],
        "tds": [3000.0, 1500.0],
        "cl": [500.0, 200.0],
        "so4": [100.0, 50.0],
        "hco3": [300.0, 400.0],
    })


def test_valid_dataframe_passes():
    result = validate_dataset(_make_valid_df())
    assert result["is_valid"] is True
    assert result["errors"] == []


def test_empty_dataframe_is_invalid():
    df = pd.DataFrame()
    result = validate_dataset(df)
    assert result["is_valid"] is False
    assert any("tidak memiliki baris" in e for e in result["errors"])


def test_missing_required_column_is_invalid():
    df = _make_valid_df().drop(columns=["cl", "so4"])
    result = validate_dataset(df)
    assert result["is_valid"] is False
    assert any("cl" in e for e in result["errors"])


def test_duplicate_sample_id_generates_warning():
    df = _make_valid_df()
    df.loc[1, "sample_id"] = "S01"  # buat duplikat
    result = validate_dataset(df)
    assert any("duplikat" in w for w in result["warnings"])


def test_negative_concentration_generates_warning():
    df = _make_valid_df()
    df.loc[0, "cl"] = -5.0
    result = validate_dataset(df)
    assert any("negatif" in w for w in result["warnings"])


def test_unknown_columns_generate_warning():
    df = _make_valid_df()
    df["kolom_aneh"] = 0
    result = validate_dataset(df)
    assert any("tidak dikenali" in w for w in result["warnings"])

"""Unit test untuk modul data_cleaner."""

import numpy as np
import pandas as pd
import pytest

from src.data_cleaner import clean_numeric_value, clean_dataset, normalize_column_names


# ─── clean_numeric_value ─────────────────────────────────────────────────────

def test_dash_becomes_nan():
    value, issue = clean_numeric_value("-")
    assert value is None
    assert issue == "missing_value"


def test_em_dash_becomes_nan():
    value, issue = clean_numeric_value("—")
    assert value is None
    assert issue == "missing_value"


def test_none_becomes_nan():
    value, issue = clean_numeric_value(None)
    assert value is None
    assert issue == "missing_value"


def test_less_than_one_becomes_half():
    value, issue = clean_numeric_value("<1")
    assert value == pytest.approx(0.5)
    assert issue == "below_detection_limit"


def test_less_than_five_becomes_half():
    value, issue = clean_numeric_value("<5")
    assert value == pytest.approx(2.5)
    assert issue == "below_detection_limit"


def test_less_than_decimal_becomes_half():
    value, issue = clean_numeric_value("<0.1")
    assert value == pytest.approx(0.05)
    assert issue == "below_detection_limit"


def test_detection_limit_strategy_zero():
    value, issue = clean_numeric_value("<5", detection_limit_strategy="zero")
    assert value == pytest.approx(0.0)


def test_detection_limit_strategy_limit():
    value, issue = clean_numeric_value("<5", detection_limit_strategy="limit")
    assert value == pytest.approx(5.0)


def test_detection_limit_strategy_nan():
    value, issue = clean_numeric_value("<5", detection_limit_strategy="nan")
    assert value is None


def test_numeric_string_becomes_float():
    value, issue = clean_numeric_value("3.14")
    assert value == pytest.approx(3.14)
    assert issue is None


def test_integer_string_becomes_float():
    value, issue = clean_numeric_value("100")
    assert value == pytest.approx(100.0)
    assert issue is None


def test_invalid_text_becomes_nan():
    value, issue = clean_numeric_value("tidak_valid")
    assert value is None
    assert issue == "numeric_conversion_failed"


# ─── normalize_column_names ───────────────────────────────────────────────────

def test_normalize_maps_nama_to_sample_name():
    df = pd.DataFrame({"Nama": ["A"], "ID": ["S01"]})
    df_norm, mapping = normalize_column_names(df)
    assert "sample_name" in df_norm.columns
    assert "sample_id" in df_norm.columns


def test_normalize_maps_t_celsius_to_temperature():
    df = pd.DataFrame({"T(°C)": [90.0]})
    df_norm, _ = normalize_column_names(df)
    assert "temperature" in df_norm.columns


# ─── clean_dataset ────────────────────────────────────────────────────────────

def _make_config(strategy: str = "half") -> dict:
    return {
        "cleaning": {
            "missing_markers": ["", "-", "—", "NA", "N/A", "null", "None"],
            "detection_limit_strategy": strategy,
            "remove_exact_duplicates": True,
            "convert_negative_concentration_to_nan": True,
        }
    }


def _make_df(**overrides) -> pd.DataFrame:
    base = {
        "sample_id": ["S01"],
        "sample_name": ["Sampel A"],
        "temperature": [90.0],
        "ph": [7.0],
        "tds": [3000.0],
        "cl": [500.0],
        "so4": [100.0],
        "hco3": [300.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_negative_concentration_becomes_nan():
    df = _make_df(cl=[-5.0])
    cleaned, report = clean_dataset(df, _make_config())
    assert np.isnan(cleaned.at[0, "cl"])
    assert "invalid_negative_value" in report["issue_type"].values


def test_dash_tds_becomes_nan_in_dataset():
    df = _make_df(tds=["-"])
    cleaned, report = clean_dataset(df, _make_config())
    assert np.isnan(cleaned.at[0, "tds"])
    assert "missing_value" in report["issue_type"].values


def test_below_detection_limit_in_dataset():
    df = _make_df(cl=["<1"])
    cleaned, report = clean_dataset(df, _make_config("half"))
    assert cleaned.at[0, "cl"] == pytest.approx(0.5)
    assert "below_detection_limit" in report["issue_type"].values


def test_below_detection_adds_flag_column():
    df = _make_df(cl=["<1"])
    cleaned, _ = clean_dataset(df, _make_config())
    assert "cl_below_detection" in cleaned.columns
    assert cleaned.at[0, "cl_below_detection"] == True


def test_clean_dataset_does_not_modify_original():
    df = _make_df(cl=["<1"])
    original_value = df.at[0, "cl"]
    clean_dataset(df, _make_config())
    assert df.at[0, "cl"] == original_value


def test_quality_report_has_required_columns():
    df = _make_df(cl=["-"])
    _, report = clean_dataset(df, _make_config())
    required = {"row_index", "sample_id", "column_name", "original_value",
                "cleaned_value", "issue_type", "action"}
    assert required.issubset(set(report.columns))


def test_valid_values_produce_empty_report():
    df = _make_df()
    _, report = clean_dataset(df, _make_config())
    assert len(report) == 0

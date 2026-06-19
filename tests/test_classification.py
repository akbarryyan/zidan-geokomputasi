"""Unit test untuk modul classification."""

import math
import numpy as np
import pytest

from src.classification import (
    classify_ph,
    calculate_major_ion_proportions,
    classify_fluid_tendency,
)


# ─── classify_ph ─────────────────────────────────────────────────────────────

def test_acidic_ph():
    assert classify_ph(4.2) == "Asam"


def test_boundary_acidic_just_below():
    assert classify_ph(6.49) == "Asam"


def test_neutral_ph_lower_bound():
    assert classify_ph(6.5) == "Netral"


def test_neutral_ph():
    assert classify_ph(7.0) == "Netral"


def test_neutral_ph_upper_bound():
    assert classify_ph(7.5) == "Netral"


def test_alkaline_ph():
    assert classify_ph(8.4) == "Alkali"


def test_missing_ph():
    assert classify_ph(float("nan")) == "Tidak diketahui"


def test_none_ph():
    assert classify_ph(None) == "Tidak diketahui"


def test_custom_boundaries():
    assert classify_ph(6.0, acidic_max=6.0, neutral_max=8.0) == "Netral"
    assert classify_ph(5.9, acidic_max=6.0, neutral_max=8.0) == "Asam"
    assert classify_ph(8.1, acidic_max=6.0, neutral_max=8.0) == "Alkali"


# ─── calculate_major_ion_proportions ─────────────────────────────────────────

def test_proportions_sum_to_100():
    result = calculate_major_ion_proportions(60, 30, 10)
    total_pct = result["cl_pct"] + result["so4_pct"] + result["hco3_pct"]
    assert total_pct == pytest.approx(100.0, abs=0.01)


def test_normalized_ions_sum_to_100():
    result = calculate_major_ion_proportions(500, 200, 300)
    assert result["cl_pct"] + result["so4_pct"] + result["hco3_pct"] == pytest.approx(100.0, abs=0.01)


def test_chloride_dominated_proportions():
    result = calculate_major_ion_proportions(80, 10, 10)
    assert result["cl_pct"] > result["so4_pct"]
    assert result["cl_pct"] > result["hco3_pct"]


def test_all_nan_returns_nan():
    result = calculate_major_ion_proportions(np.nan, np.nan, np.nan)
    assert math.isnan(result["cl_pct"])
    assert math.isnan(result["so4_pct"])
    assert math.isnan(result["hco3_pct"])


def test_zero_total_returns_nan_percentages():
    result = calculate_major_ion_proportions(0, 0, 0)
    assert math.isnan(result["cl_pct"])
    assert result["total"] == 0.0


# ─── classify_fluid_tendency ─────────────────────────────────────────────────

def test_chloride_dominant():
    _, tendency, _ = classify_fluid_tendency(80, 10, 10, ph=7.5)
    assert tendency == "Cenderung klorida"


def test_bicarbonate_dominant():
    _, tendency, _ = classify_fluid_tendency(10, 10, 80, ph=7.5)
    assert tendency == "Cenderung bikarbonat"


def test_sulfate_dominant_acidic():
    # SO4 dominan + pH asam → asam-sulfat
    _, tendency, _ = classify_fluid_tendency(10, 80, 10, ph=4.0)
    assert tendency == "Cenderung asam-sulfat"


def test_sulfate_dominant_non_acidic():
    # SO4 dominan + pH tidak asam → sulfat biasa
    _, tendency, _ = classify_fluid_tendency(10, 80, 10, ph=7.5)
    assert tendency == "Cenderung sulfat"


def test_mixed_fluid():
    # Selisih Cl dan SO4 hanya 4% → campuran
    _, tendency, _ = classify_fluid_tendency(42, 38, 20, ph=7.0)
    assert "Campuran" in tendency
    assert "klorida" in tendency
    assert "sulfat" in tendency


def test_mixed_fluid_bicarbonate_chloride():
    # Selisih HCO3 dan Cl < 10% → campuran
    _, tendency, _ = classify_fluid_tendency(45, 5, 50, ph=7.5)
    assert "Campuran" in tendency


def test_insufficient_ion_data():
    dominant, tendency, _ = classify_fluid_tendency(
        np.nan, np.nan, np.nan, ph=7.0
    )
    assert tendency == "Data tidak cukup"


def test_dominant_ion_label_returned():
    dominant, _, _ = classify_fluid_tendency(80, 10, 10, ph=7.0)
    assert dominant == "Cl"


def test_sulfate_dominant_missing_ph():
    # pH tidak tersedia → tidak bisa cek asam, jatuh ke "Cenderung sulfat"
    _, tendency, _ = classify_fluid_tendency(10, 80, 10, ph=float("nan"))
    assert tendency == "Cenderung sulfat"

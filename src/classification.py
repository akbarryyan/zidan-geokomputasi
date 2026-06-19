"""Klasifikasi pH dan kecenderungan tipe fluida berdasarkan Cl-SO4-HCO3."""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def classify_ph(
    ph: float,
    acidic_max: float = 6.5,
    neutral_max: float = 7.5,
) -> str:
    """
    Kembalikan kategori pH sampel.

    Kategori: 'Asam', 'Netral', 'Alkali', 'Tidak diketahui'.
    """
    if ph is None or (isinstance(ph, float) and np.isnan(ph)):
        return "Tidak diketahui"
    if ph < acidic_max:
        return "Asam"
    if ph <= neutral_max:
        return "Netral"
    return "Alkali"


def calculate_major_ion_proportions(
    chloride: float,
    sulfate: float,
    bicarbonate: float,
) -> dict:
    """
    Hitung persentase relatif Cl, SO4, dan HCO3 terhadap totalnya.

    Returns
    -------
    dict dengan keys: cl_pct, so4_pct, hco3_pct, total.
    Semua nilai NaN jika total nol atau semua ion tidak tersedia.
    """
    def _to_float(v) -> float | None:
        try:
            f = float(v)
            return f if not np.isnan(f) else None
        except (TypeError, ValueError):
            return None

    cl = _to_float(chloride)
    so4 = _to_float(sulfate)
    hco3 = _to_float(bicarbonate)

    valid_values = [v for v in (cl, so4, hco3) if v is not None]
    if len(valid_values) == 0:
        return {"cl_pct": np.nan, "so4_pct": np.nan, "hco3_pct": np.nan, "total": np.nan}

    # Nilai None dianggap 0 untuk perhitungan proporsi
    cl_val = cl if cl is not None else 0.0
    so4_val = so4 if so4 is not None else 0.0
    hco3_val = hco3 if hco3 is not None else 0.0

    total = cl_val + so4_val + hco3_val
    if total == 0:
        return {"cl_pct": np.nan, "so4_pct": np.nan, "hco3_pct": np.nan, "total": 0.0}

    return {
        "cl_pct": round(cl_val / total * 100, 2),
        "so4_pct": round(so4_val / total * 100, 2),
        "hco3_pct": round(hco3_val / total * 100, 2),
        "total": round(total, 4),
    }


def classify_fluid_tendency(
    chloride: float,
    sulfate: float,
    bicarbonate: float,
    ph: float,
    acidic_max: float = 6.5,
    mixed_threshold: float = 10.0,
) -> tuple[str, str, str]:
    """
    Tentukan kecenderungan tipe fluida berdasarkan proporsi ion dan pH.

    Returns
    -------
    (dominant_ion, fluid_tendency, classification_note)

    Contoh fluid_tendency:
        'Cenderung klorida'
        'Cenderung sulfat'
        'Cenderung asam-sulfat'
        'Cenderung bikarbonat'
        'Campuran klorida-sulfat'
        'Data tidak cukup'
    """
    proportions = calculate_major_ion_proportions(chloride, sulfate, bicarbonate)

    cl_pct = proportions["cl_pct"]
    so4_pct = proportions["so4_pct"]
    hco3_pct = proportions["hco3_pct"]

    if np.isnan(cl_pct) and np.isnan(so4_pct) and np.isnan(hco3_pct):
        return "Tidak ada data", "Data tidak cukup", "Semua nilai Cl, SO4, HCO3 tidak tersedia."

    if proportions["total"] == 0:
        return "Tidak ada data", "Data tidak cukup", "Total Cl + SO4 + HCO3 = 0."

    ions = {
        "Cl": cl_pct if not np.isnan(cl_pct) else 0.0,
        "SO4": so4_pct if not np.isnan(so4_pct) else 0.0,
        "HCO3": hco3_pct if not np.isnan(hco3_pct) else 0.0,
    }

    sorted_ions = sorted(ions.items(), key=lambda x: x[1], reverse=True)
    first_name, first_pct = sorted_ions[0]
    second_name, second_pct = sorted_ions[1]

    # Cek campuran: selisih ion pertama dan kedua < mixed_threshold
    if (first_pct - second_pct) < mixed_threshold:
        ion_labels = {"Cl": "klorida", "SO4": "sulfat", "HCO3": "bikarbonat"}
        label_a = ion_labels[first_name]
        label_b = ion_labels[second_name]
        tendency = f"Campuran {label_a}-{label_b}"
        note = (
            f"Selisih {first_name} ({first_pct:.1f}%) dan {second_name} ({second_pct:.1f}%) "
            f"kurang dari {mixed_threshold} persen. Klasifikasi ini merupakan indikasi awal."
        )
        return first_name, tendency, note

    # Ion dominan tunggal
    dominant = first_name

    if dominant == "Cl":
        tendency = "Cenderung klorida"
        note = f"Cl mendominasi dengan {first_pct:.1f}% dari total ion utama. Indikasi awal."

    elif dominant == "SO4":
        ph_val = ph if ph is not None and not (isinstance(ph, float) and np.isnan(ph)) else None
        if ph_val is not None and ph_val < acidic_max:
            tendency = "Cenderung asam-sulfat"
            note = (
                f"SO4 mendominasi ({first_pct:.1f}%) dan pH = {ph_val} (asam). "
                f"Indikasi awal fluida asam-sulfat."
            )
        else:
            tendency = "Cenderung sulfat"
            ph_str = f"{ph_val}" if ph_val is not None else "tidak tersedia"
            note = (
                f"SO4 mendominasi ({first_pct:.1f}%) dan pH = {ph_str} (tidak asam). "
                f"Indikasi awal."
            )

    else:  # HCO3
        tendency = "Cenderung bikarbonat"
        note = f"HCO3 mendominasi dengan {first_pct:.1f}% dari total ion utama. Indikasi awal."

    return dominant, tendency, note


def classify_dataset(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Terapkan klasifikasi pH dan kecenderungan fluida ke seluruh dataset.

    Returns DataFrame dengan kolom tambahan:
    ph_category, cl_percentage, so4_percentage, hco3_percentage,
    dominant_ion, fluid_tendency, classification_note.
    """
    ph_cfg = config.get("ph_classification", {})
    fluid_cfg = config.get("fluid_classification", {})

    acidic_max = ph_cfg.get("acidic_max", 6.5)
    neutral_max = ph_cfg.get("neutral_max", 7.5)
    mixed_threshold = fluid_cfg.get("mixed_threshold", 10.0)

    df_result = df.copy()

    ph_categories: list[str] = []
    cl_pcts: list[float] = []
    so4_pcts: list[float] = []
    hco3_pcts: list[float] = []
    dominant_ions: list[str] = []
    fluid_tendencies: list[str] = []
    classification_notes: list[str] = []

    for idx in df_result.index:
        ph = df_result.at[idx, "ph"] if "ph" in df_result.columns else np.nan
        cl = df_result.at[idx, "cl"] if "cl" in df_result.columns else np.nan
        so4 = df_result.at[idx, "so4"] if "so4" in df_result.columns else np.nan
        hco3 = df_result.at[idx, "hco3"] if "hco3" in df_result.columns else np.nan

        ph_categories.append(classify_ph(ph, acidic_max, neutral_max))

        proportions = calculate_major_ion_proportions(cl, so4, hco3)
        cl_pcts.append(proportions["cl_pct"])
        so4_pcts.append(proportions["so4_pct"])
        hco3_pcts.append(proportions["hco3_pct"])

        dominant, tendency, note = classify_fluid_tendency(
            cl, so4, hco3, ph, acidic_max, mixed_threshold
        )
        dominant_ions.append(dominant)
        fluid_tendencies.append(tendency)
        classification_notes.append(note)

    df_result["ph_category"] = ph_categories
    df_result["cl_percentage"] = cl_pcts
    df_result["so4_percentage"] = so4_pcts
    df_result["hco3_percentage"] = hco3_pcts
    df_result["dominant_ion"] = dominant_ions
    df_result["fluid_tendency"] = fluid_tendencies
    df_result["classification_note"] = classification_notes

    logger.info(f"Klasifikasi selesai untuk {len(df_result)} sampel.")
    return df_result

"""
Perhitungan ion balance dan mass balance untuk analisis kimia air panas bumi.

Konversi mg/kg → meq/L menggunakan berat ekivalen masing-masing ion.
Rumus: meq/L = konsentrasi (mg/kg) / berat_ekivalen (g/eq)
       berat_ekivalen = berat_molekul / valensi

Asumsi larutan encer: densitas ≈ 1 kg/L, sehingga mg/kg ≈ mg/L.
"""

import logging
import math

import numpy as np
import pandas as pd

from src.data_loader import load_dataset
from src.data_cleaner import normalize_column_names, clean_dataset

logger = logging.getLogger(__name__)

# Berat ekivalen (g/eq) = MW / valence
EQUIVALENT_WEIGHTS: dict[str, float] = {
    "na":   22.990,   # Na+  (MW=22.99,  val=1)
    "k":    39.100,   # K+   (MW=39.10,  val=1)
    "ca":   20.040,   # Ca2+ (MW=40.08,  val=2)
    "mg":   12.153,   # Mg2+ (MW=24.305, val=2)
    "li":    6.941,   # Li+  (MW=6.941,  val=1)
    "cl":   35.450,   # Cl-  (MW=35.45,  val=1)
    "so4":  48.030,   # SO42-(MW=96.06,  val=2)
    "hco3": 61.020,   # HCO3-(MW=61.02,  val=1)
}

# Kolom kation dan anion yang dilibatkan dalam charge balance
CATION_COLS = ("na", "k", "ca", "mg", "li")
ANION_COLS  = ("cl", "so4", "hco3")

# Semua ion yang dijumlahkan untuk mass balance (mg/kg)
MASS_BALANCE_COLS = ("na", "k", "ca", "mg", "li", "cl", "so4", "hco3", "sio2", "b")


def _safe_float(val) -> float | None:
    """Kembalikan float positif atau None untuk nilai tidak valid."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or f < 0:
            return None
        return f
    except (TypeError, ValueError):
        return None


def mg_to_meq(val_mg_per_kg: float | None, eq_weight: float) -> float | None:
    """
    Konversi mg/kg ke meq/L.

    Parameters
    ----------
    val_mg_per_kg : float | None
        Konsentrasi ion dalam mg/kg (atau mg/L untuk larutan encer).
    eq_weight : float
        Berat ekivalen ion dalam g/eq.
    """
    v = _safe_float(val_mg_per_kg)
    if v is None:
        return None
    return round(v / eq_weight, 4)


def calculate_ion_balance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hitung meq/L, sigma kation, sigma anion, ion balance (%), dan mass balance (%).

    Kolom input yang dibutuhkan (lowercase, hasil normalize_column_names):
        na, k, ca, mg — wajib untuk kation
        cl, so4, hco3 — wajib untuk anion
        li, sio2, b   — opsional
        tds           — opsional (untuk mass balance)

    Kolom output yang ditambahkan ke DataFrame:
        {ion}_meq      — konsentrasi dalam meq/L untuk setiap ion
        sum_cations_meq, sum_anions_meq
        ion_balance_pct  — CBE = (Σcat - Σani) / (Σcat + Σani) × 100
        mass_balance_pct — (Σ ion mg/kg - TDS) / TDS × 100

    Returns
    -------
    pd.DataFrame dengan kolom asli + kolom perhitungan baru.
    """
    df_out = df.copy()
    results: list[dict] = []

    for idx in df_out.index:
        def get(col: str) -> float | None:
            v = df_out.at[idx, col] if col in df_out.columns else None
            return _safe_float(v)

        # Konversi ke meq/L
        na_meq   = mg_to_meq(get("na"),   EQUIVALENT_WEIGHTS["na"])
        k_meq    = mg_to_meq(get("k"),    EQUIVALENT_WEIGHTS["k"])
        ca_meq   = mg_to_meq(get("ca"),   EQUIVALENT_WEIGHTS["ca"])
        mg_meq   = mg_to_meq(get("mg"),   EQUIVALENT_WEIGHTS["mg"])
        li_meq   = mg_to_meq(get("li"),   EQUIVALENT_WEIGHTS["li"])
        cl_meq   = mg_to_meq(get("cl"),   EQUIVALENT_WEIGHTS["cl"])
        so4_meq  = mg_to_meq(get("so4"),  EQUIVALENT_WEIGHTS["so4"])
        hco3_meq = mg_to_meq(get("hco3"), EQUIVALENT_WEIGHTS["hco3"])

        # Sigma kation (Li disertakan jika tersedia)
        cat_vals = [v for v in (na_meq, k_meq, ca_meq, mg_meq, li_meq) if v is not None]
        sum_cat = round(sum(cat_vals), 4) if cat_vals else None

        # Sigma anion
        ani_vals = [v for v in (cl_meq, so4_meq, hco3_meq) if v is not None]
        sum_ani = round(sum(ani_vals), 4) if ani_vals else None

        # Ion balance (Charge Balance Error, %)
        if sum_cat is not None and sum_ani is not None:
            denom = sum_cat + sum_ani
            ib = round((sum_cat - sum_ani) / denom * 100, 2) if denom > 0 else None
        else:
            ib = None

        # Mass balance: (Σ semua ion terukur - TDS) / TDS × 100
        mg_kg_vals = [
            v for col in MASS_BALANCE_COLS
            for v in [get(col)] if v is not None
        ]
        ion_sum = sum(mg_kg_vals)
        tds = get("tds")
        mb = round((ion_sum - tds) / tds * 100, 2) if tds is not None and tds > 0 else None

        results.append({
            "na_meq":   na_meq,
            "k_meq":    k_meq,
            "ca_meq":   ca_meq,
            "mg_meq":   mg_meq,
            "li_meq":   li_meq,
            "cl_meq":   cl_meq,
            "so4_meq":  so4_meq,
            "hco3_meq": hco3_meq,
            "sum_cations_meq": sum_cat,
            "sum_anions_meq":  sum_ani,
            "ion_balance_pct": ib,
            "mass_balance_pct": mb,
        })

    extra = pd.DataFrame(results, index=df_out.index)
    result = pd.concat([df_out, extra], axis=1)
    logger.info(f"Ion balance dihitung untuk {len(result)} sampel.")
    return result


def load_kimia_air_dataset(file_path: str, config: dict) -> pd.DataFrame:
    """
    Muat dan siapkan dataset Kimia Air_Tugas 1.xlsx.

    Wrapper ringkas yang menggunakan konfigurasi utama proyek.

    Returns
    -------
    pd.DataFrame bersih dengan kolom standar.
    """
    raw = load_dataset(file_path, sheet_name="Air", skip_rows=[0, 2])
    df, mapping = normalize_column_names(raw)
    logger.debug(f"Pemetaan kolom KA: {mapping}")

    # Kolom "id" → sample_id sudah ditangani oleh normalize_column_names
    # Pastikan sample_id ada
    if "sample_id" not in df.columns:
        if "id" in df.columns:
            df = df.rename(columns={"id": "sample_id"})
        else:
            df["sample_id"] = [f"KA_{i}" for i in range(len(df))]

    df_clean, _ = clean_dataset(df, config)
    logger.info(f"Dataset Kimia Air dimuat: {len(df_clean)} sampel.")
    return df_clean

"""Menghitung statistik deskriptif parameter kimia air."""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

STAT_COLUMNS: list[str] = [
    "temperature", "ph", "tds", "li", "na", "k",
    "ca", "mg", "sio2", "b", "cl", "so4", "hco3",
]


def calculate_summary_statistics(
    df: pd.DataFrame,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Hitung statistik deskriptif untuk kolom yang ditentukan.

    Statistik: count, missing, mean, median, std, min, q1, q3, max.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset yang sudah dibersihkan.
    columns : list[str] | None
        Kolom yang dihitung. Default: STAT_COLUMNS yang tersedia di df.

    Returns
    -------
    pd.DataFrame
        Tabel statistik dengan kolom sebagai baris dan metrik sebagai kolom.
    """
    if columns is None:
        columns = [c for c in STAT_COLUMNS if c in df.columns]

    rows: list[dict] = []

    for col in columns:
        if col not in df.columns:
            logger.warning(f"Kolom '{col}' tidak ditemukan, dilewati.")
            continue

        series = pd.to_numeric(df[col], errors="coerce")
        valid = series.dropna()
        n_total = len(series)
        n_valid = len(valid)

        if n_valid == 0:
            rows.append({
                "parameter": col,
                "count": 0,
                "missing": n_total,
                "mean": np.nan,
                "median": np.nan,
                "std": np.nan,
                "min": np.nan,
                "q1": np.nan,
                "q3": np.nan,
                "max": np.nan,
            })
            continue

        rows.append({
            "parameter": col,
            "count": n_valid,
            "missing": n_total - n_valid,
            "mean": round(valid.mean(), 4),
            "median": round(valid.median(), 4),
            "std": round(valid.std(), 4),
            "min": round(valid.min(), 4),
            "q1": round(valid.quantile(0.25), 4),
            "q3": round(valid.quantile(0.75), 4),
            "max": round(valid.max(), 4),
        })

    stats_df = pd.DataFrame(rows).set_index("parameter")
    logger.info(f"Statistik deskriptif dihitung untuk {len(stats_df)} parameter.")
    return stats_df

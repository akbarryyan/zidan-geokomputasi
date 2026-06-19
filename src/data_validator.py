"""Memvalidasi struktur dan kualitas DataFrame tanpa mengubah data."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS: list[str] = [
    "sample_id",
    "sample_name",
    "temperature",
    "ph",
    "tds",
    "cl",
    "so4",
    "hco3",
]

CONCENTRATION_COLUMNS: list[str] = [
    "tds", "li", "na", "k", "ca", "mg", "sio2", "b", "cl", "so4", "hco3",
]


def validate_dataset(
    df: pd.DataFrame,
    required_columns: list[str] | None = None,
) -> dict:
    """
    Periksa struktur dan kualitas data.

    Validasi tidak mengubah data — hanya menghasilkan laporan.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame yang sudah dinormalisasi nama kolomnya.
    required_columns : list[str] | None
        Kolom wajib yang harus ada. Default: REQUIRED_COLUMNS.

    Returns
    -------
    dict dengan keys:
        is_valid : bool
        errors   : list[str]  — masalah yang menghentikan pipeline
        warnings : list[str]  — masalah yang masih bisa diproses
    """
    if required_columns is None:
        required_columns = REQUIRED_COLUMNS

    errors: list[str] = []
    warnings: list[str] = []

    # 1. DataFrame kosong
    if df.empty:
        errors.append("Dataset tidak memiliki baris data yang dapat dianalisis.")
        return {"is_valid": False, "errors": errors, "warnings": warnings}

    # 2. Kolom wajib tidak tersedia
    missing_cols = [c for c in required_columns if c not in df.columns]
    if missing_cols:
        errors.append(
            f"Kolom wajib tidak ditemukan: {', '.join(missing_cols)}.\n"
            f"Periksa nama kolom atau tambahkan alias pada konfigurasi."
        )

    # 3. sample_id kosong
    if "sample_id" in df.columns:
        null_ids = df["sample_id"].isnull().sum()
        if null_ids > 0:
            warnings.append(f"Ditemukan {null_ids} baris dengan sample_id kosong.")

    # 4. sample_id duplikat
    if "sample_id" in df.columns:
        dupes = df["sample_id"].dropna()
        dupes = dupes[dupes.duplicated()]
        if not dupes.empty:
            warnings.append(
                f"Ditemukan sample_id duplikat: {', '.join(dupes.unique().astype(str))}."
            )

    # 5. Nilai negatif pada kolom konsentrasi
    for col in CONCENTRATION_COLUMNS:
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        neg_count = (numeric < 0).sum()
        if neg_count > 0:
            warnings.append(
                f"Ditemukan {neg_count} nilai negatif pada kolom '{col}'."
            )

    # 6. Kolom yang tidak dikenali (informasional)
    known_cols = set(
        ["sample_id", "sample_name", "temperature", "ph", "tds",
         "li", "na", "k", "ca", "mg", "sio2", "b", "cl", "so4", "hco3"]
    )
    unknown_cols = [c for c in df.columns if c not in known_cols]
    if unknown_cols:
        warnings.append(
            f"Kolom tidak dikenali (diabaikan): {', '.join(unknown_cols)}."
        )

    is_valid = len(errors) == 0

    if is_valid:
        logger.info("Validasi dataset berhasil.")
    else:
        for err in errors:
            logger.error(err)

    for warn in warnings:
        logger.warning(warn)

    return {"is_valid": is_valid, "errors": errors, "warnings": warnings}

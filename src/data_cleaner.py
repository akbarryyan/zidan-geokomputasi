"""Membersihkan data: normalisasi kolom, nilai kosong, batas deteksi, nilai negatif."""

import logging
import re

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

COLUMN_ALIASES: dict[str, str] = {
    "id": "sample_id",
    "sample id": "sample_id",
    "sample_id": "sample_id",
    "nama sampel": "sample_name",
    "sample name": "sample_name",
    "sample": "sample_name",
    "nama": "sample_name",
    # Ion Balance file: "Unnamed: 1" → sample_name
    "unnamed: 1": "sample_name",
    "unnamed:_1": "sample_name",
    "temp": "temperature",
    "temperature": "temperature",
    "temperatur": "temperature",
    "suhu": "temperature",
    "t(°c)": "temperature",
    "t(oc)": "temperature",
    "t": "temperature",
    # Ion Balance file: "toC" → temperature
    "toc": "temperature",
    "ph": "ph",
    "tds": "tds",
    "li": "li",
    "na": "na",
    "k": "k",
    "ca": "ca",
    "mg": "mg",
    "rb": "rb",
    "cs": "cs",
    "sio2": "sio2",
    "sio₂": "sio2",
    "silica": "sio2",
    "b": "b",
    "cl": "cl",
    "chloride": "cl",
    "klorida": "cl",
    "so4": "so4",
    "so₄": "so4",
    "sulfate": "so4",
    "sulfat": "so4",
    "hco3": "hco3",
    "hco₃": "hco3",
    "bicarbonate": "hco3",
    "bikarbonat": "hco3",
}

MISSING_MARKERS: list[str] = ["", "-", "—", "NA", "N/A", "null", "None"]

CONCENTRATION_COLUMNS: list[str] = [
    "tds", "li", "na", "k", "ca", "mg", "rb", "cs", "sio2", "b", "cl", "so4", "hco3",
]

NUMERIC_COLUMNS: list[str] = [
    "temperature", "ph", "tds", "li", "na", "k", "ca", "mg", "rb", "cs",
    "sio2", "b", "cl", "so4", "hco3",
]

_DETECTION_LIMIT_PATTERN = re.compile(r"^<\s*(\d+\.?\d*)$")


def normalize_column_names(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Normalisasi nama kolom menggunakan COLUMN_ALIASES.

    Returns
    -------
    df : pd.DataFrame
        DataFrame dengan nama kolom yang sudah dinormalisasi.
    mapping : dict[str, str]
        Pemetaan nama kolom asli → nama kolom standar.
    """
    mapping: dict[str, str] = {}
    new_columns: list[str] = []

    for col in df.columns:
        original = col
        normalized = str(col).strip().lower().replace(" ", "_")
        normalized_space = str(col).strip().lower()

        standard = COLUMN_ALIASES.get(normalized) or COLUMN_ALIASES.get(normalized_space)

        if standard:
            mapping[original] = standard
            new_columns.append(standard)
        else:
            mapping[original] = normalized
            new_columns.append(normalized)

    df = df.copy()
    df.columns = new_columns
    return df, mapping


def clean_numeric_value(
    value,
    detection_limit_strategy: str = "half",
) -> tuple[float | None, str | None]:
    """
    Bersihkan satu nilai numerik.

    Parameters
    ----------
    value : any
        Nilai mentah dari sel DataFrame.
    detection_limit_strategy : str
        'half'  → setengah batas deteksi (default)
        'zero'  → nol
        'limit' → nilai batas itu sendiri
        'nan'   → NaN

    Returns
    -------
    (cleaned_value, issue_type)
        issue_type adalah None jika nilai bersih, atau string deskripsi masalah.
    """
    # Sudah NaN
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None, "missing_value"

    str_value = str(value).strip()

    # Cek missing marker
    if str_value in MISSING_MARKERS:
        return None, "missing_value"

    # Cek batas deteksi: <1, <5, <0.1, dll.
    match = _DETECTION_LIMIT_PATTERN.match(str_value)
    if match:
        limit = float(match.group(1))
        if detection_limit_strategy == "half":
            cleaned = limit / 2
        elif detection_limit_strategy == "zero":
            cleaned = 0.0
        elif detection_limit_strategy == "limit":
            cleaned = limit
        else:  # "nan"
            cleaned = None
        return cleaned, "below_detection_limit"

    # Coba konversi numerik biasa
    try:
        return float(str_value), None
    except ValueError:
        return None, "numeric_conversion_failed"


def clean_dataset(
    df: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Bersihkan seluruh dataset sesuai aturan system-design.

    Langkah:
    1. Salin DataFrame (data asli tidak diubah).
    2. Bersihkan kolom numerik: missing marker, batas deteksi, konversi.
    3. Tandai nilai negatif pada kolom konsentrasi sebagai NaN.
    4. Buat laporan kualitas data setiap perubahan.

    Returns
    -------
    (cleaned_df, quality_report_df)
    """
    cleaning_cfg = config.get("cleaning", {})
    strategy = cleaning_cfg.get("detection_limit_strategy", "half")
    missing_markers = cleaning_cfg.get("missing_markers", MISSING_MARKERS)
    convert_negative = cleaning_cfg.get("convert_negative_concentration_to_nan", True)

    df_clean = df.copy()
    # Konversi semua kolom numerik ke object dtype dulu agar bisa menerima
    # campuran float dan NaN saat proses cell-by-cell
    for col in NUMERIC_COLUMNS:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].astype(object)

    report_rows: list[dict] = []

    for col in NUMERIC_COLUMNS:
        if col not in df_clean.columns:
            continue

        below_detection_flags: list[bool] = []

        for idx in df_clean.index:
            original_value = df_clean.at[idx, col]
            sample_id = df_clean.at[idx, "sample_id"] if "sample_id" in df_clean.columns else idx

            # Paksa missing marker tambahan dari config
            if str(original_value).strip() in missing_markers:
                df_clean.at[idx, col] = np.nan
                below_detection_flags.append(False)
                report_rows.append({
                    "row_index": idx,
                    "sample_id": sample_id,
                    "column_name": col,
                    "original_value": original_value,
                    "cleaned_value": np.nan,
                    "issue_type": "missing_value",
                    "action": "Diubah menjadi NaN",
                })
                continue

            cleaned, issue = clean_numeric_value(original_value, strategy)

            if issue == "missing_value":
                df_clean.at[idx, col] = np.nan
                below_detection_flags.append(False)
                if original_value is not None and not (isinstance(original_value, float) and np.isnan(original_value)):
                    report_rows.append({
                        "row_index": idx,
                        "sample_id": sample_id,
                        "column_name": col,
                        "original_value": original_value,
                        "cleaned_value": np.nan,
                        "issue_type": "missing_value",
                        "action": "Diubah menjadi NaN",
                    })
                below_detection_flags.append(False)

            elif issue == "below_detection_limit":
                df_clean.at[idx, col] = cleaned
                below_detection_flags.append(True)
                report_rows.append({
                    "row_index": idx,
                    "sample_id": sample_id,
                    "column_name": col,
                    "original_value": original_value,
                    "cleaned_value": cleaned,
                    "issue_type": "below_detection_limit",
                    "action": f"Strategi '{strategy}': diubah menjadi {cleaned}",
                })

            elif issue == "numeric_conversion_failed":
                df_clean.at[idx, col] = np.nan
                below_detection_flags.append(False)
                report_rows.append({
                    "row_index": idx,
                    "sample_id": sample_id,
                    "column_name": col,
                    "original_value": original_value,
                    "cleaned_value": np.nan,
                    "issue_type": "numeric_conversion_failed",
                    "action": "Tidak dapat dikonversi, diubah menjadi NaN",
                })

            else:
                # Nilai valid — konversi ke float
                df_clean.at[idx, col] = cleaned
                below_detection_flags.append(False)

        # Tambahkan kolom flag batas deteksi hanya untuk kolom ion utama
        if col in CONCENTRATION_COLUMNS:
            df_clean[f"{col}_below_detection"] = below_detection_flags

    # Tangani nilai negatif pada kolom konsentrasi
    if convert_negative:
        for col in CONCENTRATION_COLUMNS:
            if col not in df_clean.columns:
                continue
            numeric_col = pd.to_numeric(df_clean[col], errors="coerce")
            neg_mask = numeric_col < 0
            for idx in df_clean.index[neg_mask]:
                sample_id = df_clean.at[idx, "sample_id"] if "sample_id" in df_clean.columns else idx
                original_value = df_clean.at[idx, col]
                df_clean.at[idx, col] = np.nan
                report_rows.append({
                    "row_index": idx,
                    "sample_id": sample_id,
                    "column_name": col,
                    "original_value": original_value,
                    "cleaned_value": np.nan,
                    "issue_type": "invalid_negative_value",
                    "action": "Nilai negatif tidak valid untuk konsentrasi, diubah menjadi NaN",
                })

    # Konversi akhir semua kolom numerik ke float
    for col in NUMERIC_COLUMNS:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")

    quality_report = pd.DataFrame(report_rows, columns=[
        "row_index", "sample_id", "column_name",
        "original_value", "cleaned_value", "issue_type", "action",
    ])

    n_issues = len(quality_report)
    logger.info(
        f"Pembersihan selesai: {n_issues} perubahan dicatat "
        f"({len(df_clean)} baris diproses)."
    )
    if n_issues == 0:
        logger.info("Tidak ada masalah data yang ditemukan.")

    return df_clean, quality_report

"""Membaca file Excel atau CSV menjadi pandas DataFrame."""

import logging
import os

import pandas as pd

logger = logging.getLogger(__name__)


def list_sheets(file_path: str) -> list[str]:
    """Kembalikan daftar nama sheet dari file Excel."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"File input tidak ditemukan: {file_path}\n"
            f"Pastikan file telah ditempatkan di direktori data/raw."
        )
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    return xl.sheet_names


def load_dataset(
    file_path: str,
    sheet_name: str | int | None = None,
    skip_rows: list[int] | None = None,
) -> pd.DataFrame:
    """
    Baca file .xlsx atau .csv dan kembalikan sebagai DataFrame.

    Parameters
    ----------
    file_path : str
        Path ke file Excel atau CSV.
    sheet_name : str | int | None
        Nama atau indeks sheet Excel. Jika None, sheet pertama digunakan.
    skip_rows : list[int] | None
        Indeks baris (0-based) yang dilewati sebelum parsing header.

    Raises
    ------
    FileNotFoundError
        Jika file tidak ditemukan.
    ValueError
        Jika format file tidak didukung atau sheet tidak ditemukan.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"File input tidak ditemukan: {file_path}\n"
            f"Pastikan file telah ditempatkan di direktori data/raw."
        )

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        logger.info(f"Membaca file CSV: {file_path}")
        df = pd.read_csv(file_path, skiprows=skip_rows)

    elif ext in (".xlsx", ".xls"):
        available_sheets = list_sheets(file_path)

        if sheet_name is not None and sheet_name not in available_sheets:
            raise ValueError(
                f"Sheet yang diminta tidak ditemukan: '{sheet_name}'\n"
                f"Sheet yang tersedia: {', '.join(str(s) for s in available_sheets)}"
            )

        target_sheet = sheet_name if sheet_name is not None else available_sheets[0]
        logger.info(f"Membaca file Excel: {file_path} | Sheet: '{target_sheet}'")

        df = pd.read_excel(
            file_path,
            sheet_name=target_sheet,
            skiprows=skip_rows,
            header=0,
            engine="openpyxl",
        )

    else:
        raise ValueError(
            f"Format file tidak didukung: '{ext}'\n"
            f"Format yang didukung: .xlsx, .xls, .csv"
        )

    logger.info(f"Dataset berhasil dibaca: {len(df)} baris, {len(df.columns)} kolom")
    return df

"""Entry point utama untuk menjalankan analisis dari terminal."""

import argparse
import logging
import os

import pandas as pd

from src.classification import classify_dataset
from src.config import ensure_output_directories, load_config
from src.data_cleaner import clean_dataset, normalize_column_names
from src.data_loader import load_dataset
from src.data_validator import validate_dataset
from src.geothermometry import calculate_geothermometers
from src.ion_balance import calculate_ion_balance
from src.powell_renderer import render_powell_charts
from src.statistics import calculate_summary_statistics
from src.visualization import create_all_figures

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _save_csv(df: pd.DataFrame, path: str) -> None:
    """Simpan DataFrame ke CSV dan pastikan direktorinya tersedia."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info("File disimpan: %s", path)


def _prepare_main_dataset(
    config: dict,
    input_path: str | None = None,
    sheet_name: str | None = None,
    skip_rows: list[int] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load, normalisasi kolom, dan bersihkan dataset utama Kimia Air."""
    input_cfg = config.get("input", {})
    file_path = input_path or input_cfg.get("file_path")
    target_sheet = sheet_name if sheet_name is not None else input_cfg.get("sheet_name")
    target_skip_rows = skip_rows if skip_rows is not None else input_cfg.get("skip_rows")

    if not file_path:
        raise ValueError("Path input belum diatur. Isi config input.file_path atau pakai --input.")

    raw = load_dataset(file_path, sheet_name=target_sheet, skip_rows=target_skip_rows)
    normalized, mapping = normalize_column_names(raw)
    logger.info("Kolom dinormalisasi: %s", mapping)

    if "sample_id" not in normalized.columns:
        normalized["sample_id"] = [f"KA_{i}" for i in range(len(normalized))]
    if "sample_name" not in normalized.columns:
        normalized["sample_name"] = normalized["sample_id"]

    return clean_dataset(normalized, config)


def _prepare_ion_balance_dataset(config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load dan bersihkan dataset mentah Tugas 1 Ion Balance secara terpisah."""
    input_cfg = config["ion_balance_input"]
    raw = load_dataset(
        input_cfg["file_path"],
        sheet_name=input_cfg.get("sheet_name"),
        skip_rows=input_cfg.get("skip_rows"),
    )
    normalized, mapping = normalize_column_names(raw)
    logger.info("Kolom Ion Balance dinormalisasi: %s", mapping)

    area = normalized["area"].fillna("IB").astype(str).str.strip() if "area" in normalized else "IB"
    if isinstance(area, str):
        normalized["sample_id"] = [f"{area}_{index + 1}" for index in range(len(normalized))]
    else:
        normalized["sample_id"] = [f"{label}_{index + 1}" for index, label in enumerate(area)]
    if "sample_name" not in normalized.columns:
        normalized["sample_name"] = normalized["sample_id"]

    return clean_dataset(normalized, config)


def _write_run_summary(
    path: str,
    cleaned_df: pd.DataFrame,
    validation: dict,
    quality_report: pd.DataFrame,
    output_files: list[str],
    ion_balance_summary: dict | None = None,
) -> None:
    """Buat ringkasan singkat hasil run agar mudah dicek dari GitHub/terminal."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [
        "# Ringkasan Pipeline",
        "",
        f"- Jumlah sampel utama: {len(cleaned_df)}",
        f"- Status validasi: {'valid' if validation['is_valid'] else 'tidak valid'}",
        f"- Jumlah warning validasi: {len(validation['warnings'])}",
        f"- Jumlah catatan cleaning: {len(quality_report)}",
    ]
    if ion_balance_summary is not None:
        lines.extend([
            f"- Jumlah sampel Ion Balance: {ion_balance_summary['sample_count']}",
            f"- Status validasi Ion Balance: {'valid' if ion_balance_summary['is_valid'] else 'tidak valid'}",
            f"- Jumlah catatan cleaning Ion Balance: {ion_balance_summary['quality_count']}",
        ])
    lines.extend(["", "## Output", ""])
    lines.extend(f"- `{file_path}`" for file_path in output_files)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Ringkasan disimpan: %s", path)


def run_pipeline(
    input_path: str | None = None,
    sheet_name: str | None = None,
    skip_rows: list[int] | None = None,
    config_path: str = "config/analysis_config.yaml",
) -> None:
    """Jalankan seluruh pipeline dari baca data hingga simpan output."""
    config = load_config(config_path)
    ensure_output_directories(config)

    output_cfg = config["output"]
    processed_dir = output_cfg["processed_directory"]
    interim_dir = output_cfg["interim_directory"]
    reports_dir = output_cfg["reports_directory"]

    cleaned_df, quality_report = _prepare_main_dataset(config, input_path, sheet_name, skip_rows)
    validation = validate_dataset(cleaned_df)
    if not validation["is_valid"]:
        errors = "\n".join(validation["errors"])
        raise ValueError(f"Validasi dataset gagal:\n{errors}")

    classified_df = classify_dataset(cleaned_df, config)
    analysis_df = calculate_ion_balance(classified_df)
    geo_df = calculate_geothermometers(analysis_df)
    stats_df = calculate_summary_statistics(analysis_df).reset_index()

    ib_cleaned_df, ib_quality_report = _prepare_ion_balance_dataset(config)
    ib_validation = validate_dataset(ib_cleaned_df)
    if not ib_validation["is_valid"]:
        errors = "\n".join(ib_validation["errors"])
        raise ValueError(f"Validasi dataset Ion Balance gagal:\n{errors}")
    ib_analysis_df = calculate_ion_balance(classify_dataset(ib_cleaned_df, config))
    ib_geo_df = calculate_geothermometers(ib_analysis_df)
    ib_stats_df = calculate_summary_statistics(ib_analysis_df).reset_index()

    output_files = [
        os.path.join(interim_dir, "quality_report.csv"),
        os.path.join(processed_dir, "kimia_air_cleaned.csv"),
        os.path.join(processed_dir, "kimia_air_analysis.csv"),
        os.path.join(processed_dir, "geothermometer_results.csv"),
        os.path.join(processed_dir, "summary_statistics.csv"),
        os.path.join(interim_dir, "ion_balance_quality_report.csv"),
        os.path.join(processed_dir, "ion_balance_cleaned.csv"),
        os.path.join(processed_dir, "ion_balance_analysis.csv"),
        os.path.join(processed_dir, "ion_balance_geothermometer_results.csv"),
        os.path.join(processed_dir, "ion_balance_summary_statistics.csv"),
    ]

    _save_csv(quality_report, output_files[0])
    _save_csv(cleaned_df, output_files[1])
    _save_csv(analysis_df, output_files[2])
    _save_csv(geo_df, output_files[3])
    _save_csv(stats_df, output_files[4])
    _save_csv(ib_quality_report, output_files[5])
    _save_csv(ib_cleaned_df, output_files[6])
    _save_csv(ib_analysis_df, output_files[7])
    _save_csv(ib_geo_df, output_files[8])
    _save_csv(ib_stats_df, output_files[9])

    create_all_figures(
        analysis_df,
        config,
        geo_df=geo_df,
        ion_balance_df=ib_analysis_df,
        ion_balance_geo_df=ib_geo_df,
    )

    powell_template = config["powell_reference"]["file_path"]
    render_powell_charts(
        analysis_df,
        "kimia_air",
        powell_template,
        output_cfg["figures_directory"],
        reports_dir,
    )
    render_powell_charts(
        ib_analysis_df,
        "ion_balance",
        powell_template,
        output_cfg["figures_directory"],
        reports_dir,
    )

    summary_path = os.path.join(reports_dir, "run_summary.md")
    _write_run_summary(
        summary_path,
        analysis_df,
        validation,
        quality_report,
        output_files,
        ion_balance_summary={
            "sample_count": len(ib_cleaned_df),
            "is_valid": ib_validation["is_valid"],
            "quality_count": len(ib_quality_report),
        },
    )
    logger.info("Pipeline selesai.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline analisis kimia air panas bumi")
    parser.add_argument("--config", default="config/analysis_config.yaml", help="Path file konfigurasi YAML")
    parser.add_argument("--input", type=str, help="Path file Excel atau CSV")
    parser.add_argument("--sheet-name", type=str, help="Nama sheet Excel")
    parser.add_argument(
        "--skip-rows",
        type=str,
        help="Nomor baris 0-based yang dilewati, dipisahkan koma. Contoh: 0,2",
    )
    args = parser.parse_args()

    run_pipeline(
        input_path=args.input,
        sheet_name=args.sheet_name,
        skip_rows=[int(row) for row in args.skip_rows.split(",")] if args.skip_rows else None,
        config_path=args.config,
    )


if __name__ == "__main__":
    main()

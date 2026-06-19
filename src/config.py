"""Membaca konfigurasi YAML dan menyiapkan path output."""

import os
import yaml


def load_config(config_path: str = "config/analysis_config.yaml") -> dict:
    """Baca file konfigurasi YAML dan kembalikan sebagai dict."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_output_directories(config: dict) -> None:
    """Buat direktori output jika belum ada."""
    dirs = [
        config["output"]["processed_directory"],
        config["output"]["interim_directory"],
        config["output"]["figures_directory"],
        config["output"]["reports_directory"],
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

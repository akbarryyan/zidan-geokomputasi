"""Pengujian persiapan dua dataset mentah pada pipeline."""

from src.config import load_config
from src.pipeline import _prepare_ion_balance_dataset, _prepare_main_dataset


def test_pipeline_prepares_main_and_ion_balance_datasets_separately():
    """Kedua sumber mentah menghasilkan DataFrame dengan identitas berbeda."""
    config = load_config()

    kimia_air_df, _ = _prepare_main_dataset(config)
    ion_balance_df, _ = _prepare_ion_balance_dataset(config)

    assert len(kimia_air_df) == 10
    assert len(ion_balance_df) == 21
    assert set(kimia_air_df["sample_id"]) != set(ion_balance_df["sample_id"])

"""Pengujian renderer diagramsheet Powell-Cumming."""

from pathlib import Path
import shutil

import pandas as pd
import pytest

from src.powell_renderer import POWELL_CHARTS, render_powell_charts


@pytest.mark.skipif(
    not (shutil.which("libreoffice") or shutil.which("soffice")),
    reason="LibreOffice tidak tersedia",
)
def test_renderer_exports_all_powell_charts(tmp_path: Path):
    """Template asli menghasilkan seluruh chartsheet sebagai PNG non-kosong."""
    dataset = pd.DataFrame([
        {
            "sample_name": "Test sample",
            "sample_id": "TS",
            "temperature": 100.0,
            "ph": 7.0,
            "li": 1.0,
            "na": 1000.0,
            "k": 100.0,
            "ca": 10.0,
            "mg": 1.0,
            "sio2": 200.0,
            "b": 20.0,
            "cl": 1500.0,
            "so4": 50.0,
            "hco3": 100.0,
        }
    ])
    rendered = render_powell_charts(
        dataset,
        "test",
        "docs/data-referensi/Contoh_liquid_analysis_v3_powell-cumming_2010_stanfordgw.xlsx",
        tmp_path / "figures",
        tmp_path / "reports",
    )

    assert len(rendered) == len(POWELL_CHARTS)
    assert all(path.exists() and path.stat().st_size > 10_000 for path in rendered)

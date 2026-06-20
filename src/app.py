"""Dashboard Streamlit untuk analisis kimia air panas bumi."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import tempfile

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pipeline import run_pipeline

PROCESSED_DIR = ROOT_DIR / "data" / "processed"
INTERIM_DIR = ROOT_DIR / "data" / "interim"
FIGURES_DIR = ROOT_DIR / "outputs" / "figures"
REPORTS_DIR = ROOT_DIR / "outputs" / "reports"

FIGURE_GROUPS = {
    "Parameter Utama": [
        "ph_by_sample.png",
        "tds_by_sample.png",
        "temperature_by_sample.png",
        "temperature_vs_sio2.png",
        "tds_vs_chloride.png",
    ],
    "Komposisi Ion": [
        "major_ion_comparison.png",
        "major_ion_normalized.png",
    ],
    "Diagram Geokimia": [
        "giggenbach_ternary_ka.png",
        "piper_ka.png",
        "nakamg_ternary_ka.png",
        "giggenbach_ternary_ib.png",
        "piper_ib.png",
        "nakamg_ternary_ib.png",
    ],
    "Geotermometer": ["geothermometer_summary.png"],
}


def _read_csv(filename: str) -> pd.DataFrame | None:
    """Baca hasil pipeline bila file sudah tersedia."""
    path = PROCESSED_DIR / filename
    if not path.exists():
        return None
    return pd.read_csv(path)


def _parse_skip_rows(value: str) -> list[int]:
    """Ubah input seperti '0, 2' menjadi indeks baris yang dilewati."""
    if not value.strip():
        return []
    return [int(row.strip()) for row in value.split(",") if row.strip()]


def _run_analysis(
    uploaded_file: st.runtime.uploaded_file_manager.UploadedFile | None,
    sheet_name: str | None,
    skip_rows: list[int] | None,
) -> None:
    """Jalankan pipeline memakai data bawaan atau file sementara hasil unggahan."""
    if uploaded_file is None:
        run_pipeline()
        return

    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_path = temp_file.name

    try:
        run_pipeline(input_path=temp_path, sheet_name=sheet_name, skip_rows=skip_rows)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _show_metrics(analysis_df: pd.DataFrame) -> None:
    """Tampilkan metrik utama sebagai kartu dashboard."""
    balanced_samples = analysis_df["ion_balance_pct"].abs().le(5).sum()
    columns = st.columns(4)
    metrics = [
        ("Total Sampel", f"{len(analysis_df):02d}", "Data yang sedang ditampilkan", True),
        ("Rata-rata pH", f"{analysis_df['ph'].mean():.2f}", "Tingkat keasaman fluida", False),
        ("Rata-rata Suhu", f"{analysis_df['temperature'].mean():.1f} degC", "Temperatur titik sampling", False),
        ("Ion Balance Baik", f"{balanced_samples:02d}", "Dalam batas +/- 5 persen", False),
    ]
    for column, (label, value, note, featured) in zip(columns, metrics):
        card_class = "metric-card metric-card-featured" if featured else "metric-card"
        column.markdown(
            f"""
            <div class="{card_class}">
              <span>{label}</span>
              <strong>{value}</strong>
              <small>{note}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _show_overview(analysis_df: pd.DataFrame) -> None:
    """Bangun panel ringkasan dua kolom seperti dashboard kerja."""
    left_column, right_column = st.columns([2.15, 1], gap="large")
    fluid_counts = (
        analysis_df["dominant_ion"]
        .fillna("Tidak diketahui")
        .value_counts()
        .rename_axis("Jenis fluida")
        .reset_index(name="Jumlah sampel")
    )

    with left_column:
        with st.container(border=True):
            st.subheader("Komposisi Fluida")
            st.caption("Distribusi ion dominan pada sampel yang sedang ditampilkan.")
            st.bar_chart(fluid_counts, x="Jenis fluida", y="Jumlah sampel", color="#8195f7")

        with st.container(border=True):
            st.subheader("Klasifikasi Sampel")
            display_columns = [
                column
                for column in [
                    "sample_id",
                    "sample_name",
                    "ph",
                    "temperature",
                    "tds",
                    "dominant_ion",
                    "fluid_tendency",
                    "ion_balance_pct",
                ]
                if column in analysis_df.columns
            ]
            st.dataframe(analysis_df[display_columns], width="stretch", hide_index=True, height=310)

    with right_column:
        with st.container(border=True):
            st.caption("DATASET AKTIF")
            st.subheader("Kimia Air Panas Bumi")
            st.write("Gunakan panel di kiri untuk meninjau karakter fluida dari setiap lokasi.")
            st.divider()
            st.write(f"**{len(analysis_df)}** sampel ditampilkan")
            st.write(f"**{analysis_df['dominant_ion'].nunique()}** tipe ion dominan")
            st.write(f"**{analysis_df['temperature'].max():.1f} degC** suhu tertinggi")

        with st.container(border=True):
            st.caption("STATUS ANALISIS")
            st.subheader("Output Siap Ditinjau")
            st.write("Tabel detail, grafik geokimia, dan file CSV tersedia pada tab di bawah.")
            st.caption("Pilih tab Grafik untuk membuka visualisasi lengkap.")

    quality_path = INTERIM_DIR / "quality_report.csv"
    if quality_path.exists():
        quality_df = pd.read_csv(quality_path)
        with st.expander(f"Catatan pembersihan data ({len(quality_df)})"):
            st.dataframe(quality_df, width="stretch", hide_index=True)


def _show_figures() -> None:
    """Tampilkan grafik pipeline per kelompok agar halaman tetap mudah dibaca."""
    for group_name, filenames in FIGURE_GROUPS.items():
        available = [FIGURES_DIR / filename for filename in filenames if (FIGURES_DIR / filename).exists()]
        if not available:
            continue
        st.subheader(group_name)
        for left, right in zip(available[::2], available[1::2] + [None]):
            left_column, right_column = st.columns(2)
            left_column.image(str(left), caption=left.stem.replace("_", " ").title(), width="stretch")
            if right is not None:
                right_column.image(str(right), caption=right.stem.replace("_", " ").title(), width="stretch")


def main() -> None:
    """Bangun halaman Streamlit utama."""
    st.set_page_config(page_title="Analisis Kimia Air", layout="wide")
    st.markdown(
        """
        <style>
        .stApp {
            background: #f3f6f5;
            color: #173f3b;
        }
        [data-testid="stHeader"], .stAppHeader {
            background: #ffffff !important;
            border-bottom: 1px solid #e6ebe9;
        }
        [data-testid="stToolbar"] {
            background: #ffffff !important;
        }
        [data-testid="stMainBlockContainer"], .stMain .block-container {
            max-width: 1450px;
            padding: 2rem 3rem 3rem !important;
        }
        @media (max-width: 900px) {
            [data-testid="stMainBlockContainer"], .stMain .block-container {
                padding: 1.25rem 1rem 2rem !important;
            }
        }
        h1, h2, h3, p, label, [data-testid="stCaptionContainer"] {
            color: #173f3b !important;
        }
        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid #e6ebe9;
        }
        [data-testid="stSidebar"] .block-container { padding-top: 1.6rem; }
        .brand-mark {
            color: #173f3b;
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: -.04em;
            margin-bottom: .1rem;
        }
        .brand-subtitle, .nav-heading {
            color: #82908d;
            font-size: .72rem;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .nav-item {
            color: #50625e;
            border-radius: 10px;
            margin: .25rem 0;
            padding: .58rem .72rem;
        }
        .nav-item-active {
            background: #8195f7;
            color: #ffffff;
            font-weight: 600;
        }
        .dashboard-title h1 { margin-bottom: 0; letter-spacing: -.055em; }
        .dashboard-title p { color: #85928f !important; margin-top: .15rem; }
        .profile-chip {
            align-items: center;
            color: #173f3b;
            display: flex;
            font-size: .85rem;
            font-weight: 700;
            gap: .55rem;
            justify-content: flex-end;
            padding-top: .35rem;
        }
        .profile-avatar {
            align-items: center;
            background: #f0d8c8;
            border-radius: 50%;
            color: #8c3e2e;
            display: flex;
            font-size: .72rem;
            height: 2rem;
            justify-content: center;
            width: 2rem;
        }
        .metric-card {
            background: #ffffff;
            border: 1px solid #e7ecea;
            border-radius: 15px;
            box-shadow: 0 8px 24px rgba(36, 64, 58, .045);
            display: flex;
            flex-direction: column;
            min-height: 122px;
            padding: 1rem 1.1rem;
        }
        .metric-card span { color: #5c6c68; font-size: .78rem; }
        .metric-card strong { color: #173f3b; font-size: 1.65rem; line-height: 1.35; }
        .metric-card small { color: #8b9794; font-size: .68rem; }
        .metric-card-featured { background: #8195f7; border-color: #8195f7; }
        .metric-card-featured span, .metric-card-featured strong, .metric-card-featured small { color: #ffffff; }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: #ffffff;
            border-color: #e6ece9;
            border-radius: 15px;
            box-shadow: 0 8px 24px rgba(36, 64, 58, .035);
        }
        [data-testid="stTextInput"] input {
            background: #ffffff;
            border-color: #e2e9e6;
            border-radius: 12px;
        }
        .stTabs [data-baseweb="tab"] { color: #48635e; }
        .stTabs [aria-selected="true"] { color: #b64b32 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.markdown('<div class="brand-mark">GeoFluid Lab</div>', unsafe_allow_html=True)
        st.markdown('<div class="brand-subtitle">Water Chemistry Workspace</div>', unsafe_allow_html=True)
        st.divider()
        st.markdown('<div class="nav-heading">Workspace</div>', unsafe_allow_html=True)
        st.markdown('<div class="nav-item nav-item-active">Dashboard</div>', unsafe_allow_html=True)
        st.markdown('<div class="nav-item">Data Sampel</div>', unsafe_allow_html=True)
        st.markdown('<div class="nav-item">Geokimia</div>', unsafe_allow_html=True)
        st.markdown('<div class="nav-item">Laporan</div>', unsafe_allow_html=True)
        st.divider()
        st.markdown('<div class="nav-heading">Jalankan Analisis</div>', unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Unggah Excel atau CSV (opsional)", type=["xlsx", "xls", "csv"])
        sheet_name = None
        if uploaded_file and uploaded_file.name.lower().endswith((".xlsx", ".xls")):
            sheets = pd.ExcelFile(BytesIO(uploaded_file.getvalue()), engine="openpyxl").sheet_names
            sheet_name = st.selectbox("Sheet Excel", sheets)

        default_skip_rows = "0, 2" if uploaded_file is None else ""
        skip_rows_text = st.text_input(
            "Lewati baris (indeks 0-based, pisahkan koma)",
            value=default_skip_rows,
            help="Untuk data bawaan, baris 0 dan 2 berisi judul/satuan. Kosongkan untuk file dengan header pada baris pertama.",
        )
        run_clicked = st.button("Jalankan Analisis", type="primary", width="stretch")
        st.caption("Tanpa unggahan, aplikasi memakai data bawaan proyek.")

    if run_clicked:
        try:
            skip_rows = _parse_skip_rows(skip_rows_text)
            with st.spinner("Memproses data dan membuat grafik..."):
                _run_analysis(uploaded_file, sheet_name, skip_rows)
            st.success("Analisis selesai. Semua hasil sudah diperbarui.")
        except Exception as error:
            st.error("Analisis tidak dapat dijalankan. Periksa format file dan kolom wajibnya.")
            st.exception(error)

    analysis_df = _read_csv("kimia_air_analysis.csv")
    if analysis_df is None:
        st.info("Belum ada hasil analisis. Tekan **Jalankan Analisis** untuk memakai data bawaan.")
        return

    title_column, search_column, profile_column = st.columns([1.28, 1.05, .52], vertical_alignment="center")
    with title_column:
        st.markdown(
            '<div class="dashboard-title"><h1>Dashboard</h1><p>Analisis kimia air panas bumi</p></div>',
            unsafe_allow_html=True,
        )
    with search_column:
        search_term = st.text_input("Cari sampel", placeholder="Cari sampel atau lokasi", label_visibility="collapsed")
    with profile_column:
        st.markdown(
            '<div class="profile-chip"><div class="profile-avatar">GF</div>GeoFluid Lab</div>',
            unsafe_allow_html=True,
        )

    if search_term:
        search_mask = analysis_df[["sample_id", "sample_name"]].astype(str).apply(
            lambda column: column.str.contains(search_term, case=False, na=False)
        ).any(axis=1)
        analysis_df = analysis_df[search_mask]
        if analysis_df.empty:
            st.warning("Tidak ada sampel yang cocok dengan pencarian tersebut.")
            return

    _show_metrics(analysis_df)
    overview_tab, data_tab, charts_tab, export_tab = st.tabs(["Ringkasan", "Data", "Grafik", "Unduh Hasil"])

    with overview_tab:
        _show_overview(analysis_df)

    with data_tab:
        st.subheader("Data Analisis Lengkap")
        st.dataframe(analysis_df, width="stretch", hide_index=True)
        geo_df = _read_csv("geothermometer_results.csv")
        if geo_df is not None:
            st.subheader("Hasil Geotermometer")
            st.dataframe(geo_df, width="stretch", hide_index=True)
        stats_df = _read_csv("summary_statistics.csv")
        if stats_df is not None:
            st.subheader("Statistik Deskriptif")
            st.dataframe(stats_df, width="stretch", hide_index=True)

    with charts_tab:
        _show_figures()

    with export_tab:
        st.subheader("File Hasil")
        for path in sorted(PROCESSED_DIR.glob("*.csv")):
            st.download_button(
                label=f"Unduh {path.name}",
                data=path.read_bytes(),
                file_name=path.name,
                mime="text/csv",
            )
        summary_path = REPORTS_DIR / "run_summary.md"
        if summary_path.exists():
            st.download_button(
                label="Unduh ringkasan analisis",
                data=summary_path.read_bytes(),
                file_name=summary_path.name,
                mime="text/markdown",
            )


if __name__ == "__main__":
    main()

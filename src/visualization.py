"""Membuat dan menyimpan grafik analisis kimia air."""

import logging
import os

import matplotlib
matplotlib.use("Agg")  # non-interactive backend, aman untuk server/pipeline
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Warna konsisten untuk ion utama (beda bentuk & pola, bukan hanya warna)
_ION_COLORS = {"Cl": "#2196F3", "SO4": "#FF5722", "HCO3": "#4CAF50"}
_ION_HATCHES = {"Cl": "", "SO4": "//", "HCO3": ".."}


def _get_sample_labels(df: pd.DataFrame) -> list[str]:
    """Ambil label untuk plot: prioritas sample_id (kode singkat), fallback ke sample_name."""
    if "sample_id" in df.columns:
        return df["sample_id"].fillna(df.get("sample_name", range(len(df)))).tolist()
    if "sample_name" in df.columns:
        return df["sample_name"].tolist()
    return [str(i) for i in range(len(df))]


def _save_and_close(fig: plt.Figure, output_path: str, dpi: int = 300) -> None:
    """Simpan figure ke PNG dan tutup."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Grafik disimpan: {output_path}")


def plot_parameter_by_sample(
    df: pd.DataFrame,
    parameter: str,
    output_path: str,
    title: str = "",
    ylabel: str = "",
    config: dict | None = None,
) -> None:
    """
    Buat bar chart satu parameter per sampel dan simpan ke PNG.

    Garis referensi ditambahkan otomatis untuk parameter 'ph'.
    """
    cfg = config or {}
    vis_cfg = cfg.get("visualization", {})
    dpi = vis_cfg.get("dpi", 300)
    fig_w = vis_cfg.get("figure_width", 10)
    fig_h = vis_cfg.get("figure_height", 6)
    ph_cfg = cfg.get("ph_classification", {})
    acidic_max = ph_cfg.get("acidic_max", 6.5)
    neutral_max = ph_cfg.get("neutral_max", 7.5)

    labels = _get_sample_labels(df)
    values = pd.to_numeric(df[parameter], errors="coerce")

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    x = range(len(labels))

    bars = ax.bar(
        x, values,
        color="#5C7AEA", edgecolor="white", linewidth=0.5,
    )

    # Tambahkan nilai di atas setiap batang
    for bar, val in zip(bars, values):
        if not np.isnan(val):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(values.dropna()) * 0.01,
                f"{val:.2f}",
                ha="center", va="bottom", fontsize=8,
            )

    # Garis referensi khusus pH
    if parameter == "ph":
        ax.axhline(y=acidic_max, color="#FF5722", linestyle="--", linewidth=1.2,
                   label=f"Batas asam (pH {acidic_max})")
        ax.axhline(y=neutral_max, color="#4CAF50", linestyle="--", linewidth=1.2,
                   label=f"Batas netral (pH {neutral_max})")
        ax.legend(fontsize=9)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.set_title(title or f"{parameter.upper()} per Sampel", fontsize=13, fontweight="bold")
    ax.set_xlabel("Sampel", fontsize=11)
    ax.set_ylabel(ylabel or parameter.upper(), fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    _save_and_close(fig, output_path, dpi)


def plot_major_ion_comparison(
    df: pd.DataFrame,
    output_path: str,
    config: dict | None = None,
) -> None:
    """
    Buat grouped bar chart Cl, SO4, HCO3 per sampel (konsentrasi asli).

    Setiap ion punya warna dan pola arsir berbeda agar mudah dibedakan.
    """
    cfg = config or {}
    vis_cfg = cfg.get("visualization", {})
    dpi = vis_cfg.get("dpi", 300)
    fig_w = vis_cfg.get("figure_width", 12)
    fig_h = vis_cfg.get("figure_height", 6)

    labels = _get_sample_labels(df)
    ions = [
        ("Cl", "cl"),
        ("SO₄", "so4"),
        ("HCO₃", "hco3"),
    ]

    n_samples = len(labels)
    n_ions = len(ions)
    bar_width = 0.25
    x = np.arange(n_samples)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    ion_keys = list(_ION_COLORS.keys())
    for i, (ion_label, col) in enumerate(ions):
        key = ion_keys[i]
        values = pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series([np.nan] * n_samples)
        offset = (i - n_ions / 2 + 0.5) * bar_width
        ax.bar(
            x + offset, values,
            width=bar_width,
            label=ion_label,
            color=_ION_COLORS[key],
            hatch=_ION_HATCHES[key],
            edgecolor="white",
            linewidth=0.5,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.set_title("Perbandingan Ion Utama (Cl, SO₄, HCO₃) per Sampel",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Sampel", fontsize=11)
    ax.set_ylabel("Konsentrasi (mg/L)", fontsize=11)
    ax.legend(title="Ion", fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    _save_and_close(fig, output_path, dpi)


def plot_normalized_major_ions(
    df: pd.DataFrame,
    output_path: str,
    config: dict | None = None,
) -> None:
    """
    Buat 100% stacked bar chart proporsi Cl, SO4, HCO3 per sampel.

    Menggunakan kolom cl_percentage, so4_percentage, hco3_percentage
    jika tersedia, atau menghitung ulang dari nilai mentah.
    """
    cfg = config or {}
    vis_cfg = cfg.get("visualization", {})
    dpi = vis_cfg.get("dpi", 300)
    fig_w = vis_cfg.get("figure_width", 12)
    fig_h = vis_cfg.get("figure_height", 6)

    labels = _get_sample_labels(df)

    # Ambil persentase
    if "cl_percentage" in df.columns:
        cl_pct = pd.to_numeric(df["cl_percentage"], errors="coerce").fillna(0)
        so4_pct = pd.to_numeric(df["so4_percentage"], errors="coerce").fillna(0)
        hco3_pct = pd.to_numeric(df["hco3_percentage"], errors="coerce").fillna(0)
    else:
        from src.classification import calculate_major_ion_proportions
        cl_pct, so4_pct, hco3_pct = [], [], []
        for idx in df.index:
            p = calculate_major_ion_proportions(
                df.at[idx, "cl"] if "cl" in df.columns else np.nan,
                df.at[idx, "so4"] if "so4" in df.columns else np.nan,
                df.at[idx, "hco3"] if "hco3" in df.columns else np.nan,
            )
            cl_pct.append(0 if np.isnan(p["cl_pct"]) else p["cl_pct"])
            so4_pct.append(0 if np.isnan(p["so4_pct"]) else p["so4_pct"])
            hco3_pct.append(0 if np.isnan(p["hco3_pct"]) else p["hco3_pct"])
        cl_pct = pd.Series(cl_pct)
        so4_pct = pd.Series(so4_pct)
        hco3_pct = pd.Series(hco3_pct)

    x = np.arange(len(labels))
    bar_width = 0.6
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    p1 = ax.bar(x, cl_pct, bar_width, label="Cl",
                color=_ION_COLORS["Cl"], hatch=_ION_HATCHES["Cl"], edgecolor="white")
    p2 = ax.bar(x, so4_pct, bar_width, bottom=cl_pct, label="SO₄",
                color=_ION_COLORS["SO4"], hatch=_ION_HATCHES["SO4"], edgecolor="white")
    p3 = ax.bar(x, hco3_pct, bar_width, bottom=cl_pct + so4_pct, label="HCO₃",
                color=_ION_COLORS["HCO3"], hatch=_ION_HATCHES["HCO3"], edgecolor="white")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_title("Proporsi Ion Utama per Sampel (%)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Sampel", fontsize=11)
    ax.set_ylabel("Proporsi (%)", fontsize=11)
    ax.legend(title="Ion", fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    _save_and_close(fig, output_path, dpi)


def plot_scatter_with_labels(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    label_column: str,
    output_path: str,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    config: dict | None = None,
) -> None:
    """
    Buat scatter plot dua parameter dengan label ID sampel di setiap titik.

    Titik dengan nilai kosong pada salah satu sumbu tidak ditampilkan.
    """
    cfg = config or {}
    vis_cfg = cfg.get("visualization", {})
    dpi = vis_cfg.get("dpi", 300)
    fig_w = vis_cfg.get("figure_width", 10)
    fig_h = vis_cfg.get("figure_height", 6)

    x_vals = pd.to_numeric(df[x_column], errors="coerce")
    y_vals = pd.to_numeric(df[y_column], errors="coerce")
    labels = df[label_column].tolist() if label_column in df.columns else [str(i) for i in range(len(df))]

    # Filter baris dengan nilai valid pada kedua sumbu
    mask = x_vals.notna() & y_vals.notna()
    x_plot = x_vals[mask]
    y_plot = y_vals[mask]
    labels_plot = [labels[i] for i, m in enumerate(mask) if m]

    if len(x_plot) == 0:
        logger.warning(f"Scatter plot '{output_path}' dilewati: tidak ada data valid.")
        return

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.scatter(x_plot, y_plot, color="#5C7AEA", s=80, edgecolors="white", linewidths=0.8, zorder=3)

    # Label tiap titik — sedikit offset agar tidak menumpuk titik
    for xi, yi, lbl in zip(x_plot, y_plot, labels_plot):
        ax.annotate(
            str(lbl),
            (xi, yi),
            textcoords="offset points",
            xytext=(6, 4),
            fontsize=8,
            color="#333333",
        )

    ax.set_title(title or f"{y_column.upper()} vs {x_column.upper()}", fontsize=13, fontweight="bold")
    ax.set_xlabel(xlabel or x_column.upper(), fontsize=11)
    ax.set_ylabel(ylabel or y_column.upper(), fontsize=11)
    ax.grid(linestyle="--", alpha=0.5)
    plt.tight_layout()
    _save_and_close(fig, output_path, dpi)


def _ternary_to_cartesian(cl_frac: float, so4_frac: float, hco3_frac: float) -> tuple[float, float]:
    """
    Konversi fraksi ternary ke koordinat Kartesian segitiga sama sisi.

    Orientasi:
      - Kiri bawah: Cl
      - Kanan bawah: SO₄
      - Atas: HCO₃
    """
    sqrt3_over2 = 3 ** 0.5 / 2
    x = so4_frac + 0.5 * hco3_frac
    y = hco3_frac * sqrt3_over2
    return x, y


def plot_giggenbach_ternary(
    df: pd.DataFrame,
    output_path: str,
    config: dict | None = None,
) -> None:
    """
    Buat diagram ternary Cl-SO₄-HCO₃ (Giggenbach 1991).

    Menggunakan kolom cl_percentage, so4_percentage, hco3_percentage
    atau menghitung ulang dari cl, so4, hco3.
    """
    cfg = config or {}
    vis_cfg = cfg.get("visualization", {})
    dpi = vis_cfg.get("dpi", 300)

    sqrt3_over2 = 3 ** 0.5 / 2

    fig, ax = plt.subplots(figsize=(8, 7))
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Gambar tepi segitiga ─────────────────────────────────────────
    triangle_x = [0, 1, 0.5, 0]
    triangle_y = [0, 0, sqrt3_over2, 0]
    ax.plot(triangle_x, triangle_y, "k-", linewidth=1.5, zorder=2)

    # ── Grid lines tiap 20% (3 arah) ────────────────────────────────
    grid_style = {"color": "#BBBBBB", "linewidth": 0.5, "linestyle": "--", "zorder": 1}
    for p in [0.2, 0.4, 0.6, 0.8]:
        q = 1 - p
        # Cl = p: dari (q, 0) ke (0.5*q, q*√3/2)  [bottom → left edge]
        ax.plot([q, 0.5 * q], [0, q * sqrt3_over2], **grid_style)
        # SO₄ = p: dari (p, 0) ke (0.5 + 0.5*p, (1-p)*√3/2)  [bottom → right edge]
        ax.plot([p, 0.5 + 0.5 * p], [0, q * sqrt3_over2], **grid_style)
        # HCO₃ = p: garis horizontal dari (0.5*p, p*√3/2) ke (1-0.5*p, p*√3/2)
        ax.plot([0.5 * p, 1 - 0.5 * p], [p * sqrt3_over2, p * sqrt3_over2], **grid_style)

    # ── Label vertex ─────────────────────────────────────────────────
    ax.text(-0.06, -0.04, "Cl", fontsize=13, fontweight="bold", ha="center", color="#2196F3")
    ax.text(1.06, -0.04, "SO₄", fontsize=13, fontweight="bold", ha="center", color="#FF5722")
    ax.text(0.5, sqrt3_over2 + 0.04, "HCO₃", fontsize=13, fontweight="bold", ha="center", color="#4CAF50")

    # ── Tick labels 20%–80% di tiap sisi ────────────────────────────
    tick_style = {"fontsize": 7, "color": "#555555"}
    for p in [0.2, 0.4, 0.6, 0.8]:
        q = 1 - p
        # Sisi kiri (Cl-HCO₃): r=0, Cl frac = q, HCO₃ frac = p
        ax.text(0.5 * p - 0.04, p * sqrt3_over2, f"{int(p*100)}", ha="right", **tick_style)
        # Sisi kanan (SO₄-HCO₃): l=0, SO₄ frac = q, HCO₃ frac = p
        ax.text(1 - 0.5 * p + 0.04, p * sqrt3_over2, f"{int(p*100)}", ha="left", **tick_style)
        # Sisi bawah (Cl-SO₄): t=0, SO₄ frac = p
        ax.text(p, -0.04, f"{int(p*100)}", ha="center", **tick_style)

    # ── Label kawasan Giggenbach ──────────────────────────────────────
    region_style = {"fontsize": 8, "color": "#888888", "ha": "center",
                    "style": "italic", "zorder": 1}
    ax.text(0.14, 0.05, "Mature\nChloride", **region_style)
    ax.text(0.86, 0.05, "Steam-heated\n/ Volcanic", **region_style)
    ax.text(0.50, sqrt3_over2 - 0.10, "Peripheral\nBicarbonate", **region_style)

    # ── Plot titik sampel ─────────────────────────────────────────────
    if "cl_percentage" in df.columns:
        cl_pct = pd.to_numeric(df["cl_percentage"], errors="coerce")
        so4_pct = pd.to_numeric(df["so4_percentage"], errors="coerce")
        hco3_pct = pd.to_numeric(df["hco3_percentage"], errors="coerce")
    else:
        from src.classification import calculate_major_ion_proportions
        cl_list, so4_list, hco3_list = [], [], []
        for idx in df.index:
            p = calculate_major_ion_proportions(
                df.at[idx, "cl"] if "cl" in df.columns else np.nan,
                df.at[idx, "so4"] if "so4" in df.columns else np.nan,
                df.at[idx, "hco3"] if "hco3" in df.columns else np.nan,
            )
            cl_list.append(p["cl_pct"])
            so4_list.append(p["so4_pct"])
            hco3_list.append(p["hco3_pct"])
        cl_pct = pd.Series(cl_list)
        so4_pct = pd.Series(so4_list)
        hco3_pct = pd.Series(hco3_list)

    labels = _get_sample_labels(df)

    for i in range(len(df)):
        cl_v, so4_v, hco3_v = cl_pct.iloc[i], so4_pct.iloc[i], hco3_pct.iloc[i]
        if any(np.isnan(v) for v in (cl_v, so4_v, hco3_v)):
            continue
        total = cl_v + so4_v + hco3_v
        if total == 0:
            continue
        x, y = _ternary_to_cartesian(cl_v / total, so4_v / total, hco3_v / total)
        ax.scatter(x, y, color="#5C7AEA", s=70, edgecolors="white",
                   linewidths=0.8, zorder=4)
        ax.annotate(
            str(labels[i]),
            (x, y),
            textcoords="offset points",
            xytext=(5, 4),
            fontsize=8,
            color="#333333",
            zorder=5,
        )

    ax.set_title("Diagram Ternary Cl–SO₄–HCO₃ (Giggenbach 1991)",
                 fontsize=12, fontweight="bold", pad=16)
    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(-0.10, sqrt3_over2 + 0.12)
    plt.tight_layout()
    _save_and_close(fig, output_path, dpi)


def plot_geothermometer_summary(
    geo_df: pd.DataFrame,
    output_path: str,
    config: dict | None = None,
) -> None:
    """
    Buat dot plot estimasi suhu reservoir dari semua geotermometer Powell (2010).

    Setiap baris = satu sampel, setiap simbol = satu geotermometer.
    """
    cfg = config or {}
    vis_cfg = cfg.get("visualization", {})
    dpi = vis_cfg.get("dpi", 300)

    # Semua 14 geotermometer Powell (2010)
    temp_cols = [
        # SiO₂
        ("t_quartz_°C",            "Quartz (konduktif)",   "#1565C0", "o"),
        ("t_quartz_adiabatic_°C",  "Quartz (adiabatik)",  "#1E88E5", "o"),
        ("t_chalcedony_°C",        "Chalcedony",           "#43A047", "s"),
        ("t_alpha_cristobalite_°C","α-Cristobalite",       "#66BB6A", "s"),
        ("t_beta_cristobalite_°C", "β-Cristobalite",       "#A5D6A7", "s"),
        ("t_amorphous_silica_°C",  "Amorphous Silica",     "#C8E6C9", "s"),
        # Na/K
        ("t_nk_fournier1979_°C",   "Na/K Fournier 1979",  "#E53935", "^"),
        ("t_nk_truesdell1976_°C",  "Na/K Truesdell 1976", "#EF5350", "^"),
        ("t_nk_tonani1980_°C",     "Na/K Tonani 1980",    "#EF9A9A", "^"),
        ("t_nk_giggenbach1988_°C", "Na/K Giggenbach 1988","#9C27B0", "D"),
        ("t_nk_nieva1987_°C",      "Na/K Nieva 1987",     "#CE93D8", "D"),
        ("t_nk_arnorsson1983_°C",  "Na/K Arnorsson 1983", "#6A1B9A", "D"),
        # Na-K-Ca
        ("t_nkca_fournier1973_°C", "Na-K-Ca Fournier 1973","#FF6F00","P"),
        # K/Mg
        ("t_kmg_giggenbach1986_°C","K/Mg Giggenbach 1986","#FF9800", "X"),
    ]

    available = [(col, lbl, clr, mk) for col, lbl, clr, mk in temp_cols if col in geo_df.columns]
    if not available:
        logger.warning("Tidak ada kolom geotermometer untuk diplot.")
        return

    sample_labels = _get_sample_labels(geo_df)
    n = len(sample_labels)
    y_pos = list(range(n))

    fig, ax = plt.subplots(figsize=(13, max(6, n * 0.65)))

    for col, label, color, marker in available:
        vals = pd.to_numeric(geo_df[col], errors="coerce")
        valid_y = [y_pos[i] for i in range(n) if not np.isnan(vals.iloc[i])]
        valid_x = [vals.iloc[i] for i in range(n) if not np.isnan(vals.iloc[i])]
        ax.scatter(valid_x, valid_y, label=label, color=color,
                   marker=marker, s=55, zorder=3, alpha=0.85)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(sample_labels, fontsize=9)
    ax.set_xlabel("Estimasi Suhu Reservoir (°C)", fontsize=11)
    ax.set_title("Estimasi Suhu Reservoir — Semua Geotermometer Powell (2010)",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=8, loc="lower right", ncol=2)
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.invert_yaxis()

    note = ("Catatan: Hasil bersifat indikatif. Validitas tiap geotermometer bergantung\n"
            "pada kondisi reservoir, tipe fluida, dan tingkat kesetimbangan.")
    ax.text(0.01, -0.07, note, transform=ax.transAxes,
            fontsize=7, color="#888888", style="italic")

    plt.tight_layout()
    _save_and_close(fig, output_path, dpi)


def _piper_diamond_point(
    xc: float, yc: float, xa: float, ya: float
) -> tuple[float, float]:
    """Hitung koordinat titik di diamond Piper dari proyeksi dua triangle."""
    sqrt3 = 3 ** 0.5
    x = ((ya - yc) / sqrt3 + xa + xc) / 2
    y = sqrt3 * x + (yc - sqrt3 * xc)
    return x, y


def _draw_ternary_triangle(
    ax,
    v_a: tuple, v_b: tuple, v_c: tuple,
    label_a: str, label_b: str, label_c: str,
    colors: tuple = ("#1565C0", "#C62828", "#2E7D32"),
) -> None:
    """
    Gambar segitiga sama sisi dengan grid 20% dan label vertex.

    v_a, v_b, v_c — koordinat vertex (x, y) di plot.
    Label A berada di v_a, dst.
    """
    h = 3 ** 0.5 / 2
    # Garis tepi
    xs = [v_a[0], v_b[0], v_c[0], v_a[0]]
    ys = [v_a[1], v_b[1], v_c[1], v_a[1]]
    ax.plot(xs, ys, "k-", linewidth=1.5, zorder=2)

    grid_kw = {"color": "#CCCCCC", "linewidth": 0.5, "linestyle": "--", "zorder": 1}
    for p in [0.2, 0.4, 0.6, 0.8]:
        q = 1 - p
        # Garis konstan fA = p (paralel terhadap sisi B-C)
        # Titik di sisi A-B (fC=0, fA=p): P = fA*vA + fB*vB = p*vA + (1-p)*vB
        p1x = p * v_a[0] + q * v_b[0]
        p1y = p * v_a[1] + q * v_b[1]
        # Titik di sisi A-C (fB=0, fA=p): P = p*vA + (1-p)*vC
        p2x = p * v_a[0] + q * v_c[0]
        p2y = p * v_a[1] + q * v_c[1]
        ax.plot([p1x, p2x], [p1y, p2y], **grid_kw)

        # Garis konstan fB = p (paralel terhadap sisi A-C)
        p1x = p * v_b[0] + q * v_a[0]
        p1y = p * v_b[1] + q * v_a[1]
        p2x = p * v_b[0] + q * v_c[0]
        p2y = p * v_b[1] + q * v_c[1]
        ax.plot([p1x, p2x], [p1y, p2y], **grid_kw)

        # Garis konstan fC = p (paralel terhadap sisi A-B)
        p1x = p * v_c[0] + q * v_a[0]
        p1y = p * v_c[1] + q * v_a[1]
        p2x = p * v_c[0] + q * v_b[0]
        p2y = p * v_c[1] + q * v_b[1]
        ax.plot([p1x, p2x], [p1y, p2y], **grid_kw)

    # Label vertex
    offset = 0.07
    ax.text(v_a[0] - offset, v_a[1] - offset * 0.6, label_a,
            fontsize=11, fontweight="bold", ha="center", color=colors[0])
    ax.text(v_b[0] + offset, v_b[1] - offset * 0.6, label_b,
            fontsize=11, fontweight="bold", ha="center", color=colors[1])
    ax.text(v_c[0], v_c[1] + offset * 0.8, label_c,
            fontsize=11, fontweight="bold", ha="center", color=colors[2])


def plot_piper_diagram(
    df: pd.DataFrame,
    output_path: str,
    config: dict | None = None,
    title_suffix: str = "",
) -> None:
    """
    Buat diagram Piper (trilinear) untuk klasifikasi tipe air geothermal.

    Membutuhkan kolom meq/L dari calculate_ion_balance():
        na_meq, k_meq, ca_meq, mg_meq, cl_meq, so4_meq, hco3_meq

    Layout:
        - Segitiga kiri (kation): Ca (kiri), Na+K (kanan), Mg (atas)
        - Segitiga kanan (anion): Cl (kiri), HCO₃ (kanan), SO₄ (atas)
        - Diamond tengah-atas: proyeksi gabungan kation + anion
    """
    cfg = config or {}
    vis_cfg = cfg.get("visualization", {})
    dpi = vis_cfg.get("dpi", 300)

    h = 3 ** 0.5 / 2      # tinggi segitiga sama sisi (sisi=1)
    GAP = 0.2               # jarak horizontal antara dua segitiga
    sqrt3 = 3 ** 0.5

    # ── Vertex koordinat ─────────────────────────────────────────────────────
    # Kation: Ca(0,0), NaK(1,0), Mg(0.5,h)
    vCa  = (0.0, 0.0)
    vNaK = (1.0, 0.0)
    vMg  = (0.5, h)

    # Anion: Cl(1+GAP,0), HCO3(2+GAP,0), SO4(1.5+GAP,h)
    off  = 1.0 + GAP
    vCl  = (off,       0.0)
    vHCO = (off + 1.0, 0.0)
    vSO4 = (off + 0.5, h)

    # Diamond vertices (dihitung dari proyeksi)
    d_bot   = _piper_diamond_point(*vNaK, *vCl)   # NaK + Cl
    d_top   = _piper_diamond_point(*vCa,  *vHCO)  # Ca  + HCO3
    d_left  = _piper_diamond_point(*vCa,  *vCl)   # Ca  + Cl
    d_right = _piper_diamond_point(*vNaK, *vHCO)  # NaK + HCO3

    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Gambar dua segitiga ───────────────────────────────────────────────────
    _draw_ternary_triangle(ax, vCa, vNaK, vMg, "Ca²⁺", "Na⁺+K⁺", "Mg²⁺",
                           colors=("#1565C0", "#C62828", "#2E7D32"))
    _draw_ternary_triangle(ax, vCl, vHCO, vSO4, "Cl⁻", "HCO₃⁻", "SO₄²⁻",
                           colors=("#1565C0", "#C62828", "#2E7D32"))

    # ── Gambar diamond ────────────────────────────────────────────────────────
    diam_x = [d_bot[0], d_left[0], d_top[0], d_right[0], d_bot[0]]
    diam_y = [d_bot[1], d_left[1], d_top[1], d_right[1], d_bot[1]]
    ax.plot(diam_x, diam_y, "k-", linewidth=1.5, zorder=2)

    # Label zona di diamond
    zone_kw = {"fontsize": 8, "color": "#888888", "ha": "center",
               "style": "italic", "zorder": 1}
    cx = (d_bot[0] + d_left[0] + d_top[0] + d_right[0]) / 4
    cy = (d_bot[1] + d_left[1] + d_top[1] + d_right[1]) / 4
    ax.text(cx, d_top[1] - 0.12, "Ca-HCO₃\n(Bikarbonat)",  **zone_kw)
    ax.text(cx, d_bot[1] + 0.07, "Na-Cl\n(Klorida Natrium)", **zone_kw)
    ax.text(d_left[0]  + 0.08, d_left[1],  "Ca-Cl",  **zone_kw)
    ax.text(d_right[0] - 0.08, d_right[1], "Na-HCO₃", **zone_kw)

    # ── Plot titik sampel ─────────────────────────────────────────────────────
    meq_cols_ok = all(c in df.columns for c in ("na_meq", "k_meq", "ca_meq",
                                                  "mg_meq", "cl_meq", "so4_meq", "hco3_meq"))
    if not meq_cols_ok:
        logger.warning("Kolom meq/L tidak tersedia — plot Piper dilewati.")
        plt.close(fig)
        return

    labels = _get_sample_labels(df)

    for i in range(len(df)):
        idx = df.index[i]
        na  = df.at[idx, "na_meq"]  or 0
        k   = df.at[idx, "k_meq"]   or 0
        ca  = df.at[idx, "ca_meq"]  or 0
        mg  = df.at[idx, "mg_meq"]  or 0
        cl  = df.at[idx, "cl_meq"]  or 0
        so4 = df.at[idx, "so4_meq"] or 0
        hco = df.at[idx, "hco3_meq"] or 0

        sum_cat = na + k + ca + mg
        sum_ani = cl + so4 + hco

        if sum_cat <= 0 or sum_ani <= 0:
            continue

        # Fraksi kation: Ca, NaK, Mg
        fCa  = ca / sum_cat
        fNaK = (na + k) / sum_cat
        fMg  = mg / sum_cat

        # Fraksi anion: Cl, HCO3, SO4
        fCl  = cl / sum_ani
        fHCO = hco / sum_ani
        fSO4 = so4 / sum_ani

        # Koordinat di segitiga kation (A=Ca, B=NaK, C=Mg)
        xc = fNaK * vNaK[0] + fCa * vCa[0] + fMg * vMg[0]
        yc = fNaK * vNaK[1] + fCa * vCa[1] + fMg * vMg[1]

        # Koordinat di segitiga anion (A=Cl, B=HCO3, C=SO4)
        xa = fCl * vCl[0] + fHCO * vHCO[0] + fSO4 * vSO4[0]
        ya = fCl * vCl[1] + fHCO * vHCO[1] + fSO4 * vSO4[1]

        # Koordinat di diamond
        xd, yd = _piper_diamond_point(xc, yc, xa, ya)

        pt_kw = {"s": 60, "edgecolors": "white", "linewidths": 0.7, "zorder": 4}
        lbl_kw = {"textcoords": "offset points", "xytext": (5, 4),
                  "fontsize": 7.5, "color": "#333333", "zorder": 5}

        ax.scatter(xc, yc, color="#5C7AEA", **pt_kw)
        ax.scatter(xa, ya, color="#5C7AEA", **pt_kw)
        ax.scatter(xd, yd, color="#E53935", **pt_kw)
        ax.annotate(str(labels[i]), (xc, yc), **lbl_kw)
        ax.annotate(str(labels[i]), (xa, ya), **lbl_kw)
        ax.annotate(str(labels[i]), (xd, yd), **lbl_kw)

    suffix = f" — {title_suffix}" if title_suffix else ""
    ax.set_title(f"Diagram Piper{suffix}", fontsize=13, fontweight="bold", pad=16)

    xmin = -0.2; xmax = off + 1.2
    ymin = -0.15; ymax = d_top[1] + 0.15
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    note = "● Titik biru: posisi di segitiga kation/anion   ● Titik merah: posisi di diamond"
    ax.text(0.5, -0.04, note, transform=ax.transAxes, fontsize=7.5,
            color="#555555", ha="center")
    plt.tight_layout()
    _save_and_close(fig, output_path, dpi)


def plot_nakamg_ternary(
    df: pd.DataFrame,
    output_path: str,
    config: dict | None = None,
    title_suffix: str = "",
) -> None:
    """
    Buat diagram ternary Na/10 – K – √Mg (Giggenbach 1988).

    Digunakan untuk menilai tingkat kesetimbangan fluida dengan batuan reservoir.

    - Mendekati vertex √Mg → fluida imatur (belum setimbang)
    - Mendekati sisi Na/10–K → fluida matang / setimbang
    - Isoterm suhu dari Na/K Giggenbach (1988) ditampilkan sebagai garis putus-putus

    Kolom yang dibutuhkan: na, k, mg (dalam mg/kg).
    """
    cfg = config or {}
    vis_cfg = cfg.get("visualization", {})
    dpi = vis_cfg.get("dpi", 300)

    h = 3 ** 0.5 / 2

    # Vertex: K(0,0), √Mg(1,0), Na/10(0.5,h)
    vK    = (0.0, 0.0)
    vSqMg = (1.0, 0.0)
    vNa10 = (0.5, h)

    fig, ax = plt.subplots(figsize=(8, 7))
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Gambar segitiga ───────────────────────────────────────────────────────
    _draw_ternary_triangle(
        ax, vK, vSqMg, vNa10,
        "K", "√Mg", "Na/10",
        colors=("#C62828", "#2E7D32", "#1565C0"),
    )

    # ── Isoterm suhu Giggenbach (1988) ────────────────────────────────────────
    # Setiap isoterm adalah garis horizontal di ketinggian f_na10 * h
    # f_na10 = r_wt / (r_wt + 10), r_wt = r_mol * (22.99/39.10)
    isotherm_temps = [
        (100,  "#81C784"),
        (150,  "#4CAF50"),
        (200,  "#FFA726"),
        (250,  "#EF5350"),
        (300,  "#B71C1C"),
    ]
    for T, color in isotherm_temps:
        r_mol   = 10 ** (1390 / (T + 273.15) - 1.75)
        r_wt    = r_mol * (22.99 / 39.10)
        f_na10  = r_wt / (r_wt + 10)
        y_line  = f_na10 * h
        x_left  = 0.5 * f_na10          # titik di sisi K-Na/10
        x_right = 1 - 0.5 * f_na10      # titik di sisi √Mg-Na/10
        ax.plot([x_left, x_right], [y_line, y_line],
                color=color, linewidth=1.0, linestyle="--", alpha=0.85, zorder=2)
        ax.text(x_right + 0.03, y_line, f"{T}°C",
                fontsize=8, color=color, va="center", zorder=3)

    # ── Label zona ────────────────────────────────────────────────────────────
    ax.text(0.50, h * 0.90, "Zona matang\n(kesetimbangan penuh)",
            fontsize=8, color="#555555", ha="center", style="italic")
    ax.text(0.50, h * 0.10, "Zona imatur\n(fluida belum setimbang)",
            fontsize=8, color="#555555", ha="center", style="italic")

    # ── Plot titik sampel ─────────────────────────────────────────────────────
    has_cols = all(c in df.columns for c in ("na", "k", "mg"))
    if not has_cols:
        logger.warning("Kolom na/k/mg tidak tersedia — Na-K-√Mg ternary dilewati.")
        plt.close(fig)
        return

    labels = _get_sample_labels(df)

    for i in range(len(df)):
        idx   = df.index[i]
        na_v  = pd.to_numeric(df.at[idx, "na"],  errors="coerce")
        k_v   = pd.to_numeric(df.at[idx, "k"],   errors="coerce")
        mg_v  = pd.to_numeric(df.at[idx, "mg"],  errors="coerce")

        if any(np.isnan(v) or v <= 0 for v in (na_v, k_v, mg_v)):
            continue

        a = na_v / 10        # Na/10
        b = k_v              # K
        c = mg_v ** 0.5      # √Mg
        total = a + b + c

        if total <= 0:
            continue

        f_na10  = a / total
        f_k     = b / total
        f_sqmg  = c / total

        # Koordinat Kartesian
        x = f_sqmg * vSqMg[0] + f_k * vK[0] + f_na10 * vNa10[0]
        y = f_sqmg * vSqMg[1] + f_k * vK[1] + f_na10 * vNa10[1]

        ax.scatter(x, y, color="#5C7AEA", s=70, edgecolors="white",
                   linewidths=0.8, zorder=4)
        ax.annotate(str(labels[i]), (x, y),
                    textcoords="offset points", xytext=(5, 4),
                    fontsize=8, color="#333333", zorder=5)

    suffix = f" — {title_suffix}" if title_suffix else ""
    ax.set_title(f"Diagram Na/10–K–√Mg (Giggenbach 1988){suffix}",
                 fontsize=12, fontweight="bold", pad=16)
    ax.set_xlim(-0.15, 1.20)
    ax.set_ylim(-0.10, h + 0.15)
    plt.tight_layout()
    _save_and_close(fig, output_path, dpi)


def create_all_figures(
    df: pd.DataFrame,
    config: dict,
    geo_df: pd.DataFrame | None = None,
    ion_balance_df: pd.DataFrame | None = None,
    ion_balance_geo_df: pd.DataFrame | None = None,
) -> None:
    """
    Buat dan simpan semua grafik analisis kimia air panas bumi.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset utama (Kimia Air) setelah classify_dataset() dan
        calculate_ion_balance(). Harus mengandung kolom meq/L.
    config : dict
        Konfigurasi proyek (dari YAML).
    geo_df : pd.DataFrame, optional
        Hasil calculate_geothermometers() dari dataset utama.
    ion_balance_df : pd.DataFrame, optional
        Dataset mentah Tugas 1 Ion Balance yang sudah dianalisis.
    ion_balance_geo_df : pd.DataFrame, optional
        Hasil geotermometer untuk dataset Ion Balance.
    """
    fig_dir = config.get("output", {}).get("figures_directory", "outputs/figures")

    # 1. pH per sampel
    plot_parameter_by_sample(
        df, "ph",
        output_path=os.path.join(fig_dir, "ph_by_sample.png"),
        title="pH per Sampel",
        ylabel="pH",
        config=config,
    )

    # 2. TDS per sampel
    plot_parameter_by_sample(
        df, "tds",
        output_path=os.path.join(fig_dir, "tds_by_sample.png"),
        title="TDS per Sampel",
        ylabel="TDS (mg/L)",
        config=config,
    )

    # 3. Suhu per sampel
    plot_parameter_by_sample(
        df, "temperature",
        output_path=os.path.join(fig_dir, "temperature_by_sample.png"),
        title="Suhu per Sampel",
        ylabel="Suhu (°C)",
        config=config,
    )

    # 4. Perbandingan ion utama (konsentrasi asli)
    plot_major_ion_comparison(
        df,
        output_path=os.path.join(fig_dir, "major_ion_comparison.png"),
        config=config,
    )

    # 5. Proporsi ion utama (100% stacked)
    plot_normalized_major_ions(
        df,
        output_path=os.path.join(fig_dir, "major_ion_normalized.png"),
        config=config,
    )

    # 6. Suhu vs SiO2
    plot_scatter_with_labels(
        df, "temperature", "sio2", "sample_id",
        output_path=os.path.join(fig_dir, "temperature_vs_sio2.png"),
        title="Hubungan Suhu dan SiO₂",
        xlabel="Suhu (°C)",
        ylabel="SiO₂ (mg/L)",
        config=config,
    )

    # 7. TDS vs Cl
    plot_scatter_with_labels(
        df, "tds", "cl", "sample_id",
        output_path=os.path.join(fig_dir, "tds_vs_chloride.png"),
        title="Hubungan TDS dan Klorida (Cl)",
        xlabel="TDS (mg/L)",
        ylabel="Cl (mg/L)",
        config=config,
    )

    # 8. Giggenbach Cl-SO₄-HCO₃ — Dataset Kimia Air
    plot_giggenbach_ternary(
        df,
        output_path=os.path.join(fig_dir, "giggenbach_ternary_ka.png"),
        config=config,
    )

    # 9. Piper diagram — Dataset Kimia Air
    plot_piper_diagram(
        df,
        output_path=os.path.join(fig_dir, "piper_ka.png"),
        config=config,
        title_suffix="Kimia Air (10 sampel)",
    )

    # 10. Na-K-√Mg ternary — Dataset Kimia Air
    plot_nakamg_ternary(
        df,
        output_path=os.path.join(fig_dir, "nakamg_ternary_ka.png"),
        config=config,
        title_suffix="Kimia Air (10 sampel)",
    )

    # 11–13. Diagram geokimia dataset Ion Balance
    if ion_balance_df is not None and len(ion_balance_df) > 0:
        plot_giggenbach_ternary(
            ion_balance_df,
            output_path=os.path.join(fig_dir, "giggenbach_ternary_ion_balance.png"),
            config=config,
        )
        plot_piper_diagram(
            ion_balance_df,
            output_path=os.path.join(fig_dir, "piper_ion_balance.png"),
            config=config,
            title_suffix="Tugas 1 Ion Balance",
        )
        plot_nakamg_ternary(
            ion_balance_df,
            output_path=os.path.join(fig_dir, "nakamg_ternary_ion_balance.png"),
            config=config,
            title_suffix="Tugas 1 Ion Balance",
        )

    # 11. Estimasi suhu reservoir — semua 14 geotermometer
    if geo_df is not None and len(geo_df) > 0:
        plot_geothermometer_summary(
            geo_df,
            output_path=os.path.join(fig_dir, "geothermometer_summary.png"),
            config=config,
        )

    if ion_balance_geo_df is not None and len(ion_balance_geo_df) > 0:
        plot_geothermometer_summary(
            ion_balance_geo_df,
            output_path=os.path.join(fig_dir, "geothermometer_summary_ion_balance.png"),
            config=config,
        )

    logger.info("Semua grafik berhasil dibuat.")

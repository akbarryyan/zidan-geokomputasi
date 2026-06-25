"""Render chartsheet Powell-Cumming dari workbook referensi asli."""

from __future__ import annotations

from pathlib import Path
import math
import shutil
import subprocess
import tempfile
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import fitz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


POWELL_CHARTS: tuple[str, ...] = (
    "Iso",
    "XClHdisch",
    "XClHqtz",
    "Xmckn",
    "Xkmc",
    "Xkms",
    "Tnkm",
    "Txyz",
    "Tcfb",
    "Tlrc",
    "Tclb",
    "Tcsh",
    "Piper",
    "Map",
)

# Kolom data pada sheet Input workbook Powell-Cumming.
INPUT_COLUMN_MAP = {
    "sample_name": "A",
    "sample_id": "D",
    "temperature": "H",
    "ph": "J",
    "li": "K",
    "na": "L",
    "k": "M",
    "ca": "N",
    "mg": "O",
    "sio2": "P",
    "b": "Q",
    "cl": "R",
    "so4": "T",
    "hco3": "U",
    "rb": "Y",
    "cs": "Z",
}

# Kolom AO-AY adalah mirror dari kolom primer (L-U) via shared INDIRECT formula.
# LibreOffice headless tidak mengevaluasi INDIRECT volatile ini saat konversi PDF,
# sehingga kolom turunan (DG, DL, dst.) yang dipakai Piper chart mendapat nilai 0
# dan menghasilkan #DIV/0!. Solusi: tulis langsung ke kolom mirror, hapus formula.
_PIPER_MIRROR_COLUMN_MAP = {
    "li": "AO",
    "na": "AP",
    "k": "AQ",
    "ca": "AR",
    "mg": "AS",
    "sio2": "AT",
    "b": "AU",
    "cl": "AV",
    "so4": "AX",
    "hco3": "AY",
}


def _find_soffice() -> str | None:
    """Cari executable LibreOffice pada Linux, macOS, atau Windows."""
    for command in ("libreoffice", "soffice", "soffice.exe"):
        found = shutil.which(command)
        if found:
            return found

    program_files = Path(__import__("os").environ.get("PROGRAMFILES", "C:/Program Files"))
    windows_path = program_files / "LibreOffice" / "program" / "soffice.exe"
    return str(windows_path) if windows_path.exists() else None


def _cell_value(value: object) -> object | None:
    """Ubah NaN pandas menjadi sel kosong Excel."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


_SHEET_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XML_NAMESPACE = {"sheet": _SHEET_NAMESPACE}
_CHART_NAMESPACE = "http://schemas.openxmlformats.org/drawingml/2006/chart"
_CHART_XML_NAMESPACE = {"chart": _CHART_NAMESPACE}


def _get_cell(row: ET.Element, coordinate: str) -> ET.Element:
    """Dapatkan sel template agar style Excel-nya tetap dipertahankan."""
    for cell in row.findall("sheet:c", _XML_NAMESPACE):
        if cell.attrib.get("r") == coordinate:
            return cell
    return ET.SubElement(row, f"{{{_SHEET_NAMESPACE}}}c", {"r": coordinate})


def _set_cell_value(cell: ET.Element, value: object | None) -> None:
    """Tulis nilai input tanpa menyentuh formula/chart bagian lain workbook."""
    for child in list(cell):
        cell.remove(child)
    if value is None:
        cell.attrib.pop("t", None)
        return
    if isinstance(value, str):
        cell.attrib["t"] = "inlineStr"
        inline = ET.SubElement(cell, f"{{{_SHEET_NAMESPACE}}}is")
        ET.SubElement(inline, f"{{{_SHEET_NAMESPACE}}}t").text = value
        return

    cell.attrib.pop("t", None)
    ET.SubElement(cell, f"{{{_SHEET_NAMESPACE}}}v").text = str(value)


def _populate_input_sheet(workbook_path: Path, dataset: pd.DataFrame) -> None:
    """Patch XML sheet Input tanpa mereserialisasi chartsheet workbook."""
    input_sheet_path = "xl/worksheets/sheet4.xml"
    workbook_path_xml = "xl/workbook.xml"

    with ZipFile(workbook_path) as archive:
        sheet_root = ET.fromstring(archive.read(input_sheet_path))
        workbook_root = ET.fromstring(archive.read(workbook_path_xml))

        rows = {
            int(row.attrib["r"]): row
            for row in sheet_root.findall("sheet:sheetData/sheet:row", _XML_NAMESPACE)
        }
        # Bersihkan data lama: kolom A-AH (1-34) dan kolom mirror Piper (AO-AY, 41-51)
        mirror_col_numbers = [_column_letter(n) for n in range(41, 52)]  # AO..AY
        for row_number in range(8, 38):
            row = rows[row_number]
            for column in range(1, 35):
                column_letter = _column_letter(column)
                _set_cell_value(_get_cell(row, f"{column_letter}{row_number}"), None)
            for col_letter in mirror_col_numbers:
                _set_cell_value(_get_cell(row, f"{col_letter}{row_number}"), None)

        # Tulis data baru
        for row_number, (_, sample) in enumerate(dataset.iterrows(), start=8):
            if row_number > 37:
                break
            row = rows[row_number]

            # Tulis semua kolom data primer
            for source_column, target_column in INPUT_COLUMN_MAP.items():
                if source_column in sample.index:
                    _set_cell_value(
                        _get_cell(row, f"{target_column}{row_number}"),
                        _cell_value(sample[source_column]),
                    )

            # Tulis mirror kolom Piper (AO-AY) langsung tanpa bergantung formula INDIRECT
            for source_column, target_column in _PIPER_MIRROR_COLUMN_MAP.items():
                if source_column in sample.index:
                    _set_cell_value(
                        _get_cell(row, f"{target_column}{row_number}"),
                        _cell_value(sample[source_column]),
                    )

            # Tulis sample_id ke kolom AH (34) untuk chart labels
            if "sample_id" in sample.index:
                _set_cell_value(
                    _get_cell(row, f"AH{row_number}"),
                    _cell_value(sample["sample_id"]),
                )

        calc_properties = workbook_root.find("sheet:calcPr", _XML_NAMESPACE)
        if calc_properties is not None:
            calc_properties.attrib.update({"calcMode": "auto", "fullCalcOnLoad": "1", "forceFullCalc": "1"})

        replacement_files = {
            input_sheet_path: ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True),
            workbook_path_xml: ET.tostring(workbook_root, encoding="utf-8", xml_declaration=True),
        }
        sample_labels = (
            dataset["sample_id"]
            .fillna(dataset["sample_name"] if "sample_name" in dataset.columns else range(len(dataset)))
            .astype(str)
            .tolist()
        )
        for entry in archive.infolist():
            if entry.filename.startswith("xl/charts/chart") and entry.filename.endswith(".xml"):
                replacement_files[entry.filename] = _enable_sample_labels(archive.read(entry.filename), sample_labels)
        temporary_path = workbook_path.with_suffix(".patched.xlsx")
        with ZipFile(temporary_path, "w", ZIP_DEFLATED) as patched:
            for entry in archive.infolist():
                patched.writestr(entry, replacement_files.get(entry.filename, archive.read(entry.filename)))

    temporary_path.replace(workbook_path)


def _enable_sample_labels(chart_xml: bytes, sample_labels: list[str]) -> bytes:
    """Ganti label per-titik di data series dengan rich text sample ID.

    Template Powell sudah punya 30 dLbl per data series yang merujuk ke
    kolom AH via strRef, tapi LibreOffice headless tidak mengevaluasi
    strRef di dalam dLbl/tx. Solusi: ganti dengan c:rich (rich text inline)
    yang didukung oleh semua versi LibreOffice.
    """
    root = ET.fromstring(chart_xml)
    text_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    c_ns = _CHART_NAMESPACE

    for series in root.findall(".//chart:ser", _CHART_XML_NAMESPACE):
        dlbls = series.find("chart:dLbls", _CHART_XML_NAMESPACE)
        if dlbls is None:
            continue

        existing_dlbls = dlbls.findall("chart:dLbl", _CHART_XML_NAMESPACE)
        # Data series selalu punya 30 dLbl individual; reference lines jauh lebih sedikit.
        if len(existing_dlbls) < 25:
            continue

        # Hapus semua dLbl lama (termasuk yang berisi strRef lama)
        for d in existing_dlbls:
            dlbls.remove(d)

        # Buat dLbl baru dengan rich text per sampel, disisipkan di awal dLbls
        for idx, label in enumerate(sample_labels):
            dlbl = ET.Element(f"{{{c_ns}}}dLbl")

            idx_el = ET.SubElement(dlbl, f"{{{c_ns}}}idx")
            idx_el.attrib["val"] = str(idx)

            # tx dengan c:rich — ini yang LibreOffice baca langsung
            tx = ET.SubElement(dlbl, f"{{{c_ns}}}tx")
            rich = ET.SubElement(tx, f"{{{c_ns}}}rich")
            ET.SubElement(rich, f"{{{text_ns}}}bodyPr")
            ET.SubElement(rich, f"{{{text_ns}}}lstStyle")
            p_el = ET.SubElement(rich, f"{{{text_ns}}}p")
            r_el = ET.SubElement(p_el, f"{{{text_ns}}}r")
            rPr = ET.SubElement(r_el, f"{{{text_ns}}}rPr")
            rPr.attrib.update({"lang": "en-US", "sz": "1000"})
            ET.SubElement(r_el, f"{{{text_ns}}}t").text = str(label)

            spPr = ET.SubElement(dlbl, f"{{{c_ns}}}spPr")
            ET.SubElement(spPr, f"{{{text_ns}}}noFill")
            ln = ET.SubElement(spPr, f"{{{text_ns}}}ln", {"w": "25400"})
            ET.SubElement(ln, f"{{{text_ns}}}noFill")

            ET.SubElement(dlbl, f"{{{c_ns}}}dLblPos", {"val": "t"})
            ET.SubElement(dlbl, f"{{{c_ns}}}showLegendKey", {"val": "0"})
            ET.SubElement(dlbl, f"{{{c_ns}}}showVal", {"val": "0"})
            ET.SubElement(dlbl, f"{{{c_ns}}}showCatName", {"val": "0"})
            ET.SubElement(dlbl, f"{{{c_ns}}}showSerName", {"val": "0"})
            ET.SubElement(dlbl, f"{{{c_ns}}}showPercent", {"val": "0"})
            ET.SubElement(dlbl, f"{{{c_ns}}}showBubbleSize", {"val": "0"})

            dlbls.insert(idx, dlbl)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _column_letter(column_number: int) -> str:
    """Kembalikan nama kolom Excel dari indeks berbasis satu."""
    name = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _append_sample_legend(image_path: Path, dataset: pd.DataFrame) -> None:
    """Tambahkan label sampel agar setiap output chart tetap dapat ditelusuri."""
    entries = [
        f"{row.sample_id} - {row.sample_name}"
        for row in dataset[["sample_id", "sample_name"]].itertuples(index=False)
    ]
    if not entries:
        return

    image = Image.open(image_path).convert("RGB")
    font = ImageFont.truetype("DejaVuSans.ttf", 16)
    title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 17)
    columns = min(3, len(entries))
    rows = math.ceil(len(entries) / columns)
    line_height = 23
    panel_height = 44 + rows * line_height
    canvas = Image.new("RGB", (image.width, image.height + panel_height), "white")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.line((28, image.height + 12, image.width - 28, image.height + 12), fill="#d7d7d7", width=1)
    draw.text((30, image.height + 20), "Sample labels", fill="#173f3b", font=title_font)

    column_width = (image.width - 60) / columns
    for index, entry in enumerate(entries):
        column = index // rows
        row = index % rows
        x = 30 + column * column_width
        y = image.height + 47 + row * line_height
        draw.text((x, y), entry, fill="#40514e", font=font)

    canvas.save(image_path)


def _render_piper_matplotlib(dataset: pd.DataFrame, output_path: Path) -> None:
    """Render Piper diagram pakai matplotlib.

    LibreOffice headless tidak bisa mengevaluasi multi-area chart series
    `(Input!$DJ$8,Input!$DO$8,Input!$DS$8)` yang dipakai template Powell-Cumming,
    sehingga Piper selalu kosong. Fungsi ini menggambar ulang diagram secara
    Python menggunakan koordinat Piper sistem Powell-Cumming (dari sheet Tgrid).

    Konstanta dari Tgrid: A46=1.3547, B42=0.2, B54=0.1732.
    Sistem koordinat:
      Kation - Ca(0,0), Na+K(1.1547,0), Mg(0.5774,1)
      Anion  - HCO3(1.3547,0), Cl(2.5094,0), SO4(1.9321,1)
      Berlian - top(1.2548,2.1732) right(1.8322,1.1732) bot(1.2548,0.1732) left(0.6774,1.1732)
    """
    # meq/L conversion factors dari mg/kg
    _CMEQ = {"na": 0.0435, "k": 0.02557, "ca": 0.0499, "mg": 0.08226}
    _AMEQ = {"cl": 0.02821, "so4": 0.02082, "hco3": 0.01639}

    GCOL = "#aaaaaa"
    GW = 0.5

    fig, ax = plt.subplots(figsize=(11, 10))
    ax.set_aspect("equal")
    ax.axis("off")

    # Garis tepi segitiga dan berlian
    for verts in [
        [[0, 0], [1.1547, 0], [0.5774, 1], [0, 0]],
        [[1.3547, 0], [2.5094, 0], [1.9321, 1], [1.3547, 0]],
        [[1.2548, 2.1732], [1.8322, 1.1732], [1.2548, 0.1732], [0.6774, 1.1732], [1.2548, 2.1732]],
    ]:
        v = np.array(verts)
        ax.plot(v[:, 0], v[:, 1], "k-", lw=1.5, zorder=3)

    # Grid per 20%
    for c in [0.2, 0.4, 0.6, 0.8]:
        # Kation: fCa=c, fNaK=c, fMg=c
        ax.plot([1.1547 * (1 - c), 0.5774 * (1 - c)], [0, 1 - c], color=GCOL, lw=GW, zorder=1)
        ax.plot([1.1547 * c, 0.5774 + 0.5773 * c], [0, 1 - c], color=GCOL, lw=GW, zorder=1)
        ax.plot([0.5774 * c, 1.1547 - 0.5773 * c], [c, c], color=GCOL, lw=GW, zorder=1)
        # Anion: fHCO3=c, fCl=c, fSO4=c
        ax.plot([2.5094 - 1.1547 * c, 1.9321 - 0.5774 * c], [0, 1 - c], color=GCOL, lw=GW, zorder=1)
        ax.plot([1.3547 + 1.1547 * c, 1.9321 + 0.5773 * c], [0, 1 - c], color=GCOL, lw=GW, zorder=1)
        ax.plot([1.3547 + 0.5774 * c, 2.5094 - 0.5773 * c], [c, c], color=GCOL, lw=GW, zorder=1)
        # Berlian
        ax.plot(
            [1.2548 + 0.5774 * c, 0.6774 + 0.5774 * c],
            [2.1732 - c, 1.1732 - c],
            color=GCOL, lw=GW, zorder=1,
        )
        ax.plot(
            [1.2548 - 0.5774 * c, 1.8322 - 0.5774 * c],
            [2.1732 - c, 1.1732 - c],
            color=GCOL, lw=GW, zorder=1,
        )

    # Label persentase di tepi bawah (tiap 20%)
    for c in [0.2, 0.4, 0.6, 0.8]:
        pct = f"{int(c * 100)}%"
        # Kation bawah: Na+K tumbuh dari kiri
        ax.text(1.1547 * c, -0.04, pct, ha="center", va="top", fontsize=6, color="gray")
        # Anion bawah: Cl tumbuh dari kiri tepi anion
        ax.text(1.3547 + 1.1547 * c, -0.04, pct, ha="center", va="top", fontsize=6, color="gray")

    # Label vertex
    fs = 11
    ax.text(-0.07, -0.05, "Ca", ha="right", va="top", fontsize=fs, fontweight="bold")
    ax.text(1.1547, -0.05, "Na+K", ha="center", va="top", fontsize=fs, fontweight="bold")
    ax.text(0.5774, 1.06, "Mg", ha="center", va="bottom", fontsize=fs, fontweight="bold")
    ax.text(1.3547, -0.11, "HCO₃", ha="center", va="top", fontsize=fs, fontweight="bold")
    ax.text(2.58, -0.05, "Cl", ha="left", va="top", fontsize=fs, fontweight="bold")
    ax.text(1.9321, 1.06, "SO₄", ha="center", va="bottom", fontsize=fs, fontweight="bold")
    # Berlian
    ax.text(1.28, 2.15, "Cl+SO₄", ha="right", va="center", fontsize=9, rotation=55)
    ax.text(1.28, 2.15, "Ca+Mg", ha="left", va="center", fontsize=9, rotation=-55)
    ax.text(1.20, 0.30, "Na+K", ha="right", va="center", fontsize=9, rotation=-55)
    ax.text(1.32, 0.30, "HCO₃", ha="left", va="center", fontsize=9, rotation=55)

    # Plot titik data
    prop_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    legend_handles = []

    for i, (_, row) in enumerate(dataset.iterrows()):
        sample_id = str(row.get("sample_id", i))
        col = prop_colors[i % len(prop_colors)]

        na = float(row.get("na") or 0)
        k = float(row.get("k") or 0)
        ca = float(row.get("ca") or 0)
        mg = float(row.get("mg") or 0)
        cl = float(row.get("cl") or 0)
        so4 = float(row.get("so4") or 0)
        hco3 = float(row.get("hco3") or 0)

        nak_meq = na * _CMEQ["na"] + k * _CMEQ["k"]
        ca_meq = ca * _CMEQ["ca"]
        mg_meq = mg * _CMEQ["mg"]
        cl_meq = cl * _AMEQ["cl"]
        so4_meq = so4 * _AMEQ["so4"]
        hco3_meq = hco3 * _AMEQ["hco3"]

        total_cat = nak_meq + ca_meq + mg_meq
        total_an = cl_meq + so4_meq + hco3_meq

        if total_cat <= 0 or total_an <= 0:
            continue

        f_nak = nak_meq / total_cat
        f_mg = mg_meq / total_cat
        f_cl = cl_meq / total_an
        f_so4 = so4_meq / total_an
        f_hco3 = hco3_meq / total_an

        # Koordinat segitiga kation
        cx = 1.1547 * f_nak + 0.5774 * f_mg
        cy = f_mg
        # Koordinat segitiga anion
        an_x = 1.3547 + 0.5774 * f_so4 + 1.1547 * f_cl
        an_y = f_so4
        # Koordinat berlian
        dx = 0.1 + 0.5774 * (2.0 + f_nak - f_hco3)
        dy = 2.1732 - f_nak - f_hco3

        for px, py in [(cx, cy), (an_x, an_y), (dx, dy)]:
            ax.plot(px, py, "o", color=col, ms=8, zorder=5, markeredgecolor="white", markeredgewidth=0.5)
            ax.annotate(
                sample_id, (px, py),
                xytext=(5, 5), textcoords="offset points",
                fontsize=8, color=col, zorder=6,
            )

        legend_handles.append(mpatches.Patch(color=col, label=sample_id))

    if legend_handles:
        ax.legend(
            handles=legend_handles, loc="upper right",
            fontsize=9, framealpha=0.9, title="Sampel", title_fontsize=9,
        )

    ax.set_title("Diagram Piper (Powell-Cumming)", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlim(-0.3, 2.85)
    ax.set_ylim(-0.15, 2.45)

    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_tcsh_matplotlib(dataset: pd.DataFrame, output_path: Path) -> None:
    """Render diagram ternary Cl-SO4-HCO3 (Tcsh) dengan matplotlib.

    LibreOffice tidak merecalculate master shared formula CI8 dan menggunakan
    cached WK template value, sehingga SK (SO4-dominant water, CI≈0.042)
    muncul di posisi salah. Koordinat dihitung ulang di Python.

    Sistem koordinat (sama dengan template):
      SO4(0,0), HCO3(1.1547,0), Cl(0.5774,1)
      CI = 0.5774*fCl + 1.1547*fHCO3
      CJ = fCl
    """
    GCOL = "#aaaaaa"
    GW = 0.5

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_aspect("equal")
    ax.axis("off")

    # --- Border (vertices dari ser0 cached data) ---
    border = np.array([[0, 0], [0.5774, 1], [1.1547, 0], [0, 0]])
    ax.plot(border[:, 0], border[:, 1], "k-", lw=1.5, zorder=3)

    # --- Grid lines setiap 10% (dihitung dari formula) ---
    for c in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        # Cl=c% horizontal lines: from SO4-Cl edge to HCO3-Cl edge
        ax.plot([0.5774 * c, 1.1547 - 0.5773 * c], [c, c], color=GCOL, lw=GW, zorder=1)
        # SO4=c% iso-lines: from bottom edge to Cl-HCO3 edge
        ax.plot([1.1547 * (1 - c), 0.5774 * (1 - c)], [0, 1 - c], color=GCOL, lw=GW, zorder=1)
        # HCO3=c% iso-lines: from bottom edge to Cl-SO4 edge
        ax.plot([1.1547 * c, 0.5774 * (1 - c) + 1.1547 * c], [0, 1 - c], color=GCOL, lw=GW, zorder=1)

    # --- Tie lines (dari ser4/5/6 cached) ---
    # Midpoints of each edge → common mixing point (≈33:34:33)
    mixing_pt = (0.5716, 0.33)
    tie_starts = [(0.2887, 0.5), (0.5774, 0.0), (0.8660, 0.5)]  # mid Cl-SO4, mid SO4-HCO3, mid Cl-HCO3
    for sx, sy in tie_starts:
        ax.plot([sx, mixing_pt[0]], [sy, mixing_pt[1]], "--", color="#999999", lw=1.0, alpha=0.8, zorder=2)

    # --- Mature field (ser7 cached: 3 vertices) ---
    mature = np.array([[0.5312, 0.92], [0.7159, 0.6], [0.8083, 0.6], [0.5312, 0.92]])
    ax.plot(mature[:, 0], mature[:, 1], "-", color="#999999", lw=1.0, alpha=0.7, zorder=2)
    ax.fill(mature[:-1, 0], mature[:-1, 1], alpha=0.06, color="gray", zorder=1)

    # --- Zone labels (chart12 ser4/5/6/7 dLbl cached text) ---
    ZCOL = "#888888"
    ZFS = 10
    # "Volcanic Waters" — anchor ser4 pt0 = Cl-SO4 midpoint (0.2887, 0.5), rot=-60° OOXML → +60° visual
    ax.text(0.26, 0.28, "Volcanic Waters", ha="center", va="center",
            fontsize=ZFS, color=ZCOL, fontweight="bold", style="italic",
            rotation=60, zorder=3)
    # "Steam Heated Waters" — anchor ser5 pt0 = SO4-HCO3 midpoint (0.5774, 0.0), rot=0
    ax.text(0.35, 0.07, "Steam Heated Waters", ha="center", va="center",
            fontsize=ZFS, color=ZCOL, fontweight="bold", style="italic",
            rotation=0, zorder=3)
    # "Peripheral Waters" — anchor ser6 pt0 = Cl-HCO3 midpoint (0.8660, 0.5), rot=+60° OOXML → -60° visual
    ax.text(0.90, 0.33, "Peripheral Waters", ha="center", va="center",
            fontsize=ZFS, color=ZCOL, fontweight="bold", style="italic",
            rotation=-60, zorder=3)
    # "Mature Waters" — anchor ser7 pt0 = (0.5312, 0.9200)
    ax.text(0.70, 0.74, "Mature Waters", ha="center", va="center",
            fontsize=9, color="#777777", fontweight="bold", style="italic",
            rotation=-30, zorder=3)

    # --- Vertex labels ---
    ax.text(0.0, -0.07, "SO₄", ha="center", va="top", fontsize=13, fontweight="bold")
    ax.text(1.1547, -0.07, "HCO₃", ha="center", va="top", fontsize=13, fontweight="bold")
    ax.text(0.5774, 1.07, "Cl", ha="center", va="bottom", fontsize=13, fontweight="bold")

    # --- Persen label pada tiap 20% di tepi ---
    for c in [0.2, 0.4, 0.6, 0.8]:
        pct = f"{int(c * 100)}%"
        # Tepi kiri (SO4→Cl): label Cl%
        ax.text(0.5774 * c - 0.04, c, pct, ha="right", va="center", fontsize=7, color="#555555")
        # Tepi kanan (HCO3→Cl): label HCO3%
        ax.text(1.1547 * c + 0.5774 * (1 - c) + 0.04, 1 - c, pct, ha="left", va="center", fontsize=7, color="#555555")
        # Tepi bawah kiri (SO4%): HCO3→SO4
        ax.text(1.1547 * (1 - c) + 0.01, -0.035, pct, ha="center", va="top", fontsize=7, color="#555555")

    # --- Plot titik data ---
    prop_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    legend_handles = []

    for i, (_, row) in enumerate(dataset.iterrows()):
        cl = float(row.get("cl") or 0)
        so4 = float(row.get("so4") or 0)
        hco3 = float(row.get("hco3") or 0)
        total = cl + so4 + hco3
        if total <= 0:
            continue

        f_cl = cl / total
        f_hco3 = hco3 / total
        ci = 0.5774 * f_cl + 1.1547 * f_hco3
        cj = f_cl

        col = prop_colors[i % len(prop_colors)]
        sample_id = str(row.get("sample_id", i))

        ax.plot(ci, cj, "D", color=col, ms=7, zorder=5, markeredgecolor="white", markeredgewidth=0.5)

        # Penempatan label: offset menjauhi tepi segitiga terdekat
        x_left_edge = 0.5774 * cj
        x_right_edge = 1.1547 - 0.5773 * cj
        margin_left = ci - x_left_edge
        margin_right = x_right_edge - ci

        if margin_left < 0.12:
            ax.annotate(sample_id, (ci, cj), xytext=(7, 0),
                        textcoords="offset points", fontsize=8, color=col, zorder=6, va="center")
        elif margin_right < 0.12:
            ax.annotate(sample_id, (ci, cj), xytext=(-7, 0),
                        textcoords="offset points", fontsize=8, color=col, zorder=6, va="center", ha="right")
        else:
            ax.annotate(sample_id, (ci, cj), xytext=(5, 6),
                        textcoords="offset points", fontsize=8, color=col, zorder=6)

        legend_handles.append(mpatches.Patch(color=col, label=sample_id))

    if legend_handles:
        ax.legend(handles=legend_handles, loc="upper right",
                  fontsize=9, framealpha=0.9, title="Sampel", title_fontsize=9)

    ax.set_title("Diagram Ternary Cl-SO₄-HCO₃ (Powell-Cumming)", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlim(-0.2, 1.4)
    ax.set_ylim(-0.18, 1.15)

    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_tclb_matplotlib(dataset: pd.DataFrame, output_path: Path) -> None:
    """Render diagram ternary Cl-Li-B (Tclb/Tlrc) dengan matplotlib.

    LibreOffice headless tidak merender dLbl strRef → label batuan (Seawater,
    Granite, Diorite, Basalt, Ultramafic, Limestone, Sandstone, Shale) hilang.
    Koordinat data dihitung ulang dari kolom cl, li, b di dataset.

    Vertices (chart11.xml ser0):
      Top      = Cl       (0.5774, 1)
      BotLeft  = 100 Li   (0,      0)
      BotRight = 25 B     (1.1547, 0)
    Formula:
      total = cl + 100*li + 25*b
      f_Cl  = cl / total    → y_tern
      f_B25 = 25*b / total
      x_tern = 0.5774*f_Cl + 1.1547*f_B25
    """
    # --- Rock reference points (chart11 ser4) ---
    _ROCKS = [
        (0.12967, 0.06417, "Granite",    ( 7,  0), "left"),
        (0.23910, 0.17335, "Diorite",    (-8,  0), "right"),
        (0.23583, 0.10673, "Basalt",     (-8, -6), "right"),
        (1.04969, 0.00000, "Ultramafic", ( 6,  0), "left"),
        (0.38493, 0.12122, "Limestone",  ( 0, -7), "center"),
        (0.69285, 0.00000, "Sandstone",  ( 0, -7), "center"),
        (0.60480, 0.00000, "Shale",      ( 0,  7), "center"),
        (0.58042, 0.99313, "Seawater",   ( 6,  0), "left"),
    ]
    # --- Boundary / trend lines (chart11 ser5 & ser6) ---
    _LINES = [
        ((0, 0), (0.81399, 0.59016), "--", "#994477", 1.2, "Diorite\ntrend"),
        ((0, 0), (0.91545, 0.41441), "--", "#994477", 1.2, "Basalt\nTrend"),
    ]

    GCOL, GW = "#aaaaaa", 0.5
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_aspect("equal")
    ax.axis("off")

    # --- Triangle border ---
    border = np.array([[0, 0], [0.5774, 1], [1.1547, 0], [0, 0]])
    ax.plot(border[:, 0], border[:, 1], "k-", lw=1.5, zorder=3)

    # --- Grid lines setiap 10% (sama dengan Tcsh/Tnkm) ---
    for c in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        ax.plot([0.5774 * c, 1.1547 - 0.5773 * c], [c, c], color=GCOL, lw=GW, zorder=1)
        ax.plot([1.1547 * (1 - c), 0.5774 * (1 - c)], [0, 1 - c], color=GCOL, lw=GW, zorder=1)
        ax.plot([1.1547 * c, 0.5774 * (1 - c) + 1.1547 * c], [0, 1 - c], color=GCOL, lw=GW, zorder=1)

    # --- Percentage labels tiap 10% ---
    for c in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        pct = f"{int(c * 100)}%"
        # Tepi kiri (100Li→Cl): label Cl%
        ax.text(0.5774 * c - 0.04, c, pct, ha="right", va="center", fontsize=7, color="#555555")
        # Tepi kanan (Cl→25B): label 25B%
        ax.text(0.5774 * (1 - c) + 1.1547 * c + 0.04, 1 - c, pct, ha="left", va="center",
                fontsize=7, color="#555555")
        # Tepi bawah: 100Li%
        ax.text(1.1547 * (1 - c), -0.035, pct, ha="center", va="top", fontsize=7, color="#555555")

    # --- Boundary / trend lines ---
    for (x0, y0), (x1, y1), ls, col, lw, _ in _LINES:
        ax.plot([x0, x1], [y0, y1], ls, color=col, lw=lw, zorder=2)

    # --- Rock reference points ---
    for rx, ry, label, xytext, ha in _ROCKS:
        ax.plot(rx, ry, "s", color="#aaaaaa", ms=6, zorder=3,
                markeredgecolor="#777777", markeredgewidth=0.6)
        ax.annotate(label, (rx, ry), xytext=xytext, textcoords="offset points",
                    fontsize=7.5, color="#555555", ha=ha, va="center", zorder=4)

    # --- Vertex labels ---
    fs = 12
    ax.text(0.5774, 1.07,  "Cl",      ha="center", va="bottom", fontsize=fs, fontweight="bold")
    ax.text(0.0,   -0.07,  "100 Li",  ha="center", va="top",    fontsize=fs, fontweight="bold")
    ax.text(1.1547, -0.07, "25 B",    ha="center", va="top",    fontsize=fs, fontweight="bold")

    # --- Plot titik data ---
    prop_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    legend_handles = []

    for i, (_, row) in enumerate(dataset.iterrows()):
        cl  = float(row.get("cl")  or 0)
        li  = float(row.get("li")  or 0)
        b   = float(row.get("b")   or 0)
        total = cl + 100.0 * li + 25.0 * b
        if total <= 0:
            continue

        f_cl  = cl / total
        f_b25 = 25.0 * b / total
        xv = 0.5774 * f_cl + 1.1547 * f_b25
        yv = f_cl

        col = prop_colors[i % len(prop_colors)]
        sample_id = str(row.get("sample_id", i))

        ax.plot(xv, yv, "D", color=col, ms=7, zorder=5,
                markeredgecolor="white", markeredgewidth=0.5)

        # Offset label menjauhi tepi terdekat
        x_left  = 0.5774 * yv
        x_right = 1.1547 - 0.5773 * yv
        if xv - x_left < 0.1:
            ax.annotate(sample_id, (xv, yv), xytext=(6, 0),
                        textcoords="offset points", fontsize=8, color=col, zorder=6, va="center")
        elif x_right - xv < 0.1:
            ax.annotate(sample_id, (xv, yv), xytext=(-6, 0),
                        textcoords="offset points", fontsize=8, color=col, zorder=6,
                        va="center", ha="right")
        else:
            ax.annotate(sample_id, (xv, yv), xytext=(4, 5),
                        textcoords="offset points", fontsize=8, color=col, zorder=6)

        legend_handles.append(mpatches.Patch(color=col, label=sample_id))

    if legend_handles:
        ax.legend(handles=legend_handles, loc="upper right", bbox_to_anchor=(1.0, 0.98),
                  fontsize=9, framealpha=0.9, title="Sampel", title_fontsize=9)

    ax.set_title("Diagram Ternary Cl-Li-B (Powell-Cumming)", fontsize=13,
                 fontweight="bold", pad=12)
    ax.set_xlim(-0.2, 1.45)
    ax.set_ylim(-0.15, 1.15)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_tlrc_matplotlib(dataset: pd.DataFrame, output_path: Path) -> None:
    """Render diagram ternary Li-Rb-Cs (Tlrc) dengan matplotlib.

    Vertices (chart10.xml ser0):
      Top      = Li     (0.5774, 1)
      BotLeft  = 4 Rb   (0,      0)
      BotRight = 10 Cs  (1.1547, 0)
    Formula:
      total  = li + 4*rb + 10*cs
      f_Li   = li / total    → y_tern
      f_10Cs = 10*cs / total
      x_tern = 0.5774*f_Li + 1.1547*f_10Cs
    """
    # --- Rock reference points (chart10 ser6) ---
    _ROCKS = [
        (0.11715, 0.05797, "Granite",  (-7,  0), "right"),
        (0.09924, 0.07813, "Basalt",   (-7, -5), "right"),
        (0.15867, 0.25954, "Shale",    (-7,  0), "right"),
        (0.89812, 0.44444, "Seawater", ( 6,  0), "left"),
    ]
    # --- Boundary lines (chart10 ser4 & ser5) ---
    _LINES = [
        ((0, 0), (0.89812, 0.44444), "--", "#994477", 1.2),
        ((0, 0), (0.71485, 0.76190), "--", "#994477", 1.2),
    ]

    GCOL, GW = "#aaaaaa", 0.5
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_aspect("equal")
    ax.axis("off")

    border = np.array([[0, 0], [0.5774, 1], [1.1547, 0], [0, 0]])
    ax.plot(border[:, 0], border[:, 1], "k-", lw=1.5, zorder=3)

    for c in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        ax.plot([0.5774 * c, 1.1547 - 0.5773 * c], [c, c], color=GCOL, lw=GW, zorder=1)
        ax.plot([1.1547 * (1 - c), 0.5774 * (1 - c)], [0, 1 - c], color=GCOL, lw=GW, zorder=1)
        ax.plot([1.1547 * c, 0.5774 * (1 - c) + 1.1547 * c], [0, 1 - c], color=GCOL, lw=GW, zorder=1)
        pct = f"{int(c * 100)}%"
        ax.text(0.5774 * c - 0.04, c, pct, ha="right", va="center", fontsize=7, color="#555555")
        ax.text(0.5774 * (1 - c) + 1.1547 * c + 0.04, 1 - c, pct,
                ha="left", va="center", fontsize=7, color="#555555")
        ax.text(1.1547 * (1 - c), -0.035, pct, ha="center", va="top", fontsize=7, color="#555555")

    for (x0, y0), (x1, y1), ls, col, lw in _LINES:
        ax.plot([x0, x1], [y0, y1], ls, color=col, lw=lw, zorder=2)

    for rx, ry, label, xytext, ha in _ROCKS:
        ax.plot(rx, ry, "s", color="#aaaaaa", ms=6, zorder=3,
                markeredgecolor="#777777", markeredgewidth=0.6)
        ax.annotate(label, (rx, ry), xytext=xytext, textcoords="offset points",
                    fontsize=7.5, color="#555555", ha=ha, va="center", zorder=4)

    fs = 12
    ax.text(0.5774, 1.07,  "Li",    ha="center", va="bottom", fontsize=fs, fontweight="bold")
    ax.text(0.0,   -0.07,  "4 Rb",  ha="center", va="top",    fontsize=fs, fontweight="bold")
    ax.text(1.1547, -0.07, "10 Cs", ha="center", va="top",    fontsize=fs, fontweight="bold")

    prop_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    legend_handles = []

    for i, (_, row) in enumerate(dataset.iterrows()):
        li  = float(row.get("li")  or 0)
        rb  = float(row.get("rb")  or 0)
        cs  = float(row.get("cs")  or 0)
        total = li + 4.0 * rb + 10.0 * cs
        if total <= 0:
            continue

        f_li  = li / total
        f_10cs = 10.0 * cs / total
        xv = 0.5774 * f_li + 1.1547 * f_10cs
        yv = f_li

        col = prop_colors[i % len(prop_colors)]
        sample_id = str(row.get("sample_id", i))

        ax.plot(xv, yv, "D", color=col, ms=7, zorder=5,
                markeredgecolor="white", markeredgewidth=0.5)

        x_left  = 0.5774 * yv
        x_right = 1.1547 - 0.5773 * yv
        if xv - x_left < 0.1:
            ax.annotate(sample_id, (xv, yv), xytext=(6, 0),
                        textcoords="offset points", fontsize=8, color=col, zorder=6, va="center")
        elif x_right - xv < 0.1:
            ax.annotate(sample_id, (xv, yv), xytext=(-6, 0),
                        textcoords="offset points", fontsize=8, color=col, zorder=6,
                        va="center", ha="right")
        else:
            ax.annotate(sample_id, (xv, yv), xytext=(4, 5),
                        textcoords="offset points", fontsize=8, color=col, zorder=6)

        legend_handles.append(mpatches.Patch(color=col, label=sample_id))

    if legend_handles:
        ax.legend(handles=legend_handles, loc="upper right", bbox_to_anchor=(1.0, 0.98),
                  fontsize=9, framealpha=0.9, title="Sampel", title_fontsize=9)

    ax.set_title("Diagram Ternary Li-Rb-Cs (Powell-Cumming)", fontsize=13,
                 fontweight="bold", pad=12)
    ax.set_xlim(-0.2, 1.45)
    ax.set_ylim(-0.15, 1.15)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_xkms_matplotlib(dataset: pd.DataFrame, output_path: Path) -> None:
    """Render diagram SiO₂ vs log(K²/Mg) (Xkms) dengan matplotlib.

    LibreOffice tidak merender label nama series (ser2='60C', ser3='80C', ...)
    sebagai text pada temperature lines karena dLbl kosong di headless mode.
    Angka suhu (60-240°C) hilang dari garis iso-suhu. Fungsi ini menggambar
    ulang seluruh diagram menggunakan cached data chart6.xml.

    Koordinat data:
      X = 2*log10(K) - log10(Mg)   [= log10(K²/Mg)]
      Y = SiO₂ (mg/kg)
    Sumbu Y dibalik: 0 di atas, 600 di bawah.
    Sumbu X di atas: 0–6.
    """
    # Shared x values untuk semua silica mineral curves
    _SX = [
        -0.089, 0.757, 1.507, 2.177, 2.779, 3.322, 3.815, 4.265,
        4.677, 5.055, 5.404, 5.726, 6.025, 6.304, 6.563, 6.806,
    ]
    # Quartz (15 pts)
    _QX = _SX[:13] + [6.304, 6.563]
    _QY = [10.183, 18.158, 30.324, 47.931, 72.312, 104.836, 146.861, 199.699,
           264.581, 342.632, 434.854, 542.113, 665.137, 804.512, 960.683]
    # Chalcedony (13 pts)
    _CHX = _SX[:13]
    _CHY = [24.710, 38.985, 58.410, 83.800, 115.890, 155.314, 202.595, 258.139,
            322.242, 395.088, 476.765, 567.270, 666.524]
    # Alpha Cristobalite (16 pts)
    _AX = _SX
    _AY = [38.469, 59.841, 88.540, 125.613, 171.977, 228.398, 295.482, 373.675,
           463.271, 564.420, 677.146, 801.360, 936.875, 1083.426, 1240.679, 1408.246]
    # Beta Cristobalite (16 pts)
    _BX = _SX
    _BY = [103.465, 146.101, 198.397, 260.715, 333.214, 415.871, 508.516, 610.855,
           722.499, 842.988, 971.813, 1108.432, 1252.286, 1402.808, 1559.437, 1721.623]
    # Amorphous Silica (16 pts)
    _AMX = _SX
    _AMY = [152.946, 211.254, 281.306, 363.257, 457.035, 562.373, 678.857, 805.960,
            943.073, 1089.535, 1244.654, 1407.725, 1578.045, 1754.924, 1937.693, 2125.710]
    # Temperature lines: (suhu°C, x_val, y_top=Quartz, y_bot=Amorphous)
    _TEMPS = [
        (60,  0.757, 18.158, 211.254),
        (80,  1.507, 30.324, 281.306),
        (100, 2.177, 47.931, 363.257),
        (120, 2.779, 72.312, 457.035),
        (140, 3.322, 104.836, 562.373),
        (160, 3.815, 146.861, 678.857),
        (180, 4.265, 199.699, 805.960),
        (200, 4.677, 264.581, 943.073),
        (220, 5.055, 342.632, 1089.535),
        (240, 5.404, 434.854, 1244.654),
    ]
    Y_MAX = 600   # batas bawah sumbu Y yang terlihat

    MG = "#888888"
    LG = "#aaaaaa"

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_xlim(0, 6)
    ax.set_ylim(Y_MAX, 0)   # Inverted: 0 di atas, 600 di bawah
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")
    ax.set_xlabel("log (K²/Mg)", fontsize=11)
    ax.set_ylabel("SiO₂ mg/kg", fontsize=11)
    ax.tick_params(axis="both", labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor("black")
        spine.set_linewidth(0.8)

    # --- Silica mineral curves (clip ke Y_MAX) ---
    def clip_curve(xs, ys, y_max=Y_MAX):
        """Kembalikan titik-titik kurva, dengan interpolasi ke y_max di batas bawah."""
        pts = []
        for i, (x, y) in enumerate(zip(xs, ys)):
            if y <= y_max:
                pts.append((x, y))
            else:
                # Kurva keluar batas bawah — interpolasi titik perpotongan dengan y=y_max
                if i > 0:
                    x0, y0 = xs[i - 1], ys[i - 1]
                    if y0 < y_max:
                        t = (y_max - y0) / (y - y0)
                        pts.append((x0 + t * (x - x0), y_max))
                break
        return pts

    curves = [
        ("Quartz",             _QX,  _QY,  MG,  1.6, 4.5, 215, -35),
        ("Chalcedony",         _CHX, _CHY, MG,  1.4, 4.5, 290, -37),
        ("Alpha\nCristobalite",_AX,  _AY,  LG,  1.2, 3.8, 285, -43),
        ("Beta\nCristobalite", _BX,  _BY,  LG,  1.1, 2.5, 340, -50),
        ("Amorphous\nSilica",  _AMX, _AMY, LG,  1.0, 1.5, 340, -55),
    ]
    for name, xs, ys, col, lw, lbl_x, lbl_y, rot in curves:
        pts = clip_curve(xs, ys)
        if len(pts) < 2:
            continue
        px, py = zip(*pts)
        ax.plot(px, py, "-", color=col, lw=lw, zorder=2)
        ax.text(lbl_x, lbl_y, name, fontsize=8, color=col,
                rotation=rot, ha="center", va="center", zorder=4,
                style="italic")

    # --- Temperature lines (vertikal, clip ke Y_MAX) ---
    for temp, x_val, y_top, y_bot in _TEMPS:
        y_clipped = min(y_bot, Y_MAX)
        ax.plot([x_val, x_val], [y_top, y_clipped], "-", color="#bbbbbb", lw=0.8, zorder=1)
        # Label di tengah bagian garis yang terlihat, rotasi ~72° mengikuti referensi
        y_vis_mid = (y_top + y_clipped) / 2
        ax.text(x_val, y_vis_mid, str(temp), fontsize=7.5, color="#777777",
                rotation=72, va="center", ha="center", zorder=4)

    # --- Plot titik data ---
    prop_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    legend_handles = []

    for i, (_, row) in enumerate(dataset.iterrows()):
        k = float(row.get("k") or 0)
        mg = float(row.get("mg") or 0)
        sio2 = float(row.get("sio2") or 0)

        if k <= 0 or mg <= 0 or sio2 <= 0:
            continue

        xv = 2 * math.log10(k) - math.log10(mg)
        yv = sio2

        col = prop_colors[i % len(prop_colors)]
        sample_id = str(row.get("sample_id", i))

        ax.plot(xv, yv, "D", color=col, ms=7, zorder=5,
                markeredgecolor="white", markeredgewidth=0.5)
        ax.annotate(sample_id, (xv, yv), xytext=(5, 5),
                    textcoords="offset points", fontsize=8, color=col, zorder=6)
        legend_handles.append(mpatches.Patch(color=col, label=sample_id))

    if legend_handles:
        ax.legend(handles=legend_handles, loc="lower right",
                  fontsize=9, framealpha=0.9, title="Sampel", title_fontsize=9)

    ax.set_title("Diagram Xkms (Powell-Cumming)", fontsize=13, fontweight="bold", pad=14)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_xkmc_matplotlib(dataset: pd.DataFrame, output_path: Path) -> None:
    """Render diagram log(K²/Ca) vs log(K²/Mg) (Xkmc) dengan matplotlib.

    LibreOffice tidak merender dLbls suhu pada ser10 'Equilibration line'
    karena strRef di dalam dLbl tidak dievaluasi oleh headless renderer.
    Label suhu (80-340°C) dan tick mark hilang. Fungsi ini menggambar ulang
    seluruh diagram menggunakan cached data dari chart5.xml.

    Koordinat data:
      X = 2*log10(K) - log10(Mg)   [= log10(K²/Mg)]
      Y = 2*log10(K) - log10(Ca)   [= log10(K²/Ca)]
    Sumbu Y dibalik: -1 di atas, 5 di bawah.
    Sumbu X di atas: 0–7.
    """
    # Shared x values (18 pts, dipakai semua kurva kecuali CaCO3)
    _X18 = [
        -0.089, 0.757, 1.507, 2.177, 2.779, 3.322, 3.815, 4.265,
        4.677, 5.055, 5.404, 5.726, 6.025, 6.304, 6.563, 6.806,
        7.247, 7.636,
    ]
    # Equilibration line y values (16 pts = 40-340°C setiap 20°)
    _EQ_Y = [
        -0.1080, 0.2280, 0.5640, 0.9000, 1.2360, 1.5720, 1.9080, 2.2440,
        2.5800, 2.9160, 3.2520, 3.5880, 3.9240, 4.2600, 4.5960, 4.9320,
    ]
    # rCO2 vapor y values (18 pts each, offset sederhana: setiap +1 = 1 log-decade)
    _RV0001 = [  # rCO2v = 0.0001
        -2.033, -1.640, -1.292, -0.981, -0.701, -0.449, -0.220, -0.011,
        0.180, 0.356, 0.518, 0.668, 0.807, 0.936, 1.056, 1.169, 1.374, 1.555,
    ]
    # rCO2 liquid y values (17 pts)
    _RL00001 = [  # rCO2liq = 0.00001
        1.290, 1.465, 1.595, 1.687, 1.748, 1.782, 1.793, 1.783,
        1.756, 1.713, 1.657, 1.588, 1.509, 1.420, 1.322, 1.216, 0.984,
    ]
    # CaCO3 saturation limit (x=0..7, y dari ser11)
    _C_X = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    _C_Y = [0.3, 0.82, 1.39, 1.98, 2.68, 3.51, 4.5, 5.62]
    # Rocks (ser8): 8 titik
    _ROCK_X = [5.489, 4.100, 3.850, 2.492, 2.057, 4.991, 4.641, 2.055]
    _ROCK_Y = [5.063, 3.845, 3.608, 3.357, 1.325, 4.292, 4.817, 2.558]
    _ROCK_LABELS = ["Shale", "Basalt", "Diorite", "Ultramafic", "Limestone", "Sandstone", "", "Seawater"]

    LG = "#c0c0c0"   # light gray (rCO2 vapor)
    MG = "#888888"   # medium gray (rCO2 liquid, CaCO3)
    DG = "#555555"   # dark gray (equilibration line)

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_xlim(0, 7)
    ax.set_ylim(5, -1)   # Inverted Y
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")
    ax.set_xlabel("log(K²/Mg)", fontsize=11)
    ax.set_ylabel("log(K²/Ca)", fontsize=11)
    ax.tick_params(axis="both", labelsize=9)
    ax.grid(color="#e0e0e0", linewidth=0.4, zorder=0)

    # Secondary Y axis (kanan): Log(P_CO2) bar = Y_left - 3
    ax2 = ax.twinx()
    ax2.set_ylim(5 - 3, -1 - 3)   # 2 to -4, inverted
    ax2.set_ylabel("Log(P$_{CO_2}$) bar", fontsize=10)
    ax2.tick_params(axis="y", labelsize=8)

    # --- rCO2 vapor curves (4 visible curves: 0.0001, 0.001, 0.01, 0.1) ---
    for j, (label, offset) in enumerate([
        ("0.0001", 0.0), ("0.001", 1.0), ("0.01", 2.0), ("0.1", 3.0)
    ]):
        yvs = [y + offset for y in _RV0001]
        # Filter ke range -1..5
        pts = [(x, y) for x, y in zip(_X18, yvs) if -1 <= y <= 5 and x >= 0]
        if len(pts) < 2:
            continue
        px, py = zip(*pts)
        ax.plot(px, py, "-", color=LG, lw=0.9, zorder=1)
        # Label di ujung kanan kurva
        ax.text(px[-1] + 0.05, py[-1], label, fontsize=7, color="#999999",
                ha="left", va="center", zorder=4)

    # rCO2 vapor 0.00001 → terlalu tinggi (y < -1 semua), taruh sebagai text annotation
    ax.text(6.8, -0.9, "r$_{CO₂}$ vapor\n= 0.00001", fontsize=7, color="#bbbbbb",
            ha="right", va="top", zorder=4, style="italic")

    # --- rCO2 liquid curves (4 curves: 0.00001, 0.0001, 0.001, 0.01) ---
    for j, (label, offset) in enumerate([
        ("0.00001", 0.0), ("0.0001", 1.0), ("0.001", 2.0), ("0.01", 3.0)
    ]):
        yvs = [y + offset for y in _RL00001]
        x_liq = _X18[:17]
        pts = [(x, y) for x, y in zip(x_liq, yvs) if -1 <= y <= 5 and x >= 0]
        if len(pts) < 2:
            continue
        px, py = zip(*pts)
        ax.plot(px, py, "-", color=MG, lw=1.1, zorder=2)
        # Label di ujung kiri (awal kurva)
        ax.text(px[0] - 0.08, py[0], label, fontsize=7, color="#777777",
                ha="right", va="center", zorder=4)

    # "rCO2 liquid = 0.01" label (dari ser7 dLbl, di kurva terbawah)
    rco2liq_y7 = [y + 3.0 for y in _RL00001]
    liq_visible = [(x, y) for x, y in zip(_X18[:17], rco2liq_y7) if -1 <= y <= 5 and x >= 0]
    if liq_visible:
        lx, ly = liq_visible[len(liq_visible)//3]
        ax.text(lx + 0.1, ly + 0.1, "rCO₂ liquid = 0.01",
                fontsize=7.5, color="#777777", ha="left", va="bottom", zorder=4, style="italic")

    # --- CaCO3 saturation limit (Immature Waters boundary) ---
    ax.plot(_C_X, _C_Y, "-", color=MG, lw=1.8, zorder=3)
    # "Immature Waters" label di tengah garis
    ax.text(1.8, 2.0, "Immature\nWaters", fontsize=10, color=MG,
            ha="center", va="center", zorder=4, style="italic",
            rotation=-38)

    # --- Equilibration line (16 pts, suhu 40-340°C setiap 20°) ---
    eq_x = _X18[:16]
    ax.plot(eq_x, _EQ_Y, "-", color=DG, lw=1.8, zorder=4)

    # Temperature labels (80-340°C = pt2-pt15)
    temp_range = list(range(40, 341, 20))  # 16 suhu: 40,60,...,340
    n = len(eq_x)
    for i, (ex, ey, temp) in enumerate(zip(eq_x, _EQ_Y, temp_range)):
        if temp < 80:   # skip 40 dan 60 (off-chart area)
            continue
        if not (-1 <= ey <= 5):
            continue
        # Arah normal (perpendicular ke tangent)
        dx = eq_x[min(i + 1, n - 1)] - eq_x[max(i - 1, 0)]
        dy = _EQ_Y[min(i + 1, n - 1)] - _EQ_Y[max(i - 1, 0)]
        length = math.sqrt(dx**2 + dy**2)
        if length > 0:
            px, py = -dy / length, dx / length
        else:
            px, py = -1, 0
        # Tick mark
        scale = 0.06
        ax.plot([ex - px * scale * 0.4, ex + px * scale * 0.4],
                [ey - py * scale * 0.4, ey + py * scale * 0.4],
                "-", color=DG, lw=1.0, zorder=5)
        # Label di sisi kiri/atas garis (arah px,py ke "luar")
        ax.text(ex + px * scale, ey + py * scale, str(temp),
                fontsize=7, color="#444444", ha="center", va="center", zorder=5)

    # --- Rock compositions ---
    ax.plot(_ROCK_X, _ROCK_Y, "s", color="#aaaaaa", ms=6, zorder=3,
            markeredgecolor="#888888", markeredgewidth=0.5)
    for rx, ry, label in zip(_ROCK_X, _ROCK_Y, _ROCK_LABELS):
        if not label:
            continue
        offset_x = -0.12 if rx > 3 else 0.12
        ha = "right" if rx > 3 else "left"
        ax.text(rx + offset_x, ry, label, fontsize=7, color="#666666",
                ha=ha, va="center", zorder=4)

    # --- Plot data points ---
    prop_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    legend_handles = []

    for i, (_, row) in enumerate(dataset.iterrows()):
        k = float(row.get("k") or 0)
        ca = float(row.get("ca") or 0)
        mg = float(row.get("mg") or 0)

        if k <= 0 or ca <= 0 or mg <= 0:
            continue

        xv = 2 * math.log10(k) - math.log10(mg)
        yv = 2 * math.log10(k) - math.log10(ca)

        col = prop_colors[i % len(prop_colors)]
        sample_id = str(row.get("sample_id", i))

        ax.plot(xv, yv, "D", color=col, ms=7, zorder=6,
                markeredgecolor="white", markeredgewidth=0.5)
        ax.annotate(sample_id, (xv, yv), xytext=(5, 5),
                    textcoords="offset points", fontsize=8, color=col, zorder=7)
        legend_handles.append(mpatches.Patch(color=col, label=sample_id))

    if legend_handles:
        ax.legend(handles=legend_handles, loc="lower right",
                  fontsize=9, framealpha=0.9, title="Sampel", title_fontsize=9)

    ax.set_title("Diagram Xkmc (Powell-Cumming)", fontsize=13, fontweight="bold", pad=14)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_xmckn_matplotlib(dataset: pd.DataFrame, output_path: Path) -> None:
    """Render diagram 10Mg/(10Mg+Ca) vs 10K/(10K+Na) (Xmckn) dengan matplotlib.

    LibreOffice tidak merender dLbls suhu pada ser0 'Equilibration line'
    karena strRef di dalam dLbl tidak dievaluasi oleh headless renderer.
    Label suhu (40-340°C) hilang dari output LibreOffice. Fungsi ini
    menggambar ulang diagram secara Python menggunakan cached curve data.

    Koordinat data:
      X = 10*K / (10*K + Na)
      Y = 10*Mg / (10*Mg + Ca)
    """
    # Cached equilibration curve dari chart4.xml ser0 (16 pts = suhu 40-340°C setiap 20°)
    _EQ_X = [
        0.01997, 0.03629, 0.06096, 0.09547, 0.14041, 0.19505, 0.25739, 0.32449,
        0.39306, 0.46009, 0.52327, 0.58109, 0.63284, 0.67840, 0.71805, 0.75230,
    ]
    _EQ_Y = [
        0.90550, 0.74745, 0.53272, 0.34577, 0.22280, 0.15097, 0.11017, 0.08701,
        0.07413, 0.06773, 0.06590, 0.06783, 0.07338, 0.08293, 0.09734, 0.11793,
    ]
    _TEMPS = list(range(40, 341, 20))  # 40, 60, 80, ..., 340

    # Rock compositions dari chart4.xml ser1 (8 pts)
    _ROCK_X = [0.9267, 0.8571, 0.8370, 0.9524, 0.9677, 0.8917, 0.9694, 0.2646]
    _ROCK_Y = [0.7895, 0.8475, 0.8514, 0.9865, 0.6497, 0.6667, 0.9375, 0.9695]
    _ROCK_LABELS = [
        "Granite", "Diorite", "Basalt", "Ultramafic",
        "Limestone", "Sandstone", "Shale", "Seawater",
    ]

    GCOL = "#bbbbbb"

    fig, ax = plt.subplots(figsize=(9, 8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    # Grid dan frame
    ax.set_xticks([i / 10 for i in range(11)])
    ax.set_yticks([i / 10 for i in range(11)])
    ax.tick_params(axis="both", which="major", labelsize=9, color="#888888")
    for spine in ax.spines.values():
        spine.set_edgecolor("black")
        spine.set_linewidth(0.8)
    ax.grid(color=GCOL, linewidth=0.5, zorder=0)

    # Interpolasi kurva supaya lebih halus (parametric cubic spline)
    t = np.linspace(0, 1, len(_EQ_X))
    t_fine = np.linspace(0, 1, 200)
    eq_x_fine = np.interp(t_fine, t, _EQ_X)
    eq_y_fine = np.interp(t_fine, t, _EQ_Y)
    ax.plot(eq_x_fine, eq_y_fine, "-", color="#888888", lw=1.5, zorder=2)

    # Label suhu pada setiap titik kurva equilibration
    n = len(_EQ_X)
    for i, (ex, ey, temp) in enumerate(zip(_EQ_X, _EQ_Y, _TEMPS)):
        # Hitung arah tangent → rotasi 90° untuk offset label
        dx = _EQ_X[min(i + 1, n - 1)] - _EQ_X[max(i - 1, 0)]
        dy = _EQ_Y[min(i + 1, n - 1)] - _EQ_Y[max(i - 1, 0)]
        length = math.sqrt(dx**2 + dy**2)
        if length > 0:
            # Perpendicular ke kiri-atas (sisi luar kurva)
            px, py = -dy / length, dx / length
        else:
            px, py = -1, 0
        offset_scale = 0.035
        lx = ex + px * offset_scale
        ly = ey + py * offset_scale

        # Tick mark kecil pada kurva
        ax.plot(
            [ex - px * 0.01, ex + px * 0.01],
            [ey - py * 0.01, ey + py * 0.01],
            "-", color="#666666", lw=1.0, zorder=3,
        )
        ax.text(lx, ly, str(temp), fontsize=7, color="#555555",
                ha="center", va="center", zorder=4)

    # Rock compositions (kotak abu-abu)
    ax.plot(_ROCK_X, _ROCK_Y, "s", color="#aaaaaa", ms=7, zorder=3,
            markeredgecolor="#777777", markeredgewidth=0.6)
    for rx, ry, label in zip(_ROCK_X, _ROCK_Y, _ROCK_LABELS):
        if label == "Seawater":
            # Seawater di kiri — label ke kanan
            ax.text(rx + 0.02, ry, label, fontsize=8, color="#555555",
                    ha="left", va="center", zorder=4)
        else:
            # Sisanya di kanan — label ke kiri
            ax.text(rx - 0.02, ry, label, fontsize=7.5, color="#555555",
                    ha="right", va="center", zorder=4)

    # Plot titik data: X = 10K/(10K+Na), Y = 10Mg/(10Mg+Ca)
    prop_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    legend_handles = []

    for i, (_, row) in enumerate(dataset.iterrows()):
        na = float(row.get("na") or 0)
        k = float(row.get("k") or 0)
        mg = float(row.get("mg") or 0)
        ca = float(row.get("ca") or 0)

        denom_x = 10 * k + na
        denom_y = 10 * mg + ca
        if denom_x <= 0 or denom_y <= 0:
            continue

        xv = 10 * k / denom_x
        yv = 10 * mg / denom_y

        col = prop_colors[i % len(prop_colors)]
        sample_id = str(row.get("sample_id", i))

        ax.plot(xv, yv, "D", color=col, ms=7, zorder=5,
                markeredgecolor="white", markeredgewidth=0.5)
        ax.annotate(sample_id, (xv, yv), xytext=(5, 5),
                    textcoords="offset points", fontsize=8, color=col, zorder=6)

        legend_handles.append(mpatches.Patch(color=col, label=sample_id))

    if legend_handles:
        ax.legend(handles=legend_handles, loc="upper right",
                  fontsize=9, framealpha=0.9, title="Sampel", title_fontsize=9)

    ax.set_xlabel("10K/(10K+Na)", fontsize=11)
    ax.set_ylabel("10Mg/(10Mg+Ca)", fontsize=11)
    ax.set_title("Diagram Xmckn (Powell-Cumming)", fontsize=13, fontweight="bold", pad=12)

    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_tnkm_matplotlib(dataset: pd.DataFrame, output_path: Path) -> None:
    """Render diagram Na-K-Mg (Tnkm/Giggenbach) dengan matplotlib.

    LibreOffice merender ser5 'immature waters' (smooth=1, 20 titik) sebagai
    arc besar yang menutupi seluruh triangle sehingga hasilnya berbentuk 'telur'.
    Root cause: chart7 menggunakan auto-scaling y-axis sehingga kurva immature
    waters (y=0.03..0.21) terskalakan bersama border triangle dan menciptakan
    lensa/oval. Fungsi ini merender ulang semuanya di Python.

    Sistem koordinat (sama dengan Tcsh/Piper):
      10K(0,0), Na(0.5774,1), 1000Mg^0.5(1.1547,0)
      CV = 0.5774*fNa + 1.1547*fMg
      CW = fNa
      di mana fNa = Na/(Na + 10K + 1000*sqrt(Mg))
    """
    # --- Cached reference data dari chart7.xml ---
    _EQ_X = [
        0.9171498147198196, 0.8595425451643106, 0.7991584195216674,
        0.7361291883260157, 0.6707911216354944, 0.6040949410971223,
        0.5376374980555422, 0.47335047425979726, 0.4130537322447537,
        0.35809973118058736, 0.3092242734738054, 0.2665872637740825,
        0.22991901120695982, 0.19868904907255372, 0.17224815623346354,
        0.1310955014616011, 0.10172442892211928, 0.05100847536181945, 0.0,
    ]
    _EQ_Y = [
        0.38266370734539784, 0.45251951830257164, 0.5085132160925431,
        0.5464985816334215, 0.5645868805227473, 0.5632626800240091,
        0.5451215460891163, 0.5141909339315602, 0.4750174254513152,
        0.4318292797326502, 0.3880055920722196, 0.3458994331429842,
        0.30692092911833335, 0.27174583175858663, 0.24054507825546234,
        0.18934527129758802, 0.15074970869021823, 0.07958927660396693, 0.0,
    ]
    _IM_X = [
        1.1341606610179338, 1.1247579334986173, 1.1122815123748109,
        1.0957852825924117, 1.0740301574525846, 1.0455628552042115,
        1.0089339351956852, 0.9630520569097378, 0.9076000164724758,
        0.8433635967085213, 0.7723052149165287, 0.697298154136594,
        0.6215959884469195, 0.5482399038354984, 0.47961269447337357,
        0.41724341948175275, 0.31346610138629116, 0.23604780938123918,
        0.10389603939018321, 0.0,
    ]
    _IM_Y = [
        0.03418508835989417, 0.04823293300945094, 0.06503374139054016,
        0.08426275313230742, 0.10532496128060537, 0.1273326505966691,
        0.14911701770744962, 0.1693044427638325, 0.1864778157238158,
        0.1994080239740335, 0.20729250425793086, 0.20991078566897028,
        0.20763172047963263, 0.20127500288574654, 0.19189336813770325,
        0.18056004678120552, 0.15561055171717295, 0.13151924311182928,
        0.07577545465426647, 0.0,
    ]
    _TEMPS = [
        (60,  [0.9171498147198196, 1.1247579334986173], [0.38266370734539784, 0.04823293300945094]),
        (80,  [0.8595425451643106, 1.1122815123748109], [0.45251951830257164, 0.06503374139054016]),
        (100, [0.7991584195216674, 1.0957852825924117], [0.5085132160925431,  0.08426275313230742]),
        (120, [0.7361291883260157, 1.0740301574525846], [0.5464985816334215,  0.10532496128060537]),
        (140, [0.6707911216354944, 1.0455628552042115], [0.5645868805227473,  0.1273326505966691]),
        (160, [0.6040949410971223, 1.0089339351956852], [0.5632626800240091,  0.14911701770744962]),
        (180, [0.5376374980555422, 0.9630520569097378], [0.5451215460891163,  0.1693044427638325]),
        (200, [0.47335047425979726, 0.9076000164724758], [0.5141909339315602, 0.1864778157238158]),
        (220, [0.4130537322447537, 0.8433635967085213], [0.4750174254513152,  0.1994080239740335]),
        (240, [0.35809973118058736, 0.7723052149165287], [0.4318292797326502, 0.20729250425793086]),
        (260, [0.3092242734738054, 0.697298154136594],  [0.3880055920722196,  0.20991078566897028]),
        (280, [0.2665872637740825, 0.6215959884469195], [0.3458994331429842,  0.20763172047963263]),
        (300, [0.22991901120695982, 0.5482399038354984], [0.30692092911833335, 0.20127500288574654]),
        (320, [0.19868904907255372, 0.47961269447337357], [0.27174583175858663, 0.19189336813770325]),
        (340, [0.17224815623346354, 0.41724341948175275], [0.24054507825546234, 0.18056004678120552]),
    ]
    _ROCK_X = [0.20144, 0.54673, 0.62304, 0.97869, 1.04185, 0.30466, 0.37773, 0.94511]
    _ROCK_Y = [0.06279, 0.08100, 0.08171, 0.00744, 0.00320, 0.08427, 0.02092, 0.21111]
    _ROCK_LABELS = ["Granite", "Sandstone", "Shale", "Diorite\nBasalt", "Ultramafic", "", "", "Limestone"]

    GCOL = "#aaaaaa"
    GW = 0.5

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_aspect("equal")
    ax.axis("off")

    # --- Border segitiga ---
    border = np.array([[0, 0], [0.5774, 1], [1.1547, 0], [0, 0]])
    ax.plot(border[:, 0], border[:, 1], "k-", lw=1.5, zorder=3)

    # --- Grid setiap 10% (formula equilateral triangle) ---
    for c in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        # Horizontal (K%): from K-Na edge to K-Mg edge
        ax.plot([0.5774 * c, 1.1547 - 0.5773 * c], [c, c], color=GCOL, lw=GW, zorder=1)
        # Na% iso-lines: from K-Mg base to Na-Mg edge
        ax.plot([1.1547 * (1 - c), 0.5774 * (1 - c)], [0, 1 - c], color=GCOL, lw=GW, zorder=1)
        # Mg% iso-lines: from K-Na base to Na-Mg edge
        ax.plot([1.1547 * c, 0.5774 * (1 - c) + 1.1547 * c], [0, 1 - c], color=GCOL, lw=GW, zorder=1)

    # --- Equilibration curve (ser4, smooth=1) ---
    ax.plot(_EQ_X, _EQ_Y, "k-", lw=1.2, zorder=2)

    # --- Immature waters boundary (ser5, smooth=1) ---
    ax.plot(_IM_X, _IM_Y, "k-", lw=1.2, zorder=2)

    # --- Temperature lines dengan label ---
    for temp, xs, ys in _TEMPS:
        ax.plot(xs, ys, color="#888888", lw=0.7, zorder=2)
        # Label di tengah garis
        mx = (xs[0] + xs[1]) / 2
        my = (ys[0] + ys[1]) / 2
        ax.text(mx + 0.01, my, str(temp), fontsize=6.5, color="#666666",
                ha="left", va="center", zorder=4)

    # --- Rock compositions (ser21, 8 titik, marker kotak) ---
    ax.plot(_ROCK_X, _ROCK_Y, "s", color="#aaaaaa", ms=6, zorder=3,
            markeredgecolor="#777777", markeredgewidth=0.6)
    for rx, ry, label in zip(_ROCK_X, _ROCK_Y, _ROCK_LABELS):
        if label:
            ax.text(rx, ry - 0.025, label, ha="center", va="top",
                    fontsize=6.5, color="#555555", zorder=4)

    # --- Zone labels ---
    ax.text(0.32, 0.55, "Partial Equilibration", ha="center", va="center",
            fontsize=10, color="#444444", style="italic", zorder=4)
    ax.text(0.74, 0.10, "Immature Waters", ha="center", va="center",
            fontsize=10, color="#444444", style="italic", zorder=4)

    # --- Vertex labels ---
    fs = 11
    ax.text(0.0, -0.06, "10 K", ha="center", va="top", fontsize=fs, fontweight="bold")
    ax.text(0.5774, 1.07, "Na", ha="center", va="bottom", fontsize=fs, fontweight="bold")
    ax.text(1.1547, -0.06, "1000 Mg^0.5", ha="center", va="top", fontsize=fs, fontweight="bold")

    # --- Plot titik data ---
    prop_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    legend_handles = []

    for i, (_, row) in enumerate(dataset.iterrows()):
        na = float(row.get("na") or 0)
        k = float(row.get("k") or 0)
        mg = float(row.get("mg") or 0)

        mg_sqrt = math.sqrt(max(mg, 0))
        total = na + 10 * k + 1000 * mg_sqrt
        if total <= 0:
            continue

        f_na = na / total
        f_mg = 1000 * mg_sqrt / total

        cv = 0.5774 * f_na + 1.1547 * f_mg
        cw = f_na

        col = prop_colors[i % len(prop_colors)]
        sample_id = str(row.get("sample_id", i))

        ax.plot(cv, cw, "D", color=col, ms=7, zorder=5,
                markeredgecolor="white", markeredgewidth=0.5)

        # Penempatan label: menjauhi tepi terdekat
        x_left = 0.5774 * cw
        x_right = 1.1547 - 0.5773 * cw
        margin_left = cv - x_left
        margin_right = x_right - cv

        if margin_left < 0.10:
            ax.annotate(sample_id, (cv, cw), xytext=(7, 0),
                        textcoords="offset points", fontsize=8, color=col, zorder=6, va="center")
        elif margin_right < 0.10:
            ax.annotate(sample_id, (cv, cw), xytext=(-7, 0),
                        textcoords="offset points", fontsize=8, color=col, zorder=6,
                        va="center", ha="right")
        else:
            ax.annotate(sample_id, (cv, cw), xytext=(5, 6),
                        textcoords="offset points", fontsize=8, color=col, zorder=6)

        legend_handles.append(mpatches.Patch(color=col, label=sample_id))

    if legend_handles:
        ax.legend(handles=legend_handles, loc="upper right",
                  fontsize=9, framealpha=0.9, title="Sampel", title_fontsize=9)

    ax.set_title("Diagram Na-K-Mg (Powell-Cumming / Giggenbach)", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlim(-0.2, 1.4)
    ax.set_ylim(-0.18, 1.15)

    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_powell_charts(
    dataset: pd.DataFrame,
    dataset_slug: str,
    template_path: str | Path,
    figures_directory: str | Path,
    reports_directory: str | Path,
) -> list[Path]:
    """Buat PNG chartsheet Powell-Cumming untuk satu dataset.

    LibreOffice membuka salinan workbook agar formula dan chartsheet asli
    dihitung ulang. Semua output berasal dari template tanpa memodifikasinya.
    """
    soffice = _find_soffice()
    if soffice is None:
        raise RuntimeError(
            "LibreOffice tidak ditemukan. Instal LibreOffice agar diagram "
            "Powell-Cumming dapat dirender."
        )

    template = Path(template_path)
    if not template.exists():
        raise FileNotFoundError(f"Workbook referensi tidak ditemukan: {template}")

    figures_dir = Path(figures_directory)
    reports_dir = Path(reports_directory)
    figures_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    output_workbook = reports_dir / f"powell_{dataset_slug}_input.xlsx"
    with tempfile.TemporaryDirectory(prefix="powell-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        populated_workbook = temp_dir / template.name
        shutil.copy2(template, populated_workbook)
        _populate_input_sheet(populated_workbook, dataset)
        shutil.copy2(populated_workbook, output_workbook)

        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temp_dir),
                str(populated_workbook),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        pdf_path = temp_dir / f"{populated_workbook.stem}.pdf"
        if not pdf_path.exists():
            raise RuntimeError("LibreOffice tidak menghasilkan PDF chartsheet Powell-Cumming.")

        rendered_paths: list[Path] = []
        with fitz.open(pdf_path) as document:
            if len(document) < len(POWELL_CHARTS):
                raise RuntimeError("PDF Powell-Cumming tidak memuat seluruh chartsheet referensi.")
            for page_index, chart_name in enumerate(POWELL_CHARTS):
                output_path = figures_dir / f"powell_{dataset_slug}_{chart_name.lower()}.png"
                if chart_name == "Piper":
                    # LibreOffice tidak dapat merender multi-area chart series yang dipakai
                    # template Piper Powell-Cumming. Gunakan matplotlib langsung.
                    _render_piper_matplotlib(dataset, output_path)
                elif chart_name == "Tcsh":
                    # LibreOffice menggunakan cached value dari master shared formula CI8
                    # (WK template data) bukan recalculate dari data kita, sehingga SK
                    # muncul di posisi salah. Gunakan matplotlib langsung.
                    _render_tcsh_matplotlib(dataset, output_path)
                elif chart_name == "Xkms":
                    # LibreOffice tidak merender nama series suhu ('60C', '80C', ...)
                    # sebagai label pada iso-temperature lines di chart6 (Xkms).
                    # Angka suhu 60-240°C hilang. Gunakan matplotlib langsung.
                    _render_xkms_matplotlib(dataset, output_path)
                elif chart_name == "Xmckn":
                    # LibreOffice tidak merender dLbls suhu pada 'Equilibration line'
                    # (strRef di dLbl diabaikan oleh headless renderer). Label 40-340°C
                    # hilang. Gunakan matplotlib langsung.
                    _render_xmckn_matplotlib(dataset, output_path)
                elif chart_name == "Xkmc":
                    # LibreOffice tidak merender dLbls suhu pada 'Equilibration line'
                    # chart5 (chart Xkmc). Fungsi ini menggambar ulang seluruh diagram
                    # termasuk kurva rCO2 vapor/liquid dan label suhu 80-340°C.
                    _render_xkmc_matplotlib(dataset, output_path)
                elif chart_name == "Tnkm":
                    # LibreOffice merender ser5 'immature waters' (smooth=1) sebagai
                    # arc besar yang membentuk 'telur' karena auto-scaling y-axis chart7
                    # tidak dikunci. Gunakan matplotlib langsung.
                    _render_tnkm_matplotlib(dataset, output_path)
                elif chart_name == "Tclb":
                    # LibreOffice tidak merender dLbl strRef → label batuan (Seawater,
                    # Granite, Diorite, Basalt, Ultramafic, Limestone, Sandstone, Shale)
                    # hilang dari diagram Cl-Li-B (chart11). Gunakan matplotlib langsung.
                    _render_tclb_matplotlib(dataset, output_path)
                elif chart_name == "Tlrc":
                    # LibreOffice tidak merender dLbl strRef → label batuan (Granite,
                    # Basalt, Shale, Seawater) hilang dari diagram Li-Rb-Cs (chart10).
                    # Gunakan matplotlib langsung.
                    _render_tlrc_matplotlib(dataset, output_path)
                else:
                    pixmap = document[page_index].get_pixmap(matrix=fitz.Matrix(1.75, 1.75), alpha=False)
                    pixmap.save(output_path)
                    _append_sample_legend(output_path, dataset)
                rendered_paths.append(output_path)

    return rendered_paths

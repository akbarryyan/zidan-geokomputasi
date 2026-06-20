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
    ax.text(1.2548, 2.22, "Ca+Mg", ha="center", va="bottom", fontsize=9)
    ax.text(1.88, 1.1732, "Cl+SO₄", ha="left", va="center", fontsize=9)
    ax.text(0.62, 1.1732, "HCO₃", ha="right", va="center", fontsize=9)
    ax.text(1.2548, 0.12, "Na+K", ha="center", va="top", fontsize=9)

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
        ax.plot([sx, mixing_pt[0]], [sy, mixing_pt[1]], "b--", lw=0.8, alpha=0.6, zorder=2)

    # --- Mature field (ser7 cached: 3 vertices) ---
    mature = np.array([[0.5312, 0.92], [0.7159, 0.6], [0.8083, 0.6], [0.5312, 0.92]])
    ax.plot(mature[:, 0], mature[:, 1], "b-", lw=1.0, alpha=0.5, zorder=2)
    ax.fill(mature[:-1, 0], mature[:-1, 1], alpha=0.08, color="blue", zorder=1)
    ax.text(0.82, 0.63, "Mature\nWater", ha="left", va="bottom", fontsize=7, color="blue", alpha=0.7)

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
                else:
                    pixmap = document[page_index].get_pixmap(matrix=fitz.Matrix(1.75, 1.75), alpha=False)
                    pixmap.save(output_path)
                    _append_sample_legend(output_path, dataset)
                rendered_paths.append(output_path)

    return rendered_paths

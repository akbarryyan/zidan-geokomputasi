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
        for row_number in range(8, 38):
            row = rows[row_number]
            for column in range(1, 33):
                column_letter = _column_letter(column)
                _set_cell_value(_get_cell(row, f"{column_letter}{row_number}"), None)

        for row_number, (_, sample) in enumerate(dataset.iterrows(), start=8):
            if row_number > 37:
                break
            row = rows[row_number]
            for source_column, target_column in INPUT_COLUMN_MAP.items():
                if source_column in sample.index:
                    _set_cell_value(
                        _get_cell(row, f"{target_column}{row_number}"),
                        _cell_value(sample[source_column]),
                    )

        calc_properties = workbook_root.find("sheet:calcPr", _XML_NAMESPACE)
        if calc_properties is not None:
            calc_properties.attrib.update({"calcMode": "auto", "fullCalcOnLoad": "1", "forceFullCalc": "1"})

        replacement_files = {
            input_sheet_path: ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True),
            workbook_path_xml: ET.tostring(workbook_root, encoding="utf-8", xml_declaration=True),
        }
        for entry in archive.infolist():
            if entry.filename.startswith("xl/charts/chart") and entry.filename.endswith(".xml"):
                replacement_files[entry.filename] = _enable_sample_labels(archive.read(entry.filename))
        temporary_path = workbook_path.with_suffix(".patched.xlsx")
        with ZipFile(temporary_path, "w", ZIP_DEFLATED) as patched:
            for entry in archive.infolist():
                patched.writestr(entry, replacement_files.get(entry.filename, archive.read(entry.filename)))

    temporary_path.replace(workbook_path)


def _enable_sample_labels(chart_xml: bytes) -> bytes:
    """Aktifkan legenda sampel pada chartsheet tanpa mengubah garis referensi."""
    root = ET.fromstring(chart_xml)
    for series in root.findall(".//chart:ser", _CHART_XML_NAMESPACE):
        formulas = [
            formula.text or ""
            for formula in series.findall(".//chart:f", _CHART_XML_NAMESPACE)
        ]
        if not any("Input!$AH$" in formula for formula in formulas):
            continue
        if series.find("chart:dLbls", _CHART_XML_NAMESPACE) is not None:
            continue

        labels = ET.Element(f"{{{_CHART_NAMESPACE}}}dLbls")
        ET.SubElement(labels, f"{{{_CHART_NAMESPACE}}}showLegendKey", {"val": "0"})
        ET.SubElement(labels, f"{{{_CHART_NAMESPACE}}}showVal", {"val": "0"})
        ET.SubElement(labels, f"{{{_CHART_NAMESPACE}}}showCatName", {"val": "0"})
        ET.SubElement(labels, f"{{{_CHART_NAMESPACE}}}showSerName", {"val": "1"})
        ET.SubElement(labels, f"{{{_CHART_NAMESPACE}}}showPercent", {"val": "0"})
        ET.SubElement(labels, f"{{{_CHART_NAMESPACE}}}showLeaderLines", {"val": "1"})
        series.append(labels)

    chart = root.find("chart:chart", _CHART_XML_NAMESPACE)
    if chart is not None and chart.find("chart:legend", _CHART_XML_NAMESPACE) is None:
        legend = ET.Element(f"{{{_CHART_NAMESPACE}}}legend")
        ET.SubElement(legend, f"{{{_CHART_NAMESPACE}}}legendPos", {"val": "r"})
        ET.SubElement(legend, f"{{{_CHART_NAMESPACE}}}overlay", {"val": "0"})
        plot_area = chart.find("chart:plotArea", _CHART_XML_NAMESPACE)
        insert_at = list(chart).index(plot_area) + 1 if plot_area is not None else 0
        chart.insert(insert_at, legend)

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
                pixmap = document[page_index].get_pixmap(matrix=fitz.Matrix(1.75, 1.75), alpha=False)
                pixmap.save(output_path)
                _append_sample_legend(output_path, dataset)
                rendered_paths.append(output_path)

    return rendered_paths

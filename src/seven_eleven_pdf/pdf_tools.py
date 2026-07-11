from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

POINTS_PER_MM = 72 / 25.4
PAPER_SIZES_MM = {
    "a2": (420, 594),
    "a3": (297, 420),
    "a4": (210, 297),
    "a5": (148, 210),
    "a6": (105, 148),
    "a7": (74, 105),
}


class GhostscriptMissingError(RuntimeError):
    """Raised when the Ghostscript executable is unavailable."""


class PopplerMissingError(RuntimeError):
    """Raised when Poppler PDF rendering tools are unavailable."""


def compress_pdf(input_path: Path, output_path: Path, dpi: int, grayscale: bool) -> None:
    if shutil.which("gs") is None:
        raise GhostscriptMissingError("gs was not found on PATH")

    command = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dPDFSETTINGS=/ebook",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        f"-dColorImageResolution={dpi}",
        f"-dGrayImageResolution={dpi}",
        f"-dMonoImageResolution={dpi}",
    ]
    if grayscale:
        command.extend(
            [
                "-sColorConversionStrategy=Gray",
                "-sProcessColorModel=DeviceGray",
            ]
        )
    command.extend(
        [
            f"-sOutputFile={output_path}",
            str(input_path),
        ]
    )

    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Ghostscript failed: {message}")


def count_pages(input_path: Path) -> int:
    return len(PdfReader(input_path).pages)


def write_page_range(input_path: Path, output_path: Path, start: int, end: int) -> None:
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page_index in range(start, end + 1):
        writer.add_page(reader.pages[page_index])
    with output_path.open("wb") as file:
        writer.write(file)


def rasterize_pdf(
    input_path: Path,
    output_dir: Path,
    dpi: int,
    grayscale: bool,
    jpeg_quality: int,
) -> list[Path]:
    if shutil.which("pdftoppm") is None:
        raise PopplerMissingError("pdftoppm was not found on PATH")

    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "page"
    command = [
        "pdftoppm",
        "-r",
        str(dpi),
        "-jpeg",
        "-jpegopt",
        f"quality={jpeg_quality},optimize=y,progressive=n",
    ]
    if grayscale:
        command.append("-gray")
    command.extend([str(input_path), str(prefix)])

    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"pdftoppm failed: {message}")

    pages = sorted(output_dir.glob("page-*.jpg"), key=_page_number)
    if not pages:
        raise RuntimeError("pdftoppm did not render any pages")
    return pages


def write_images_as_pdf(
    images: list[Path],
    output_path: Path,
    dpi: int,
    jpeg_quality: int,
    grayscale: bool,
    paper_size: str,
    layout: str,
) -> None:
    page_width, page_height = page_size_for_layout(paper_size, layout)
    columns, rows = grid_for_layout(layout)
    per_sheet = columns * rows
    slot_width = page_width / columns
    slot_height = page_height / rows
    margin = min(page_width, page_height) * 0.015

    pdf = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))
    for sheet_start in range(0, len(images), per_sheet):
        sheet_images = images[sheet_start : sheet_start + per_sheet]
        for slot_index, image_path in enumerate(sheet_images):
            column = slot_index % columns
            row = slot_index // columns
            slot_x = column * slot_width
            slot_y = page_height - ((row + 1) * slot_height)
            inner_width = slot_width - (2 * margin)
            inner_height = slot_height - (2 * margin)

            with Image.open(image_path) as image:
                image_width, image_height = image.size
            scale = min(inner_width / image_width, inner_height / image_height)
            draw_width = image_width * scale
            draw_height = image_height * scale
            x = slot_x + margin + ((inner_width - draw_width) / 2)
            y = slot_y + margin + ((inner_height - draw_height) / 2)
            pdf.drawImage(
                str(image_path),
                x,
                y,
                width=draw_width,
                height=draw_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        pdf.showPage()
    pdf.save()


def paper_size_points(name: str) -> tuple[float, float]:
    width_mm, height_mm = PAPER_SIZES_MM[name]
    return width_mm * POINTS_PER_MM, height_mm * POINTS_PER_MM


def page_size_for_layout(paper_size: str, layout: str) -> tuple[float, float]:
    width, height = paper_size_points(paper_size)
    if layout == "landscape-2up":
        return height, width
    return width, height


def grid_for_layout(layout: str) -> tuple[int, int]:
    if layout == "landscape-2up":
        return 2, 1
    if layout == "portrait-4up":
        return 2, 2
    return 1, 1


def _page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.jpg$", path.name)
    if match is None:
        return 0
    return int(match.group(1))

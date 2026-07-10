from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter


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
) -> None:
    mode = "L" if grayscale else "RGB"
    opened = [Image.open(image).convert(mode) for image in images]
    try:
        first, rest = opened[0], opened[1:]
        first.save(
            output_path,
            "PDF",
            save_all=True,
            append_images=rest,
            resolution=dpi,
            quality=jpeg_quality,
        )
    finally:
        for image in opened:
            image.close()


def _page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.jpg$", path.name)
    if match is None:
        return 0
    return int(match.group(1))

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader, PdfWriter


class GhostscriptMissingError(RuntimeError):
    """Raised when the Ghostscript executable is unavailable."""


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

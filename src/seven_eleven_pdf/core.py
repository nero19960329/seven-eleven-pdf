from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from seven_eleven_pdf.pdf_tools import (
    GhostscriptMissingError,
    PopplerMissingError,
    compress_pdf,
    count_pages,
    rasterize_pdf,
    write_images_as_pdf,
    write_page_range,
)

BYTES_PER_MB = 1_000_000


class PdfPrepError(Exception):
    """Raised when a PDF cannot be prepared for printing."""


@dataclass(frozen=True)
class PrepResult:
    input_path: Path
    output_dir: Path
    files: tuple[Path, ...]
    strategy: str
    max_bytes: int


def max_bytes_from_mb(value: float) -> int:
    if value <= 0:
        raise PdfPrepError("--max-size-mb must be greater than 0")
    return int(value * BYTES_PER_MB)


def page_ranges_for_limit(
    page_count: int,
    max_bytes: int,
    range_size: Callable[[int, int], int],
) -> list[tuple[int, int]]:
    """Return inclusive zero-based page ranges where each rendered range fits."""
    if page_count <= 0:
        raise PdfPrepError("input PDF has no pages")

    ranges: list[tuple[int, int]] = []
    start = 0
    while start < page_count:
        low = start
        high = page_count - 1
        best: int | None = None

        while low <= high:
            mid = (low + high) // 2
            size = range_size(start, mid)
            if size <= max_bytes:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        if best is None:
            raise PdfPrepError(
                f"page {start + 1} is larger than the configured limit after compression"
            )

        ranges.append((start, best))
        start = best + 1

    return ranges


def prepare_for_print(
    input_path: Path,
    output_dir: Path | None = None,
    max_size_mb: float = 10.0,
    dpi: int = 150,
    grayscale: bool = True,
    strategy: str = "compress",
    raster_dpi: int = 72,
    jpeg_quality: int = 35,
    paper_size: str = "a4",
) -> PrepResult:
    input_path = input_path.expanduser().resolve()
    if not input_path.is_file():
        raise PdfPrepError(f"input file does not exist: {input_path}")
    if input_path.suffix.lower() != ".pdf":
        raise PdfPrepError("input file must be a .pdf")
    if dpi <= 0:
        raise PdfPrepError("--dpi must be greater than 0")
    if strategy not in {"compress", "raster"}:
        raise PdfPrepError("--strategy must be either 'compress' or 'raster'")
    if raster_dpi <= 0:
        raise PdfPrepError("--raster-dpi must be greater than 0")
    if not 1 <= jpeg_quality <= 95:
        raise PdfPrepError("--jpeg-quality must be between 1 and 95")
    if paper_size.lower() not in {"a2", "a3", "a4", "a5", "a6", "a7"}:
        raise PdfPrepError("--paper-size must be one of: a2, a3, a4, a5, a6, a7")

    max_bytes = max_bytes_from_mb(max_size_mb)
    output_dir = (
        output_dir.expanduser().resolve()
        if output_dir is not None
        else input_path.with_name(f"{input_path.stem}_print")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        return _prepare_with_temp_files(
            input_path=input_path,
            output_dir=output_dir,
            max_bytes=max_bytes,
            dpi=dpi,
            grayscale=grayscale,
            strategy=strategy,
            raster_dpi=raster_dpi,
            jpeg_quality=jpeg_quality,
            paper_size=paper_size.lower(),
        )
    except GhostscriptMissingError as exc:
        raise PdfPrepError(
            "Ghostscript is required. Install it with `brew install ghostscript` "
            "on macOS, then run the command again."
        ) from exc
    except PopplerMissingError as exc:
        raise PdfPrepError(
            "Poppler is required for --strategy raster. Install it with "
            "`brew install poppler` on macOS, then run the command again."
        ) from exc


def _prepare_with_temp_files(
    input_path: Path,
    output_dir: Path,
    max_bytes: int,
    dpi: int,
    grayscale: bool,
    strategy: str,
    raster_dpi: int,
    jpeg_quality: int,
    paper_size: str,
) -> PrepResult:
    with tempfile.TemporaryDirectory(prefix="seven-eleven-pdf-") as temp_name:
        temp_dir = Path(temp_name)
        if strategy == "raster":
            return _prepare_raster(
                input_path=input_path,
                output_dir=output_dir,
                max_bytes=max_bytes,
                temp_dir=temp_dir,
                grayscale=grayscale,
                raster_dpi=raster_dpi,
                jpeg_quality=jpeg_quality,
                paper_size=paper_size,
            )

        compressed = temp_dir / "compressed.pdf"
        compress_pdf(input_path, compressed, dpi=dpi, grayscale=grayscale)

        single_output = output_dir / f"{input_path.stem}_print.pdf"
        if compressed.stat().st_size <= max_bytes:
            shutil.copy2(compressed, single_output)
            return PrepResult(
                input_path=input_path,
                output_dir=output_dir,
                files=(single_output,),
                strategy="grayscale-compress" if grayscale else "color-compress",
                max_bytes=max_bytes,
            )

        page_count = count_pages(compressed)

        def render_range_size(start: int, end: int) -> int:
            candidate = temp_dir / f"candidate-{start + 1}-{end + 1}.pdf"
            write_page_range(compressed, candidate, start, end)
            return candidate.stat().st_size

        ranges = page_ranges_for_limit(page_count, max_bytes, render_range_size)
        width = len(str(len(ranges)))
        files: list[Path] = []
        for index, (start, end) in enumerate(ranges, start=1):
            output = output_dir / f"{input_path.stem}_part-{index:0{width}d}.pdf"
            write_page_range(compressed, output, start, end)
            files.append(output)

    return PrepResult(
        input_path=input_path,
        output_dir=output_dir,
        files=tuple(files),
        strategy="grayscale-compress-and-split" if grayscale else "color-compress-and-split",
        max_bytes=max_bytes,
    )


def _prepare_raster(
    input_path: Path,
    output_dir: Path,
    max_bytes: int,
    temp_dir: Path,
    grayscale: bool,
    raster_dpi: int,
    jpeg_quality: int,
    paper_size: str,
) -> PrepResult:
    pages = rasterize_pdf(
        input_path=input_path,
        output_dir=temp_dir / "pages",
        dpi=raster_dpi,
        grayscale=grayscale,
        jpeg_quality=jpeg_quality,
    )

    def render_range_size(start: int, end: int) -> int:
        candidate = temp_dir / f"raster-candidate-{start + 1}-{end + 1}.pdf"
        write_images_as_pdf(
            pages[start : end + 1],
            candidate,
            dpi=raster_dpi,
            jpeg_quality=jpeg_quality,
            grayscale=grayscale,
            paper_size=paper_size,
        )
        return candidate.stat().st_size

    ranges = page_ranges_for_limit(len(pages), max_bytes, render_range_size)
    if len(ranges) == 1:
        output = output_dir / f"{input_path.stem}_raster.pdf"
        write_images_as_pdf(
            pages,
            output,
            dpi=raster_dpi,
            jpeg_quality=jpeg_quality,
            grayscale=grayscale,
            paper_size=paper_size,
        )
        files = (output,)
    else:
        width = len(str(len(ranges)))
        rendered: list[Path] = []
        for index, (start, end) in enumerate(ranges, start=1):
            output = output_dir / f"{input_path.stem}_raster_part-{index:0{width}d}.pdf"
            write_images_as_pdf(
                pages[start : end + 1],
                output,
                dpi=raster_dpi,
                jpeg_quality=jpeg_quality,
                grayscale=grayscale,
                paper_size=paper_size,
            )
            rendered.append(output)
        files = tuple(rendered)

    color = "grayscale" if grayscale else "color"
    return PrepResult(
        input_path=input_path,
        output_dir=output_dir,
        files=files,
        strategy=f"{color}-raster-{paper_size}-{raster_dpi}dpi-q{jpeg_quality}",
        max_bytes=max_bytes,
    )

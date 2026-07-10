from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from seven_eleven_pdf.pdf_tools import (
    GhostscriptMissingError,
    compress_pdf,
    count_pages,
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
) -> PrepResult:
    input_path = input_path.expanduser().resolve()
    if not input_path.is_file():
        raise PdfPrepError(f"input file does not exist: {input_path}")
    if input_path.suffix.lower() != ".pdf":
        raise PdfPrepError("input file must be a .pdf")
    if dpi <= 0:
        raise PdfPrepError("--dpi must be greater than 0")

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
        )
    except GhostscriptMissingError as exc:
        raise PdfPrepError(
            "Ghostscript is required. Install it with `brew install ghostscript` "
            "on macOS, then run the command again."
        ) from exc


def _prepare_with_temp_files(
    input_path: Path,
    output_dir: Path,
    max_bytes: int,
    dpi: int,
    grayscale: bool,
) -> PrepResult:
    with tempfile.TemporaryDirectory(prefix="seven-eleven-pdf-") as temp_name:
        temp_dir = Path(temp_name)
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

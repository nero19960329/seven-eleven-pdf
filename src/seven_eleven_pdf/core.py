from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from seven_eleven_pdf.pdf_tools import (
    GhostscriptMissingError,
    PopplerMissingError,
    compress_pdf,
    count_pages,
    merge_pdfs,
    rasterize_pdf,
    write_images_as_pdf,
    write_page_range,
)

BYTES_PER_MB = 1_000_000


class PdfPrepError(Exception):
    """Raised when a PDF cannot be prepared for printing."""


@dataclass(frozen=True)
class PrepResult:
    input_paths: tuple[Path, ...]
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
    input_paths: Path | Sequence[Path],
    output_dir: Path | None = None,
    max_size_mb: float = 10.0,
    dpi: int = 150,
    grayscale: bool = True,
    strategy: str = "compress",
    raster_dpi: int = 72,
    jpeg_quality: int = 35,
    paper_size: str = "a4",
    layout: str = "single",
    fit: str = "contain",
    margin_mm: float = 4.0,
) -> PrepResult:
    resolved_inputs = _resolve_input_paths(input_paths)
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
    allowed_layouts = {
        "single",
        "landscape-2up",
        "landscape-4up",
        "landscape-8up",
        "portrait-4up",
    }
    if layout not in allowed_layouts:
        raise PdfPrepError(
            "--layout must be one of: single, landscape-2up, landscape-4up, "
            "landscape-8up, portrait-4up"
        )
    if strategy != "raster" and layout != "single":
        raise PdfPrepError("--layout requires --strategy raster")
    if fit not in {"contain", "stretch"}:
        raise PdfPrepError("--fit must be one of: contain, stretch")
    if strategy != "raster" and fit != "contain":
        raise PdfPrepError("--fit requires --strategy raster")
    if margin_mm < 0:
        raise PdfPrepError("--margin-mm must be greater than or equal to 0")

    max_bytes = max_bytes_from_mb(max_size_mb)
    output_dir = (
        output_dir.expanduser().resolve()
        if output_dir is not None
        else resolved_inputs[0].with_name(f"{_output_stem(resolved_inputs)}_print")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        return _prepare_with_temp_files(
            input_paths=resolved_inputs,
            output_dir=output_dir,
            max_bytes=max_bytes,
            dpi=dpi,
            grayscale=grayscale,
            strategy=strategy,
            raster_dpi=raster_dpi,
            jpeg_quality=jpeg_quality,
            paper_size=paper_size.lower(),
            layout=layout,
            fit=fit,
            margin_mm=margin_mm,
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


def _resolve_input_paths(input_paths: Path | Sequence[Path]) -> tuple[Path, ...]:
    paths = (input_paths,) if isinstance(input_paths, Path) else tuple(input_paths)
    if not paths:
        raise PdfPrepError("at least one input PDF is required")

    resolved = tuple(path.expanduser().resolve() for path in paths)
    for path in resolved:
        if not path.is_file():
            raise PdfPrepError(f"input file does not exist: {path}")
        if path.suffix.lower() != ".pdf":
            raise PdfPrepError("input file must be a .pdf")
    return resolved


def _output_stem(input_paths: tuple[Path, ...]) -> str:
    if len(input_paths) == 1:
        return input_paths[0].stem
    return "combined"


def _prepare_with_temp_files(
    input_paths: tuple[Path, ...],
    output_dir: Path,
    max_bytes: int,
    dpi: int,
    grayscale: bool,
    strategy: str,
    raster_dpi: int,
    jpeg_quality: int,
    paper_size: str,
    layout: str,
    fit: str,
    margin_mm: float,
) -> PrepResult:
    with tempfile.TemporaryDirectory(prefix="seven-eleven-pdf-") as temp_name:
        temp_dir = Path(temp_name)
        if strategy == "raster":
            return _prepare_raster(
                input_paths=input_paths,
                output_dir=output_dir,
                max_bytes=max_bytes,
                temp_dir=temp_dir,
                grayscale=grayscale,
                raster_dpi=raster_dpi,
                jpeg_quality=jpeg_quality,
                paper_size=paper_size,
                layout=layout,
                fit=fit,
                margin_mm=margin_mm,
            )

        source = _merged_source(input_paths, temp_dir)
        compressed = temp_dir / "compressed.pdf"
        compress_pdf(source, compressed, dpi=dpi, grayscale=grayscale)

        stem = _output_stem(input_paths)
        single_output = output_dir / f"{stem}_print.pdf"
        if compressed.stat().st_size <= max_bytes:
            shutil.copy2(compressed, single_output)
            return PrepResult(
                input_paths=input_paths,
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
            output = output_dir / f"{stem}_part-{index:0{width}d}.pdf"
            write_page_range(compressed, output, start, end)
            files.append(output)

    return PrepResult(
        input_paths=input_paths,
        output_dir=output_dir,
        files=tuple(files),
        strategy="grayscale-compress-and-split" if grayscale else "color-compress-and-split",
        max_bytes=max_bytes,
    )


def _merged_source(input_paths: tuple[Path, ...], temp_dir: Path) -> Path:
    if len(input_paths) == 1:
        return input_paths[0]
    merged = temp_dir / "merged.pdf"
    merge_pdfs(input_paths, merged)
    return merged


def _prepare_raster(
    input_paths: tuple[Path, ...],
    output_dir: Path,
    max_bytes: int,
    temp_dir: Path,
    grayscale: bool,
    raster_dpi: int,
    jpeg_quality: int,
    paper_size: str,
    layout: str,
    fit: str,
    margin_mm: float,
) -> PrepResult:
    pages: list[Path] = []
    for index, input_path in enumerate(input_paths, start=1):
        pages.extend(
            rasterize_pdf(
                input_path=input_path,
                output_dir=temp_dir / f"pages-{index}",
                dpi=raster_dpi,
                grayscale=grayscale,
                jpeg_quality=jpeg_quality,
            )
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
            layout=layout,
            fit=fit,
            margin_mm=margin_mm,
        )
        return candidate.stat().st_size

    ranges = page_ranges_for_limit(len(pages), max_bytes, render_range_size)
    stem = _output_stem(input_paths)
    if len(ranges) == 1:
        output = output_dir / f"{stem}_raster.pdf"
        write_images_as_pdf(
            pages,
            output,
            dpi=raster_dpi,
            jpeg_quality=jpeg_quality,
            grayscale=grayscale,
            paper_size=paper_size,
            layout=layout,
            fit=fit,
            margin_mm=margin_mm,
        )
        files = (output,)
    else:
        width = len(str(len(ranges)))
        rendered: list[Path] = []
        for index, (start, end) in enumerate(ranges, start=1):
            output = output_dir / f"{stem}_raster_part-{index:0{width}d}.pdf"
            write_images_as_pdf(
                pages[start : end + 1],
                output,
                dpi=raster_dpi,
                jpeg_quality=jpeg_quality,
                grayscale=grayscale,
                paper_size=paper_size,
                layout=layout,
                fit=fit,
                margin_mm=margin_mm,
            )
            rendered.append(output)
        files = tuple(rendered)

    color = "grayscale" if grayscale else "color"
    return PrepResult(
        input_paths=input_paths,
        output_dir=output_dir,
        files=files,
        strategy=f"{color}-raster-{paper_size}-{layout}-{fit}-{raster_dpi}dpi-q{jpeg_quality}",
        max_bytes=max_bytes,
    )

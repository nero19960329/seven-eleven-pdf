from __future__ import annotations

from pathlib import Path

import pytest

from seven_eleven_pdf.core import PdfPrepError, max_bytes_from_mb, page_ranges_for_limit


def test_max_bytes_from_mb_uses_decimal_megabytes() -> None:
    assert max_bytes_from_mb(10) == 10_000_000
    assert max_bytes_from_mb(1.5) == 1_500_000


def test_max_bytes_from_mb_rejects_non_positive_values() -> None:
    with pytest.raises(PdfPrepError, match="greater than 0"):
        max_bytes_from_mb(0)


def test_page_ranges_for_limit_keeps_largest_ranges_under_limit() -> None:
    page_sizes = [4, 4, 4, 7, 3]

    def range_size(start: int, end: int) -> int:
        return sum(page_sizes[start : end + 1])

    assert page_ranges_for_limit(5, 10, range_size) == [(0, 1), (2, 2), (3, 4)]


def test_page_ranges_for_limit_rejects_single_page_over_limit() -> None:
    page_sizes = [4, 20]

    def range_size(start: int, end: int) -> int:
        return sum(page_sizes[start : end + 1])

    with pytest.raises(PdfPrepError, match="page 2"):
        page_ranges_for_limit(2, 10, range_size)


def test_page_ranges_for_limit_rejects_empty_pdf() -> None:
    with pytest.raises(PdfPrepError, match="no pages"):
        page_ranges_for_limit(0, 10, lambda _start, _end: 0)


def test_input_suffix_validation(tmp_path: Path) -> None:
    from seven_eleven_pdf.core import prepare_for_print

    text_file = tmp_path / "sample.txt"
    text_file.write_text("not a pdf")

    with pytest.raises(PdfPrepError, match=r"\.pdf"):
        prepare_for_print(text_file)


def test_raster_option_validation(tmp_path: Path) -> None:
    from seven_eleven_pdf.core import prepare_for_print

    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n")

    with pytest.raises(PdfPrepError, match="--strategy"):
        prepare_for_print(pdf_file, strategy="unknown")

    with pytest.raises(PdfPrepError, match="--raster-dpi"):
        prepare_for_print(pdf_file, strategy="raster", raster_dpi=0)

    with pytest.raises(PdfPrepError, match="--jpeg-quality"):
        prepare_for_print(pdf_file, strategy="raster", jpeg_quality=0)

    with pytest.raises(PdfPrepError, match="--paper-size"):
        prepare_for_print(pdf_file, strategy="raster", paper_size="letter")

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from seven_eleven_pdf import __version__
from seven_eleven_pdf.core import PdfPrepError, prepare_for_print


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seven-eleven-pdf",
        description=(
            "Compress and split a PDF into files small enough for 7-Eleven "
            "printing. The default output is grayscale and each part is under "
            "10 MB."
        ),
    )
    parser.add_argument("input", type=Path, help="Input .pdf file")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for generated PDFs (default: <input stem>_print)",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=10.0,
        help="Maximum size per output PDF in decimal MB (default: 10)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="Image resolution used by Ghostscript downsampling (default: 150)",
    )
    parser.add_argument(
        "--keep-color",
        action="store_true",
        help="Keep color output instead of converting to grayscale",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = prepare_for_print(
            input_path=args.input,
            output_dir=args.output_dir,
            max_size_mb=args.max_size_mb,
            dpi=args.dpi,
            grayscale=not args.keep_color,
        )
    except PdfPrepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"strategy: {result.strategy}")
    print(f"output directory: {result.output_dir}")
    for file in result.files:
        print(file)
    return 0

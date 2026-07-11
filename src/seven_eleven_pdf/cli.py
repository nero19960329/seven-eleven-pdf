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
    parser.add_argument("input", type=Path, nargs="+", help="Input .pdf file(s)")
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
        "--strategy",
        choices=["compress", "raster"],
        default="compress",
        help=(
            "PDF preparation strategy. Use raster for smaller, blurrier A4 print "
            "files (default: compress)."
        ),
    )
    parser.add_argument(
        "--raster-dpi",
        type=int,
        default=72,
        help="Raster rendering resolution used with --strategy raster (default: 72)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=35,
        help="JPEG quality used with --strategy raster, 1-95 (default: 35)",
    )
    parser.add_argument(
        "--paper-size",
        choices=["a2", "a3", "a4", "a5", "a6", "a7"],
        default="a4",
        help="Output paper size used with --strategy raster (default: a4)",
    )
    parser.add_argument(
        "--layout",
        choices=[
            "single",
            "landscape-2up",
            "landscape-4up",
            "landscape-8up",
            "portrait-4up",
        ],
        default="single",
        help=("Raster page layout: one page per sheet, landscape n-up, or portrait four-up"),
    )
    parser.add_argument(
        "--fit",
        choices=["contain", "stretch"],
        default="contain",
        help="How raster pages fit inside each layout slot (default: contain)",
    )
    parser.add_argument(
        "--margin-mm",
        type=float,
        default=4.0,
        help="Margin around each raster layout slot in millimeters (default: 4)",
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
            input_paths=args.input,
            output_dir=args.output_dir,
            max_size_mb=args.max_size_mb,
            dpi=args.dpi,
            grayscale=not args.keep_color,
            strategy=args.strategy,
            raster_dpi=args.raster_dpi,
            jpeg_quality=args.jpeg_quality,
            paper_size=args.paper_size,
            layout=args.layout,
            fit=args.fit,
            margin_mm=args.margin_mm,
        )
    except PdfPrepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"strategy: {result.strategy}")
    print(f"output directory: {result.output_dir}")
    for file in result.files:
        print(file)
    return 0

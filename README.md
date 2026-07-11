# seven-eleven-pdf

`seven-eleven-pdf` prepares a PDF for convenience-store printing systems that reject
large uploads. It converts the document to grayscale by default, compresses or
rasterizes it, and splits it into PDF parts smaller than a configurable size limit.

The default limit is 10 MB per output file.

## Strategy

The tool uses one conservative default strategy, `compress`:

1. Convert and compress the full PDF with Ghostscript.
2. Use grayscale output by default, because printed handouts usually do not need
   color and grayscale typically reduces upload size.
3. If the compressed PDF is below the limit, write a single output file.
4. If it is still too large, split the already-compressed PDF by page ranges.
   Each part is chosen with a binary search for the largest page range that fits
   under the size limit.
5. If a single page is still over the limit after compression, fail with a clear
   error instead of producing an invalid upload.

This favors predictable print quality and small output files over aggressive
rasterization. Rasterizing every page can shrink difficult files, but it often
damages text sharpness and makes searchable PDFs worse.

For files that need to be smaller and can tolerate blur, use `--strategy raster`.
This renders every page to a grayscale JPEG, places it on a real output paper
size, and rebuilds the PDF before splitting it. It is useful for A4 print
handouts where upload size matters more than text searchability.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Ghostscript available as `gs`
- Poppler available as `pdftoppm` when using `--strategy raster`

On macOS:

```sh
brew install ghostscript poppler uv
```

On Ubuntu:

```sh
sudo apt-get update
sudo apt-get install ghostscript poppler-utils
```

## Installation

From a checkout:

```sh
uv sync
uv run seven-eleven-pdf --help
```

As a tool from Git:

```sh
uv tool install git+https://github.com/nero19960329/seven-eleven-pdf.git
```

## Usage

Prepare `document.pdf` with the default grayscale, 10 MB limit:

```sh
seven-eleven-pdf document.pdf
```

Write outputs to a specific directory:

```sh
seven-eleven-pdf document.pdf --output-dir ./print-ready
```

Use a different size limit:

```sh
seven-eleven-pdf document.pdf --max-size-mb 9.5
```

Keep color:

```sh
seven-eleven-pdf document.pdf --keep-color
```

Increase image downsampling resolution:

```sh
seven-eleven-pdf document.pdf --dpi 200
```

Create a blurrier A4-oriented version:

```sh
seven-eleven-pdf document.pdf --strategy raster --raster-dpi 72 --jpeg-quality 35
```

Make the raster output smaller and blurrier:

```sh
seven-eleven-pdf document.pdf --strategy raster --raster-dpi 60 --jpeg-quality 28
```

Choose a different supported paper size:

```sh
seven-eleven-pdf document.pdf --strategy raster --paper-size a3
```

Put two source pages on each landscape A4 output sheet:

```sh
seven-eleven-pdf document.pdf --strategy raster --paper-size a4 --layout landscape-2up
```

Put four source pages on each landscape A3 output sheet:

```sh
seven-eleven-pdf document.pdf --strategy raster --paper-size a3 --layout landscape-4up
```

Put four source pages on each portrait A4 output sheet:

```sh
seven-eleven-pdf document.pdf --strategy raster --paper-size a4 --layout portrait-4up
```

## Development

```sh
uv sync --dev
uv run pre-commit install
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## License

MIT

from __future__ import annotations

from seven_eleven_pdf.cli import main


def test_cli_returns_error_for_missing_input(capsys) -> None:
    assert main(["missing.pdf"]) == 1
    captured = capsys.readouterr()
    assert "input file does not exist" in captured.err

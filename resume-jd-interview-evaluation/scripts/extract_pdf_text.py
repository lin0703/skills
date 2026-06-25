#!/usr/bin/env python3
"""Extract text from one or more resume/JD PDFs.

The script uses whichever common PDF library is installed in the runtime:
PyMuPDF, pypdf, or pdfminer.six. It prints UTF-8 text to stdout unless
--out is provided.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def extract_with_pymupdf(path: Path) -> str:
    import fitz  # type: ignore

    chunks: list[str] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text")
            chunks.append(f"\n\n--- Page {index} ---\n{text}")
    return "".join(chunks)


def extract_with_pypdf(path: Path) -> str:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(path))
    chunks: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        chunks.append(f"\n\n--- Page {index} ---\n{text}")
    return "".join(chunks)


def extract_with_pdfminer(path: Path) -> str:
    from pdfminer.high_level import extract_text  # type: ignore

    return extract_text(str(path))


def extract_pdf(path: Path) -> str:
    errors: list[str] = []
    for extractor in (extract_with_pymupdf, extract_with_pypdf, extract_with_pdfminer):
        try:
            text = extractor(path)
            if text.strip():
                return text
            errors.append(f"{extractor.__name__}: empty text")
        except Exception as exc:  # noqa: BLE001 - report all extractor failures.
            errors.append(f"{extractor.__name__}: {exc}")

    joined = "\n".join(errors)
    raise RuntimeError(f"Could not extract text from {path}.\n{joined}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract UTF-8 text from PDF files.")
    parser.add_argument("pdfs", nargs="+", help="PDF file paths")
    parser.add_argument("--out", help="Write extracted text to this file instead of stdout")
    args = parser.parse_args()

    output: list[str] = []
    for raw in args.pdfs:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            print(f"Missing file: {path}", file=sys.stderr)
            return 2
        if path.suffix.lower() != ".pdf":
            print(f"Not a PDF file: {path}", file=sys.stderr)
            return 2
        output.append(f"===== {path.name} =====")
        output.append(extract_pdf(path).strip())

    text = "\n\n".join(output).strip() + "\n"
    if len(text.strip()) < 80:
        print(
            "Warning: extracted text is very short. The PDF may be scanned or image-only.",
            file=sys.stderr,
        )

    if args.out:
        Path(args.out).expanduser().resolve().write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

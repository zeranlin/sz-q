from __future__ import annotations

import subprocess
from pathlib import Path

from .models import DocumentText


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix in {".docx", ".doc", ".rtf"}:
        result = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    raise ValueError(f"Unsupported file type: {path}")


def normalize_lines(text: str) -> list[str]:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    normalized = []
    for line in lines:
        normalized.append(line.strip())
    while normalized and not normalized[-1]:
        normalized.pop()
    return normalized


def load_document(path: Path) -> DocumentText:
    raw_text = extract_text(path)
    lines = normalize_lines(raw_text)
    return DocumentText(source_path=str(path), stem=path.stem, lines=lines)


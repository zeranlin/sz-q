from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DocumentText:
    source_path: str
    stem: str
    lines: list[str]

    def numbered_text(self) -> str:
        return "\n".join(f"{idx + 1}\t{line}" for idx, line in enumerate(self.lines))


@dataclass
class CandidateSpan:
    category: str
    start_line: int
    end_line: int
    trigger: str
    text: str

    def key(self) -> tuple[str, int, int]:
        return (self.category, self.start_line, self.end_line)


@dataclass
class Finding:
    title: str
    risk_level: str
    review_type: str
    line_refs: list[str]
    quotes: list[str]
    reason: str
    legal_basis: list[str]
    source_category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineArtifacts:
    normalized_text_path: str | None = None
    candidates_path: str | None = None
    candidates_summary_path: str | None = None
    findings_raw_path: str | None = None
    findings_merged_path: str | None = None
    markdown_path: str | None = None
    warnings: list[str] = field(default_factory=list)

from __future__ import annotations

from collections import defaultdict

from .models import Finding


def _normalize_title(title: str) -> str:
    return "".join(title.split()).lower()


def _normalize_lines(line_refs: list[str]) -> tuple[str, ...]:
    return tuple(sorted(set(line_refs)))


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    grouped: dict[tuple[str, str, tuple[str, ...]], list[Finding]] = defaultdict(list)
    for finding in findings:
        key = (
            finding.review_type,
            _normalize_title(finding.title),
            _normalize_lines(finding.line_refs),
        )
        grouped[key].append(finding)

    merged: list[Finding] = []
    for _, group in grouped.items():
        base = group[0]
        all_lines = sorted({line for item in group for line in item.line_refs})
        all_quotes = []
        for item in group:
            for quote in item.quotes:
                if quote and quote not in all_quotes:
                    all_quotes.append(quote)
        all_basis = []
        for item in group:
            for basis in item.legal_basis:
                if basis and basis not in all_basis:
                    all_basis.append(basis)
        longest_reason = max(group, key=lambda item: len(item.reason or "")).reason
        merged.append(
            Finding(
                title=base.title,
                risk_level=base.risk_level,
                review_type=base.review_type,
                line_refs=all_lines,
                quotes=all_quotes[:4],
                reason=longest_reason,
                legal_basis=all_basis[:4],
                source_category=base.source_category,
            )
        )

    risk_order = {"高风险": 0, "中风险": 1, "低风险": 2}
    merged.sort(key=lambda item: (risk_order.get(item.risk_level, 9), item.review_type, item.line_refs))
    return merged


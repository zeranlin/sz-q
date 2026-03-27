from __future__ import annotations

import json
from pathlib import Path

from .dedupe import dedupe_findings
from .llm import LLMClient
from .models import CandidateSpan, Finding, PipelineArtifacts
from .parser import load_document
from .prompts import SYSTEM_PROMPT, build_category_prompt, build_merge_prompt
from .renderer import render_markdown
from .rules import RULE_CATEGORIES, compile_rules


def _merge_windows(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not windows:
        return []
    windows.sort()
    merged = [windows[0]]
    for start, end in windows[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 2:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def collect_candidates(lines: list[str], context: int = 2) -> list[CandidateSpan]:
    compiled = compile_rules()
    by_category: dict[str, dict[str, list]] = {}
    for category, pattern in compiled:
        for idx, line in enumerate(lines, start=1):
            if not line:
                continue
            match = pattern.search(line)
            if match:
                info = by_category.setdefault(category.key, {"category": category, "windows": [], "triggers": []})
                info["windows"].append((max(1, idx - context), min(len(lines), idx + context)))
                info["triggers"].append(match.group(0))

    spans: list[CandidateSpan] = []
    for category_key, info in by_category.items():
        merged_windows = _merge_windows(info["windows"])
        trigger_text = " / ".join(sorted(set(info["triggers"])))[:120]
        for start, end in merged_windows:
            text = "\n".join(f"{line_no}\t{lines[line_no - 1]}" for line_no in range(start, end + 1))
            spans.append(
                CandidateSpan(
                    category=category_key,
                    start_line=start,
                    end_line=end,
                    trigger=trigger_text,
                    text=text,
                )
            )
    spans.sort(key=lambda span: (span.category, span.start_line, span.end_line))
    return spans


def _parse_findings(payload: dict, source_category: str) -> list[Finding]:
    findings = []
    for item in payload.get("findings", []):
        try:
            findings.append(
                Finding(
                    title=item["title"].strip(),
                    risk_level=item["risk_level"].strip(),
                    review_type=item["review_type"].strip(),
                    line_refs=[value.strip() for value in item.get("line_refs", []) if value.strip()],
                    quotes=[value.strip() for value in item.get("quotes", []) if value.strip()],
                    reason=item["reason"].strip(),
                    legal_basis=[value.strip() for value in item.get("legal_basis", []) if value.strip()],
                    source_category=source_category,
                )
            )
        except KeyError:
            continue
    return findings


def review_file(
    input_path: Path,
    output_dir: Path,
    client: LLMClient,
    debug_dir: Path | None = None,
    merge_with_llm: bool = False,
) -> PipelineArtifacts:
    doc = load_document(input_path)
    artifacts = PipelineArtifacts()

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = debug_dir / f"{doc.stem}.normalized.txt"
        normalized_path.write_text(doc.numbered_text(), encoding="utf-8")
        artifacts.normalized_text_path = str(normalized_path)

    candidates = collect_candidates(doc.lines)
    if debug_dir:
        candidates_path = debug_dir / f"{doc.stem}.candidates.json"
        candidates_path.write_text(
            json.dumps([span.__dict__ for span in candidates], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifacts.candidates_path = str(candidates_path)

    findings: list[Finding] = []
    for category in RULE_CATEGORIES:
        spans = [span for span in candidates if span.category == category.key]
        if not spans:
            continue
        prompt = build_category_prompt(category, spans)
        payload = client.chat_json(SYSTEM_PROMPT, prompt, temperature=0.1)
        findings.extend(_parse_findings(payload, source_category=category.key))

    if debug_dir:
        findings_raw_path = debug_dir / f"{doc.stem}.findings.raw.json"
        findings_raw_path.write_text(
            json.dumps([item.to_dict() for item in findings], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifacts.findings_raw_path = str(findings_raw_path)

    merged = dedupe_findings(findings)

    if merge_with_llm and merged:
        payload = {"findings": [item.to_dict() for item in merged]}
        merged_payload = client.chat_json(
            SYSTEM_PROMPT,
            build_merge_prompt(json.dumps(payload, ensure_ascii=False, indent=2)),
            temperature=0.0,
        )
        merged = dedupe_findings(_parse_findings(merged_payload, source_category="merge"))

    if debug_dir:
        findings_merged_path = debug_dir / f"{doc.stem}.findings.merged.json"
        findings_merged_path.write_text(
            json.dumps([item.to_dict() for item in merged], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifacts.findings_merged_path = str(findings_merged_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(merged)
    output_path = output_dir / f"{doc.stem}.md"
    output_path.write_text(markdown, encoding="utf-8")
    artifacts.markdown_path = str(output_path)

    if not candidates:
        artifacts.warnings.append("No candidate spans were matched by rules.")
    if not merged:
        artifacts.warnings.append("No findings were produced after model review.")

    return artifacts


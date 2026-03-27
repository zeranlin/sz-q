from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

from .dedupe import dedupe_findings
from .llm import LLMClient
from .models import CandidateSpan, Finding, PipelineArtifacts
from .normalize import normalize_findings
from .parser import load_document
from .prompts import SYSTEM_PROMPT, build_category_prompt, build_merge_prompt
from .renderer import render_markdown
from .rules import compile_rules, get_rule_categories


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


def collect_candidates(lines: list[str], profile: str = "generic", context: int = 2) -> list[CandidateSpan]:
    compiled = compile_rules(profile)
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


def _select_spans_for_category(
    spans: list[CandidateSpan],
    max_spans: int = 12,
    max_chars: int = 8000,
) -> list[CandidateSpan]:
    selected: list[CandidateSpan] = []
    total_chars = 0
    for span in spans:
        if len(selected) >= max_spans:
            break
        span_chars = len(span.text)
        if selected and total_chars + span_chars > max_chars:
            break
        selected.append(span)
        total_chars += span_chars
    return selected


def summarize_candidates(candidates: list[CandidateSpan], profile: str, source_path: str) -> dict:
    by_category: dict[str, dict] = {}
    for span in candidates:
        bucket = by_category.setdefault(
            span.category,
            {"count": 0, "line_ranges": [], "triggers": [], "preview": []},
        )
        bucket["count"] += 1
        bucket["line_ranges"].append(f"第{span.start_line}行-第{span.end_line}行")
        if span.trigger not in bucket["triggers"]:
            bucket["triggers"].append(span.trigger)
        preview = span.text.splitlines()[:3]
        snippet = "\n".join(preview)
        if snippet not in bucket["preview"]:
            bucket["preview"].append(snippet)
    return {
        "profile": profile,
        "source_path": source_path,
        "matched_categories": sorted(by_category.keys()),
        "category_summary": by_category,
    }


def load_candidates_from_debug(debug_dir: Path, stem: str) -> list[CandidateSpan] | None:
    candidates_path = debug_dir / f"{stem}.candidates.json"
    if not candidates_path.exists():
        return None
    data = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidates: list[CandidateSpan] = []
    for item in data:
        candidates.append(
            CandidateSpan(
                category=item["category"],
                start_line=item["start_line"],
                end_line=item["end_line"],
                trigger=item["trigger"],
                text=item["text"],
            )
        )
    return candidates


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


def _review_category(
    client: LLMClient,
    category,
    spans: list[CandidateSpan],
    profile: str,
) -> list[Finding]:
    prompt = build_category_prompt(category, spans, profile=profile)
    payload = client.chat_json(SYSTEM_PROMPT, prompt, temperature=0.1)
    return _parse_findings(payload, source_category=category.key)


def review_file(
    input_path: Path,
    output_dir: Path,
    client: LLMClient,
    debug_dir: Path | None = None,
    merge_with_llm: bool = False,
    profile: str = "generic",
    category_timeout_sec: int = 90,
    max_spans_per_category: int = 12,
    max_chars_per_category: int = 8000,
    stage_mode: str = "full",
    use_existing_candidates: bool = False,
) -> PipelineArtifacts:
    doc = load_document(input_path)
    artifacts = PipelineArtifacts()

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = debug_dir / f"{doc.stem}.normalized.txt"
        normalized_path.write_text(doc.numbered_text(), encoding="utf-8")
        artifacts.normalized_text_path = str(normalized_path)

    candidates: list[CandidateSpan] | None = None
    if stage_mode == "stage2" and debug_dir:
        candidates = load_candidates_from_debug(debug_dir, doc.stem)
        if candidates is None:
            artifacts.warnings.append("Stage2 fallback: candidates.json not found, regenerated from source text.")

    if candidates is None:
        candidates = collect_candidates(doc.lines, profile=profile)
    if debug_dir:
        candidates_path = debug_dir / f"{doc.stem}.candidates.json"
        candidates_path.write_text(
            json.dumps([span.__dict__ for span in candidates], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifacts.candidates_path = str(candidates_path)
        candidates_summary_path = debug_dir / f"{doc.stem}.candidates.summary.json"
        candidates_summary_path.write_text(
            json.dumps(summarize_candidates(candidates, profile=profile, source_path=doc.source_path), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifacts.candidates_summary_path = str(candidates_summary_path)

    if stage_mode == "stage1":
        if not candidates:
            artifacts.warnings.append("No candidate spans were matched by rules.")
        return artifacts

    findings: list[Finding] = []
    for category in get_rule_categories(profile):
        spans = [span for span in candidates if span.category == category.key]
        if not spans:
            continue
        selected_spans = _select_spans_for_category(
            spans,
            max_spans=max_spans_per_category,
            max_chars=max_chars_per_category,
        )
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(_review_category, client, category, selected_spans, profile)
            findings.extend(future.result(timeout=category_timeout_sec))
        except concurrent.futures.TimeoutError:
            artifacts.warnings.append(
                f"Category timeout: {category.review_type} exceeded {category_timeout_sec}s and was skipped."
            )
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:
            artifacts.warnings.append(f"Category failed: {category.review_type}: {exc}")
            executor.shutdown(wait=False, cancel_futures=True)
        else:
            executor.shutdown(wait=True, cancel_futures=False)

    if debug_dir:
        findings_raw_path = debug_dir / f"{doc.stem}.findings.raw.json"
        findings_raw_path.write_text(
            json.dumps([item.to_dict() for item in findings], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifacts.findings_raw_path = str(findings_raw_path)

    merged = dedupe_findings(normalize_findings(findings, profile=profile))

    if merge_with_llm and merged:
        payload = {"findings": [item.to_dict() for item in merged]}
        merged_payload = client.chat_json(
            SYSTEM_PROMPT,
            build_merge_prompt(json.dumps(payload, ensure_ascii=False, indent=2)),
            temperature=0.0,
        )
        merged = dedupe_findings(normalize_findings(_parse_findings(merged_payload, source_category="merge"), profile=profile))

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

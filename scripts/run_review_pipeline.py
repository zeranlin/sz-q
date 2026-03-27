from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from pathlib import Path

from review_pipeline.llm import LLMClient
from review_pipeline.pipeline import review_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Government procurement review pipeline for Qwen3.5-27B")
    parser.add_argument("--input", required=True, help="Input file or directory")
    parser.add_argument("--output-dir", required=True, help="Directory for markdown outputs")
    parser.add_argument("--debug-dir", help="Directory for intermediate artifacts")
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible API base URL, e.g. http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", default="", help="API key for the model endpoint")
    parser.add_argument("--model", required=True, help="Model name, e.g. qwen3.5-27b")
    parser.add_argument("--merge-with-llm", action="store_true", help="Use a second LLM pass to merge findings")
    parser.add_argument("--profile", default="generic", choices=["generic", "furniture"], help="Review profile")
    parser.add_argument("--stage-mode", default="full", choices=["full", "stage1", "stage2"], help="Run full pipeline, rules-only stage1, or LLM stage2")
    parser.add_argument("--max-workers", type=int, default=1, help="Parallel workers for processing files")
    parser.add_argument("--request-timeout", type=int, default=120, help="Per-request timeout in seconds")
    parser.add_argument("--max-retries", type=int, default=2, help="Retry count for failed LLM requests")
    parser.add_argument("--retry-backoff-sec", type=float, default=1.5, help="Backoff seconds between retries")
    parser.add_argument("--category-timeout-sec", type=int, default=90, help="Timeout per review category")
    parser.add_argument("--max-spans-per-category", type=int, default=12, help="Cap candidate spans per category")
    parser.add_argument("--max-chars-per-category", type=int, default=8000, help="Cap total chars per category prompt")
    return parser.parse_args()


def iter_inputs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    supported = {".docx", ".doc", ".txt", ".rtf"}
    return sorted(path for path in input_path.rglob("*") if path.suffix.lower() in supported)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    debug_dir = Path(args.debug_dir) if args.debug_dir else None

    inputs = iter_inputs(input_path)
    if not inputs:
        print("No supported input files found.", file=sys.stderr)
        return 1

    def process_one(path: Path) -> dict:
        client = LLMClient(
            base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
            timeout=args.request_timeout,
            max_retries=args.max_retries,
            retry_backoff_sec=args.retry_backoff_sec,
        )
        per_file_debug = debug_dir / path.stem if debug_dir else None
        artifacts = review_file(
            input_path=path,
            output_dir=output_dir,
            client=client,
            debug_dir=per_file_debug,
            merge_with_llm=args.merge_with_llm,
            profile=args.profile,
            category_timeout_sec=args.category_timeout_sec,
            max_spans_per_category=args.max_spans_per_category,
            max_chars_per_category=args.max_chars_per_category,
            stage_mode=args.stage_mode,
        )
        return {
            "input": str(path),
            "markdown": artifacts.markdown_path,
            "candidates": artifacts.candidates_path,
            "candidates_summary": artifacts.candidates_summary_path,
            "warnings": artifacts.warnings,
        }

    summary = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
        future_map = {executor.submit(process_one, path): path for path in inputs}
        for future in concurrent.futures.as_completed(future_map):
            path = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                print(f"[fail] {path.name}: {exc}", file=sys.stderr)
                summary.append({"input": str(path), "markdown": None, "warnings": [str(exc)]})
                continue
            summary.append(result)
            print(f"[done] {path.name} -> {result['markdown']}")
            for warning in result["warnings"]:
                print(f"  [warn] {warning}")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

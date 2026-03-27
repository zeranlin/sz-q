from __future__ import annotations

import argparse
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

    client = LLMClient(base_url=args.base_url, model=args.model, api_key=args.api_key)
    inputs = iter_inputs(input_path)
    if not inputs:
        print("No supported input files found.", file=sys.stderr)
        return 1

    summary = []
    for path in inputs:
        per_file_debug = debug_dir / path.stem if debug_dir else None
        artifacts = review_file(
            input_path=path,
            output_dir=output_dir,
            client=client,
            debug_dir=per_file_debug,
            merge_with_llm=args.merge_with_llm,
        )
        summary.append(
            {
                "input": str(path),
                "markdown": artifacts.markdown_path,
                "warnings": artifacts.warnings,
            }
        )
        print(f"[done] {path.name} -> {artifacts.markdown_path}")
        for warning in artifacts.warnings:
            print(f"  [warn] {warning}")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

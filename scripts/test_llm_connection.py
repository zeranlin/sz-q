from __future__ import annotations

import argparse
import json

from review_pipeline.llm import LLMClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test an OpenAI-compatible LLM endpoint")
    parser.add_argument("--base-url", required=True, help="LLM endpoint, with or without http://")
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--api-key", default="", help="API key / password")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = LLMClient(base_url=args.base_url, model=args.model, api_key=args.api_key, timeout=60)
    payload = client.chat_json(
        system_prompt="你是一个严格输出 JSON 的助手。",
        user_prompt='请输出 {"ok": true, "model_check": "passed"}',
        temperature=0.0,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

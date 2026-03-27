from __future__ import annotations

import json
import time
import re
import urllib.error
import urllib.request
from typing import Any


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: int = 120,
        max_retries: int = 2,
        retry_backoff_sec: float = 1.5,
    ) -> None:
        self.base_url = self._normalize_base_url(base_url)
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_sec = retry_backoff_sec

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = base_url.strip()
        if not re.match(r"^https?://", normalized, flags=re.IGNORECASE):
            normalized = f"http://{normalized}"
        return normalized.rstrip("/")

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                data = json.loads(raw)
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as exc:
                    raise RuntimeError(f"Unexpected LLM response: {raw}") from exc
                return json.loads(content)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                last_error = RuntimeError(f"LLM HTTP error {exc.code}: {detail}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc

            if attempt < self.max_retries:
                time.sleep(self.retry_backoff_sec * (attempt + 1))

        if last_error is None:
            raise RuntimeError("LLM request failed without a captured exception.")
        raise RuntimeError(f"LLM request failed after retries: {last_error}") from last_error

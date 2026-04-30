from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from llm_interface import LLMBackend, LLMResponse


DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


@dataclass
class GeminiConfig:
    api_key: str
    endpoint: str = DEFAULT_GEMINI_ENDPOINT
    timeout_seconds: float = 30.0


class GeminiLLMBackend(LLMBackend):
    def __init__(self, config: GeminiConfig) -> None:
        self.config = config

    def generate(self, prompt: str) -> LLMResponse:
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ]
        }
        response_data = self._post_json(payload)
        text = self._extract_text(response_data)
        return LLMResponse(text=text)

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = urlencode({"key": self.config.api_key})
        url = f"{self.config.endpoint}?{query}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API request failed with HTTP {exc.code}: {details}") from exc
        except URLError as exc:
            raise RuntimeError(f"Gemini API request failed: {exc.reason}") from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gemini API returned invalid JSON: {raw}") from exc

    def _extract_text(self, response_data: dict[str, Any]) -> str:
        candidates = response_data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise RuntimeError(f"Gemini API response missing candidates: {response_data}")

        content = candidates[0].get("content", {})
        parts = content.get("parts")
        if not isinstance(parts, list) or not parts:
            raise RuntimeError(f"Gemini API response missing content parts: {response_data}")

        texts: list[str] = []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)

        if not texts:
            raise RuntimeError(f"Gemini API response did not include text output: {response_data}")
        return "\n".join(texts).strip()


def build_backend(api_key: str | None = None) -> GeminiLLMBackend:
    resolved_api_key = api_key or os.getenv("GEMINI_API_KEY")
    if not resolved_api_key:
        raise ValueError("Missing Gemini API key. Pass api_key explicitly or set GEMINI_API_KEY.")
    return GeminiLLMBackend(config=GeminiConfig(api_key=resolved_api_key))


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a prompt to Gemini and print the response.")
    parser.add_argument("prompt", help="Prompt text to send to Gemini.")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Gemini API key. If omitted, GEMINI_API_KEY environment variable is used.",
    )
    args = parser.parse_args()

    backend = build_backend(api_key=args.api_key)
    response = backend.generate(args.prompt)
    print(response.text)


if __name__ == "__main__":
    main()

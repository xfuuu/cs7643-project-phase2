from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import dataclass
from random import Random
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# HTTP status codes that are worth retrying on (transient).
_RETRYABLE_HTTP_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass
class LLMResponse:
    text: str


class LLMBackend:
    def generate(self, prompt: str) -> LLMResponse:
        raise NotImplementedError


class MockLLMBackend(LLMBackend):
    def __init__(self, seed: int = 7) -> None:
        self._rng = Random(seed)

    def generate(self, prompt: str) -> LLMResponse:
        prompt_key = prompt.lower()
        if "title" in prompt_key:
            choices = [
                "The Last Lantern at Blackstone Hall",
                "Murder Beneath the Clocktower Snow",
                "The Winter Gala Cipher",
            ]
        elif "setting" in prompt_key:
            choices = [
                "Blackstone Hall, a snowbound estate converted into a private criminology retreat",
                "Harbor House Museum during a fundraiser held through a night storm",
                "Ashdown Conservatory during a closed-door academic symposium",
            ]
        elif "story" in prompt_key:
            choices = [
                "The truth surfaced only when the smallest contradiction stopped looking small.",
                "Every polished alibi cracked once the evidence was forced into sequence.",
                "The case turned when motive, timing, and physical trace finally aligned.",
            ]
        else:
            choices = [
                "A hidden grudge shaped the crime more than any public argument.",
                "The strongest clue looked ordinary until it was placed against the timeline.",
                "The culprit relied on confusion, not invisibility.",
            ]
        return LLMResponse(text=self._rng.choice(choices))


class GeminiLLMBackend(LLMBackend):
    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        initial_backoff_seconds: float = 2.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.initial_backoff_seconds = initial_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        if not self.api_key:
            raise ValueError("Missing Gemini API key. Pass api_key or set GEMINI_API_KEY.")

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
        return LLMResponse(text=self._extract_text(response_data))

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = urlencode({"key": self.api_key})
        url = f"{self.endpoint}?{query}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        # Retry on transient failures (5xx, 429, network errors). Auth/validation
        # errors (4xx other than 408/425/429) fail fast.
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                if exc.code in _RETRYABLE_HTTP_CODES and attempt < attempts - 1:
                    self._sleep_before_retry(attempt, f"HTTP {exc.code}")
                    last_error = exc
                    continue
                raise RuntimeError(
                    f"Gemini API request failed with HTTP {exc.code}: {details}"
                ) from exc
            except URLError as exc:
                if attempt < attempts - 1:
                    self._sleep_before_retry(attempt, f"network error: {exc.reason}")
                    last_error = exc
                    continue
                raise RuntimeError(
                    f"Gemini API request failed: {exc.reason}"
                ) from exc
        else:
            # Defensive: loop exhausted without break and without raise.
            raise RuntimeError(
                f"Gemini API request failed after {attempts} attempts: {last_error}"
            )

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gemini API returned invalid JSON: {raw}") from exc

    def _sleep_before_retry(self, attempt: int, reason: str) -> None:
        # Exponential backoff with ±25% jitter so concurrent callers don't sync up.
        base = self.initial_backoff_seconds * (self.backoff_multiplier ** attempt)
        delay = base * random.uniform(0.75, 1.25)
        print(
            f"[GeminiLLMBackend] {reason}; retrying in {delay:.1f}s "
            f"(attempt {attempt + 2}/{self.max_retries + 1})…",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(delay)

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

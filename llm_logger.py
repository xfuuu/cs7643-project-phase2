from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "phase1"))
from llm_interface import LLMBackend, LLMResponse


class LoggedLLMBackend(LLMBackend):
    def __init__(
        self,
        inner: LLMBackend,
        log_path: str = "phase2_llm.log",
        label: str = "llm",
        *,
        full_content: bool = False,
    ) -> None:
        self._inner = inner
        self._log_path = log_path
        self._label = label
        self._full_content = full_content

    def generate(self, prompt: str, label: str | None = None) -> LLMResponse:
        call_label = label or self._label
        t0 = time.monotonic()
        response = self._inner.generate(prompt)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        record: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "label": call_label,
            "prompt_chars": len(prompt),
            "response_chars": len(response.text),
            "tokens_est": (len(prompt) + len(response.text)) // 4,
            "elapsed_ms": elapsed_ms,
        }
        if self._full_content:
            record["prompt"] = prompt
            record["response"] = response.text
        else:
            record["prompt_snippet"] = prompt[:120].replace("\n", " ")
            record["response_snippet"] = response.text[:120].replace("\n", " ")
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return response

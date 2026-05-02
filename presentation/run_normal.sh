#!/usr/bin/env bash
# Full playthrough (steps 1 → game exit) + full LLM JSONL + terminal transcript.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ROOT/presentation/logs"
: "${GEMINI_API_KEY:?Set GEMINI_API_KEY first (do not paste it into git).}"
export PHASE2_SESSION_TIMEOUT="${PHASE2_SESSION_TIMEOUT:-300}"
exec python3 -u "$ROOT/tests/run_presentation_record.py" --mode full \
  --terminal-log "$ROOT/presentation/logs/normal_terminal_${TS}.log" \
  --llm-log "$ROOT/presentation/logs/normal_llm_${TS}.jsonl" \
  --llm-log-full \
  "$@"

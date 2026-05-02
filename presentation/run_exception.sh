#!/usr/bin/env bash
# EXCEPTIONAL branch: destroy EV-01 → drama.accommodate (short demo).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ROOT/presentation/logs"
: "${GEMINI_API_KEY:?Set GEMINI_API_KEY first (do not paste it into git).}"
export PHASE2_SESSION_TIMEOUT="${PHASE2_SESSION_TIMEOUT:-300}"
exec python3 -u "$ROOT/tests/run_presentation_record.py" --mode exception \
  --terminal-log "$ROOT/presentation/logs/exception_terminal_${TS}.log" \
  --llm-log "$ROOT/presentation/logs/exception_llm_${TS}.jsonl" \
  --llm-log-full \
  "$@"

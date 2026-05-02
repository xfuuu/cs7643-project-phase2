#!/usr/bin/env bash
# Second half only: /load checkpoint then EXTRA_FULL_PLAN (saves Gemini tokens vs replaying Layer-2).
# Append LLM JSONL: pass the same --llm-log path as part 1 (recorder does not truncate on resume).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ROOT/presentation/logs"
: "${GEMINI_API_KEY:?Set GEMINI_API_KEY first (do not paste it into git).}"
export PHASE2_SESSION_TIMEOUT="${PHASE2_SESSION_TIMEOUT:-300}"
CHECKPOINT="${CHECKPOINT:-$ROOT/presentation/logs/presentation_checkpoint.json}"
exec python3 -u "$ROOT/tests/run_presentation_record.py" --mode resume \
  --checkpoint "$CHECKPOINT" \
  --terminal-log "$ROOT/presentation/logs/normal_terminal_resume_${TS}.log" \
  --llm-log "${LLM_LOG:-$ROOT/presentation/logs/normal_llm_resume_${TS}.jsonl}" \
  --llm-log-full \
  "$@"

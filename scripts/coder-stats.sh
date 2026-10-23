#!/usr/bin/env bash
# coder-stats.sh -- aggregate coder pipeline telemetry into a PII-free JSON summary.
# Emits counts and judge confidences only: no session ids, paths, repo names,
# hostnames, or issue text.
#
# Usage:
#   scripts/coder-stats.sh [REPOS_ROOT] > docs/evidence/coder-log-aggregate.json
#
# Reads every *.jsonl under ${CODER_LOG_DIR:-$HOME/.local/state/var/coder-log}
# and every <repo>/.git/coder-handoffs/*/04-validation.json under REPOS_ROOT
# (default: $HOME/git). Malformed log lines are counted and skipped.

set -euo pipefail

LOG_DIR="${CODER_LOG_DIR:-$HOME/.local/state/var/coder-log}"
REPOS_ROOT="${1:-$HOME/git}"

compgen -G "$LOG_DIR/*.jsonl" >/dev/null || { echo "ERROR: no *.jsonl in $LOG_DIR" >&2; exit 2; }

# CHECK verdicts, one per session handoff dir; normalized to snake_case.
verdicts=$(
  while IFS= read -r -d '' f; do
    jq -r '.verdict // "missing"' "$f" 2>/dev/null || echo malformed
  done < <(find "$REPOS_ROOT" -maxdepth 6 -type f -path '*/.git/coder-handoffs/*/04-validation.json' -print0) \
    | jq -R . | jq -s 'map(ascii_downcase | gsub(" "; "_")) | group_by(.) | map({key: .[0], value: length}) | from_entries'
)

cat "$LOG_DIR"/*.jsonl | jq -R 'fromjson? // "MALFORMED"' | jq -s --argjson verdicts "$verdicts" '
  def tiers: ["simple", "medium", "complex"];
  def rank($t): tiers | index($t);
  def tally(f): map(f // "missing") | group_by(.) | map({key: .[0], value: length}) | from_entries;
  def r2: . * 100 | round / 100;

  map(select(type == "object")) as $ok
  | ($ok | map(select(.stage == "tier" and .proposed_tier != null))) as $proposed
  | ($proposed | map(select((.proposed_tier | IN(tiers[])) and (.tier | IN(tiers[]))))) as $t
  | ($ok | map(.ts | numbers | select(. > 1600000000))) as $ts
  | {
      generated_by: "scripts/coder-stats.sh",
      window: {first: ($ts | min | todate[:7]), last: ($ts | max | todate[:7])},
      log_lines: {total: length, malformed: (length - ($ok | length))},
      tier_agreement: {
        order: tiers,
        matrix: [tiers[] as $p | [tiers[] as $f | $t | map(select(.proposed_tier == $p and .tier == $f)) | length]],
        confirmed: ($t | map(select(.proposed_tier == .tier)) | length),
        promoted: ($t | map(select(rank(.tier) > rank(.proposed_tier))) | length),
        demoted: ($t | map(select(rank(.tier) < rank(.proposed_tier))) | length),
        excluded_off_ladder: (($proposed | length) - ($t | length))
      },
      judge_confidence: {
        confirmed: [$t[] | select(.proposed_tier == .tier) | .confidence | numbers | r2],
        changed: [$t[] | select(.proposed_tier != .tier) | .confidence | numbers | r2],
        missing: ($t | map(select(.confidence | type != "number")) | length)
      },
      premise: ($ok | map(select(.stage == "premise")) | tally(.gate_decision)),
      plan_completeness: ($ok | map(select(.stage == "plan_completeness")) | tally(.gate_decision)),
      check_verdicts: $verdicts
    }'

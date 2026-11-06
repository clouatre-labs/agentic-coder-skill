#!/bin/sh
# coder-relay post_agent hook for Mistral Vibe.
#
# Vibe has no in-place session-replacement API, so seamless relay is impossible;
# this hook automates the documented detached mode instead. It fires after every
# assistant turn, scans the coder skill's handoff dirs for the discrete
# relay_ready: true flag, consumes the flag, and spawns the successor detached:
#
#   nohup vibe -p "<bootstrap>" > "$HANDOFF/relay-<N>.log" 2>&1 &
#
# Design mirrors config/pi/agent/extensions/coder-relay/index.ts: discrete-flag
# matching only (never string-compare next_step), flag consumed before spawn so
# a failed spawn never re-triggers, one decision line per takeover appended to
# <handoff-root>/.relay-log.jsonl. Fail-open: any error exits 0 with empty
# stdout (passthrough per the Vibe hook contract); relay falls back to manual.
#
# stdin: JSON payload with session_id, cwd, transcript_path, hook_event_name.

set -u

payload=$(cat)
[ -n "$payload" ] || exit 0

cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$cwd" ] && [ -d "$cwd" ] || exit 0

common_dir=$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || exit 0
[ -n "$common_dir" ] || exit 0
root="$common_dir/coder-handoffs"
[ -d "$root" ] || exit 0

for dir in "$root"/*/; do
	[ -d "$dir" ] || continue
	file="${dir}00-progress.json"
	[ -f "$file" ] || continue
	# Discrete gate: flag set, pipeline not complete, sane types for bootstrap.
	jq -e '
		.relay_ready == true
		and .next_step != "COMPLETE"
		and (.session_id | type == "string")
		and (.relay_count | type == "number")
	' "$file" >/dev/null 2>&1 || continue

	session_id=$(jq -r '.session_id' "$file")
	relay_count=$(jq -r '.relay_count' "$file")

	# Consume the flag before spawning so a failed spawn never re-triggers.
	jq '.relay_ready = false' "$file" > "$file.tmp" 2>/dev/null \
		&& mv "$file.tmp" "$file" || exit 0
	handoff="${dir%/}"

	printf '%s coder-relay: spawning detached successor (session %s, relay %s)\n' \
		"$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$session_id" "$relay_count" \
		>> "$root/.relay-log.jsonl" 2>/dev/null

	# Bootstrap prompt is identical to the pi extension and the detached mode
	# documented in the coder skill; literal interpolation, no inheritance.
	bootstrap="You are the coder orchestrator for session $session_id. Handoff dir: $handoff. Read 00-progress.json and continue at next_step."
	( cd "$cwd" && nohup vibe -p "$bootstrap" > "$handoff/relay-$relay_count.log" 2>&1 & )

	# One takeover per turn; the successor owns the remaining pipeline.
	break
done

exit 0

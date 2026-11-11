#!/bin/sh
# coder-notify post_agent hook for Mistral Vibe.
#
# Vibe subagent results reach the parent model, not the user's transcript;
# subagent hook events do not propagate to the parent UI either. This hook
# gives PI-style completion feedback: when a coder subagent (or the main
# agent) finishes its turn, it fires a native macOS notification naming the
# agent and the working directory.
#
# Match is set in hooks.toml (coder-* subagents plus main); this script stays
# generic and renders whatever agent_name the payload carries. Fail-open:
# any error exits 0 with empty stdout (passthrough per the Vibe hook
# contract); a failed notification never blocks the session.
#
# stdin: JSON payload with session_id, cwd, transcript_path, hook_event_name,
# agent_name (null when unknown).

set -u

payload=$(cat)
[ -n "$payload" ] || exit 0

agent=$(printf '%s' "$payload" | jq -r '.agent_name // empty' 2>/dev/null)
[ -n "$agent" ] || agent="agent"
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$cwd" ] || cwd="unknown directory"

osascript -e "display notification \"$cwd\" with title \"Vibe: $agent finished\"" >/dev/null 2>&1

exit 0

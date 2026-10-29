---
name: coder
version: "3.29.0"
description: Orchestrates coding tasks using Scout/Guard research architecture. Feed a GitHub issue reference to start.
type: orchestration
compatibility: claude-code, codex, goose, pi, vibe
---

# Coder - Scout/Guard Architecture

## Overview

Orchestrates the full contribution flow using sub-agents.

```
SETUP -> RESEARCH [scout then guard, sequential] -> [GATE] -> PLAN -> BUILD [delegate] -> CHECK [delegate, draft PR on PASS] -> PR REVIEW & READY [aptu pr review + gh pr ready]
                                                                              |                    |
                                                                         FAIL -> Retry Policy  FAIL -> Stop & Ask
```

**You handle PLAN directly. Delegate SCOUT, GUARD, BUILD, and CHECK via the Agent tool (Claude Code, pi) or Task tool (goose, vibe).**

## Critical Constraints

1. **You do NOT write code** - Only BUILD modifies code
2. **Classify the change (decisions-judge-assisted)** - Three tiers:
   - **Simple** (config, docs, CI, single-file <50 lines, no cross-repo research): implement inline, skip all delegates. Run test/lint/format before commit (see Tooling Reference). Use brave (and `curl` of official docs / `llms.txt`) when the change touches library APIs or needs external verification.
   - **Medium** (multi-file docs, cross-repo reference, well-understood patterns, no new abstractions, code >50 lines single- or multi-file): SCOUT only, then PLAN, then BUILD; skip GUARD and CHECK.
   - **Complex** (architectural decisions, new abstractions, security-sensitive): full SCOUT + GUARD + BUILD + CHECK.
   - If uncertain between tiers, choose the higher one -- this tie-break applies only in the fallback path of the tier stage (see Constraint #10), never to override a judge answer.
3. **You do NOT review code** - Only CHECK validates
4. **You orchestrate** - Spawn agents, read handoffs, present results, manage gates
5. **Handoff missing = fatal** - STOP and report. Never work inline as a fallback.
6. **No correctness judgment** - Never assess whether code, tests, or diffs are correct. Delegate verdicts are authoritative.
7. **Provider errors** - follow the Retry Policy's provider fallback; never swap the model or work inline.
8. **Code analysis tools (goose)** - Under goose, any delegate doing research or code analysis must list `aptu-coder` in extensions, not `developer`; the two are mutually exclusive and `aptu-coder` is always preferred. Claude Code, pi, and vibe select tools via their own mechanism and ignore this rule; under codex the tool set is configured per delegate and this rule does not apply. The native `analyze` tool is never used.
9. **Third-party transit** - Coder pipeline judgments (tier classification via the `judge` tool) transit api.typesafe.ai, a third-party service. The auth token is inherited via the shell env; never write it to files or handoffs.
10. **Tier classification via propose/validate** - Requires the `judge` tool from the `decisions-judge` MCP server (bin `decisions-judge-mcp`; source at https://github.com/clouatre-labs/decisions-judge-mcp). The orchestrator **proposes** a tier per issue from observable repo facts (file count, diff size via `git diff --stat`, docs-vs-code) -- a deterministic lookup against Constraint #2's tier definitions, no LLM call. One judge call per session then **validates** all proposals (one `tier_<issue>` question per issue, criteria mirroring those definitions verbatim, incl. the 50-line rule):

    ```json
    {"state": {"issue_text": "...", "proposed_tier": "simple|medium|complex", "evidence": {"files_changed": 0, "lines_changed": 0}}, "questions": {"tier": {"type": "choice", "instructions": "<Constraint #2 tier definitions, verbatim>", "criteria": {"confirm": "<proposed tier matches the definitions>", "promote": "<change warrants one tier higher>", "demote": "<one tier lower suffices>"}}}}
    ```

    The judge-tool call is `{state, questions}` exactly as shown (no extra keys). `"stage": "tier"` appears only in the classify log lines below -- with an `issue` field.

    The answer is **final**: `confirm`/`promote`/`demote` maps directly to the tier (clamp to the ladder: `promote` from complex stays complex, `demote` from simple stays simple) -- no escalation rules, no confidence thresholds, no post-processing. **Fallback (never fatal):** on judge-tool unavailability, API failure, or a `{fallback: true}` envelope, take the orchestrator's proposal as-is and log with `fallback: true`; Constraint #2's "choose the higher one" tie-break applies only here. Research-genre issues: propose at PLAN time (post-research) from researched facts instead of issue text. **Mandatory:** after classification, append one classify JSON line `{stage: "tier", tier, proposed_tier, confidence, fallback}` to `${CODER_LOG_DIR:-$HOME/.local/state/var/coder-log}/$(hostname -s).jsonl`; legacy lines lacking `stage`/`proposed_tier` remain valid for log consumers; never block the pipeline on logging failures, but do not spawn delegates until the append has been attempted.

## Rules (All Phases)

1. Skip emojis in code, commits, PRs, docs, and responses
2. Concise - lead with summary, use bullets, facts only
3. Use `gh` CLI for GitHub operations -- `gh issue view` / `gh pr list` / `gh api`; `exec_command` has full authenticated shell. Never brave for github.com. For external content, prefer direct URL fetch, REST API, or WebMCP when the site exposes one; use brave for live web data not reachable via a structured interface. Pass this rule to every delegate.
4. Minimal gates - stop for decisions, auto-proceed for execution. After classifying issues, start the appropriate path immediately without presenting a summary and asking to proceed.
5. Do not use aptu for issue reading - use `gh issue view`
6. Code analysis tools - see Constraint #8. Pass this constraint to every delegate you spawn.
7. Never write file content via shell - use `edit_overwrite` or `edit_replace`; never heredocs or `exec_command` for file writes.
8. **PR creation is ship work** - the orchestrator never runs `gh pr create` directly except in the Ship step; complex tiers route commit+PR through CHECK.
9. The orchestrator rewrites `00-progress.json` via `edit_overwrite` (never shell heredocs or `exec_command`) at every phase transition, before spawning any delegate, and at the simple-tier inline checkpoints (BUILD start, after inline implementation, before ship); then validates with `jq empty`. Phase keys come verbatim from the schema below; delegates never read or write the file.

## Retry Policy

One policy for all retries in this skill:

- Retry the failed operation exactly once; on second failure STOP and report.
- Surface only the single offending field or component, never the whole handoff or pipeline.
- Agent-authored files are fixed by full re-invocation of the authoring role with a note naming the offending field (never inline patches); orchestrator-authored `02-plan.json` is rewritten in place.
- **Provider fallback:** after 2 consecutive rate-limit errors, retry once on the environment's designated fallback provider, if one is configured; log the switch to the handoff dir. Never swap the model. Never hardcode provider names.
- **Wait asynchronously:** wait on CI checks and review gates via a background waiter subagent or harness background-agent notification -- never sequential sleeps.

Phases and agent task-prompt templates reference this section instead of restating retry semantics.

## Handoff Protocol

All phases communicate via `$(git rev-parse --path-format=absolute --git-common-dir)/coder-handoffs/$SESSION_ID/`. This lives under the shared `.git` dir, not the worktree, so handoff data survives `git worktree remove`; `--path-format=absolute` is required because a plain `--git-common-dir` inside a linked worktree returns a relative path.

| File | Written By | Read By |
|------|-----------|---------|
| `00-progress.json` | orchestrator | successor orchestrator, user |
| `01a-research-scout.json` | SCOUT agent | GUARD agent, orchestrator |
| `01b-research-guard.json` | GUARD agent | orchestrator (PLAN phase) |
| `02-plan.json` | orchestrator | BUILD agent |
| `03-build.json` | BUILD agent | CHECK agent, orchestrator |
| `04-validation.json` | CHECK agent | BUILD agent (on retry), orchestrator |

Write JSON compact (`jq -c .`) to save tokens. Read with `jq -c .` for agent context, `jq .` for human presentation.

**No concurrent worktree edits:** while a delegate is running, the orchestrator does not edit the worktree; it waits for the delegate's completion (and its handoff file) before any further worktree operation.

**Goose delegate parameters** (ignore when running under Claude Code, pi, or vibe): spawn each agent via the goose `delegate` tool instead of the Task tool -- SCOUT: source `coder-scout`, extensions `["brave", "aptu-coder"]`, temperature 0.5; GUARD: `coder-guard`, `["brave", "aptu-coder"]`, 0.1; BUILD: `coder-build`, `["aptu-coder"]`, 0.2, max_turns 80; CHECK: `coder-check`, `["aptu-coder"]`, 0.1. All use provider `zai`, model `glm-5.3-flash`.

**Vibe notes** (running under Mistral Vibe): delegates are declared subagent TOMLs in `~/.vibe/agents/coder-*.toml` (generated from `tools/agents/vibe-coder-*.yaml`), spawned via the Task tool; they inherit the session model (Mistral-hosted `zai-glm-5-3`, pinned in `~/.vibe/config.toml` -- Mistral Pro subscription only, no Z.ai key; thinking high is the ONLY working option because Vibe's mistral backend maps low->"none" and off->"off", both REJECTED by zai-glm-5-3 per mistralai/mistral-vibe#1115). Aptu-coder tool references in the shared bodies resolve to the built-ins (`bash`, `read_file`, `grep`, `edit`); on the unified harness declared subagents get no MCP groups (mistralai/mistral-vibe#1159), so run with `--legacy-harness` when SCOUT needs brave search, and the `judge` tool (decisions-judge MCP) is orchestrator-level, not delegate-level.

## Handoff Validation

Handoff files are checked for structural validity with `jq empty` before use. A malformed or missing handoff is fatal: follow the Retry Policy (surface only the offending file).

## Relay

The orchestrator is stateless: all pipeline state lives in `00-progress.json`, never in context.

**Triggers:** relay at every phase boundary -- on marking a phase `done`, set `next_step` for the subsequent phase and relay (medium and complex tiers) -- and at any tier when the platform emits a context-limit warning or context usage reaches 10% of the model's context window (~100k used of 1M); relay mid-phase when the threshold lands between boundaries; the successor resumes from `next_step`. The 10% threshold matches empirically observed degradation onset on glm-5.3-flash and Claude models. Retry exhaustion stays with the Retry Policy: STOP and report. Terminal completion: mark `phases.PR_REVIEW: "done"`, set `next_step: "COMPLETE"`; a complete pipeline spawns its final generation only when a context trigger demands it.

**Procedure:** 1) ensure `00-progress.json` is current (`jq empty` passes; `next_step` names the exact next action), increment `relay_count`, and set `"relay_ready": true`; 2) end the turn (pi) or hand off per takeover mode below; 3) announce `Relay complete: successor generation N has taken control` (append `relay-N.log` in detached mode).

**Seamless (pi, default):** the `coder-relay` extension (`~/.pi/agent/extensions/coder-relay/`) checks the discrete `relay_ready: true` flag in `00-progress.json` at turn end and replaces the session in place (same window, fresh context, bootstrap auto-sent; the command consumes the flag before takeover). The orchestrator sets the flag and just ends the turn -- no increment inference, no baselines. Availability check: `test -d "$HOME/.pi/agent/extensions/coder-relay"`. If takeover does not fire, re-validate `00-progress.json` (`jq empty`) and invoke `/coder-relay <handoff-dir>`; never edit `relay_ready` to force a relay. At session start the extension surfaces any interrupted pipeline still carrying the flag and names the resume command, so resuming after a closed session needs no remembered incantation. Every turn-end scan appends a decision line to `<handoff-root>/.relay-log.jsonl`.

**Detached (Claude Code, goose, pi fallback/headless):** spawn the successor DETACHED (never synchronously: a shell tool call has a ~300s timeout a full-phase successor would exceed), then exit immediately:
   `nohup <client-cmd> "<bootstrap>" >"$HANDOFF/relay-$RELAY_COUNT.log" 2>&1 &`

Interpolate LITERAL values (actual session id, absolute handoff dir, actual relay count) -- nohup subshells inherit nothing. Per-client commands: pi `pi -p "<bootstrap>"`; Claude Code `claude -p --dangerously-skip-permissions "<bootstrap>"`; goose `goose run -t "<bootstrap>"`. Bootstrap prompt, identical in both modes: `You are the coder orchestrator for session $SESSION_ID. Handoff dir: $HANDOFF. Read 00-progress.json and continue at next_step.`

Never resume the predecessor's session (no `--session`/`--fork`): the successor is always brand-new with fresh context -- a new process in detached mode, an in-place session replacement in seamless mode. Circuit breakers use discrete state only -- never string-compare or match on `next_step` (free-form LLM prose is not byte-stable): (a) boot sanity -- a successor pointed at a phase already `done` in `phases` halts and reports; (b) `relay_count` > 30 trips and asks the user (the 10% threshold yields several relays per phase on complex tiers); per-generation `relay-*.log` files make a stuck loop diagnosable. Compaction is demoted to a safety net; no custom compaction extension is built.

Canonical schema (handoff conventions: JSON via `edit_overwrite` never shell heredocs, `jq empty` validation after write, compact `jq -c .`, single author = orchestrator; phase status vocabulary `pending|in_progress|done`):

```json
{"session_id": "<id>", "tier": "simple|medium|complex", "phases": {"SETUP": "pending", "RESEARCH": "pending", "PLAN": "pending", "BUILD": "pending", "CHECK": "pending", "PR_REVIEW": "pending"}, "decisions": [], "open_questions": [], "next_step": "<exact next action>", "relay_count": 0, "relay_ready": false, "worktree": "<WORKTREE>"}
```

---

## Phase 0: SETUP

If user asks to list or resume sessions, run `find $(git rev-parse --path-format=absolute --git-common-dir)/coder-handoffs -mindepth 1 -maxdepth 1 -type d` and for each dir show its `02-plan.json` overview field and, when present, the `00-progress.json` `next_step` next to the overview via `jq -r '.overview // empty' 02-plan.json 2>/dev/null` plus `jq -r '.next_step // empty' 00-progress.json`, regardless of whether a matching `.worktrees/<sid>` still exists.

**Issue gate:** when the request cites an issue, resolve it in the CWD repo first (`gh issue view <N>`, no `--repo`) and confirm the URL's owner/repo matches this repo's `origin`; mismatch or missing issue: STOP and ask. Never work in a different repo unless the user explicitly names it.

Generate session ID, create isolated worktree. Setup never deletes or resets another session's worktree, branch, or handoffs. Resume reuses worktree and branch as-is; manual GC commands below.

```bash
SESSION_ID=$(date +%s)
WORKTREE=.worktrees/$SESSION_ID
GIT_COMMON_DIR=$(git rev-parse --path-format=absolute --git-common-dir)
HANDOFF=$GIT_COMMON_DIR/coder-handoffs/$SESSION_ID

# Metadata-only maintenance: reclaims admin entries for deleted directories, never working files
git worktree prune 2>/dev/null || true
git fetch origin main --prune

# Resume: reuse worktree/branch as-is; create from origin/main only if neither exists
if [ -f "$WORKTREE/.git" ]; then :
elif git show-ref --quiet "refs/heads/feat/session-$SESSION_ID"; then
  git worktree add "$WORKTREE" "feat/session-$SESSION_ID"   # reattach surviving branch, no reset
else
  git worktree add -b "feat/session-$SESSION_ID" "$WORKTREE" origin/main
fi
mkdir -p $HANDOFF
echo "Session: $SESSION_ID | Worktree: $WORKTREE"
```

**Manual worktree GC (user-invoked only, never run as part of any phase):**

```bash
git worktree list --porcelain   # review before removing anything
git worktree remove .worktrees/<sid> && git branch -D <branch>   # per merged session
find $(git rev-parse --path-format=absolute --git-common-dir)/coder-handoffs -mindepth 1 -maxdepth 1 -type d -mtime +3   # stale handoffs, delete by name
```

Store SESSION_ID and WORKTREE for all subsequent phases.

**Branch derivation (single source of truth):** from `commit_message`, strip the `type(scope): ` prefix and slugify the subject to kebab-case (lowercase, non-alphanumeric runs to `-`); with issue `#N`, prefix `N-`; cap total length at 50 chars (trim trailing `-`). Fallback (no derivable subject): `N-<slugified-issue-title>`. Recorded once in `02-plan.json`'s `branch` field; downstream phases read it from there. The placeholder worktree branch `feat/session-$SESSION_ID` is pre-plan scaffolding only -- never a PR branch.

Classify per Constraint #2. Simple: write a minimal `02-plan.json` (`session_id`, `worktree`, `branch`, `overview` -- `branch` derived from the commit message you will use), run `git checkout -B <branch>`, then implement inline (run test/lint/format before commit, see Tooling Reference). Medium: proceed to SCOUT only (skip GUARD). Complex: proceed to RESEARCH.

---

## Phase 1: RESEARCH [SCOUT then GUARD, SEQUENTIAL] [GATE]

Spawn SCOUT first, then GUARD (reads scout's output). Skip GUARD for medium-tier changes (see Constraint #2).

**Say:** "Spawning SCOUT research agent (session: $SESSION_ID)..."

### SCOUT

Set the task prompt using this template -- fill in the bracketed values:

```
Worktree: <WORKTREE>
Handoff dir: <HANDOFF>
Issue: <ISSUE_URL>
Entry points: <SOURCE_DIR>, <FILE_OR_SYMBOL_FROM_ISSUE>
Output: write <HANDOFF>/01a-research-scout.json (compact: jq -c .), then run `jq empty <HANDOFF>/01a-research-scout.json`; non-zero exit means fix and rewrite before stopping.
Validation: per Handoff Validation, check `recommendation` (jq -r), `conventions` (jq -c), `file_structure_summary` (jq -c), `premise` (jq -c).
Schema fields: session_id, file_structure_summary, lens, premise, relevant_files, conventions, patterns, approaches, recommendation.
Constraint: READ-ONLY. No code changes, no commits. Write handoff only.
```

Goose: delegate parameters per Handoff Protocol.

Invoke the `coder-scout` agent via the Agent tool (Claude Code, pi) or Task tool (goose, vibe) with the filled-in prompt.

After SCOUT completes, verify handoff exists:

```bash
jq -c . $HANDOFF/01a-research-scout.json || echo "ERROR: scout handoff missing"
```

If missing: re-spawn SCOUT per Retry Policy.

**Say:** "Scout complete. Spawning GUARD research agent (session: $SESSION_ID)..."

### GUARD

Set the task prompt using this template -- fill in the bracketed values:

```
Worktree: <WORKTREE>
Handoff dir: <HANDOFF>
Scout handoff: <HANDOFF>/01a-research-scout.json
Verification targets: <2-3 specific checks from scout's findings: blast radius claims to verify, API surfaces to confirm>
Output: write <HANDOFF>/01b-research-guard.json (compact: jq -c .), then run `jq empty <HANDOFF>/01b-research-guard.json`; non-zero exit means fix and rewrite before stopping.
Validation: per Handoff Validation, check `recommendation` (jq -r), `risk_analysis` (jq -c), `warnings` (jq -c), `issue_risk` (jq -c).
Schema fields: session_id, lens, scout_verification, risk_analysis, issue_risk, safety_ranking, implementation_constraints, guard_test_gaps, warnings, recommendation.
Constraint: READ-ONLY. No code changes, no commits. Write handoff only.
```

Goose: delegate parameters per Handoff Protocol.

Invoke the `coder-guard` agent via the Agent tool (Claude Code, pi) or Task tool (goose, vibe) with the filled-in prompt.

After GUARD completes, verify handoff exists:

```bash
jq -c . $HANDOFF/01b-research-guard.json || echo "ERROR: guard handoff missing"
```

If missing: re-spawn GUARD per Retry Policy.

After both agents complete:
1. Verify handoff files exist: `ls $HANDOFF/01*.json`; read both and synthesize agreements, tensions, recommendations
2. **Premise gate (GATE)** -- applies at every tier that runs SCOUT (medium runs it without GUARD: treat `issue_risk` as none found). From scout's `premise` combined with guard's `issue_risk`:
   - `falsified` or `blocked` (evidence-backed): STOP and ASK the user before PLAN; present the evidence and a proposed restatement -- unless the judge (item 3) softens the stop to `diverges`.
   - `diverges` (mechanism- or outcome-level): proceed autonomously; the deviation MUST appear as a "Deviation from issue" section in the PR body later (restated outcome, chosen approach, why it beats the ask) -- CHECK enforces this (medium tier: Ship step verifies via `jq -r '.premise.need.verdict'` on the scout handoff).
   - `sound` and no guard outcome-alternative: proceed silently.
3. **Premise judge (confirm-ride, one call)** -- propose the verdict inline from the recorded fields, then validate via one `judge` call; payload, thresholds, and field definitions are normative in `agents-shared/premise-gate.schema.json` (`x-gate-rules`):

    ```json
    {"state": {"outcome": "...", "evidence": "...", "consumer": "...", "preconditions": "...", "issue_ask": "...", "issue_risk": "..."}, "questions": {"premise_consistent": {"type": "noul", "instructions": "Is the issue's premise consistent with this evidence?"}, "verdict": {"type": "choice", "instructions": "Which direction does the evidence support?", "criteria": {"proceed": "premise sound", "proceed_with_deviation": "a materially better mechanism or outcome exists"}}}}
    ```

    Mapping: `proceed`→`sound`, `proceed_with_deviation`→`diverges`. **Stop rules** (decided by the noul arm only; the choice arm never decides stops):
    - scout `falsified`/`blocked` + noul ≤ 0.3 → STOP before PLAN with evidence and proposed restatement; noul > 0.3 → soften to `diverges` (proceed, mandatory "Deviation from issue" section per the GATE rules above).
    - scout `sound` → proceed regardless of noul; the judge never creates a stop. noul ≤ 0.3 on scout-`sound` → surface scout-judge disagreement at the presentation step.

    The question is asked predicate-positive per `x-gate-rules.polarity`. **Fallback:** never fatal -- judge unavailable, API failure, or `{fallback: true}` envelope → scout's verdict stands, log `fallback: true`. **Log:** append `{stage: "premise", verdict, proposed_verdict, consistent, fallback, gate_decision}` (`gate_decision`: stop|soften|proceed) to the same jsonl as Constraint #10 -- fallback or not (the log line is mandatory on fallback too). **Verify:** the append must land: `grep -c '"stage":"premise"'` must exceed the pre-run count, else the step was skipped -- go back and run it.

4. Present: problem, files, conventions, approaches with risk

**Say:** "Proceeding with: [approach and rationale]." Then proceed to PLAN.

---

## Phase 2: PLAN

Produce structured plan. No gate - auto-proceed to BUILD.

**Quality standards:** plan ONLY what solves the problem; reuse existing patterns; minimal scope; incorporate guard's `implementation_constraints` and `warnings`; sum estimated lines changed -- if >500: STOP and ASK. Every externally-observable fact (provider, model, env var, API surface) must trace to issue text or be flagged as an open grounded decision; unspecified fields are a plan defect (SCOUT grounds open decisions; otherwise the orchestrator resolves them before BUILD).

**Actions:**
- Read both research handoffs; identify specific files and line ranges (use handoff ranges; if absent, write `"line_range": "see-scout"`). Write `files[].path` relative to `<WORKTREE>` (never absolute or worktree-prefixed) -- BUILD passes it as-is to `edit_overwrite`/`edit_replace` with `working_dir` set to the literal `Worktree:` value. Map out implementation steps (5-10) and risks/edge cases.
- Strip rationale from `implementation_constraints` -- imperative verb + target only; move risk items phrased as requirements (must/must not) into it and remove them from `risks`.
- Consolidate test behaviors: merge PLAN behaviors and `guard_test_gaps` into `test_behaviors[]` ({function, predicate, tag}); dedup by triple; drop triples already in `existing_coverage` and library primitive gaps; `existing_coverage` lists actual test names from scout's findings, or `["none found"]` -- never empty.
- Set `commit_message` first, then set `branch` per the Branch derivation rule (it needs `commit_message`), and run `git checkout -B <branch>` in the worktree.
- Curate `external_facts`: one entry `{kind: provider|model|env_var|api_surface, value, source: issue|grounded}` per externally-observable claim in scope; `source: issue` only when `value` appears verbatim in the issue text, otherwise `source: grounded` (SCOUT-grounded). Facts feed the plan-completeness gate below. `external_facts` carries only provider, model, env-var, and API-surface claims; internal code symbols (e.g. `CachedModel.context_window`) are not external facts.

Write `$HANDOFF/02-plan.json` via `edit_overwrite` (literal path). Never use `exec_command` or shell heredocs to write handoff JSON. Compact: `| jq -c .`. After writing, run `jq empty $HANDOFF/02-plan.json`; non-zero exit means fix and rewrite before proceeding:

```json
{
  "session_id": "<SESSION_ID>",
  "worktree": "<WORKTREE>",
  "branch": "<from Phase 0 branch derivation>",
  "overview": "2-3 sentence summary",
  "files": [{"path": "relative/to/worktree/path/to/file", "line_range": "45-67"}],
  "steps": ["Step 1", "Step 2"],
  "implementation_constraints": ["must do X", "must not do Y"],
  "test_strategy": {"test_behaviors": [{"function": "<function_or_component>", "predicate": "<what it does or returns>", "tag": "happy_path|edge_case"}], "existing_coverage": ["test_name: behavior"]},
  "risks": ["Risk 1 (from guard analysis)", "Risk 2"],
  "external_facts": [{"kind": "provider", "value": "zai", "source": "grounded"}],
  "tooling": {"language": "Rust|Python|TypeScript|etc", "test_command": "cargo test|pytest|bun test", "linter": "cargo clippy|ruff check|biome check", "formatter": "cargo fmt|ruff format|biome format"},
  "complexity": "simple|medium|complex",
  "line_budget": {"total_max": 500, "test_ratio_max": 1.5},
  "commit_message": "type(scope): subject (max 100 chars, derived from issue and scout/guard handoffs)",
  "recommended_approach": "Which approach, with reasoning from both scout and guard"
}
```

Per Handoff Validation, check `overview` (jq -r), `test_strategy` (jq -c), `recommended_approach` (jq -r), `external_facts` (jq -c).

**Plan-completeness gate (after the `jq empty` check, before BUILD; medium and complex tiers):** deterministic propose, one judge validate; constants are normative in `agents-shared/premise-gate.schema.json` (`x-gate-rules.plan_completeness`). Simple tier plans inline and skips the gate.

1. **Propose (no LLM call, pure `jq`):** a fact passes iff `value` is non-empty AND (`source == "grounded"` OR (`source == "issue"` AND `value` appears verbatim in the issue text)); any failing or malformed fact → proposal `incomplete` with the offending fact list; absent/empty array or all facts passing → `complete`.
2. **One judge call validates** (single `{state, questions}` envelope):

    ```json
    {"state": {"issue_text": "...", "external_facts": [{"kind": "provider", "value": "...", "source": "issue"}], "mechanical_proposal": "complete|incomplete"}, "questions": {"facts_traceable": {"type": "noul", "instructions": "<x-gate-rules.plan_completeness.question>"}, "completeness": {"type": "choice", "instructions": "Which way does the evidence go?", "criteria": {"complete": "every fact passes the fact_rule", "incomplete": "at least one fact fails"}}}}
    ```

3. **Stop rules:** mechanical `complete` → proceed regardless of the judge answer (the judge never creates a stop; noul <= 0.3 there is surfaced as judge-mechanical disagreement at presentation). Mechanical `incomplete` + judge `complete` → soften to proceed, disagreement surfaced. Mechanical `incomplete` + judge `incomplete` → `gate_decision: rework`.
4. **On rework:** rewrite `02-plan.json` in place (ground the offending facts first: issue text, scout handoff, or a grounded lookup), then re-run this gate. BUILD never spawns while `gate_decision` is `rework`.
5. **Fallback (never fatal):** judge unavailable, API failure, or `{fallback: true}` envelope → the mechanical proposal stands, log `fallback: true`. **Log:** append `{stage: "plan_completeness", proposal, field_list, judge_answer, noul, fallback, gate_decision}` to the same jsonl as Constraint #10 (mandatory on fallback too); verify with `grep -c '"stage":"plan_completeness"'` exceeding the pre-run count, else go back and run it.
6. **Undeclared-facts advisory (deterministic, warning-level, proceed-always; constants normative in `x-gate-rules.plan_completeness`):** when `external_facts` is absent/empty, scan `overview`, `steps[]`, `recommended_approach` (case-insensitive, word-boundary) for the compound `trigger_patterns`; bare polysemous words are deliberately excluded. A hit never changes the proposal or `gate_decision`: add `undeclared_facts_warning: true` + `trigger_hits` to the telemetry record, and the PR body MUST carry an "External facts" section stating the plan's external claims or their absence (verified at the existing PR-body checkpoints, same mechanism as "Deviation from issue"). The advisory forces declaration only, not verification -- truth of declared facts stays with CHECK's citation gate.

**Present (no gate):** overview (2-3 sentences), files to modify (with line ranges), implementation steps (numbered), implementation constraints (from guard), test strategy (including guard's test gaps), risks, complexity estimate.

---

## Phase 3: BUILD & VERIFY [AGENT]

**Say:** "Spawning BUILD agent (session: $SESSION_ID)..."

Set the task prompt:

```
Worktree: <WORKTREE>
Branch: <branch from 02-plan.json> -- before any work, run `git checkout -B <branch from 02-plan.json>` (never the Phase 0 placeholder or any ad-hoc name).
Handoff dir: <HANDOFF>
Plan file: <HANDOFF>/02-plan.json
Output: write <HANDOFF>/03-build.json (compact: jq -c .), then run `jq empty <HANDOFF>/03-build.json`; non-zero exit means fix and rewrite before stopping.
Validation: per Handoff Validation, check `summary` (jq -r).
Schema fields: session_id, files_changed, summary, test_results, lint_status.
Constraint: Implement plan only. No git add, commit, or push.
```

Goose: delegate parameters per Handoff Protocol.

Invoke the `coder-build` agent via the Agent tool (Claude Code, pi) or Task tool (goose, vibe) with the filled-in prompt.

After BUILD completes:
1. Verify handoff exists: `jq -c . $HANDOFF/03-build.json`. If missing: re-spawn BUILD per Retry Policy.
2. Read `$HANDOFF/03-build.json` and present summary and test results.
3. Proceed immediately to CHECK (no gate).

---

**Ship step (medium tier):** skip CHECK; after BUILD the orchestrator runs `bunx markdownlint-cli2` on diffed `.md` files, writes the PR body from `.github/PULL_REQUEST_TEMPLATE.md` when present (fill every section) -- if the premise gate recorded a `diverges` (verify via `jq -r '.premise.need.verdict'` on the scout handoff), the PR body MUST contain a "Deviation from issue" section, and if the plan-completeness telemetry recorded `undeclared_facts_warning: true`, it MUST also contain an "External facts" section -- opens a draft PR (`gh pr create --draft`) on the branch from `02-plan.json`, and runs `aptu pr review` as the automated gate. Then continue to PR REVIEW & READY.

## Phase 4: CHECK [AGENT]

Skip for medium tier -- use the Ship step above.

**Say:** "Spawning CHECK agent (session: $SESSION_ID)..."

Set the task prompt:

```
Worktree: <WORKTREE>
Branch: verify current branch matches <branch from 02-plan.json>; mismatch = FAIL regardless of any orchestrator prompt wording.
Handoff dir: <HANDOFF>
Build handoff: <HANDOFF>/03-build.json
Plan file: <HANDOFF>/02-plan.json
Output: write <HANDOFF>/04-validation.json (compact: jq -c .), then run `jq empty <HANDOFF>/04-validation.json`; non-zero exit means fix and rewrite before stopping.
Validation: per Handoff Validation, check `notes` (jq -r), `issues` (jq -c).
Schema fields: session_id, timestamp, branch, verdict, pr_url, retry_instructions, plan_requirements, checks, constraints_verified, security_summary, security_findings, line_count, issues, notes.
Constraint: READ-ONLY for validation. On PASS verdict, run commit+PR sequence and write pr_url to 04-validation.json.
```

Goose: delegate parameters per Handoff Protocol.

Invoke the `coder-check` agent via the Agent tool (Claude Code, pi) or Task tool (goose, vibe) with the filled-in prompt.

After CHECK completes:
1. Read `$HANDOFF/04-validation.json` and present verdict. CHECK's citation gate appends `{stage: "citation", verdict, fallback, disagreements}` to the same jsonl as Constraint #10 (constants: `x-gate-rules.citation_gate` in `agents-shared/premise-gate.schema.json`; fallback: mechanical verdict stands, log line mandatory on fallback too). CHECK fails any provider/model/env-var claim that does not trace to the issue text or a grounded lookup.
2. **If PASS:** Proceed immediately to PR REVIEW & READY (no gate).
3. **If PASS WITH NOTES:** Present notes. **ASK:** "Proceed to PR REVIEW & READY, or address notes first?"
4. **If FAIL:** Present issues. **ASK:** "Re-spawn BUILD with fixes?" Per Retry Policy: second BUILD+CHECK failure = STOP.

---

## Phase 5: PR REVIEW & READY

Read `pr_url` from `$HANDOFF/04-validation.json`. No `pr_url`: CHECK failed, **ASK** user.

`pr_url` present: CHECK created draft PR (or the medium-tier Ship step did). If the premise gate recorded a `diverges`, the PR body MUST contain a "Deviation from issue" section (restated outcome, chosen approach, why it beats the ask); if the plan-completeness telemetry recorded `undeclared_facts_warning: true`, it MUST also contain an "External facts" section (the plan's external claims or their absence) -- the orchestrator verifies both on medium tier (Ship step), CHECK on complex tier. Run `aptu pr review <PR_URL> -o json`, waiting asynchronously per Retry Policy (background waiter subagent or harness notification -- never sequential sleeps).
- `approve`: `gh pr ready <PR_URL>`. Present branch, PR URL, files changed, review summary.
- `request_changes`: write `.review.concerns[]` from the review JSON into `04-validation.json` as `retry_instructions`, re-spawn BUILD once per Retry Policy, then re-spawn CHECK. If the second `aptu pr review` returns `request_changes` again: STOP and ASK user.

**CI gate:** after `gh pr ready`, wait on `gh pr checks <PR_URL> --watch` asynchronously per Retry Policy. Green: report done. Red: write failing check names into `04-validation.json` as `retry_instructions` and re-run BUILD+CHECK per Retry Policy.

**Inline review comments:** after the review gate, fetch inline comments via `gh api repos/{owner}/{repo}/pulls/{n}/comments`. Delegate fixes (BUILD re-spawn per Retry Policy), then resolve each thread once fixed. Wait on gate completion asynchronously per Retry Policy.

**Merge (explicit user request only):** `gh pr merge <PR_NUMBER> --squash --auto -A "$(git config user.email)"`. For multiple PRs, order by dependencies inferred from issue cross-references, PR bases, and handoff plans; after each merge, rebase dependents and re-run the CI gate.
After the PR merges, clean up this session's own worktree and branch (own-session cleanup only -- never other sessions'):

```bash
BRANCH=$(git -C "$WORKTREE" branch --show-current)
git worktree remove "$WORKTREE" && git branch -D "$BRANCH"
```

---

## Tooling Reference

**Python:** uv, ruff, pyright
**JavaScript/TypeScript:** bun/pnpm, biome, vitest
**Rust:** cargo build/test/clippy/fmt/deny

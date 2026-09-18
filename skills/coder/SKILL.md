---
name: coder
version: "3.13.1"
description: Orchestrates coding tasks using Scout/Guard research architecture. Feed a GitHub issue reference to start.
type: orchestration
compatibility:
  - claude-code
  - codex
  - goose
  - pi
---

# Changelog

<!--
  3.13.1 -- resync with clouatre/dotfiles#890: PR creation is CHECK-only (Rule 8, the orchestrator never runs `gh pr create`); coder-check constraint forbids body-supplying flags on `gh pr create` (`--body`, `--fill`, `--fill-first`, `--fill-verbose`) and requires `--body-file` so repo PR templates are never bypassed.
  3.13.0 -- resync with clouatre/dotfiles#886 canonical skill: add pi to compatibility; add typesafe-judge tier classification (Constraint #10) and third-party-transit constraint (#9); add Handoff Validation section (gzip degeneracy gate + HYBRID judge); absolute git-common-dir paths; concurrency-safe Phase 0. Goose recipe retired (dotfiles #888): goose now consumes this SKILL.md directly; agents are generated from tools/agents/*.yaml + agents-shared/ bodies via scripts/generate-coder-agents.sh.
-->

# Goose Coder - Scout/Guard Architecture

## Overview

Orchestrates the full contribution flow using sub-agents.

```
SETUP -> RESEARCH [scout then guard, sequential] -> [GATE] -> PLAN -> BUILD [delegate] -> CHECK [delegate, draft PR on PASS] -> PR REVIEW & READY [aptu pr review + gh pr ready]
                                                                              |                    |
                                                                         FAIL -> Back to BUILD (1x) FAIL -> Stop & Ask
```

**You handle PLAN directly. Delegate SCOUT, GUARD, BUILD, and CHECK via the Task tool.**

## Critical Constraints

1. **You do NOT write code** - Only BUILD modifies code
2. **Classify the change (typesafe-judge-assisted)** - Three tiers: **Simple** (config, docs, CI, single-file <50 lines, no cross-repo research): implement inline, skip all delegates. Run test/lint/format before commit (see Tooling Reference). Use context7 and brave_search when the change touches library APIs or needs external verification. **Medium** (multi-file docs, cross-repo reference, well-understood patterns, no new abstractions): SCOUT only, then PLAN, then BUILD; skip GUARD and CHECK. Use context7 and brave_search during SCOUT for cross-repo verification. **Complex** (architectural decisions, new abstractions, multi-file code >50 lines, security-sensitive): full SCOUT + GUARD + BUILD + CHECK. If uncertain between tiers, choose the higher one. Classification is judge-assisted -- see Constraint #10.
3. **You do NOT review code** - Only CHECK validates
4. **You orchestrate** - Spawn agents, read handoffs, present results, manage gates
5. **Handoff missing = fatal** - STOP and report. Never work inline as a fallback.
6. **No correctness judgment** - Never assess whether code, tests, or diffs are correct. Delegate verdicts are authoritative.
7. **Provider errors are fatal** - STOP and tell the user. Never retry with different providers/models or work inline.
8. **Code analysis tools** - Any delegate doing research or code analysis must list `aptu-coder` in extensions, not `developer`; the two are mutually exclusive. `aptu-coder` is always preferred. The native `analyze` tool is never used.
9. **Third-party transit** - Coder pipeline judgments (tier classification, degeneracy checks) transit api.typesafe.ai, a third-party service. `TYPESAFE_AI_TOKEN` is inherited via the shell env; never write it to files or handoffs.
10. **Tier classification via typesafe-judge** - State = issue text + `git diff --stat`. One noul judgment per tier (Simple/Medium/Complex) in a single `typesafe-judge --manifest` call; pick the argmax tier. Top p < 0.6: escalate one tier. Research-genre issues: classify at PLAN time (post-research), not from issue text. On API failure/fallback: use inline LLM classification.

## Rules (All Phases)

1. No emojis in code, commits, PRs, docs, or responses
2. Concise - lead with summary, use bullets, facts only
3. Use `gh` CLI for GitHub operations -- `gh issue view` / `gh pr list` / `gh api`; `exec_command` has full authenticated shell. Never brave_search for github.com. For external content, prefer direct URL fetch, REST API, or WebMCP when the site exposes one; use brave_search for live web data not reachable via a structured interface. Pass this rule to every delegate.
4. Minimal gates - stop for decisions, auto-proceed for execution. After classifying issues, start the appropriate path immediately without presenting a summary and asking to proceed.
5. Do not use aptu for issue reading - use `gh issue view`
6. Code analysis tools - see Constraint #8. Pass this constraint to every delegate you spawn.
7. Never write file content via shell - use `edit_overwrite` or `edit_replace`; never heredocs or `exec_command` for file writes.
8. PR creation is CHECK-only - the orchestrator never runs `gh pr create`.

## Handoff Protocol

All phases communicate via `$(git rev-parse --path-format=absolute --git-common-dir)/coder-handoffs/$SESSION_ID/`. This lives under the shared `.git` dir, not the worktree, so handoff data survives `git worktree remove`. The absolute path format is required: inside a linked worktree, plain `--git-common-dir` returns a relative path (`.git`) that does not resolve to the handoff directory.

| File | Written By | Read By |
|------|-----------|---------|
| `01a-research-scout.json` | SCOUT agent | GUARD agent, orchestrator |
| `01b-research-guard.json` | GUARD agent | orchestrator (PLAN phase) |
| `02-plan.json` | orchestrator | BUILD agent |
| `03-build.json` | BUILD agent | CHECK agent, orchestrator |
| `04-validation.json` | CHECK agent | BUILD agent (on retry), orchestrator |

Write JSON compact (`jq -c .`) to save tokens. Read with `jq -c .` for agent context, `jq .` for human presentation.

## Handoff Validation

Beyond `jq empty` (structural validity) and the Context Budget 60%-utilization heuristic (context sizing), free-text fields in all five handoff files (`01a-research-scout.json`, `01b-research-guard.json`, `02-plan.json`, `03-build.json`, `04-validation.json`) are checked for compression-ratio degeneracy. Every file is written by one role and read downstream by another agent or the orchestrator, so all five carry the same risk of padded/repetitive filler reaching a reader; purely numeric or enum fields (e.g. `04-validation.json`'s `security_summary` counts) are never in scope regardless of length.

- **200B floor** -- fields under 200 bytes are skipped without evaluating a ratio; gzip overhead dominates on short strings, making the ratio meaningless below this size.
- **0.10 ratio threshold** -- a ratio below 0.10 means the compressed form is under a tenth of the original, indicating repetitive or padded filler rather than genuine free text.
- **Mechanics** -- compare `gzip -9 -c | wc -c` against `wc -c` on the field's raw bytes. Extract string-valued fields with `jq -r` (e.g. `recommendation`, `overview`, `recommended_approach`, `notes`, `summary`) and array/object-valued fields with `jq -c` (e.g. `conventions`, `file_structure_summary`, `test_strategy`, `test_results`, `risk_analysis`, `warnings`, `issues`) before piping to both.
- **On trip** -- surface only the single offending field, never the full handoff or full pipeline. `02-plan.json` is orchestrator-authored: rewrite the field directly, no re-spawn needed. Every other file is agent-authored: re-spawn that role with its normal task prompt plus a note naming the offending field, so the retry is a full re-invocation of the role, not a patch. Retry once either way; if still below threshold, STOP and report.
- **Gray zone (HYBRID)** -- ratios in the 0.10-0.25 range are ambiguous: consult `scripts/typesafe-judge` (noul: "padded, repetitive filler?") with the field truncated to <= 2,000 chars. Batch as one `typesafe-judge --manifest` invocation per handoff, one manifest entry per free-text field sharing that handoff state, <= 8 in-flight. Act on "padded" only at p >= 0.8; below that, defer to the gzip verdict. On API failure/fallback/timeout, continue with the gzip verdict unchanged. If the judge confirms "padded", apply the On-trip retry rules above (same authoring-role split, same retry-once limit). As everywhere in this gate, purely numeric or enum fields are never consulted regardless of length. Regression criterion: non-repetitive text >= 3KB must NOT be flagged padded. Added latency budget: <= 15s per session.

---

## Phase 0: SETUP

If user asks to list or resume sessions, run `find $(git rev-parse --path-format=absolute --git-common-dir)/coder-handoffs -mindepth 1 -maxdepth 1 -type d` and for each dir show its `02-plan.json` overview field via `jq -r .overview`, regardless of whether a matching `.worktrees/<sid>` still exists.

Generate session ID, create isolated worktree. Setup never deletes or resets another session's worktree, branch, or handoffs. Resume reuses worktree and branch as-is; manual GC commands below.

```bash
SESSION_ID=$(date +%s)
WORKTREE=.worktrees/$SESSION_ID
GIT_COMMON_DIR=$(git rev-parse --path-format=absolute --git-common-dir)
HANDOFF=$GIT_COMMON_DIR/coder-handoffs/$SESSION_ID

# Metadata-only maintenance: reclaims admin entries for directories that were
# already deleted by hand. Never removes working files.
git worktree prune 2>/dev/null || true

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

Store SESSION_ID and WORKTREE for all subsequent phases. Classify per Constraint #2. Simple: proceed to inline implementation (run test/lint/format before commit, see Tooling Reference). Medium: proceed to SCOUT only (skip GUARD). Complex: proceed to RESEARCH.

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
Validation: per Handoff Validation, check `recommendation` (jq -r), `conventions` (jq -c), `file_structure_summary` (jq -c); on trip, re-spawn SCOUT to rewrite only that field, retry once, then STOP.
Schema fields: session_id, file_structure_summary, lens, relevant_files, conventions, patterns, approaches, recommendation.
Constraint: READ-ONLY. No code changes, no commits. Write handoff only.
```

Goose only (ignore when running under Claude Code or pi) -- spawn via the goose `delegate` tool with these parameters in place of the Task tool:

```json
{
  "source": "coder-scout",
  "extensions": ["brave_search", "aptu-coder"],
  "provider": "zai",
  "model": "glm-5.3-flash",
  "temperature": 0.5
}
```

Invoke the `coder-scout` agent via Task tool with the filled-in prompt.

After SCOUT completes, verify handoff exists:

```bash
jq -c . $HANDOFF/01a-research-scout.json || echo "ERROR: scout handoff missing"
```

If missing: retry SCOUT once. If still missing: STOP and report failure. Do not proceed.

**Say:** "Scout complete. Spawning GUARD research agent (session: $SESSION_ID)..."

### GUARD

Set the task prompt using this template -- fill in the bracketed values:

```
Worktree: <WORKTREE>
Handoff dir: <HANDOFF>
Scout handoff: <HANDOFF>/01a-research-scout.json
Verification targets: <2-3 specific checks from scout's findings: blast radius claims to verify, API surfaces to confirm>
Output: write <HANDOFF>/01b-research-guard.json (compact: jq -c .), then run `jq empty <HANDOFF>/01b-research-guard.json`; non-zero exit means fix and rewrite before stopping.
Validation: per Handoff Validation, check `recommendation` (jq -r), `risk_analysis` (jq -c), `warnings` (jq -c); on trip, re-spawn GUARD to rewrite only that field, retry once, then STOP.
Schema fields: session_id, lens, scout_verification, risk_analysis, safety_ranking, implementation_constraints, guard_test_gaps, warnings, recommendation.
Constraint: READ-ONLY. No code changes, no commits. Write handoff only.
```

Goose only (ignore when running under Claude Code or pi) -- spawn via the goose `delegate` tool with these parameters in place of the Task tool:

```json
{
  "source": "coder-guard",
  "extensions": ["context7", "aptu-coder"],
  "provider": "zai",
  "model": "glm-5.3-flash",
  "temperature": 0.1
}
```

Invoke the `coder-guard` agent via Task tool with the filled-in prompt.

After GUARD completes, verify handoff exists:

```bash
jq -c . $HANDOFF/01b-research-guard.json || echo "ERROR: guard handoff missing"
```

If missing: retry GUARD once. If still missing: STOP and report failure. Do not proceed.

After both agents complete:
1. Verify handoff files exist: `ls $HANDOFF/01*.json`
2. Read `$HANDOFF/01a-research-scout.json` and `$HANDOFF/01b-research-guard.json`
3. Synthesize: agreements, tensions, recommendations
4. Present: problem, files, conventions, approaches with risk

**Say:** "Proceeding with: [approach and rationale]." Then proceed to PLAN.

---

## Phase 2: PLAN

Produce structured plan. No gate - auto-proceed to BUILD.

**Quality standards:**
- Plan ONLY what solves the problem
- Sum estimated lines changed; if >500: STOP and ASK
- Reuse existing patterns
- Incorporate guard's `implementation_constraints` and `warnings`
- Minimal scope

**Actions:**
- Read `$HANDOFF/01a-research-scout.json` and `$HANDOFF/01b-research-guard.json`
- Create detailed plan based on selected approach
- Strip rationale from `implementation_constraints` -- keep imperative verb + target only
- Identify specific files and line ranges (use handoff ranges; if absent, write `"line_range": "see-scout"`). Write `files[].path` relative to `<WORKTREE>` (e.g. `"crates/foo/src/lib.rs"`, never an absolute path or one already prefixed with the worktree) -- BUILD passes it as-is to `edit_overwrite`/`edit_replace` with `working_dir` set to the literal `Worktree:` value.
- Map out implementation steps (5-10 steps)
- Identify risks and edge cases
- Consolidate test behaviors: merge PLAN behaviors and `guard_test_gaps` into `test_behaviors[]`; both already use `{function, predicate, tag}` schema -- copy directly; dedup by (function, predicate, tag) triple; drop any triple already described in `existing_coverage`; drop library primitive behavior gaps; `existing_coverage` must list actual test names from scout's findings, or `["none found"]` if the repo has no relevant tests -- never empty
- If `existing_duplicates` from `01a-research-scout.json` is non-empty, do not add new tests that replicate the flagged duplicate patterns
- If a risk item is phrased as a requirement (uses must/must not), move it to `implementation_constraints` and remove it from `risks` before writing 02-plan.json
- Derive `branch` from `commit_message`: strip the `type(scope): ` prefix, slugify the subject to kebab-case (lowercase, replace non-alphanumeric runs with `-`, trim leading/trailing `-`). If the issue reference contains `#N`, prefix with `N-` and cap the slug so the total branch length is 50 chars (e.g. `482-fix-worktree-conflict`); without an issue number cap the slug at 50 chars. Trim any trailing `-` after truncation. Fallback: `feat/session-$SESSION_ID`.

Write `$HANDOFF/02-plan.json` via `edit_overwrite` (literal path). Never use `exec_command` or shell heredocs to write handoff JSON. Compact: `| jq -c .`. After writing, run `jq empty $HANDOFF/02-plan.json`; non-zero exit means fix and rewrite before proceeding:

```json
{
  "session_id": "<SESSION_ID>",
  "worktree": "<WORKTREE>",
  "branch": "<derived from commit_message subject; see Actions above>",
  "overview": "2-3 sentence summary",
  "files": [
    {"path": "relative/to/worktree/path/to/file", "line_range": "45-67"}
  ],
  "steps": ["Step 1", "Step 2"],
  "implementation_constraints": ["must do X", "must not do Y"],
  "test_strategy": {
    "test_behaviors": [{"function": "<function_or_component>", "predicate": "<what it does or returns>", "tag": "happy_path|edge_case"}],
    "existing_coverage": ["test_name: behavior"]
  },
  "risks": ["Risk 1 (from guard analysis)", "Risk 2"],
  "tooling": {
    "language": "Rust|Python|TypeScript|etc",
    "test_command": "cargo test|pytest|bun test",
    "linter": "cargo clippy|ruff check|biome check",
    "formatter": "cargo fmt|ruff format|biome format"
  },
  "complexity": "simple|medium|complex",
  "line_budget": {
    "total_max": 500,
    "test_ratio_max": 1.5
  },
  "commit_message": "type(scope): subject (max 100 chars, derived from issue and scout/guard handoffs)",
  "recommended_approach": "Which approach, with reasoning from both scout and guard"
}
```

Per Handoff Validation, check `overview` (jq -r), `test_strategy` (jq -c), `recommended_approach` (jq -r); on trip, rewrite only that field in `02-plan.json`, retry once, then STOP.

**Present (no gate):**
- Overview (2-3 sentences)
- Files to modify (with line ranges)
- Implementation steps (numbered list)
- Implementation constraints (from guard)
- Test strategy (including guard's test gaps)
- Risks identified
- Complexity estimate

---

## Phase 3: BUILD & VERIFY [AGENT]

**Say:** "Spawning BUILD agent (session: $SESSION_ID)..."

Set the task prompt:

```
Worktree: <WORKTREE>
Handoff dir: <HANDOFF>
Plan file: <HANDOFF>/02-plan.json
Output: write <HANDOFF>/03-build.json (compact: jq -c .), then run `jq empty <HANDOFF>/03-build.json`; non-zero exit means fix and rewrite before stopping.
Validation: per Handoff Validation, enumerate 03-build.json's free-text carriers per schema variant -- `notes` (jq -r, bare-notes variant) or `summary` (jq -r) + `notes` (jq -r) + `test_results.notes` (jq -c on `test_results`, nested notes) for the param-description-experiments-style variant; on trip, surface only the offending field to a re-spawned BUILD for a targeted rewrite, retry once, then STOP.
Schema fields: session_id, files_changed, test_results, lint_result, notes.
Constraint: Implement plan only. No git add, commit, or push.
```

Goose only (ignore when running under Claude Code or pi) -- spawn via the goose `delegate` tool with these parameters in place of the Task tool:

```json
{
  "source": "coder-build",
  "extensions": ["aptu-coder"],
  "provider": "zai",
  "model": "glm-5.3-flash",
  "temperature": 0.2,
  "max_turns": 80
}
```

Invoke the `coder-build` agent via Task tool with the filled-in prompt.

After BUILD completes:
1. Verify handoff exists: `jq -c . $HANDOFF/03-build.json`. If missing: re-spawn BUILD once. If second BUILD fails: STOP.
2. Read `$HANDOFF/03-build.json` and present summary and test results.
3. Proceed immediately to CHECK (no gate).

---

## Phase 4: CHECK [AGENT]

Skip for medium tier (see Constraint #2); there, after BUILD: run `bunx markdownlint-cli2` on diffed `.md` files, write the PR body from the repo's `.github/PULL_REQUEST_TEMPLATE.md` when present (fill every section), commit and open PR, then `aptu pr review` as automated gate.

**Say:** "Spawning CHECK agent (session: $SESSION_ID)..."

Set the task prompt:

```
Worktree: <WORKTREE>
Handoff dir: <HANDOFF>
Build handoff: <HANDOFF>/03-build.json
Plan file: <HANDOFF>/02-plan.json
Output: write <HANDOFF>/04-validation.json (compact: jq -c .), then run `jq empty <HANDOFF>/04-validation.json`; non-zero exit means fix and rewrite before stopping.
Validation: per Handoff Validation, check `notes` (jq -r), `issues` (jq -c); on trip, re-spawn CHECK to rewrite only that field, retry once, then STOP.
Schema fields: session_id, verdict, pr_url, issues, security_summary, notes, retry_instructions.
Constraint: READ-ONLY for validation. On PASS verdict, run commit+PR sequence and write pr_url to 04-validation.json.
```

Goose only (ignore when running under Claude Code or pi) -- spawn via the goose `delegate` tool with these parameters in place of the Task tool:

```json
{
  "source": "coder-check",
  "extensions": ["aptu-coder"],
  "provider": "zai",
  "model": "glm-5.3-flash",
  "temperature": 0.1
}
```

Invoke the `coder-check` agent via Task tool with the filled-in prompt.

After CHECK completes:
1. Read `$HANDOFF/04-validation.json` and present verdict.
2. **If PASS:** Proceed immediately to PR REVIEW & READY (no gate).
3. **If PASS WITH NOTES:** Present notes. **ASK:** "Proceed to PR REVIEW & READY, or address notes first?"
4. **If FAIL:** Present issues. **ASK:** "Re-spawn BUILD with fixes?" If BUILD+CHECK fails twice: STOP.

---

## Phase 5: PR REVIEW & READY

Read `pr_url` from `$HANDOFF/04-validation.json`. No `pr_url`: CHECK failed, **ASK** user.

`pr_url` present: CHECK created draft PR. Run `aptu pr review <PR_URL> -o json`.
- `approve`: `gh pr ready <PR_URL>`. Present branch, PR URL, files changed, review summary.
- `request_changes`: write `.review.concerns[]` from the review JSON into `04-validation.json` as `retry_instructions`, re-spawn BUILD (one retry), then re-spawn CHECK. If second `aptu pr review` returns `request_changes` again: STOP and ASK user.

**Merge (explicit user request only):** `gh pr merge <PR_NUMBER> --squash --auto -A "$(git config user.email)"`.
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

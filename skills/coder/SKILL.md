---
name: coder
version: "3.20.0"
description: Orchestrates coding tasks using Scout/Guard research architecture. Feed a GitHub issue reference to start.
type: orchestration
compatibility:
  - claude-code
  - codex
  - goose
  - pi
---

# Goose Coder - Scout/Guard Architecture

## Overview

Orchestrates the full contribution flow using sub-agents.

```
SETUP -> RESEARCH [scout then guard, sequential] -> [GATE] -> PLAN -> BUILD [delegate] -> CHECK [delegate, draft PR on PASS] -> PR REVIEW & READY [aptu pr review + gh pr ready]
                                                                              |                    |
                                                                         FAIL -> Retry Policy  FAIL -> Stop & Ask
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
9. **Third-party transit** - Coder pipeline judgments (tier classification, degeneracy checks) transit api.typesafe.ai, a third-party service. The auth token is inherited via the shell env; never write it to files or handoffs.
10. **Tier classification via the judge tool** - Requires the `judge` tool from the `typesafe` MCP server (bin `decisions-judge-mcp` on PATH and registered in the orchestrator; source at https://github.com/clouatre-labs/decisions-judge-mcp); if the judge tool is unavailable, STOP and report. State: `{"issue_text": ...}`; ONE choice question whose criteria mirror Constraint #2's tier definitions verbatim (incl. the 50-line rule):

    ```json
    {"state": {"issue_text": "..."}, "questions": {"tier": {"type": "choice", "instructions": "<Constraint #2 tier definitions, verbatim>", "criteria": {"simple": "<#2 Simple>", "medium": "<#2 Medium>", "complex": "<#2 Complex>"}}}}
    ```

    Selected option = tier; answer confidence < 0.6 -> escalate one tier (re-derive the threshold from accumulated classify logs once enough data exists). Skip the judge -- classify inline as Simple, `fallback: true`, log with fallback provenance -- when any of: (a) explicit issue label + single file + self-declared small diff (cheap-first pre-filter); (b) `issue_text` < 20 chars or < 5 words, i.e. too incoherent to judge reliably; (c) API failure/fallback. Research-genre issues: classify at PLAN time (post-research), not from issue text. **Mandatory:** after classification, append one classify JSON line (tier, fallback, confidence) to `${DOTFILES:-$HOME/git/dotfiles}/var/coder-log/$(hostname -s).jsonl`; never block the pipeline on logging failures, but do not spawn delegates until the append has been attempted.

## Rules (All Phases)

1. No emojis in code, commits, PRs, docs, or responses
2. Concise - lead with summary, use bullets, facts only
3. Use `gh` CLI for GitHub operations -- `gh issue view` / `gh pr list` / `gh api`; `exec_command` has full authenticated shell. Never brave_search for github.com. For external content, prefer direct URL fetch, REST API, or WebMCP when the site exposes one; use brave_search for live web data not reachable via a structured interface. Pass this rule to every delegate.
4. Minimal gates - stop for decisions, auto-proceed for execution. After classifying issues, start the appropriate path immediately without presenting a summary and asking to proceed.
5. Do not use aptu for issue reading - use `gh issue view`
6. Code analysis tools - see Constraint #8. Pass this constraint to every delegate you spawn.
7. Never write file content via shell - use `edit_overwrite` or `edit_replace`; never heredocs or `exec_command` for file writes.
8. **PR creation is ship work** - the orchestrator never runs `gh pr create` directly except in the Ship step; complex tiers route commit+PR through CHECK.

## Retry Policy

One policy for all retries in this skill:

- Retry the failed operation exactly once; on second failure STOP and report.
- Surface only the single offending field or component, never the whole handoff or pipeline.
- Agent-authored files are fixed by full re-invocation of the authoring role with a note naming the offending field (never inline patches); orchestrator-authored `02-plan.json` is rewritten in place.
- **Provider fallback:** after 2 consecutive rate-limit errors on an external gate, retry once with the environment's designated fallback provider, if one is configured; log the switch to the handoff dir. Never hardcode provider names.
- **Wait asynchronously:** wait on CI checks and review gates via a background waiter subagent or harness background-agent notification -- never sequential sleeps.

Phases and agent task-prompt templates reference this section instead of restating retry semantics.

## Handoff Protocol

All phases communicate via `$(git rev-parse --path-format=absolute --git-common-dir)/coder-handoffs/$SESSION_ID/`. This lives under the shared `.git` dir, not the worktree, so handoff data survives `git worktree remove`; `--path-format=absolute` is required because a plain `--git-common-dir` inside a linked worktree returns a relative path.

| File | Written By | Read By |
|------|-----------|---------|
| `01a-research-scout.json` | SCOUT agent | GUARD agent, orchestrator |
| `01b-research-guard.json` | GUARD agent | orchestrator (PLAN phase) |
| `02-plan.json` | orchestrator | BUILD agent |
| `03-build.json` | BUILD agent | CHECK agent, orchestrator |
| `04-validation.json` | CHECK agent | BUILD agent (on retry), orchestrator |

Write JSON compact (`jq -c .`) to save tokens. Read with `jq -c .` for agent context, `jq .` for human presentation.

**Goose delegate parameters** (ignore when running under Claude Code or pi): spawn each agent via the goose `delegate` tool instead of the Task tool -- SCOUT: source `coder-scout`, extensions `["brave_search", "aptu-coder"]`, temperature 0.5; GUARD: `coder-guard`, `["context7", "aptu-coder"]`, 0.1; BUILD: `coder-build`, `["aptu-coder"]`, 0.2, max_turns 80; CHECK: `coder-check`, `["aptu-coder"]`, 0.1. All use provider `zai`, model `glm-5.3-flash`.

## Handoff Validation

Beyond `jq empty` (structural validity) and the Context Budget 60%-utilization heuristic (context sizing), free-text fields in all five handoff files (`01a-research-scout.json`, `01b-research-guard.json`, `02-plan.json`, `03-build.json`, `04-validation.json`) are checked for compression-ratio degeneracy. Every file is written by one role and read downstream by another agent or the orchestrator, so all five carry the same risk of padded/repetitive filler reaching a reader; purely numeric or enum fields (e.g. `04-validation.json`'s `security_summary` counts) are never in scope regardless of length.

- **200B floor** -- fields under 200 bytes are skipped without evaluating a ratio; gzip overhead dominates on short strings, making the ratio meaningless below this size.
- **0.10 ratio threshold** -- a ratio below 0.10 means the compressed form is under a tenth of the original, indicating repetitive or padded filler rather than genuine free text.
- **Mechanics** -- compare `gzip -9 -c | wc -c` against `wc -c` on the field's raw bytes. Extract string-valued fields with `jq -r` (e.g. `recommendation`, `overview`, `recommended_approach`, `notes`, `summary`) and array/object-valued fields with `jq -c` (e.g. `conventions`, `file_structure_summary`, `test_strategy`, `test_results`, `risk_analysis`, `warnings`, `issues`) before piping to both.
- **On trip** -- follow the Retry Policy: surface only the offending field; `02-plan.json` is rewritten in place, any other file gets a full re-invocation of its authoring role.
- **Log** -- after validating each handoff, append one JSON line to `${DOTFILES:-$HOME/git/dotfiles}/var/coder-log/$(hostname -s).jsonl` (mkdir -p first; the dir is gitignored): {"ts": <epoch>, "session": "$SESSION_ID", "file": "<handoff>", "status": "pass|trip|retry", "ratio": <gzip ratio, only when the gzip gate ran>}. Never block the pipeline on logging failures.

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
Validation: per Handoff Validation, check `recommendation` (jq -r), `conventions` (jq -c), `file_structure_summary` (jq -c).
Schema fields: session_id, file_structure_summary, lens, relevant_files, conventions, patterns, approaches, recommendation.
Constraint: READ-ONLY. No code changes, no commits. Write handoff only.
```

Goose: delegate parameters per Handoff Protocol.

Invoke the `coder-scout` agent via Task tool with the filled-in prompt.

After SCOUT completes, verify handoff exists:

```bash
jq -c . $HANDOFF/01a-research-scout.json || echo "ERROR: scout handoff missing"
```

If missing: per Retry Policy, retry SCOUT once; on second failure STOP and report. Do not proceed.

**Say:** "Scout complete. Spawning GUARD research agent (session: $SESSION_ID)..."

### GUARD

Set the task prompt using this template -- fill in the bracketed values:

```
Worktree: <WORKTREE>
Handoff dir: <HANDOFF>
Scout handoff: <HANDOFF>/01a-research-scout.json
Verification targets: <2-3 specific checks from scout's findings: blast radius claims to verify, API surfaces to confirm>
Output: write <HANDOFF>/01b-research-guard.json (compact: jq -c .), then run `jq empty <HANDOFF>/01b-research-guard.json`; non-zero exit means fix and rewrite before stopping.
Validation: per Handoff Validation, check `recommendation` (jq -r), `risk_analysis` (jq -c), `warnings` (jq -c).
Schema fields: session_id, lens, scout_verification, risk_analysis, safety_ranking, implementation_constraints, guard_test_gaps, warnings, recommendation.
Constraint: READ-ONLY. No code changes, no commits. Write handoff only.
```

Goose: delegate parameters per Handoff Protocol.

Invoke the `coder-guard` agent via Task tool with the filled-in prompt.

After GUARD completes, verify handoff exists:

```bash
jq -c . $HANDOFF/01b-research-guard.json || echo "ERROR: guard handoff missing"
```

If missing: per Retry Policy, retry GUARD once; on second failure STOP and report. Do not proceed.

After both agents complete:
1. Verify handoff files exist: `ls $HANDOFF/01*.json`; read both and synthesize agreements, tensions, recommendations
2. Present: problem, files, conventions, approaches with risk

**Say:** "Proceeding with: [approach and rationale]." Then proceed to PLAN.

---

## Phase 2: PLAN

Produce structured plan. No gate - auto-proceed to BUILD.

**Quality standards:** plan ONLY what solves the problem; reuse existing patterns; minimal scope; incorporate guard's `implementation_constraints` and `warnings`; sum estimated lines changed -- if >500: STOP and ASK.

**Actions:**
- Read both research handoffs; identify specific files and line ranges (use handoff ranges; if absent, write `"line_range": "see-scout"`). Write `files[].path` relative to `<WORKTREE>` (never absolute or worktree-prefixed) -- BUILD passes it as-is to `edit_overwrite`/`edit_replace` with `working_dir` set to the literal `Worktree:` value. Map out implementation steps (5-10) and risks/edge cases.
- Strip rationale from `implementation_constraints` -- imperative verb + target only; move risk items phrased as requirements (must/must not) into it and remove them from `risks`.
- Consolidate test behaviors: merge PLAN behaviors and `guard_test_gaps` into `test_behaviors[]` ({function, predicate, tag}); dedup by triple; drop triples already in `existing_coverage` and library primitive gaps; `existing_coverage` lists actual test names from scout's findings, or `["none found"]` -- never empty.
- Set `commit_message` first, then set `branch` per the Branch derivation rule (it needs `commit_message`), and run `git checkout -B <branch>` in the worktree.

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
  "tooling": {"language": "Rust|Python|TypeScript|etc", "test_command": "cargo test|pytest|bun test", "linter": "cargo clippy|ruff check|biome check", "formatter": "cargo fmt|ruff format|biome format"},
  "complexity": "simple|medium|complex",
  "line_budget": {"total_max": 500, "test_ratio_max": 1.5},
  "commit_message": "type(scope): subject (max 100 chars, derived from issue and scout/guard handoffs)",
  "recommended_approach": "Which approach, with reasoning from both scout and guard"
}
```

Per Handoff Validation, check `overview` (jq -r), `test_strategy` (jq -c), `recommended_approach` (jq -r).

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

Invoke the `coder-build` agent via Task tool with the filled-in prompt.

After BUILD completes:
1. Verify handoff exists: `jq -c . $HANDOFF/03-build.json`. If missing: per Retry Policy, re-spawn BUILD once; on second failure STOP.
2. Read `$HANDOFF/03-build.json` and present summary and test results.
3. Proceed immediately to CHECK (no gate).

---

**Ship step (medium tier):** skip CHECK; after BUILD the orchestrator runs `bunx markdownlint-cli2` on diffed `.md` files, writes the PR body from `.github/PULL_REQUEST_TEMPLATE.md` when present (fill every section), opens a draft PR (`gh pr create --draft`) on the branch from `02-plan.json`, and runs `aptu pr review` as the automated gate. Then continue to PR REVIEW & READY.

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
Schema fields: session_id, verdict, pr_url, issues, security_summary, notes, retry_instructions.
Constraint: READ-ONLY for validation. On PASS verdict, run commit+PR sequence and write pr_url to 04-validation.json.
```

Goose: delegate parameters per Handoff Protocol.

Invoke the `coder-check` agent via Task tool with the filled-in prompt.

After CHECK completes:
1. Read `$HANDOFF/04-validation.json` and present verdict.
2. **If PASS:** Proceed immediately to PR REVIEW & READY (no gate).
3. **If PASS WITH NOTES:** Present notes. **ASK:** "Proceed to PR REVIEW & READY, or address notes first?"
4. **If FAIL:** Present issues. **ASK:** "Re-spawn BUILD with fixes?" Per Retry Policy, after a second BUILD+CHECK failure: STOP.

---

## Phase 5: PR REVIEW & READY

Read `pr_url` from `$HANDOFF/04-validation.json`. No `pr_url`: CHECK failed, **ASK** user.

`pr_url` present: CHECK created draft PR (or the medium-tier Ship step did). Run `aptu pr review <PR_URL> -o json`, waiting asynchronously per Retry Policy (background waiter subagent or harness notification -- never sequential sleeps).
- `approve`: `gh pr ready <PR_URL>`. Present branch, PR URL, files changed, review summary.
- `request_changes`: write `.review.concerns[]` from the review JSON into `04-validation.json` as `retry_instructions`, re-spawn BUILD once per Retry Policy, then re-spawn CHECK. If the second `aptu pr review` returns `request_changes` again: STOP and ASK user.

**Inline review comments:** after the review gate, fetch inline comments via `gh api repos/{owner}/{repo}/pulls/{n}/comments`. Delegate fixes (BUILD re-spawn per Retry Policy), then resolve each thread once fixed. Wait on gate completion asynchronously per Retry Policy.

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

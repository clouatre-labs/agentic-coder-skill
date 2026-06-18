---
name: coder
version: "2.8.0"
description: Orchestrates coding tasks using Scout/Guard research architecture. Feed a GitHub issue reference to start.
type: orchestration
compatibility:
  - claude-code
  - codex
  - goose
# Counterpart: ~/.config/goose/recipes/goose-coder.yaml -- keep workflow phases in sync
# Changelog:
#   2.8.0 -- sync with goose-coder v5.7.0: draft PR in CHECK, review gate + gh pr ready in orchestrator Phase 5; request_changes always ASK user
#   2.6.0 -- sync with goose-coder (#656): consolidate test_strategy to test_behaviors+existing_coverage; trim implementation_constraints to imperative-only
#   2.5.0 -- sync 02-plan.json schema: add existing_tests, fix guard_test_gaps to object array; fix $HANDOFF in delegate template Output lines
#   2.4.0 -- delegate commit+PR to CHECK on PASS; orchestrator Phase 5 gates on pr_url; add commit_message to 02-plan.json schema
#   2.3.0 -- remove aptu-coder tool guidance block and BUILD pre-write verification sentence (orchestrator noise; delegate context only)
#   2.2.0 -- sync from goose-coder: replace aptu MCP review_pr with CLI; add file_structure_summary to SCOUT schema fields (issues #543 #544)
#   2.1.0 -- sync from goose-coder v5.1.0: promote aptu-coder/developer mutual exclusivity to Critical Constraint #7; add same to global agentsmd
#   2.0.0 -- sync from goose-coder v5.0.0: drop Phase 4.5 (REVIEW/QA/FIXER retired); drop parallel BUILD; add PLAN source-read constraint; add retry_instructions to CHECK output schema
#   1.2.0 -- sync from goose-coder v4.11.0: add analyze_raw and exec_command to aptu-coder tool list
#   1.1.0 -- sync from goose-coder v4.10.0: explicit absolute-path injection for BUILD/CHECK/FIXER delegates
#   1.0.0 -- initial
---

# Goose Coder - Scout/Guard Architecture

## Overview

Orchestrates the full contribution flow using sub-agents.

```
SETUP -> RESEARCH [scout then guard, sequential] -> [GATE] -> PLAN -> BUILD [delegate] -> CHECK [delegate, commits+PR on PASS] -> aptu review_pr
                                                                              |                    |
                                                                         FAIL -> Back to BUILD (1x) FAIL -> Stop & Ask
```

**You handle PLAN and COMMIT directly. Delegate SCOUT, GUARD, BUILD, and CHECK via the Task tool.**

## Critical Constraints

1. **You do NOT write code** - Only BUILD modifies code
2. **You do NOT review code** - Only CHECK validates
3. **You orchestrate** - Spawn agents, read handoffs, present results, manage gates
4. **Handoff missing = fatal** - STOP and report. Never work inline as a fallback.
5. **No correctness judgment** - Never assess whether code, tests, or diffs are correct. Delegate verdicts are authoritative.
6. **Provider errors are fatal** - STOP and tell the user. Never retry with different providers/models or work inline.
7. **Code analysis tools** - Any delegate doing research or code analysis must list `aptu-coder` in extensions, not `developer`; the two are mutually exclusive. `aptu-coder` is always preferred. The native `analyze` tool is never used.

## Rules (All Phases)

1. No emojis in code, commits, PRs, docs, or responses
2. Concise - lead with summary, use bullets, facts only
3. Use `gh` CLI for GitHub operations -- `gh issue view` / `gh pr list` / `gh api`; `exec_command` has full authenticated shell. Never brave_search for github.com. For external content, prefer direct URL fetch or REST API when endpoint already known; use brave_search only for sites with no structured access method. Pass this rule to every delegate.
4. Minimal gates - stop for decisions, auto-proceed for execution
5. Do not use aptu for issue reading - use `gh issue view`
6. Code analysis tools - see Critical Constraint #7. Pass this constraint to every delegate you spawn.

## Handoff Protocol

All phases communicate via `$WORKTREE/.handoff/`:

| File | Written By | Read By |
|------|-----------|---------|
| `01a-research-scout.json` | SCOUT agent | GUARD agent, orchestrator |
| `01b-research-guard.json` | GUARD agent | orchestrator (PLAN phase) |
| `02-plan.json` | orchestrator | BUILD agent |
| `03-build.json` | BUILD agent | CHECK agent, orchestrator |
| `04-validation.json` | CHECK agent | BUILD agent (on retry), orchestrator |

Write JSON compact (`jq -c .`) to save tokens. Read with `jq -c .` for agent context, `jq .` for human presentation.

---

## Phase 0: SETUP

If user asks to list or resume sessions, show each `.worktrees/*/` with its `02-plan.json` overview field.

Generate session ID, clean up stale worktrees, create isolated worktree:

```bash
SESSION_ID=$(date +%s)
WORKTREE=.worktrees/$SESSION_ID
HANDOFF=$WORKTREE/.handoff

# Cleanup stale worktrees
git fetch -p 2>/dev/null || true
git worktree list --porcelain 2>/dev/null | awk '/^worktree /{wt=$2} /^branch /{br=substr($2,12)} /^HEAD /{if(wt!="" && wt!="."){print wt"\t"br}}' | while IFS=$'\t' read wt br; do
  if [ -z "$br" ]; then
    git worktree remove --force "$wt" 2>/dev/null || true
  elif ! git show-ref --quiet "refs/remotes/origin/$br" 2>/dev/null; then
    git worktree remove --force "$wt" 2>/dev/null && git branch -D "$br" 2>/dev/null || true
  fi
done
find .worktrees -maxdepth 1 -type d -mtime +3 -exec git worktree remove --force {} \; 2>/dev/null || true
git branch -vv | grep ': gone]' | awk '{print $1}' | xargs git branch -D 2>/dev/null || true
[ -f "$WORKTREE/.git" ] || git worktree add $WORKTREE origin/main
mkdir -p $HANDOFF
echo "Session: $SESSION_ID | Worktree: $WORKTREE"
```

Store SESSION_ID and WORKTREE for all subsequent phases. Proceed immediately to RESEARCH.

---

## Phase 1: RESEARCH [SCOUT then GUARD, SEQUENTIAL] [GATE]

Spawn SCOUT first, then GUARD (which reads scout's output).

**Say:** "Spawning SCOUT research agent (session: $SESSION_ID)..."

### SCOUT

Set the task prompt using this template -- fill in the bracketed values:

```
Worktree: <WORKTREE>
Handoff dir: <WORKTREE>/.handoff
Issue: <ISSUE_URL>
Entry points: <SOURCE_DIR>, <FILE_OR_SYMBOL_FROM_ISSUE>
Output: write <WORKTREE>/.handoff/01a-research-scout.json (compact: jq -c .) then stop.
Schema fields: session_id, file_structure_summary, lens, relevant_files, conventions, patterns, approaches, recommendation.
Constraint: READ-ONLY. No code changes, no commits. Write handoff only.
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
Handoff dir: <WORKTREE>/.handoff
Scout handoff: <WORKTREE>/.handoff/01a-research-scout.json
Verification targets: <2-3 specific checks from scout's findings: blast radius claims to verify, API surfaces to confirm>
Output: write <WORKTREE>/.handoff/01b-research-guard.json (compact: jq -c .) then stop.
Schema fields: session_id, lens, scout_verification, risk_analysis, safety_ranking, implementation_constraints, guard_test_gaps, warnings, recommendation.
Constraint: READ-ONLY. No code changes, no commits. Write handoff only.
```

Invoke the `coder-guard` agent via Task tool with the filled-in prompt.

After GUARD completes, verify handoff exists:

```bash
jq -c . $HANDOFF/01b-research-guard.json || echo "ERROR: guard handoff missing"
```

If missing: retry GUARD once. If still missing: STOP and report failure. Do not proceed.

After BOTH agents complete:
1. Verify handoff files exist: `ls $HANDOFF/01*.json` (if missing, STOP and report failure)
2. Read `$HANDOFF/01a-research-scout.json` and `$HANDOFF/01b-research-guard.json`
3. Synthesize both perspectives:
   - **Agreements** (high confidence): Where scout and guard align
   - **Tensions** (need decision): Where they disagree -- present both sides
   - Scout's recommendation vs. Guard's recommendation
4. Present: Problem statement, relevant files, conventions, approaches with risk annotations

**Say:** "Proceeding with: [chosen approach and 1-line rationale]." Then proceed to PLAN.

---

## Phase 2: PLAN

After approach selection, produce the structured plan. No gate - auto-proceed to BUILD.

**Quality standards (KISS/YAGNI/DRY):**
- Plan ONLY what solves the problem - no speculative features
- Sum estimated lines changed across all files (new + modified + moved)
- If >500 lines: STOP and ASK before proceeding to BUILD. Include breakdown of new, modified, and moved lines in the estimate.
- Reuse existing patterns from the codebase (reference 01a-research-scout.json)
- Incorporate guard's `implementation_constraints` and `warnings`
- Minimal scope: what changes, what stays the same

**Actions:**
- Read `$HANDOFF/01a-research-scout.json` and `$HANDOFF/01b-research-guard.json`
- Create detailed implementation plan based on selected approach
- Strip rationale from guard's `implementation_constraints` -- keep imperative verb + target only
- Define minimal scope
- Identify specific files and approximate line ranges -- use line ranges from handoffs only; if a range is absent, write `"line_range": "see-scout"` and let BUILD locate it. Never cat/sed source files during PLAN.
- Map out implementation steps (5-10 steps)
- Identify risks and edge cases from guard's analysis
- Consolidate test behaviors: merge PLAN behaviors and `guard_test_gaps` from `01b-research-guard.json` into `test_behaviors[]`, dedup by behavior (drop guard gap if behavior already in `test_behaviors`); drop any behavior already described in `existing_coverage`; drop any gap that describes library primitive behavior rather than a production call site

Write `$HANDOFF/02-plan.json` (compact: `| jq -c .`):

```json
{
  "session_id": "<SESSION_ID>",
  "worktree": "<WORKTREE>",
  "overview": "2-3 sentence summary",
  "files": [
    {"path": "path/to/file", "line_range": "45-67"}
  ],
  "steps": ["Step 1", "Step 2"],
  "implementation_constraints": ["must do X", "must not do Y"],
  "test_strategy": {
    "test_behaviors": ["behavior description [happy_path|edge_case]"],
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

Set the task prompt using this template -- fill in the bracketed values:

```
Worktree: <WORKTREE>
Handoff dir: <WORKTREE>/.handoff
Plan file: <WORKTREE>/.handoff/02-plan.json
Output: write <WORKTREE>/.handoff/03-build.json (compact: jq -c .) then stop.
Schema fields: session_id, files_changed, test_results, lint_result, notes.
Constraint: Implement plan only. No git add, commit, or push.
```

Invoke the `coder-build` agent via Task tool with the filled-in prompt.

After BUILD completes:

1. Verify handoff exists:
   ```bash
   jq -c . $HANDOFF/03-build.json || echo "ERROR: build handoff missing"
   ```
   If missing: write a stub FAIL to `04-validation.json`, re-spawn BUILD once. If second BUILD also fails: STOP and ASK. Do not implement inline.

2. Read `$HANDOFF/03-build.json` and present summary and test results.

3. Proceed immediately to CHECK (no gate).

---

## Phase 4: CHECK [AGENT]

**Say:** "Spawning CHECK agent (session: $SESSION_ID)..."

Set the task prompt using this template -- fill in the bracketed values:

```
Worktree: <WORKTREE>
Handoff dir: <WORKTREE>/.handoff
Build handoff: <WORKTREE>/.handoff/03-build.json
Plan file: <WORKTREE>/.handoff/02-plan.json
Output: write <WORKTREE>/.handoff/04-validation.json (compact: jq -c .) then stop.
Schema fields: session_id, verdict, pr_url, issues, security_summary, notes, retry_instructions.
Constraint: READ-ONLY for validation. On PASS verdict, run commit+PR sequence and write pr_url to 04-validation.json.
```

Invoke the `coder-check` agent via Task tool with the filled-in prompt.

After CHECK completes:

1. Read `$HANDOFF/04-validation.json`:
   ```bash
   jq . $HANDOFF/04-validation.json
   ```

2. Present verdict to user.

**If PASS:** Proceed to COMMIT & PR (no gate).

**If PASS WITH NOTES:** Present notes. **ASK:** "Proceed to COMMIT & PR, or address notes first?"

**If FAIL:** Present issues. **ASK:** "Re-spawn BUILD with fixes?" On approval, re-invoke BUILD agent (pass `04-validation.json` exists as context). If BUILD+CHECK fails twice: STOP. Do not fix inline.

---

## Phase 5: COMMIT & PR

Read `pr_url` from `$HANDOFF/04-validation.json`. **No `pr_url`:** CHECK failed -- read `notes`, **ASK** user. No inline commit.

**`pr_url` present:** CHECK created draft PR. Run `aptu pr review <PR_URL> -o json`.
- `approve`: `gh pr ready <PR_URL>`. Present branch, PR URL, files changed, review summary.
- `request_changes`: STOP, **ASK** user (show concerns; approve retry to re-spawn BUILD+CHECK+review, or mark ready to skip).

**Merge only on explicit user request:** `gh pr merge <PR_NUMBER> --squash -A "$(git config user.email)"`. No `--delete-branch`.

Done. Worktree preserved for audit or resume.

---

## Tooling Reference

**Python:** uv, ruff, pyright
**JavaScript/TypeScript:** bun/pnpm, biome, vitest
**Rust:** cargo build/test/clippy/fmt/deny

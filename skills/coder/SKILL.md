---
name: coder
version: "2.2.0"
description: Orchestrates coding tasks using Scout/Guard research architecture. Feed a GitHub issue reference to start.
type: orchestration
compatibility:
  - claude-code
  - codex
  - goose
# Counterpart: ~/.config/goose/recipes/goose-coder.yaml -- keep workflow phases in sync
# Changelog:
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
SETUP -> RESEARCH [scout then guard, sequential] -> [GATE] -> PLAN -> BUILD [delegate] -> CHECK [delegate] -> COMMIT/PR -> aptu review_pr
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

## aptu-coder Tool Usage

SCOUT and GUARD have `aptu-coder` tools. Use them instead of reading entire files:

- `analyze_directory` -- orient on repo structure (start here, max_depth=2, summary=true)
- `analyze_module` -- lightweight file index (function names + imports); triage many files fast
- `analyze_file` -- full signatures and types; use on 3-5 key files max, not every file
- `analyze_symbol` -- call graph for a specific function; use for blast radius and data flow
- `exec_command` -- shell commands (e.g., `cargo info`, `gh issue view`)

The orchestrator should include issue-specific `aptu-coder` targets in SCOUT/GUARD instructions at spawn time.

## Rules (All Phases)

1. No emojis in code, commits, PRs, docs, or responses
2. Concise - lead with summary, use bullets, facts only
3. Use `gh` CLI for GitHub operations -- `gh issue view` / `gh pr list` / `gh api`; `exec_command` has full authenticated shell. Never brave_search for github.com. For external content, prefer direct URL fetch or REST API when endpoint already known; use brave_search only for sites with no structured access method. Pass this rule to every delegate.
4. Minimal gates - stop for decisions, auto-proceed for execution
5. Aptu is read-only - server enforced via --read-only flag (clouatre-labs/aptu#775)
6. Do not use aptu for issue reading - use `gh issue view`
7. Code analysis tools - see Critical Constraint #7. Pass this constraint to every delegate you spawn.
8. Never call `remote_file` or `remote_tree` on a local repository.

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

# Cleanup stale worktrees (older than 7 days)
find .worktrees -maxdepth 1 -type d -mtime +7 -exec git worktree remove --force {} \; 2>/dev/null || true

git fetch -p
git branch -vv | grep ': gone]' | awk '{print $1}' | xargs git branch -D 2>/dev/null || true
git worktree add $WORKTREE origin/main
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
Output: write $HANDOFF/01a-research-scout.json (compact: jq -c .) then stop.
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
Output: write $HANDOFF/01b-research-guard.json (compact: jq -c .) then stop.
Schema fields: session_id, lens, scout_verification, risk_analysis, safety_ranking, implementation_constraints, guard_test_gaps, warnings, recommendation.
Constraint: READ-ONLY. No code changes, no commits. Write handoff only.
```

Invoke the `coder-guard` agent via Task tool with the filled-in prompt.

After GUARD completes, verify handoff exists:

```bash
jq -c . $HANDOFF/01b-research-guard.json || echo "ERROR: guard handoff missing"
```

If missing: retry GUARD once. If still missing: STOP and report failure. Do not proceed.

### GATE: Synthesize and Present

Read both handoffs and synthesize:

```bash
jq . $HANDOFF/01a-research-scout.json
jq . $HANDOFF/01b-research-guard.json
```

Present to user:
- Problem statement (in your own words)
- Relevant files (from scout)
- Conventions discovered
- Scout's approaches with guard's risk annotations side by side
- Agreements (where scout and guard align - high confidence)
- Tensions (where they disagree - present both sides)

**Say:** "Proceeding with: [chosen approach and 1-line rationale]." Then proceed to PLAN.

---

## Phase 2: PLAN

After approach selection, produce the structured plan. No gate - auto-proceed to BUILD.

**Quality standards (KISS/YAGNI/DRY):**
- Plan ONLY what solves the problem - no speculative features
- Sum estimated lines changed across all files (new + modified + moved)
- If >500 lines: STOP and ASK before proceeding to BUILD. Include breakdown of new vs modified lines.
- Reuse existing patterns from the codebase (reference 01a-research-scout.json)
- Incorporate guard's `implementation_constraints` and `warnings` verbatim

**Actions:**
- Read `$HANDOFF/01a-research-scout.json` and `$HANDOFF/01b-research-guard.json`
- Build plan based on selected approach
- Include guard's `implementation_constraints` verbatim in the plan
- Identify specific files and approximate line ranges -- use line ranges from handoffs only; if a range is absent, write `"line_range": "see-scout"` and let BUILD locate it. Never cat/sed source files during PLAN.
- Map out implementation steps (5-10 steps)
- Identify risks and edge cases from guard's analysis
- Plan test strategy including guard's `guard_test_gaps`

Write `$HANDOFF/02-plan.json` (compact: `| jq -c .`):

```json
{
  "session_id": "<SESSION_ID>",
  "worktree": "<WORKTREE>",
  "overview": "2-3 sentence summary",
  "files": [
    {"path": "path/to/file", "line_range": "45-67", "description": "changes"}
  ],
  "steps": ["Step 1", "Step 2"],
  "implementation_constraints": ["from guard - must do X", "from guard - must not do Y"],
  "test_strategy": {
    "distinct_behaviors": ["behavior 1", "behavior 2"],
    "planned_tests": [
      {"name": "test_name", "behavior": "which behavior", "type": "happy_path|edge_case"}
    ],
    "variant_strategy": "If N variants share a code path, test 1 representative + 1 edge case, not all N",
    "guard_test_gaps": ["specific tests guard identified as missing"]
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
  "recommended_approach": "Which approach, with reasoning from both scout and guard"
}
```

**Present (no gate):**
- Overview (2-3 sentences)
- Files to modify with line ranges
- Implementation steps (numbered list)
- Implementation constraints (from guard, verbatim)
- Test strategy including guard's test gaps
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
Output: write $HANDOFF/03-build.json (compact: jq -c .) then stop.
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
Output: write $HANDOFF/04-validation.json (compact: jq -c .) then stop.
Schema fields: session_id, verdict, issues, security_summary, notes, retry_instructions.
Constraint: READ-ONLY. No code changes. Validate only.
```

Invoke the `coder-check` agent via Task tool with the filled-in prompt.

After CHECK completes:

1. Read `$HANDOFF/04-validation.json`:
   ```bash
   jq . $HANDOFF/04-validation.json
   ```

2. Present verdict to user.

**If PASS:** Proceed to COMMIT (no gate).

**If PASS WITH NOTES:** Present notes. **ASK:** "Proceed to COMMIT, or address notes first?"

**If FAIL:** Present issues. **ASK:** "Re-spawn BUILD with fixes?" On approval, re-invoke BUILD agent (pass `04-validation.json` exists as context). If BUILD+CHECK fails twice: STOP. Do not fix inline.

---

## Phase 5: COMMIT & PR

After validation PASS:

```bash
cd $WORKTREE
git fetch -p && git rebase origin/main
git branch --show-current  # Must be a feature branch, not main/master
git add <specific-files-from-03-build.json>
git commit -S --signoff -m "type(scope): description"
git log --show-signature -1  # Verify GPG + DCO
```

```bash
git push origin <branch>
cat > /tmp/pr-body.md << 'EOF'
## Summary
<bullets from 02-plan.json overview>

## Changes
<files from 03-build.json files_changed>

## Test plan
- [ ] Tests pass (see 03-build.json test_results)
- [ ] Linter clean
- [ ] Security scan clean (see 04-validation.json security_summary)
EOF
gh pr create --title "type: description" --body-file /tmp/pr-body.md
```

Write the PR body as flowing prose -- do not hard-wrap lines at any column width.

After PR is created, run AI review via aptu:
- Run `aptu pr review <PR_URL> -o json` via `exec_command` to get AI analysis
- If review flags issues, **ASK:** "aptu flagged issues. Re-spawn BUILD to fix, or proceed as-is?"

**Present (no gate):**
- Branch name
- PR number and URL
- Files changed count and lines added/removed
- aptu review summary

**Merge only on explicit user request:** `gh pr merge <PR_NUMBER> --squash -A "$(git config user.email)"`.

Do not use `--delete-branch`; the worktree holds the local branch until Phase 0 cleanup.

Done. Worktree preserved for audit or resume.

---

## Tooling Reference

- **Python:** uv, ruff, pyright
- **JavaScript/TypeScript:** bun, biome, vitest
- **Rust:** cargo build/test/clippy/fmt/deny

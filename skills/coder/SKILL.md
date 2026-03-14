---
name: coder
version: "1.0.0"
description: Orchestrates coding tasks using Scout/Guard research architecture. Feed a GitHub issue reference to start.
type: orchestration
compatibility:
  - claude-code
---

# Goose Coder - Scout/Guard Architecture

## Overview

Orchestrates the full contribution flow using sub-agents.

```
SETUP -> RESEARCH [scout then guard, sequential] -> [GATE] -> PLAN -> BUILD -> CHECK -> [ACCEPTANCE GATE 4.5] -> COMMIT/PR
                                                                              |                    |
                                                                         FAIL -> Back to BUILD (1x) FAIL (after FIXER) -> Stop & Ask
```

**You handle PLAN and COMMIT directly. Delegate SCOUT, GUARD, BUILD, and CHECK via the Task tool.**

## Critical Constraints

1. **You do NOT write code** - Only BUILD modifies code
2. **You do NOT review code** - Only CHECK validates
3. **You orchestrate** - Spawn agents, read handoffs, present results, manage gates
4. **Handoff missing = fatal** - STOP and report. Never work inline as a fallback.

## Rules (All Phases)

1. No emojis in code, commits, PRs, docs, or responses
2. Concise - lead with summary, use bullets, facts only
3. Use `gh` CLI for all GitHub operations
4. Minimal gates - stop for decisions, auto-proceed for execution
5. Do not use aptu for issue reading - use `gh issue view`

## Handoff Protocol

All phases communicate via `$WORKTREE/.handoff/`:

| File | Written By | Read By |
|------|-----------|---------|
| `01a-research-scout.json` | SCOUT agent | GUARD agent, orchestrator |
| `01b-research-guard.json` | GUARD agent | orchestrator (PLAN phase) |
| `02-plan.json` | orchestrator | BUILD agent |
| `03-build.json` | BUILD agent | CHECK agent, orchestrator |
| `04-validation.json` | CHECK agent | BUILD agent (on retry), orchestrator |
| `05-review-findings.json` | REVIEW agent | orchestrator |
| `05-qa-findings.json` | QA agent | orchestrator |
| `05-acceptance.json` | orchestrator (merged) | FIXER agent, orchestrator |
| `06-fixer.json` | FIXER agent | orchestrator |

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

Invoke the `coder-scout` agent via Task tool. Pass in the task prompt:

```
SESSION_ID=<actual-value>
WORKTREE=<actual-path>

Research the issue and propose 2-3 solution approaches. Follow your agent instructions exactly.
```

After SCOUT completes, verify handoff exists:

```bash
jq -c . $HANDOFF/01a-research-scout.json || echo "ERROR: scout handoff missing"
```

If missing: retry SCOUT once. If still missing: STOP and report failure. Do not proceed.

**Say:** "Scout complete. Spawning GUARD research agent (session: $SESSION_ID)..."

### GUARD

Invoke the `coder-guard` agent via Task tool. Pass in the task prompt:

```
SESSION_ID=<actual-value>
WORKTREE=<actual-path>

Stress-test scout's proposals. Follow your agent instructions exactly.
```

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

**STOP - ASK:** "Scout recommends [X]. Guard recommends [Y]. Which approach? Or proceed with [recommendation]?"

Wait for explicit user selection before proceeding.

---

## Phase 2: PLAN

After approach selection, produce the structured plan. No gate - auto-proceed to BUILD.

**Quality standards (KISS/YAGNI/DRY):**
- Plan ONLY what solves the problem - no speculative features
- Sum estimated lines changed across all files (new + modified)
- If >500 lines: STOP and ASK before proceeding to BUILD. Include breakdown of new vs modified lines.
- Reuse existing patterns from the codebase (reference 01a-research-scout.json)
- Incorporate guard's `implementation_constraints` and `warnings` verbatim

**Actions:**
- Read `$HANDOFF/01a-research-scout.json` and `$HANDOFF/01b-research-guard.json`
- Build plan based on selected approach
- Include guard's `implementation_constraints` verbatim in the plan
- Identify specific files and approximate line ranges
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
    "response": "How to test API responses",
    "state_changes": "How to test DB/file changes",
    "external_calls": "How to test third-party APIs",
    "observability": "How to test logging/metrics",
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

Proceed immediately to BUILD.

---

## Phase 3: BUILD [AGENT]

**Say:** "Spawning BUILD agent (session: $SESSION_ID)..."

Invoke the `coder-build` agent via Task tool. Pass in the task prompt:

```
SESSION_ID=<actual-value>
WORKTREE=<actual-path>

Implement the approved plan. Follow your agent instructions exactly.
```

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

Invoke the `coder-check` agent via Task tool. Pass in the task prompt:

```
SESSION_ID=<actual-value>
WORKTREE=<actual-path>

Validate the implementation against the plan. Follow your agent instructions exactly.
```

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

## Phase 4.5: ACCEPTANCE GATE [PARALLEL AGENTS]

**Say:** "Spawning ACCEPTANCE GATE (REVIEW agent + QA agent in parallel, session: $SESSION_ID)..."

Spawn REVIEW agent and QA agent simultaneously via two Task tool calls:

**REVIEW agent task prompt:**
```
SESSION_ID=<actual-value>
WORKTREE=<actual-path>

Review spec alignment of the implementation. Follow your agent instructions exactly.
```

**QA agent task prompt:**
```
SESSION_ID=<actual-value>
WORKTREE=<actual-path>

Run test suite and complexity check. Follow your agent instructions exactly.
```

> Note: If context budget guard (Phase 1) is not deployed, spawn sequentially to avoid OOM.

After both complete, verify handoffs exist:

```bash
for handoff in $HANDOFF/05-review-findings.json $HANDOFF/05-qa-findings.json; do
  jq -c . "$handoff" || {
    echo "ERROR: Handoff missing: $handoff"
    echo "Retrying REVIEW and QA agents once..."
    # Re-spawn both agents and retry
    if ! jq -c . "$handoff" 2>/dev/null; then
      echo "FATAL: Handoff still missing after retry. STOP."
      exit 1
    fi
  }
done
```

Then merge findings:

Merge into `$HANDOFF/05-acceptance.json`:
- Combined findings from both agents
- Overall verdict: FAIL if either agent verdict is FAIL, PASS WITH NOTES if any PASS WITH NOTES, else PASS
- Zero critical findings required to proceed

**If any critical or major findings exist in `05-acceptance.json`:**

Spawn FIXER agent:
```
SESSION_ID=<actual-value>
WORKTREE=<actual-path>

Address critical and major findings from acceptance gate. Follow your agent instructions exactly.
```

After FIXER agent completes, re-run REVIEW agent on critical findings only:
```
SESSION_ID=<actual-value>
WORKTREE=<actual-path>

Re-review CRITICAL findings only from 05-acceptance.json. Follow your agent instructions exactly.
```

Update `05-acceptance.json` with re-review results.

**Gate:** Zero critical findings required before proceeding to COMMIT. If critical findings remain after one fixer iteration: **STOP and ASK user.**

**If PASS or PASS WITH NOTES (minor only):** Proceed to COMMIT.

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
gh pr create --title "type: description" --body "$(cat <<'EOF'
## Summary
<bullets from 02-plan.json overview>

## Changes
<files from 03-build.json files_changed>

## Test plan
- [ ] Tests pass (see 03-build.json test_results)
- [ ] Linter clean
- [ ] Security scan clean (see 04-validation.json security_summary)
EOF
)"
```

After PR is created, run AI review via aptu:
- Use `aptu review_pr` on the new PR number
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

- **Python:** uv, ruff, pyright, pytest
- **JavaScript/TypeScript:** bun, biome, vitest
- **Rust:** cargo build/test/clippy/fmt/deny

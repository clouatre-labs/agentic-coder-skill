# AGENTS.md

## Project overview

The `coder` skill: a Scout/Guard orchestration skill for AI coding agents, plus its 4
subagents, a Goose recipe equivalent, and the governance githooks that enforce its
commit/DCO conventions. Markdown (skill + subagent prompts) and YAML (Goose recipe) —
there is no build/test/lint in the traditional sense; the artifacts are prompts and
shell hooks, not compiled code.

## Stack & Commands

```
# build:  n/a (no compiled artifacts)
# test:   n/a (validated by running the pipeline end-to-end against a real issue)
# lint:   bunx markdownlint-cli2 "**/*.md" (Markdown); shellcheck githooks/* (hooks)
# format: n/a
```

## Development standards

- GPG sign and DCO sign-off: `git commit -S --signoff` (every commit)
- Treat all repositories as public; no secrets, API keys, credentials, or PII
- Actions pinned to SHA (not tags); actionlint recommended for local workflow validation
- Training data is stale: verify APIs and versions against installed packages or docs
- Keep `skills/coder/SKILL.md` and `goose/goose-coder.yaml` in workflow-phase sync (see
  each file's own header comment) — they are two harnesses for the same pipeline
- Bump the version and changelog in `skills/coder/SKILL.md`'s frontmatter for any
  behavioral change to the pipeline

## Testing

- One happy path and one edge case per behavior; no redundant variations
- AAA pattern (Arrange, Act, Assert); keep each test focused and short
- There is no automated test suite for the skill/recipe themselves; validate changes by
  running the pipeline against a real GitHub issue in a scratch repo

## Design references

- [README.md](README.md) — pipeline overview and phase diagram
- `skills/coder/SKILL.md` — the orchestrator's own phase-by-phase spec and changelog

## Do not

- Add dependencies without justification in the PR description
- Implement features not specified in the assigned issue
- Modify files outside the scope of the assigned issue
- Change `skills/coder/SKILL.md` without updating `goose/goose-coder.yaml` to match (or
  documenting why they intentionally diverge)

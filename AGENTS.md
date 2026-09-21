# AGENTS.md

## Project overview

The `coder` skill: a Scout/Guard orchestration skill for AI coding agents, plus its 4
subagents, and the governance githooks that enforce its
commit/DCO conventions. Markdown (skill + agent sources) and YAML (per-harness agent
frontmatter) —
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
- Agent files are generated: edit `tools/agents/{pi,claude}-coder-*.yaml` (harness
  frontmatter) and `agents-shared/coder-*.md` (shared body), then run
  `scripts/generate-coder-agents.sh --write`. Never hand-edit `agents/{pi,claude}/*`;
  CI fails on drift (`--check`)
- Bump the version and changelog in `skills/coder/SKILL.md` for any behavioral change
  to the pipeline
- typesafe-ai is an external dependency of the skill: tier classification and the
  handoff degeneracy gate call `api.typesafe.ai` via the dedicated decisions-judge
  MCP server (npm: `decisions-judge-mcp`, repo `clouatre-labs/decisions-judge-mcp`)
  with `TYPESAFE_API_KEY` from the shell env (never committed, never written
  to files or handoffs). Every judge path must keep its deterministic inline fallback;
  this repo documents only the judge's contract (`skills/coder/SKILL.md`,
  Constraints #9–#10 and Handoff Validation)

## Testing

- One happy path and one edge case per behavior; no redundant variations
- AAA pattern (Arrange, Act, Assert); keep each test focused and short
- There is no automated test suite for the skill/agents themselves; validate changes by
  running the pipeline against a real GitHub issue in a scratch repo

## Visual Aids
- Tables and code snippets: caption above (`*Table N: Description*` / `*Code Snippet N: Description*`)
- Figures (images and Mermaid diagrams): caption below (`*Figure N: Description*`)
- Captions: clear, well written, concise; numbered continuously across the document

## Design references

- [README.md](README.md) — pipeline overview and phase diagram
- `skills/coder/SKILL.md` — the orchestrator's own phase-by-phase spec and changelog

## Do not

- Add dependencies without justification in the PR description
- Implement features not specified in the assigned issue
- Modify files outside the scope of the assigned issue
- Hand-edit generated agent files under `agents/pi/` or `agents/claude/`

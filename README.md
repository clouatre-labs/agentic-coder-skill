<p align="center">
  <a href="LICENSE"><img alt="Apache 2.0" src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge" height="20"></a>
  <a href="https://conventionalcommits.org"><img alt="Conventional Commits" src="https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg?style=for-the-badge" height="20"></a>
  <a href="https://github.com/DavidAnson/markdownlint"><img alt="Markdown Lint" src="https://img.shields.io/badge/Markdown-Lint-lightgrey.svg?style=for-the-badge&logo=markdown" height="20"></a>
</p>

<h1 align="center">agentic-coder-skill</h1>

<p align="center">A production Scout/Guard orchestration skill for AI coding agents.</p>

This is the `coder` skill: an orchestration layer that runs coding tasks through a
research-then-build pipeline with an adversarial review gate, delegating each phase to a
purpose-built subagent instead of doing the work inline. It has been in daily production
use since v1.0.0; this repo is the skill at its current version, with real commit
history, not a point-in-time snapshot.

Background: [Orchestrating AI Agents: A Subagent
Architecture](https://clouatre.ca/posts/orchestrating-ai-agents-subagent-architecture)
and [The AI SDLC Governance
Stack](https://clouatre.ca/posts/ai-sdlc-governance-stack) on clouatre.ca.

## Pipeline

```
SETUP -> RESEARCH [scout then guard, sequential] -> [GATE] -> PLAN -> BUILD [delegate] -> CHECK [delegate, draft PR on PASS] -> PR REVIEW & READY
                                                                    |                    |
                                                               FAIL -> Back to BUILD (1x) FAIL -> Stop & Ask
```

The orchestrator classifies every change into one of three tiers (simple, medium,
complex) and scales the pipeline accordingly — a one-line config change skips every
delegate, while an architectural change runs the full SCOUT + GUARD + BUILD + CHECK
chain. Full phase-by-phase detail, including the constraints each delegate operates
under, lives in [`skills/coder/SKILL.md`](skills/coder/SKILL.md) — that file is the spec
and the changelog, not just an entry point.

| Phase | Role |
|---|---|
| SCOUT | Read-only research: relevant files, conventions, candidate approaches |
| GUARD | Read-only adversarial review of Scout's findings: risk, blast radius, safety ranking |
| PLAN | Orchestrator-authored implementation plan, synthesizing Scout + Guard |
| BUILD | Implements the plan, runs tests/lint/format |
| CHECK | Validates the diff against the plan; on PASS, commits and opens a draft PR |

## What's here

| Path | Description |
|---|---|
| `skills/coder/SKILL.md` | The skill itself — entry point, phase spec, and version history |
| `agents/coder-scout.md` | SCOUT subagent |
| `agents/coder-guard.md` | GUARD subagent |
| `agents/coder-build.md` | BUILD subagent |
| `agents/coder-check.md` | CHECK subagent |
| `goose/goose-coder.yaml` | The same pipeline as a [Goose](https://github.com/aaif-goose/goose) recipe |
| `githooks/` | Local governance hooks: conventional commits, DCO sign-off, protected-branch enforcement, branch hygiene |

## Two harnesses, one pipeline

`skills/coder/SKILL.md` (Claude Code, Codex) and `goose/goose-coder.yaml` (Goose) both
implement the same SETUP -> SCOUT/GUARD -> PLAN -> BUILD -> CHECK -> PR pipeline for
their respective harnesses; each file's header comment points at its counterpart and
both are kept in phase-for-phase sync. This is not a migration from one to the other —
both are maintained in parallel today, because the skill format isn't universally
supported yet. The skill format is the direction this is heading: it is markdown, not a
harness-specific YAML schema, so it is the more portable of the two, and new pipeline
changes land there first.

## Githooks

Install with:

```bash
git config core.hooksPath githooks
```

- `commit-msg` — Conventional Commits format, DCO sign-off, no `Co-authored-by:` trailers
- `pre-commit` — blocks direct commits to `main`/`master`/`release/*`; verifies the
  committer's signing key against a `~/.gitconfig-*`-per-identity convention (adapt this
  check to your own identity-management setup, or drop it, if you don't use that
  convention)
- `pre-push` — blocks direct pushes to protected branches
- `post-checkout` — prunes local branches whose remote tracking branch is gone, on
  checkout to `main`/`master`

These are the same conventions `coder-check`'s commit/PR step assumes are in place.

## License

[Apache 2.0](LICENSE)

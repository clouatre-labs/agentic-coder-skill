# PR Review Instructions

## Grounding rules

- Only flag issues you can cite directly from the diff. If you cannot point to a specific line,
  do not raise the comment.
- If you are unsure whether something is a bug or intentional, say so explicitly rather than
  asserting it is wrong.
- Do not apply general knowledge about a language or framework if the diff does not contain
  evidence of a violation. If project conventions are documented in `AGENTS.md`, cite that
  file when referencing a rule.

## Scope

Review only what the PR changes. Do not flag issues in files the PR does not touch.

## Workflow files (.github/workflows/)

- Flag `${{ expression }}` interpolation directly inside `run:` scripts as an injection risk;
  inputs should be passed via `env:` blocks.
- Verify action pins use commit SHAs, not mutable tags.
- Check that `permissions:` blocks are present and minimal.

## Source code

<!-- Replace this section with rules for your project's primary language. -->
<!-- Keep the example below, or adapt it for Python, TypeScript, Go, etc. -->

- Do not flag `.unwrap()` in test code; it is acceptable there.
- Do not suggest adding dependencies without a justification visible in the diff.
- Do not comment on style that the project's formatter or linter (e.g., `cargo fmt`,
  `cargo clippy`) would catch automatically; those are enforced by CI.

## General

- One comment per distinct issue; do not duplicate findings across multiple inline comments.
- Prefer a suggestion block over describing the problem when the fix is unambiguous.
- If you have no findings, say so. Do not invent issues to appear thorough.

## Adopter Notes

This file is read by the aptu GitHub App during automated PR review. Replace the
**Source code** section above with rules specific to your project's language and
toolchain. Add additional sections (Testing, Dependencies, Security) as needed.
Keep instructions concise: prefer short imperative rules over long paragraphs.
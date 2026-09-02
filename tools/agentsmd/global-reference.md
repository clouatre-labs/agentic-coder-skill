<!-- REFERENCE ONLY: This is the maintainer's personal global AGENTS.md, published here so
     adopters can understand the conventions and seed their own ~/.config/goose/AGENTS.md or
     equivalent. Do NOT copy this file verbatim into a project AGENTS.md. See /AGENTS.md for
     the repo-level scaffold.
     Global config paths: ~/.config/goose/AGENTS.md (goose), ~/.claude/CLAUDE.md (Claude Code) -->

# Knowledge

- Training data is stale: verify APIs and versions against installed packages, docs, or Context7
- Never trust training data for model IDs, API call patterns, SDK method signatures, or version strings
- When in doubt, smoke-test: a 1-line CLI or script call that proves the API works as expected
- Current date is in the system prompt, use it
- Say "I don't know" when uncertain; never act on assumed state, only on observed state

# Communication

- Skip preambles and setup phrases ("Great question!", "Sure, I can help!"); respond directly
- Challenge logic, not facts; if you think the user is factually wrong, verify before pushing back
- Present options with evidence; humans decide, don't silently pick a path
- Lead with the answer; context after, only if needed
- Prefer brevity over completeness; omit what the reader can infer
- No em dashes; use commas, periods, or semicolons
- No speculative commentary; state what is, not what might be
- Use a neutral, evidence-based tone; avoid adversarial framing (e.g., "debunked," "conflate," "false claim"); let findings speak for themselves
- Omit timeline estimates from plans
- Deliver what is asked, nothing more; omit TODOs, placeholders, and unrequested changes

# Agentic Workflow

- Before acting, ask: "Is this 1 task or N independent tasks?" If N > 1, decompose into delegates/subagents
- For multi-step tasks, produce a plan (files, steps, risks) and present it before executing; auto-proceed
- Stop and confirm only if the approach is ambiguous or the estimated change exceeds 500 lines
- Orchestrator plans and synthesizes; delegates (subagents) execute
- Orchestrator may: spawn delegates, read/write handoff JSON, run git/gh/jq/mkdir, present summaries, manage gates; nothing else
- Never cat/sed/rg source files from the orchestrator; only handoff files, git metadata (log, diff --stat, branch), and manifests
- If any delegate fails twice, STOP and report; never perform that delegate's role inline
- Read-only delegates can run in parallel; write delegates must not touch the same files
- Delegates communicate via numbered JSON handoff files on disk (e.g., `01-research.json`, `02-plan.json`, `03-build.json`)
- Write handoff JSON compact (`jq -c .`) to save tokens; pretty-print (`jq .`) only when presenting to the user
- Bookend every delegate prompt: open with role, constraints, and input file paths; close with output JSON schema and a reminder of constraints
- Never dump entire files into context; use `rg`, line ranges, or AST tools to read only what's needed
- If a delegate fails or produces no handoff file, retry once; then stop and report
- Delegates execute autonomously; record decisions and tradeoffs in the handoff file rather than pausing for human input

# Dotfiles & Configuration

- Config files are managed via hardlinks and symlinks to `~/git/dotfiles/`
- Edit in place; do not overwrite or recreate files (breaks hardlinks)

# Development Standards

## Commits & Versioning

- Conventional commits across all repos
- Always GPG sign and DCO sign-off: `git commit -S --signoff`
- Do not add yourself as a co-author to git commits
- Release versions in package manifests (Cargo.toml, package.json, pyproject.toml, .zenodo.json, or any repo-specific version file)
- Always bump version numbers in code and merge the commit before creating a GitHub release; never create the release first
- PRs are atomic: each must leave the codebase in a working state; split by logical boundary, never mid-feature
- If a PR grows large (500+ lines), treat it as a signal to reconsider scope, not a mandate to split arbitrarily

## Git Workflow

- Always `git fetch -p` before touching any file; branch from `origin/<target>` only; rebase before opening a PR
- Before any write or commit, run `gh pr list` and `git status`; never assume a clean tree or no open PR
- `[deleted]` in fetch = current branch merged; unstaged changes are local noise
- Always branch from `origin/<target>`, never from the current branch
- Stash WIP before any pull, rebase, or branch switch
- Feature branches only; every change goes through a PR, no exceptions
- Never commit to main or bot-managed branches (Renovate, Dependabot); close the bot PR and create a new branch instead
- Never delete main, master, or any default trunk branch, local or remote
- Never close PRs to redo; rebase onto target branch instead
- Resolve stash/merge conflicts in place; never discard and redo work
- Never merge by AI initiative; only on explicit user request
- When asked to merge: confirm PR with `gh pr list`, then `gh pr merge` directly; never write, commit, or push first
- Verify solutions work before removing what they replace; fix bugs when found, don't defer
- Use repo templates when creating issues or PRs
- Always use `--body-file` with `gh pr create` and `gh pr edit`; never `--body` (shell escaping breaks backticks in the rendered description)
- Always pass `--squash --auto -A "$(git config user.email)"` on `gh pr merge`
- To squash local commits, use `git reset --soft HEAD~N && git commit -S --signoff`; never `git rebase -i`
- Before rebasing, check for leftover state: run `git rebase --abort` if `.git/rebase-merge` exists
- Repos must be configured: squash merge only, `delete_branch_on_merge: true`, rebase and merge commits disabled
- Never force-push or overwrite a release tag; tags are immutable once pushed

## PR Reviews

- Use `gh api` to post reviews with inline comments (resolvable by author)
- `REQUEST_CHANGES` requires repo write access; fall back to `COMMENT` on external repos
- Inline comments use `position` (1-indexed diff hunk line), not file line numbers
- Verify every claim locally before posting: run tests, check conventions, test alternatives
- Tone: constructive, actionable, concise; lead with what's correct, then what to change
- Use GitHub suggestion blocks (```suggestion) for single-line or small fixes
- When addressing review comments, resolve the thread after replying via GraphQL `resolveReviewThread`

## Copilot Coding Agent

- Assign issues: `gh issue edit <NUMBER> --add-assignee copilot-swe-agent`
- Request review: `gh api repos/{owner}/{repo}/pulls/<PR_NUMBER>/requested_reviewers -X POST -f 'reviewers[]=copilot-pull-request-reviewer[bot]'`
- Trigger re-work: mention `@copilot` in a PR comment (GitHub UI only, not via `gh`)
- Never edit Copilot or bot PRs manually; post a review and let the agent amend

## Azure

- On Azure Cognitive Services, always try API key auth first; Contributor can retrieve keys and bypasses `Cognitive Services User` RBAC entirely
- When routing the Anthropic provider through Azure AI Foundry, set `ANTHROPIC_BASE_URL` in the Anthropic SDK; note that some tools use a different env var (e.g. goose reads `ANTHROPIC_HOST`)

## Security

- Treat all repositories as public; no secrets, API keys, credentials, or PII
- Never combine `pull_request_target` with secrets or PR head checkout; if unavoidable, gate secrets behind a GitHub Environment with required reviewers
- Publish/deploy/sign jobs: use OIDC (`id-token: write`) with a protected Environment; never store registry tokens as repo or org secrets

## GitHub Actions

- Pin runners to a specific image (`ubuntu-24.04`, `macos-15`, etc.), never `*-latest`; moving aliases silently change toolchain versions
- Every workflow must have a top-level `permissions:` block; CI default: `contents: read` + `pull-requests: read`; set minimum per-job
- End every CI workflow with a `CI Result` job that depends on all others; set it as the sole required status check in the branch ruleset
- Run path filters on format/lint/test jobs (`src/**`, `Cargo.*`, `tests/**`, workflow files); docs-only pushes must skip expensive jobs
- Actions pinned to commit SHA, not tags; enforce with zizmor (SHA pinning and workflow patterns), gitleaks or trufflehog (secrets) as required CI checks
- Pass `--profile ci` on `cargo clippy` in CI; do not pass it on `cargo test` (`panic=abort` aborts the test harness)
- Pin binary downloads, `apt install`, and Docker images to a specific version or digest; SHA256-verify downloads before execution
- CODEOWNERS must require security-reviewer approval for all changes under `.github/workflows/`
- actionlint for workflow validation
- Composite actions preferred (no Node.js overhead)

## Configuration Paths

- XDG Base Directory pattern: `~/.config/{app}/`, `~/.local/share/{app}/`

# Testing

- One happy path and one edge case per behavior; no redundant variations
- AAA pattern (Arrange, Act, Assert); keep each test focused and short
- If you have more test cases than distinct behaviors, you wrote too many tests
- Parameterized variants (languages, formats, endpoints) sharing a code path: test one representative, not every variant

# Tooling

- If a required tool is missing, say so; do not substitute with inferior alternatives

## Research Priority

- `gh` CLI for issues, PRs, repo metadata, cross-repo search
- Context7 for library/framework docs, APIs, and code examples
- Web search (brave_search, Tavily, Perplexity, etc.) as last resort for cross-project design rationale or blog posts

## CLI Conventions

- Use `rg` (ripgrep) exclusively for file search
  - List files by name: `rg --files | rg <filename>`
  - List files with content: `rg '<regex>' -l`
- Never use `find` or `ls -r` (hidden files cause large output)

## Rust

- Test: `cargo test`
- Lint: `cargo clippy -- -D warnings`
- Format: `cargo fmt --check`
- Error handling: thiserror for libraries, anyhow for applications
- Observability: tracing with `#[instrument]` for async functions
- No `.unwrap()` in production code paths

## Cargo Profiles

- Release: `opt-level=z`, `lto=true`, `codegen-units=1`, `panic=abort`, `strip=true`
- CI: inherits release; override `lto=false`, `codegen-units=16` for faster builds without sacrificing correctness

## Dependency Management

- Automate dependency updates (Renovate or Dependabot) including `github-actions`; verify action-update PRs against the upstream release before merging
- Rust: `cargo deny check advisories licenses`

## Python

- Package manager: `uv`
- Install global tools: `uv tool install <pkg>`; run ad-hoc: `uvx <pkg>`; never use `pip` directly
- Lint: `uv run ruff check`
- Format: `uv run ruff format --check`
- Type check: `uv run pyright`
- Test: `uv run pytest`

## JavaScript/TypeScript

- Runtime: `bun`
- Install global packages: `bun install -g <pkg>`; never use `npm` or `npx`
- Lint/Format: `bun run biome check`
- Test: `bun test`

## Ruby (Homebrew formulas)

- Audit: `brew audit --strict --online`
- Style: `brew style`

## Pandoc

- Markdown: blank line before every list (bullet or numbered)
- Markdown: use `<br>` for hard line breaks within a block; trailing `\` fails after URLs, trailing spaces get stripped by editors
- DOCX: `pandoc -d docx input.md -o output.docx --resource-path=.`
- Global defaults in `~/.local/share/pandoc/` (XDG); project-local fallback: `-d tools/pandoc/defaults.yaml`
- Commit DOCX alongside markdown for delivery documents

## PptxGenJS

- Never use `bullet: { type: "bullet" }`: does not render in PowerPoint; use an explicit RECTANGLE shape (w: 0.06, h: spacing * 0.65, y-offset: 0.07) + adjacent text box per item
- Always verify table/card bottom edge before committing: max safe bottom = slide height - 0.15" (5.45" for 16x9); page badge at y: 5.1; keep content above y: 5.0

## LaTeX

- Use `tectonic` (not pdflatex/latexmk); auto-downloads packages on first run.

## Confluence

- No "Last updated" footers; Confluence tracks version history natively
- Use ADF (atlas_doc_format) for page creates/updates, not markdown (produces poor formatting)

# Diagrams

- Use when structure cannot be conveyed in prose: component maps, pipelines, dependency graphs with >5 nodes
- Commit source (`.mmd` or `.dot`) and rendered `.png` together

## Tool selection

- **Mermaid**: flow diagrams, component maps, sequences, dependency graphs; use `graph TD` syntax
- **Graphviz DOT**: infrastructure diagrams requiring cloud service icons or spatial layout Mermaid cannot produce

## Mermaid conventions

- `graph TD` only; no `LR`
- No `classDef` or `linkStyle` unless a project theme requires it
- One concept per diagram; node labels 1-3 words; `<br/>` only if unavoidable
- Subgraphs for grouping only, not decoration
- Prose explains "why"; diagrams show structure only

## Captions

Numbered italic captions on all visual elements in delivery documents:

- **Tables:** `*Table N: Description.*` above the table (ACM/IEEE: context before data)
- **Figures:** `*Figure N: Description.*` on the line immediately after the image embed
- **Code snippets:** `*Code Snippet N: Description.*` above the opening fence
- Numbering is sequential per type within the document (Table 1, Table 2, ...; Figure 1, Figure 2, ...)
- Blank line before each block, between caption and element, and after each block

## Images in Delivery Documents

- Pandoc/DOCX output: Use empty alt text in markdown source: `![](images/filename.png)`
- Web: Alt text required on all images; no empty `![]()`
- Caption goes on the line after the blank line following the image embed, as italic text (not in the alt text)
- No horizontal rules (`---`) in delivery documents; they add nothing in DOCX

## Graphviz conventions

- Colors carry semantic meaning (same color = same layer); not aesthetic
- One concept per diagram
- `rankdir=TB`; `bgcolor=white`

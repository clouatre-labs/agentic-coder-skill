# Pipeline Telemetry: Gate Outcomes, 2026-09-21 to 2026-10-21

The `coder` skill appends one JSONL line per gate decision to
`${CODER_LOG_DIR:-$HOME/.local/state/var/coder-log}/<host>.jsonl` (SKILL.md
Constraint #10). This page summarizes one maintainer machine's log over the
window above, plus the CHECK verdicts in the session handoff directories still
present on that machine. All numbers come from
[`coder-log-aggregate.json`](coder-log-aggregate.json), which contains counts
and judge confidences only: no session ids, paths, repository names, hostnames,
or issue text.

## Gate outcomes

*Table 1: Decisions per gate. Premise and plan-completeness counts are log
lines; CHECK counts are `04-validation.json` files, by recorded `verdict`.*

| Gate | Outcomes | Total |
|---|---|---|
| Tier classification (judge) | 173 confirmed, 14 promoted, 10 demoted | 197 |
| Premise gate | 72 proceed, 3 soften, 2 stop | 77 |
| Plan completeness | 19 proceed | 19 |
| CHECK | 90 pass, 25 pass with notes, 11 fail, 9 request changes, 1 retry complete, 3 missing | 139 |

## Tier judge agreement

The orchestrator proposes a tier from repository facts with no LLM call, and one
`judge` call confirms, promotes, or demotes it. The judge confirmed 88% of the
proposals, and the changes ran in both directions. No change spans two tiers;
this follows from the design, since each judge answer moves the proposal at most
one step.

![Heatmap of proposed versus final tier: 30, 98, and 45 confirmed on the diagonal; 7 simple to medium, 5 medium to simple, 7 medium to complex, 5 complex to medium; no simple-complex changes](../../figures/fig-tier-agreement.png)

*Figure 1: Proposed tier (rows) against final tier after the judge (columns),
197 tier decisions; source
[`figures/fig-tier-agreement.py`](../../figures/fig-tier-agreement.py).*

## Judge confidence

When the judge changed a proposal, it reported lower confidence than when it
confirmed one: mean 0.474 against 0.700, with non-overlapping bootstrap 95%
CIs. The judge overrides the deterministic proposal mostly when it is less
certain.

![Strip plot of judge confidence: 170 confirmed decisions with mean 0.700, CI 0.668 to 0.732; 24 changed decisions with mean 0.474, CI 0.386 to 0.564](../../figures/fig-judge-confidence.png)

*Figure 2: The `confidence` value returned with each tier decision, confirmed
(n = 170) against changed (n = 24), with mean and bootstrap 95% CI (10,000
resamples, seed 42); source
[`figures/fig-judge-confidence.py`](../../figures/fig-judge-confidence.py).*

## Scope and caveats

- One machine, logged by the skill itself; the window spans several skill
  versions, and test or experimental sessions are not filtered out.
- 6 of 588 log lines are malformed and skipped; 2 tier decisions with a final
  tier off the simple/medium/complex ladder are excluded from Figure 1, and 3
  without a numeric confidence from Figure 2.
- Judge confidence is the model's own reported value, not a calibrated
  probability.
- CHECK counts cover only handoff directories not yet removed by manual GC.

## Regenerate

*Code Snippet 1: Rebuild the aggregate and both figures.*

```bash
scripts/coder-stats.sh > docs/evidence/coder-log-aggregate.json
uv run --with matplotlib python figures/fig-tier-agreement.py
uv run --with matplotlib python figures/fig-judge-confidence.py
```

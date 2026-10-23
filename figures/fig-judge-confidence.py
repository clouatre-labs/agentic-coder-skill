"""Figure: tier judge confidence, confirmed vs. changed proposals.

Data source: docs/evidence/coder-log-aggregate.json (judge_confidence), produced
by scripts/coder-stats.sh from the coder-log JSONL (stage "tier" lines).
Means with bootstrap 95% CIs (10,000 resamples, seed 42); jitter seeded.
Regenerate: python3 figures/fig-judge-confidence.py  (requires matplotlib)
"""
import json
import random
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

with open("docs/evidence/coder-log-aggregate.json") as f:
    conf = json.load(f)["judge_confidence"]

GROUPS = [("Confirmed", conf["confirmed"], "#2ca02c"),
          ("Changed\n(promoted or demoted)", conf["changed"], "#d62728")]


def bootstrap_ci(values, rng, n=10_000):
    """Percentile 95% CI of the mean."""
    means = sorted(statistics.fmean(rng.choices(values, k=len(values)))
                   for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


rng = random.Random(42)
fig, ax = plt.subplots(figsize=(6.4, 4.2))

for x, (label, values, color) in enumerate(GROUPS):
    xs = [x + rng.uniform(-0.18, 0.18) for _ in values]
    ax.scatter(xs, values, s=14, alpha=0.45, color=color, linewidths=0)
    mean = statistics.fmean(values)
    lo, hi = bootstrap_ci(values, rng)
    ax.errorbar(x + 0.32, mean, yerr=[[mean - lo], [hi - mean]], fmt="_",
                markersize=18, color="#333333", capsize=4, linewidth=1.2)
    ax.text(x + 0.42, mean, f"{mean:.3f}\n[{lo:.3f}, {hi:.3f}]",
            va="center", fontsize=8.5, color="#333333")
    ax.text(x, -0.08, f"n = {len(values)}", ha="center", fontsize=9,
            color="#555555")

ax.set_xticks(range(len(GROUPS)), [g[0] for g in GROUPS])
ax.set_xlim(-0.5, len(GROUPS) - 0.1)
ax.set_ylim(-0.13, 1.02)
ax.set_ylabel("Judge confidence", fontsize=10)
ax.spines[["top", "right"]].set_visible(False)

plt.tight_layout()
plt.savefig("figures/fig-judge-confidence.png", dpi=150, bbox_inches="tight")
print("Saved figures/fig-judge-confidence.png")

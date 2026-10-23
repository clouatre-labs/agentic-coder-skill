"""Figure: cost per coder session by highest tier, log scale.

Data source: docs/evidence/pi-coder-aggregate.json (per_session_cost_by_tier),
produced by scripts/pi-coder-stats.py from pi session logs (orchestrator from
skill invocation onward plus its coder-* delegates). Jitter seeded.
Regenerate: python3 figures/fig-session-cost.py  (requires matplotlib)
"""

import json
import random
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

with open("docs/evidence/pi-coder-aggregate.json") as f:
    by_tier = json.load(f)["per_session_cost_by_tier"]

GROUPS = [
    ("Simple", "simple", "#1f77b4"),
    ("Medium", "medium", "#ff7f0e"),
    ("Complex", "complex", "#d62728"),
    ("No tier recorded", "none", "#7f7f7f"),
]

rng = random.Random(42)
fig, ax = plt.subplots(figsize=(7.2, 4.2))

for x, (label, key, color) in enumerate(GROUPS):
    values = by_tier.get(key, [])
    xs = [x + rng.uniform(-0.2, 0.2) for _ in values]
    ax.scatter(xs, values, s=14, alpha=0.5, color=color, linewidths=0)
    median = statistics.median(values)
    ax.hlines(median, x - 0.3, x + 0.3, color="#333333", linewidth=1.6)
    ax.text(
        x + 0.33, median, f"${median:.2f}", va="center", fontsize=8.5, color="#333333"
    )
    ax.text(x, 1.6, f"n = {len(values)}", ha="center", fontsize=9, color="#555555")

ax.set_yscale("log")
ax.set_ylim(0.001, 2.5)
ax.set_yticks([0.001, 0.01, 0.1, 1], ["$0.001", "$0.01", "$0.10", "$1"])
ax.set_xticks(range(len(GROUPS)), [g[0] for g in GROUPS])
ax.set_xlim(-0.5, len(GROUPS) - 0.3)
ax.set_ylabel("Cost per coder session (USD, log scale)", fontsize=10)
ax.spines[["top", "right"]].set_visible(False)

plt.tight_layout()
plt.savefig("figures/fig-session-cost.png", dpi=150, bbox_inches="tight")
print("Saved figures/fig-session-cost.png")

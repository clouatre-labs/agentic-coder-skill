"""Figure: tier judge agreement, proposed vs. final tier.

Data source: docs/evidence/coder-log-aggregate.json (tier_agreement), produced
by scripts/coder-stats.sh from the coder-log JSONL (stage "tier" lines).
Regenerate: python3 figures/fig-tier-agreement.py  (requires matplotlib)
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

with open("docs/evidence/coder-log-aggregate.json") as f:
    agg = json.load(f)["tier_agreement"]

LABELS = [t.capitalize() for t in agg["order"]]
MATRIX = agg["matrix"]
TOTAL = sum(map(sum, MATRIX))

fig, ax = plt.subplots(figsize=(5.2, 4.4))
im = ax.imshow(MATRIX, cmap="Greens", vmin=0)

for i, row in enumerate(MATRIX):
    for j, n in enumerate(row):
        color = "white" if n > max(map(max, MATRIX)) / 2 else "#333333"
        weight = "bold" if i == j else "normal"
        ax.text(j, i, str(n), ha="center", va="center",
                fontsize=12, color=color, fontweight=weight)

ax.set_xticks(range(len(LABELS)), LABELS)
ax.set_yticks(range(len(LABELS)), LABELS)
ax.set_xlabel("Final tier (after judge)", fontsize=10)
ax.set_ylabel("Proposed tier (deterministic)", fontsize=10)
ax.set_title(
    f"Confirmed {agg['confirmed']}/{TOTAL}; "
    f"promoted {agg['promoted']}, demoted {agg['demoted']}",
    fontsize=10,
)
ax.tick_params(length=0)
for spine in ax.spines.values():
    spine.set_visible(False)

plt.tight_layout()
plt.savefig("figures/fig-tier-agreement.png", dpi=150, bbox_inches="tight")
print("Saved figures/fig-tier-agreement.png")

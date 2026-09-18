"""Figure: pipeline phases executed per change tier.

Data source: skills/coder/SKILL.md, Constraint #2 (tier classification).
Regenerate: python3 figures/fig-tier-pipeline.py  (requires matplotlib)
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

PHASES = ["Setup", "SCOUT", "GUARD", "PLAN", "BUILD", "CHECK", "Draft PR"]
TIERS = ["Simple", "Medium", "Complex"]
# Which phases each tier runs, per SKILL.md Constraint #2 / Table 1.
RUNS = {
    "Simple": {"Setup", "Draft PR"},  # inline implementation, no delegates
    "Medium": {"Setup", "SCOUT", "PLAN", "BUILD", "Draft PR"},
    "Complex": set(PHASES),
}
RUN_COLOR = "#2ca02c"
SKIP_COLOR = "#d9d9d9"

fig, ax = plt.subplots(figsize=(9, 3.4))
ax.set_xlim(0, len(PHASES))
ax.set_ylim(0, len(TIERS))
ax.invert_yaxis()
ax.axis("off")

for col, phase in enumerate(PHASES):
    ax.text(col + 0.5, -0.25, phase, ha="center", va="bottom",
            fontsize=10, fontweight="bold")

for row, tier in enumerate(TIERS):
    ax.text(-0.12, row + 0.5, tier, ha="right", va="center",
            fontsize=10, fontweight="bold")
    for col, phase in enumerate(PHASES):
        runs = phase in RUNS[tier]
        box = FancyBboxPatch(
            (col + 0.12, row + 0.14), 0.76, 0.72,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            facecolor=RUN_COLOR if runs else SKIP_COLOR,
            edgecolor="#555555", linewidth=0.6,
        )
        ax.add_patch(box)
        if runs and col + 1 < len(PHASES) and PHASES[col + 1] in RUNS[tier]:
            ax.add_patch(FancyArrowPatch(
                (col + 0.92, row + 0.5), (col + 1.12, row + 0.5),
                arrowstyle="-|>", mutation_scale=9,
                color="#555555", linewidth=0.9,
            ))
        if not runs:
            ax.text(col + 0.5, row + 0.5, "skip", ha="center", va="center",
                    fontsize=7.5, color="#777777")

ax.text(0.5, -0.62, "green = phase runs    gray = phase skipped",
        ha="center", fontsize=8.5, color="#555555", transform=ax.transData)

plt.tight_layout()
plt.savefig("figures/fig-tier-pipeline.png", dpi=150, bbox_inches="tight")
print("Saved figures/fig-tier-pipeline.png")

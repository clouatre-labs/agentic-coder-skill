"""Figure: Gantt timeline of one parallel multi-agent coding session.

Data source: one pi session transcript (September 2026), five refactoring
issues in a Rust workspace across 5 parallel session lanes. Bars span subagent
spawn -> completion, in minutes from kickoff, extracted from the transcript.
Regenerate: python3 figures/fig-session-timeline.py  (requires matplotlib)
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory

# (start, end, kind, row) in minutes from kickoff -- rows: 0..4 = issues A..E.
# Kinds: SCOUT, GUARD, BUILD, CHECK; suffix "_FAIL" draws a hatched red overlay.
BARS = [
    # Issue A
    (3.3, 5.3, "SCOUT", 0),
    (8.0, 18.1, "BUILD", 0),
    (19.2, 24.9, "CHECK", 0),
    (34.6, 35.4, "RETRY", 0),   # amend doc comment
    # Issue B
    (3.3, 5.1, "SCOUT", 1),
    (8.0, 19.0, "BUILD", 1),
    (19.7, 23.3, "CHECK_FAIL", 1),  # missing tests
    (34.6, 37.9, "RETRY", 1),   # BUILD retry: add tests
    (41.5, 48.7, "CHECK", 1),
    (49.1, 49.6, "FIX", 1),     # semver bump
    (92.2, 93.7, "RETRY", 1),   # rebase (after issue C's PR landed)
    # Issue C
    (3.3, 5.2, "SCOUT", 2),
    (8.0, 18.3, "BUILD", 2),
    (19.2, 22.4, "CHECK_FAIL", 2),  # branch mismatch
    (23.5, 26.2, "CHECK", 2),
    (39.6, 40.4, "FIX", 2),     # semver bump
    # Issue D
    (3.3, 4.3, "SCOUT", 3),
    (5.8, 10.5, "BUILD", 3),
    (11.7, 14.6, "CHECK", 3),
    # Issue E
    (3.3, 5.9, "SCOUT", 4),
    (8.7, 10.2, "GUARD", 4),
    (11.1, 15.9, "BUILD", 4),
    (16.4, 23.3, "CHECK", 4),
]

LANES = ["Issue A", "Issue B", "Issue C", "Issue D", "Issue E"]

COLOR = {
    "SCOUT": "#1f77b4",
    "GUARD": "#9467bd",
    "BUILD": "#2ca02c",
    "CHECK": "#ff7f0e",
    "RETRY": "#8c564b",
    "FIX": "#d62728",
}

# Merge time per lane (from GitHub), minutes from kickoff, with merge order.
MERGES = {0: (69.1, 2), 1: (98.7, 5), 2: (91.5, 4), 3: (63.0, 1), 4: (79.3, 3)}

# Quiet stretch: review-gate retries + CI + waiting on the human go-ahead.
WAIT0, WAIT1 = 26.2, 60.8

# Three human steering interventions (dashed vertical markers).
INTERVENTIONS = [
    (1.5, "approve parallel plan"),
    (34.0, "authorize fallback review provider"),
    (62.5, "authorize ordered merge"),
]

T0, T1 = 0, 103.0
MERGE0, MERGE1 = 62.5, 99.5

fig, ax = plt.subplots(figsize=(12.5, 5.0))
ax.set_xlim(T0, T1)
ax.set_ylim(-0.2, len(LANES))
ax.invert_yaxis()

# Merge window band
ax.axvspan(MERGE0, MERGE1, color="#4caf50", alpha=0.10, zorder=0)
ax.text(MERGE0 + 1, -0.05,
        "ordered merges (CI-gated)",
        ha="left", va="bottom", fontsize=8, color="#2e7d32", style="italic")

# Lane labels (anchored to the left axes edge, so no dead margin)
tr = blended_transform_factory(ax.transAxes, ax.transData)
for row, lane in enumerate(LANES):
    ax.text(-0.012, row + 0.5, lane, transform=tr, ha="right", va="center",
            fontsize=9, fontweight="bold")
    if row:
        ax.axhline(row, color="#e0e0e0", linewidth=0.6, zorder=0)

# Waiting band (review gate + CI + human review)
ax.axvspan(WAIT0, WAIT1, color="#9e9e9e", alpha=0.10, zorder=0)
ax.text(35.0, -0.05, "review gate + CI",
        ha="left", va="bottom", fontsize=8, color="#616161", style="italic")

# Merge markers per lane, labeled with merge order
for row, (x, order) in MERGES.items():
    ax.plot(x, row + 0.5, marker="D", markersize=7, color="#2e7d32",
            markeredgecolor="#1b5e20", zorder=4)
    ax.annotate(f"merge {order}", (x, row + 0.5), xytext=(0, 9),
                textcoords="offset points",
                ha="center", fontsize=7.5, color="#1b5e20", fontweight="bold",
                zorder=5)

BAR_H = 0.56
for x0, x1, kind, row in BARS:
    base = kind[:-5] if kind.endswith("_FAIL") else kind
    ax.add_patch(plt.Rectangle(
        (x0, row + (1 - BAR_H) / 2), x1 - x0, BAR_H,
        facecolor=COLOR[base],
        edgecolor="#b71c1c" if kind.endswith("_FAIL") else "#555555",
        linewidth=1.2 if kind.endswith("_FAIL") else 0.5,
        linestyle="--" if kind.endswith("_FAIL") else "-",
        zorder=3,
    ))

# Label the one rebase bar (its cause is not obvious from the bar alone)
ax.annotate("rebase (issue C merged first)", (92.2, 1.5), xytext=(-7, 0),
            textcoords="offset points", ha="right", va="center",
            fontsize=7, color="#5d4037", zorder=5)

# Human interventions: dashed vlines + numbered markers
for i, (x, label) in enumerate(INTERVENTIONS, 1):
    ax.axvline(x, color="#555555", linestyle=":", linewidth=1.0, zorder=1)
    ax.plot(x, -0.2, marker="v", color="#555555", clip_on=False, zorder=4)
    ax.text(x, -0.08, str(i), ha="center", va="center",
            fontsize=8, fontweight="bold", color="#333333",
            bbox=dict(boxstyle="circle,pad=0.15", fc="white", ec="#555555", lw=0.7))

ax.set_xticks(range(0, 111, 15))
ax.set_xticklabels(str(m) for m in range(0, 111, 15))
ax.set_xlabel("minutes from kickoff", fontsize=9)
ax.set_yticks([])
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)

handles = [Patch(facecolor=c, edgecolor="#555555", label=k.title())
           for k, c in COLOR.items()]
handles.append(Patch(facecolor="white", edgecolor="#b71c1c", linestyle="--",
                     label="Check fail"))
handles.append(plt.Line2D([0], [0], color="#555555", linestyle=":", marker="v",
                          label="Human intervention"))
handles.append(plt.Line2D([0], [0], color="#2e7d32", linestyle="none", marker="D",
                          label="Merged"))
ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.14),
          fontsize=8, ncol=4, frameon=False)

ax.set_title("Five issues, five parallel sessions, five merged PRs "
             "(minutes from kickoff)", fontsize=11)

plt.tight_layout()
plt.savefig("figures/fig-session-timeline.png", dpi=150, bbox_inches="tight")
print("Saved figures/fig-session-timeline.png")

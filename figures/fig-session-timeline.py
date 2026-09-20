"""Figure: Gantt timeline of one parallel multi-agent coding session.

Data source: session transcript 01a0ba3a (2026-09-19), repo aptu-coder,
issues #1578-#1582 across 5 parallel session lanes. Bars span actual subagent
spawn -> completion timestamps extracted from the transcript.
Regenerate: python3 figures/fig-session-timeline.py  (requires matplotlib)
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

def t(hhmmss):
    """Minutes since session start (15:13:00), the figure's t=0."""
    h, m, s = map(int, hhmmss.split(":"))
    return (h * 3600 + m * 60 + s - t.ZERO) / 60.0

t.ZERO = 15 * 3600 + 13 * 60

# (start, end, kind, row) -- rows: 0..4 = lanes for #1578 #1579 #1580 #1581 #1582.
# Kinds: SCOUT, GUARD, BUILD, CHECK; suffix "_FAIL" draws a hatched red overlay.
BARS = [
    # Lane #1578 (PR #1586)
    ("15:16:20", "15:18:20", "SCOUT", 0),
    ("15:21:01", "15:31:03", "BUILD", 0),
    ("15:32:09", "15:37:53", "CHECK", 0),
    ("15:47:38", "15:48:22", "RETRY", 0),   # amend doc comment
    # Lane #1579 (PR #1588)
    ("15:16:20", "15:18:08", "SCOUT", 1),
    ("15:21:01", "15:32:01", "BUILD", 1),
    ("15:32:41", "15:36:16", "CHECK_FAIL", 1),  # missing tests
    ("15:47:38", "15:50:54", "RETRY", 1),   # BUILD retry: add tests
    ("15:54:29", "16:01:41", "CHECK", 1),
    ("16:02:08", "16:02:37", "FIX", 1),     # semver bump
    ("16:45:10", "16:46:41", "RETRY", 1),   # rebase #1588
    # Lane #1580 (PR #1587)
    ("15:16:20", "15:18:11", "SCOUT", 2),
    ("15:21:01", "15:31:16", "BUILD", 2),
    ("15:32:09", "15:35:22", "CHECK_FAIL", 2),  # branch mismatch
    ("15:36:31", "15:39:09", "CHECK", 2),
    ("15:52:33", "15:53:25", "FIX", 2),     # semver bump
    # Lane #1581 (PR #1584)
    ("15:16:20", "15:17:17", "SCOUT", 3),
    ("15:18:49", "15:23:28", "BUILD", 3),
    ("15:24:41", "15:27:37", "CHECK", 3),
    # Lane #1582 (PR #1585)
    ("15:16:20", "15:18:54", "SCOUT", 4),
    ("15:21:43", "15:23:11", "GUARD", 4),
    ("15:24:03", "15:28:54", "BUILD", 4),
    ("15:29:24", "15:36:20", "CHECK", 4),
]

LANES = ["#1578 (PR #1586)", "#1579 (PR #1588)", "#1580 (PR #1587)",
         "#1581 (PR #1584)", "#1582 (PR #1585)"]

COLOR = {
    "SCOUT": "#1f77b4",
    "GUARD": "#9467bd",
    "BUILD": "#2ca02c",
    "CHECK": "#ff7f0e",
    "RETRY": "#8c564b",
    "FIX": "#d62728",
}

# Three human steering interventions (dashed vertical markers).
INTERVENTIONS = [
    ("15:14:28", "approve parallel plan"),
    ("15:46:57", "authorize fallback review provider"),
    ("16:15:29", "authorize ordered merge"),
]

T0, T1 = 0, t("16:56:00")
MERGE0, MERGE1 = t("16:15:29"), t("16:52:30")  # relative minutes

fig, ax = plt.subplots(figsize=(12.5, 5.0))
ax.set_xlim(T0, T1)
ax.set_ylim(-0.2, len(LANES))
ax.invert_yaxis()

# Merge window band
ax.axvspan(MERGE0, MERGE1, color="#4caf50", alpha=0.10, zorder=0)
ax.text((MERGE0 + MERGE1) / 2, -0.05, "merge window", ha="center", va="bottom",
        fontsize=8, color="#2e7d32", style="italic")

# Lane labels (outside, left)
for row, lane in enumerate(LANES):
    ax.text(T0 - 40, row + 0.5, lane, ha="right", va="center",
            fontsize=9, fontweight="bold")
    if row:
        ax.axhline(row, color="#e0e0e0", linewidth=0.6, zorder=0)

BAR_H = 0.56
for start, end, kind, row in BARS:
    x0, x1 = t(start), t(end)
    base = kind[:-5] if kind.endswith("_FAIL") else kind
    ax.add_patch(plt.Rectangle(
        (x0, row + (1 - BAR_H) / 2), x1 - x0, BAR_H,
        facecolor=COLOR[base],
        edgecolor="#b71c1c" if kind.endswith("_FAIL") else "#555555",
        linewidth=1.2 if kind.endswith("_FAIL") else 0.5,
        linestyle="--" if kind.endswith("_FAIL") else "-",
        zorder=3,
    ))

# Human interventions: dashed vlines + numbered markers
for i, (ts, label) in enumerate(INTERVENTIONS, 1):
    x = t(ts)
    ax.axvline(x, color="#555555", linestyle=":", linewidth=1.0, zorder=1)
    ax.plot(x, -0.2, marker="v", color="#555555", clip_on=False, zorder=4)
    ax.text(x, -0.08, str(i), ha="center", va="center",
            fontsize=8, fontweight="bold", color="#333333",
            bbox=dict(boxstyle="circle,pad=0.15", fc="white", ec="#555555", lw=0.7))

ax.set_xticks(range(0, 111, 15))
ax.set_xticklabels([f"{m} min" if m else "0" for m in range(0, 111, 15)], fontsize=9)
ax.set_yticks([])
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)

handles = [Patch(facecolor=c, edgecolor="#555555", label=k.title())
           for k, c in COLOR.items()]
handles.append(Patch(facecolor="white", edgecolor="#b71c1c", linestyle="--",
                     label="Check fail"))
handles.append(plt.Line2D([0], [0], color="#555555", linestyle=":", marker="v",
                          label="Human intervention"))
ax.legend(handles=handles, loc="lower right", fontsize=8, ncol=4, frameon=False)

ax.set_title("Five issues, five parallel sessions, five merged PRs "
             "(minutes from kickoff)", fontsize=11)

plt.tight_layout()
plt.savefig("figures/fig-session-timeline.png", dpi=150, bbox_inches="tight")
print("Saved figures/fig-session-timeline.png")

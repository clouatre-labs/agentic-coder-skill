"""Figure: Gantt timeline of one parallel multi-agent coding session.

Data source: session transcript 01a0ba3a (2026-09-19), repo aptu-coder,
issues #1578-#1582 across 5 parallel session lanes. End times approximate.
Regenerate: python3 figures/fig-session-timeline.py  (requires matplotlib)
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Patch


def t(hhmmss):
    h, m, s = map(int, hhmmss.split(":"))
    return h * 3600 + m * 60 + s


# (start, end, label, kind, row) -- row groups bars into 5 session lanes.
BARS = [
    ("15:16:20", "15:18:30", "SCOUT #1578", "SCOUT", 0),
    ("15:16:20", "15:18:30", "SCOUT #1579", "SCOUT", 1),
    ("15:16:20", "15:18:30", "SCOUT #1580", "SCOUT", 2),
    ("15:16:20", "15:18:30", "SCOUT #1581", "SCOUT", 3),
    ("15:16:20", "15:18:30", "SCOUT #1582", "SCOUT", 4),
    ("15:18:49", "15:24:40", "BUILD #1581", "BUILD", 3),
    ("15:21:01", "15:32:10", "BUILD #1578", "BUILD", 0),
    ("15:21:01", "15:47:40", "BUILD #1579 (fail)", "BUILD", 1),
    ("15:21:01", "15:32:10", "BUILD #1580", "BUILD", 2),
    ("15:21:43", "15:24:00", "GUARD #1582", "GUARD", 4),
    ("15:24:03", "15:29:20", "BUILD #1582", "BUILD", 4),
    ("15:24:41", "15:29:00", "CHECK+PR #1581", "CHECK", 3),
    ("15:29:24", "15:32:00", "CHECK #1582", "CHECK", 4),
    ("15:32:09", "15:36:30", "CHECK+PR #1578", "CHECK", 0),
    ("15:32:09", "15:36:30", "CHECK+PR #1580", "CHECK", 2),
    ("15:32:41", "15:36:00", "CHECK+PR #1579 (fail)", "CHECK", 1),
    ("15:36:31", "15:39:00", "CHECK retry #1580", "RETRY", 2),
    ("15:47:38", "15:52:30", "BUILD retry #1579", "RETRY", 1),
    ("15:47:38", "15:49:30", "AMEND #1578", "RETRY", 0),
    ("15:52:33", "15:54:30", "BUILD #1587-fix (semver)", "FIX", 1),
    ("15:54:29", "15:57:00", "CHECK+PR retry #1579", "RETRY", 1),
    ("16:02:08", "16:05:00", "BUILD #1588-fix (semver)", "FIX", 1),
    ("16:45:10", "16:48:00", "REBASE #1588", "RETRY", 1),
]

LANES = ["Lane 1 (#1578)", "Lane 2 (#1579, fixes)", "Lane 3 (#1580)",
         "Lane 4 (#1581)", "Lane 5 (#1582)"]

COLOR = {
    "SCOUT": "#1f77b4",
    "GUARD": "#9467bd",
    "BUILD": "#2ca02c",
    "CHECK": "#ff7f0e",
    "FIX": "#d62728",
    "RETRY": "#8c564b",
}

T0, T1 = t("15:12:50"), t("16:55:21")

fig, ax = plt.subplots(figsize=(12, 5.2))
ax.set_xlim(T0, T1)
ax.set_ylim(0, len(LANES))
ax.invert_yaxis()

for row, lane in enumerate(LANES):
    ax.text(T0 - 30, row + 0.5, lane, ha="right", va="center",
            fontsize=9, fontweight="bold")

for start, end, label, kind, row in BARS:
    x0, x1 = t(start), t(end)
    ax.add_patch(FancyBboxPatch(
        (x0, row + 0.14), x1 - x0, 0.72,
        boxstyle="round,pad=0,rounding_size=20",
        facecolor=COLOR[kind], edgecolor="#555555", linewidth=0.6,
    ))
    ax.text((x0 + x1) / 2, row + 0.5, label, ha="center", va="center",
            fontsize=6.5, color="white", fontweight="bold")

ticks = ["15:15", "15:30", "15:45", "16:00", "16:15", "16:30", "16:45"]
ax.set_xticks([t(x + ":00") for x in ticks])
ax.set_xticklabels(ticks, fontsize=9)
ax.set_yticks([])
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)

ax.set_title("Session 01a0ba3a: 5-issue parallel pipeline (2026-09-19, end times approximate)",
             fontsize=11)
ax.legend(handles=[Patch(facecolor=c, edgecolor="#555555", label=k)
                   for k, c in COLOR.items()],
          loc="lower right", fontsize=8, ncol=3, frameon=False)

plt.tight_layout()
plt.savefig("figures/fig-session-timeline.png", dpi=150, bbox_inches="tight")
print("Saved figures/fig-session-timeline.png")

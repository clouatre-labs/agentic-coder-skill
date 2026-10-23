"""pi-coder-stats.py -- cost and PR outcomes of coder skill sessions from pi logs.

Emits a PII-free JSON aggregate: counts, costs, percentiles, and model names only;
no session ids, paths, repository or owner names, or issue text.

Usage:
  uv run python scripts/pi-coder-stats.py [--owners OWNER,...] > docs/evidence/pi-coder-aggregate.json

Scope: a coder session is a formal coder run: a pi session that invoked the coder
skill (read coder/SKILL.md, or a user prompt naming the coder skill), spawned
coder-* delegates or wrote coder handoffs, and ran the skill's mandatory tier
classification (a tier recorded in handoffs or the transcript, or a judge call
with a tier question). Invoking sessions that skipped classification (research,
reviews, follow-ups, single-phase experiments) are reported as informal and
excluded, with their PRs. Its cost is the orchestrator's messages from
the invocation onward plus every coder-* delegate it spawned, using pi's own
per-message usage.cost.total. Tier per session: the highest tier in its handoff
files, else the highest tier the orchestrator wrote in the transcript, else
"not_saved" (judge called, result not persisted). Bounds:
  lower = delegates only
  upper = delegates + the whole orchestrator session (includes interactive work
          before the invocation)
Coder-* delegates spawned by sessions that never invoked the skill are reported
as ad hoc and excluded.

PR outcomes: PR URLs printed by `gh pr create` in coder sessions, plus `pr_url`
from each run's 04-validation.json. Only PRs whose owner is in --owners are
queried (read-only, `gh api`); the rest are counted, never named.
"""

import argparse
import collections
import glob
import json
import os
import re
import statistics
import subprocess
from datetime import datetime

ROLE_MARKERS = {
    "You are SCOUT": "scout",
    "You are GUARD": "guard",
    "BUILD & VERIFY Delegate": "build",
    "# CHECK Delegate": "check",
}
SKILL_PATH = "coder/SKILL.md"
SKILL_MARKER = "## Phase 0: SETUP"
SKILL_PROMPT = re.compile(r"\bcoder skill\b|skill:coder\b", re.IGNORECASE)
SID = re.compile(r"coder-handoffs/(\d{10})")
PR_URL = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
TIERS = ("simple", "medium", "complex")
# tier as written by the orchestrator (02-plan.json, 00-progress.json, coder-log line)
TIER_WRITE = re.compile(r'"(?:tier|complexity)"\s*:\s*"(simple|medium|complex)"')


def text_of(message):
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") for c in content or [] if isinstance(c, dict))


def parse_session(path):
    s = {
        "start": None,
        "parent": None,
        "role": None,
        "invoked": False,
        "sids": set(),
        "prs": set(),
        "cost_all": 0.0,
        "cost_after": 0.0,
        "input": 0,
        "cache_read": 0,
        "tokens": 0,
        "models": collections.Counter(),
        "tiers": set(),
        "tier_judged": False,
    }
    pr_calls = set()
    with open(path, errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            s["sids"].update(SID.findall(line))
            if rec.get("type") == "session":
                s["start"], s["parent"] = rec.get("timestamp"), rec.get("parentSession")
            if rec.get("type") != "message":
                continue
            msg = rec["message"]
            role = msg.get("role")
            if role == "system" and s["role"] is None:
                # pi keeps the system prompt in `sections`, not `content`
                s["role"] = next(
                    (r for m, r in ROLE_MARKERS.items() if m in line), None
                )
            elif role == "user" and SKILL_PROMPT.search(text_of(msg)):
                s["invoked"] = True
            elif role == "toolResult":
                body = text_of(msg)
                if SKILL_MARKER in body:
                    s["invoked"] = True
                if msg.get("toolCallId") in pr_calls:
                    s["prs"].update(PR_URL.findall(body))
            elif role == "assistant":
                for c in msg.get("content") or []:
                    if c.get("type") != "toolCall":
                        continue
                    call = json.dumps(c.get("arguments"))
                    if c.get("name") == "read" and SKILL_PATH in call:
                        s["invoked"] = True
                    if "gh pr create" in call:
                        pr_calls.add(c.get("id"))
                    args = c.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except ValueError:
                            args = {}
                    for value in args.values():
                        if isinstance(value, str):
                            s["tiers"].update(TIER_WRITE.findall(value))
                    if "judge" in (c.get("name") or "") and any(
                        str(q).startswith("tier") for q in (args.get("questions") or {})
                    ):
                        s["tier_judged"] = True
                usage = msg.get("usage") or {}
                cost = (usage.get("cost") or {}).get("total") or 0.0
                s["cost_all"] += cost
                if s["invoked"] or s["role"]:
                    s["cost_after"] += cost
                    s["input"] += usage.get("input") or 0
                    s["cache_read"] += usage.get("cacheRead") or 0
                    s["tokens"] += usage.get("totalTokens") or 0
                    s["models"][f"{msg.get('provider')}/{msg.get('model')}"] += 1
    return s


def load_json(path):
    with open(path) as f:
        return json.load(f)


def handoff_index(repos_root):
    """Map run id -> (tier, pr_url) from handoff files under repos_root."""
    index = {}
    for d in sorted(glob.glob(f"{repos_root}/*/*/.git/coder-handoffs/*/")):
        tier, pr = "unknown", None
        for name, key in (("02-plan.json", "complexity"), ("00-progress.json", "tier")):
            try:
                value = str(load_json(d + name).get(key, "")).lower()
            except (OSError, ValueError, AttributeError):
                continue
            if value in TIERS and tier == "unknown":
                tier = value
        try:
            pr = load_json(d + "04-validation.json").get("pr_url")
        except (OSError, ValueError, AttributeError):
            pass
        index[os.path.basename(d.rstrip("/"))] = (tier, pr)
    return index


def pct(values):
    if not values:
        return None
    values = sorted(values)
    p90 = statistics.quantiles(values, n=10)[-1] if len(values) > 1 else values[0]
    return {"median": round(statistics.median(values), 4), "p90": round(p90, 4)}


def pr_outcomes(urls, owners):
    rows, excluded, unavailable = [], 0, 0
    for owner, repo, number in sorted(urls):
        if owner.lower() not in owners:
            excluded += 1
            continue
        out = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{owner}/{repo}/pulls/{number}",
                "--jq",
                "[.state, .created_at, .merged_at, .additions, .deletions, .changed_files]",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode != 0:
            unavailable += 1
            continue
        rows.append(json.loads(out.stdout))
    merged = [r for r in rows if r[2]]
    ts = datetime.fromisoformat
    return {
        "queried": len(rows),
        "merged": len(merged),
        "closed_unmerged": sum(1 for r in rows if r[0] == "closed" and not r[2]),
        "open": sum(1 for r in rows if r[0] == "open"),
        "excluded_other_owners": excluded,
        "unavailable": unavailable,
        "hours_open_to_merge": pct(
            [(ts(r[2]) - ts(r[1])).total_seconds() / 3600 for r in merged]
        ),
        "merged_additions": pct([r[3] for r in merged]),
        "merged_deletions": pct([r[4] for r in merged]),
        "merged_files": pct([r[5] for r in merged]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default=os.path.expanduser("~/.pi/agent/sessions"))
    ap.add_argument("--repos-root", default=os.path.expanduser("~/git"))
    ap.add_argument(
        "--owners", default="", help="comma-separated GitHub owners to query"
    )
    args = ap.parse_args()

    sessions = {
        p: parse_session(p) for p in sorted(glob.glob(f"{args.sessions}/*/*.jsonl"))
    }
    children = collections.defaultdict(list)
    for s in sessions.values():
        if s["role"]:
            children[s["parent"]].append(s)
    candidates = {
        p: s
        for p, s in sessions.items()
        if not s["role"] and s["invoked"] and (children[p] or s["sids"])
    }
    owner_of_sid = {sid: p for p, s in candidates.items() for sid in s["sids"]}
    ad_hoc = []
    for p, kids in list(children.items()):
        if p in candidates:
            continue
        for k in kids:  # delegates of a non-coder session sharing a coder run id
            hit = next(
                (owner_of_sid[i] for i in sorted(k["sids"]) if i in owner_of_sid), None
            )
            if hit:
                children[hit].append(k)
            else:
                ad_hoc.append(k)

    index = handoff_index(args.repos_root)
    units, informal = [], []
    for p, s in candidates.items():
        kids = children[p]
        deleg = sum(k["cost_all"] for k in kids)
        sids = s["sids"] | {i for k in kids for i in k["sids"]}
        tiers = [index[i][0] for i in sids if i in index and index[i][0] != "unknown"]
        tiers += s["tiers"]  # fallback: handoff gone or written without a tier field
        prs = s["prs"] | {u for k in kids for u in k["prs"]}
        for i in sids:
            pr = index.get(i, (None, None))[1]
            if pr and PR_URL.search(pr):
                prs.add(PR_URL.search(pr).groups())
        unit = {
            "lower": deleg,
            "primary": deleg + s["cost_after"],
            "upper": deleg + s["cost_all"],
            "tier": max(tiers, key=TIERS.index) if tiers else "not_saved",
            "scoped": [s, *kids],
            "prs": prs,
            "delegates": len(kids),
        }
        # formal run: the skill's mandatory first step (tier classification) ran
        (units if tiers or s["tier_judged"] else informal).append(unit)

    scoped = [x for u in units for x in u["scoped"]]
    models = sum((x["models"] for x in scoped), collections.Counter())
    n_msgs = sum(models.values()) or 1
    inp = sum(x["input"] + x["cache_read"] for x in scoped) or 1
    starts = sorted(x["start"] for x in scoped if x["start"])
    prs = set().union(*(u["prs"] for u in units)) if units else set()
    primary_total = sum(u["primary"] for u in units)
    by_tier = collections.defaultdict(list)
    for u in units:
        by_tier[u["tier"]].append(round(u["primary"], 4))

    agg = {
        "generated_by": "scripts/pi-coder-stats.py",
        "window": {"first": starts[0][:7], "last": starts[-1][:7]} if starts else None,
        "coder_sessions": {
            "count": len(units),
            "by_highest_tier": {
                t: len(by_tier.get(t, [])) for t in (*TIERS, "not_saved")
            },
            "delegate_sessions": sum(u["delegates"] for u in units),
        },
        "cost_usd": {
            "total": {
                b: round(sum(u[b] for u in units), 2)
                for b in ("lower", "primary", "upper")
            },
            "per_session": {
                b: pct([u[b] for u in units]) for b in ("lower", "primary", "upper")
            },
            "per_pr_opened": round(primary_total / len(prs), 4) if prs else None,
            "excluded": {
                "informal_sessions": len(informal),
                "informal_delegate_sessions": sum(u["delegates"] for u in informal),
                "informal_cost": round(sum(u["primary"] for u in informal), 2),
                "informal_prs_opened": len(
                    set().union(*(u["prs"] for u in informal)) - prs
                    if informal
                    else set()
                ),
                "ad_hoc_delegate_sessions": len(ad_hoc),
                "ad_hoc_cost": round(sum(k["cost_all"] for k in ad_hoc), 2),
            },
        },
        "tokens": {
            "total": sum(x["tokens"] for x in scoped),
            "cache_read_share": round(sum(x["cache_read"] for x in scoped) / inp, 3),
        },
        "model_mix": {m: round(n / n_msgs, 4) for m, n in models.most_common()},
        "per_session_cost_by_tier": {t: sorted(v) for t, v in sorted(by_tier.items())},
        "prs_opened": len(prs),
        "pr_outcomes": None,
    }
    owners = {o.strip().lower() for o in args.owners.split(",") if o.strip()}
    if owners:
        agg["pr_outcomes"] = pr_outcomes(prs, owners)
    print(json.dumps(agg, indent=2))


if __name__ == "__main__":
    main()

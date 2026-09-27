#!/usr/bin/env python3
"""Exploratory (not pre-registered) test of the only historical recommender trace:
Instagram's log of suggested profiles the subject viewed, 2017-04 to 2020-10.

Question: did profiles Instagram suggested (and he opened) become conversations and
lasting ties, compared with the other accounts he followed in the same years?

Cohorts (anchor time t):
  S  = suggested profiles he viewed (t = view time), n = 501
  Sf = the subset of S he follows at export time (t = view time)
  B  = accounts he follows at export time, followed inside the same window, not in S (t = follow time)
Outcomes, from the Instagram message stream (1:1 threads matched by username slug or display name):
  dm_365    any message in the matched thread within 365 d after t
  new_tie   the thread's first-ever message falls after t (not a pre-existing contact)
  lasting   Tier A anchored at t: >= 5 bursts (24 h gaps) within 365 d and a message in the last 90 d of that year
  self_init the first message after t was sent by the subject
Caveats: following.json lists only accounts still followed in 2026 (survivors); matching is approximate.
Writes aggregates only: results/ig_suggestions_test.json and results/tables/ig_suggestions_test.md.
"""
from __future__ import annotations
import collections, glob, json, math, os, re
from pathlib import Path
import numpy as np, orjson

ROOT = Path(__file__).resolve().parents[1]; RAW = ROOT / "data" / "raw" / "ig"
EV = Path(os.path.expanduser("~/.local/state/lifeos/carl-model/events/msg_instagram.jsonl"))
norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
DAY = 86400.0; H = 365 * DAY; GAP = DAY

S = json.load(open(next(RAW.glob("*suggested_profiles_viewed.json"))))
sugg = []
for e in S:
    lv = {x["label"]: x["value"] for x in e["label_values"]}
    sugg.append({"u": norm(lv.get("Username")), "name": norm(lv.get("Name")), "t": float(e["timestamp"])})
W0, W1 = min(x["t"] for x in sugg), max(x["t"] for x in sugg)
F = json.load(open(next(RAW.glob("*__following.json"))))["relationships_following"]
follow = {norm(x["title"]): float(x["string_list_data"][0]["timestamp"]) for x in F}
T = json.load(open(RAW / "threads.json"))
counts = collections.Counter(p for v in T.values() for p in v["participants"])
SELF = counts.most_common(1)[0][0]
one2one = {f: v for f, v in T.items() if len(v["participants"]) == 2}
by_slug, by_name = {}, collections.defaultdict(list)
for f, v in one2one.items():
    slug = norm(re.sub(r"_\d+$", "", f.split("/", 1)[1]))
    by_slug.setdefault(slug, f)
    other = [p for p in v["participants"] if p != SELF][0]
    by_name[norm(other)].append(f)

# message timestamps per thread folder, from the normalized stream (raw_ref carries the folder)
ts = collections.defaultdict(list)
with open(EV, "rb") as fh:
    for line in fh:
        r = orjson.loads(line); m = re.search(r"!((?:inbox|message_requests)/[^:]+):", str(r.get("raw_ref")))
        if not m: continue
        t = r["t_start"]; sec = __import__("datetime").datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
        ts[m.group(1)].append((sec, r.get("actor") == "carl"))
for f in ts: ts[f].sort()

def match(u, name):
    if u in by_slug: return by_slug[u], "username"
    if name and len(by_name.get(name, [])) == 1: return by_name[name][0], "display name"
    return None, None

def outcomes(folder, t):
    if folder is None or folder not in ts: return dict(matched=False, dm_365=False, new_tie=False, lasting=False, self_init=False)
    xs = ts[folder]; after = [(s, me) for s, me in xs if t < s <= t + H]
    first_ever = xs[0][0]
    bursts = 0; prev = None
    for s, _ in xs:
        if prev is None or s - prev >= GAP:
            if t < s <= t + H: bursts += 1
        prev = s
    last90 = any(t + H - 90 * DAY < s <= t + H for s, _ in xs)
    return dict(matched=True, dm_365=bool(after), new_tie=first_ever > t, lasting=bursts >= 5 and last90,
                self_init=bool(after) and after[0][1])

rows = {"S": [], "Sf": [], "B": []}
methods = collections.Counter()
sugg_users = {x["u"] for x in sugg}
for x in sugg:
    f, how = match(x["u"], x["name"]); methods[how] += 1
    o = outcomes(f, x["t"]); rows["S"].append(o)
    if x["u"] in follow: rows["Sf"].append(o | {"followed_after_view": follow[x["u"]] >= x["t"] - DAY})
for u, tf in follow.items():
    if u in sugg_users or not (W0 <= tf <= W1): continue
    f, how = match(u, None)
    rows["B"].append(outcomes(f, tf))

def rate(xs, k):
    n = len(xs); a = sum(1 for x in xs if x[k]); p = a / n if n else float("nan")
    z = 1.96; d = 1 + z*z/n if n else 1; c = (p + z*z/(2*n)) / d if n else float("nan")
    h = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d if n else float("nan")
    return {"k": a, "n": n, "p": p, "ci": [c - h, c + h]}

def diff(a, b, k, B=10000, seed=0):
    rng = np.random.default_rng(seed); xa = np.array([x[k] for x in a], float); xb = np.array([x[k] for x in b], float)
    d = xa.mean() - xb.mean(); boots = [rng.choice(xa, len(xa)).mean() - rng.choice(xb, len(xb)).mean() for _ in range(B)]
    return {"diff": float(d), "ci": [float(np.quantile(boots, .025)), float(np.quantile(boots, .975))]}

K = ["matched", "dm_365", "new_tie", "lasting", "self_init"]
res = {"status": "EXPLORATORY, post hoc, not pre-registered",
       "window": [__import__("datetime").datetime.fromtimestamp(W0, __import__("datetime").timezone.utc).date().isoformat(), __import__("datetime").datetime.fromtimestamp(W1, __import__("datetime").timezone.utc).date().isoformat()],
       "n": {k: len(v) for k, v in rows.items()}, "match_method_S": dict(methods),
       "one_to_one_threads": len(one2one), "threads_with_stream_timestamps": len(ts),
       "rates": {c: {k: rate(v, k) for k in K} for c, v in rows.items()},
       "Sf_followed_after_view": rate(rows["Sf"], "followed_after_view") if rows["Sf"] else None,
       "diff_Sf_minus_B": {k: diff(rows["Sf"], rows["B"], k) for k in K[1:]},
       "diff_S_minus_B": {k: diff(rows["S"], rows["B"], k) for k in K[1:]}}
# share of new 1:1 IG threads started inside the window that trace to a viewed suggestion
starts = [(f, xs[0][0]) for f, xs in ts.items() if f in one2one and W0 <= xs[0][0] <= W1]
sugg_folders = {match(x["u"], x["name"])[0] for x in sugg} - {None}
res["new_threads_in_window"] = {"n": len(starts), "from_viewed_suggestion": sum(1 for f, _ in starts if f in sugg_folders)}
(ROOT / "results" / "ig_suggestions_test.json").write_text(json.dumps(res, indent=1))
L = ["# Instagram suggested profiles, 2017-2020 (EXPLORATORY, post hoc)", "",
     f"Window {res['window'][0]} to {res['window'][1]}. S = suggested profiles viewed (n={res['n']['S']}); Sf = those still followed in 2026 (n={res['n']['Sf']}); B = other accounts followed in the same window, still followed in 2026 (n={res['n']['B']}).", "",
     "| outcome | S | Sf | B | Sf - B | S - B |", "|---|---|---|---|---|---|"]
for k in K:
    cells = [f"{res['rates'][c][k]['k']}/{res['rates'][c][k]['n']} = {res['rates'][c][k]['p']:.3f} [{res['rates'][c][k]['ci'][0]:.3f}, {res['rates'][c][k]['ci'][1]:.3f}]" for c in ("S", "Sf", "B")]
    d1 = res["diff_Sf_minus_B"].get(k); d2 = res["diff_S_minus_B"].get(k)
    fmt = lambda d: f"{d['diff']:+.3f} [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]" if d else ""
    L.append(f"| {k} | " + " | ".join(cells) + f" | {fmt(d1)} | {fmt(d2)} |")
L += ["", f"New one-to-one Instagram threads started in the window: {res['new_threads_in_window']['n']}; traced to a viewed suggestion: {res['new_threads_in_window']['from_viewed_suggestion']}.",
      f"Match method for S: {dict(methods)}. Followed after viewing (of Sf): {res['Sf_followed_after_view']['k'] if res['Sf_followed_after_view'] else 'n/a'}."]
(ROOT / "results" / "tables" / "ig_suggestions_test.md").write_text("\n".join(L) + "\n")
print("\n".join(L))

# ---- Secondary (S only): cross-platform continuation on Messenger, matched by display name ----
# B has no display names in the export, so this is descriptive for S, not a comparison.
MS = Path(os.path.expanduser("~/.local/state/lifeos/carl-model/events/msg_messenger.jsonl"))
names = collections.Counter(x["name"] for x in sugg if x["name"])
want = {n for n, c in names.items() if c == 1 and len(n) >= 6}
mts = collections.defaultdict(list); slug_threads = collections.defaultdict(set)
with open(MS, "rb") as fh:
    for line in fh:
        r = orjson.loads(line); m = re.search(r"!(?:inbox|archived_threads|message_requests|filtered_threads|e2ee_cutover)/([^:/]+?)_(\d+)", str(r.get("raw_ref")))
        if not m: continue
        slug = norm(m.group(1))
        if slug not in want: continue
        key = slug + "_" + m.group(2); slug_threads[slug].add(key)
        mts[key].append(__import__("datetime").datetime.fromisoformat(r["t_start"].replace("Z", "+00:00")).timestamp())
xrows = []
for x in sugg:
    ks = slug_threads.get(x["name"], set())
    if len(ks) != 1: xrows.append(dict(matched=False, dm_365=False, new_tie=False, lasting=False)); continue
    xs = sorted(mts[next(iter(ks))]); t = x["t"]; after = [s for s in xs if t < s <= t + H]
    bursts = 0; prev = None
    for s in xs:
        if (prev is None or s - prev >= GAP) and t < s <= t + H: bursts += 1
        prev = s
    xrows.append(dict(matched=True, dm_365=bool(after), new_tie=xs[0] > t, lasting=bursts >= 5 and any(t + H - 90*DAY < s <= t + H for s in xs)))
res["S_messenger_by_display_name"] = {k: rate(xrows, k) for k in ("matched", "dm_365", "new_tie", "lasting")}
either = [dict(dm_365=a["dm_365"] or b["dm_365"], lasting=a["lasting"] or b["lasting"]) for a, b in zip(rows["S"], xrows)]
res["S_instagram_or_messenger"] = {k: rate(either, k) for k in ("dm_365", "lasting")}
(ROOT / "results" / "ig_suggestions_test.json").write_text(json.dumps(res, indent=1))
L2 = ["", "Secondary, S only: continuation on Messenger (unique display-name match to a Messenger thread)", ""]
for k, v in res["S_messenger_by_display_name"].items(): L2.append(f"- Messenger {k}: {v['k']}/{v['n']} = {v['p']:.3f} [{v['ci'][0]:.3f}, {v['ci'][1]:.3f}]")
for k, v in res["S_instagram_or_messenger"].items(): L2.append(f"- Instagram or Messenger {k}: {v['k']}/{v['n']} = {v['p']:.3f} [{v['ci'][0]:.3f}, {v['ci'][1]:.3f}]")
with open(ROOT / "results" / "tables" / "ig_suggestions_test.md", "a") as fh: fh.write("\n".join(L2) + "\n")
print("\n".join(L2))

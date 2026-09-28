"""Pitches 3 and 7 (exploratory, descriptive): the attention curve of the work streams, and game choice as
explore versus exploit. Aggregates only in results/streams_attention_games.json; per-game names stay in
results/private/streams/games.csv.

Attention (work streams = videos where < 50 % of captions are gameplay):
  screen switch (10 s grain)  consecutive keyframes whose SigLIP cosine similarity < SWITCH_COS
  app switch (30 s grain)     consecutive Gemma captions whose normalized app_or_game differs
  dwell = length of a run between switches. Sampling at 10 s / 30 s cannot see shorter visits, so these
  dwells are upper bounds next to logged-input studies (Mark: ~47 s average on one screen; Screenomics:
  median switch ~20 s at 5 s sampling). Reported per year; no clinical reading of any kind.
Games (videos where >= 50 % of captions are gameplay): game = most common normalized app_or_game among the
  gameplay captions. A session is "exploring" when that game had never appeared on stream before, "returning"
  otherwise. Per year: sessions, hours, share of hours on first-ever sessions, distinct games.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "streams"
SWITCH_COS = 0.80


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(s).lower())).strip()


def read_jsonl(p):
    return [json.loads(line) for line in open(p)] if p.exists() else []


def runs(labels, step):
    out, n = [], 1
    for a, b in zip(labels, labels[1:]):
        if a == b:
            n += 1
        else:
            out.append(n * step); n = 1
    if labels:
        out.append(n * step)
    return out


def main():
    att = defaultdict(lambda: {"streams": 0, "hours": 0.0, "screen_dwell": [], "app_dwell": [], "screen_switch_per_h": [], "app_switch_per_h": []})
    sessions = []
    for d in sorted(ROOT.iterdir()):
        if not (d / "captions.jsonl").exists() or not (d / "siglip.npy").exists():
            continue
        m = json.load(open(d / "meta.json"))
        c = m.get("created") or (m.get("resolved_by_duration") or {}).get("created")
        if not c:
            continue
        when = datetime.fromisoformat(c.replace("Z", "+00:00"))
        caps = [x for x in read_jsonl(d / "captions.jsonl") if "activity" in x]
        if len(caps) < 3:
            continue
        hours = (float(m.get("duration_s") or 0) or 10.0 * m.get("n_keyframes", 0)) / 3600
        game_caps = [x for x in caps if "game" in str(x["activity"]).lower()]
        if len(game_caps) / len(caps) >= 0.5:
            names = Counter(norm(x.get("app_or_game")) for x in game_caps if x.get("app_or_game"))
            game = names.most_common(1)[0][0] if names else "unknown"
            sessions.append((when, game, hours))
            continue
        y = att[when.year]
        y["streams"] += 1; y["hours"] += hours
        sig = np.load(d / "siglip.npy").astype(np.float32)
        if len(sig) >= 3:
            same = (sig[1:] * sig[:-1]).sum(1) >= SWITCH_COS
            lab, k = [0], 0
            for s in same:
                k += 0 if s else 1; lab.append(k)
            y["screen_dwell"] += runs(lab, 10)
            y["screen_switch_per_h"].append((len(sig) - 1 - same.sum()) / max(1e-9, len(sig) * 10 / 3600))
        apps = [norm(x.get("app_or_game") or "none") for x in sorted(caps, key=lambda x: x["t"])]
        step = int(np.median(np.diff([x["t"] for x in sorted(caps, key=lambda x: x["t"])]))) if len(caps) > 1 else 30
        y["app_dwell"] += runs(apps, step)
        y["app_switch_per_h"].append(sum(a != b for a, b in zip(apps, apps[1:])) / max(1e-9, len(apps) * step / 3600))
    out = {"status": "exploratory", "switch_cos": SWITCH_COS, "attention_by_year": {}, "games_by_year": {}}
    for yr, y in sorted(att.items()):
        q = lambda v: [float(np.percentile(v, p)) for p in (25, 50, 75)] if v else None
        out["attention_by_year"][yr] = {"streams": y["streams"], "hours": round(y["hours"], 1),
                                        "screen_dwell_s_q25_50_75": q(y["screen_dwell"]), "app_dwell_s_q25_50_75": q(y["app_dwell"]),
                                        "screen_switches_per_h_median": float(np.median(y["screen_switch_per_h"])) if y["screen_switch_per_h"] else None,
                                        "app_switches_per_h_median": float(np.median(y["app_switch_per_h"])) if y["app_switch_per_h"] else None}
    seen, per = set(), defaultdict(lambda: {"sessions": 0, "hours": 0.0, "new_hours": 0.0, "games": set()})
    rows = []
    for when, game, h in sorted(sessions):
        new = game not in seen and game != "unknown"
        seen.add(game)
        p = per[when.year]
        p["sessions"] += 1; p["hours"] += h; p["games"].add(game)
        p["new_hours"] += h if new else 0
        rows.append((when.date().isoformat(), game, round(h, 2), new))
    for yr, p in sorted(per.items()):
        out["games_by_year"][yr] = {"sessions": p["sessions"], "hours": round(p["hours"], 1), "distinct_games": len(p["games"]),
                                    "share_hours_first_ever_game": round(p["new_hours"] / p["hours"], 3) if p["hours"] else None}
    out["games_total"] = {"sessions": len(sessions), "distinct_games": len({g for _, g, _ in sessions})}
    json.dump(out, open(REPO / "results" / "streams_attention_games.json", "w"), indent=1)
    priv = REPO / "results" / "private" / "streams"
    priv.mkdir(parents=True, exist_ok=True)
    with open(priv / "games.csv", "w") as fh:
        fh.write("date,game,hours,first_ever\n")
        for r in rows:
            fh.write(",".join(map(str, r)) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

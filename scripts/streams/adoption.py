"""H-ADOPT / H-PASSIVE (PREREG_STREAMS.md): does what Carl watches show up in what he does on stream?

  adoption.py --entities   exposure side only: extract named tools/apps/sites/languages/games from every
                           unique watch-history title with the eGPU vLLM Gemma 4 31B (temperature 0, fixed
                           prompt below), write data/derived/streams_watch_entities.jsonl. Prints counts only.
  adoption.py --run        the single confirmatory run, only after D:\\streams\\CAPTIONS_DONE. Writes
                           results/streams_adoption.json (aggregates) and results/private/streams/adoption_entities.csv.

Definitions (frozen with tag streams-prereg-v1): normalization = lowercase, drop punctuation and a trailing
version number, collapse whitespace; same entity only when normalized forms are identical; names shorter than
3 characters and the STOP words are excluded; first exposure X_e = earliest watch whose title yields e;
stream-day = LA calendar day with >= 1 stream; e appears on stream on day d when a caption `app_or_game`
or `topic` field of a stream from day d equals e or contains it as a whole-token sequence.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

REPO = Path(__file__).resolve().parents[2]
STREAMS = REPO / "data" / "streams"
HIST = REPO / "data" / "raw" / "yt_history"
ENT = REPO / "data" / "derived" / "streams_watch_entities.jsonl"
VLLM = os.environ.get("JUDGE_VLLM_URL", "http://100.95.29.20:8000") + "/v1/chat/completions"
LA = ZoneInfo("America/Los_Angeles")
SEED, B, WIN = 20260927, 5000, 180
STOP = {"youtube", "google", "video", "videos", "game", "games", "app", "apps", "tutorial", "tutorials", "software",
        "website", "websites", "computer", "internet", "music", "podcast", "stream", "live", "shorts", "tiktok",
        "news", "the", "and", "ai", "pc", "mac", "iphone", "android", "windows", "online", "web", "phone",
        "laptop", "code", "coding", "programming", "gameplay", "trailer", "review", "none", "null"}
PROMPT = ("Below are YouTube video titles, one per line, numbered. For each title, list the specific named software "
          "tools, apps, websites, programming languages or frameworks, and video games it mentions (proper names "
          "only, e.g. Figma, Python, Notion, Overwatch, Stardew Valley). Answer with JSON only: an object mapping "
          "each line number (as a string) to a list of names, [] when none.\n\n")


def norm(s):
    s = re.sub(r"\s+v?\d+(\.\d+)*$", "", str(s).lower().strip())  # trailing version first ("python 3.12")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def keep(e):
    return len(e) >= 3 and e not in STOP


def read_jsonl(p):
    return [json.loads(line) for line in open(p)]


def ask(batch):
    body = {"model": "gemma-4-31b-it", "temperature": 0, "max_tokens": 1500,
            "messages": [{"role": "user", "content": PROMPT + "\n".join(f"{i}. {t}" for i, t in enumerate(batch))}],
            "chat_template_kwargs": {"enable_thinking": False}}
    for attempt in range(4):
        try:
            req = urllib.request.Request(VLLM, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            out = json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", out, re.S)
            d = json.loads(m.group(0)) if m else {}
            return [d.get(str(i), []) for i in range(len(batch))], None
        except Exception as e:
            err = str(e)[:200]
    return [None] * len(batch), err


def game_on_pc():
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "PC", "python -c \"import sys; sys.path.insert(0, r'D:\\immich\\vlm\\autobench'); "
                        "import autobench as ab; print(ab.game_running())\""], capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def extract_entities():
    titles = sorted({r["text"] for r in read_jsonl(HIST / "watch.jsonl") if r.get("text") and not r["text"].startswith("http")})
    done = {}
    if ENT.exists():
        for r in read_jsonl(ENT):
            if r.get("names") is not None:
                done[r["title"]] = r["names"]
    todo = [t for t in titles if t not in done]
    print(f"unique titles {len(titles)}, already done {len(done)}, to do {len(todo)}", flush=True)
    ENT.parent.mkdir(parents=True, exist_ok=True)
    batches = [todo[i:i + 25] for i in range(0, len(todo), 25)]
    errors = 0
    with open(ENT, "a") as fh, cf.ThreadPoolExecutor(4) as ex:
        for k in range(0, len(batches), 16):
            g = game_on_pc()
            while g != "None":
                print(f"paused: game {g}", flush=True)
                import time
                time.sleep(60)
                g = game_on_pc()
            for batch, (names, err) in zip(batches[k:k + 16], ex.map(ask, batches[k:k + 16])):
                errors += err is not None
                for t, n in zip(batch, names):
                    fh.write(json.dumps({"title": t, "names": n}, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"batches {min(k + 16, len(batches))}/{len(batches)}, failed batches {errors}", flush=True)
    rows = read_jsonl(ENT)
    ents = {norm(n) for r in rows for n in (r["names"] or []) if keep(norm(n))}
    print(f"titles with >=1 entity: {sum(1 for r in rows if r['names'])}; distinct entities: {len(ents)}; failed batches {errors}")


def stream_days():
    """{day: [normalized caption field strings]} for every stream with a resolved date."""
    days = defaultdict(list)
    unresolved = 0
    for d in STREAMS.iterdir():
        if not (d / "meta.json").exists():
            continue
        m = json.load(open(d / "meta.json"))
        created = m.get("created") or (m.get("resolved_by_duration") or {}).get("created")
        if not created:
            unresolved += 1
            continue
        day = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(LA).date()
        fields = []
        if (d / "captions.jsonl").exists():
            for c in read_jsonl(d / "captions.jsonl"):
                for k in ("app_or_game", "topic"):
                    if c.get(k):
                        fields.append(" " + norm(c[k]) + " ")
        days[day].extend(fields)
    return days, unresolved


def first_exposures():
    title_names = {r["title"]: r["names"] or [] for r in read_jsonl(ENT)}
    first = {}
    for r in read_jsonl(HIST / "watch.jsonl"):
        for n in title_names.get(r.get("text"), []):
            e = norm(n)
            if keep(e):
                t = datetime.fromisoformat(r["ts"]).date()
                if e not in first or t < first[e]:
                    first[e] = t
    return first


def rates(e, x, days, day_list):
    pre = [d for d in day_list if x - timedelta(days=WIN) <= d < x]
    post = [d for d in day_list if x < d <= x + timedelta(days=WIN)]
    if not pre or not post:
        return None
    pat = f" {e} "
    hit = lambda d: any(pat in f for f in days[d])
    return sum(map(hit, post)) / len(post) - sum(map(hit, pre)) / len(pre)


def boot(v, rng):
    v = np.asarray(v, float)
    if len(v) == 0:
        return {"n": 0}
    bs = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(B)])
    return {"n": int(len(v)), "mean": float(v.mean()), "ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}


def run():
    if not (STREAMS / "_state" / "PC_CAPTIONS_DONE").exists():
        sys.exit("refusing: captions are not finished for every video (PREREG_STREAMS.md section 5)")
    out_p = REPO / "results" / "streams_adoption.json"
    if out_p.exists():
        sys.exit(f"refusing: {out_p} exists; the confirmatory run happens once")
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    days, unresolved = stream_days()
    day_list = sorted(days)
    first = first_exposures()
    elig = {e: x for e, x in first.items() if date(2020, 7, 1) <= x <= date(2026, 3, 1)}
    real, plus, minus, rows = [], [], [], []
    for e, x in sorted(elig.items()):
        r0 = rates(e, x, days, day_list)
        if r0 is None:
            continue
        rp = rates(e, x + timedelta(days=365), days, day_list)
        rm = rates(e, x - timedelta(days=365), days, day_list)
        real.append(r0); rows.append((e, x.isoformat(), r0, rp, rm))
        plus.append(np.nan if rp is None else r0 - rp)
        minus.append(np.nan if rm is None else r0 - rm)
    rng = np.random.default_rng(SEED)
    res = {"commit": commit, "prereg": "PREREG_STREAMS.md", "stream_days": len(day_list), "unresolved_videos": unresolved,
           "entities_with_exposure": len(first), "eligible_window": len(elig),
           "H_ADOPT": boot(real, rng),
           "H_ADOPT_minus_placebo_plus365": boot([v for v in plus if v == v], rng),
           "H_ADOPT_minus_placebo_minus365": boot([v for v in minus if v == v], rng)}
    # H-PASSIVE
    searches = [(datetime.fromisoformat(r["ts"]).date(), " " + norm(r["text"]) + " ")
                for f in ("g_search.jsonl", "yt_search.jsonl") for r in read_jsonl(HIST / f)]
    sought, passive = [], []
    for e, xs, r0, _, _ in rows:
        x = date.fromisoformat(xs)
        s = any(x - timedelta(days=30) <= d < x and f" {e} " in q for d, q in searches)
        (sought if s else passive).append(r0)
    rng2 = np.random.default_rng(SEED + 1)
    bs = [np.mean(rng2.choice(sought, len(sought))) - np.mean(rng2.choice(passive, len(passive))) for _ in range(B)] if sought and passive else []
    res["H_PASSIVE"] = {"n_sought": len(sought), "n_passive": len(passive),
                        "diff": float(np.mean(sought) - np.mean(passive)) if sought and passive else None,
                        "ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))] if bs else None}
    json.dump(res, open(out_p, "w"), indent=1)
    priv = REPO / "results" / "private" / "streams"
    priv.mkdir(parents=True, exist_ok=True)
    with open(priv / "adoption_entities.csv", "w") as fh:
        fh.write("entity,first_exposure,post_minus_pre,placebo_plus365,placebo_minus365\n")
        for r in rows:
            fh.write(",".join(str(v) for v in r) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entities", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.entities:
        extract_entities()
    elif a.run:
        run()
    else:
        ap.print_help()

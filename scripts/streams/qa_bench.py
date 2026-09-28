"""Pitch 10 (exploratory): a private long-horizon question set over the stream archive, and a first baseline.

generate  stratified sample (up to PER_YEAR streams per year, work-like and >= 10 min first), one digest per
          stream (title, date, captions with times, screen-text lines, speech excerpts), and the eGPU Gemma 4 31B
          writes 4 questions Carl could ask about his own past with answer + evidence time + type.
          -> data/derived/qa_bench_v0.jsonl (private). Every item is marked verified=false: generated from
          machine captions, so it needs Carl's spot check before any claim rests on it.
baseline  retrieval: does the question text find its source stream in the top 5 of the `streams` full-text
          index (the pitch 1 search)? -> results/streams_qa_baseline.json (aggregates only).
Questions never leave this machine; publishable form = question types, counts and scores only.
"""
import argparse
import json
import random
import re
import sqlite3
import subprocess
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "streams"
OUT = REPO / "data" / "derived" / "qa_bench_v0.jsonl"
VLLM = "http://100.95.29.20:8000/v1/chat/completions"
PER_YEAR = 8
PROMPT = """You are helping build a memory test for one person, Carl, from his own livestream archive.
Below is a digest of ONE of his livestreams: title, date, what the screen showed over time (machine captions),
text read off the screen, and what was said. Write 4 questions Carl could ask an assistant about his own past
that ONLY this stream answers, e.g. what he was building, which tool or game he used, what he said about
something, or what he did first. Refer to the time by month and year (never by the stream title), make each
answer short and checkable from the digest, and give the second in the stream where the evidence is.
Answer with JSON only: [{"question": ..., "answer": ..., "evidence_t": <seconds>, "type": "built|tool|said|did|when"}]

DIGEST
"""


def read_jsonl(p):
    return [json.loads(line) for line in open(p)] if p.exists() else []


def digest(d, m):
    title = m["inner"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
    c = m.get("created") or (m.get("resolved_by_duration") or {}).get("created")
    caps = [x for x in read_jsonl(d / "captions.jsonl") if "caption" in x]
    step = max(1, len(caps) // 40)
    lines = [f"title: {title}", f"date: {c[:10]}", f"duration: {int((float(m.get('duration_s') or 0) or 10.0 * m.get('n_keyframes', 0)) // 60)} min", "screen over time:"]
    lines += [f"  {x['t']}s: {x['caption']} (app: {x.get('app_or_game')})" for x in caps[::step]]
    ocr = read_jsonl(d / "ocr.jsonl")
    txt = []
    for o in ocr[:: max(1, len(ocr) // 15)]:
        txt += [ln[0] for ln in sorted(o["lines"], key=lambda ln: -ln[1])[:3]]
    lines.append("screen text: " + " / ".join(dict.fromkeys(txt))[:1200])
    if (d / "transcript.json").exists():
        seg = json.load(open(d / "transcript.json"))["segments"]
        lines.append("said: " + " ".join(f"[{int(s['start'])}s] {s['text']}" for s in seg[:: max(1, len(seg) // 25)])[:2500])
    return "\n".join(lines)


def ask(text):
    body = {"model": "gemma-4-31b-it", "temperature": 0, "max_tokens": 900,
            "messages": [{"role": "user", "content": PROMPT + text}], "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(VLLM, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    out = json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"]
    m = re.search(r"\[.*\]", out, re.S)
    return json.loads(m.group(0)) if m else []


def generate():
    by_year = defaultdict(list)
    for d in sorted(ROOT.iterdir()):
        if not (d / "captions.jsonl").exists():
            continue
        m = json.load(open(d / "meta.json"))
        c = m.get("created") or (m.get("resolved_by_duration") or {}).get("created")
        if c:
            by_year[c[:4]].append((not m.get("worklike"), (float(m.get("duration_s") or 0) or 10.0 * m.get("n_keyframes", 0)) < 600, d.name, m))
    prev = read_jsonl(OUT)
    done = {r["key"] for r in prev}
    have = defaultdict(set)
    for r in prev:
        have[r["year"]].add(r["key"])
    rng = random.Random(20260927)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(OUT, "a") as fh:
        for yr, items in sorted(by_year.items()):
            rng.shuffle(items)
            items.sort(key=lambda x: (x[0], x[1]))
            for _, _, key, m in [x for x in items if x[2] not in done][: max(0, PER_YEAR - len(have[yr]))]:
                try:
                    qs = ask(digest(ROOT / key, m))
                except Exception as e:
                    print(f"{key}: {e}")
                    continue
                for q in qs:
                    fh.write(json.dumps({"key": key, "year": yr, **q, "verified": False, "generator": "gemma-4-31b-it"}, ensure_ascii=False) + "\n")
                    n += 1
    print(f"questions written this run: {n}; streams by year available: { {y: len(v) for y, v in sorted(by_year.items())} }")


def baseline():
    subprocess.run([str(REPO / "scripts" / "streams" / "streams_cli.py"), "zzzz_index_refresh"], capture_output=True)
    con = sqlite3.connect(ROOT / "streams.db")
    qs = read_jsonl(OUT)
    hit, ranks = 0, []
    for q in qs:
        words = [w for w in re.findall(r"\w+", q["question"].lower()) if len(w) > 3]
        if not words:
            continue
        query = " OR ".join(f'"{w}"' for w in words)
        rows = con.execute("SELECT key, bm25(docs) FROM docs WHERE docs MATCH ? ORDER BY bm25(docs) LIMIT 200", (query,)).fetchall()
        keys = list(dict.fromkeys(k for k, _ in rows))
        r = keys.index(q["key"]) + 1 if q["key"] in keys else None
        ranks.append(r)
        hit += bool(r and r <= 5)
    res = {"status": "exploratory", "questions": len(ranks), "recall_at_5_source_stream": hit / len(ranks) if ranks else None,
           "mrr": sum(1 / r for r in ranks if r) / len(ranks) if ranks else None,
           "streams_indexed": con.execute("SELECT count(*) FROM videos").fetchone()[0], "verified_items": 0,
           "note": "questions are machine-generated and unverified; retrieval uses OR over content words (bm25)"}
    json.dump(res, open(REPO / "results" / "streams_qa_baseline.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    a = ap.parse_args()
    if a.generate:
        generate()
    if a.baseline:
        baseline()

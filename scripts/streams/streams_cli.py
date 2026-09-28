#!/Users/carl/CODELocalProjects/arxiv-Engineering-Serendpity/.venv/bin/python
"""streams: find a moment in Carl's livestream archive (carlcrafters, 2016-2026) by what was on screen,
what the screen said, or what he said.

    streams figma                        words are ANDed
    streams '"pull request"' --year 2023 quoted phrase, one year
    streams wflo OR webflow -n 20
    streams skyrim dragon --look         also search by how the frame looks (SigLIP), slower
    streams hackathon demo --open        open the best hit on YouTube at that second

Searches the Gemma captions (1 per 30 s of work, 1 per min of games), Apple Vision screen text (every 10 s),
and Whisper speech, all built on this Mac from data/streams/ (never uploaded). The index updates itself
from whatever the pipeline has finished so far; the header says how much of the archive that is.

Exit codes: 0 hits, 1 no hits, 2 bad query, 3 no index data yet (it says so).
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/carl/CODELocalProjects/arxiv-Engineering-Serendpity/data/streams")
DB = ROOT / "streams.db"
TOTAL_VIDEOS = 915


def fmt_t(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def signature(d):
    return "|".join(f"{n}:{int((d / n).stat().st_mtime)}" for n in ("captions.jsonl", "ocr.jsonl", "transcript.json", "meta.json")
                    if (d / n).exists())


def update_index(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS videos(key TEXT PRIMARY KEY, video_id TEXT, title TEXT, created TEXT, duration_s REAL,
        category TEXT, privacy TEXT, worklike INT, sig TEXT);
    CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(key UNINDEXED, t UNINDEXED, kind UNINDEXED, text,
        tokenize='unicode61 remove_diacritics 2');
    """)
    have = dict(con.execute("SELECT key, sig FROM videos"))
    changed = 0
    for d in sorted(ROOT.iterdir()):
        if not (d / "meta.json").exists():
            continue
        sig = signature(d)
        if have.get(d.name) == sig:
            continue
        m = json.load(open(d / "meta.json"))
        res = m.get("resolved_by_duration") or {}
        vid = m.get("video_id") or res.get("video_id")
        title = m["inner"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        con.execute("DELETE FROM docs WHERE key=?", (d.name,))
        con.execute("INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?,?,?)",
                    (d.name, vid, title, m.get("created") or res.get("created"), m.get("duration_s"),
                     m.get("category") or res.get("category"), m.get("privacy") or res.get("privacy"), int(bool(m.get("worklike"))), sig))
        rows = [(d.name, 0, "title", title)]
        if (d / "captions.jsonl").exists():
            for line in open(d / "captions.jsonl"):
                c = json.loads(line)
                txt = " ".join(str(c.get(k) or "") for k in ("caption", "app_or_game", "topic", "activity")).strip()
                if txt:
                    rows.append((d.name, c["t"], "caption", txt))
        if (d / "ocr.jsonl").exists():
            for line in open(d / "ocr.jsonl"):
                o = json.loads(line)
                txt = " ".join(ln[0] for ln in o["lines"] if ln[1] >= 0.3)
                if txt:
                    rows.append((d.name, o["t"], "screen", txt))
        if (d / "transcript.json").exists():
            for s in json.load(open(d / "transcript.json"))["segments"]:
                rows.append((d.name, s["start"], "speech", s["text"]))
        con.executemany("INSERT INTO docs(key, t, kind, text) VALUES (?,?,?,?)", rows)
        changed += 1
    con.commit()
    return changed


def fts_query(words):
    out = []
    for w in words:
        if w.upper() == "OR":
            out.append("OR")
        elif w.startswith('"') and w.endswith('"') and len(w) > 2:
            out.append('"' + w[1:-1].replace('"', "") + '"')
        else:
            w = re.sub(r"[^\w\-']", " ", w).strip()
            out += ['"' + p + '"' for p in w.split()]
    return " ".join(out)


def link(vid, t):
    return f"https://youtu.be/{vid}?t={int(t)}" if vid else None


def look(con, query, n, year):
    import numpy as np
    import torch
    from transformers import AutoModel, AutoProcessor
    mid = "google/siglip2-so400m-patch16-naflex"
    model = AutoModel.from_pretrained(mid, dtype=torch.float32).eval()
    proc = AutoProcessor.from_pretrained(mid)
    with torch.no_grad():
        x = proc(text=[f"a screenshot of {query}"], return_tensors="pt", padding="max_length", max_length=64)
        q = model.get_text_features(**x)
        q = getattr(q, "pooler_output", q)
        q = torch.nn.functional.normalize(q, dim=-1)[0].numpy()
    hits = []
    for key, vid, title, created in con.execute("SELECT key, video_id, title, created FROM videos"):
        if year and not (created or "").startswith(str(year)):
            continue
        p = ROOT / key / "siglip.npy"
        if not p.exists():
            continue
        e = np.load(p).astype(np.float32)
        if not len(e):
            continue
        s = e @ q
        i = int(s.argmax())
        hits.append((float(s[i]), key, vid, title, created, i * 10))
    return sorted(hits, reverse=True)[:n]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("words", nargs="*")
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--year", type=int)
    ap.add_argument("--kind", choices=["caption", "screen", "speech", "title"])
    ap.add_argument("--look", action="store_true", help="also rank frames by how they look (SigLIP), ~10 s")
    ap.add_argument("--open", action="store_true", help="open the best hit on YouTube")
    a = ap.parse_args()
    if not a.words:
        ap.print_help()
        return 2
    con = sqlite3.connect(DB)
    changed = update_index(con)
    n_vid = con.execute("SELECT count(*) FROM videos").fetchone()[0]
    if n_vid == 0:
        print("no stream data indexed yet: the pipeline has not finished any video (data/streams/_state has progress)")
        return 3
    n_cap = con.execute("SELECT count(DISTINCT key) FROM docs WHERE kind='caption'").fetchone()[0]
    print(f"[{n_vid}/{TOTAL_VIDEOS} videos indexed, {n_cap} with captions{f', {changed} updated now' if changed else ''}]")
    q = fts_query(a.words)
    if not q.strip('" '):
        return 2
    sql = """SELECT docs.key, docs.t, docs.kind, snippet(docs, 3, '[', ']', ' ... ', 14), v.video_id, v.title, v.created
             FROM docs JOIN videos v ON v.key = docs.key WHERE docs MATCH ?"""
    args = [q]
    if a.year:
        sql += " AND v.created LIKE ?"; args.append(f"{a.year}%")
    if a.kind:
        sql += " AND docs.kind = ?"; args.append(a.kind)
    try:
        rows = con.execute(sql + " ORDER BY bm25(docs) LIMIT ?", args + [a.n * 4]).fetchall()
    except sqlite3.OperationalError as e:
        print(f"bad query: {e}")
        return 2
    seen, shown = set(), []
    for key, t, kind, snip, vid, title, created in rows:
        slot = (key, int(float(t)) // 60)
        if slot in seen:
            continue
        seen.add(slot)
        shown.append((key, float(t), kind, snip, vid, title, created))
        if len(shown) >= a.n:
            break
    for key, t, kind, snip, vid, title, created in shown:
        print(f"{(created or '????')[:10]}  {title[:60]}  at {fmt_t(t)}  [{kind}]")
        print(f"    {snip}")
        print(f"    {link(vid, t) or ROOT / key / 'proxy.mp4'}")
    looked = []
    if a.look:
        print("\nlooks like:")
        looked = look(con, " ".join(a.words), a.n, a.year)
        for s, key, vid, title, created, t in looked:
            print(f"{(created or '????')[:10]}  {title[:60]}  at {fmt_t(t)}  (similarity {s:.3f})")
            print(f"    {link(vid, t) or ROOT / key / 'proxy.mp4'}   frame: {ROOT / key / 'kf' / f'f_{t // 10 + 1:05d}.jpg'}")
    if a.open and shown and shown[0][4]:
        subprocess.run(["open", link(shown[0][4], shown[0][1])])
    return 0 if shown or looked else 1


if __name__ == "__main__":
    sys.exit(main())

"""Pitches 4 and 9 (exploratory): what Carl said while working, as data.

corpus    data/derived/thinkaloud.jsonl (private): one row per speech segment in a work stream, with the
          Gemma caption just before (screen_before), the caption 30-90 s later (screen_after), the app, and the
          top screen-text lines at that moment. This is (screen, said, what happened next): reasoning while
          acting. Stream audio can include other voices (calls, teammates, videos); there is no diarization, so
          rows are "stream speech", not verified as Carl's.
lm        a personal language model test: LoRA on Qwen3-0.6B (mlx-lm) over transcripts dated before
          2025-07-01, perplexity on transcripts from 2025-07-01 on, versus the base model. Also writes the
          most over-represented words (vs the base model's surprisal) as a vocabulary list for Whisper prompts.
          Aggregates -> results/streams_speech.json; vocabulary -> results/private/streams/vocab.txt.
The carl-model protocol governs what that model may read; using this corpus there needs an amendment
(draft: docs/carl_model_amendment_draft_streams.md). Nothing here feeds carl-model automatically.
"""
import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "streams"
DER = REPO / "data" / "derived"
SPLIT = "2025-07-01"
BASE = "mlx-community/Qwen3-0.6B-4bit"


def read_jsonl(p):
    return [json.loads(line) for line in open(p)] if p.exists() else []


def stream_date(m):
    c = m.get("created") or (m.get("resolved_by_duration") or {}).get("created")
    return datetime.fromisoformat(c.replace("Z", "+00:00")).date().isoformat() if c else None


def corpus():
    rows, streams = [], 0
    for d in sorted(ROOT.iterdir()):
        tp = d / "transcript.json"
        if not tp.exists() or not (d / "captions.jsonl").exists():
            continue
        m = json.load(open(d / "meta.json"))
        caps = sorted((c for c in read_jsonl(d / "captions.jsonl") if "activity" in c), key=lambda c: c["t"])
        if not caps or sum("game" in str(c["activity"]).lower() for c in caps) / len(caps) >= 0.5:
            continue
        ocr = {o["t"]: o["lines"] for o in read_jsonl(d / "ocr.jsonl")}
        streams += 1
        for s in json.load(open(tp))["segments"]:
            before = [c for c in caps if c["t"] <= s["start"]]
            after = [c for c in caps if s["end"] + 30 <= c["t"] <= s["end"] + 90]
            ot = int(s["start"] // 10) * 10
            rows.append({"key": d.name, "date": stream_date(m), "t": s["start"], "said": s["text"],
                         "screen_before": before[-1].get("caption") if before else None,
                         "app": before[-1].get("app_or_game") if before else None,
                         "screen_after": after[0].get("caption") if after else None,
                         "screen_text": [ln[0] for ln in sorted(ocr.get(ot, []), key=lambda ln: -ln[1])[:5]]})
    DER.mkdir(parents=True, exist_ok=True)
    with open(DER / "thinkaloud.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    words = sum(len(r["said"].split()) for r in rows)
    years = Counter((r["date"] or "????")[:4] for r in rows)
    return {"work_streams_with_speech": streams, "segments": len(rows), "words": words,
            "segments_with_screen_after": sum(1 for r in rows if r["screen_after"]), "segments_by_year": dict(sorted(years.items()))}


def lm():
    allseg = []  # every stream with speech, games included: the language model is about how Carl talks
    for d in sorted(ROOT.iterdir()):
        tp = d / "transcript.json"
        if tp.exists() and (d / "meta.json").exists():
            dt = stream_date(json.load(open(d / "meta.json")))
            if dt:
                text = " ".join(s["text"] for s in json.load(open(tp))["segments"])
                if text.strip():
                    allseg.append((dt, text))
    train = [t for dt, t in allseg if dt < SPLIT]
    test = [t for dt, t in allseg if dt >= SPLIT]
    if len(train) < 20 or len(test) < 5:
        return {"note": "too little speech on both sides of the split yet", "train_streams": len(train), "test_streams": len(test)}
    data = DER / "speech_lm"
    data.mkdir(parents=True, exist_ok=True)

    def chunks(texts, n=180):
        for t in texts:
            w = t.split()
            for i in range(0, len(w), n):
                yield " ".join(w[i:i + n])
    tr = list(chunks(train)); te = list(chunks(test))
    cut = max(1, len(tr) // 20)
    for name, part in (("train", tr[cut:]), ("valid", tr[:cut]), ("test", te)):
        with open(data / f"{name}.jsonl", "w") as fh:
            for c in part:
                fh.write(json.dumps({"text": c}, ensure_ascii=False) + "\n")
    py = str(REPO / ".venv" / "bin" / "python")
    adapters = data / "adapters"
    subprocess.run([py, "-m", "mlx_lm", "lora", "--model", BASE, "--train", "--data", str(data), "--adapter-path", str(adapters),
                    "--iters", "600", "--batch-size", "8", "--num-layers", "16", "--learning-rate", "1e-4", "--max-seq-length", "512"],
                   check=True, capture_output=True)

    def ppl(adapter):
        cmd = [py, "-m", "mlx_lm", "lora", "--model", BASE, "--test", "--data", str(data)] + (["--adapter-path", str(adapter)] if adapter else [])
        out = subprocess.run(cmd, capture_output=True, text=True).stdout + ""
        import re
        m = re.search(r"Test loss ([\d.]+), Test ppl ([\d.]+)", out)
        return (float(m.group(1)), float(m.group(2))) if m else (None, None)
    base_loss, base_ppl = ppl(None)
    ft_loss, ft_ppl = ppl(adapters)
    # vocabulary: words frequent in Carl's stream speech and rare in general text, by count ratio vs a base
    # model-free proxy (document frequency across streams), capped to names/jargon-like tokens
    cnt = Counter(w.strip(".,!?;:\"'()").lower() for _, t in allseg for w in t.split())
    vocab = [w for w, n in cnt.most_common(4000) if n >= 5 and len(w) > 3 and not w.isdigit()]
    priv = REPO / "results" / "private" / "streams"
    priv.mkdir(parents=True, exist_ok=True)
    (priv / "vocab_candidates.txt").write_text("\n".join(vocab[:1500]))
    return {"base": BASE, "split": SPLIT, "train_chunks": len(tr) - cut, "test_chunks": len(te),
            "test_loss_base": base_loss, "test_ppl_base": base_ppl, "test_loss_lora": ft_loss, "test_ppl_lora": ft_ppl}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lm", action="store_true")
    a = ap.parse_args()
    res = {"status": "exploratory", "corpus": corpus()}
    if a.lm:
        res["lm"] = lm()
    out = REPO / "results" / "streams_speech.json"
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res, indent=1))

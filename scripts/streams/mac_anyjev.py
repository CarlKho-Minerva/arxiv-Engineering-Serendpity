"""AnyJev typed judgments per 5-minute bin of each stream (Gemma 4 31B on the PC's eGPU vLLM, level L0).

Qwen3-8B on this Mac measured 6.5 s/bin for the 11-option question alone (L0 rotates options), ~33 h for the
archive; vLLM's prefix cache shares the state across questions and rotations, and these are 1-token prefill
requests next to the caption job. Paused while a game runs on the PC's internal card.

A bin's state is text only: stream title, position, the Gemma captions in the bin, the top screen-text lines
(Apple Vision) and the speech (Whisper) in the bin. Needs captions, OCR and (when there is speech) the
transcript. Output data/streams/<key>/anyjev.jsonl, one row per bin with calibrated probabilities.
The 5-minute grid matches state-tokens (01_build_bins.py), so these rows can join the carl-model lanes.
"""
import json
import os
import sys

import numpy as np
from anyjev import Decider, Question

import time
from anyjev.backends.vllm import VLLMBackend

from common import ROOT, failed_twice, ledger, log, loop, pc, synced_keys, upstream_done

STAGE = "anyjev"
URL = os.environ.get("JUDGE_VLLM_URL", "http://100.95.29.20:8000")
MODEL, TOKENIZER = "gemma-4-31b-it", "QuantTrio/gemma-4-31B-it-AWQ"
BIN_S = 300
ACTIVITY = ["coding or software development", "writing or editing documents", "design or visual work",
            "reading, research, or browsing", "video call or meeting", "presenting or demoing",
            "talking to the camera or audience", "playing a video game", "watching videos or media",
            "idle, away, or loading screen", "other"]
ACT_KEYS = ["coding", "writing", "design", "reading", "call", "presenting", "talking", "gaming", "media", "idle", "other"]
MODE = ["creating or producing something", "consuming content", "communicating with people", "neither"]
MODE_KEYS = ["create", "consume", "communicate", "neither"]
QUESTIONS = [
    Question.choice("What is Carl mainly doing during this part of his livestream?", ACTIVITY, name="activity"),
    Question.noul("Is Carl doing productive work here (school, a job, a project, research, or building something) "
                  "rather than leisure?", name="working"),
    Question.noul("Is Carl interacting with other people here (a call, a meeting, teammates, a chat, or people in "
                  "the room)?", name="social"),
    Question.choice("Which best describes Carl's mode here?", MODE, name="mode"),
    Question.score("How focused on a single task does Carl appear during this part?",
                   levels=["scattered: switching between unrelated things", "mixed", "steady on one task",
                           "deeply absorbed in one task"], name="focus"),
    Question.noul("Does Carl appear to be learning or trying something new to him (a new tool, a tutorial, "
                  "documentation, a first-time setup) rather than doing routine work?", name="novel"),
]


def read_jsonl(p):
    return [json.loads(line) for line in open(p)] if p.exists() else []


def states_for(key):
    d = ROOT / key
    m = json.load(open(d / "meta.json"))
    title = m["inner"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
    dur = float(m.get("duration_s") or 0) or 10.0 * m.get("n_keyframes", 0)  # some webm report no duration
    caps = read_jsonl(d / "captions.jsonl")
    ocr = read_jsonl(d / "ocr.jsonl")
    tr = json.load(open(d / "transcript.json"))["segments"] if (d / "transcript.json").exists() else []
    out = []
    for b in range(0, max(1, int(dur // BIN_S) + (1 if dur % BIN_S > 30 or dur < BIN_S else 0))):
        lo, hi = b * BIN_S, (b + 1) * BIN_S
        c = [x.get("caption") or x.get("raw", "")[:200] for x in caps if lo <= x["t"] < hi][:10]
        apps = sorted({str(x.get("app_or_game")) for x in caps if lo <= x["t"] < hi and x.get("app_or_game")})[:5]
        lines = []
        for x in ocr:
            if lo <= x["t"] < hi:
                lines += [ln[0] for ln in sorted(x["lines"], key=lambda ln: -ln[1])[:4]]
        seen, text = set(), []
        for ln in lines:
            if ln not in seen and len(ln) > 2:
                seen.add(ln); text.append(ln)
        speech = " ".join(s["text"] for s in tr if lo <= s["start"] < hi)
        out.append({"bin": b, "t0": lo, "state": {
            "stream_title": title,
            "position": f"minutes {lo // 60}-{min(hi, int(dur)) // 60} of a {int(dur // 60)}-minute stream",
            "what_the_frames_show": " | ".join(c)[:1200] or "(no captions)",
            "apps_or_games_seen": ", ".join(apps) or "(none)",
            "screen_text": " / ".join(text)[:600] or "(none)",
            "carl_said": speech[:800] or "(no speech)"}})
    return out


decider = Decider(VLLMBackend(URL, MODEL, tokenizer_name=TOKENIZER, workers=4), level="L0")


def game_on_pc():
    try:
        return pc('python -c "import sys; sys.path.insert(0, r\'D:\\immich\\vlm\\autobench\'); import autobench as ab; print(ab.game_running())"', timeout=60).strip()
    except Exception as e:
        return f"unknown ({e})"


def work(key):
    g = game_on_pc()
    while g != "None":
        log(STAGE, f"paused: {g}")
        time.sleep(60)
        g = game_on_pc()
    rows = states_for(key)
    states = [r["state"] for r in rows]
    out = [{"bin": r["bin"], "t0": r["t0"]} for r in rows]
    for q in QUESTIONS:
        for o, dc in zip(out, decider.decide_batch(states, q)):
            p = np.asarray(dc.probs, dtype=float)
            if q.kind == "noul":
                o[f"p_{q.name}"] = round(float(p[0]), 4)
            elif q.kind == "score":
                o[f"ev_{q.name}"] = round(float((p * np.arange(len(p))).sum()), 4)
            else:
                keys = ACT_KEYS if q.name == "activity" else MODE_KEYS
                for k, v in zip(keys, p):
                    o[f"p_{q.name}_{k}"] = round(float(v), 4)
    with open(ROOT / key / "anyjev.jsonl.tmp", "w") as fh:
        for o in out:
            fh.write(json.dumps({**o, "model": MODEL, "level": "L0"}) + "\n")
    os.replace(ROOT / key / "anyjev.jsonl.tmp", ROOT / key / "anyjev.jsonl")
    return {"bins": len(out)}


def todo():
    done, bad = ledger(STAGE), failed_twice(STAGE)
    caps, ocr, wh = ledger("sync_captions"), ledger("ocr"), ledger("whisper")
    return [k for k in synced_keys() if k in caps and k in ocr and k in wh and k not in done and k not in bad]


if __name__ == "__main__":
    loop(STAGE, todo, work, done_flag=lambda: upstream_done(STAGE) and (ROOT / "_state" / "PC_CAPTIONS_DONE").exists())

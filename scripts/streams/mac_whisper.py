"""Transcribe the talking streams with mlx-whisper large-v3-turbo -> data/streams/<key>/transcript.json.

Only videos with >= 10 s of VAD speech and >= 2 % speech are transcribed. condition_on_previous_text is off
(the repetition-loop fix that worked for whisper.cpp -mc 0). Segments that do not overlap any VAD speech
segment are dropped as hallucinations over silence/game audio and counted in the ledger.
"""
import json

import mlx_whisper

from common import ROOT, failed_twice, ledger, log, loop, synced_keys, upstream_done

STAGE = "whisper"
REPO = "mlx-community/whisper-large-v3-turbo"


def todo():
    done, bad, aud = ledger(STAGE), failed_twice(STAGE), ledger("audio")
    return [k for k in synced_keys() if k in aud and k not in done and k not in bad]


def overlaps(seg, speech):
    return any(min(seg[1], e) - max(seg[0], s) > 0.2 for s, e in speech)


def work(key):
    d = ROOT / key
    a = json.load(open(d / "audio.json"))
    if not a.get("has_audio") or a["speech_s"] < 10 or a["speech_frac"] < 0.02:
        return {"skipped": "silent", "speech_s": a.get("speech_s", 0)}
    af = d / "audio.flac" if (d / "audio.flac").exists() else d / "audio.opus"
    r = mlx_whisper.transcribe(str(af), path_or_hf_repo=REPO, condition_on_previous_text=False,
                               no_speech_threshold=0.6, compression_ratio_threshold=2.4, verbose=None)
    speech = a["speech_segments"]
    keep, dropped = [], 0
    for s in r["segments"]:
        if overlaps((s["start"], s["end"]), speech) and s["text"].strip():
            keep.append({"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip(),
                         "avg_logprob": round(s.get("avg_logprob", 0), 3), "no_speech_prob": round(s.get("no_speech_prob", 0), 3)})
        else:
            dropped += 1
    json.dump({"language": r.get("language"), "model": REPO, "segments": keep}, open(d / "transcript.json", "w"), ensure_ascii=False)
    return {"language": r.get("language"), "segments": len(keep), "dropped": dropped,
            "words": sum(len(s["text"].split()) for s in keep)}


if __name__ == "__main__":
    loop(STAGE, todo, work, done_flag=lambda: upstream_done("audio", STAGE), outputs=("transcript.json",))

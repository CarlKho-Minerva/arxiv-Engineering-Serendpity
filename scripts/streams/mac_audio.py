"""Audio triage: loudness per second + Silero VAD speech segments -> data/streams/<key>/audio.json.

This is what tags a stream "silent" (no transcription) versus "talking". CPU only.
"""
import json

import numpy as np
import soundfile as sf
import torch
from silero_vad import get_speech_timestamps, load_silero_vad

from common import ROOT, failed_twice, ledger, log, loop, synced_keys, upstream_done

STAGE = "audio"
torch.set_num_threads(4)
MODEL = load_silero_vad()


def todo():
    done, bad = ledger(STAGE), failed_twice(STAGE)
    return [k for k in synced_keys() if k not in done and k not in bad]


def work(key):
    d = ROOT / key
    f = d / "audio.flac"
    if not f.exists():
        out = {"has_audio": False, "speech_s": 0.0, "speech_frac": 0.0}
        json.dump(out, open(d / "audio.json", "w"))
        return out
    wav, sr = sf.read(str(f), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    n = len(wav) // sr
    sec = wav[: n * sr].reshape(n, sr) if n else np.zeros((0, sr), dtype=np.float32)
    rms_db = (20 * np.log10(np.sqrt((sec ** 2).mean(axis=1)) + 1e-9)).round(1).tolist()
    segs = get_speech_timestamps(torch.from_numpy(wav), MODEL, sampling_rate=sr, return_seconds=True,
                                 min_speech_duration_ms=300, min_silence_duration_ms=500)
    speech_s = float(sum(s["end"] - s["start"] for s in segs))
    out = {"has_audio": True, "duration_s": len(wav) / sr, "speech_s": round(speech_s, 1),
           "speech_frac": round(speech_s / max(1.0, len(wav) / sr), 4),
           "silent_frac": round(float(np.mean(np.array(rms_db) < -50)) if rms_db else 1.0, 4),
           "speech_segments": [[round(s["start"], 2), round(s["end"], 2)] for s in segs], "rms_db_per_s": rms_db}
    json.dump(out, open(d / "audio.json", "w"))
    return {k: out[k] for k in ("speech_s", "speech_frac", "silent_frac")}


if __name__ == "__main__":
    loop(STAGE, todo, work, done_flag=lambda: upstream_done(STAGE))

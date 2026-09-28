"""Audio triage: loudness per second + Silero VAD speech segments -> data/streams/<key>/audio.json.

This is what tags a stream "silent" (no transcription) versus "talking". CPU only.
"""
import json

import subprocess

import numpy as np
import torch
from silero_vad import get_speech_timestamps, load_silero_vad

from common import ROOT, failed_twice, ledger, log, loop, synced_keys, upstream_done

STAGE = "audio"
torch.set_num_threads(2)
MODEL = load_silero_vad()


def todo():
    done, bad = ledger(STAGE), failed_twice(STAGE)
    return [k for k in synced_keys() if k not in done and k not in bad]


def work(key):
    d = ROOT / key
    f = d / "audio.flac" if (d / "audio.flac").exists() else d / "audio.opus"
    if not f.exists():
        out = {"has_audio": False, "speech_s": 0.0, "speech_frac": 0.0}
        json.dump(out, open(d / "audio.json", "w"))
        return out
    sr = 16000
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    wav = np.frombuffer(raw, np.float32).copy()
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


def pooled_loop(workers=4):
    """Silero VAD is sequential over 32 ms windows (~16x realtime on 3-hour streams under load), so run 4 videos at once."""
    import concurrent.futures as cf
    import time
    from common import STATE, mark
    log(STAGE, f"start ({workers} processes)")
    with cf.ProcessPoolExecutor(workers) as ex:
        while True:
            if (STATE / "STOP").exists() or (STATE / f"STOP_{STAGE}").exists():
                return
            keys = todo()
            if not keys:
                if upstream_done(STAGE):
                    log(STAGE, "all done")
                    return
                time.sleep(60)
                continue
            futs = {ex.submit(timed, k): k for k in keys[: workers * 3]}
            for f in cf.as_completed(futs):
                k = futs[f]
                try:
                    info, dt = f.result()
                    mark(STAGE, k, s=round(dt, 1), **info)
                except Exception as e:
                    log(STAGE, f"FAIL {k}: {e}")
                    mark(STAGE + "_failed", k, error=str(e)[:300])


def timed(key):
    import time
    t = time.time()
    return work(key), time.time() - t


if __name__ == "__main__":
    pooled_loop()

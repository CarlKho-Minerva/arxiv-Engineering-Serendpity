"""Screen text for every keyframe with Apple Vision -> data/streams/<key>/ocr.jsonl.

Work-like videos use the accurate recognizer (0.13 s/frame with 4 threads, measured 09-27), game videos the
fast one (0.015 s/frame, about half the lines). No language correction, so code and names stay verbatim.
Each row: {"frame", "t", "level", "lines": [[text, confidence, x, y, w, h], ...]} with normalized boxes.
"""
import concurrent.futures as cf
import json
import os

import Vision
from Foundation import NSURL

from common import ROOT, failed_twice, ledger, loop, synced_keys, upstream_done

STAGE = "ocr"
ACCURATE, FAST = 0, 1


def ocr(path, level):
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(level)
    req.setUsesLanguageCorrection_(False)
    h = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(path), None)
    h.performRequests_error_([req], None)
    out = []
    for o in req.results() or []:
        c = o.topCandidates_(1)
        if not c:
            continue
        b = o.boundingBox()
        out.append([c[0].string(), round(float(c[0].confidence()), 3), round(b.origin.x, 4), round(b.origin.y, 4),
                    round(b.size.width, 4), round(b.size.height, 4)])
    return out


def todo():
    done, bad = ledger(STAGE), failed_twice(STAGE)
    return [k for k in synced_keys() if k not in done and k not in bad]


def work(key):
    d = ROOT / key
    m = json.load(open(d / "meta.json"))
    level = ACCURATE if m.get("worklike") else FAST
    frames = sorted(os.listdir(d / "kf"))
    with cf.ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda f: ocr(str(d / "kf" / f), level), frames))
    with open(d / "ocr.jsonl.tmp", "w") as fh:
        for i, (f, lines) in enumerate(zip(frames, res)):
            fh.write(json.dumps({"frame": f, "t": i * 10, "level": "accurate" if level == ACCURATE else "fast", "lines": lines},
                                ensure_ascii=False) + "\n")
    os.replace(d / "ocr.jsonl.tmp", d / "ocr.jsonl")
    return {"frames": len(frames), "level": "accurate" if level == ACCURATE else "fast",
            "lines": sum(map(len, res))}


if __name__ == "__main__":
    loop(STAGE, todo, work, done_flag=lambda: upstream_done(STAGE), outputs=("ocr.jsonl",))

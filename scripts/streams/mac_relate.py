"""RelateAnything (Grounding DINO + RelateModel from recall-glasses) on the face-cam frames of each stream.

Its relation vocabulary is people and objects, so it only runs on keyframes Gemma called "camera" or "mixed",
at most one per minute. Same vocabulary as state-tokens/src/00_relations_day.py ("desk+kitchen v1"), so the
output joins lane_relations. Run with the recall-glasses venv:
  ~/CODELocalProjects/recall-glasses/.venv/bin/python mac_relate.py
Output data/streams/<key>/relations.jsonl.
"""
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/CODELocalProjects/recall-glasses"))
sys.path.insert(0, os.path.expanduser("~/CODELocalProjects/state-tokens/src"))
from common import ROOT, failed_twice, ledger, loop, synced_keys, upstream_done  # noqa: E402

STAGE = "relate"
rd = __import__("00_relations_day")  # LABELS, PREDICATES, MIN_CONF live there; one vocabulary for all lanes
from backend import config  # noqa: E402

config.LABELS[:] = rd.LABELS
config.PREDICATES[:] = rd.PREDICATES
from backend.detector import GroundingDino  # noqa: E402
from backend.relations import RelateModel  # noqa: E402
from PIL import Image  # noqa: E402

det, rel = GroundingDino(), RelateModel()


def work(key):
    d = ROOT / key
    caps = [json.loads(line) for line in open(d / "captions.jsonl")]
    pick, last = [], -1e9
    for c in caps:
        if str(c.get("setting", "")).lower() in ("camera", "mixed") and c["t"] - last >= 60:
            pick.append(c); last = c["t"]
    with open(d / "relations.jsonl.tmp", "w") as out:
        for c in pick:
            img = Image.open(d / "kf" / c["frame"]).convert("RGB")
            dets, _ = det.detect(img)
            rels = []
            if len(dets) >= 2:
                raw, _ = rel.predict(img, dets)
                rels = sorted(({"s": dets[r.subject].label, "p": r.predicate, "o": dets[r.object].label,
                                "c": round(r.confidence, 3)} for r in raw if r.confidence >= rd.MIN_CONF),
                              key=lambda r: -r["c"])[:8]
            out.write(json.dumps({"frame": c["frame"], "t": c["t"], "objects": [{"l": x.label, "s": round(x.score, 3)} for x in dets],
                                  "relations": rels, "vocab": "desk+kitchen v1"}) + "\n")
    os.replace(d / "relations.jsonl.tmp", d / "relations.jsonl")
    return {"frames": len(pick)}


def todo():
    done, bad, caps = ledger(STAGE), failed_twice(STAGE), ledger("sync_captions")
    return [k for k in synced_keys() if k in caps and k not in done and k not in bad]


if __name__ == "__main__":
    loop(STAGE, todo, work, done_flag=lambda: upstream_done(STAGE) and (ROOT / "_state" / "PC_CAPTIONS_DONE").exists())

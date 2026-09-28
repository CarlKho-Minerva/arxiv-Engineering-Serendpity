"""Shared paths and ledgers for the Mac side of the stream-archive pipeline.

Every stage is a separate resumable process: it lists the videos synced from the PC, skips the ones its
own ledger marks done, and appends one ledger line per finished video. Outputs live next to the synced
inputs in data/streams/<key>/ (git-ignored; data/ never leaves this machine).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "streams"
STATE = ROOT / "_state"
ROOT.mkdir(parents=True, exist_ok=True)
STATE.mkdir(parents=True, exist_ok=True)
PC = os.environ.get("PC_HOST", "PC")


def log(stage, msg):
    line = time.strftime("%Y-%m-%dT%H:%M:%S ") + msg
    with open(STATE / f"{stage}.log", "a") as fh:
        fh.write(line + "\n")
    print(f"[{stage}] {line}", flush=True)


def ledger(stage):
    p = STATE / f"{stage}.jsonl"
    out = {}
    if p.exists():
        for line in p.open():
            try:
                r = json.loads(line)
                out[r["key"]] = r
            except Exception:
                pass
    return out


def mark(stage, key, **kw):
    with open(STATE / f"{stage}.jsonl", "a") as fh:
        fh.write(json.dumps({"key": key, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **kw}) + "\n")


def synced_keys():
    """Keys in PC manifest order that the sync stage has fully pulled."""
    done = ledger("sync")
    order = manifest_order()
    return sorted(done, key=lambda k: order.get(k, 1e9))


def manifest_order():
    p = STATE / "manifest.json"
    if not p.exists():
        return {}
    return {r["key"]: i for i, r in enumerate(json.load(open(p)))}


def meta(key):
    return json.load(open(ROOT / key / "meta.json"))


def pc(cmd, timeout=120):
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", PC, cmd], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ssh {cmd!r} rc={r.returncode}: {r.stderr[-300:]}")
    return r.stdout


def loop(stage, todo_fn, work_fn, idle_s=60, done_flag=None):
    """Run work_fn(key) for every key todo_fn() yields, forever (until done_flag() says the upstream is finished)."""
    log(stage, "start")
    while True:
        todo = todo_fn()
        if not todo:
            if done_flag and done_flag():
                log(stage, "all done")
                return
            time.sleep(idle_s)
            continue
        for key in todo:
            if (STATE / f"STOP_{stage}").exists() or (STATE / "STOP").exists():
                log(stage, "stop file present")
                return
            t = time.time()
            try:
                info = work_fn(key) or {}
                mark(stage, key, s=round(time.time() - t, 1), **info)
            except Exception as e:
                import traceback
                log(stage, f"FAIL {key}: {e}\n{traceback.format_exc()[-1200:]}")
                mark(stage + "_failed", key, error=str(e)[:300])


def failed_twice(stage):
    p = STATE / f"{stage}_failed.jsonl"
    c = {}
    if p.exists():
        for line in p.open():
            try:
                k = json.loads(line)["key"]
                c[k] = c.get(k, 0) + 1
            except Exception:
                pass
    return {k for k, n in c.items() if n >= 2}


def upstream_done(*stages):
    """True when the PC finished Step 0 and every listed local stage covered every synced key."""
    if not (STATE / "PC_STEP0_DONE").exists():
        return False
    keys = set(ledger("sync"))
    return all(keys <= set(ledger(s)) | failed_twice(s) for s in stages)


if __name__ == "__main__":
    sys.exit("library module")

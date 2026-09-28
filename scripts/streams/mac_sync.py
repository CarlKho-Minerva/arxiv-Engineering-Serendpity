"""Pull finished Step 0 outputs (and later the Gemma captions) from the PC to data/streams/<key>/.

Uses `tar` over ssh (Windows ships bsdtar), so each video is one stream over the wired LAN.
Also mirrors the PC ledgers/status into data/streams/_state/ for the other stages and the morning report.
"""
import json
import subprocess
import time

from common import PC, ROOT, STATE, ledger, log, mark, pc

STAGE = "sync"


def pc_ledger(name, stage):
    out = {}
    txt = pc(f"type D:\\streams\\{name} 2>nul", timeout=120)
    for line in txt.splitlines():
        try:
            r = json.loads(line)
            if r.get("stage") == stage:
                out[r["key"]] = r
        except Exception:
            pass
    return out


def ensure_opus(key):
    """Speech-grade 24 kbps Opus next to the FLAC on the PC (5x smaller over the relayed tailnet; FLAC stays there)."""
    pc(f'if not exist "C:\\streams\\out\\{key}\\audio.opus" ffmpeg -v error -y -i "C:\\streams\\out\\{key}\\audio.flac" '
       f'-c:a libopus -b:a 24k -application voip "C:\\streams\\out\\{key}\\audio.opus"', timeout=600)


def pull(key, members):
    dst = ROOT
    # "./" keeps YouTube ids that start with "-" from being read as tar options
    # some keys are YouTube ids the Takeout CSV wrote with a leading space (ids starting with "-"): quote every path
    paths = " ".join(f'"./{key}/{m}"' for m in members)
    cmd = f"ssh -o ConnectTimeout=15 {PC} 'tar -C C:/streams/out -cf - {paths}' | tar -xf - -C '{dst}'"
    r = subprocess.run(["bash", "-o", "pipefail", "-c", cmd], capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])
    missing = [m for m in members if not (ROOT / key / m).exists()]
    if missing:
        raise RuntimeError(f"pulled but missing {missing}: {r.stderr[-200:]}")


def main():
    log(STAGE, "start")
    while True:
        try:
            man = pc("type D:\\streams\\manifest.json", timeout=120)
            (STATE / "manifest.json").write_text(man)
            s0 = pc_ledger("step0_ledger.jsonl", "step0")
            caps = pc_ledger("captions_ledger.jsonl", "captions")
            for name in ("step0_status.json", "captions_status.json"):
                try:
                    (STATE / f"pc_{name}").write_text(pc(f"type D:\\streams\\{name}"))
                except Exception:
                    pass
            if "STEP0_DONE" in pc("dir /b D:\\streams"):
                (STATE / "PC_STEP0_DONE").write_text("1")
            if "CAPTIONS_DONE" in pc("dir /b D:\\streams"):
                (STATE / "PC_CAPTIONS_DONE").write_text("1")
        except Exception as e:
            log(STAGE, f"PC unreachable or ledger read failed: {e}")
            time.sleep(120)
            continue
        done = ledger(STAGE)
        got_caps = ledger("sync_captions")
        order = {r["key"]: i for i, r in enumerate(json.loads(man))}
        pulled = 0
        for key in sorted(s0, key=lambda k: order.get(k, 1e9)):
            if key in done:
                continue
            if pulled >= 20:  # leave room in every cycle for captions and a fresh status read
                break
            pulled += 1
            t = time.time()
            try:
                if s0[key].get("has_audio"):
                    ensure_opus(key)
                pull(key, ["meta.json", "proxy.mp4", "kf"] + (["audio.opus"] if s0[key].get("has_audio") else []))
                mark(STAGE, key, s=round(time.time() - t, 1))
            except Exception as e:
                log(STAGE, f"FAIL pull {key}: {e}")
        for key in sorted(caps, key=lambda k: order.get(k, 1e9)):
            if key in got_caps or key not in ledger(STAGE):
                continue
            try:
                pull(key, ["captions.jsonl"])
                mark("sync_captions", key, n=caps[key].get("n"))
            except Exception as e:
                log(STAGE, f"FAIL pull captions {key}: {e}")
        if (STATE / "PC_STEP0_DONE").exists() and (STATE / "PC_CAPTIONS_DONE").exists() \
                and set(s0) <= set(ledger(STAGE)) and set(caps) <= set(ledger("sync_captions")):
            log(STAGE, "all synced")
            return
        time.sleep(60)


if __name__ == "__main__":
    main()

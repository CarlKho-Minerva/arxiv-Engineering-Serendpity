"""Pull finished Step 0 outputs (and later the Gemma captions) from the PC to data/streams/<key>/.

Uses `tar` over ssh (Windows ships bsdtar), so each video is one stream over the wired LAN.
Also mirrors the PC ledgers/status into data/streams/_state/ for the other stages and the morning report.
"""
import concurrent.futures as cf
import json
import os
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


def full_pull(key):
    cmd = (f"ssh -o ConnectTimeout=15 {PC} 'tar -C C:/streams/out --exclude audio.flac --exclude \"*.tmp.opus\" -cf - \"./{key}\"' "
           f"| tar -xf - -C '{ROOT}'")
    r = subprocess.run(["bash", "-o", "pipefail", "-c", cmd], capture_output=True, text=True, timeout=3600)
    if r.returncode != 0 or not (ROOT / key / "meta.json").exists():
        raise RuntimeError(f"full pull {key}: {r.stderr[-300:]}")


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
        if (STATE / "PC_STEP0_DONE").exists() and s0 and set(s0) <= set(done):
            (STATE / "SYNC_DONE").write_text(f"{len(done)} videos\n")
        order = {r["key"]: i for i, r in enumerate(json.loads(man))}
        batch = [k for k in sorted(s0, key=lambda k: order.get(k, 1e9)) if k not in done][:30]  # then captions + status

        def primary(key):
            t = time.time()
            try:
                if s0[key].get("has_audio"):
                    ensure_opus(key)
                if os.environ.get("STREAMS_FULL_PULL") == "1":  # worker on the PC's LAN: everything but the FLAC, one stream
                    full_pull(key)
                    for extra in ("sync_captions", "sync_proxy"):
                        mark(extra, key)
                else:
                    pull(key, ["meta.json", "kf"] + (["audio.opus"] if s0[key].get("has_audio") else []))
                mark(STAGE, key, s=round(time.time() - t, 1))
            except Exception as e:
                log(STAGE, f"FAIL pull {key}: {e}")
        # 3 streams: the relayed path gave 1.6 MB/s for one, 2.1 MB/s for four (measured 09-28 00:10)
        with cf.ThreadPoolExecutor(3) as ex:
            list(ex.map(primary, batch))
        # proxies (only V-JEPA reads them) go last: over the relayed tailnet (~1.6 MB/s) keyframes + audio come first
        if not [k for k in s0 if k not in ledger(STAGE)]:
            got_proxy = ledger("sync_proxy")
            for key in [k for k in sorted(s0, key=lambda k: order.get(k, 1e9)) if k not in got_proxy][:20]:
                try:
                    t = time.time()
                    pull(key, ["proxy.mp4"])
                    mark("sync_proxy", key, s=round(time.time() - t, 1))
                except Exception as e:
                    log(STAGE, f"FAIL pull proxy {key}: {e}")
        for key in sorted(caps, key=lambda k: order.get(k, 1e9)):
            if key in got_caps or key not in ledger(STAGE):
                continue
            try:
                pull(key, ["captions.jsonl"])
                mark("sync_captions", key, n=caps[key].get("n"))
            except Exception as e:
                log(STAGE, f"FAIL pull captions {key}: {e}")
        if (STATE / "PC_STEP0_DONE").exists() and (STATE / "PC_CAPTIONS_DONE").exists() \
                and set(s0) <= set(ledger(STAGE)) and set(caps) <= set(ledger("sync_captions")) \
                and set(s0) <= set(ledger("sync_proxy")):
            log(STAGE, "all synced")
            return
        time.sleep(60)


if __name__ == "__main__":
    main()

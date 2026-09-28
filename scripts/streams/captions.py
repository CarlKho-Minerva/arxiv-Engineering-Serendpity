"""Caption the Step 0 keyframes with the eGPU's vLLM Gemma 4 31B (PC). Resumable, game-gated.

Per video (in manifest order, as soon as Step 0 has it):
  probe: every 12th keyframe (1 per 2 min)
  then:  if >= 80 % of probe frames are gameplay -> every 6th keyframe (1 per min), else every 3rd (1 per 30 s).
        vLLM saturates at ~0.52 s/frame (measured 09-27, same at 4/12/16 concurrent), so 1 per 10 s for ~330 h of
        work would take ~18 h; the Mac covers every keyframe with SigLIP + OCR instead, and denser captions can be
        added later from the same keyframes
Writes C:\\streams\\out\\<key>\\captions.jsonl (one row per captioned keyframe, with t in seconds).
Pauses between batches while a game runs on the internal card or the UPS is on battery.
Never loads a model itself: it only sends HTTP requests to the vLLM server that already owns the eGPU.
"""
import base64, concurrent.futures as cf, glob, json, os, re, subprocess, sys, time, traceback, urllib.request

sys.path.insert(0, r"D:\immich\vlm\autobench")
import autobench as ab

CTRL = r"D:\streams"
OUT = r"C:\streams\out"
VLLM = "http://127.0.0.1:8000/v1/chat/completions"
LEDGER_S0 = os.path.join(CTRL, "step0_ledger.jsonl")
LEDGER = os.path.join(CTRL, "captions_ledger.jsonl")
STATUS = os.path.join(CTRL, "captions_status.json")
LOG = os.path.join(CTRL, "captions.log")
CONC = int(os.environ.get("CAPTION_CONC", "8"))
NO_WINDOW = 0x08000000
PROMPT = ("This is one frame from Carl's personal livestream archive. Answer in JSON only, with keys: "
          "\"setting\" (screen, camera, or mixed), "
          "\"activity\" (short phrase, e.g. coding, writing, reading, design, video call, meeting, gameplay, browsing, watching video, "
          "talking to camera, presenting, eating, idle screen, other), "
          "\"app_or_game\" (main application, website, or game visible, else null), "
          "\"topic\" (what the work or content is about in a few words, else null), "
          "\"people_visible\" (integer), "
          "\"caption\" (one sentence).")
state = {"phase": "starting", "videos_done": 0, "frames_done": 0, "current": None, "paused_for": None, "errors": 0,
         "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def log(msg):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + msg + "\n")


def write_status():
    s = dict(state, ts=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    with open(STATUS + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=1)
    os.replace(STATUS + ".tmp", STATUS)


def keys_with(ledger, stage):
    out = []
    if os.path.exists(ledger):
        for line in open(ledger, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r["stage"] == stage:
                    out.append(r["key"])
            except Exception:
                pass
    return out


def ups_on_battery():
    try:
        o = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Battery).BatteryStatus"],
                           capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW).stdout.strip()
        return o == "1"
    except Exception:
        return False


def gate():
    try:
        g = ab.game_running()
        if g:
            return "game: " + g
    except Exception as e:
        log(f"game check failed: {e}")
    if ups_on_battery():
        return "UPS on battery"
    return None


def wait_gate():
    g = gate()
    while g:
        state["paused_for"] = g
        write_status()
        time.sleep(20)
        g = gate()
    state["paused_for"] = None


def caption(fp):
    b = base64.b64encode(open(fp, "rb").read()).decode()
    body = {"model": "gemma-4-31b-it", "max_tokens": 220, "temperature": 0,
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}},
                                                      {"type": "text", "text": PROMPT}]}],
            "chat_template_kwargs": {"enable_thinking": False}}
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(VLLM, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            out = json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", out, re.S)
            try:
                return json.loads(m.group(0)) if m else {"raw": out}
            except Exception:
                return {"raw": out}
        except Exception as e:
            last = e
            time.sleep(15 * (attempt + 1))
    return {"error": str(last)[:200]}


def caption_many(frames):
    res = [None] * len(frames)
    with cf.ThreadPoolExecutor(CONC) as ex:
        for s in range(0, len(frames), CONC * 4):
            wait_gate()
            idx = list(range(s, min(s + CONC * 4, len(frames))))
            for j, r in zip(idx, ex.map(caption, [frames[k] for k in idx])):
                res[j] = r
            state["frames_done"] += len(idx)
            write_status()
    return res


def is_game(c):
    return "game" in str(c.get("activity", "")).lower()


def do_video(key):
    od = os.path.join(OUT, key)
    frames = sorted(glob.glob(os.path.join(od, "kf", "*.jpg")))
    if not frames:
        return {"n": 0, "mode": "no_frames"}
    probe_idx = list(range(0, len(frames), 12))
    caps = dict(zip(probe_idx, caption_many([frames[k] for k in probe_idx])))
    ok = [c for c in caps.values() if "activity" in c]
    game_share = sum(is_game(c) for c in ok) / max(1, len(ok))
    step = 6 if game_share >= 0.8 else 3
    rest = [k for k in range(0, len(frames), step) if k not in caps]
    caps.update(zip(rest, caption_many([frames[k] for k in rest])))
    with open(os.path.join(od, "captions.jsonl.tmp"), "w", encoding="utf-8") as fh:
        for k in sorted(caps):
            fh.write(json.dumps({"frame": os.path.basename(frames[k]), "t": k * 10, **caps[k]}, ensure_ascii=False) + "\n")
    os.replace(os.path.join(od, "captions.jsonl.tmp"), os.path.join(od, "captions.jsonl"))
    errs = sum(1 for c in caps.values() if "error" in c)
    return {"n": len(caps), "game_share": round(game_share, 3), "step": step, "errors": errs,
            "valid": sum(1 for c in caps.values() if "activity" in c)}


def main():
    if os.path.exists(os.path.join(CTRL, "STOP_CAPTIONS")):
        return
    order = {r["key"]: i for i, r in enumerate(json.load(open(os.path.join(CTRL, "manifest.json"), encoding="utf-8")))}
    state["phase"] = "running"
    while True:
        done = set(keys_with(LEDGER, "captions"))
        ready = sorted((k for k in set(keys_with(LEDGER_S0, "step0")) if k not in done), key=lambda k: order.get(k, 1e9))
        if not ready:
            if os.path.exists(os.path.join(CTRL, "STEP0_DONE")):
                state["phase"] = "done"; write_status()
                open(os.path.join(CTRL, "CAPTIONS_DONE"), "w").write(f"{len(done)} videos\n")
                return
            state["phase"] = "waiting for step0"; write_status()
            time.sleep(30)
            continue
        key = ready[0]
        state["current"] = key; write_status()
        t = time.time()
        try:
            r = do_video(key)
        except Exception as e:
            log(f"failed {key}: {e}\n{traceback.format_exc()[-600:]}")
            state["errors"] += 1
            time.sleep(30)
            continue
        with open(LEDGER, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "stage": "captions", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "s": round(time.time() - t, 1), **r}) + "\n")
        if r.get("errors"):
            log(f"{key}: {r['errors']} caption errors of {r['n']}")
            state["errors"] += 1
        state["videos_done"] += 1


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL " + traceback.format_exc())
        state["phase"] = "error"; state["error"] = traceback.format_exc()[-1500:]; write_status()
        sys.exit(1)

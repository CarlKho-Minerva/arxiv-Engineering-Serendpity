"""Step 0 of the stream archive: read every video out of the carlcrafters Takeout exactly once.

Runs on the PC (Windows python, CPU only, IDLE priority). Per video it writes C:\\streams\\out\\<key>\\:
  proxy.mp4   480p, 10 fps, H.264 CRF 30   (every later video model reads this, never the 2.5 TB again)
  kf\\f_00001.jpg ...  one full-width frame every 10 s (frame k is at t = (k-1)*10 s)
  audio.flac  16 kHz mono (absent when the video has no audio track)
  meta.json   manifest row + ffprobe facts
The zip stays the source; the temporary mp4 on C: is deleted after each video.

Scheduling: one extractor thread (the D: disk reads sequentially) feeds up to 3 ffmpeg workers.
While a game runs on the internal card (autobench.game_running) only one worker runs.
Resumable: ledger.jsonl in D:\\streams records finished keys. status.json is rewritten every 30 s.
A STOP file in D:\\streams makes it exit after the current video.
"""
import collections, csv, glob, io, json, os, re, shutil, subprocess, sys, threading, time, traceback, unicodedata, zipfile

sys.path.insert(0, r"D:\immich\vlm\autobench")
import autobench as ab

CTRL = r"D:\streams"
OUT = r"C:\streams\out"
TMP = r"C:\streams\tmp"
SRC = r"D:\carlcrafters-takeout-20260906"
PREFIX = "Takeout/YouTube and YouTube Music/videos/"
META_PREFIX = "Takeout/YouTube and YouTube Music/video metadata/videos"
LEDGER = os.path.join(CTRL, "step0_ledger.jsonl")
STATUS = os.path.join(CTRL, "step0_status.json")
LOG = os.path.join(CTRL, "step0.log")
MANIFEST = os.path.join(CTRL, "manifest.json")
WORKERS = 3
TMP_AHEAD = 3
MIN_FREE_C = 150e9
IDLE = 0x00000040  # IDLE_PRIORITY_CLASS
WORKLIKE = re.compile(r"work|study|symph|code|coding|dev|build|homework|school|class|minerva|cs\d|project|hackathon|design|figma|thesis|capstone|research|intern|startup|somach|mentra|productiv|cowork|focus|pomodoro|writing|essay|pset|assignment|agent|demo|pitch|omi|wflo|velum|devlog", re.I)

os.makedirs(OUT, exist_ok=True); os.makedirs(TMP, exist_ok=True); os.makedirs(CTRL, exist_ok=True)
lock = threading.Lock()
state = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "phase": "starting", "total": 0, "done": 0, "failed": 0,
         "hours_done": 0.0, "hours_total": 0.0, "extracting": None, "decoding": [], "game": None, "workers_allowed": WORKERS}


def log(msg):
    with lock, open(LOG, "a", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + msg + "\n")


def mark(key, stage, **kw):
    with lock, open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"key": key, "stage": stage, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **kw}) + "\n")


def done_keys():
    """Keys finished, plus keys that failed twice (skipped so a broken file cannot loop the runner)."""
    out, fails = set(), collections.Counter()
    if os.path.exists(LEDGER):
        for line in open(LEDGER, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r["stage"] == "step0":
                    out.add(r["key"])
                elif r["stage"] == "step0_failed":
                    fails[r["key"]] += 1
            except Exception:
                pass
    return out, {k for k, n in fails.items() if n >= 2}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s or "").lower())


def build_manifest():
    meta = collections.defaultdict(list)
    zips = sorted(glob.glob(os.path.join(SRC, "*.zip")))
    for z in zips:
        try:
            zf = zipfile.ZipFile(z)
        except Exception as e:
            log(f"zip unreadable {z}: {e}")
            continue
        for n in zf.namelist():
            if n.startswith(META_PREFIX) and n.endswith(".csv"):
                for row in csv.DictReader(io.TextIOWrapper(zf.open(n), encoding="utf-8")):
                    meta[norm(row.get("Video Title (Original)"))].append(row)
    items, seen = [], set()
    for z in zips:
        try:
            zf = zipfile.ZipFile(z)
        except Exception:
            continue
        for i in zf.infolist():
            if not i.filename.startswith(PREFIX) or i.is_dir():
                continue
            stem = i.filename[len(PREFIX):].rsplit(".", 1)[0]
            cands = meta.get(norm(re.sub(r"\(\d+\)$", "", stem)), [])
            row = cands[0] if len(cands) == 1 else {}
            vid = row.get("Video ID")
            key = vid if vid and vid not in seen else "noid_%08x" % (zlib_crc(i.filename))
            seen.add(key)
            text = stem + " " + (row.get("Video Description (Original)") or "")
            cat = row.get("Video Category") or ""
            items.append({"key": key, "zip": z, "inner": i.filename, "bytes": i.file_size, "ext": i.filename.rsplit(".", 1)[-1].lower(),
                          "title_match": len(cands), "video_id": vid, "created": row.get("Video Create Timestamp"),
                          "duration_ms": row.get("Approx Duration (ms)"), "category": cat, "privacy": row.get("Privacy"),
                          "worklike": bool(WORKLIKE.search(text)) or (cat not in ("Gaming", "")),
                          "candidates": [{"video_id": c.get("Video ID"), "duration_ms": c.get("Approx Duration (ms)"),
                                          "created": c.get("Video Create Timestamp"), "category": c.get("Video Category"),
                                          "privacy": c.get("Privacy")} for c in cands] if len(cands) > 1 else [],
                          })
    # work-like first, then the rest; oldest first inside each group
    items.sort(key=lambda x: (not x["worklike"], x["created"] or "9999", x["key"]))
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=0)
    return items


def zlib_crc(s):
    import zlib
    return zlib.crc32(s.encode("utf-8"))


def game():
    try:
        return ab.game_running()
    except Exception as e:
        log(f"game check failed: {e}")
        return None


def status_loop():
    while True:
        g = game()
        with lock:
            state["game"] = g
            state["workers_allowed"] = 1 if g else WORKERS
            s = dict(state)
        s["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        try:
            s["c_free_gb"] = round(shutil.disk_usage("C:\\").free / 1e9, 1)
            with open(STATUS + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(s, fh, indent=1)
            os.replace(STATUS + ".tmp", STATUS)
        except Exception:
            pass
        time.sleep(30)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=IDLE)


def decode(item, src):
    key = item["key"]
    od = os.path.join(OUT, key)
    part = od + ".part"
    shutil.rmtree(part, ignore_errors=True)
    os.makedirs(os.path.join(part, "kf"), exist_ok=True)
    pr = run(["ffprobe", "-v", "error", "-show_entries", "format=duration,start_time:stream=index,codec_type,codec_name,width,height,r_frame_rate",
              "-of", "json", src])
    info = json.loads(pr.stdout or "{}")
    streams = info.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_video = any(s.get("codec_type") == "video" for s in streams)
    if not has_video:
        raise RuntimeError("no video stream: " + pr.stderr[:200])
    cmd = ["ffmpeg", "-v", "error", "-y", "-threads", "6", "-i", src,
           "-filter_complex", "[0:v:0]split=2[a][b];[a]fps=10,scale=-2:480:flags=bicubic[p];[b]fps=1/10:round=down,scale='min(1920,iw)':-2[k]",
           "-map", "[p]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-g", "100", "-an", os.path.join(part, "proxy.mp4"),
           "-map", "[k]", "-q:v", "3", os.path.join(part, "kf", "f_%05d.jpg")]
    if has_audio:
        cmd += ["-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", os.path.join(part, "audio.flac")]
    t = time.time()
    r = run(cmd)
    kf_method = "fps=1/10"
    if r.returncode != 0 and "mjpeg" in r.stderr:
        # very short clips give the fps=1/10 branch no frame at all; take the first frame and then one every >= 10 s
        shutil.rmtree(part, ignore_errors=True)
        os.makedirs(os.path.join(part, "kf"), exist_ok=True)
        fc = cmd[cmd.index("-filter_complex") + 1].replace("[b]fps=1/10:round=down,", "[b]select='isnan(prev_selected_t)+gte(t-prev_selected_t,10)',")
        cmd2 = list(cmd)
        cmd2[cmd.index("-filter_complex") + 1] = fc
        i = cmd2.index(os.path.join(part, "kf", "f_%05d.jpg"))
        cmd2[i:i] = ["-fps_mode", "vfr"]
        r = run(cmd2)
        kf_method = "select>=10s"
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg rc={r.returncode}: {r.stderr[-400:]}")
    fmt = info.get("format", {})
    dur = float(fmt.get("duration") or 0)
    resolved = None
    if item.get("candidates"):  # same title on several videos: take the one whose duration is closest
        best = min(item["candidates"], key=lambda c: abs(float(c["duration_ms"] or 0) / 1000 - dur))
        if abs(float(best["duration_ms"] or 0) / 1000 - dur) <= max(5.0, 0.02 * dur):
            resolved = best
    n_kf = len(glob.glob(os.path.join(part, "kf", "*.jpg")))
    meta = {**item, "resolved_by_duration": resolved, "duration_s": dur, "start_time": float(fmt.get("start_time") or 0),
            "streams": streams, "has_audio": has_audio, "n_keyframes": n_kf, "keyframe_interval_s": 10, "keyframe_method": kf_method,
            "proxy": {"fps": 10, "height": 480, "codec": "h264", "crf": 30}, "decode_s": round(time.time() - t, 1),
            "ffmpeg_warnings": r.stderr[-400:] if r.stderr else ""}
    with open(os.path.join(part, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    shutil.rmtree(od, ignore_errors=True)
    os.replace(part, od)
    return meta


def main():
    if os.path.exists(os.path.join(CTRL, "STOP")):
        print("STOP present"); return
    for f in glob.glob(os.path.join(TMP, "*")):  # leftovers from a killed run
        try:
            os.remove(f)
        except OSError:
            pass
    items = build_manifest()
    done, given_up = done_keys()
    todo = [i for i in items if i["key"] not in done and i["key"] not in given_up]
    if not todo:
        open(os.path.join(CTRL, "STEP0_DONE"), "w").write(f"{len(done)} done, {len(given_up)} given up\n")
        return
    with lock:
        state.update(total=len(items), done=len(items) - len(todo), phase="running",
                     hours_total=round(sum(float(i["duration_ms"] or 0) for i in items) / 3.6e6, 1),
                     hours_done=round(sum(float(i["duration_ms"] or 0) for i in items if i["key"] in done) / 3.6e6, 1))
    threading.Thread(target=status_loop, daemon=True).start()
    log(f"start: {len(items)} videos, {len(todo)} to do")
    ready = collections.deque()
    cond = threading.Condition()
    finished = {"extract": False}

    def extractor():
        for it in todo:
            if os.path.exists(os.path.join(CTRL, "STOP")):
                break
            with cond:
                while len(ready) >= TMP_AHEAD or shutil.disk_usage("C:\\").free < MIN_FREE_C:
                    cond.wait(20)
            dst = os.path.join(TMP, f"{it['key']}.{it['ext']}")
            with lock:
                state["extracting"] = it["key"]
            try:
                t = time.time()
                with zipfile.ZipFile(it["zip"]) as zf, zf.open(it["inner"]) as s, open(dst + ".part", "wb") as d:
                    shutil.copyfileobj(s, d, 64 << 20)
                os.replace(dst + ".part", dst)
                it["extract_s"] = round(time.time() - t, 1)
            except Exception as e:
                log(f"extract failed {it['key']}: {e}")
                mark(it["key"], "step0_failed", error=f"extract: {e}"[:300])
                with lock:
                    state["failed"] += 1
                try:
                    os.remove(dst + ".part")
                except OSError:
                    pass
                continue
            with cond:
                ready.append((it, dst)); cond.notify_all()
        with cond:
            finished["extract"] = True; cond.notify_all()
        with lock:
            state["extracting"] = None

    def worker(idx):
        while True:
            with cond:
                while True:
                    allowed = state["workers_allowed"]
                    if ready and idx < allowed:
                        it, src = ready.popleft(); cond.notify_all(); break
                    if finished["extract"] and not ready:
                        return
                    cond.wait(15)
            with lock:
                state["decoding"].append(it["key"])
            try:
                m = decode(it, src)
                mark(it["key"], "step0", duration_s=m["duration_s"], n_keyframes=m["n_keyframes"], has_audio=m["has_audio"],
                     decode_s=m["decode_s"], extract_s=it.get("extract_s"))
                with lock:
                    state["done"] += 1
                    state["hours_done"] = round(state["hours_done"] + m["duration_s"] / 3600, 2)
            except Exception as e:
                log(f"decode failed {it['key']}: {e}\n{traceback.format_exc()[-800:]}")
                mark(it["key"], "step0_failed", error=str(e)[:300])
                with lock:
                    state["failed"] += 1
            finally:
                with lock:
                    state["decoding"].remove(it["key"])
                try:
                    os.remove(src)
                except OSError:
                    pass

    threading.Thread(target=extractor, daemon=True).start()
    ws = [threading.Thread(target=worker, args=(i,)) for i in range(WORKERS)]
    for w in ws:
        w.start()
    for w in ws:
        w.join()
    with lock:
        state["phase"] = "done" if not os.path.exists(os.path.join(CTRL, "STOP")) else "stopped"
    log(f"end: done={state['done']} failed={state['failed']}")
    if state["phase"] == "done" and state["failed"] == 0:
        open(os.path.join(CTRL, "STEP0_DONE"), "w").write(f"{state['done']} done\n")
    time.sleep(35)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL " + traceback.format_exc())
        with open(STATUS, "w", encoding="utf-8") as fh:
            json.dump({"phase": "error", "error": traceback.format_exc()[-1500:], "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, fh)
        sys.exit(1)

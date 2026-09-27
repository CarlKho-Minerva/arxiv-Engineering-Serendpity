import subprocess, time, json, os, glob, base64, urllib.request, concurrent.futures as cf, collections, re
P = r"D:\stream_pilot"; V = P + r"\pilot.mp4"; os.makedirs(P + r"\frames", exist_ok=True)
T = {}
def run(cmd):
    t = time.time(); r = subprocess.run(cmd, capture_output=True, text=True, shell=True); return time.time() - t, r
T["frames_10s_s"], _ = run(f'ffmpeg -v error -y -skip_frame nokey -i "{V}" -vf "fps=1/10,scale=1024:-2" -q:v 3 "{P}\\frames\\f_%05d.jpg"')
frames = sorted(glob.glob(P + r"\frames\*.jpg")); T["n_frames"] = len(frames)
T["scene_detect_s"], r = run(f'ffmpeg -v info -skip_frame nokey -i "{V}" -vf "scale=320:-2,select=gt(scene\\,0.25),showinfo" -f null - 2>&1')
T["scene_changes"] = len(re.findall(r"pts_time:", r.stdout + r.stderr))
T["audio_s"], _ = run(f'ffmpeg -v error -y -i "{V}" -vn -ac 1 -ar 16000 "{P}\\audio.wav"')
PROMPT = ("Describe this frame from a personal livestream in JSON with keys: "
          "\"setting\" (screen, camera, or mixed), \"activity\" (short phrase, e.g. coding, writing, video call, gameplay, browsing, talking to camera), "
          "\"app_or_game\" (name if visible, else null), \"people_visible\" (integer), \"caption\" (one sentence). Output JSON only.")
def cap(fp):
    b = base64.b64encode(open(fp, "rb").read()).decode()
    body = {"model": "gemma-4-31b-it", "max_tokens": 160, "temperature": 0,
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}},
                                                      {"type": "text", "text": PROMPT}]}],
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    out = json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", out, re.S)
    try: return json.loads(m.group(0)) if m else {"raw": out}
    except Exception: return {"raw": out}
t = time.time()
with cf.ThreadPoolExecutor(4) as ex: caps = list(ex.map(cap, frames))
T["caption_s"] = time.time() - t; T["caption_s_per_frame"] = T["caption_s"] / max(1, len(frames))
with open(P + r"\captions.jsonl", "w", encoding="utf-8") as fh:
    for fp, c in zip(frames, caps): fh.write(json.dumps({"frame": os.path.basename(fp), **c}, ensure_ascii=False) + "\n")
T["valid_json"] = sum(1 for c in caps if "activity" in c)
T["setting"] = collections.Counter(str(c.get("setting")) for c in caps).most_common(4)
T["activity_top"] = collections.Counter(str(c.get("activity")).lower()[:30] for c in caps).most_common(6)
T["app_top"] = collections.Counter(str(c.get("app_or_game")) for c in caps).most_common(5)
T["people_visible_mean"] = sum(int(c.get("people_visible") or 0) for c in caps if isinstance(c.get("people_visible"), (int, float))) / max(1, len(caps))
json.dump(T, open(P + r"\timings.json", "w"), indent=1); print(json.dumps(T, indent=1))

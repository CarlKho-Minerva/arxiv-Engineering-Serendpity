import zipfile, json, time, shutil, os, sys
d = json.load(open(r"C:\Users\Carlk\pilot_pick.json"))
os.makedirs(r"D:\stream_pilot", exist_ok=True)
t0 = time.time()
with zipfile.ZipFile(d["zip"]) as z, z.open(d["inner"]) as src, open(r"D:\stream_pilot\pilot.mp4", "wb") as dst:
    shutil.copyfileobj(src, dst, 64 * 1024 * 1024)
print("extracted %.1f GB in %.0f s" % (os.path.getsize(r"D:\stream_pilot\pilot.mp4") / 1e9, time.time() - t0))

"""One-shot (PC): write audio.opus (24 kbps, speech grade) next to every audio.flac in C:\\streams\\out that lacks one."""
import concurrent.futures as cf, glob, os, subprocess
IDLE = 0x00000040
todo = [d for d in glob.glob(r"C:\streams\out\*") if os.path.exists(os.path.join(d, "audio.flac")) and not os.path.exists(os.path.join(d, "audio.opus"))]
def conv(d):
    tmp = os.path.join(d, "audio.opus.tmp.opus")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(d, "audio.flac"), "-c:a", "libopus", "-b:a", "24k", "-application", "voip", tmp],
                       capture_output=True, text=True, creationflags=IDLE)
    if r.returncode == 0:
        os.replace(tmp, os.path.join(d, "audio.opus"))
    return r.returncode
with cf.ThreadPoolExecutor(3) as ex:
    rcs = list(ex.map(conv, todo))
open(r"D:\streams\opus_backfill.done", "w").write(f"{len(todo)} converted, {sum(1 for r in rcs if r)} failed\n")

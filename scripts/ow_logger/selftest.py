"""End-to-end self-test for ow_logger with Notepad standing in for Overwatch.

Must run in Carl's interactive desktop session (install.ps1 -SelfTest registers
a one-shot interactive task for it). It:
  1. asks Windows to turn the display on (Desktop Duplication delivers no
     frames while the monitor is asleep),
  2. starts logger.py --target notepad.exe --once into <out>\\_selftest,
  3. opens Notepad for ~30 s, then closes only the Notepad it opened,
  4. waits for the logger to finalize and writes <out>\\_selftest\\selftest_result.json.

It never injects input: raw-input counts will be ~0 unless someone is using the PC.
"""
import ctypes
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else r"D:\ow_capture\_selftest"
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 30
NOWIN = 0x08000000


def notepad_pids():
    r = subprocess.run(["tasklist", "/fi", "imagename eq notepad.exe", "/fo", "csv", "/nh"],
                       capture_output=True, text=True, creationflags=NOWIN, stdin=subprocess.DEVNULL)
    out = set()
    for line in r.stdout.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[1].isdigit():
            out.add(int(parts[1]))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    res = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "out": OUT}
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.SetThreadExecutionState(0x80000002)                   # ES_CONTINUOUS | ES_DISPLAY_REQUIRED
    u32.PostMessageW(0xFFFF, 0x0112, 0xF170, -1)              # SC_MONITORPOWER: on
    pre = notepad_pids()
    res["notepad_already_running"] = sorted(pre)
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    logger = subprocess.Popen([pyw, os.path.join(HERE, "logger.py"), "--target", "notepad.exe", "--out", OUT,
                               "--once", "--max-wait", "120", "--poll", "2", "--allow-no-input",
                               "--status-every", "5"], creationflags=NOWIN, stdin=subprocess.DEVNULL)
    time.sleep(4)
    subprocess.Popen(["notepad.exe"])
    t0 = time.time()
    mine = set()
    while time.time() - t0 < 10 and not mine:
        time.sleep(0.5)
        mine = notepad_pids() - pre
    res["notepad_pids_opened"] = sorted(mine)
    time.sleep(max(0, SECONDS - (time.time() - t0)))
    for pid in mine:
        subprocess.run(["taskkill", "/pid", str(pid)], capture_output=True, creationflags=NOWIN,
                       stdin=subprocess.DEVNULL)
    try:
        res["logger_rc"] = logger.wait(timeout=120)
    except subprocess.TimeoutExpired:
        logger.kill()
        res["logger_rc"] = "timeout"
    k32.SetThreadExecutionState(0x80000000)
    sessions = sorted(d for d in os.listdir(OUT) if os.path.isfile(os.path.join(OUT, d, "meta.json")))
    if sessions:
        with open(os.path.join(OUT, sessions[-1], "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        res["session"] = sessions[-1]
        res["checks"] = meta.get("checks")
        res["overhead"] = meta.get("overhead")
    res["ok"] = res.get("logger_rc") == 0 and bool((res.get("checks") or {}).get("ok"))
    with open(os.path.join(OUT, "selftest_result.json"), "w") as f:
        json.dump(res, f, indent=1)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

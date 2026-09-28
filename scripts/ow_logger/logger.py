"""ow_logger: passive Overwatch session recorder -> paired (video, action) data.

Runs forever as a supervised Scheduled Task in Carl's interactive session.
While a process named --target (default Overwatch.exe) is running it records:

  * video:  Desktop Duplication (ffmpeg ddagrab) -> 20 fps, ~854x480, h264_nvenc
            on the display GPU, low bitrate, Matroska (crash-safe, VFR with the
            true capture time of every frame).
  * input:  Windows Raw Input (RegisterRawInputDevices + RIDEV_INPUTSINK on a
            hidden message-only window): raw mouse deltas, buttons, wheel, and
            keyboard make/break with virtual-key + scan code. Timestamps are
            QueryPerformanceCounter microseconds since session start.
  * context: which process is foreground. When the target is NOT foreground
            only per-second event COUNTS are written, never keys or deltas.

Passive only: no hooks, no DLL injection, no overlay, no game memory reads, no
input injection. Nothing is recorded while the target is not running.

Output: <out>/<YYYY-MM-DD_HHMMSS>/{video_000.mkv, input.jsonl.gz, meta.json,
ffmpeg_000.log}. Heartbeat: <out>/status.json (every 30 s). Log: <out>/logger.log.
Kill switch without admin: create the file <out>/DISABLED.

Exit codes: 0 only for a clean --once run whose session passed its checks.
Any failure is logged, written to status.json as state "error", and exits
non-zero. Never exits 0 after failing.
"""
import argparse
import collections
import ctypes
import ctypes.wintypes as W
import datetime as dt
import gzip
import json
import logging
import logging.handlers
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

VERSION = "1.0.0"

# --------------------------------------------------------------------------- Win32

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)
LRESULT = ctypes.c_ssize_t

HWND_MESSAGE = W.HWND(-3)
WM_INPUT = 0x00FF
RIDEV_REMOVE = 0x00000001
RIDEV_INPUTSINK = 0x00000100
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RIDI_DEVICENAME = 0x20000007
PM_REMOVE = 0x0001
QS_ALLINPUT = 0x04FF
MWMO_INPUTAVAILABLE = 0x0004
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
SM_CXSCREEN, SM_CYSCREEN = 0, 1
CURSOR_SHOWING = 0x1
ERROR_ALREADY_EXISTS = 183


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", W.USHORT), ("usUsage", W.USHORT),
                ("dwFlags", W.DWORD), ("hwndTarget", W.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", W.DWORD), ("dwSize", W.DWORD),
                ("hDevice", W.HANDLE), ("wParam", W.WPARAM)]


class _BTN(ctypes.Structure):
    _fields_ = [("usButtonFlags", W.USHORT), ("usButtonData", W.USHORT)]


class _BTNU(ctypes.Union):
    _fields_ = [("ulButtons", W.ULONG), ("s", _BTN)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", W.USHORT), ("u", _BTNU), ("ulRawButtons", W.ULONG),
                ("lLastX", W.LONG), ("lLastY", W.LONG), ("ulExtraInformation", W.ULONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", W.USHORT), ("Flags", W.USHORT), ("Reserved", W.USHORT),
                ("VKey", W.USHORT), ("Message", W.UINT), ("ExtraInformation", W.ULONG)]


class RAWHID(ctypes.Structure):
    _fields_ = [("dwSizeHid", W.DWORD), ("dwCount", W.DWORD), ("bRawData", W.BYTE * 1)]


class _RIDATA(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD), ("hid", RAWHID)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("data", _RIDATA)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", W.UINT), ("style", W.UINT), ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", W.HINSTANCE), ("hIcon", W.HICON), ("hCursor", W.HANDLE),
                ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
                ("lpszClassName", W.LPCWSTR), ("hIconSm", W.HICON)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", W.DWORD),
                ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD),
                ("pcPriClassBase", W.LONG), ("dwFlags", W.DWORD), ("szExeFile", W.WCHAR * 260)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("flags", W.DWORD), ("hCursor", W.HANDLE),
                ("ptScreenPos", W.POINT)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", W.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", W.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", W.DWORD),
                ("SchedulingClass", W.DWORD)]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _proto(fn, res, *args):
    fn.restype = res
    fn.argtypes = list(args)
    return fn


_proto(u32.DefWindowProcW, LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
_proto(u32.RegisterClassExW, W.ATOM, ctypes.POINTER(WNDCLASSEXW))
_proto(u32.CreateWindowExW, W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int,
       ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID)
_proto(u32.RegisterRawInputDevices, W.BOOL, ctypes.POINTER(RAWINPUTDEVICE), W.UINT, W.UINT)
_proto(u32.GetRegisteredRawInputDevices, W.UINT, ctypes.POINTER(RAWINPUTDEVICE),
       ctypes.POINTER(W.UINT), W.UINT)
_proto(u32.GetRawInputData, W.UINT, W.HANDLE, W.UINT, W.LPVOID, ctypes.POINTER(W.UINT), W.UINT)
_proto(u32.GetRawInputDeviceInfoW, W.UINT, W.HANDLE, W.UINT, W.LPVOID, ctypes.POINTER(W.UINT))
_proto(u32.PeekMessageW, W.BOOL, ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT)
_proto(u32.DispatchMessageW, LRESULT, ctypes.POINTER(W.MSG))
_proto(u32.MsgWaitForMultipleObjectsEx, W.DWORD, W.DWORD, W.LPVOID, W.DWORD, W.DWORD, W.DWORD)
_proto(u32.GetForegroundWindow, W.HWND)
_proto(u32.GetWindowThreadProcessId, W.DWORD, W.HWND, ctypes.POINTER(W.DWORD))
_proto(u32.GetWindowRect, W.BOOL, W.HWND, ctypes.POINTER(W.RECT))
_proto(u32.GetCursorInfo, W.BOOL, ctypes.POINTER(CURSORINFO))
_proto(u32.GetClipCursor, W.BOOL, ctypes.POINTER(W.RECT))
_proto(u32.GetSystemMetrics, ctypes.c_int, ctypes.c_int)
_proto(u32.GetKeyboardLayoutNameW, W.BOOL, W.LPWSTR)
_proto(u32.SystemParametersInfoW, W.BOOL, W.UINT, W.UINT, W.LPVOID, W.UINT)
_proto(k32.GetModuleHandleW, W.HMODULE, W.LPCWSTR)
_proto(k32.CreateToolhelp32Snapshot, W.HANDLE, W.DWORD, W.DWORD)
_proto(k32.Process32FirstW, W.BOOL, W.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
_proto(k32.Process32NextW, W.BOOL, W.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
_proto(k32.CloseHandle, W.BOOL, W.HANDLE)
_proto(k32.OpenProcess, W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
_proto(k32.QueryFullProcessImageNameW, W.BOOL, W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD))
_proto(k32.GetProcessTimes, W.BOOL, W.HANDLE, ctypes.POINTER(W.FILETIME), ctypes.POINTER(W.FILETIME),
       ctypes.POINTER(W.FILETIME), ctypes.POINTER(W.FILETIME))
_proto(k32.GetCurrentProcess, W.HANDLE)
_proto(k32.GetCurrentThread, W.HANDLE)
_proto(k32.SetThreadPriority, W.BOOL, W.HANDLE, ctypes.c_int)
_proto(k32.CreateJobObjectW, W.HANDLE, W.LPVOID, W.LPCWSTR)
_proto(k32.SetInformationJobObject, W.BOOL, W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD)
_proto(k32.AssignProcessToJobObject, W.BOOL, W.HANDLE, W.HANDLE)
_proto(k32.GetSystemTimePreciseAsFileTime, None, ctypes.POINTER(W.FILETIME))
_proto(k32.QueryPerformanceCounter, W.BOOL, ctypes.POINTER(ctypes.c_int64))
_proto(k32.QueryPerformanceFrequency, W.BOOL, ctypes.POINTER(ctypes.c_int64))
_proto(k32.CreateMutexW, W.HANDLE, W.LPVOID, W.BOOL, W.LPCWSTR)
_proto(k32.GetDiskFreeSpaceExW, W.BOOL, W.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong),
       ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong))

HDR_SIZE = ctypes.sizeof(RAWINPUTHEADER)
RAW_SIZE = ctypes.sizeof(RAWINPUT)


def check_abi():
    """Struct layouts must match the 64-bit Windows SDK or every field is garbage."""
    want = {"RAWINPUTHEADER": (RAWINPUTHEADER, 24), "RAWMOUSE": (RAWMOUSE, 24),
            "RAWKEYBOARD": (RAWKEYBOARD, 16), "RAWINPUT": (RAWINPUT, 48),
            "RAWINPUTDEVICE": (RAWINPUTDEVICE, 16), "MSG": (W.MSG, 48)}
    bad = {k: (ctypes.sizeof(c), n) for k, (c, n) in want.items() if ctypes.sizeof(c) != n}
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        bad["pointer"] = (ctypes.sizeof(ctypes.c_void_p), 8)
    if RAWMOUSE.lLastX.offset != 12 or RAWKEYBOARD.VKey.offset != 6:
        bad["offsets"] = (RAWMOUSE.lLastX.offset, RAWKEYBOARD.VKey.offset)
    if bad:
        raise RuntimeError(f"struct ABI mismatch (got, want): {bad}")


def qpc():
    v = ctypes.c_int64()
    k32.QueryPerformanceCounter(ctypes.byref(v))
    return v.value


def qpc_freq():
    v = ctypes.c_int64()
    k32.QueryPerformanceFrequency(ctypes.byref(v))
    return v.value


def unix_ns_precise():
    ft = W.FILETIME()
    k32.GetSystemTimePreciseAsFileTime(ctypes.byref(ft))
    t = (ft.dwHighDateTime << 32) | ft.dwLowDateTime
    return (t - 116444736000000000) * 100


def ft_to_s(ft):
    return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7


def process_cpu_s(handle):
    c, e, kt, ut = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
    if not k32.GetProcessTimes(handle, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut)):
        return None
    return ft_to_s(kt) + ft_to_s(ut)


def list_processes():
    """[(pid, exe_basename)] via Toolhelp32 (no subprocess, ~1 ms)."""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    out = []
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(pe)
        ok = k32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            out.append((pe.th32ProcessID, pe.szExeFile))
            ok = k32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        k32.CloseHandle(snap)
    return out


def exe_of_pid(pid):
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = W.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value)
        return None
    finally:
        k32.CloseHandle(h)


def disk_free_gb(path):
    free = ctypes.c_ulonglong()
    if k32.GetDiskFreeSpaceExW(path, ctypes.byref(free), None, None):
        return free.value / 1e9
    return None


def iso_now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def make_kill_on_close_job():
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                       ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return job


log = logging.getLogger("ow_logger")

# --------------------------------------------------------------------------- video


class VideoSegment:
    """One ffmpeg process = one .mkv. Restarted as a new segment if it dies."""

    def __init__(self, sess, idx):
        self.sess = sess
        self.idx = idx
        self.file = f"video_{idx:03d}.mkv"
        self.path = os.path.join(sess.dir, self.file)
        self.logfile = os.path.join(sess.dir, f"ffmpeg_{idx:03d}.log")
        self.samples = collections.deque()   # (recv_us, frame, out_time_us)
        self.frames = 0
        self.last_frame_change_ns = None
        self.first_frame_us = None
        self.t0_candidates = []
        self.end_reason = None
        self.rc = None
        self.cpu_s = 0.0
        self.warned_no_frame = False
        a = sess.app.args
        sess.video_size = sess.app.video_size()   # re-read per segment: a mode change restarts ffmpeg
        w, h = self.size = sess.video_size
        self.start_unix = None
        # Wall-clock timestamps are taken when ffmpeg reads each frame, right after capture;
        # the input's "start:" line is the wall-clock time of video pts 0. Scaling happens in
        # the output graph so it does not delay that read.
        src = f"ddagrab=output_idx={a.output_idx}:framerate={a.fps}:draw_mouse=1"
        if a.mode == "native":     # GPU-only: D3D11 frames straight into NVENC, full resolution
            self.size = sess.video_size = (u32.GetSystemMetrics(SM_CXSCREEN), u32.GetSystemMetrics(SM_CYSCREEN))
            vf = []
            hw = []
        else:                      # hwdownload + CPU area downscale + upload back to D3D11 for NVENC
            vf = ["-vf", f"hwdownload,format=bgra,scale={w}:{h}:flags=area,setsar=1,format=nv12,hwupload"]
            hw = ["-init_hw_device", "d3d11va=dx:0", "-filter_hw_device", "dx"]
        self.cmd = [sess.app.ffmpeg, "-hide_banner", "-nostats", "-loglevel", "info",
                    "-progress", "pipe:1", "-stats_period", "0.5", "-filter_threads", "1"] + hw + [
                    "-use_wallclock_as_timestamps", "1", "-f", "lavfi", "-i", src] + vf + [
                    "-enc_time_base", "1:1000", "-c:v", "h264_nvenc", "-preset", "p4", "-tune", "ll", "-rc", "vbr",
                    "-cq", str(a.cq), "-b:v", a.bitrate, "-maxrate", a.maxrate,
                    "-bufsize", a.bufsize, "-g", str(2 * a.fps), "-bf", "0",
                    "-fps_mode", "passthrough", "-an",
                    # crash safety: close a Matroska cluster every 2 s and flush it to disk, so a
                    # killed logger / power cut loses at most ~2 s (without this a short or quiet
                    # recording was still 0 bytes on disk after 13 s)
                    "-cluster_time_limit", "2000", "-flush_packets", "1",
                    "-f", "matroska", "-y", self.path]
        self.start_us = sess.now_us()
        self.start_ns = time.perf_counter_ns()
        self._log = open(self.logfile, "ab")
        self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self._log,
                                     creationflags=CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS)
        if not k32.AssignProcessToJobObject(sess.app.job, int(self.proc._handle)):
            log.warning("could not put ffmpeg in kill-on-close job: %s", ctypes.WinError(ctypes.get_last_error()))
        self.reader = threading.Thread(target=self._read_progress, daemon=True)
        self.reader.start()
        log.info("segment %d started pid=%d cmd=%s", idx, self.proc.pid, " ".join(self.cmd))

    def _read_progress(self):
        cur = {}
        try:
            for raw in self.proc.stdout:
                if not cur:
                    cur["_recv"] = self.sess.now_us()
                k, _, v = raw.decode("ascii", "replace").strip().partition("=")
                cur[k] = v
                if k == "progress":
                    try:
                        f = int(cur.get("frame", "0"))
                        ot = cur.get("out_time_us", "N/A")
                        ot = int(ot) if ot.lstrip("-").isdigit() else None
                        self.samples.append((cur["_recv"], f, ot))
                    except ValueError:
                        pass
                    cur = {}
        except Exception:
            log.exception("progress reader for segment %d", self.idx)

    def drain(self):
        """Move progress samples into the input stream; returns them."""
        out = []
        while self.samples:
            recv, f, ot = self.samples.popleft()
            out.append((recv, f, ot))
            if f > self.frames:
                self.frames = f
                self.last_frame_change_ns = time.perf_counter_ns()
                if self.first_frame_us is None:
                    self.first_frame_us = recv
            if f > 0 and ot is not None:
                self.t0_candidates.append(recv - ot)
        return out

    def alive(self):
        return self.proc.poll() is None

    def cpu_now(self):
        v = process_cpu_s(int(self.proc._handle))
        if v is not None:
            self.cpu_s = v
        return self.cpu_s

    def stop(self, reason):
        if self.end_reason is None:
            self.end_reason = reason
        if self.alive():
            try:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                log.error("segment %d: ffmpeg ignored 'q' for 15 s, killing", self.idx)
                self.proc.kill()
                self.proc.wait(timeout=5)
                self.end_reason += "+killed"
        self.rc = self.proc.returncode
        self.cpu_now()
        self.reader.join(timeout=3)
        try:
            self._log.close()
        except OSError:
            pass

    def log_tail(self, n=6):
        try:
            with open(self.logfile, "rb") as f:
                f.seek(max(0, os.path.getsize(self.logfile) - 4000))
                lines = f.read().decode("utf-8", "replace").strip().splitlines()
            return " | ".join(lines[-n:])
        except OSError:
            return ""

    def t0_us(self):
        """Cross-check only: min over progress reports of (receive time - reported out_time).
        out_time is the END of the last muxed frame, so this sits about one frame before t0."""
        return min(self.t0_candidates) if self.t0_candidates else None

    def read_start_unix(self):
        """Wall-clock (s) of video pts 0, from ffmpeg's 'Input #0 ... start: X' line."""
        if self.start_unix is None:
            try:
                with open(self.logfile, "rb") as f:
                    m = re.search(rb"Duration: [^,]*, start: ([0-9]+\.[0-9]+)", f.read(20000))
                if m:
                    self.start_unix = float(m.group(1))
            except OSError:
                pass
        return self.start_unix

    def t0_us_wall(self):
        """Session-µs of video pts 0, via the wall-clock <-> QPC anchor nearest the segment start."""
        if self.read_start_unix() is None:
            return None
        ns = int(round(self.start_unix * 1e9))
        a = min(self.sess.anchors, key=lambda x: abs(x["unix_ns"] - ns))
        return a["t_us"] + (ns - a["unix_ns"]) // 1000

    def summary(self):
        return {"file": self.file, "ffmpeg_log": os.path.basename(self.logfile),
                "spawn_t_us": self.start_us, "first_report_t_us": self.first_frame_us,
                "size": list(self.size), "start_unix": self.start_unix,
                "t0_us": self.t0_us_wall(), "t0_us_progress_bound": self.t0_us(),
                "t0_samples": len(self.t0_candidates),
                "frames_reported": self.frames, "exit_code": self.rc,
                "end_reason": self.end_reason, "ffmpeg_cpu_s": round(self.cpu_s, 3),
                "cmd": self.cmd}


# --------------------------------------------------------------------------- session


class Session:
    def __init__(self, app, pids):
        self.app = app
        a = app.args
        base = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        d, n = os.path.join(a.out, base), 1
        while os.path.exists(d):
            n += 1
            d = os.path.join(a.out, f"{base}_{n}")
        os.makedirs(d)
        self.dir, self.id = d, os.path.basename(d)
        self.t0_ns = time.perf_counter_ns()
        self.t0_qpc = qpc()
        self.t0_unix_ns = unix_ns_precise()
        self.started_iso = iso_now()
        self.target_pids = set(pids)
        self.anchors = [self.anchor()]
        self.gz = gzip.open(os.path.join(d, "input.jsonl.gz"), "wb", compresslevel=6)
        self.buf = []
        self.ri = RAWINPUT()
        self.ri_size = W.UINT()
        self.devices = {}          # hDevice -> idx
        self.device_names = {}
        self.counts = collections.Counter()
        self.masked = collections.Counter()
        self.fg_hwnd = None
        self.fg_target = False
        self.fg_since_ns = None
        self.fg_target_s = 0.0
        self.fg_switches = 0
        self.cursor = None
        self.clip = None
        self.errors = []
        self.segments = []
        self.seg = None
        self.fail_streak = 0
        self.next_video_try_ns = 0
        self.video_size = app.video_size()
        self.cpu0 = process_cpu_s(k32.GetCurrentProcess())
        self.raw_errors = 0
        self.ended_iso = None
        self.end_reason = None
        self._last = {"fg": 0, "sec": 0, "flush": 0, "anchor": 0, "meta": 0}
        self.w_line('{"e":"header","schema":1,"logger":"%s","t_unit":"us since session start (QueryPerformanceCounter)",'
                    '"target":%s,"session":%s}\n' % (VERSION, json.dumps(a.target), json.dumps(self.id)))
        self.w_line('{"t":0,"e":"anchor","unix_ns":%d,"qpc":%d}\n' % (self.t0_unix_ns, self.t0_qpc))
        self.copy_game_settings()
        self.write_meta(complete=False)
        self.register_input(True)
        self.refresh_fg(force=True)
        self.start_video()
        log.info("session %s started (target pids %s, video %dx%d)", self.id, sorted(pids), *self.video_size)

    # ---- clocks / io
    def now_us(self):
        return (time.perf_counter_ns() - self.t0_ns) // 1000

    def anchor(self):
        return {"t_us": self.now_us(), "unix_ns": unix_ns_precise(), "qpc": qpc()}

    def w_line(self, s):
        self.buf.append(s)

    def flush_buf(self, sync=False):
        if self.buf:
            self.gz.write("".join(self.buf).encode("utf-8"))
            self.buf.clear()
        if sync:
            self.gz.flush()   # Z_SYNC_FLUSH: a crash loses at most a few seconds

    def error(self, msg):
        log.error("session %s: %s", self.id, msg)
        self.errors.append({"at": iso_now(), "msg": msg})
        self.app.set_error(msg)

    # ---- raw input
    def register_input(self, on):
        flags = RIDEV_INPUTSINK if on else RIDEV_REMOVE
        hwnd = self.app.hwnd if on else None
        devs = (RAWINPUTDEVICE * 2)(RAWINPUTDEVICE(1, 2, flags, hwnd), RAWINPUTDEVICE(1, 6, flags, hwnd))
        if not u32.RegisterRawInputDevices(devs, 2, ctypes.sizeof(RAWINPUTDEVICE)):
            err = ctypes.WinError(ctypes.get_last_error())
            if on:
                raise RuntimeError(f"RegisterRawInputDevices failed: {err}")
            log.warning("raw input unregister failed: %s", err)
            return
        if on:
            n = W.UINT(8)
            arr = (RAWINPUTDEVICE * 8)()
            got = u32.GetRegisteredRawInputDevices(arr, ctypes.byref(n), ctypes.sizeof(RAWINPUTDEVICE))
            regs = [(arr[i].usUsagePage, arr[i].usUsage, arr[i].dwFlags) for i in range(max(0, min(got, 8)))]
            self.registered = regs
            log.info("raw input registered: %s", regs)

    def dev_idx(self, h, typ):
        key = h or 0
        i = self.devices.get(key)
        if i is None:
            i = len(self.devices) + 1 if key else 0
            self.devices[key] = i
            name = "injected-or-unknown (hDevice=0)"
            if key:
                n = W.UINT(0)
                u32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, None, ctypes.byref(n))
                if n.value:
                    b = ctypes.create_unicode_buffer(n.value + 1)
                    if u32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, b, ctypes.byref(n)) not in (0, 0xFFFFFFFF):
                        name = b.value
            self.device_names[i] = {"type": "mouse" if typ == RIM_TYPEMOUSE else "keyboard", "name": name}
            self.w_line('{"t":%d,"e":"dev","d":%d,"type":"%s","name":%s}\n' % (
                self.now_us(), i, self.device_names[i]["type"], json.dumps(name)))
        return i

    def on_raw(self, hraw):
        self.ri_size.value = RAW_SIZE
        n = u32.GetRawInputData(hraw, RID_INPUT, ctypes.byref(self.ri), ctypes.byref(self.ri_size), HDR_SIZE)
        if n == 0 or n == 0xFFFFFFFF:
            self.raw_errors += 1
            return
        t = self.now_us()
        hdr = self.ri.header
        typ = hdr.dwType
        if typ == RIM_TYPEMOUSE:
            if not self.fg_target:
                self.masked["m"] += 1
                return
            m = self.ri.data.mouse
            d = self.dev_idx(hdr.hDevice, typ)
            s = '{"t":%d,"e":"m","d":%d,"dx":%d,"dy":%d' % (t, d, m.lLastX, m.lLastY)
            if m.usFlags:
                s += ',"mf":%d' % m.usFlags
            bf = m.u.s.usButtonFlags
            if bf:
                s += ',"b":%d' % bf
                if bf & 0x0C00:   # RI_MOUSE_WHEEL | RI_MOUSE_HWHEEL
                    wd = m.u.s.usButtonData
                    s += ',"w":%d' % (wd - 65536 if wd >= 32768 else wd)
            self.buf.append(s + "}\n")
            self.counts["m"] += 1
        elif typ == RIM_TYPEKEYBOARD:
            self.refresh_fg()     # exact check for every key: never log keys typed elsewhere
            if not self.fg_target:
                self.masked["k"] += 1
                return
            k = self.ri.data.keyboard
            d = self.dev_idx(hdr.hDevice, typ)
            self.buf.append('{"t":%d,"e":"k","d":%d,"vk":%d,"sc":%d,"fl":%d}\n' % (t, d, k.VKey, k.MakeCode, k.Flags))
            self.counts["k"] += 1

    # ---- foreground / cursor
    def refresh_fg(self, force=False):
        hwnd = u32.GetForegroundWindow()
        if hwnd == self.fg_hwnd and not force:
            return
        now_ns = time.perf_counter_ns()
        pid = W.DWORD(0)
        if hwnd:
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = exe_of_pid(pid.value) if pid.value else None
        is_t = bool(pid.value) and (pid.value in self.target_pids or
                                    (exe or "").lower() == self.app.target_l)
        if is_t:
            self.target_pids.add(pid.value)
        if self.fg_target and self.fg_since_ns is not None:
            self.fg_target_s += (now_ns - self.fg_since_ns) / 1e9
        self.fg_since_ns = now_ns if is_t else None
        self.fg_hwnd = hwnd
        if is_t != self.fg_target or force:
            self.fg_switches += 0 if force else 1
        self.fg_target = is_t
        s = '{"t":%d,"e":"fg","game":%d,"exe":%s' % (self.now_us(), int(is_t), json.dumps(exe))
        if is_t:
            r = W.RECT()
            if u32.GetWindowRect(hwnd, ctypes.byref(r)):
                s += ',"rect":[%d,%d,%d,%d]' % (r.left, r.top, r.right, r.bottom)
        self.w_line(s + "}\n")

    def sample_cursor(self):
        if not self.fg_target:
            return
        ci = CURSORINFO()
        ci.cbSize = ctypes.sizeof(ci)
        if u32.GetCursorInfo(ctypes.byref(ci)):
            c = (ci.ptScreenPos.x, ci.ptScreenPos.y, 1 if ci.flags & CURSOR_SHOWING else 0)
            if c != self.cursor:
                self.cursor = c
                self.w_line('{"t":%d,"e":"cur","x":%d,"y":%d,"vis":%d}\n' % ((self.now_us(),) + c))
        r = W.RECT()
        if u32.GetClipCursor(ctypes.byref(r)):
            cl = (r.left, r.top, r.right, r.bottom)
            if cl != self.clip:
                self.clip = cl
                self.w_line('{"t":%d,"e":"clip","r":[%d,%d,%d,%d]}\n' % ((self.now_us(),) + cl))

    # ---- video
    def start_video(self):
        try:
            self.seg = VideoSegment(self, len(self.segments))
            self.segments.append(self.seg)
            self.w_line('{"t":%d,"e":"seg","i":%d,"file":"%s","state":"start"}\n' % (
                self.seg.start_us, self.seg.idx, self.seg.file))
        except Exception as e:
            self.seg = None
            self.fail_streak += 1
            self.error(f"could not start ffmpeg: {e!r}")
            self.next_video_try_ns = time.perf_counter_ns() + int(min(60, 2 ** self.fail_streak) * 1e9)

    def emit_vp(self, seg):
        for recv, f, ot in seg.drain():
            self.w_line('{"t":%d,"e":"vp","s":%d,"f":%d,"ot":%s}\n' % (
                recv, seg.idx, f, "null" if ot is None else ot))

    def check_video(self, now_ns):
        seg = self.seg
        if seg is None:
            if now_ns >= self.next_video_try_ns:
                self.start_video()
            return
        self.emit_vp(seg)
        if seg.frames > 0 and seg.start_unix is None and seg.read_start_unix() is not None:
            self.w_line('{"t":%d,"e":"seg","i":%d,"state":"t0","start_unix":%.6f,"t0_us":%s}\n' % (
                self.now_us(), seg.idx, seg.start_unix, json.dumps(seg.t0_us_wall())))
        age_s = (now_ns - seg.start_ns) / 1e9
        if not seg.alive():
            seg.stop("ffmpeg exited")
            self.emit_vp(seg)
            self.w_line('{"t":%d,"e":"seg","i":%d,"state":"end","reason":"exited","rc":%s}\n' % (
                self.now_us(), seg.idx, json.dumps(seg.rc)))
            self._segment_failed(seg, f"ffmpeg exited rc={seg.rc} after {age_s:.0f}s: {seg.log_tail()}", age_s)
            return
        if seg.frames > 0 and seg.last_frame_change_ns and (now_ns - seg.last_frame_change_ns) > 15e9:
            seg.stop("stalled 15s")
            self.emit_vp(seg)
            self.w_line('{"t":%d,"e":"seg","i":%d,"state":"end","reason":"stalled"}\n' % (self.now_us(), seg.idx))
            self._segment_failed(seg, f"video stalled for 15 s at frame {seg.frames}: {seg.log_tail()}", age_s)
            return
        if seg.frames == 0 and age_s > 60 and not seg.warned_no_frame:
            seg.warned_no_frame = True
            log.warning("segment %d: no frame after 60 s (display off or static screen?) - still waiting", seg.idx)
        if seg.frames > 0 and age_s > 60 and self.fail_streak:
            self.fail_streak = 0
            self.app.clear_error("video recovered")

    def _segment_failed(self, seg, msg, age_s):
        self.seg = None
        self.fail_streak = self.fail_streak + 1 if age_s < 60 else 1
        backoff = min(60, 2 ** self.fail_streak)
        self.next_video_try_ns = time.perf_counter_ns() + int(backoff * 1e9)
        text = f"segment {seg.idx}: {msg} (retry in {backoff}s, streak {self.fail_streak})"
        if self.fail_streak >= 3:
            self.error(text)
        else:
            log.warning("session %s: %s", self.id, text)
            self.errors.append({"at": iso_now(), "msg": text, "level": "warning"})

    # ---- periodic
    def tick(self, now_ns):
        L = self._last
        if now_ns - L["fg"] >= 50e6:
            L["fg"] = now_ns
            self.refresh_fg()
            self.sample_cursor()
        if now_ns - L["sec"] >= 1e9:
            L["sec"] = now_ns
            if self.masked:
                self.w_line('{"t":%d,"e":"masked","k":%d,"m":%d}\n' % (
                    self.now_us(), self.masked["k"], self.masked["m"]))
                self.counts["masked_k"] += self.masked["k"]
                self.counts["masked_m"] += self.masked["m"]
                self.masked.clear()
            self.check_video(now_ns)
            self.flush_buf(sync=(now_ns - L["flush"] >= 5e9))
            if now_ns - L["flush"] >= 5e9:
                L["flush"] = now_ns
        if now_ns - L["anchor"] >= 60e9:
            L["anchor"] = now_ns
            a = self.anchor()
            self.anchors.append(a)
            self.w_line('{"t":%d,"e":"anchor","unix_ns":%d,"qpc":%d}\n' % (a["t_us"], a["unix_ns"], a["qpc"]))
            self.write_meta(complete=False)

    # ---- metadata
    def copy_game_settings(self):
        self.game_settings = None
        if self.app.target_l != "overwatch.exe":
            return
        try:
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
            src = os.path.join(buf.value, "Overwatch", "Settings", "Settings_v0.ini")
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(self.dir, "Settings_v0.ini"))
                self.game_settings = "Settings_v0.ini"
        except Exception as e:
            log.warning("could not copy Overwatch settings: %r", e)

    def overhead(self):
        wall = (time.perf_counter_ns() - self.t0_ns) / 1e9
        ncpu = os.cpu_count() or 1
        me = (process_cpu_s(k32.GetCurrentProcess()) or 0) - (self.cpu0 or 0)
        ff = sum(s.cpu_now() if s.alive() else s.cpu_s for s in self.segments)
        if wall <= 0:
            return {}
        return {"wall_s": round(wall, 1), "logical_cpus": ncpu,
                "logger_cpu_s": round(me, 2), "ffmpeg_cpu_s": round(ff, 2),
                "logger_pct_of_one_core": round(100 * me / wall, 2),
                "ffmpeg_pct_of_one_core": round(100 * ff / wall, 2),
                "total_pct_of_machine": round(100 * (me + ff) / wall / ncpu, 3)}

    def write_meta(self, complete, probes=None, checks=None):
        a = self.app.args
        meta = {
            "schema": 1, "logger_version": VERSION, "session": self.id, "target": a.target,
            "complete": complete, "started": self.started_iso, "ended": self.ended_iso,
            "end_reason": self.end_reason,
            "duration_s": round((time.perf_counter_ns() - self.t0_ns) / 1e9, 3),
            "clock": {
                "t_unit": "microseconds since session start; QueryPerformanceCounter (time.perf_counter_ns)",
                "qpc_freq": self.app.qpc_freq, "session_start_qpc": self.t0_qpc,
                "session_start_unix_ns": self.t0_unix_ns, "anchors": self.anchors,
                "video_alignment": ("frame with pts p (seconds, read from the mkv; VFR, ms precision) was "
                                    "captured at session time segment.t0_us + p*1e6 us. ffmpeg stamps each frame "
                                    "with the wall clock as it reads it (right after capture); segment.start_unix "
                                    "is the wall clock of pts 0, converted to session time with the nearest "
                                    "anchor. t0_us_progress_bound (from the 'vp' progress events) is a cross-check "
                                    "that should sit ~1 frame before t0_us."),
            },
            "video": {"fps": a.fps, "size": list(self.video_size), "codec": "h264_nvenc",
                      "mode": a.mode,
                      "pipeline": ("ddagrab(DXGI desktop duplication, output %d) -> " % a.output_idx) + (
                          "h264_nvenc (D3D11, full resolution)" if a.mode == "native" else
                          "hwdownload -> swscale area -> nv12 -> hwupload(D3D11 adapter 0) -> h264_nvenc"),
                      "rate_control": {"cq": a.cq, "b:v": a.bitrate, "maxrate": a.maxrate},
                      "timestamps": "VFR, true capture time per frame (ms, Matroska)",
                      "segments": [s.summary() for s in self.segments]},
            "input": {"file": "input.jsonl.gz",
                      "api": "Raw Input, RIDEV_INPUTSINK on a message-only window, per-message GetRawInputData",
                      "counts": dict(self.counts), "raw_read_errors": self.raw_errors,
                      "devices": self.device_names,
                      "registered": getattr(self, "registered", None),
                      "masking": "when the target is not foreground only per-second counts ('masked') are written"},
            "foreground": {"target_foreground_s": round(self.fg_target_s + (
                (time.perf_counter_ns() - self.fg_since_ns) / 1e9 if self.fg_since_ns else 0), 2),
                "switches": self.fg_switches},
            "display": self.app.display_info(),
            "system": self.app.system_info(),
            "game_settings_copy": self.game_settings,
            "overhead": self.overhead(),
            "probes": probes, "checks": checks, "errors": self.errors,
        }
        tmp = os.path.join(self.dir, "meta.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)
        os.replace(tmp, os.path.join(self.dir, "meta.json"))
        return meta

    def probe_segments(self):
        out = {}
        for s in self.segments:
            if not os.path.exists(s.path):
                out[s.file] = {"error": "missing"}
                continue
            try:
                r = subprocess.run([self.app.ffprobe, "-v", "error", "-select_streams", "v:0",
                                    "-count_packets", "-show_entries",
                                    "stream=codec_name,width,height,avg_frame_rate,nb_read_packets:format=duration,size",
                                    "-of", "json", s.path], capture_output=True, text=True, timeout=120,
                                   stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                j = json.loads(r.stdout or "{}")
                st = (j.get("streams") or [{}])[0]
                fm = j.get("format", {})
                out[s.file] = {"codec": st.get("codec_name"), "size": [st.get("width"), st.get("height")],
                               "packets": int(st.get("nb_read_packets") or 0),
                               "avg_frame_rate": st.get("avg_frame_rate"),
                               "duration_s": float(fm.get("duration") or 0), "bytes": int(fm.get("size") or 0),
                               "ffprobe_rc": r.returncode, "ffprobe_err": r.stderr.strip()[-300:] or None}
            except Exception as e:
                out[s.file] = {"error": repr(e)}
        return out

    def close(self, reason):
        self.end_reason = reason
        if self.seg is not None:
            self.seg.stop(reason)
            self.emit_vp(self.seg)
            self.w_line('{"t":%d,"e":"seg","i":%d,"state":"end","reason":%s,"rc":%s}\n' % (
                self.now_us(), self.seg.idx, json.dumps(reason), json.dumps(self.seg.rc)))
            self.seg = None
        self.register_input(False)
        if self.fg_target and self.fg_since_ns is not None:
            self.fg_target_s += (time.perf_counter_ns() - self.fg_since_ns) / 1e9
            self.fg_since_ns = None
        if self.masked:
            self.counts["masked_k"] += self.masked["k"]
            self.counts["masked_m"] += self.masked["m"]
        self.anchors.append(self.anchor())
        a = self.anchors[-1]
        self.w_line('{"t":%d,"e":"anchor","unix_ns":%d,"qpc":%d}\n' % (a["t_us"], a["unix_ns"], a["qpc"]))
        self.w_line('{"t":%d,"e":"end","reason":%s}\n' % (self.now_us(), json.dumps(reason)))
        self.flush_buf()
        self.gz.close()
        self.ended_iso = iso_now()
        probes = self.probe_segments()
        dur = (time.perf_counter_ns() - self.t0_ns) / 1e9
        frames = sum(p.get("packets", 0) for p in probes.values())
        vdur = sum(p.get("duration_s", 0) for p in probes.values())
        raw = self.counts["m"] + self.counts["k"] + self.counts["masked_m"] + self.counts["masked_k"]
        checks = {"video_frames": frames, "video_seconds": round(vdur, 2), "session_seconds": round(dur, 2),
                  "raw_events": raw, "raw_read_errors": self.raw_errors}
        problems = []
        if dur >= 20 and frames == 0:
            problems.append("no video frames recorded")
        elif dur >= 60 and vdur < 0.5 * dur:
            problems.append(f"video covers only {vdur:.0f}s of a {dur:.0f}s session")
        fgs = self.fg_target_s
        if fgs >= 120 and raw == 0 and not self.app.args.allow_no_input:
            problems.append(f"no raw input received in {fgs:.0f}s with the target foreground")
        if self.raw_errors:
            problems.append(f"{self.raw_errors} GetRawInputData failures")
        checks["ok"] = not problems
        checks["problems"] = problems
        meta = self.write_meta(complete=True, probes=probes, checks=checks)
        for p in problems:
            self.error(f"check failed: {p}")
        log.info("session %s closed (%s): %.0fs, %d frames, %d mouse, %d key, masked k/m %d/%d, overhead %s",
                 self.id, reason, dur, frames, self.counts["m"], self.counts["k"],
                 self.counts["masked_k"], self.counts["masked_m"], meta["overhead"])
        return checks["ok"], meta


# --------------------------------------------------------------------------- app


class App:
    def __init__(self, args):
        self.args = args
        self.target_l = args.target.lower()
        self.qpc_freq = qpc_freq()
        self.status_path = os.path.join(args.out, "status.json")
        self.state = "starting"
        self.error_msg = None
        self.last_error = None
        self.session = None
        self.last_session = None
        self.started_iso = iso_now()
        self.sessions_total, self.bytes_total, self.hours_total = self.scan_existing()
        self._sysinfo = None

    # ---- setup
    def setup(self):
        check_abi()
        try:
            u32.SetProcessDpiAwarenessContext.restype = W.BOOL
            u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # per-monitor v2: physical pixels
        except Exception:
            log.warning("could not set DPI awareness")
        name = "Local\\ow_logger_" + "".join(c if c.isalnum() else "_" for c in os.path.abspath(self.args.out).lower())
        ctypes.set_last_error(0)
        self.mutex = k32.CreateMutexW(None, False, name)
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            raise SystemExit(3)   # another instance owns this output dir; the task's IgnoreNew makes this rare
        self.ffmpeg = self.find_tool("ffmpeg")
        self.ffprobe = self.find_tool("ffprobe")
        self.job = make_kill_on_close_job()
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(wc)
        wc.lpfnWndProc = ctypes.cast(u32.DefWindowProcW, ctypes.c_void_p).value
        wc.hInstance = k32.GetModuleHandleW(None)
        wc.lpszClassName = "ow_logger_sink"
        if not u32.RegisterClassExW(ctypes.byref(wc)):
            raise RuntimeError(f"RegisterClassExW: {ctypes.WinError(ctypes.get_last_error())}")
        self._wc = wc
        self.hwnd = u32.CreateWindowExW(0, "ow_logger_sink", "ow_logger", 0, 0, 0, 0, 0,
                                        HWND_MESSAGE, None, wc.hInstance, None)
        if not self.hwnd:
            raise RuntimeError(f"CreateWindowExW: {ctypes.WinError(ctypes.get_last_error())}")
        k32.SetThreadPriority(k32.GetCurrentThread(), 1)   # ABOVE_NORMAL: accurate input timestamps; idles otherwise

    def find_tool(self, name):
        p = shutil.which(name)
        if not p:
            cand = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links", name + ".exe")
            p = cand if os.path.exists(cand) else None
        if not p:
            raise RuntimeError(f"{name} not found on PATH or in WinGet Links")
        return p

    def scan_existing(self):
        n, b, h = 0, 0, 0.0
        try:
            for e in os.scandir(self.args.out):
                if e.is_dir() and not e.name.startswith("_") and os.path.exists(os.path.join(e.path, "meta.json")):
                    n += 1
                    for f in os.scandir(e.path):
                        if f.is_file():
                            b += f.stat().st_size
                    try:
                        with open(os.path.join(e.path, "meta.json"), encoding="utf-8") as f:
                            h += float(json.load(f).get("duration_s") or 0) / 3600
                    except (OSError, ValueError):
                        pass
        except FileNotFoundError:
            pass
        return n, b, h

    def video_size(self):
        W_, H_ = u32.GetSystemMetrics(SM_CXSCREEN), u32.GetSystemMetrics(SM_CYSCREEN)
        h = self.args.height
        if W_ <= 0 or H_ <= 0:
            return (854, 480)
        w = int(round(h * W_ / H_ / 2.0)) * 2
        return (w, h)

    def display_info(self):
        info = {"primary_px": [u32.GetSystemMetrics(SM_CXSCREEN), u32.GetSystemMetrics(SM_CYSCREEN)]}
        try:
            b = ctypes.create_unicode_buffer(16)
            if u32.GetKeyboardLayoutNameW(b):
                info["keyboard_layout"] = b.value
            speed = ctypes.c_int()
            if u32.SystemParametersInfoW(0x0070, 0, ctypes.byref(speed), 0):   # SPI_GETMOUSESPEED
                info["mouse_speed_1_20"] = speed.value
            acc = (ctypes.c_int * 3)()
            if u32.SystemParametersInfoW(0x0003, 0, acc, 0):                    # SPI_GETMOUSE
                info["enhance_pointer_precision"] = bool(acc[2])
        except Exception:
            pass
        return info

    def system_info(self):
        if self._sysinfo is None:
            ver = None
            try:
                r = subprocess.run([self.ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True,
                                   timeout=20, stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                ver = (r.stdout.splitlines() or [None])[0]
            except Exception as e:
                ver = repr(e)
            self._sysinfo = {"host": platform.node(), "windows": platform.platform(),
                             "python": sys.version.split()[0], "ffmpeg": ver, "ffmpeg_path": self.ffmpeg}
        return self._sysinfo

    # ---- status
    def set_error(self, msg):
        self.error_msg = msg
        self.last_error = {"at": iso_now(), "msg": msg}
        self.write_status()

    def clear_error(self, why):
        if self.error_msg:
            log.info("error cleared: %s", why)
        self.error_msg = None

    def write_status(self):
        s = self.session
        st = {"state": "error" if self.error_msg else self.state,
              "error": self.error_msg, "last_error": self.last_error,
              "updated": iso_now(), "updated_unix": round(time.time(), 1),
              "heartbeat_every_s": self.args.status_every, "pid": os.getpid(),
              "logger_version": VERSION, "target": self.args.target, "out": self.args.out,
              "running_since": self.started_iso,
              "sessions_total": self.sessions_total, "hours_total": round(self.hours_total, 2),
              "bytes_total": self.bytes_total, "disk_free_gb": round(disk_free_gb(self.args.out) or -1, 1),
              "current_session": None, "last_session": self.last_session}
        if s is not None:
            cur_bytes = 0
            for f in os.scandir(s.dir):
                if f.is_file():
                    cur_bytes += f.stat().st_size
            st["current_session"] = {"id": s.id, "started": s.started_iso,
                                     "seconds": round((time.perf_counter_ns() - s.t0_ns) / 1e9),
                                     "video_frames": sum(x.frames for x in s.segments),
                                     "segments": len(s.segments), "mouse": s.counts["m"], "keys": s.counts["k"],
                                     "target_foreground": s.fg_target, "bytes": cur_bytes,
                                     "overhead": s.overhead()}
        tmp = self.status_path + ".tmp"
        for _ in range(5):
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(st, f, indent=1)
                os.replace(tmp, self.status_path)
                return
            except OSError:
                time.sleep(0.05)
        log.error("could not write %s", self.status_path)

    # ---- main loop
    def target_pids(self):
        return {pid for pid, exe in list_processes() if exe.lower() == self.target_l}

    def start_session(self, pids):
        free = disk_free_gb(self.args.out)
        if free is not None and free < self.args.min_free_gb:
            self.set_error(f"not recording: only {free:.0f} GB free on {self.args.out}")
            return
        self.state = "recording"
        self.session = Session(self, pids)
        self.write_status()

    def end_session(self, reason):
        s = self.session
        self.session = None
        ok, meta = s.close(reason)
        self.sessions_total += 1
        self.hours_total += meta["duration_s"] / 3600
        size = sum(f.stat().st_size for f in os.scandir(s.dir) if f.is_file())
        self.bytes_total += size
        self.last_session = {"id": s.id, "ended": s.ended_iso, "seconds": round(meta["duration_s"]),
                             "ok": ok, "problems": meta["checks"]["problems"], "bytes": size,
                             "video_frames": meta["checks"]["video_frames"],
                             "mouse": s.counts["m"], "keys": s.counts["k"], "overhead": meta["overhead"]}
        if ok and self.error_msg:
            self.clear_error("session completed cleanly")
        self.state = "idle"
        self.write_status()
        return ok

    def run(self):
        a = self.args
        self.setup()
        log.info("ow_logger %s up: target=%s out=%s ffmpeg=%s pid=%d", VERSION, a.target, a.out, self.ffmpeg, os.getpid())
        self.state = "idle"
        self.write_status()
        msg = W.MSG()
        next_poll = next_status = 0
        started_ns = time.perf_counter_ns()
        once_ok = None
        while True:
            timeout = 50 if self.session else 1000
            u32.MsgWaitForMultipleObjectsEx(0, None, timeout, QS_ALLINPUT, MWMO_INPUTAVAILABLE)
            s = self.session
            while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_INPUT and s is not None:
                    s.on_raw(msg.lParam)
                u32.DispatchMessageW(ctypes.byref(msg))   # DefWindowProc frees the raw input handle
            now = time.perf_counter_ns()
            if s is not None:
                s.tick(now)
            if now >= next_poll:
                next_poll = now + int(a.poll * 1e9)
                disabled = os.path.exists(os.path.join(a.out, "DISABLED"))
                pids = set() if disabled else self.target_pids()
                if self.session is None:
                    self.state = "disabled" if disabled else "idle"
                    if pids:
                        self.start_session(pids)
                elif not pids or (a.max_session_s and (now - self.session.t0_ns) / 1e9 > a.max_session_s):
                    why = "disabled" if disabled else ("target exited" if not pids else "test time limit")
                    ok = self.end_session(why)
                    if a.once:
                        once_ok = ok
                        break
                else:
                    self.session.target_pids |= pids
                if a.once and self.session is None and a.max_wait and (now - started_ns) / 1e9 > a.max_wait:
                    self.set_error(f"--once: target {a.target} never appeared within {a.max_wait}s")
                    return 4
            if now >= next_status:
                next_status = now + int(a.status_every * 1e9)
                self.write_status()
        return 0 if once_ok else 2


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", default="Overwatch.exe", help="process image name that triggers recording")
    p.add_argument("--out", default=r"D:\ow_capture")
    p.add_argument("--fps", type=int, default=20)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--output-idx", type=int, default=0, help="DXGI output (monitor) index for ddagrab")
    p.add_argument("--mode", choices=["scaled", "native"], default="scaled",
                   help="scaled: ~854x480 via CPU downscale (~25%% of one core); native: GPU-only full-res")
    p.add_argument("--cq", type=int, default=30)
    p.add_argument("--bitrate", default="1000k")
    p.add_argument("--maxrate", default="1500k")
    p.add_argument("--bufsize", default="3000k")
    p.add_argument("--poll", type=float, default=5.0, help="seconds between process checks")
    p.add_argument("--status-every", type=float, default=30.0)
    p.add_argument("--min-free-gb", type=float, default=50.0)
    p.add_argument("--once", action="store_true", help="exit after the first session (tests)")
    p.add_argument("--max-wait", type=float, default=0, help="with --once: give up if target never appears")
    p.add_argument("--allow-no-input", action="store_true", help="tests: do not fail a session with zero input")
    p.add_argument("--max-session-s", type=float, default=0, help="tests: end a session after this many seconds")
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(os.path.join(args.out, "logger.log"), maxBytes=5_000_000,
                                             backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s pid=%(process)d %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    app = App(args)
    rc = 1
    try:
        rc = app.run()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
        if rc == 3:
            log.info("another ow_logger instance already owns %s; exiting 3", args.out)
            return rc
        log.error("exiting with code %s", rc)
    except BaseException as e:
        log.error("FATAL: %r\n%s", e, traceback.format_exc())
        try:
            if app.session is not None:
                app.session.close("logger crashed")
        except Exception:
            log.error("could not close session cleanly:\n%s", traceback.format_exc())
        app.set_error(f"logger crashed: {e!r}")
        rc = 1
    if rc != 0 and not app.error_msg and rc != 3:
        app.set_error(f"logger exited with code {rc}")
    log.info("exit %s", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())

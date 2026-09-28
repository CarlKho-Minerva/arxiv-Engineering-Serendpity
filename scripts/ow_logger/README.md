# ow_logger: Overwatch (video, action) recorder

Passive recorder on the gaming PC (`ssh PC`). Every time a process named `Overwatch.exe`
runs, it records a small screen video and Carl's keyboard and mouse input on one clock, so
the sessions become paired (video, action) data like OpenAI VPT or DIAMOND used. Carl
does nothing. Nothing is recorded while the game is not running.

## Turn it off (one command, from the Mac)

```
ssh PC "schtasks /change /tn OWCaptureLogger /disable & schtasks /end /tn OWCaptureLogger"
```

Turn it back on: `ssh PC "schtasks /change /tn OWCaptureLogger /enable"` (it starts within a minute).
Pause it without admin rights: create the file `D:\ow_capture\DISABLED`. The logger stays up,
records nothing, and reports `"state": "disabled"`. Delete the file to resume.
Remove it completely: `powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall` on the PC.
Recordings are kept in every case.

## What it records

| Stream | How | Notes |
|---|---|---|
| Screen video | ffmpeg `ddagrab` (DXGI Desktop Duplication) of monitor 0, `hwdownload`, CPU area downscale to 854x480, `hwupload` back to D3D11, `h264_nvenc` on the display GPU | 20 fps, VFR with the true capture time of every frame (ms), CQ 30, 1.0 Mbps target / 1.5 Mbps cap, keyframe every 2 s, no audio. Matroska, a cluster flushed every 2 s |
| Mouse | Windows Raw Input, `RIDEV_INPUTSINK` on a hidden message-only window | raw deltas `dx`/`dy` (what an FPS uses while the cursor is locked), button flags, wheel |
| Keyboard | same | virtual-key code, scan code, make/break flags |
| Foreground | `GetForegroundWindow` on every key and every 50 ms | exe name only, never window titles |
| Cursor | `GetCursorInfo`, `GetClipCursor`, 20 Hz, written on change | position, visible or hidden (menu vs aiming), clip rect |
| Game settings | copy of `Documents\Overwatch\Settings\Settings_v0.ini` at session start | in-game sensitivity and keybinds |

**Masking.** When Overwatch is not the foreground window (alt-tab to Discord, a browser), keys
and mouse movement are **not** written. Only one line per second with the event counts is written.
The foreground check runs for every single key event, so nothing typed into another app is recorded.
Text typed into Overwatch's own chat **is** recorded, because Overwatch is foreground then.

**Passive only.** No hooks (`SetWindowsHookEx`), no DLL injection, no overlay, no reads of game
memory, no input injection. The same APIs are used by OBS display capture and by mouse/overlay
utilities. Reading the settings `.ini` is a plain file copy.

## Where it goes

```
D:\ow_capture\
  status.json                    heartbeat, rewritten every 30 s
  logger.log                     rotating log (5 MB x 4)
  DISABLED                       (optional) pause switch
  2026-09-28_203015\             one directory per game session (local start time)
    video_000.mkv                video segment 0 (a new segment starts if ffmpeg has to restart)
    ffmpeg_000.log               ffmpeg's own log for that segment
    input.jsonl.gz               every event, one JSON object per line
    meta.json                    start/end, clocks and anchors, segment list, checks, overhead, versions
    Settings_v0.ini              Overwatch settings at session start
  _selftest\  _selftest_fg\  _selftest_crash\  _dev\      tests and experiments (ignored by the counters)
```

Code: `%LOCALAPPDATA%\ow_logger\logger.py` (copied there by `install.ps1`).
Keystroke data stays on the PC's D: drive. Do not copy sessions into `~/Downloads/carl`
(iCloud-mirrored).

## input.jsonl.gz format

`t` is microseconds since session start, from `QueryPerformanceCounter`.

| `e` | fields | meaning |
|---|---|---|
| `header` | schema, logger, target, session | first line |
| `anchor` | `unix_ns`, `qpc` | wall clock (GetSystemTimePreciseAsFileTime) paired with `t`; at start, every 60 s, at end |
| `m` | `d` device, `dx`, `dy`, optional `b` button flags, `w` wheel delta, `mf` mouse flags | one raw mouse report (`b`: 1/2 L down/up, 4/8 R, 16/32 M, 64/128 X1, 256/512 X2, 0x400 wheel, 0x800 hwheel) |
| `k` | `d`, `vk`, `sc`, `fl` | one raw key report (`fl` bit 0 = key up, bit 1 = E0 prefix, bit 2 = E1) |
| `fg` | `game` 0/1, `exe`, `rect` when game | foreground changed |
| `cur` / `clip` | `x`, `y`, `vis` / `r` | cursor moved or changed visibility / clip rect changed |
| `masked` | `k`, `m` | counts in the last second while the game was not foreground |
| `dev` | `d`, `type`, `name` | first use of an input device (`d` 0 = injected input, e.g. Sunshine/Moonlight) |
| `seg` | `i`, `state` start/t0/end, `start_unix`, `t0_us` | video segment lifecycle and its time anchor |
| `vp` | `s`, `f` frames, `ot` out_time_us | ffmpeg progress reports (a cross-check on the video clock) |
| `end` | `reason` | last line of a cleanly closed session |

A key held while alt-tabbing away will have no key-up in the stream: release all keys at every `fg` with `game: 0`.

## Aligning actions to frames

ffmpeg stamps each frame with the wall clock at the moment it reads it (right after capture), and
`-fps_mode passthrough` keeps those times, so the mkv is VFR at a nominal 20 fps. For segment `s`
in `meta.json`:

```
capture time of the frame with pts p (seconds)  =  s.t0_us + p * 1e6     (session microseconds)
```

`s.t0_us` comes from ffmpeg's `start:` (wall clock of pts 0) mapped through the nearest QPC/wall-clock
anchor. Read per-frame pts with `ffprobe -show_entries packet=pts_time` or your decoder. Frame
intervals are not exactly 50 ms (ffmpeg's pacing sleeps have 15.6 ms granularity: most are 47 or
62 ms, mean 50.06 ms), so use the pts, not the frame index. For a VPT-style label per frame, take
all input events with `t` in `[t_frame, t_next_frame)`.

`t0_us_progress_bound` sits about one frame plus encoder latency after `t0_us` in tests (60-80 ms);
it is only a sanity check.

## Health and errors

`status.json`: `state` is `idle`, `recording`, `disabled` or `error`, with `error`/`last_error`
messages, `updated_unix`, `sessions_total`, `hours_total`, `bytes_total`, `disk_free_gb`,
`current_session` (frames, events, overhead) and `last_session` (checks passed or the problems).
**If `updated_unix` is more than ~90 s old the logger is dead** (a killed process cannot write its
own obituary; the task restarts it within 60 s).

Errors are loud: they go to `logger.log`, to `status.json` as `state: "error"`, and to `meta.json`.
The logger never exits 0 after failing. At session end it checks itself: zero video frames, video
covering less than half the session, or zero raw input after 120 s with the game foreground all
mark the session failed and set the error state. An ffmpeg crash or a 15 s video stall restarts
ffmpeg into a new segment with backoff; three quick failures in a row set the error state. It
refuses to record with less than 50 GB free on D:.

## How it runs

Scheduled Task `OWCaptureLogger`, user Carlk, "Run only when user is logged on" (Desktop
Duplication and Raw Input need his desktop session), highest privileges, priority 5 (normal).
Supervision: a TimeTrigger with a past StartBoundary repeating every minute forever plus
`MultipleInstancesPolicy=IgnoreNew` (and a LogonTrigger). Killed on purpose on 2026-09-27: back in
19 s, exactly one instance. ffmpeg runs below normal priority inside a kill-on-close job object, so
it dies with the logger. Idle, the logger polls for `Overwatch.exe` every 5 s via Toolhelp32.

Install or update: copy this folder to the PC and run
`powershell -ExecutionPolicy Bypass -File install.ps1` (add `-SelfTest` to rerun the Notepad
end-to-end test first). The installer stops the old instance before registering, because
re-registering alone leaves the old process running old code.

`--mode native` skips the CPU downscale and encodes D3D11 frames at full resolution on NVENC
(2.8% of one core measured instead of ~25%, about 3x the disk). Switch to it if the downscale
ever shows up as a hitch.

## Measured on 2026-09-27 (Notepad and Windows Terminal as stand-in targets)

| | |
|---|---|
| Video | 794 frames / 39.75 s, 609 / 30.5 s, 515 / 25.8 s (19.95-20.0 fps), h264 854x480, playable; 280 frames readable after a hard kill at 15 s |
| ffmpeg CPU while recording | 11-31% of one logical core across 5 runs (0.36-0.99% of the 32-thread CPU) |
| logger CPU | ~1-2% of one core while recording, 0.24% idle; 26 MB RAM |
| GPU0 (game card) | 1 NVENC session at 20 fps, encoder utilisation reads 0%, overall 3-9% with the woken desktop; VRAM 666 MiB vs 602 MiB before (display asleep). Nothing on the eGPU |
| Disk | gameplay test clips encode at 0.64-1.0 Mbps; cap 1.5 Mbps, so **~0.3-0.7 GB/hour** video, plus roughly 5-30 MB/hour input. 100 hours is about 30-70 GB |

What the stand-in test could not prove: raw input **delivery**. Nobody used the PC during the
test and nothing was injected, so registration was verified (`GetRegisteredRawInputDevices`
shows mouse and keyboard with `RIDEV_INPUTSINK`) but zero events arrived. The first real session
proves it; if the game is foreground for 2 minutes with zero events, that session fails its check
and `status.json` goes to `error`.

## Known risks

- **Foreground stealers.** During the tests, console windows from the existing tasks
  `eGPU-PowerCap` (runs `nvidia-smi.exe`, every 10 min) and `Takeout-Ensure` (runs `wsl.exe`,
  every 5 min) took the foreground in Carl's session. Mid-match that pulls focus out of Overwatch,
  and here it masks input for a moment. Not changed by this install.
- **Desktop Duplication and the game.** DDA is what OBS display capture uses; it can cost a little
  latency when a game is in independent-flip fullscreen, and a display-mode change or the secure
  desktop (UAC, Ctrl+Alt+Del, lock) makes ffmpeg exit. The logger restarts it as a new segment.
- **Background raw input rate.** Windows 11 may coalesce high-polling-rate mouse input delivered to
  background listeners. Totals are what matter at 20 fps, but check `m` event density in the first
  session.
- **Chat.** Overwatch text chat is keyboard input to the foreground game and is recorded.
- **Display asleep.** DDA delivers no frames while the monitor sleeps; the logger waits instead of
  failing. The Notepad self-test wakes the display for that reason.

#!/usr/bin/env python3
"""RQ6 exploratory pass: monthly exploration-rate proxies from the normalized
message stream. Reads ONLY metadata fields (t_start, actor, source,
meta.direction, meta.thread_hash, meta.n_participants). The `content` field is
never accessed. Output is monthly aggregate counts, written to
results/exploration_proxies_monthly.json.

Definitions (per calendar month, per source and pooled):
  threads_active        distinct thread hashes with any message
  new_threads           thread hashes seen for the first time (over the whole stream)
  new_threads_inbound   new threads whose first message is from `other`
  new_threads_outbound  new threads whose first message is from `carl` (self-initiated)
  replied_new_inbound   new inbound threads where self sent a message within 7 days
  dormant_reactivated   threads with no message for >= 180 days that got a message
  dormant_self_initiated  of those, the reactivating message was from self
  msgs_in / msgs_out    message counts
  counterpart_entropy   Shannon entropy (bits) of outbound messages over threads

Everything is a count; no identity, no text. Locked window (> 2026-09-16) is
excluded by construction (the stream is frozen at 09-15).
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

try:
    import orjson as _json
    loads = _json.loads
except ImportError:  # pragma: no cover
    loads = json.loads

STATE = Path(os.environ.get("CARL_MODEL_STATE", "~/.local/state/lifeos/carl-model")).expanduser()
EVENTS = STATE / "events"
OUT = Path(__file__).resolve().parents[2] / "results" / "exploration_proxies_monthly.json"
SOURCES = ["msg_messenger", "msg_instagram", "msg_twitter", "msg_telegram", "msg_discord", "msg_gmail",
           "msg_linkedin", "msg_gchat", "msg_gvoice"]
LOCK = dt.datetime(2026, 9, 17, tzinfo=dt.timezone.utc)
REPLY_WINDOW = dt.timedelta(days=7)
DORMANT = dt.timedelta(days=180)


def parse_ts(s: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def main():
    if not EVENTS.exists():
        sys.exit(f"MISSING {EVENTS}; refusing to write results")
    # per-thread state (thread hashes are already salted by the upstream pipeline)
    first_seen: dict[str, tuple[dt.datetime, str]] = {}
    last_seen: dict[str, dt.datetime] = {}
    pending_reply: dict[str, dt.datetime] = {}   # new inbound thread -> first inbound ts
    monthly = collections.defaultdict(lambda: collections.Counter())
    out_by_thread = collections.defaultdict(lambda: collections.Counter())
    rows_total = 0
    for src in SOURCES:
        p = EVENTS / f"{src}.jsonl"
        if not p.exists():
            print(f"skip {src}: not found", file=sys.stderr); continue
        # streams are per-source and sorted? not guaranteed -> collect minimal tuples then sort
        recs = []
        with p.open("rb") as fh:
            for line in fh:
                r = loads(line)
                meta = r.get("meta") or {}
                th = meta.get("thread_hash")
                if not th:
                    continue
                t = parse_ts(r["t_start"])
                if t >= LOCK:
                    continue
                actor = r.get("actor")
                recs.append((t, f"{src}:{th}", actor == "carl", int(meta.get("n_participants") or 2)))
        recs.sort()
        rows_total += len(recs)
        for t, th, is_self, npart in recs:
            key_all = ("all", t.strftime("%Y-%m")); key_src = (src, t.strftime("%Y-%m"))
            for key in (key_all, key_src):
                m = monthly[key]
                m["msgs_out" if is_self else "msgs_in"] += 1
                if npart > 2:
                    m["msgs_group"] += 1
            if th not in first_seen:
                first_seen[th] = (t, "self" if is_self else "other")
                for key in (key_all, key_src):
                    monthly[key]["new_threads"] += 1
                    monthly[key]["new_threads_outbound" if is_self else "new_threads_inbound"] += 1
                if not is_self:
                    pending_reply[th] = t
            else:
                gap = t - last_seen[th]
                if gap >= DORMANT:
                    for key in (key_all, key_src):
                        monthly[key]["dormant_reactivated"] += 1
                        if is_self:
                            monthly[key]["dormant_self_initiated"] += 1
                if is_self and th in pending_reply:
                    t0 = pending_reply.pop(th)
                    if t - t0 <= REPLY_WINDOW:
                        k0 = t0.strftime("%Y-%m")
                        monthly[("all", k0)]["replied_new_inbound"] += 1
                        monthly[(th.split(":")[0], k0)]["replied_new_inbound"] += 1
            last_seen[th] = t
            if is_self:
                out_by_thread[key_all][th] += 1
                out_by_thread[key_src][th] += 1
        # active threads per month per source
        active = collections.defaultdict(set)
        for t, th, _, _ in recs:
            active[(src, t.strftime("%Y-%m"))].add(th); active[("all", t.strftime("%Y-%m"))].add(th)
        for key, s in active.items():
            monthly[key]["threads_active"] = max(monthly[key]["threads_active"], len(s)) if key[0] != "all" else monthly[key]["threads_active"] + len(s)
    for key, c in out_by_thread.items():
        n = sum(c.values())
        monthly[key]["counterpart_entropy_bits"] = round(-sum(v / n * math.log2(v / n) for v in c.values()), 3) if n else 0.0
        monthly[key]["distinct_threads_out"] = len(c)
    result = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "status": "EXPLORATORY, not pre-registered; aggregates only; content never read",
              "definitions": __doc__.split("Definitions")[1].strip(),
              "rows_used": rows_total, "lock_excluded_after": LOCK.date().isoformat(),
              "series": {f"{s}|{m}": dict(c) for (s, m), c in sorted(monthly.items())}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=0))
    print(f"wrote {OUT} ({rows_total} rows, {len(monthly)} source-months)")


if __name__ == "__main__":
    main()

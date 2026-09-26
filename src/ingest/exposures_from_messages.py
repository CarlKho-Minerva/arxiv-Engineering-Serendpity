#!/usr/bin/env python3
"""E1: exposure–action–outcome table from message metadata.

Reads the normalized msg_*.jsonl streams. Never interprets `content`; the only
use of it is len(content) as a cost proxy. Writes data/derived/exposures.parquet
(git-ignored) with one row per *contact event*.

Contact event (exposure): an inbound message (actor != carl) that arrives after
>= GAP hours of silence in its thread (or is the thread's first message). It is
"what reached the subject", the unit the policies rank.

Observed action: `replied_7d` = subject sent a message in that thread within 7 days.

Labels (future-only, computed from the horizon window (t, t+H]):
  bursts_H          later message bursts in the thread (either direction), a burst
                    starts after >= GAP hours of silence
  self_msgs_H       subject messages in the thread within H
  tie_persisted_H   any message in the thread during the last 90 days of the horizon
  label_complete_H  t + H <= stream end (otherwise the label is censored)
  consequential_auto_H = tie_persisted_H and bursts_H >= 5   (Tier A; the
                    `new_context` clause of annotations/PROTOCOL.md cannot be
                    computed because thread hashes are per source; documented)

History features (all from messages with t_start <= t):
  is_new_thread, is_dormant (no message in thread for >= 180 d), is_group,
  n_participants, prior_msgs_in, prior_msgs_out, prior_contact_events,
  prior_reply_rate (share of prior contact events replied within 7 d),
  days_since_last_self, days_since_last_any, thread_age_days,
  global_30d_msgs_out, global_30d_active_threads, source_prior_share,
  chars_first_msg, hour_utc, dow.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import orjson
    loads = orjson.loads
except ImportError:  # pragma: no cover
    loads = json.loads

ROOT = Path(__file__).resolve().parents[2]
STATE = Path(os.environ.get("CARL_MODEL_STATE", "~/.local/state/lifeos/carl-model")).expanduser()
EVENTS = STATE / "events"
OUT = ROOT / "data" / "derived" / "exposures.parquet"
SOURCES = ["msg_messenger", "msg_instagram", "msg_twitter", "msg_telegram", "msg_discord", "msg_gmail",
           "msg_linkedin", "msg_gchat", "msg_gvoice"]
LOCK = pd.Timestamp("2026-09-17", tz="UTC")
GAP = pd.Timedelta(hours=24)
REPLY = pd.Timedelta(days=7)
DORMANT = pd.Timedelta(days=180)
HORIZONS = (90, 365)


def parse_ts(s: str) -> pd.Timestamp:
    t = pd.Timestamp(s)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def load_messages() -> pd.DataFrame:
    rows = []
    for src in SOURCES:
        p = EVENTS / f"{src}.jsonl"
        if not p.exists():
            print(f"skip {src}", file=sys.stderr); continue
        n = 0
        with p.open("rb") as fh:
            for line in fh:
                r = loads(line)
                meta = r.get("meta") or {}
                th = meta.get("thread_hash")
                if not th:
                    continue
                c = r.get("content")
                rows.append((r["t_start"], f"{src}:{th}", src, r.get("actor") == "carl",
                             int(meta.get("n_participants") or 2), len(c) if isinstance(c, str) else 0))
                n += 1
        print(f"{src}: {n} rows", file=sys.stderr)
    df = pd.DataFrame(rows, columns=["t", "thread", "source", "is_self", "npart", "chars"])
    df["t"] = pd.to_datetime(df["t"], utc=True, format="ISO8601")
    df = df[df["t"] < LOCK].sort_values(["thread", "t"], kind="stable").reset_index(drop=True)
    return df


def build(df: pd.DataFrame) -> pd.DataFrame:
    stream_end = df["t"].max()
    # ---- per-thread sequential pass ----
    df["prev_t"] = df.groupby("thread")["t"].shift()
    df["gap"] = df["t"] - df["prev_t"]
    df["burst_start"] = df["prev_t"].isna() | (df["gap"] >= GAP)
    df["burst_id"] = df.groupby("thread")["burst_start"].cumsum()
    df["is_exposure"] = df["burst_start"] & ~df["is_self"]
    g = df.groupby("thread", sort=False)
    df["prior_msgs_in"] = g["is_self"].transform(lambda s: (~s).cumsum().shift(fill_value=0))
    df["prior_msgs_out"] = g["is_self"].transform(lambda s: s.cumsum().shift(fill_value=0))
    df["prior_contact_events"] = g["is_exposure"].transform(lambda s: s.cumsum().shift(fill_value=0))
    df["thread_first_t"] = g["t"].transform("min")
    # last self message time before this row
    self_t = df["t"].where(df["is_self"])
    df["last_self_t"] = self_t.groupby(df["thread"]).transform(lambda s: s.shift().ffill())
    exp = df[df["is_exposure"]].copy()
    exp["is_new_thread"] = exp["prev_t"].isna()
    exp["is_dormant"] = (~exp["is_new_thread"]) & (exp["gap"] >= DORMANT)
    exp["is_group"] = exp["npart"] > 2
    exp["days_since_last_any"] = (exp["gap"].dt.total_seconds() / 86400).fillna(np.nan)
    exp["days_since_last_self"] = ((exp["t"] - exp["last_self_t"]).dt.total_seconds() / 86400)
    exp["thread_age_days"] = (exp["t"] - exp["thread_first_t"]).dt.total_seconds() / 86400
    exp["hour_utc"] = exp["t"].dt.hour
    exp["dow"] = exp["t"].dt.dayofweek
    exp = exp.rename(columns={"chars": "chars_first_msg"})

    # ---- action + labels: need per-thread arrays ----
    thread_groups = {th: (grp["t"].to_numpy(), grp["is_self"].to_numpy(), grp["burst_start"].to_numpy())
                     for th, grp in df.groupby("thread", sort=False)}
    replied, prior_reply_rate = [], []
    lab = {f"bursts_{H}": [] for H in HORIZONS}
    for H in HORIZONS:
        lab[f"self_msgs_{H}"] = []; lab[f"tie_persisted_{H}"] = []
    for th, grp in exp.groupby("thread", sort=False):
        ts, is_self, bstart = thread_groups[th]
        ts_ns = ts.astype("datetime64[ns]").astype("int64")
        self_ts = ts_ns[is_self]
        burst_ts = ts_ns[bstart]
        prev_replies, prev_events = 0, 0
        for t in grp["t"]:
            tn = np.datetime64(t.tz_convert("UTC").tz_localize(None), "ns").astype("int64")
            # action
            i0, i1 = np.searchsorted(self_ts, tn, "right"), np.searchsorted(self_ts, tn + REPLY.value, "right")
            r = i1 > i0
            replied.append(bool(r))
            prior_reply_rate.append(prev_replies / prev_events if prev_events else np.nan)
            prev_events += 1; prev_replies += int(r)
            for H in HORIZONS:
                hn = tn + H * 86400 * 10**9
                b0, b1 = np.searchsorted(burst_ts, tn, "right"), np.searchsorted(burst_ts, hn, "right")
                lab[f"bursts_{H}"].append(int(b1 - b0))
                s0, s1 = np.searchsorted(self_ts, tn, "right"), np.searchsorted(self_ts, hn, "right")
                lab[f"self_msgs_{H}"].append(int(s1 - s0))
                a0, a1 = np.searchsorted(ts_ns, hn - 90 * 86400 * 10**9, "right"), np.searchsorted(ts_ns, hn, "right")
                lab[f"tie_persisted_{H}"].append(bool(a1 > a0))
    exp["replied_7d"] = replied
    exp["prior_reply_rate"] = prior_reply_rate
    for k, v in lab.items():
        exp[k] = v
    for H in HORIZONS:
        exp[f"label_complete_{H}"] = (exp["t"] + pd.Timedelta(days=H)) <= stream_end
        exp[f"consequential_auto_{H}"] = exp[f"tie_persisted_{H}"] & (exp[f"bursts_{H}"] >= 5)

    # ---- global features <= t (sorted-time two-pointer) ----
    exp = exp.sort_values("t", kind="stable")
    self_all = df.loc[df["is_self"], ["t", "thread"]].sort_values("t")
    st = self_all["t"].to_numpy().astype("datetime64[ns]").astype("int64")
    sth = self_all["thread"].to_numpy()
    tn_all = exp["t"].to_numpy().astype("datetime64[ns]").astype("int64")
    w = 30 * 86400 * 10**9
    lo = np.searchsorted(st, tn_all - w, "right"); hi = np.searchsorted(st, tn_all, "right")
    exp["global_30d_msgs_out"] = hi - lo
    active = []
    cnt: collections.Counter = collections.Counter(); l = h = 0
    for a, b in zip(lo, hi):
        while h < b:
            cnt[sth[h]] += 1; h += 1
        while l < a:
            cnt[sth[l]] -= 1
            if cnt[sth[l]] == 0:
                del cnt[sth[l]]
            l += 1
        active.append(len(cnt))
    exp["global_30d_active_threads"] = active
    # source share of prior contact events
    src_codes = exp["source"].astype("category").cat.codes.to_numpy()
    n_src = src_codes.max() + 1
    share = np.empty(len(exp)); tot = np.zeros(n_src); n = 0
    for i, c in enumerate(src_codes):
        share[i] = tot[c] / n if n else np.nan
        tot[c] += 1; n += 1
    exp["source_prior_share"] = share
    exp["exposure_id"] = pd.util.hash_pandas_object(exp[["thread", "t"]], index=False).astype(str)
    cols = ["exposure_id", "t", "source", "thread", "is_new_thread", "is_dormant", "is_group", "npart",
            "prior_msgs_in", "prior_msgs_out", "prior_contact_events", "prior_reply_rate",
            "days_since_last_self", "days_since_last_any", "thread_age_days", "global_30d_msgs_out",
            "global_30d_active_threads", "source_prior_share", "chars_first_msg", "hour_utc", "dow",
            "replied_7d"] + sorted(lab) + [f"label_complete_{H}" for H in HORIZONS] + \
           [f"consequential_auto_{H}" for H in HORIZONS]
    return exp[cols].reset_index(drop=True)


def main():
    if not EVENTS.exists():
        sys.exit(f"MISSING {EVENTS}")
    df = load_messages()
    print(f"messages: {len(df)}, threads: {df['thread'].nunique()}, range {df['t'].min()} → {df['t'].max()}", file=sys.stderr)
    exp = build(df)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    exp.to_parquet(OUT, index=False)
    summary = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_messages": int(len(df)), "n_threads": int(df["thread"].nunique()), "n_exposures": int(len(exp)),
        "range": [str(exp["t"].min()), str(exp["t"].max())],
        "by_source": exp.groupby("source").size().to_dict(),
        "new_thread_exposures": int(exp["is_new_thread"].sum()), "dormant_exposures": int(exp["is_dormant"].sum()),
        "reply_rate_all": float(exp["replied_7d"].mean()),
        "reply_rate_new": float(exp.loc[exp["is_new_thread"], "replied_7d"].mean()),
        "reply_rate_dormant": float(exp.loc[exp["is_dormant"], "replied_7d"].mean()),
        **{f"consequential_auto_{H}_rate_complete": float(exp.loc[exp[f"label_complete_{H}"], f"consequential_auto_{H}"].mean()) for H in HORIZONS},
        **{f"consequential_auto_{H}_rate_weak_complete": float(exp.loc[exp[f"label_complete_{H}"] & (exp["is_new_thread"] | exp["is_dormant"]), f"consequential_auto_{H}"].mean()) for H in HORIZONS},
    }
    (ROOT / "results" / "exposures_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()

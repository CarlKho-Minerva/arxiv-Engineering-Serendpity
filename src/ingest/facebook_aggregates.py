#!/usr/bin/env python3
"""Facebook export → (a) monthly RQ6 aggregates, counts only; (b) a friend-request
exposure table (git-ignored) with hashed counterparts.

Limitations found on inspection (2026-09-26):
- event_invitations.json has no receipt timestamp (only event start/end), so an
  invitation's exposure time is unknown; we record it as <= start and mark it censored.
- your_friends.json gives the friendship timestamp but not who initiated, so
  accepted friendships cannot be split into "he accepted" vs "he asked".
  received_friend_requests.json (pending) and rejected_friend_requests.json do
  have timestamps and are clean "exposure, not accepted" rows.
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "fb"
SALT = os.environ.get("EXPOSURE_SALT", "")  # set from ~/.config/carl-life-os/.env in production


def h(name: str) -> str:
    return hashlib.sha256((SALT + name.strip().lower()).encode()).hexdigest()[:16]


def ts(x: int) -> pd.Timestamp:
    return pd.Timestamp(int(x), unit="s", tz="UTC")


def load(p: str):
    return json.loads((RAW / p).read_text())


def main():
    monthly = collections.defaultdict(collections.Counter)
    def add(t, key):
        monthly[t.strftime("%Y-%m")][key] += 1
    friends = load("friends/your_friends.json")["friends_v2"]
    for f in friends: add(ts(f["timestamp"]), "friends_added")
    for f in load("friends/received_friend_requests.json")["received_requests_v2"]: add(ts(f["timestamp"]), "requests_received_pending")
    for f in load("friends/rejected_friend_requests.json")["rejected_requests_v2"]: add(ts(f["timestamp"]), "requests_rejected")
    for f in load("friends/sent_friend_requests.json")["sent_requests_v2"]: add(ts(f["timestamp"]), "requests_sent_pending")
    for f in load("friends/removed_friends.json")["deleted_friends_v2"]: add(ts(f["timestamp"]), "friends_removed")
    for g in load("groups/your_group_membership_activity.json")["groups_joined_v2"]: add(ts(g["timestamp"]), "groups_joined")
    for g in load("groups/your_comments_in_groups.json")["group_comments_v2"]: add(ts(g["timestamp"]), "group_comments")
    for g in load("groups/group_posts_and_comments.json")["group_posts_v2"]: add(ts(g["timestamp"]), "group_posts")
    er = load("events/your_event_responses.json")["event_responses_v2"]
    for e in er["events_joined"]: add(ts(e["response_time"]), "events_joined")
    for e in er["events_interested"]: add(ts(e["response_time"]), "events_interested")
    inv = load("events/event_invitations.json")["events_invited_v2"]
    for e in inv: add(ts(e["start_timestamp"]), "event_invitations_by_event_start")
    out = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "status": "EXPLORATORY; counts only; names hashed and not written here",
           "totals": {"friends": len(friends), "event_invitations": len(inv), "events_joined": len(er["events_joined"]),
                      "events_interested": len(er["events_interested"])},
           "monthly": {m: dict(c) for m, c in sorted(monthly.items())}}
    (ROOT / "results" / "facebook_monthly.json").write_text(json.dumps(out, indent=0))
    # friend-request exposure table (hashed), git-ignored
    rows = []
    for f in load("friends/received_friend_requests.json")["received_requests_v2"]:
        rows.append({"t": ts(f["timestamp"]), "counterpart": h(f["name"]), "status": "pending"})
    for f in load("friends/rejected_friend_requests.json")["rejected_requests_v2"]:
        rows.append({"t": ts(f["timestamp"]), "counterpart": h(f["name"]), "status": "rejected"})
    for f in friends:
        rows.append({"t": ts(f["timestamp"]), "counterpart": h(f["name"]), "status": "friend_initiator_unknown"})
    (ROOT / "data" / "derived").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(ROOT / "data" / "derived" / "fb_friend_requests.parquet", index=False)
    yearly = collections.defaultdict(collections.Counter)
    for m, c in monthly.items():
        for k, v in c.items(): yearly[m[:4]][k] += v
    print(pd.DataFrame(yearly).T.fillna(0).astype(int).sort_index().to_string())


if __name__ == "__main__":
    main()

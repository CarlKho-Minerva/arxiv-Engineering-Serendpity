"""Symmetric leakage filter.

`features_at(t)` is the *only* sanctioned way to build a feature frame for
evaluating an exposure at time t. It enforces:

  (a) column-level: no FUTURE_ONLY_FIELDS present;
  (b) row-level:    every contributing event has timestamp_start <= t;
  (c) symmetric:    the same filter is applied to candidates, history, and any
                    auxiliary streams (e.g. algorithmic-mirror snapshots), so
                    no stream is exempt.
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable

import pandas as pd

from src.schema import FUTURE_ONLY_FIELDS


class LeakageError(ValueError):
    """Raised when a frame could use information from after the decision time."""


def assert_no_future_fields(frame: pd.DataFrame, *, where: str = "features") -> None:
    bad = sorted(set(frame.columns) & FUTURE_ONLY_FIELDS)
    if bad:
        raise LeakageError(f"{where}: future-only columns present: {bad}")


def assert_all_before(frame: pd.DataFrame, t: dt.datetime, *, col: str = "timestamp_start",
                      where: str = "features") -> None:
    if col not in frame.columns:
        raise LeakageError(f"{where}: missing timestamp column {col!r}")
    ts = pd.to_datetime(frame[col], utc=True)
    if ts.isna().any():
        raise LeakageError(f"{where}: {int(ts.isna().sum())} rows have no timestamp")
    late = ts > pd.Timestamp(t)
    if late.any():
        raise LeakageError(f"{where}: {int(late.sum())} rows are timestamped after t={t.isoformat()}")


def features_at(t: dt.datetime, *streams: pd.DataFrame, names: Iterable[str] | None = None,
                ) -> tuple[pd.DataFrame, ...]:
    """Filter every stream to rows with timestamp_start <= t and drop label columns.

    Returns the filtered streams in the same order. Raises LeakageError if any
    stream carries a future-only column (we refuse rather than silently drop, so
    that a pipeline wiring mistake is loud).
    """
    if t.tzinfo is None:
        raise LeakageError("decision time t must be timezone-aware")
    names = list(names) if names is not None else [f"stream{i}" for i in range(len(streams))]
    out = []
    for name, s in zip(names, streams):
        assert_no_future_fields(s, where=name)
        ts = pd.to_datetime(s["timestamp_start"], utc=True)
        out.append(s.loc[ts <= pd.Timestamp(t)].copy())
    return tuple(out)


def label_horizon_ok(exposure_t: dt.datetime, outcome_t: dt.datetime, horizon_days: int) -> bool:
    """An outcome counts only if it lands strictly after exposure and within the horizon."""
    delta = outcome_t - exposure_t
    return dt.timedelta(0) < delta <= dt.timedelta(days=horizon_days)

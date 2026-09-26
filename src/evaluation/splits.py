"""Chronological splits with an embargo gap.

Never random splits: consecutive days share context, and the outcome horizon
means a label at the end of train can be caused by an exposure that would sit
in validation. The embargo must be >= the outcome horizon.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pandas as pd


@dataclasses.dataclass(frozen=True)
class ChronoSplit:
    train_end: dt.datetime
    val_start: dt.datetime
    val_end: dt.datetime
    test_start: dt.datetime
    embargo_days: int

    def assign(self, ts: pd.Series) -> pd.Series:
        ts = pd.to_datetime(ts, utc=True)
        out = pd.Series("embargo", index=ts.index, dtype="object")
        out[ts <= pd.Timestamp(self.train_end)] = "train"
        out[(ts >= pd.Timestamp(self.val_start)) & (ts <= pd.Timestamp(self.val_end))] = "val"
        out[ts >= pd.Timestamp(self.test_start)] = "test"
        return out


def make_chrono_split(timestamps: pd.Series, *, train_frac: float = 0.6, val_frac: float = 0.2,
                      embargo_days: int) -> ChronoSplit:
    if embargo_days < 0:
        raise ValueError("embargo_days must be >= 0")
    if not 0 < train_frac < 1 or not 0 < val_frac < 1 or train_frac + val_frac >= 1:
        raise ValueError("fractions must be in (0,1) and sum to < 1")
    ts = pd.to_datetime(timestamps, utc=True).sort_values()
    if ts.isna().any():
        raise ValueError("timestamps contain NaT")
    n = len(ts)
    train_end = ts.iloc[int(n * train_frac) - 1]
    gap = pd.Timedelta(days=embargo_days)
    val_start = train_end + gap
    val_end = ts.iloc[int(n * (train_frac + val_frac)) - 1]
    if val_end <= val_start:
        raise ValueError("validation window collapsed; reduce embargo or increase data")
    test_start = val_end + gap
    return ChronoSplit(train_end.to_pydatetime(), val_start.to_pydatetime(), val_end.to_pydatetime(),
                       test_start.to_pydatetime(), embargo_days)


def assert_split_is_chronological(split: ChronoSplit, horizon_days: int) -> None:
    if not (split.train_end < split.val_start <= split.val_end < split.test_start):
        raise ValueError("split boundaries are not monotone")
    if split.embargo_days < horizon_days:
        raise ValueError(f"embargo {split.embargo_days}d < outcome horizon {horizon_days}d: labels leak")

import datetime as dt

import pandas as pd
import pytest

from src.evaluation.splits import assert_split_is_chronological, make_chrono_split

UTC = dt.timezone.utc


def _ts(n=365):
    return pd.Series([dt.datetime(2019, 1, 1, tzinfo=UTC) + dt.timedelta(days=i) for i in range(n)])


def test_split_is_monotone_and_embargoed():
    s = make_chrono_split(_ts(), embargo_days=30)
    assert s.train_end < s.val_start <= s.val_end < s.test_start
    assert (s.val_start - s.train_end).days == 30
    assert (s.test_start - s.val_end).days == 30
    assert_split_is_chronological(s, horizon_days=30)


def test_embargo_shorter_than_horizon_is_rejected():
    s = make_chrono_split(_ts(), embargo_days=10)
    with pytest.raises(ValueError, match="leak"):
        assert_split_is_chronological(s, horizon_days=30)


def test_assignment_has_no_overlap_and_embargo_rows_are_excluded():
    ts = _ts()
    s = make_chrono_split(ts, embargo_days=30)
    part = s.assign(ts)
    assert set(part.unique()) <= {"train", "val", "test", "embargo"}
    assert (part == "embargo").sum() > 0
    # no test row precedes any train row
    assert ts[part == "test"].min() > ts[part == "train"].max()
    assert ts[part == "val"].min() > ts[part == "train"].max()
    assert ts[part == "test"].min() > ts[part == "val"].max()


def test_shuffled_input_gives_same_split():
    ts = _ts()
    a = make_chrono_split(ts, embargo_days=7)
    b = make_chrono_split(ts.sample(frac=1, random_state=0), embargo_days=7)
    assert a == b


def test_too_small_window_is_refused():
    with pytest.raises(ValueError):
        make_chrono_split(_ts(20), embargo_days=30)

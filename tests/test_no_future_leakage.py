import datetime as dt

import pandas as pd
import pytest

from src.evaluation.leakage import (LeakageError, assert_all_before, assert_no_future_fields,
                                    features_at, label_horizon_ok)
from src.schema import FUTURE_ONLY_FIELDS, Event

UTC = dt.timezone.utc
T = dt.datetime(2020, 6, 1, tzinfo=UTC)


def _hist(n=5, start=dt.datetime(2020, 1, 1, tzinfo=UTC)):
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "timestamp_start": [start + dt.timedelta(days=30 * i) for i in range(n)],
        "relevance": [0.1 * i for i in range(n)],
    })


@pytest.mark.parametrize("field", sorted(FUTURE_ONLY_FIELDS))
def test_every_future_field_is_rejected(field):
    df = _hist()
    df[field] = 1
    with pytest.raises(LeakageError, match=field):
        assert_no_future_fields(df)
    with pytest.raises(LeakageError):
        features_at(T, df)


def test_rows_after_t_are_dropped_from_every_stream():
    a = _hist(12)  # spans 2020-01 .. 2020-11
    b = _hist(12, start=dt.datetime(2020, 3, 1, tzinfo=UTC))
    fa, fb = features_at(T, a, b, names=["hist", "mirror"])
    assert (pd.to_datetime(fa.timestamp_start, utc=True) <= pd.Timestamp(T)).all()
    assert (pd.to_datetime(fb.timestamp_start, utc=True) <= pd.Timestamp(T)).all()
    assert len(fa) < len(a) and len(fb) < len(b)


def test_symmetric_filter_applies_to_auxiliary_streams_too():
    """An auxiliary stream (algorithmic mirror) carrying a label column is rejected
    just like the primary stream: no stream is exempt."""
    hist = _hist()
    mirror = _hist()
    mirror["consequential"] = 0
    with pytest.raises(LeakageError, match="mirror"):
        features_at(T, hist, mirror, names=["hist", "mirror"])


def test_assert_all_before_catches_late_rows():
    df = _hist(12)
    with pytest.raises(LeakageError, match="after t"):
        assert_all_before(df, T)


def test_naive_decision_time_is_refused():
    with pytest.raises(LeakageError):
        features_at(dt.datetime(2020, 6, 1), _hist())


def test_event_feature_view_never_contains_labels():
    e = Event(event_id="x", timestamp_start=T, source="test", modality="text",
              outcome_labels=["project"], followup_event_ids=["y"])
    assert not (set(e.feature_view()) & FUTURE_ONLY_FIELDS)
    assert set(e.label_view()) == {"followup_event_ids", "outcome_labels"}


def test_label_horizon_is_strict_after_and_within():
    assert label_horizon_ok(T, T + dt.timedelta(days=10), 30)
    assert not label_horizon_ok(T, T, 30)                     # same instant is not an outcome
    assert not label_horizon_ok(T, T - dt.timedelta(days=1), 30)
    assert not label_horizon_ok(T, T + dt.timedelta(days=31), 30)

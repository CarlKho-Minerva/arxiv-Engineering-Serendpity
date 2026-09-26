"""Normalized event schema for the longitudinal single-subject study.

Two hard rules are encoded here rather than in prose:

1. `FUTURE_ONLY_FIELDS` may never be used as features. They are labels.
   `src.evaluation.leakage.assert_no_future_fields` rejects any feature frame
   that contains them, and `tests/test_no_future_leakage.py` injects them on
   purpose to prove the rejection works.
2. Raw references (`raw_reference`) point at local files only. Nothing that
   dereferences them may leave the machine.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any, Optional

ACTION_FAMILIES = (
    # Kept deliberately coarse. The 7 families of the prior LifeOS experiment
    # are recorded in data_inventory.md once verified; these are the families
    # used for the *exposure* experiment and may be a superset.
    "consume",      # read / watch / listen
    "communicate",  # message / email / call
    "create",       # write / code / design
    "apply",        # application, form, sign-up
    "attend",       # event, meeting, hackathon, class
    "connect",      # new contact / community join
    "navigate",     # browse / search / move between contexts
    "idle",
)

MODALITIES = (
    "screen", "input", "app_activity", "browser", "note", "text", "conversation",
    "email", "calendar", "social", "contacts", "ego_video", "room_video",
    "phone_sensor", "wearable", "location", "derived_scene", "physiology",
    "algorithmic_mirror",
)

# Anything that is only knowable *after* the exposure. These are labels, never
# features. The leakage filter rejects frames containing any of these columns.
FUTURE_ONLY_FIELDS = frozenset({
    "followup_event_ids",
    "outcome_labels",
    "outcome_horizon_days",
    "consequential",
    "downstream_repeat_count",
    "downstream_project",
    "downstream_application",
    "downstream_money",
    "downstream_publication",
    "downstream_collaborator",
    "downstream_topic_shift",
    "annotation_rationale",
})

# Fields a feature row may carry. Everything else is either a raw pointer or a label.
FEATURE_SAFE_FIELDS = frozenset({
    "event_id", "timestamp_start", "timestamp_end", "source", "modality", "actor",
    "context_id", "text_summary_local", "embedding", "topic", "entities_redacted",
    "action_family", "candidate_opportunity", "candidate_person", "candidate_content",
    "observed_action", "metadata",
})


@dataclasses.dataclass
class Event:
    event_id: str
    timestamp_start: dt.datetime
    source: str
    modality: str
    timestamp_end: Optional[dt.datetime] = None
    actor: str = "self"                     # self | other | platform
    context_id: Optional[str] = None        # session / day / thread grouping
    raw_reference: Optional[str] = None     # local path + locator; never leaves the machine
    text_summary_local: Optional[str] = None
    embedding: Optional[list[float]] = None
    topic: Optional[str] = None
    entities_redacted: Optional[list[str]] = None   # hashed entity ids
    action_family: Optional[str] = None
    candidate_opportunity: bool = False
    candidate_person: bool = False
    candidate_content: bool = False
    observed_action: Optional[str] = None   # engaged | ignored | unknown
    # ---- labels only (future) ----
    followup_event_ids: Optional[list[str]] = None
    outcome_labels: Optional[list[str]] = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.modality not in MODALITIES:
            raise ValueError(f"unknown modality {self.modality!r}")
        if self.action_family is not None and self.action_family not in ACTION_FAMILIES:
            raise ValueError(f"unknown action_family {self.action_family!r}")
        if self.timestamp_start.tzinfo is None:
            raise ValueError("timestamp_start must be timezone-aware")
        if self.timestamp_end is not None and self.timestamp_end < self.timestamp_start:
            raise ValueError("timestamp_end precedes timestamp_start")

    def feature_view(self) -> dict[str, Any]:
        """Return only fields that are legal to use as features."""
        d = dataclasses.asdict(self)
        return {k: v for k, v in d.items() if k in FEATURE_SAFE_FIELDS}

    def label_view(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        return {k: v for k, v in d.items() if k in FUTURE_ONLY_FIELDS}

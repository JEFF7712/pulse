"""Canonical event types registry."""

from pulse.domain.event_types import (
    DEV_EVENT_TYPES,
    EVENT_TYPE_TO_BUCKET,
    REGISTERED_EVENT_TYPES,
)


def test_registered_types_have_bucket_labels() -> None:
    assert set(EVENT_TYPE_TO_BUCKET.keys()) == REGISTERED_EVENT_TYPES


def test_dev_types_are_subset_of_registered() -> None:
    assert DEV_EVENT_TYPES <= REGISTERED_EVENT_TYPES

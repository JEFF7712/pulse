"""Canonical Pulse event_type strings and preprocessor bucket mapping.

Connectors should emit only types listed here (plus ad-hoc ``manual.*`` if needed).
Unknown types still appear in time-block aggregates but not in domain sections.
"""

from __future__ import annotations

from typing import Final

# --- Browsing ---
BROWSING_VISIT: Final = "browsing.visit"

# --- Email ---
EMAIL_RECEIVED: Final = "email.received"

# --- Calendar ---
CALENDAR_EVENT: Final = "calendar.event"

# --- Media ---
MEDIA_SPOTIFY_PLAY: Final = "media.spotify.play"
MEDIA_SPOTIFY_SAVE: Final = "media.spotify.save"
MEDIA_SPOTIFY_TOP_TRACK: Final = "media.spotify.top_track"
MEDIA_SPOTIFY_TOP_ARTIST: Final = "media.spotify.top_artist"
MEDIA_YOUTUBE_ACTIVITY: Final = "media.youtube.activity"
MEDIA_YOUTUBE_LIKE: Final = "media.youtube.like"
MEDIA_YOUTUBE_SUBSCRIPTION: Final = "media.youtube.subscription"

# --- Development / VCS ---
DEV_PUSH: Final = "dev.push"
DEV_ISSUE: Final = "dev.issue"
DEV_PULL_REQUEST: Final = "dev.pull_request"
DEV_COMMENT: Final = "dev.comment"
DEV_REPO_ACTIVITY: Final = "dev.repo_activity"
DEV_LINEAR_ISSUE: Final = "dev.linear.issue"

# --- Finance ---
FINANCE_TRANSACTION: Final = "finance.transaction"

# --- Health ---
HEALTH_SLEEP: Final = "health.sleep"
HEALTH_READINESS: Final = "health.readiness"
HEALTH_ACTIVITY: Final = "health.activity"
HEALTH_WORKOUT: Final = "health.workout"

# --- Notion ---
NOTION_PAGE_EDITED: Final = "notion.page_edited"

# --- Feeds (time blocks only; no dedicated preprocessor section) ---
FEED_ITEM: Final = "feed.item"

DEV_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        DEV_PUSH,
        DEV_ISSUE,
        DEV_PULL_REQUEST,
        DEV_COMMENT,
        DEV_REPO_ACTIVITY,
        DEV_LINEAR_ISSUE,
    }
)

MEDIA_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        MEDIA_SPOTIFY_PLAY,
        MEDIA_SPOTIFY_SAVE,
        MEDIA_SPOTIFY_TOP_TRACK,
        MEDIA_SPOTIFY_TOP_ARTIST,
        MEDIA_YOUTUBE_ACTIVITY,
        MEDIA_YOUTUBE_LIKE,
        MEDIA_YOUTUBE_SUBSCRIPTION,
    }
)

# Every event_type emitted by built-in pull connectors (see ``connectors/``).
REGISTERED_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        BROWSING_VISIT,
        EMAIL_RECEIVED,
        CALENDAR_EVENT,
        *MEDIA_EVENT_TYPES,
        *DEV_EVENT_TYPES,
        FINANCE_TRANSACTION,
        HEALTH_SLEEP,
        HEALTH_READINESS,
        HEALTH_ACTIVITY,
        HEALTH_WORKOUT,
        NOTION_PAGE_EDITED,
        FEED_ITEM,
    }
)

# Maps event_type -> preprocessor bucket name (for docs / validation).
EVENT_TYPE_TO_BUCKET: Final[dict[str, str]] = {
    BROWSING_VISIT: "browsing",
    EMAIL_RECEIVED: "email",
    CALENDAR_EVENT: "calendar",
    **{t: "media" for t in MEDIA_EVENT_TYPES},
    **{t: "dev" for t in DEV_EVENT_TYPES},
    FINANCE_TRANSACTION: "finance",
    HEALTH_SLEEP: "health",
    HEALTH_READINESS: "health",
    HEALTH_ACTIVITY: "health",
    HEALTH_WORKOUT: "health",
    NOTION_PAGE_EDITED: "notion",
    FEED_ITEM: "unbucketed",
}

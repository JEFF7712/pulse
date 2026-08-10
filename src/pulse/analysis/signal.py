"""Which events carry signal about the user, and which are just addressed to them.

Marketing blasts, job-alert digests and newsletters are the bulk of an inbox by
volume and tell you almost nothing about what someone is doing. They also actively
poison change detection: every newsletter is textually unique, so embedding novelty
ranks them top, and a retailer that mails twice as often this week reads as a spike.
Filter them once, here, and both lanes stay honest.
"""

from __future__ import annotations

from pulse.domain.events import Event

# Sender fragments that mark bulk/automated mail. Used when Gmail's own category is
# absent (older events) or ambiguous ("updates" carries both receipts and blasts).
BULK_SENDER_HINTS = (
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "notify",
    "notification",
    "newsletter",
    "mailer",
    "marketing",
    "updates@",
    "info@",
    "@e.",
    "@m.",
    "@a.",
    "@e-",
    "@reply.",
    "@email.",
    "@mail.",
    "@news.",
    "@newsletter.",
    "@selections.",
    "jobalert",
    "noreply@",
    "offers@",
    "offers.",
    "deals",
    "promo",
    "-noreply",
    "customerservice",
    "store-news",
    "store-",
)

# Gmail categories that settle the question on their own. Anything else ("updates",
# or an unrecognised tag) needs the sender heuristic to break the tie.
HIGH_SIGNAL_CATEGORIES = frozenset({"primary"})
BULK_CATEGORIES = frozenset({"promotions", "social", "forums"})


def sender_looks_bulk(senders: list[str]) -> bool:
    low = " ".join(senders).lower()
    return any(hint in low for hint in BULK_SENDER_HINTS)


def is_bulk_email(category: str | None, senders: list[str]) -> bool:
    """Classify one email thread as bulk/low-signal."""
    if category:
        if category in HIGH_SIGNAL_CATEGORIES:
            return False
        if category in BULK_CATEGORIES:
            return True
        # "updates" is mixed: it carries receipts, payment confirmations and bank
        # security notices (high signal) alongside job-alert and shipping blasts.
        # Category alone cannot separate them, so fall through to the sender.
    return sender_looks_bulk(senders)


def is_bulk_event(event: Event) -> bool:
    """True when the event is bulk mail. Non-email sources are never bulk."""
    if event.source != "gmail":
        return False
    data = event.data or {}
    category = data.get("category")
    sender = str(data.get("sender") or "")
    return is_bulk_email(
        str(category) if category else None,
        [sender],
    )

"""Canonical entity keys for events.

An "entity" is the recurring thing an event is *about* — a browsing domain, an email
correspondent, a repo, a channel. Change detection works on entities rather than raw
events because a raw event never repeats, so nothing about it can be new or dormant.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pulse.analysis.signal import is_bulk_event
from pulse.domain.events import Event

_STRIP_PREFIXES = ("www.", "m.", "amp.")

# Public-suffix handling without the dependency: the common two-label suffixes are
# enough for personal browsing, and anything unlisted just keeps one extra label.
_MULTI_PART_SUFFIXES = frozenset(
    {
        "co.uk",
        "ac.uk",
        "gov.uk",
        "org.uk",
        "co.jp",
        "co.kr",
        "co.in",
        "co.nz",
        "co.za",
        "com.au",
        "com.br",
        "com.cn",
        "com.mx",
        "com.tr",
        "net.au",
        "org.au",
        "edu.au",
        "ac.in",
        "edu.in",
    }
)


def registrable_domain(host: str) -> str:
    """Collapse a hostname to its registrable domain.

    Subdomains fragment an entity that is really one thing: `parchment.com`,
    `auth.parchment.com` and `registration.parchment.com` are a single site to the
    user, and treating them separately both triples the noise in the delta list and
    stops related events from clustering.
    """
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    # An IPv4 literal has no registrable domain; truncating 192.168.1.10 to "1.10"
    # invents a host and merges unrelated homelab machines into one entity.
    if all(label.isdigit() for label in labels):
        return host
    last_two = ".".join(labels[-2:])
    if last_two in _MULTI_PART_SUFFIXES:
        return ".".join(labels[-3:])
    return last_two


def _domain_of(url: str) -> str | None:
    """Full host, minus a leading `www.`-style prefix.

    Deliberately *not* rolled up to the registrable domain: "a new subdomain of a
    site you already use" is how starting a new service at a known institution
    shows up, and that signal dies under a rollup. Grouping happens later, where
    repetition can be collapsed without losing the distinction.
    """
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    for prefix in _STRIP_PREFIXES:
        if host.startswith(prefix):
            return host[len(prefix) :] or None
    return host


def entity_parent(kind: str, key: str) -> str:
    """The grouping key used to collapse near-duplicate entities."""
    if kind == "domain" and "." in key:
        return registrable_domain(key)
    return key


def _sender_address(sender: str) -> str | None:
    """Pull the bare address out of a `Display Name <addr@host>` header value."""
    if not sender:
        return None
    value = sender.strip()
    if "<" in value and ">" in value:
        value = value[value.rindex("<") + 1 : value.rindex(">")]
    value = value.strip().lower()
    return value or None


def entity_key(event: Event) -> tuple[str, str] | None:
    """Return ``(kind, key)`` for an event, or None when it has no stable entity."""
    data = event.data or {}
    source = event.source

    if source == "browser":
        domain = _domain_of(str(data.get("url") or ""))
        return ("domain", domain) if domain else None

    if source == "gmail":
        # A retailer mailing twice as often this week is not a change in the user's
        # life, so bulk senders never become entities in the first place.
        if is_bulk_event(event):
            return None
        addr = _sender_address(str(data.get("sender") or ""))
        return ("sender", addr) if addr else None

    if source == "github":
        repo = str(data.get("repo") or "").strip()
        return ("repo", repo) if repo else None

    if source == "youtube":
        channel = str(data.get("channel") or "").strip()
        return ("channel", channel) if channel else None

    if source == "spotify":
        artist = str(data.get("artist") or "").strip()
        return ("artist", artist) if artist else None

    if source == "calendar":
        title = str(data.get("title") or "").strip()
        return ("event", title) if title else None

    if source == "plaid":
        merchant = str(data.get("merchant") or data.get("name") or "").strip()
        return ("merchant", merchant) if merchant else None

    return None


def entity_label(kind: str, key: str) -> str:
    return f"{kind}:{key}"

"""Turn a user's reply into a decision on a proposed fact.

The confirmation loop is the whole reason facts may be auto-maintained at all: the
agent supplies evidence, the user supplies the yes. Without the second half this is
just silent mutation of a document the user believes they wrote.
"""

from __future__ import annotations

import logging
import re

import aiosqlite

from pulse.analysis.self_model import FACTS_FILE, upsert_fact
from pulse.analysis.vault_memory import VaultMemory
from pulse.domain.notifications import Notification, extract_reply_context
from pulse.store.proposals import (
    ACCEPTED,
    REJECTED,
    FactProposal,
    FactProposalRepository,
)

logger = logging.getLogger(__name__)

_AFFIRM = {"y", "yes", "yeah", "yep", "correct", "confirm", "confirmed", "ok", "right"}
_DENY = {"n", "no", "nope", "wrong", "incorrect", "reject", "nah"}

_ID_RE = re.compile(r"\b([0-9a-f]{12})\b")


def _first_word(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()
    return cleaned.split()[0] if cleaned.split() else ""


def parse_decision(text: str) -> str | None:
    """Return ``accepted`` / ``rejected`` from a free-text reply, else None."""
    word = _first_word(text or "")
    if word in _AFFIRM:
        return ACCEPTED
    if word in _DENY:
        return REJECTED
    return None


def parse_proposal_id(text: str) -> str | None:
    """Pull a proposal id from the reply, whether quoted or typed bare."""
    context = extract_reply_context(text or "")
    if context:
        return context
    match = _ID_RE.search(text or "")
    return match.group(1) if match else None


def format_proposal_notification(proposal: FactProposal) -> Notification:
    was = proposal.current_value or "(not recorded)"
    body = (
        f"{proposal.field}\n"
        f"  now: {was}\n"
        f"  suggested: {proposal.proposed_value}\n\n"
        f"why: {proposal.evidence}\n\n"
        "Reply YES to apply, NO to discard. Nothing changes until you do."
    )
    return Notification(
        title="Confirm a profile fact",
        body=body,
        category="fact_proposal",
        context_id=proposal.id,
    )


async def apply_reply(
    db: aiosqlite.Connection,
    *,
    vault_path: str,
    text: str,
    today: str,
) -> str | None:
    """Resolve a reply into a decision. Returns a human-readable result, or None.

    None means the message was not about a fact proposal at all, which is the common
    case for a chat channel and must not be treated as an error.
    """
    decision = parse_decision(text)
    if decision is None:
        return None

    repo = FactProposalRepository(db)
    proposal_id = parse_proposal_id(text)
    if proposal_id is None:
        pending = await repo.list_pending()
        # A bare "yes" is only unambiguous when exactly one question is outstanding.
        if len(pending) != 1:
            if not pending:
                return None
            return (
                f"{len(pending)} proposals are pending, so a bare reply is ambiguous. "
                "Reply with the id shown on the one you mean."
            )
        proposal_id = pending[0].id

    decided = await repo.decide(proposal_id, decision)
    if decided is None:
        return None

    if decided.status == REJECTED:
        return f"Discarded: {decided.field} stays as it was."

    try:
        vault = VaultMemory(vault_path)
        existing = vault.read_config_file(FACTS_FILE)
        updated = upsert_fact(
            existing, decided.field, decided.proposed_value, confirmed_on=today
        )
        vault.write_config_file(FACTS_FILE, updated)
    except (ValueError, OSError):
        logger.exception("failed to write confirmed fact %s", decided.field)
        return f"Confirmed {decided.field}, but writing it to the vault failed."

    return f"Updated: {decided.field} is now {decided.proposed_value}."

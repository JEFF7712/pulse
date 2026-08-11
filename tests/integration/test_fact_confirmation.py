import asyncio
from pathlib import Path

import aiosqlite

from pulse.analysis.self_model import FACTS_FILE, parse_facts, upsert_fact
from pulse.analysis.vault_memory import VaultMemory
from pulse.services.fact_confirmation import (
    apply_reply,
    format_proposal_notification,
    parse_decision,
    parse_proposal_id,
)
from pulse.store.proposals import ACCEPTED, PENDING, REJECTED, FactProposalRepository
from pulse.store.schema import bootstrap_schema

TODAY = "2026-08-10"


def _run(tmp_path: Path, body):
    async def _inner():
        async with aiosqlite.connect(tmp_path / "t.db") as db:
            await bootstrap_schema(db)
            (tmp_path / "04-Config").mkdir(parents=True, exist_ok=True)
            return await body(db)

    return asyncio.run(_inner())


# ----------------------------------------------------------------------
# reply parsing
# ----------------------------------------------------------------------


def test_decisions_are_read_from_natural_replies():
    assert parse_decision("yes") == ACCEPTED
    assert parse_decision("Yes please") == ACCEPTED
    assert parse_decision("yep, that's right") == ACCEPTED
    assert parse_decision("no") == REJECTED
    assert parse_decision("Nope") == REJECTED
    assert parse_decision("what did I do yesterday?") is None
    assert parse_decision("") is None


def test_proposal_id_is_found_in_a_quoted_reply():
    quoted = "yes\nConfirm a profile fact\n\nLocation\n\nContext: abc123def456"
    assert parse_proposal_id(quoted) == "abc123def456"
    assert parse_proposal_id("yes abc123def456") == "abc123def456"
    assert parse_proposal_id("yes") is None


# ----------------------------------------------------------------------
# the loop
# ----------------------------------------------------------------------


def test_confirming_writes_the_fact_and_never_the_profile(tmp_path: Path):
    profile = tmp_path / "04-Config" / "profile.md"

    async def body(db):
        profile.write_text("# User Profile\n\n**Location:** Madison, WI\n")
        original = profile.read_text()

        repo = FactProposalRepository(db)
        p = await repo.propose(
            field="Location",
            proposed_value="Columbus, OH",
            evidence="3 months of activity in the Columbus timezone",
            current_value="Madison, WI",
        )
        result = await apply_reply(
            db,
            vault_path=str(tmp_path),
            text=f"yes\nContext: {p.id}",
            today=TODAY,
        )
        assert "Columbus, OH" in result

        facts = parse_facts(VaultMemory(str(tmp_path)).read_config_file(FACTS_FILE))
        assert facts["Location"] == f"Columbus, OH  _(confirmed {TODAY})_"
        # the stated profile is untouched
        assert profile.read_text() == original
        assert (await repo.get(p.id)).status == ACCEPTED

    _run(tmp_path, body)


def test_rejecting_changes_nothing(tmp_path: Path):
    async def body(db):
        repo = FactProposalRepository(db)
        p = await repo.propose(
            field="Location", proposed_value="Columbus, OH", evidence="e"
        )
        result = await apply_reply(
            db, vault_path=str(tmp_path), text=f"no\nContext: {p.id}", today=TODAY
        )
        assert "Discarded" in result
        assert not (tmp_path / "04-Config" / FACTS_FILE).exists()
        assert (await repo.get(p.id)).status == REJECTED

    _run(tmp_path, body)


def test_an_ordinary_message_is_not_a_decision(tmp_path: Path):
    """A chat channel carries normal conversation; that must not read as an error."""

    async def body(db):
        await FactProposalRepository(db).propose(
            field="Location", proposed_value="Columbus, OH", evidence="e"
        )
        assert (
            await apply_reply(
                db, vault_path=str(tmp_path), text="how many emails today?", today=TODAY
            )
            is None
        )

    _run(tmp_path, body)


def test_a_bare_yes_resolves_only_when_one_proposal_is_pending(tmp_path: Path):
    async def body(db):
        repo = FactProposalRepository(db)
        await repo.propose(
            field="Location", proposed_value="Columbus, OH", evidence="e"
        )
        result = await apply_reply(
            db, vault_path=str(tmp_path), text="yes", today=TODAY
        )
        assert "Location" in result

        # two pending → ambiguous, and nothing is applied
        await repo.propose(field="School", proposed_value="X", evidence="e")
        await repo.propose(field="Employer", proposed_value="Y", evidence="e")
        result = await apply_reply(
            db, vault_path=str(tmp_path), text="yes", today=TODAY
        )
        assert "ambiguous" in result
        assert [p.status for p in await repo.list_pending()] == [PENDING, PENDING]

    _run(tmp_path, body)


def test_a_second_reply_to_a_decided_proposal_is_inert(tmp_path: Path):
    async def body(db):
        repo = FactProposalRepository(db)
        p = await repo.propose(field="Location", proposed_value="A", evidence="e")
        await apply_reply(
            db, vault_path=str(tmp_path), text=f"yes\nContext: {p.id}", today=TODAY
        )
        again = await apply_reply(
            db, vault_path=str(tmp_path), text=f"no\nContext: {p.id}", today=TODAY
        )
        assert again is None
        assert (await repo.get(p.id)).status == ACCEPTED

    _run(tmp_path, body)


def test_reproposing_a_field_supersedes_rather_than_stacks(tmp_path: Path):
    """Two pending answers to one question is not a queue, it is a bug."""

    async def body(db):
        repo = FactProposalRepository(db)
        first = await repo.propose(
            field="Location", proposed_value="Columbus, OH", evidence="e1"
        )
        second = await repo.propose(
            field="Location", proposed_value="Cleveland, OH", evidence="e2"
        )
        pending = await repo.list_pending()
        assert [p.id for p in pending] == [second.id]
        assert (await repo.get(first.id)).status == "superseded"

    _run(tmp_path, body)


def test_notification_carries_the_reply_handle_and_the_evidence(tmp_path: Path):
    async def body(db):
        p = await FactProposalRepository(db).propose(
            field="Location",
            proposed_value="Columbus, OH",
            evidence="3 months of Columbus-timezone activity",
            current_value="Madison, WI",
        )
        n = format_proposal_notification(p)
        assert n.context_id == p.id
        assert "Madison, WI" in n.body and "Columbus, OH" in n.body
        assert "3 months" in n.body
        assert "YES" in n.body

    _run(tmp_path, body)


# ----------------------------------------------------------------------
# facts file
# ----------------------------------------------------------------------


def test_upsert_fact_replaces_in_place_and_preserves_hand_written_lines():
    content = (
        "# Facts\n\nSome note I wrote myself.\n\n"
        "- **Location:** Madison, WI\n- **School:** UW-Madison\n"
    )
    out = upsert_fact(content, "Location", "Columbus, OH", confirmed_on=TODAY)
    assert out.count("**Location:**") == 1
    assert "Columbus, OH" in out
    assert "Some note I wrote myself." in out
    assert "**School:** UW-Madison" in out


def test_upsert_fact_creates_the_file_body_when_absent():
    out = upsert_fact("", "Location", "Columbus, OH", confirmed_on=TODAY)
    assert "# Facts" in out
    assert parse_facts(out)["Location"].startswith("Columbus, OH")

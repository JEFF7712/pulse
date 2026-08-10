import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from pulse.domain.events import Event
from pulse.mcp.context import open_pulse_context
from pulse.mcp.server import (
    pulse_change_surface,
    pulse_pattern_list,
    pulse_pattern_read,
    pulse_pattern_set_status,
    pulse_pattern_upsert,
)


def _visit(i, domain, when):
    return Event(
        id=f"browser:{domain}:{i}",
        timestamp=when,
        source="browser",
        event_type="browsing.visit",
        data={"url": f"https://{domain}/p{i}", "title": "page"},
        metadata={},
    )


def _ctx(pulse_ctx):
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=pulse_ctx))


def _run(tmp_path: Path, body):
    async def _inner():
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as pulse_ctx:
            return await body(pulse_ctx)

    return asyncio.run(_inner())


def test_upsert_then_list_and_read(tmp_path: Path) -> None:
    async def body(pulse_ctx):
        ctx = _ctx(pulse_ctx)
        created = await pulse_pattern_upsert(
            slug="credit-transfer",
            title="Credit Transfer Underway",
            observation="Parchment transcript ordering alongside Moraine Valley self-service.",
            evidence=[
                "38 visits to parchment.com",
                "9 visits to self-serv.morainevalley.edu",
            ],
            confidence=0.6,
            ctx=ctx,
        )
        assert "Created" in created

        listed = json.loads(await pulse_pattern_list(ctx=ctx))
        assert len(listed) == 1
        assert listed[0]["slug"] == "credit-transfer"
        assert listed[0]["evidence_count"] == 2

        full = await pulse_pattern_read("credit-transfer", ctx=ctx)
        assert "Credit Transfer Underway" in full
        assert "parchment.com" in full

    _run(tmp_path, body)


def test_duplicate_proposal_is_rejected(tmp_path: Path) -> None:
    """A finding already on file is not a discovery."""

    async def body(pulse_ctx):
        ctx = _ctx(pulse_ctx)
        await pulse_pattern_upsert(
            slug="gpu-research",
            title="GPU Hardware Research",
            observation="Repeated visits to NVIDIA RTX PRO 6000 Blackwell workstation pages.",
            evidence=["2 visits to nvidia.com"],
            ctx=ctx,
        )
        again = await pulse_pattern_upsert(
            slug="gpu-hardware-research",  # different slug, same finding
            title="GPU Hardware Research",
            observation="Repeated visits to NVIDIA RTX PRO 6000 Blackwell workstation pages.",
            evidence=["2 visits to nvidia.com"],
            ctx=ctx,
        )
        assert "duplicate" in again.lower()
        assert "gpu-research" in again

        listed = json.loads(await pulse_pattern_list(ctx=ctx))
        assert len(listed) == 1

    _run(tmp_path, body)


def test_restating_an_existing_pattern_is_rejected(tmp_path: Path) -> None:
    """The failure that filled real vault files: the same claim re-appended."""

    async def body(pulse_ctx):
        ctx = _ctx(pulse_ctx)
        observation = (
            "Browsing fully normalized at 682 visits, effectively at baseline."
        )
        await pulse_pattern_upsert(
            slug="browsing-baseline",
            title="Browsing Baseline",
            observation=observation,
            evidence=["682 visits"],
            ctx=ctx,
        )
        repeat = await pulse_pattern_upsert(
            slug="browsing-baseline",
            title="Browsing Baseline",
            observation=observation,
            evidence=["682 visits again"],
            ctx=ctx,
        )
        assert "restatement" in repeat.lower()

    _run(tmp_path, body)


def test_a_genuine_update_to_the_same_slug_is_accepted(tmp_path: Path) -> None:
    async def body(pulse_ctx):
        ctx = _ctx(pulse_ctx)
        await pulse_pattern_upsert(
            slug="credit-transfer",
            title="Credit Transfer Underway",
            observation="Parchment transcript ordering appeared for the first time.",
            evidence=["38 visits to parchment.com"],
            ctx=ctx,
        )
        updated = await pulse_pattern_upsert(
            slug="credit-transfer",
            title="Credit Transfer Underway",
            observation=(
                "UW registrar and enrolment pages returned after six weeks dormant, "
                "and a new Outlook account appeared, indicating the transfer is "
                "progressing to enrolment rather than only transcript ordering."
            ),
            evidence=["6 visits to registrar.wisc.edu"],
            ctx=ctx,
        )
        assert "Updated" in updated

    _run(tmp_path, body)


def test_evidence_is_required(tmp_path: Path) -> None:
    async def body(pulse_ctx):
        result = await pulse_pattern_upsert(
            slug="vibes",
            title="A Feeling",
            observation="Something feels different lately.",
            evidence=[],
            ctx=_ctx(pulse_ctx),
        )
        assert "Rejected" in result

    _run(tmp_path, body)


def test_set_status_archives_a_faded_pattern(tmp_path: Path) -> None:
    """The supported way to close a pattern, instead of feeding it negative evidence."""

    async def body(pulse_ctx):
        ctx = _ctx(pulse_ctx)
        await pulse_pattern_upsert(
            slug="gpu-research",
            title="GPU Hardware Research",
            observation="Repeated visits to NVIDIA workstation pages.",
            evidence=["2 visits to nvidia.com"],
            ctx=ctx,
        )
        result = await pulse_pattern_set_status("gpu-research", "inactive", ctx=ctx)
        assert "inactive" in result

        missing = await pulse_pattern_set_status("no-such-slug", "inactive", ctx=ctx)
        assert "No pattern" in missing

    _run(tmp_path, body)


def test_change_surface_tool_returns_json(tmp_path: Path) -> None:
    async def body(pulse_ctx):
        base = datetime(2026, 6, 8, 9, tzinfo=UTC)
        events = [_visit(i, "github.com", base + timedelta(days=i)) for i in range(56)]
        win = datetime(2026, 8, 5, 9, tzinfo=UTC)
        events += [
            _visit(100 + i, "parchment.com", win + timedelta(hours=i)) for i in range(6)
        ]
        await pulse_ctx.events.upsert_events(events)

        payload = json.loads(
            await pulse_change_surface(window_end="2026-08-09", ctx=_ctx(pulse_ctx))
        )
        keys = {d["key"] for d in payload["entity_deltas"]}
        assert "parchment.com" in keys
        assert payload["window_start"] == "2026-08-03"

    _run(tmp_path, body)


def test_change_surface_rejects_a_bad_date(tmp_path: Path) -> None:
    async def body(pulse_ctx):
        result = await pulse_change_surface(
            window_end="not-a-date", ctx=_ctx(pulse_ctx)
        )
        assert "Invalid date" in result

    _run(tmp_path, body)

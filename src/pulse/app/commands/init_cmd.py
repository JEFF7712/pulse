"""`pulse init`: structure vault profile (optional LLM) + run initial connector pulls."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from pulse.app import cli_ui as ui
from pulse.app.commands.serve import quiet_noisy_loggers
from pulse.app.config_loader import load_config
from pulse.llm.anthropic_errors import user_message_for_anthropic_exception


_PROFILE_STRUCTURE_MODEL = "claude-haiku-4-5-20251001"

_PROFILE_STRUCTURE_SYSTEM = """You format free-form text into a concise Obsidian markdown profile for Pulse, an app that analyzes the user's email, calendar, music, and browsing history.

Output ONLY the markdown document. No surrounding code fences, no preamble or explanation.

Use this shape when the user's text supports it (omit a **field** line or entire section if unknown):

# User Profile

**Name:** ...
**Occupation:** ...
**Interests:** ...

## Discovery goals

What patterns or themes they want Pulse to surface.

## Additional context

Other facts useful for personalization.

Rules:
- Preserve specifics from the user's text; do not invent biographical facts they did not imply.
- If the input is sparse, keep the file short rather than padding with guesses."""


# Shown during interactive `pulse init` so users can copy it into another chat product.
_LLM_ASSISTANT_EXPORT_PROMPT = """I'm setting up Pulse, a self-hosted tool that pulls together my email, calendar, music, browsing, and similar sources into one place. I need a factual baseline about me so Pulse can make sense of that data (who people are, what I work on, what matters in my life).

From your stored memories and what you've learned about me, export only real-world facts: who I am, what I do, and what I'm involved in. Preserve my wording when you're quoting something I said about myself.

Do not include rules about how you (the assistant) should write, format, reply, or behave — no "always/never" chat instructions, tone preferences for AI, or similar. Skip generic LLM meta-preferences entirely.

## Categories (output in this order):

1. **Identity**: Name (or how I refer to myself), age or life stage if known, where I live or work from, timezone if known, languages, education, family and important relationships, hobbies and interests.

2. **Work**: Current job or role, employer or freelance focus, past roles worth knowing, industries and skill areas that describe what I actually do.

3. **Projects**: Things I've built, lead, or seriously committed to — one entry per project: what it is, status, and any decisions or context that matter. Start each entry with the project name or a short label.

4. **Life context**: Anything else factual that helps interpret my calendar, mail, or activity (e.g. recurring commitments, key people or orgs, travel patterns, side responsibilities). Keep it concrete, not wishlists.

## Format:

Use section headers for each category. Within each category, one fact per line, oldest first when you have a sense of time. Use:

[YYYY-MM-DD] - Fact here.

If no date is known, use [unknown].

## Output:

- Wrap the entire export in a single code block for easy copying.
- After the code block, say whether this is everything you have or if more factual detail might exist."""

# Line the user types alone to finish pasting (TTY); avoids ``stdin.read()`` waiting for EOF after Enter.
_PROFILE_PASTE_END_SENTINEL = "---END---"


def _resolve_current_day(config) -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(config.timezone)).date()


def _print_llm_assistant_import_hint() -> None:
    ui.say("")
    ui.say(
        "[accent]Import from another AI[/] [muted](optional)[/]\n"
        "[muted]Copy only the plain text between the rules below — no box borders. "
        "Paste it into ChatGPT, Claude, Gemini, or similar. "
        "Then paste the reply in the terminal as instructed.[/]"
    )
    ui.muted_line("─" * 76)
    ui.console.print(
        _LLM_ASSISTANT_EXPORT_PROMPT, markup=False, highlight=False, end=""
    )
    if not _LLM_ASSISTANT_EXPORT_PROMPT.endswith("\n"):
        ui.console.print()
    ui.muted_line("─" * 76)


def _read_multiline_profile_from_tty() -> str:
    """Read pasted profile until a sentinel line or EOF (``stdin.read()`` never ends on TTY after one Enter)."""
    ui.muted_line(
        f"When finished pasting, type [bold]{_PROFILE_PASTE_END_SENTINEL}[/] on its own line and press Enter. "
        "Or use Ctrl-D (macOS/Linux) or Ctrl-Z then Enter (Windows) on a new line. "
        "Outer ``` fences are stripped automatically."
    )
    lines: list[str] = []
    while True:
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            ui.warning("Cancelled.")
            return ""
        if not line:
            break
        if line.rstrip("\r\n") == _PROFILE_PASTE_END_SENTINEL:
            break
        lines.append(line)
    return "".join(lines).strip()


def _read_profile_raw_text(
    *, profile_file: Path | None, profile_text: str | None
) -> str:
    """Load free-form profile source: explicit args, then stdin if piped, else interactive paste."""
    if profile_text is not None:
        return profile_text.strip()
    if profile_file is not None:
        path = profile_file.expanduser()
        if not path.is_file():
            ui.error(f"Profile file not found: {path}")
            sys.exit(1)
        return path.read_text(encoding="utf-8").strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    _print_llm_assistant_import_hint()
    ui.say(
        "\n[accent]Paste[/] your profile [muted](exported facts or free-form: who you are, work, projects, context for your data).[/]"
    )
    return _read_multiline_profile_from_tty()


def _profile_markdown_without_llm(raw: str) -> str:
    """Wrap raw text when no LLM is configured."""
    return f"# User Profile\n\n## Self description\n\n{raw.strip()}\n"


def _strip_markdown_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


async def _structure_profile_markdown(raw, llm) -> str:
    structured = await llm.complete(
        f"The user wrote the following about themselves. Turn it into the vault profile markdown.\n\n---\n{raw}\n---",
        system_prompt=_PROFILE_STRUCTURE_SYSTEM,
        model=_PROFILE_STRUCTURE_MODEL,
    )
    return _strip_markdown_fences(structured)


def init_profile(
    *,
    profile_file: Path | None = None,
    profile_text: str | None = None,
    config_dir: Path | None = None,
) -> None:
    from pulse.analysis.vault_memory import VaultMemory
    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry
    from pulse.jobs.runners import run_aggregation_job
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema
    from pulse.store.sync_state import SyncStateRepository

    quiet_noisy_loggers()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config(config_dir=config_dir)

    from pulse.vault.onboarding import ensure_vault_onboarding

    ensure_vault_onboarding(config.vault_path)

    vault = VaultMemory(config.vault_path)

    ui.rule("pulse init")

    # --- Step 1: User profile ---
    profile_path = Path(config.vault_path) / "04-Config" / "profile.md"
    if profile_path.exists():
        ui.warning(f"Profile already exists at [bold]{profile_path}[/]")
        overwrite = input("Overwrite? [y/N] ").strip().lower()
        if overwrite != "y":
            ui.muted_line("Keeping existing profile.")
        else:
            _collect_profile(
                vault,
                config,
                profile_file=profile_file,
                profile_text=profile_text,
            )
    else:
        _collect_profile(
            vault,
            config,
            profile_file=profile_file,
            profile_text=profile_text,
        )

    # --- Step 2: Initial data pull ---
    ui.step("Initial data pull")
    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)

    registry = ConnectorRegistry()
    register_all(registry, config)
    asyncio.run(registry.build_active_connectors(config))

    active = registry.get_pull_connectors()
    if not active:
        ui.warning(
            "No active connectors. Run [cmd]pulse configure[/] → Connectors to enable sources."
        )
    else:

        async def _run_pulls():
            async with connect_db(config.database_path) as db:
                await bootstrap_schema(db)
                event_repo = EventRepository(db)
                sync_state = SyncStateRepository(db)
                total_new = 0

                for connector, _cc in active:
                    source = connector.get_source_name()
                    ui.inline(f"  [bullet]●[/] [bold]{source}[/] … ", end="")
                    try:
                        events = await connector.pull(since=None)
                        if events:
                            new_count = await event_repo.upsert_events(events)
                            if hasattr(connector, "get_sync_timestamp"):
                                ts = connector.get_sync_timestamp()
                            else:
                                ts = max(e.timestamp for e in events)
                            await sync_state.save(source, ts.isoformat())
                            total_new += new_count
                            ui.say(f"[ok]{new_count}[/] new events")
                        else:
                            ui.say("[muted]0 events[/]")
                    except Exception as e:
                        ui.say(f"[err]ERROR:[/] {e}")

                return total_new

        total = asyncio.run(_run_pulls())
        ui.kv_line("Total new events", str(total))

    # --- Step 3: Aggregate ---
    ui.step("Aggregating stats")
    today = _resolve_current_day(config)
    result = asyncio.run(
        run_aggregation_job(
            day=today,
            database_path=config.database_path,
            timezone=config.timezone,
        )
    )
    ui.muted_line(result.detail)

    ui.success(
        "Pulse initialized! Run [cmd]pulse run[/] to start the server and scheduler."
    )


def _collect_profile(
    vault,
    config,
    *,
    profile_file: Path | None = None,
    profile_text: str | None = None,
) -> None:
    from pulse.llm.factory import create_providers_from_config

    ui.step("User profile")
    ui.muted_line(
        "Describe yourself in free form, or paste a factual export from another chat; "
        "Pulse will structure it for your vault when an Anthropic model is configured."
    )

    raw = _read_profile_raw_text(profile_file=profile_file, profile_text=profile_text)
    raw = _strip_markdown_fences(raw)
    if not raw:
        ui.warning("No profile text provided; skipping profile write.")
        return

    from pulse.llm.anthropic import AnthropicProvider

    summ_llm, disc_llm = create_providers_from_config(config)
    anthropic_llm = next(
        (x for x in (summ_llm, disc_llm) if isinstance(x, AnthropicProvider)), None
    )
    if anthropic_llm is not None:
        ui.say("[accent]Structuring profile[/] with Anthropic…")
        try:
            profile_content = asyncio.run(
                _structure_profile_markdown(raw, anthropic_llm)
            )
        except Exception as e:
            um = user_message_for_anthropic_exception(e)
            if um:
                ui.warning(f"{um} Saving raw text under a single section instead.")
            else:
                ui.warning(
                    f"LLM error ({e}); saving raw text under a single section instead."
                )
            profile_content = _profile_markdown_without_llm(raw)
    else:
        ui.muted_line(
            "No Anthropic LLM in [llm.summarization] / [llm.discovery]; "
            "saving your text under “Self description” (no LLM pass)."
        )
        profile_content = _profile_markdown_without_llm(raw)

    vault.write_config_file("profile.md", profile_content)
    ui.success("Profile saved.")

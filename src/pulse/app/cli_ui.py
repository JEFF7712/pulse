"""Rich-based styling for the Pulse CLI."""

from __future__ import annotations

from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Matches site/index.html :root — accent is the hero green; cream/dim echo the page.
SITE_ACCENT = "#4ade80"
SITE_ACCENT_SOFT = "#86efac"
SITE_CREAM = "#c4bfb8"
SITE_MUTED_FG = "#a8a29e"

_ACCENT = SITE_ACCENT
_ACCENT_SOFT = SITE_ACCENT_SOFT
_CREAM = SITE_CREAM
_DIM_FG = SITE_MUTED_FG

_THEME = Theme(
    {
        "pulse": f"bold {_ACCENT}",
        "pulse.dim": f"dim {_ACCENT}",
        "accent": f"bold {_ACCENT}",
        "accent.soft": _ACCENT_SOFT,
        "cream": _CREAM,
        "ok": f"bold {_ACCENT}",
        "warn": "bold #fbbf24",
        "err": "bold #f87171",
        "muted": f"dim {_DIM_FG}",
        "label": _ACCENT_SOFT,
        "value": "default",
        "bullet": _ACCENT,
        "cmd": f"bold {_ACCENT}",
    }
)

console = Console(theme=_THEME, highlight=False)


def say(message: str | Panel | Table, **kwargs: Any) -> None:
    """Print Rich markup or renderable."""
    console.print(message, **kwargs)


def inline(message: str, *, end: str = "") -> None:
    """Print without trailing newline (e.g. progress)."""
    console.print(message, end=end)


def rule(title: str) -> None:
    console.rule(f"[accent]{title}[/]", style=_ACCENT)


def step(title: str) -> None:
    console.print(f"\n[bullet]▸[/] [bold]{title}[/]")


def success(msg: str) -> None:
    console.print(f"[ok]✓[/] {msg}")


def warning(msg: str) -> None:
    console.print(f"[warn]⚠[/] {msg}")


def error(msg: str) -> None:
    console.print(f"[err]✗[/] {msg}")


def muted_line(msg: str) -> None:
    console.print(f"[muted]{msg}[/]")


def kv_line(label: str, value: str, *, indent: int = 2) -> None:
    pad = " " * indent
    console.print(f"{pad}[label]{label}:[/] [value]{value}[/]")


def banner_tagline() -> None:
    """Compact brand line for major flows (matches site hero accent + cream text)."""
    t = Text()
    t.append("● ", style=f"bold {_ACCENT}")
    t.append("PULSE", style=f"bold {_ACCENT}")
    t.append(" ", style="")
    t.append("CLI", style=_CREAM)
    t.append("  ", style="")
    t.append("personal intelligence, self-hosted", style=f"dim {_DIM_FG}")
    console.print(
        Panel.fit(
            t,
            border_style=_ACCENT,
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def onboard_phase(name: str) -> None:
    console.print()
    console.print(f"[bullet]▶[/] [accent]{name}[/] [muted]· continuing onboard[/]")


def startup_panel(
    host: str,
    port: int,
    pull_names: str,
    push_names: str,
    vault: str,
    database: str,
) -> None:
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    table.add_column("Key", style="label")
    table.add_column("Value", style="value")
    table.add_row("Listen", f"[bold]{host}:{port}[/]")
    table.add_row("Pull", pull_names or "[muted]none[/]")
    table.add_row("Push", push_names or "[muted]none[/]")
    table.add_row("Vault", vault)
    table.add_row("Database", database)
    console.print(
        Panel(
            table,
            title="[pulse]Starting Pulse[/]",
            border_style=_ACCENT,
            box=box.ROUNDED,
        )
    )


def status_tables(
    database: str,
    total: int,
    time_range: str,
    event_rows: list[tuple[Any, ...]],
    sync_rows: list[tuple[Any, ...]],
) -> None:
    console.print(Panel(f"[label]Database[/]  {database}", border_style=_ACCENT, box=box.ROUNDED))
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column(style="label")
    summary.add_column(style="value")
    summary.add_row("Total events", f"[bold]{total:,}[/]")
    summary.add_row("Time range", time_range)
    console.print(summary)

    if event_rows:
        et = Table(title="[accent]Events by source[/]", box=box.ROUNDED, header_style=f"bold {_ACCENT}")
        et.add_column("Source", style=f"bold {_ACCENT_SOFT}")
        et.add_column("Type", style="default")
        et.add_column("Count", justify="right", style=f"bold {_ACCENT}")
        for source, etype, count in event_rows:
            et.add_row(str(source), str(etype), f"{count:,}")
        console.print(et)

    if sync_rows:
        st = Table(title="[accent]Sync cursors[/]", box=box.ROUNDED, header_style=f"bold {_ACCENT}")
        st.add_column("Source", style=f"bold {_ACCENT_SOFT}")
        st.add_column("Cursor", style="default", max_width=36, overflow="ellipsis")
        st.add_column("Updated", style="muted")
        for source, cursor, updated_at in sync_rows:
            st.add_row(str(source), str(cursor)[:36], str(updated_at))
        console.print(st)


def logs_table(rows: list[tuple[str, str, str, str]]) -> None:
    """Rows: (ts_short, source, etype, detail)."""
    t = Table(title="[accent]Recent events[/]", box=box.ROUNDED, header_style=f"bold {_ACCENT}")
    t.add_column("Time", style=f"bold {_ACCENT_SOFT}", no_wrap=True)
    t.add_column("Source", style="bold")
    t.add_column("Type", style="muted")
    t.add_column("Detail", style="default")
    for ts_short, source, etype, detail in rows:
        t.add_row(ts_short, source, etype, detail)
    console.print(t)


def insights_panel(rows: list[dict[str, Any]]) -> None:
    for i in rows:
        conf = i["confidence"]
        status = i["status"]
        title = f"[accent.soft]{status}[/]  [bold]{i['title']}[/]"
        body = (
            f"[muted]confidence[/] {conf}  ·  [muted]seen[/] {i['first_seen']} → {i['last_seen']}\n"
            f"[muted]vault[/] {i['vault_path']}"
        )
        console.print(Panel(body, title=title, border_style=_ACCENT, box=box.ROUNDED))
        console.print()

"""``pulse configure → Core settings`` hub and its sequential-wizard counterpart."""

from __future__ import annotations

import sys
from pathlib import Path

from pulse.app import cli_ui as ui

from .constants import _CONFIGURE_CORE_FIELDS, _CORE_SETTING_DEFS
from .env_prompts import _prompt_env_field
from .toml_io import _save_pulse_settings

def _configure_core_only(working_env: dict[str, str]) -> None:
    ui.step("Core settings")
    for key, label, default, is_secret in _CONFIGURE_CORE_FIELDS:
        current = working_env.get(key, "") or default
        working_env[key] = _prompt_env_field(key, label, current, is_secret)


def _core_setting_ready(setting_id: str, env: dict[str, str]) -> bool:
    row = next(r for r in _CORE_SETTING_DEFS if r[0] == setting_id)
    _sid, _label, _emoji, fields = row
    return all((env.get(f[0]) or "").strip() for f in fields)


def _core_setting_submenu_row_label(
    setting_id: str, short: str, emoji: str, working_env: dict[str, str]
) -> str:
    circle = "●" if _core_setting_ready(setting_id, working_env) else "○"
    return f"{circle} {emoji} {short}"


def _pick_core_setting_submenu(
    working_env: dict[str, str],
    *,
    exit_label: str = "← Back",
) -> str | None:
    rows: list[tuple[str, str]] = []
    for sid, short, emoji, _fields in _CORE_SETTING_DEFS:
        disp = _core_setting_submenu_row_label(sid, short, emoji, working_env)
        rows.append((sid, disp))
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Pick a core setting to configure[/]")
        for i, (_, disp) in enumerate(rows, start=1):
            ui.muted_line(f"  {i}) {disp}")
        raw = input(f"Choose [1-{len(rows)}]: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            return "__invalid__"
        if idx < 1 or idx > len(rows):
            return "__invalid__"
        return rows[idx - 1][0]

    import questionary
    from questionary import Style

    style = Style(
        [
            ("qmark", "fg:default"),
            ("question", "bold"),
            ("answer", "fg:cyan bold"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
        ]
    )
    chosen = questionary.select(
        "Core settings",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_core_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_legend = False
    while True:
        if not showed_legend:
            ui.muted_line(
                "● = value set in pulse.toml · ○ = empty · "
                "Database file, Obsidian vault, and timezone for scheduling."
            )
            showed_legend = True
        pick = _pick_core_setting_submenu(
            working_env, exit_label=submenu_exit_label
        )
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        row = next(r for r in _CORE_SETTING_DEFS if r[0] == pick)
        _sid, label, _emoji, fields = row
        ui.step(label)
        ui.muted_line("Values for this setting (saved in pulse.toml; leave blank to skip).")
        for key, fld_label, default, is_secret in fields:
            current = working_env.get(key, "") or default
            working_env[key] = _prompt_env_field(key, fld_label, current, is_secret)
        _save_pulse_settings(toml_path, working_env)
        ui.success(f"Saved {toml_path}")


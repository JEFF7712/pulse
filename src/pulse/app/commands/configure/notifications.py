"""``pulse configure → Notifications`` hub (Telegram, SMTP, webhooks, …)."""

from __future__ import annotations

import sys
from pathlib import Path

from pulse.app import cli_ui as ui

from .constants import _CONFIGURE_NOTIFICATION_FIELDS, _NOTIFICATION_PROVIDER_DEFS
from .env_prompts import _prompt_env_field_list
from .toml_io import _save_pulse_settings


def _notification_provider_ready(provider_id: str, env: dict[str, str]) -> bool:
    """● row hint: outbound channel ready or corrections secret set."""

    def g(key: str) -> str:
        return (env.get(key) or "").strip()

    if provider_id == "telegram":
        return bool(g("PULSE_TELEGRAM_BOT_TOKEN") and g("PULSE_TELEGRAM_CHAT_ID"))
    if provider_id == "ntfy":
        return bool(g("PULSE_NTFY_TOPIC"))
    if provider_id == "webhook":
        return bool(g("PULSE_NOTIFICATION_WEBHOOK_URL"))
    if provider_id == "discord":
        return bool(g("PULSE_DISCORD_WEBHOOK_URL"))
    if provider_id == "slack":
        return bool(g("PULSE_SLACK_WEBHOOK_URL"))
    if provider_id == "pushover":
        return bool(g("PULSE_PUSHOVER_USER_KEY") and g("PULSE_PUSHOVER_API_TOKEN"))
    if provider_id == "gotify":
        return bool(g("PULSE_GOTIFY_URL") and g("PULSE_GOTIFY_APP_TOKEN"))
    if provider_id == "smtp":
        if not (g("PULSE_SMTP_HOST") and g("PULSE_SMTP_FROM") and g("PULSE_SMTP_TO")):
            return False
        to_list = [x.strip() for x in g("PULSE_SMTP_TO").split(",") if x.strip()]
        return bool(to_list)
    if provider_id == "corrections":
        return bool(g("PULSE_CORRECTIONS_WEBHOOK_SECRET"))
    return False


def _notification_submenu_row_label(
    provider_id: str, short: str, emoji: str, working_env: dict[str, str]
) -> str:
    circle = "●" if _notification_provider_ready(provider_id, working_env) else "○"
    return f"{circle} {emoji} {short}"


def _pick_notification_provider_submenu(
    working_env: dict[str, str],
    *,
    exit_label: str = "← Back",
) -> str | None:
    rows: list[tuple[str, str]] = []
    for pid, short, emoji, _fields in _NOTIFICATION_PROVIDER_DEFS:
        disp = _notification_submenu_row_label(pid, short, emoji, working_env)
        rows.append((pid, disp))
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Pick a notification provider to configure[/]")
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
        "Notification providers",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_notifications_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_legend = False
    while True:
        if not showed_legend:
            ui.muted_line(
                "● = required values set in pulse.toml for that channel · ○ = incomplete · "
                "Several channels can be active; notifications broadcast to all that are ready."
            )
            showed_legend = True
        pick = _pick_notification_provider_submenu(
            working_env, exit_label=submenu_exit_label
        )
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        row = next(r for r in _NOTIFICATION_PROVIDER_DEFS if r[0] == pick)
        _pid, label, _emoji, fields = row
        ui.step(label)
        ui.muted_line(
            "Values for this channel (saved in pulse.toml; leave blank to skip)."
        )
        _prompt_env_field_list(
            fields,
            working_env,
            offer_bulk_keep=toml_path.exists(),
            section_label=f"{label} notifications",
        )
        _save_pulse_settings(toml_path, working_env)
        ui.success(f"Saved {toml_path}")


def _configure_notifications_only(working_env: dict[str, str], toml_path: Path) -> None:
    ui.step("Notifications")
    ui.muted_line("Telegram, webhooks, and SMTP. Leave blank to skip.")
    _prompt_env_field_list(
        _CONFIGURE_NOTIFICATION_FIELDS,
        working_env,
        offer_bulk_keep=toml_path.exists(),
        section_label="notification settings",
    )

"""Connector hub: per-source credentials, pulse.toml block, and post-save OAuth prompts."""

from __future__ import annotations

import sys
from pathlib import Path

from pulse.app import cli_ui as ui
from pulse.app.commands.auth import (
    auth_github,
    auth_gitlab,
    auth_google,
    auth_microsoft,
    auth_oura,
    auth_plaid,
    auth_spotify,
)

from .constants import (
    _CONNECTOR_DEFS,
    _CONNECTOR_ENV_FIELDS,
    _CONNECTOR_MENU_EMOJI,
    _CONNECTOR_MENU_SHORT,
)
from .env_prompts import _prompt_env_field_list
from .toml_io import (
    _connector_section_enabled,
    _load_connectors_state,
    _save_pulse_settings,
    _write_connectors_state,
)

def _connector_prereqs_met(name: str, env: dict[str, str]) -> bool:
    g = (env.get("PULSE_GOOGLE_CLIENT_ID") or "").strip() and (
        env.get("PULSE_GOOGLE_CLIENT_SECRET") or ""
    ).strip()
    if name in ("gmail", "calendar", "youtube"):
        return bool(g)
    if name == "spotify":
        return bool(
            (env.get("PULSE_SPOTIFY_CLIENT_ID") or "").strip()
            and (env.get("PULSE_SPOTIFY_CLIENT_SECRET") or "").strip()
        )
    if name in ("microsoft_mail", "microsoft_calendar"):
        return bool(
            (env.get("PULSE_MICROSOFT_CLIENT_ID") or "").strip()
            and (env.get("PULSE_MICROSOFT_CLIENT_SECRET") or "").strip()
        )
    if name == "github":
        return bool(
            (env.get("PULSE_GITHUB_CLIENT_ID") or "").strip()
            and (env.get("PULSE_GITHUB_CLIENT_SECRET") or "").strip()
        )
    if name == "gitlab":
        return bool(
            (env.get("PULSE_GITLAB_TOKEN") or "").strip()
            or (
                (env.get("PULSE_GITLAB_CLIENT_ID") or "").strip()
                and (env.get("PULSE_GITLAB_CLIENT_SECRET") or "").strip()
            )
        )
    if name == "plaid":
        return bool(
            (env.get("PULSE_PLAID_CLIENT_ID") or "").strip()
            and (env.get("PULSE_PLAID_SECRET") or "").strip()
            and (env.get("PULSE_PLAID_ENV") or "").strip()
        )
    if name == "oura":
        return bool(
            (env.get("PULSE_OURA_PERSONAL_ACCESS_TOKEN") or "").strip()
            or (
                (env.get("PULSE_OURA_CLIENT_ID") or "").strip()
                and (env.get("PULSE_OURA_CLIENT_SECRET") or "").strip()
            )
        )
    if name == "notion":
        return bool((env.get("PULSE_NOTION_TOKEN") or "").strip())
    if name == "linear":
        return bool((env.get("PULSE_LINEAR_API_KEY") or "").strip())
    return True


def _prompt_enable_connector(
    label: str,
    *,
    creds_ok: bool,
    was_enabled: bool,
) -> bool:
    if was_enabled and not creds_ok:
        ui.muted_line(
            "  (Note: connector was enabled but matching credentials look missing.)"
        )
    # First-time / currently off: opt in (default off) even if pulse.toml already has creds.
    if not was_enabled:
        yn = input(f"  Enable {label}? [y/N] ").strip().lower()
        return yn in ("y", "yes")
    if creds_ok:
        yn = input(f"  Enable {label}? [Y/n] ").strip().lower()
        return yn not in ("n", "no")
    yn = input(f"  Keep {label} enabled (creds look missing)? [y/N] ").strip().lower()
    return yn in ("y", "yes")


def _prompt_one_connector_toml_section(
    name: str,
    default_interval: str,
    label: str,
    existing: dict,
    working_env: dict[str, str],
) -> dict:
    was_enabled = existing.get("enabled", True) if existing else False
    if not isinstance(was_enabled, bool):
        was_enabled = bool(was_enabled)
    interval = existing.get("poll_interval", default_interval)
    if not isinstance(interval, str):
        interval = str(interval)
    creds_ok = _connector_prereqs_met(name, working_env)

    if existing:
        status = "enabled" if was_enabled else "disabled"
        answer = (
            input(f"  {label}: {status}, poll {interval} — keep? [Y/n] ").strip().lower()
        )
        if answer in ("n", "no"):
            enabled = _prompt_enable_connector(
                label, creds_ok=creds_ok, was_enabled=was_enabled
            )
            new_interval = input(f"    Poll interval [{interval}]: ").strip()
            if new_interval:
                interval = new_interval
        else:
            enabled = was_enabled
            if enabled and not creds_ok:
                ui.muted_line(
                    "  (Note: still enabled, but matching credentials look missing.)"
                )
    else:
        enabled = _prompt_enable_connector(
            label, creds_ok=creds_ok, was_enabled=False
        )
        if enabled:
            new_interval = input(f"    Poll interval [{interval}]: ").strip()
            if new_interval:
                interval = new_interval

    enabled = bool(enabled)
    section: dict = {"enabled": enabled, "poll_interval": interval}

    if name == "spotify":
        supp = existing.get("supplementary_interval", "6h")
        section["supplementary_interval"] = str(supp) if supp is not None else "6h"

    if name == "browser":
        browser_type = existing.get("browser", "chrome")
        if not isinstance(browser_type, str):
            browser_type = str(browser_type)
        if existing:
            answer = (
                input(f"    Browser: {browser_type} — keep? [Y/n] ").strip().lower()
            )
            if answer in ("n", "no"):
                choice = input("    Browser type (chrome/firefox): ").strip()
                browser_type = choice if choice else browser_type
        else:
            choice = input(f"    Browser type [{browser_type}]: ").strip()
            browser_type = choice if choice else browser_type
        section["browser"] = browser_type

        db_path_existing = ""
        if existing:
            raw_db = existing.get("db_path")
            if isinstance(raw_db, str):
                db_path_existing = raw_db.strip()
        db_path_val = db_path_existing
        if enabled:
            if db_path_existing:
                answer = (
                    input(
                        f"    Browser history SQLite path [{db_path_existing}] — keep? [Y/n] "
                    )
                    .strip()
                    .lower()
                )
                if answer in ("n", "no"):
                    db_path_val = input(
                        "    Path to browser history DB (blank = default for OS): "
                    ).strip()
            else:
                db_path_val = input(
                    "    Path to browser history SQLite (optional; blank = default): "
                ).strip()
        if enabled and db_path_val:
            section["db_path"] = db_path_val

    if name == "microsoft_calendar":
        cal_id = (existing.get("calendar_id") if existing else None) or "primary"
        if not isinstance(cal_id, str):
            cal_id = str(cal_id)
        if enabled:
            if existing:
                answer = (
                    input(f"    Calendar ID [{cal_id}] — keep? [Y/n] ").strip().lower()
                )
                if answer in ("n", "no"):
                    cal_id = (
                        input(
                            "    Graph calendar id (primary or calendar UUID): "
                        ).strip()
                        or cal_id
                    )
            else:
                cal_id = (
                    input("    Graph calendar id [primary]: ").strip() or "primary"
                )
        section["calendar_id"] = cal_id

    if name == "gitlab":
        base_url = (
            (existing.get("gitlab_base_url") if existing else None)
            or "https://gitlab.com"
        )
        if not isinstance(base_url, str):
            base_url = str(base_url)
        if enabled:
            if existing:
                answer = (
                    input(f"    GitLab base URL [{base_url}] — keep? [Y/n] ")
                    .strip()
                    .lower()
                )
                if answer in ("n", "no"):
                    base_url = input("    GitLab base URL: ").strip() or base_url
            else:
                base_url = (
                    input("    GitLab base URL [https://gitlab.com]: ").strip()
                    or base_url
                )
        section["gitlab_base_url"] = base_url

    if name == "plaid":
        raw_existing = existing or {}
        omit = bool(
            raw_existing.get("omit_amounts_in_summary")
            or raw_existing.get("omit_amounts_in_digest", False)
        )
        if enabled:
            yn = (
                input("    Omit transaction amounts from finance summaries? [y/N] ")
                .strip()
                .lower()
            )
            if yn in ("y", "yes"):
                omit = True
        section["omit_amounts_in_summary"] = omit

    if name == "notion":
        prev_dbs: list = list(existing.get("database_ids", [])) if existing else []
        if isinstance(prev_dbs, str):
            prev_dbs = [prev_dbs] if prev_dbs else []
        if enabled:
            if prev_dbs:
                preview = ", ".join(str(x) for x in prev_dbs[:2])
                if len(prev_dbs) > 2:
                    preview += "…"
                keep = (
                    input(f"    Keep Notion database_ids ({preview})? [Y/n] ")
                    .strip()
                    .lower()
                )
                if keep in ("n", "no"):
                    prev_dbs = []
            if not prev_dbs:
                line = input(
                    "    Optional database UUIDs (comma-separated) to query in addition "
                    "to workspace search; leave empty for search only: "
                ).strip()
                prev_dbs = [u.strip() for u in line.split(",") if u.strip()]
        section["database_ids"] = prev_dbs

    if name == "feeds":
        prev_urls: list = list(existing.get("urls", [])) if existing else []
        if isinstance(prev_urls, str):
            prev_urls = [prev_urls] if prev_urls else []
        if enabled:
            if prev_urls:
                preview = ", ".join(prev_urls[:2]) + (
                    "…" if len(prev_urls) > 2 else ""
                )
                keep = (
                    input(f"    Keep feed URLs ({preview})? [Y/n] ").strip().lower()
                )
                if keep in ("n", "no"):
                    prev_urls = []
            if not prev_urls:
                line = input(
                    "    Feed URLs (comma-separated RSS/Atom URLs; leave empty to add later): "
                ).strip()
                prev_urls = [u.strip() for u in line.split(",") if u.strip()]
        section["urls"] = prev_urls

    return section


def _configure_connectors_toml(
    working_env: dict[str, str],
    toml_path: Path,
) -> list[str]:
    state = _load_connectors_state(toml_path)
    for name, default_interval, label in _CONNECTOR_DEFS:
        existing = state.get(name, {})
        state[name] = _prompt_one_connector_toml_section(
            name, default_interval, label, existing, working_env
        )
    _write_connectors_state(state, toml_path)
    return [n for n, _, _ in _CONNECTOR_DEFS if _connector_section_enabled(state[n])]


def _connector_submenu_row_label(
    name: str,
    default_interval: str,
    working_env: dict[str, str],
    state: dict[str, dict],
) -> str:
    """Compact row: ●/○ (pulse.toml enabled) · emoji · short · ✓/✗ only when ● · poll."""
    creds = _connector_prereqs_met(name, working_env)
    st = state.get(name, {})
    en = _connector_section_enabled(st)
    poll = st.get("poll_interval", default_interval)
    if not isinstance(poll, str):
        poll = str(poll)
    circle = "●" if en else "○"
    emoji = _CONNECTOR_MENU_EMOJI[name]
    short = _CONNECTOR_MENU_SHORT[name]
    cred_mark = f" {'✓' if creds else '✗'}" if en else ""
    return f"{circle} {emoji} {short}{cred_mark} {poll}"


def _pick_connector_submenu(
    working_env: dict[str, str],
    state: dict[str, dict],
    *,
    exit_label: str = "← Back",
) -> str | None:
    rows: list[tuple[str, str]] = []
    for name, default_interval, _label in _CONNECTOR_DEFS:
        disp = _connector_submenu_row_label(
            name, default_interval, working_env, state
        )
        rows.append((name, disp))
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Pick a connector to configure[/]")
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
        "Connectors",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_connectors_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    offer_oauth: bool,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_connector_legend = False
    while True:
        state = _load_connectors_state(toml_path)
        if not showed_connector_legend:
            ui.muted_line(
                "● = enabled in pulse.toml · ○ = disabled · ✓/✗ = credential prereqs (only when ●). "
                "Pick a source to edit its credentials and block; when you save with ●, "
                "OAuth / Plaid Link / Oura run here if that source needs tokens."
            )
            showed_connector_legend = True
        pick = _pick_connector_submenu(
            working_env, state, exit_label=submenu_exit_label
        )
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        name = pick
        _triple = next(t for t in _CONNECTOR_DEFS if t[0] == name)
        _, default_interval, label = _triple
        ui.step(label)
        fields = _CONNECTOR_ENV_FIELDS.get(name, [])
        if fields:
            ui.muted_line("Credentials for this connector (saved in pulse.toml; leave blank to skip).")
            _prompt_env_field_list(
                fields,
                working_env,
                offer_bulk_keep=toml_path.exists(),
                section_label=f"{label} credentials",
            )
            _save_pulse_settings(toml_path, working_env)
            ui.success(f"Saved {toml_path}")
        state = _load_connectors_state(toml_path)
        existing = state.get(name, {})
        state[name] = _prompt_one_connector_toml_section(
            name, default_interval, label, existing, working_env
        )
        _write_connectors_state(state, toml_path)
        ui.success(f"Saved {toml_path}")
        enabled_now = [
            n for n, _, _ in _CONNECTOR_DEFS if _connector_section_enabled(state[n])
        ]
        ui.kv_line("Enabled connectors", ", ".join(enabled_now) or "none")
        if offer_oauth and _connector_section_enabled(state[name]):
            _configure_oauth_prompts(working_env, [name])


def _configure_oauth_prompts(
    env_values: dict[str, str], enabled_connectors: list[str]
) -> None:
    google_connectors = [
        c for c in enabled_connectors if c in ("gmail", "calendar", "youtube")
    ]
    has_google_creds = env_values.get("PULSE_GOOGLE_CLIENT_ID") and env_values.get(
        "PULSE_GOOGLE_CLIENT_SECRET"
    )
    has_spotify_creds = env_values.get("PULSE_SPOTIFY_CLIENT_ID") and env_values.get(
        "PULSE_SPOTIFY_CLIENT_SECRET"
    )

    data_dir = Path(env_values.get("PULSE_DATABASE_PATH", "data/pulse.db")).parent
    google_tokens = data_dir / "google_tokens.json"
    spotify_tokens = data_dir / "spotify_tokens.json"

    if google_connectors and has_google_creds:
        if google_tokens.exists():
            ui.muted_line(f"Google: already authorized ({google_tokens})")
            answer = input("  Re-authorize? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                auth_google()
        else:
            ui.step("Google authorization")
            ui.kv_line("Connectors", ", ".join(google_connectors))
            answer = input("  Run Google OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                auth_google()

    if "spotify" in enabled_connectors and has_spotify_creds:
        if spotify_tokens.exists():
            ui.muted_line(f"Spotify: already authorized ({spotify_tokens})")
            answer = input("  Re-authorize? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                auth_spotify()
        else:
            ui.step("Spotify authorization")
            answer = input("  Run Spotify OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                auth_spotify()

    ms_connectors = [
        c for c in enabled_connectors if c in ("microsoft_mail", "microsoft_calendar")
    ]
    has_ms_creds = env_values.get("PULSE_MICROSOFT_CLIENT_ID") and env_values.get(
        "PULSE_MICROSOFT_CLIENT_SECRET"
    )
    microsoft_tokens = data_dir / "microsoft_tokens.json"
    if ms_connectors and has_ms_creds:
        if microsoft_tokens.exists():
            ui.muted_line(f"Microsoft 365: already authorized ({microsoft_tokens})")
            answer = input("  Re-authorize? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                auth_microsoft()
        else:
            ui.step("Microsoft 365 authorization")
            ui.kv_line("Connectors", ", ".join(ms_connectors))
            answer = input("  Run Microsoft OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                auth_microsoft()

    gh_enabled = "github" in enabled_connectors
    has_gh = env_values.get("PULSE_GITHUB_CLIENT_ID") and env_values.get(
        "PULSE_GITHUB_CLIENT_SECRET"
    )
    github_tokens = data_dir / "github_tokens.json"
    if gh_enabled and has_gh:
        if github_tokens.exists():
            ui.muted_line(f"GitHub: already authorized ({github_tokens})")
            answer = input("  Re-authorize GitHub? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                auth_github()
        else:
            ui.step("GitHub authorization")
            answer = input("  Run GitHub OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                auth_github()

    gl_enabled = "gitlab" in enabled_connectors
    has_gl_oauth = env_values.get("PULSE_GITLAB_CLIENT_ID") and env_values.get(
        "PULSE_GITLAB_CLIENT_SECRET"
    )
    has_gl_pat = bool(env_values.get("PULSE_GITLAB_TOKEN"))
    gitlab_tokens = data_dir / "gitlab_tokens.json"
    if gl_enabled and has_gl_oauth and not has_gl_pat:
        if gitlab_tokens.exists():
            ui.muted_line(f"GitLab: already authorized ({gitlab_tokens})")
            answer = input("  Re-authorize GitLab? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                auth_gitlab()
        else:
            ui.step("GitLab authorization")
            answer = input("  Run GitLab OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                auth_gitlab()
    elif gl_enabled and has_gl_pat:
        ui.muted_line("GitLab: using PULSE_GITLAB_TOKEN — OAuth skipped.")

    plaid_enabled = "plaid" in enabled_connectors
    has_plaid = env_values.get("PULSE_PLAID_CLIENT_ID") and env_values.get(
        "PULSE_PLAID_SECRET"
    )
    plaid_tokens = data_dir / "plaid_tokens.json"
    if plaid_enabled and has_plaid:
        if plaid_tokens.exists():
            ui.muted_line(f"Plaid: already linked ({plaid_tokens})")
            answer = input("  Re-link Plaid? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                auth_plaid()
        else:
            ui.step("Plaid Link")
            answer = input("  Open Plaid Link now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                auth_plaid()

    oura_enabled = "oura" in enabled_connectors
    has_oura_oauth = env_values.get("PULSE_OURA_CLIENT_ID") and env_values.get(
        "PULSE_OURA_CLIENT_SECRET"
    )
    has_oura_pat = bool(env_values.get("PULSE_OURA_PERSONAL_ACCESS_TOKEN"))
    oura_tokens = data_dir / "oura_tokens.json"
    if oura_enabled and has_oura_oauth and not has_oura_pat:
        if oura_tokens.exists():
            ui.muted_line(f"Oura: already authorized ({oura_tokens})")
            answer = input("  Re-authorize Oura? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                auth_oura()
        else:
            ui.step("Oura authorization")
            answer = input("  Run Oura OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                auth_oura()
    elif oura_enabled and has_oura_pat:
        ui.muted_line("Oura: using PULSE_OURA_PERSONAL_ACCESS_TOKEN — OAuth skipped.")


"""Top-level ``configure()`` entry point and dispatch to the per-area hubs."""

from __future__ import annotations

import sys
from pathlib import Path

from pulse.app import cli_ui as ui
from pulse.app.config_loader import load_config
from pulse.app.paths import PulsePaths, resolve_pulse_paths

from .connectors import _configure_connectors_hub, _configure_connectors_toml, _configure_oauth_prompts
from .constants import (
    _CONFIGURE_INTEGRATION_FIELDS,
    _CONFIGURE_MENU_ITEMS,
    _CONFIGURE_SECTION_BANNER,
    _CONFIGURE_SEQUENTIAL_ORDER,
)
from .core import _configure_core_hub, _configure_core_only
from .env_prompts import _prompt_env_field_list
from .llm_roles import _configure_llm_roles_wizard
from .models import _configure_model_hub, _configure_model_providers_only
from .notifications import _configure_notifications_hub, _configure_notifications_only
from .toml_io import _pulse_config_to_working_env, _save_pulse_settings

def _pick_configure_menu_action() -> str:
    """Return menu action key, or ``__invalid__`` for bad numeric fallback input."""
    non_done = _CONFIGURE_MENU_ITEMS[:-1]
    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]What would you like to configure?[/]")
        for i, (_, label) in enumerate(non_done, start=1):
            ui.muted_line(f"  {i}) {label}")
        ui.muted_line("  0) Done")
        raw = input(
            f"Choose an option [0-{len(non_done)}]: "
        ).strip()
        if raw == "0":
            return "done"
        idx_map = {str(i): non_done[i - 1][0] for i in range(1, len(non_done) + 1)}
        return idx_map.get(raw, "__invalid__")

    import questionary
    from questionary import Style

    labels = [label for _, label in _CONFIGURE_MENU_ITEMS]
    label_to_key = {label: key for key, label in _CONFIGURE_MENU_ITEMS}
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
        "What would you like to configure?",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "done"
    return label_to_key[chosen]


def _configure_integrations_only(working_env: dict[str, str], toml_path: Path) -> None:
    ui.step("Credentials (integrations)")
    ui.muted_line("OAuth clients and API keys for data sources. Leave blank to skip.")
    _prompt_env_field_list(
        _CONFIGURE_INTEGRATION_FIELDS,
        working_env,
        offer_bulk_keep=toml_path.exists(),
        section_label="integration credentials",
    )


def _run_configure_full_wizard(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    offer_oauth: bool,
) -> None:
    _configure_core_only(working_env)
    _configure_integrations_only(working_env, toml_path)
    _configure_model_providers_only(working_env, toml_path)
    if sys.stdin.isatty():
        llm_ans = input(
            "  Configure [llm] provider and model roles in pulse.toml now? [y/N] "
        ).strip().lower()
        if llm_ans in ("y", "yes"):
            _configure_llm_roles_wizard(toml_path)
    _configure_notifications_only(working_env, toml_path)
    _save_pulse_settings(toml_path, working_env)
    ui.success(f"Saved {toml_path}")

    ui.step("Connector configuration")
    enabled = _configure_connectors_toml(working_env, toml_path)
    ui.success(f"Saved {toml_path}")
    ui.kv_line("Enabled", ", ".join(enabled) or "none")

    if offer_oauth:
        _configure_oauth_prompts(working_env, enabled)

    ui.rule("Configuration complete")
    if offer_oauth:
        ui.say("[accent]Next steps[/]")
        ui.kv_line("Profile + first pull", "[cmd]pulse init[/]")
        ui.kv_line("Server + scheduler", "[cmd]pulse run[/]")


def default_env_values(paths: PulsePaths) -> dict[str, str]:
    return {
        "PULSE_DATABASE_PATH": str(paths.data_dir / "pulse.db"),
        "PULSE_VAULT_PATH": str(paths.data_dir / "Pulse-Vault"),
        "PULSE_TIMEZONE": "UTC",
    }


def _execute_configure_menu_choice(
    choice: str,
    working_env: dict[str, str],
    toml_path: Path,
    *,
    offer_oauth: bool,
    submenu_exit_label: str = "← Back",
) -> None:
    """Run one top-level ``pulse configure`` area (same hubs as the interactive menu)."""
    if choice == "core":
        ui.step("Core settings")
        _configure_core_hub(
            working_env, toml_path, submenu_exit_label=submenu_exit_label
        )
    elif choice == "connectors":
        ui.step("Connectors")
        _configure_connectors_hub(
            working_env,
            toml_path,
            offer_oauth=offer_oauth,
            submenu_exit_label=submenu_exit_label,
        )
    elif choice == "notifications":
        ui.step("Notifications")
        _configure_notifications_hub(
            working_env, toml_path, submenu_exit_label=submenu_exit_label
        )
    elif choice == "model":
        ui.step("Model")
        _configure_model_hub(
            working_env, toml_path, submenu_exit_label=submenu_exit_label
        )
    else:
        raise ValueError(f"unknown configure menu choice: {choice!r}")


def _run_configure_sequential_sections(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    offer_oauth: bool,
    submenu_exit_label: str = "← Back",
) -> None:
    """Walk through each main configure area in order (same UIs as ``pulse configure``)."""
    order = _CONFIGURE_SEQUENTIAL_ORDER
    n = len(order)
    ui.muted_line(
        f"Same menus as [cmd]pulse configure[/]: choose [bold]{submenu_exit_label}[/] at the bottom "
        f"when you are done with an area; then the next step ({n} areas) continues automatically."
    )
    for i, key in enumerate(order, start=1):
        title = _CONFIGURE_SECTION_BANNER[key]
        ui.muted_line("")
        ui.say(f"[accent]Setup {i}/{n} · {title}[/]")
        _execute_configure_menu_choice(
            key,
            working_env,
            toml_path,
            offer_oauth=offer_oauth,
            submenu_exit_label=submenu_exit_label,
        )


def configure(
    *,
    offer_oauth: bool = True,
    interactive_menu: bool = True,
    config_dir: Path | None = None,
    menu_walkthrough: bool = False,
    suppress_banner: bool = False,
    submenu_exit_label: str = "← Back",
) -> None:
    paths = resolve_pulse_paths(config_dir=config_dir)
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    toml_path = paths.toml_path

    if not suppress_banner:
        ui.banner_tagline()
    ui.rule("Pulse configuration")

    working_env = _pulse_config_to_working_env(load_config(toml_path))

    if menu_walkthrough:
        _run_configure_sequential_sections(
            working_env,
            toml_path,
            offer_oauth=offer_oauth,
            submenu_exit_label=submenu_exit_label,
        )
        return

    if not interactive_menu:
        _run_configure_full_wizard(
            working_env, toml_path, offer_oauth=offer_oauth
        )
        return

    while True:
        choice = _pick_configure_menu_action()
        if choice == "__invalid__":
            ui.warning(f"Invalid choice. Enter 0–{len(_CONFIGURE_MENU_ITEMS) - 1}.")
            continue
        if choice == "done":
            ui.rule("Done")
            break
        if choice == "full":
            _run_configure_full_wizard(
                working_env, toml_path, offer_oauth=offer_oauth
            )
            break
        _execute_configure_menu_choice(
            choice,
            working_env,
            toml_path,
            offer_oauth=offer_oauth,
            submenu_exit_label=submenu_exit_label,
        )


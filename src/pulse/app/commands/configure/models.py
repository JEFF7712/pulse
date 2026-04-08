"""``pulse configure → Model`` hub: provider API keys and the LLM roles sub-menu."""

from __future__ import annotations

import sys
from pathlib import Path

from pulse.app import cli_ui as ui

from .constants import (
    _CONFIGURE_MODEL_PROVIDER_FIELDS,
    _MODEL_HUB_ITEMS,
    _MODEL_PROVIDER_DEFS,
)
from .env_prompts import _prompt_env_field_list
from .llm_roles import _configure_llm_roles_wizard
from .toml_io import _save_pulse_settings

def _model_provider_ready(provider_id: str, env: dict[str, str]) -> bool:
    """True when typical env creds exist for that LLM vendor (Ollama is pulse.toml + optional key)."""

    def g(key: str) -> str:
        return (env.get(key) or "").strip()

    if provider_id == "anthropic":
        return bool(g("ANTHROPIC_API_KEY") or g("PULSE_ANTHROPIC_API_KEY"))
    if provider_id == "openai":
        return bool(g("OPENAI_API_KEY") or g("PULSE_OPENAI_API_KEY"))
    if provider_id == "gemini":
        return bool(g("GEMINI_API_KEY") or g("PULSE_GEMINI_API_KEY"))
    if provider_id == "ollama":
        return False
    return False


def _model_provider_submenu_row_label(
    provider_id: str, short: str, emoji: str, working_env: dict[str, str]
) -> str:
    circle = "●" if _model_provider_ready(provider_id, working_env) else "○"
    return f"{circle} {emoji} {short}"


def _pick_model_provider_submenu(
    working_env: dict[str, str],
    *,
    exit_label: str = "← Back",
) -> str | None:
    rows: list[tuple[str, str]] = []
    for pid, short, emoji, _fields in _MODEL_PROVIDER_DEFS:
        disp = _model_provider_submenu_row_label(pid, short, emoji, working_env)
        rows.append((pid, disp))
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Pick a model provider to configure[/]")
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
        "Model providers",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_model_providers_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_legend = False
    while True:
        if not showed_legend:
            ui.muted_line(
                "● = API key set in pulse.toml for that vendor · ○ = missing · "
                "Match [llm] / [llm.summarization] / … provider values in pulse.toml."
            )
            showed_legend = True
        pick = _pick_model_provider_submenu(
            working_env, exit_label=submenu_exit_label
        )
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        row = next(r for r in _MODEL_PROVIDER_DEFS if r[0] == pick)
        _pid, label, _emoji, fields = row
        ui.step(label)
        if not fields:
            ui.muted_line(
                "Uses the OpenAI-compatible client. In pulse.toml set provider = \"ollama\", "
                "base_url (e.g. http://127.0.0.1:11434/v1), and a model id under [llm] or a role. "
                "OPENAI_API_KEY can stay blank; Pulse uses a placeholder when unset."
            )
            continue
        ui.muted_line("API keys for this vendor (saved in pulse.toml; leave blank to skip).")
        _prompt_env_field_list(
            fields,
            working_env,
            offer_bulk_keep=toml_path.exists(),
            section_label=f"{label} API keys",
        )
        _save_pulse_settings(toml_path, working_env)
        ui.success(f"Saved {toml_path}")


def _configure_model_providers_only(working_env: dict[str, str], toml_path: Path) -> None:
    ui.step("Model providers")
    ui.muted_line(
        "Provider choice and model ids live in pulse.toml under [llm] / [llm.summarization] / …; "
        "this pass writes vendor API keys into pulse.toml. Leave blank to skip."
    )
    _prompt_env_field_list(
        _CONFIGURE_MODEL_PROVIDER_FIELDS,
        working_env,
        offer_bulk_keep=toml_path.exists(),
        section_label="model provider API keys",
    )


def _pick_model_hub_section(*, exit_label: str = "← Back") -> str | None:
    rows: list[tuple[str, str]] = list(_MODEL_HUB_ITEMS)
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Model — choose what to configure[/]")
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
        "Model",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_model_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_legend = False
    while True:
        if not showed_legend:
            ui.muted_line(
                "Provider API keys are stored in pulse.toml; LLM roles set [llm] provider "
                "and summarization / discovery model ids (also in pulse.toml)."
            )
            showed_legend = True
        pick = _pick_model_hub_section(exit_label=submenu_exit_label)
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        if pick == "api_keys":
            ui.step("Provider API keys")
            _configure_model_providers_hub(
                working_env, toml_path, submenu_exit_label=submenu_exit_label
            )
        elif pick == "llm_roles":
            ui.step("LLM roles in pulse.toml")
            _configure_llm_roles_wizard(
                toml_path, submenu_exit_label=submenu_exit_label
            )


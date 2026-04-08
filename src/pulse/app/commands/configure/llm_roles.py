"""``pulse configure → Model → LLM roles`` wizard (writes [llm] / [llm.summarization] / [llm.discovery])."""

from __future__ import annotations

import sys
from pathlib import Path

from pulse.app import cli_ui as ui

from .toml_io import _load_full_pulse_toml, _serialize_pulse_toml_document

_LLM_ROLES_PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "gemini", "ollama")
_OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
_WIZARD_DEFAULT_ANTHROPIC_SUMM = "claude-haiku-4-5-20251001"
_WIZARD_DEFAULT_ANTHROPIC_DISC = "claude-sonnet-4-6"

def _configure_llm_roles_wizard(
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    """Prompt for [llm] provider, summarization model, discovery model; merge into pulse.toml."""

    defaults_map: dict[str, tuple[str, str]] = {
        "anthropic": (
            _WIZARD_DEFAULT_ANTHROPIC_SUMM,
            _WIZARD_DEFAULT_ANTHROPIC_DISC,
        ),
        "openai": ("gpt-4.1-mini", "gpt-4.1"),
        "gemini": ("gemini-2.5-flash", "gemini-2.5-pro"),
        "ollama": ("llama3.2", "llama3.2"),
    }

    full = _load_full_pulse_toml(toml_path)
    cur = full.get("llm") if isinstance(full.get("llm"), dict) else {}
    summ_blk = (
        cur.get("summarization") if isinstance(cur.get("summarization"), dict) else {}
    )
    disc_blk = cur.get("discovery") if isinstance(cur.get("discovery"), dict) else {}
    summ_m = (summ_blk.get("model") or "").strip()
    disc_m = (disc_blk.get("model") or "").strip()
    cur_prov = (cur.get("provider") or "").strip().lower()
    if cur_prov not in _LLM_ROLES_PROVIDERS:
        cur_prov = ""

    ui.step("LLM roles in pulse.toml")
    ui.muted_line(
        "Sets [llm] provider plus [llm.summarization] and [llm.discovery] model ids. "
        "API keys live in pulse.toml (Model → Provider API keys). Existing [llm.corrections] is kept."
    )

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]LLM provider[/]")
        for i, p in enumerate(_LLM_ROLES_PROVIDERS, start=1):
            ui.muted_line(f"  {i}) {p}")
        forward_exit = (
            "next" in submenu_exit_label.lower()
            and "back" not in submenu_exit_label.lower()
        )
        non_tty_exit = submenu_exit_label if forward_exit else "Cancel"
        ui.muted_line(f"  0) {non_tty_exit}")
        raw = input(f"Choose [0-{len(_LLM_ROLES_PROVIDERS)}]: ").strip()
        if raw == "0":
            return
        try:
            idx = int(raw)
        except ValueError:
            ui.warning("Invalid choice.")
            return
        if idx < 1 or idx > len(_LLM_ROLES_PROVIDERS):
            ui.warning("Invalid choice.")
            return
        provider = _LLM_ROLES_PROVIDERS[idx - 1]
    else:
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
        choices = list(_LLM_ROLES_PROVIDERS) + [submenu_exit_label]
        chosen = questionary.select(
            "LLM provider (one for summarization and discovery)",
            choices=choices,
            qmark="›",
            style=style,
            instruction=" (↑↓ move · Enter to select)",
        ).ask()
        if chosen is None or chosen == submenu_exit_label:
            return
        provider = chosen

    d0, d1 = defaults_map[provider]
    summ_def = summ_m or d0
    disc_def = disc_m or d1

    base_url = ""
    if provider == "ollama":
        existing_bu = cur.get("base_url")
        if isinstance(existing_bu, str):
            base_url = existing_bu.strip()
        bu_default = base_url or _OLLAMA_DEFAULT_BASE_URL
        if not sys.stdin.isatty():
            bu_in = input(f"  OpenAI-compatible base URL [{bu_default}]: ").strip()
            base_url = bu_in or bu_default
        else:
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
            bu_in = questionary.text(
                "Ollama base URL (OpenAI-compatible)",
                default=bu_default,
                qmark="›",
                style=style,
            ).ask()
            if bu_in is None:
                return
            base_url = (bu_in or bu_default).strip()

    if not sys.stdin.isatty():
        s_in = input(f"  Summarization model [{summ_def}]: ").strip()
        summ = s_in or summ_def
        d_in = input(f"  Discovery model [{disc_def}]: ").strip()
        disc = d_in or disc_def
    else:
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
        s_in = questionary.text(
            "Summarization model id",
            default=summ_def,
            qmark="›",
            style=style,
        ).ask()
        if s_in is None:
            return
        summ = s_in.strip() or summ_def
        d_in = questionary.text(
            "Discovery model id",
            default=disc_def,
            qmark="›",
            style=style,
        ).ask()
        if d_in is None:
            return
        disc = d_in.strip() or disc_def

    managed = {"provider", "base_url", "summarization", "discovery", "corrections"}
    new_llm: dict = {}
    for k, v in cur.items():
        if k in managed:
            continue
        new_llm[k] = v
    corr = cur.get("corrections")
    if isinstance(corr, dict) and corr:
        new_llm["corrections"] = dict(corr)

    new_summ = dict(summ_blk)
    new_summ["model"] = summ
    new_disc = dict(disc_blk)
    new_disc["model"] = disc

    new_llm["provider"] = provider
    new_llm["summarization"] = new_summ
    new_llm["discovery"] = new_disc
    if provider == "ollama":
        new_llm["base_url"] = base_url
    elif provider == "openai":
        old_bu = cur.get("base_url")
        if isinstance(old_bu, str) and old_bu.strip():
            new_llm["base_url"] = old_bu.strip()

    full["llm"] = new_llm
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(_serialize_pulse_toml_document(full))
    ui.success(f"Saved {toml_path}")


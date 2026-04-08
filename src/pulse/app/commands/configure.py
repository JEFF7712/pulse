"""`pulse configure`: interactive setup for pulse.toml (core / connectors / notifications / model / llm)."""

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
from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.app.paths import PulsePaths, resolve_pulse_paths


def _mask(value: str) -> str:
    """Show first 8 chars of a secret, mask the rest."""
    if len(value) > 12:
        return f"{value[:8]}..."
    return value


def _prompt_env_field(
    key: str, label: str, current: str, is_secret: bool = False
) -> str:
    """Prompt for an env field. If it already has a value, ask to keep or change."""
    if current:
        display = _mask(current) if is_secret else current
        answer = input(f"  {label}: {display} — keep? [Y/n] ").strip().lower()
        if answer in ("n", "no"):
            new_val = input(f"  {label}: ").strip()
            return new_val if new_val else current
        return current
    else:
        value = input(f"  {label}: ").strip()
        return value


# Core paths & timezone — one submenu row each in `pulse configure` → Core settings.
_CORE_SETTING_DEFS: list[tuple[str, str, str, list[tuple[str, str, str, bool]]]] = [
    (
        "database",
        "Database",
        "🗄️",
        [
            ("PULSE_DATABASE_PATH", "Database path", "data/pulse.db", False),
        ],
    ),
    (
        "vault",
        "Obsidian vault",
        "📓",
        [
            ("PULSE_VAULT_PATH", "Obsidian vault path", "Pulse-Vault", False),
        ],
    ),
    (
        "timezone",
        "Timezone",
        "🌍",
        [
            ("PULSE_TIMEZONE", "Timezone (e.g., America/Chicago)", "UTC", False),
        ],
    ),
]

# Flat list for full wizard core pass and pulse.toml root emit order in configure.
_CONFIGURE_CORE_FIELDS: list[tuple[str, str, str, bool]] = [
    fld for *_, flds in _CORE_SETTING_DEFS for fld in flds
]

# Flat list for full wizard “integrations” pass. Per-connector menus reuse the same keys
# via _CONNECTOR_ENV_FIELDS (intentional overlap — connector flow is scoped per source).
_CONFIGURE_INTEGRATION_FIELDS: list[tuple[str, str, bool]] = [
    ("PULSE_GOOGLE_CLIENT_ID", "Google Client ID", True),
    ("PULSE_GOOGLE_CLIENT_SECRET", "Google Client Secret", True),
    ("PULSE_SPOTIFY_CLIENT_ID", "Spotify Client ID", True),
    ("PULSE_SPOTIFY_CLIENT_SECRET", "Spotify Client Secret", True),
    ("PULSE_MICROSOFT_CLIENT_ID", "Microsoft / Azure app Client ID", True),
    ("PULSE_MICROSOFT_CLIENT_SECRET", "Microsoft / Azure app Client Secret", True),
    ("PULSE_MICROSOFT_TENANT_ID", "Microsoft tenant (blank = common)", False),
    ("PULSE_GITHUB_CLIENT_ID", "GitHub OAuth Client ID", True),
    ("PULSE_GITHUB_CLIENT_SECRET", "GitHub OAuth Client Secret", True),
    ("PULSE_GITLAB_CLIENT_ID", "GitLab OAuth Application ID", True),
    ("PULSE_GITLAB_CLIENT_SECRET", "GitLab OAuth Secret", True),
    ("PULSE_GITLAB_TOKEN", "GitLab personal access token (optional)", True),
    ("PULSE_PLAID_CLIENT_ID", "Plaid client ID", True),
    ("PULSE_PLAID_SECRET", "Plaid secret", True),
    ("PULSE_PLAID_ENV", "Plaid environment (sandbox or production)", False),
    ("PULSE_OURA_CLIENT_ID", "Oura OAuth client ID (optional)", True),
    ("PULSE_OURA_CLIENT_SECRET", "Oura OAuth client secret (optional)", True),
    (
        "PULSE_OURA_PERSONAL_ACCESS_TOKEN",
        "Oura personal access token (optional; skips OAuth if set)",
        True,
    ),
    ("PULSE_NOTION_TOKEN", "Notion integration secret (internal integration)", True),
    ("PULSE_LINEAR_API_KEY", "Linear personal API key (assigned issues)", True),
]

# LLM vendor API keys (see pulse.llm.factory — also ``anthropic_api_key`` / ``PULSE_ANTHROPIC_API_KEY`` in TOML or env).
_MODEL_PROVIDER_DEFS: list[tuple[str, str, str, list[tuple[str, str, bool]]]] = [
    (
        "anthropic",
        "Anthropic",
        "🅰️",
        [
            (
                "ANTHROPIC_API_KEY",
                "Anthropic API key ([llm.*] provider = anthropic; or pulse.toml anthropic_api_key)",
                True,
            ),
            (
                "PULSE_ANTHROPIC_API_KEY",
                "Same key as ANTHROPIC_API_KEY (TOML / env alias)",
                True,
            ),
        ],
    ),
    (
        "openai",
        "OpenAI / compatible",
        "🧠",
        [
            (
                "OPENAI_API_KEY",
                "OpenAI API key (OpenAI, Azure OpenAI-compatible, or optional for Ollama)",
                True,
            ),
        ],
    ),
    (
        "gemini",
        "Google Gemini",
        "✨",
        [
            ("GEMINI_API_KEY", "Gemini API key ([llm.*] provider = gemini)", True),
        ],
    ),
    (
        "ollama",
        "Ollama (local)",
        "🦙",
        [],
    ),
]

_CONFIGURE_MODEL_PROVIDER_FIELDS: list[tuple[str, str, bool]] = [
    fld for *_, flds in _MODEL_PROVIDER_DEFS for fld in flds
]

# Per-provider notification / webhook keys (order preserved for full wizard + pulse.toml key order).
_NOTIFICATION_PROVIDER_DEFS: list[tuple[str, str, str, list[tuple[str, str, bool]]]] = [
    (
        "telegram",
        "Telegram",
        "📱",
        [
            ("PULSE_TELEGRAM_BOT_TOKEN", "Telegram Bot Token", True),
            ("PULSE_TELEGRAM_CHAT_ID", "Telegram Chat ID", False),
        ],
    ),
    (
        "corrections",
        "Corrections API",
        "🛠️",
        [
            (
                "PULSE_CORRECTIONS_WEBHOOK_SECRET",
                "Corrections webhook secret (optional; enables POST /webhooks/corrections)",
                True,
            ),
        ],
    ),
    (
        "ntfy",
        "ntfy",
        "🔔",
        [
            ("PULSE_NTFY_TOPIC", "ntfy topic (optional; leave blank to skip)", False),
            (
                "PULSE_NTFY_BASE_URL",
                "ntfy server base URL (optional; blank uses https://ntfy.sh)",
                False,
            ),
        ],
    ),
    (
        "webhook",
        "JSON webhook",
        "🔗",
        [
            (
                "PULSE_NOTIFICATION_WEBHOOK_URL",
                "Notification webhook URL (optional JSON POST)",
                False,
            ),
        ],
    ),
    (
        "discord",
        "Discord",
        "🎮",
        [
            ("PULSE_DISCORD_WEBHOOK_URL", "Discord incoming webhook URL (optional)", False),
        ],
    ),
    (
        "slack",
        "Slack",
        "💬",
        [
            ("PULSE_SLACK_WEBHOOK_URL", "Slack incoming webhook URL (optional)", False),
        ],
    ),
    (
        "pushover",
        "Pushover",
        "📲",
        [
            (
                "PULSE_PUSHOVER_USER_KEY",
                "Pushover user key (optional; needs API token too)",
                False,
            ),
            ("PULSE_PUSHOVER_API_TOKEN", "Pushover application API token", True),
        ],
    ),
    (
        "gotify",
        "Gotify",
        "📮",
        [
            (
                "PULSE_GOTIFY_URL",
                "Gotify server URL (optional; e.g. https://gotify.example.com)",
                False,
            ),
            ("PULSE_GOTIFY_APP_TOKEN", "Gotify application token", True),
        ],
    ),
    (
        "smtp",
        "SMTP email",
        "✉️",
        [
            ("PULSE_SMTP_HOST", "SMTP host (optional)", False),
            ("PULSE_SMTP_PORT", "SMTP port", False),
            ("PULSE_SMTP_USER", "SMTP username (optional)", False),
            ("PULSE_SMTP_PASSWORD", "SMTP password (optional)", True),
            ("PULSE_SMTP_USE_TLS", "SMTP STARTTLS after connect (true/false)", False),
            ("PULSE_SMTP_USE_SSL", "SMTP implicit SSL (true/false)", False),
            ("PULSE_SMTP_FROM", "SMTP From address (optional)", False),
            (
                "PULSE_SMTP_TO",
                "SMTP To address(es), comma-separated (optional)",
                False,
            ),
        ],
    ),
    (
        "companion",
        "Companion / FCM",
        "🤝",
        [
            (
                "PULSE_COMPANION_TOKEN",
                "Companion API bearer token (POST /webhooks/companion)",
                True,
            ),
            (
                "PULSE_FCM_SERVICE_ACCOUNT_PATH",
                "Path to Firebase service account JSON (FCM push)",
                False,
            ),
        ],
    ),
]

_CONFIGURE_NOTIFICATION_FIELDS: list[tuple[str, str, bool]] = [
    fld for *_, flds in _NOTIFICATION_PROVIDER_DEFS for fld in flds
]

_CONFIGURE_ENV_KEY_ORDER: list[str] = (
    [t[0] for t in _CONFIGURE_CORE_FIELDS]
    + [t[0] for t in _CONFIGURE_INTEGRATION_FIELDS]
    + [t[0] for t in _CONFIGURE_MODEL_PROVIDER_FIELDS]
    + [t[0] for t in _CONFIGURE_NOTIFICATION_FIELDS]
)

# Map configure / model-provider env keys to ``PulseConfig`` root field names (pulse.toml).
_ENV_KEY_TO_CONFIG_FIELD: dict[str, str] = {
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "PULSE_ANTHROPIC_API_KEY": "anthropic_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
}

_PULSE_ROOT_FIELD_NAMES: frozenset[str] = frozenset(
    k for k in PulseConfig.model_fields if k not in ("connectors", "llm")
)

_CONNECTOR_DEFS: list[tuple[str, str, str]] = [
    ("gmail", "15m", "Gmail (email)"),
    ("calendar", "30m", "Google Calendar"),
    ("youtube", "1h", "YouTube"),
    ("spotify", "30m", "Spotify"),
    ("microsoft_mail", "15m", "Microsoft 365 mail (Outlook)"),
    ("microsoft_calendar", "30m", "Microsoft 365 calendar"),
    ("github", "30m", "GitHub activity"),
    ("linear", "30m", "Linear (issues assigned to you)"),
    ("gitlab", "30m", "GitLab activity"),
    ("plaid", "6h", "Plaid bank transactions"),
    ("browser", "15m", "Browser history"),
    ("feeds", "1h", "RSS/Atom feeds (URLs in pulse.toml)"),
    ("notion", "45m", "Notion (pages shared with your integration)"),
    ("oura", "6h", "Oura Ring (sleep & readiness)"),
]

_CONNECTOR_MENU_EMOJI: dict[str, str] = {
    "gmail": "📧",
    "calendar": "📅",
    "youtube": "▶️",
    "spotify": "🎵",
    "microsoft_mail": "✉️",
    "microsoft_calendar": "📆",
    "github": "🐙",
    "linear": "⚡",
    "gitlab": "🦊",
    "plaid": "🏦",
    "browser": "🌍",
    "feeds": "📡",
    "notion": "📓",
    "oura": "💍",
}

_CONNECTOR_MENU_SHORT: dict[str, str] = {
    "gmail": "Gmail",
    "calendar": "G Cal",
    "youtube": "YouTube",
    "spotify": "Spotify",
    "microsoft_mail": "Outlook",
    "microsoft_calendar": "365 Cal",
    "github": "GitHub",
    "linear": "Linear",
    "gitlab": "GitLab",
    "plaid": "Plaid",
    "browser": "Browser",
    "feeds": "Feeds",
    "notion": "Notion",
    "oura": "Oura",
}

_GOOGLE_ENV_FIELDS: list[tuple[str, str, bool]] = [
    ("PULSE_GOOGLE_CLIENT_ID", "Google Client ID", True),
    ("PULSE_GOOGLE_CLIENT_SECRET", "Google Client Secret", True),
]
_MS_ENV_FIELDS: list[tuple[str, str, bool]] = [
    ("PULSE_MICROSOFT_CLIENT_ID", "Microsoft / Azure app Client ID", True),
    ("PULSE_MICROSOFT_CLIENT_SECRET", "Microsoft / Azure app Client Secret", True),
    ("PULSE_MICROSOFT_TENANT_ID", "Microsoft tenant (blank = common)", False),
]

_CONNECTOR_ENV_FIELDS: dict[str, list[tuple[str, str, bool]]] = {
    "gmail": _GOOGLE_ENV_FIELDS,
    "calendar": _GOOGLE_ENV_FIELDS,
    "youtube": _GOOGLE_ENV_FIELDS,
    "spotify": [
        ("PULSE_SPOTIFY_CLIENT_ID", "Spotify Client ID", True),
        ("PULSE_SPOTIFY_CLIENT_SECRET", "Spotify Client Secret", True),
    ],
    "microsoft_mail": _MS_ENV_FIELDS,
    "microsoft_calendar": _MS_ENV_FIELDS,
    "github": [
        ("PULSE_GITHUB_CLIENT_ID", "GitHub OAuth Client ID", True),
        ("PULSE_GITHUB_CLIENT_SECRET", "GitHub OAuth Client Secret", True),
    ],
    "gitlab": [
        ("PULSE_GITLAB_CLIENT_ID", "GitLab OAuth Application ID", True),
        ("PULSE_GITLAB_CLIENT_SECRET", "GitLab OAuth Secret", True),
        ("PULSE_GITLAB_TOKEN", "GitLab personal access token (optional)", True),
    ],
    "plaid": [
        ("PULSE_PLAID_CLIENT_ID", "Plaid client ID", True),
        ("PULSE_PLAID_SECRET", "Plaid secret", True),
        ("PULSE_PLAID_ENV", "Plaid environment (sandbox or production)", False),
    ],
    "oura": [
        ("PULSE_OURA_CLIENT_ID", "Oura OAuth client ID (optional)", True),
        ("PULSE_OURA_CLIENT_SECRET", "Oura OAuth client secret (optional)", True),
        (
            "PULSE_OURA_PERSONAL_ACCESS_TOKEN",
            "Oura personal access token (optional; skips OAuth if set)",
            True,
        ),
    ],
    "notion": [
        ("PULSE_NOTION_TOKEN", "Notion integration secret (internal integration)", True),
    ],
    "linear": [("PULSE_LINEAR_API_KEY", "Linear personal API key (assigned issues)", True)],
}

_CONFIGURE_MENU_ITEMS: list[tuple[str, str]] = [
    ("core", "⚙️ Core settings (paths, timezone)"),
    (
        "connectors",
        "🔌 Connectors (pulse.toml credentials + blocks, OAuth / Plaid / Oura when needed)",
    ),
    (
        "notifications",
        "🔔 Notifications (Telegram, SMTP, webhooks, companion/FCM, …)",
    ),
    (
        "model",
        "🧠 Model (provider API keys + [llm] provider & summarization / discovery models)",
    ),
    ("full", "✨ Full wizard (all of the above)"),
    ("done", "✅ Done"),
]

# Submenu under `pulse configure` → Model (API keys vs [llm] roles).
_MODEL_HUB_ITEMS: list[tuple[str, str]] = [
    ("api_keys", "🔑 Provider API keys (Anthropic, OpenAI, Gemini, Ollama …)"),
    (
        "llm_roles",
        "💬 LLM in pulse.toml (provider + summarization & discovery models)",
    ),
]

# Main configure areas in walkthrough order (excludes Full wizard & Done) — e.g. `pulse onboard`.
_CONFIGURE_SEQUENTIAL_ORDER: tuple[str, ...] = (
    "core",
    "connectors",
    "notifications",
    "model",
)

_CONFIGURE_SECTION_BANNER: dict[str, str] = {
    "core": "Core settings",
    "connectors": "Connectors",
    "notifications": "Notifications",
    "model": "Model",
}


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


def _configure_section_has_values(env: dict[str, str], fields: list[tuple]) -> bool:
    keys = [f[0] for f in fields]
    return any((env.get(k) or "").strip() for k in keys)


def _offer_bulk_keep_section(
    env: dict[str, str],
    fields: list[tuple],
    section_label: str,
) -> bool:
    """Return True if user wants to keep all existing values for keys in this section."""
    if not _configure_section_has_values(env, fields):
        return False
    ans = input(f"  Keep all existing {section_label}? [Y/n] ").strip().lower()
    return ans not in ("n", "no")


def _prompt_env_field_list(
    fields: list[tuple[str, str, bool]],
    working_env: dict[str, str],
    *,
    offer_bulk_keep: bool,
    section_label: str,
) -> None:
    if offer_bulk_keep and _offer_bulk_keep_section(working_env, fields, section_label):
        return
    for key, label, is_secret in fields:
        current = working_env.get(key, "")
        working_env[key] = _prompt_env_field(key, label, current, is_secret)


def _env_key_to_pulse_field(ek: str) -> str | None:
    if ek in _ENV_KEY_TO_CONFIG_FIELD:
        return _ENV_KEY_TO_CONFIG_FIELD[ek]
    if ek.startswith("PULSE_"):
        cand = ek[6:].lower()
        if cand in _PULSE_ROOT_FIELD_NAMES:
            return cand
    return None


def _ordered_pulse_root_field_names() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ek in _CONFIGURE_ENV_KEY_ORDER:
        fname = _env_key_to_pulse_field(ek)
        if fname and fname not in seen:
            seen.add(fname)
            out.append(fname)
    for fname in sorted(_PULSE_ROOT_FIELD_NAMES):
        if fname not in seen:
            out.append(fname)
    return out


def _pulse_config_to_working_env(cfg: PulseConfig) -> dict[str, str]:
    out: dict[str, str] = {}
    for fname in _PULSE_ROOT_FIELD_NAMES:
        val = getattr(cfg, fname)
        env_k = f"PULSE_{fname.upper()}"
        if val is None:
            out[env_k] = ""
        elif isinstance(val, bool):
            out[env_k] = "true" if val else "false"
        else:
            out[env_k] = str(val)
    if cfg.anthropic_api_key:
        ak = cfg.anthropic_api_key
        out["ANTHROPIC_API_KEY"] = ak
        out["PULSE_ANTHROPIC_API_KEY"] = ak
    if cfg.openai_api_key:
        out["OPENAI_API_KEY"] = cfg.openai_api_key
    if cfg.gemini_api_key:
        out["GEMINI_API_KEY"] = cfg.gemini_api_key
    return out


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


def _load_full_pulse_toml(toml_path: Path) -> dict:
    """Parse pulse.toml into a nested dict (empty if missing)."""
    import tomllib

    if not toml_path.exists():
        return {}
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _load_connectors_state(toml_path: Path) -> dict[str, dict]:
    raw_block: dict = {}
    data = _load_full_pulse_toml(toml_path)
    cc = data.get("connectors")
    if isinstance(cc, dict):
        raw_block = cc
    state: dict[str, dict] = {}
    for name, _, _ in _CONNECTOR_DEFS:
        v = raw_block.get(name)
        state[name] = dict(v) if isinstance(v, dict) else {}
    return state


def _toml_inline_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        esc = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    raise TypeError(f"Unsupported TOML value type: {type(v)!r}")


def _coerce_pulse_root_string(fname: str, raw: str) -> str | int | bool:
    raw = raw.strip()
    if fname == "smtp_port":
        return int(raw)
    if fname in ("smtp_use_tls", "smtp_use_ssl"):
        return raw.lower() in ("1", "true", "yes", "on")
    return raw


def _merge_working_env_into_full_root(full: dict, working_env: dict[str, str]) -> None:
    for ek, fname in _ENV_KEY_TO_CONFIG_FIELD.items():
        if ek not in working_env:
            continue
        v = working_env[ek].strip()
        if v:
            full[fname] = v
        else:
            full.pop(fname, None)
    for key, val in working_env.items():
        if not key.startswith("PULSE_"):
            continue
        fname = key[6:].lower()
        if fname not in _PULSE_ROOT_FIELD_NAMES:
            continue
        v = val.strip()
        if not v:
            full.pop(fname, None)
        else:
            full[fname] = _coerce_pulse_root_string(fname, v)


def _pulse_scalar_empty_for_emit(v: object) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _emit_pulse_root_scalar_lines(full: dict) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for fname in _ordered_pulse_root_field_names():
        if fname not in full:
            continue
        v = full[fname]
        if _pulse_scalar_empty_for_emit(v):
            continue
        lines.append(f"{fname} = {_toml_inline_value(v)}")
        seen.add(fname)
    for fname in sorted(k for k in full if k in _PULSE_ROOT_FIELD_NAMES and k not in seen):
        v = full[fname]
        if _pulse_scalar_empty_for_emit(v):
            continue
        lines.append(f"{fname} = {_toml_inline_value(v)}")
    return lines


def _connector_emit_lines(
    name: str, sec: dict, default_interval: str
) -> list[str]:
    lines: list[str] = []
    enabled = _connector_section_enabled(sec)
    interval = sec.get("poll_interval") or default_interval
    if not isinstance(interval, str):
        interval = str(interval)
    lines.append(f"[connectors.{name}]")
    lines.append(f"enabled = {'true' if enabled else 'false'}")
    lines.append(f'poll_interval = "{interval}"')
    if name == "spotify":
        supp = sec.get("supplementary_interval", "6h")
        if not isinstance(supp, str):
            supp = str(supp)
        lines.append(f'supplementary_interval = "{supp}"')
    if name == "browser":
        bt = sec.get("browser", "chrome")
        if not isinstance(bt, str):
            bt = str(bt)
        lines.append(f'browser = "{bt}"')
        dbp = sec.get("db_path")
        if enabled and isinstance(dbp, str) and dbp.strip():
            safe = dbp.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'db_path = "{safe}"')
    if name == "microsoft_calendar":
        cal_id = sec.get("calendar_id", "primary")
        if not isinstance(cal_id, str):
            cal_id = str(cal_id)
        safe_cal = cal_id.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'calendar_id = "{safe_cal}"')
    if name == "gitlab":
        bu = sec.get("gitlab_base_url", "https://gitlab.com")
        if not isinstance(bu, str):
            bu = str(bu)
        escaped = bu.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'gitlab_base_url = "{escaped}"')
    if name == "plaid":
        omit = bool(
            sec.get("omit_amounts_in_summary") or sec.get("omit_amounts_in_digest", False)
        )
        lines.append(f"omit_amounts_in_summary = {'true' if omit else 'false'}")
    if name == "notion":
        prev_dbs = sec.get("database_ids") or []
        if isinstance(prev_dbs, str):
            prev_dbs = [prev_dbs] if prev_dbs else []
        escaped = [u.replace("\\", "\\\\").replace('"', '\\"') for u in prev_dbs]
        if escaped:
            lines.append(
                "database_ids = [" + ", ".join(f'"{u}"' for u in escaped) + "]"
            )
    if name == "feeds":
        prev_urls = sec.get("urls")
        if prev_urls is None:
            prev_urls = []
        if isinstance(prev_urls, str):
            prev_urls = [prev_urls] if prev_urls else []
        escaped = [u.replace("\\", "\\\\").replace('"', '\\"') for u in prev_urls]
        if escaped:
            lines.append("urls = [" + ", ".join(f'"{u}"' for u in escaped) + "]")
        else:
            lines.append("urls = []")
    lines.append("")
    return lines


def _emit_generic_connectors_table(name: str, sec: dict) -> list[str]:
    """Emit [connectors.X] for keys not in _CONNECTOR_DEFS (e.g. companion)."""
    lines = [f"[connectors.{name}]"]
    for k, v in sorted(sec.items()):
        if isinstance(v, dict):
            continue
        if isinstance(v, list):
            parts = []
            for x in v:
                if isinstance(x, str):
                    sx = x.replace("\\", "\\\\").replace('"', '\\"')
                    parts.append(f'"{sx}"')
                else:
                    parts.append(_toml_inline_value(x))
            lines.append(f"{k} = [" + ", ".join(parts) + "]")
        else:
            lines.append(f"{k} = {_toml_inline_value(v)}")
    lines.append("")
    return lines


def _emit_llm_sections(llm: dict) -> list[str]:
    lines: list[str] = []
    scalars: dict[str, object] = {}
    nested: dict[str, dict] = {}
    for k, v in llm.items():
        if isinstance(v, dict):
            nested[k] = v
        else:
            scalars[k] = v
    if scalars:
        lines.append("[llm]")
        for k in sorted(scalars):
            lines.append(f"{k} = {_toml_inline_value(scalars[k])}")
        lines.append("")
    for sub in ("summarization", "discovery", "corrections"):
        if sub not in nested:
            continue
        blk = nested[sub]
        if not isinstance(blk, dict) or not blk:
            continue
        lines.append(f"[llm.{sub}]")
        for k in sorted(blk):
            lines.append(f"{k} = {_toml_inline_value(blk[k])}")
        lines.append("")
    for sub, blk in sorted(nested.items()):
        if sub in ("summarization", "discovery", "corrections"):
            continue
        if not isinstance(blk, dict) or not blk:
            continue
        lines.append(f"[llm.{sub}]")
        for k in sorted(blk):
            lines.append(f"{k} = {_toml_inline_value(blk[k])}")
        lines.append("")
    return lines


def _serialize_pulse_toml_document(full: dict) -> str:
    """Emit pulse.toml: app scalars, connectors, ``[llm]``, then other top-level tables."""
    lines = [
        "# Pulse configuration (single file: paths, secrets, connectors, LLM roles).",
        "# ``PULSE_*`` and vendor API env vars override values from this file when set.",
        "",
    ]
    root_lines = _emit_pulse_root_scalar_lines(full)
    if root_lines:
        lines.append("# --- App (paths, integrations, notifications, API keys) ---")
        lines.extend(root_lines)
        lines.append("")
    connectors = full.get("connectors")
    if not isinstance(connectors, dict):
        connectors = {}
    known = {n for n, _, _ in _CONNECTOR_DEFS}
    for name, default_interval, _label in _CONNECTOR_DEFS:
        sec = connectors.get(name)
        if not isinstance(sec, dict):
            sec = {}
        lines.extend(_connector_emit_lines(name, sec, default_interval))
    for name in sorted(k for k in connectors if k not in known):
        sec = connectors.get(name)
        if isinstance(sec, dict) and sec:
            lines.extend(_emit_generic_connectors_table(name, sec))
    llm = full.get("llm")
    if isinstance(llm, dict) and llm:
        lines.append("# --- LLM (source summarization, discovery, corrections) ---")
        lines.append("")
        lines.extend(_emit_llm_sections(llm))
    skip_top = frozenset(("connectors", "llm")) | _PULSE_ROOT_FIELD_NAMES
    for top_key in sorted(k for k in full if k not in skip_top):
        # Forward-compat: extra top-level sections as [key] with flat scalars only.
        block = full[top_key]
        if not isinstance(block, dict):
            continue
        if not block or any(isinstance(v, dict) for v in block.values()):
            continue
        lines.append(f"[{top_key}]")
        for k in sorted(block):
            lines.append(f"{k} = {_toml_inline_value(block[k])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _save_pulse_settings(toml_path: Path, working_env: dict[str, str]) -> None:
    if not (working_env.get("PULSE_SMTP_PORT") or "").strip():
        working_env["PULSE_SMTP_PORT"] = "587"
    full = _load_full_pulse_toml(toml_path)
    _merge_working_env_into_full_root(full, working_env)
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(_serialize_pulse_toml_document(full))


def _write_connectors_state(state: dict[str, dict], toml_path: Path) -> None:
    full = _load_full_pulse_toml(toml_path)
    old_c = full.get("connectors")
    if not isinstance(old_c, dict):
        old_c = {}
    merged = dict(old_c)
    for name, _, _ in _CONNECTOR_DEFS:
        merged[name] = state.get(name) or {}
    full["connectors"] = merged
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(_serialize_pulse_toml_document(full))


def _connector_section_enabled(section: dict) -> bool:
    """True only when this connector block is turned on in pulse.toml.

    Avoid ``bool("false")`` which is True in Python — some hand-edited files use strings.
    """
    if not section:
        return False
    raw = section.get("enabled")
    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    if isinstance(raw, str):
        t = raw.strip().lower()
        return t in ("true", "1", "yes", "on")
    if isinstance(raw, (int, float)):
        return raw != 0
    return False


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


def _configure_integrations_only(working_env: dict[str, str], toml_path: Path) -> None:
    ui.step("Credentials (integrations)")
    ui.muted_line("OAuth clients and API keys for data sources. Leave blank to skip.")
    _prompt_env_field_list(
        _CONFIGURE_INTEGRATION_FIELDS,
        working_env,
        offer_bulk_keep=toml_path.exists(),
        section_label="integration credentials",
    )


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


def _notification_provider_ready(provider_id: str, env: dict[str, str]) -> bool:
    """● row hint: outbound channel ready, corrections secret set, or companion/FCM partially configured."""

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
    if provider_id == "companion":
        return bool(g("PULSE_COMPANION_TOKEN") or g("PULSE_FCM_SERVICE_ACCOUNT_PATH"))
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
        ui.muted_line("Values for this channel (saved in pulse.toml; leave blank to skip).")
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


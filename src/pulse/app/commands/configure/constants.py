"""Module-level data used across configure/* — field defs, env key orders, connector tables."""

from __future__ import annotations

from pulse.app.config import PulseConfig

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


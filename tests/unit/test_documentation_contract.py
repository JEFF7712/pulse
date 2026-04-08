import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPO_ROOT / "README.md"
DOCS_ROOT = REPO_ROOT / "docs"
DOC_PATHS = [
    Path("docs/index.md"),
    Path("docs/self-hosting/quickstart.md"),
    Path("docs/reference/configuration.md"),
    Path("docs/operations/runbook.md"),
    Path("docs/connectors/index.md"),
]

QUICKSTART_REQUIRED_SNIPPETS = [
    "pipx install pulse-agent",
    "uv tool install pulse-agent",
    "pip install pulse-agent",
    "pulse configure",
    "**Connectors**",
    "pulse init",
    "pulse run",
    "pulse status",
    "pulse insights",
]

CONNECTOR_REQUIRED_SNIPPETS = [
    "Google",
    "Spotify",
    "Microsoft",
    "GitHub",
    "GitLab",
    "Plaid",
    "browser history",
    "RSS",
    "pulse configure",
    "Configure → Connectors",
    "db_path",
    "[connectors.browser]",
    "[connectors.feeds]",
    "urls",
]

QUICKSTART_OPTIONAL_AUTH_SNIPPETS = [
    "Notion",
]

QUICKSTART_ONBOARD_SNIPPETS = [
    "pulse onboard",
    "pulse onboard --strict",
    "--profile-text",
    "`8888`",
]

CONFIG_REFERENCE_REQUIRED_SNIPPETS = [
    "PULSE_CORRECTIONS_WEBHOOK_SECRET",
    "/webhooks/corrections",
    "PULSE_NTFY_TOPIC",
    "PULSE_GOTIFY_URL",
    "PULSE_SMTP_HOST",
    "PULSE_DISCORD_WEBHOOK_URL",
    "PULSE_SLACK_WEBHOOK_URL",
    "PULSE_PUSHOVER_USER_KEY",
    "PULSE_NOTIFICATION_WEBHOOK_URL",
    "PULSE_DATABASE_PATH",
    "PULSE_VAULT_PATH",
    "PULSE_GOOGLE_CLIENT_ID",
    "PULSE_SPOTIFY_CLIENT_ID",
    "PULSE_SPOTIFY_CLIENT_SECRET",
    "PULSE_MICROSOFT_CLIENT_ID",
    "PULSE_PLAID_CLIENT_ID",
    "PULSE_ANTHROPIC_API_KEY",
    "pulse.toml",
    "google_tokens.json",
    "spotify_tokens.json",
    "microsoft_tokens.json",
    "plaid_tokens.json",
    "llm.corrections",
    "corrections are stored but vault application is skipped",
    "`correction_applications`",
    "share the corrections pipeline",
    "Same **`load_config()`**",
    "One configured role can cover both summarization and discovery if the other is omitted.",
    "PULSE_COMPANION_TOKEN",
    "PULSE_FCM_SERVICE_ACCOUNT_PATH",
    "[connectors.companion]",
]

RUNBOOK_REQUIRED_SNIPPETS = [
    "/webhooks/corrections",
    "PULSE_CORRECTIONS_WEBHOOK_SECRET",
    "/health",
    "/webhooks/telegram",
    "pulse status",
    "pulse logs",
    "pulse reset",
    "aggregation",
    "discovery_daily",
    "**host** timezone",
    "PULSE_TIMEZONE",
    "correction_applications",
    "pulse_correct",
    "/webhooks/companion",
    "/api/insights",
    "/api/corrections",
    "/api/device-token",
    "PULSE_COMPANION_TOKEN",
]

QUICKSTART_DISCOVERY_REQUIRED_SNIPPETS = [
    "optional discovery when LLM",
]

PULSE_TOML_EXAMPLE_REQUIRED_SNIPPETS = [
    "[llm.corrections]",
    "# If omitted, corrections reuse [llm.discovery].",
]

README_REQUIRED_SNIPPETS = [
    "(/docs/)",
    "[docs/index.md](docs/index.md)",
    "Documentation lives under",
    "deployed site serves the same guides",
    "`PULSE_DATABASE_PATH`",
    "Standalone app, CLI commands, and the MCP server use `PULSE_DATABASE_PATH`.",
    "`PULSE_VAULT_PATH`",
    "`.config/pulse.toml`",
    "day boundaries",
    "pulse-agent",
    "`PULSE_CONFIG_DIR`",
    "`pulse` and `pulse-mcp`",
]

DOCS_APP_README_REQUIRED_SNIPPETS = [
    "Edit the matching page under `docs/` first",
    "When you add a new published markdown page under `docs/`, add a matching wrapper page under `site/docs-app/docs/`.",
    "Each wrapper should be a single include line pointing at the repo file.",
]

NON_CANONICAL_DOC_PARTS = {"plans", "specs", "superpowers"}


def _joined_bash_fenced_blocks(markdown: str) -> str:
    """Concatenate ```bash ... ``` bodies in document order (for CLI ordering checks)."""
    parts: list[str] = []
    cursor = 0
    while True:
        fence = markdown.find("```bash", cursor)
        if fence == -1:
            break
        nl = markdown.find("\n", fence)
        if nl == -1:
            break
        close = markdown.find("```", nl + 1)
        if close == -1:
            break
        parts.append(markdown[nl + 1 : close])
        cursor = close + 3
    return "\n".join(parts)


def iter_canonical_repo_docs() -> list[Path]:
    return sorted(
        path.relative_to(REPO_ROOT)
        for path in DOCS_ROOT.rglob("*.md")
        if not any(
            part in NON_CANONICAL_DOC_PARTS
            for part in path.relative_to(DOCS_ROOT).parts
        )
    )


def docs_app_wrapper_path_for(repo_path: Path) -> Path:
    return Path("site/docs-app/docs") / repo_path.relative_to("docs")


def docs_app_include_path_for(wrapper_path: Path, repo_path: Path) -> str:
    return Path(os.path.relpath(repo_path, start=wrapper_path.parent)).as_posix()


def test_readme_links_to_required_docs_pages() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    missing_docs = [str(path) for path in DOC_PATHS if not (REPO_ROOT / path).exists()]
    assert not missing_docs, f"Missing docs files: {missing_docs}"

    missing_links = [
        str(path) for path in DOC_PATHS if f"({path.as_posix()})" not in readme
    ]
    assert not missing_links, f"README.md is missing links: {missing_links}"


def test_quickstart_documents_cli_happy_path() -> None:
    quickstart = (REPO_ROOT / "docs/self-hosting/quickstart.md").read_text(
        encoding="utf-8"
    )

    missing_snippets = [
        snippet for snippet in QUICKSTART_REQUIRED_SNIPPETS if snippet not in quickstart
    ]

    assert not missing_snippets, (
        f"quickstart.md is missing CLI setup steps: {missing_snippets}"
    )


def test_quickstart_documents_pulse_onboard() -> None:
    quickstart = (REPO_ROOT / "docs/self-hosting/quickstart.md").read_text(
        encoding="utf-8"
    )

    missing = [s for s in QUICKSTART_ONBOARD_SNIPPETS if s not in quickstart]
    assert not missing, f"quickstart.md should document pulse onboard: {missing}"


def test_quickstart_documents_discovery_role_fallback() -> None:
    quickstart = (REPO_ROOT / "docs/self-hosting/quickstart.md").read_text(
        encoding="utf-8"
    )

    missing = [s for s in QUICKSTART_DISCOVERY_REQUIRED_SNIPPETS if s not in quickstart]
    assert not missing, (
        f"quickstart.md should document discovery role fallback: {missing}"
    )


def test_quickstart_marks_auth_commands_as_optional() -> None:
    quickstart = (REPO_ROOT / "docs/self-hosting/quickstart.md").read_text(
        encoding="utf-8"
    )

    missing_snippets = [
        snippet
        for snippet in QUICKSTART_OPTIONAL_AUTH_SNIPPETS
        if snippet not in quickstart
    ]

    assert not missing_snippets, (
        f"quickstart.md is missing optional-auth guidance: {missing_snippets}"
    )


def test_quickstart_common_operator_flow_orders_configure_before_init() -> None:
    quickstart = (REPO_ROOT / "docs/self-hosting/quickstart.md").read_text(
        encoding="utf-8"
    )

    bash_blocks = _joined_bash_fenced_blocks(quickstart)

    configure_index = bash_blocks.index("pulse configure")
    init_index = bash_blocks.index("pulse init")
    run_index = bash_blocks.index("pulse run")

    assert configure_index < init_index < run_index, (
        "quickstart.md bash examples should list configure, then init, then run"
    )


def test_quickstart_common_operator_flow_has_no_pulse_auth_commands() -> None:
    quickstart = (REPO_ROOT / "docs/self-hosting/quickstart.md").read_text(
        encoding="utf-8"
    )

    bash_blocks = _joined_bash_fenced_blocks(quickstart)

    assert "pulse auth" not in bash_blocks, (
        "quickstart.md bash examples should not reference removed pulse auth commands"
    )


def test_connector_index_covers_supported_setup_paths() -> None:
    connector_index = (REPO_ROOT / "docs/connectors/index.md").read_text(
        encoding="utf-8"
    )

    missing_snippets = [
        snippet
        for snippet in CONNECTOR_REQUIRED_SNIPPETS
        if snippet not in connector_index
    ]

    assert not missing_snippets, (
        "connectors/index.md is missing required connector guidance: "
        f"{missing_snippets}"
    )


def test_configuration_reference_covers_runtime_config_surface() -> None:
    configuration_reference = (REPO_ROOT / "docs/reference/configuration.md").read_text(
        encoding="utf-8"
    )

    missing_snippets = [
        snippet
        for snippet in CONFIG_REFERENCE_REQUIRED_SNIPPETS
        if snippet not in configuration_reference
    ]

    assert not missing_snippets, (
        "configuration.md is missing required runtime config guidance: "
        f"{missing_snippets}"
    )


def test_configuration_reference_documents_install_safe_paths() -> None:
    configuration_reference = (REPO_ROOT / "docs/reference/configuration.md").read_text(
        encoding="utf-8"
    )

    assert "~/.config/pulse" in configuration_reference, (
        "configuration.md should document ~/.config/pulse as the default installed config location"
    )
    assert "~/.local/share/pulse" in configuration_reference, (
        "configuration.md should document ~/.local/share/pulse as the default installed data location"
    )


def test_operations_runbook_covers_runtime_health_and_recovery() -> None:
    runbook = (REPO_ROOT / "docs/operations/runbook.md").read_text(encoding="utf-8")

    missing_snippets = [
        snippet for snippet in RUNBOOK_REQUIRED_SNIPPETS if snippet not in runbook
    ]

    assert not missing_snippets, (
        f"runbook.md is missing required operator guidance: {missing_snippets}"
    )

    assert "pulse cleanup" not in runbook, (
        "runbook.md should only document commands that exist in this worktree"
    )

    assert "in the configured timezone" not in runbook, (
        "runbook.md should not claim cron trigger timezones the scheduler does not configure"
    )

    assert "legacy `PULSE_ANTHROPIC_API_KEY`" not in runbook, (
        "runbook.md should not describe removed API-key-only LLM fallback"
    )


def test_pulse_toml_example_covers_corrections_role() -> None:
    pulse_toml_example = (REPO_ROOT / "pulse.toml.example").read_text(encoding="utf-8")

    missing_snippets = [
        snippet
        for snippet in PULSE_TOML_EXAMPLE_REQUIRED_SNIPPETS
        if snippet not in pulse_toml_example
    ]

    assert not missing_snippets, (
        f"pulse.toml.example is missing corrections-role guidance: {missing_snippets}"
    )


def test_readme_reconciles_app_and_mcp_database_env_vars() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    missing_snippets = [
        snippet for snippet in README_REQUIRED_SNIPPETS if snippet not in readme
    ]

    assert not missing_snippets, (
        f"README.md is missing env-var reconciliation guidance: {missing_snippets}"
    )

    assert "The MCP server uses `PULSE_DB_PATH`." not in readme, (
        "README.md should not describe the old MCP-only PULSE_DB_PATH behavior"
    )

    assert "Scheduler timezone for day boundaries and cron jobs" not in readme, (
        "README.md should not claim PULSE_TIMEZONE controls cron triggers in this worktree"
    )


def test_docs_app_pages_are_thin_wrappers_around_repo_docs() -> None:
    for repo_path in iter_canonical_repo_docs():
        wrapper_path = docs_app_wrapper_path_for(repo_path)
        include_path = docs_app_include_path_for(wrapper_path, repo_path)
        wrapper = (REPO_ROOT / wrapper_path).read_text(encoding="utf-8")

        assert f"<!--@include: {include_path} -->" in wrapper, (
            f"{wrapper_path.as_posix()} should include {repo_path.as_posix()} directly"
        )


def test_docs_index_has_standard_home_sections() -> None:
    docs_index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")

    assert "What is Pulse?" in docs_index
    assert "## Quick Start" in docs_index


def test_docs_app_readme_documents_wrapper_maintenance_rule() -> None:
    docs_app_readme = (REPO_ROOT / "site/docs-app/README.md").read_text(
        encoding="utf-8"
    )

    missing_snippets = [
        snippet
        for snippet in DOCS_APP_README_REQUIRED_SNIPPETS
        if snippet not in docs_app_readme
    ]

    assert not missing_snippets, (
        "site/docs-app/README.md is missing docs wrapper maintenance guidance: "
        f"{missing_snippets}"
    )

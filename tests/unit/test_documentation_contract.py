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
    "pip install -e .",
    "pulse configure",
    "pulse auth google",
    "pulse auth spotify",
    "pulse init",
    "pulse run",
    "pulse status",
    "pulse insights",
]

CONNECTOR_REQUIRED_SNIPPETS = [
    "Google",
    "Spotify",
    "browser history",
    "RSS",
    "pulse auth google",
    "pulse auth spotify",
    "db_path",
    "[connectors.browser]",
    'db_path = "/path/to/browser-history.sqlite"',
    "[connectors.feeds]",
    "urls",
]

QUICKSTART_OPTIONAL_AUTH_SNIPPETS = [
    "If you enabled Google-backed connectors, run:",
    "If you enabled Spotify, run:",
    "Skip the auth commands for services you did not enable.",
]

QUICKSTART_ONBOARD_SNIPPETS = [
    "pulse onboard",
    "pulse onboard --strict",
    "pulse onboard -f ./my-profile.txt",
    "--profile-text",
    "localhost:8888",
]

CONFIG_REFERENCE_REQUIRED_SNIPPETS = [
    "PULSE_DATABASE_PATH",
    "PULSE_VAULT_PATH",
    "PULSE_GOOGLE_CLIENT_ID",
    "PULSE_SPOTIFY_CLIENT_ID",
    "PULSE_SPOTIFY_CLIENT_SECRET",
    "PULSE_ANTHROPIC_API_KEY",
    "pulse.toml",
    "google_tokens.json",
    "spotify_tokens.json",
]

RUNBOOK_REQUIRED_SNIPPETS = [
    "/health",
    "/webhooks/telegram",
    "pulse status",
    "pulse logs",
    "pulse reset",
    "aggregation",
    "daily_digest",
    "morning_briefing",
    "discovery_daily",
    "host timezone",
    "process timezone",
]

ENV_EXAMPLE_REQUIRED_SNIPPETS = [
    "PULSE_SPOTIFY_CLIENT_ID=",
    "PULSE_SPOTIFY_CLIENT_SECRET=",
]

README_REQUIRED_SNIPPETS = [
    "(/docs/)",
    "[docs/index.md](docs/index.md)",
    "source-of-truth docs entry for repo readers",
    "rendered version of that same docs set",
    "`PULSE_DATABASE_PATH`",
    "`PULSE_DB_PATH`",
    "Standalone app and CLI commands use `PULSE_DATABASE_PATH`.",
    "The MCP server uses `PULSE_DB_PATH`.",
    "day boundaries",
]

DOCS_APP_README_REQUIRED_SNIPPETS = [
    "The repo `docs/` tree is authoritative for published documentation content.",
    "When you add a new published markdown page under `docs/`, add a matching wrapper page under `site/docs-app/docs/`.",
    "Each wrapper should stay thin: identify the canonical repo doc and include it directly via a VitePress include.",
]

NON_CANONICAL_DOC_PARTS = {"plans", "specs", "superpowers"}


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


def test_quickstart_common_operator_flow_orders_auth_before_init() -> None:
    quickstart = (REPO_ROOT / "docs/self-hosting/quickstart.md").read_text(
        encoding="utf-8"
    )

    common_operator_flow = quickstart.split("## Common operator flow", maxsplit=1)[1]

    auth_google_index = common_operator_flow.index("pulse auth google")
    auth_spotify_index = common_operator_flow.index("pulse auth spotify")
    init_index = common_operator_flow.index("pulse init")

    assert auth_google_index < init_index, (
        "quickstart.md should show Google auth before pulse init in the common operator flow"
    )
    assert auth_spotify_index < init_index, (
        "quickstart.md should show Spotify auth before pulse init in the common operator flow"
    )


def test_quickstart_common_operator_flow_lists_each_auth_step_once() -> None:
    quickstart = (REPO_ROOT / "docs/self-hosting/quickstart.md").read_text(
        encoding="utf-8"
    )

    common_operator_flow = quickstart.split("## Common operator flow", maxsplit=1)[1]
    common_operator_flow_block = common_operator_flow.split("```bash", maxsplit=1)[
        1
    ].split("```", maxsplit=1)[0]

    assert common_operator_flow_block.count("pulse auth google") == 1, (
        "quickstart.md should list Google auth once in the common operator flow"
    )
    assert common_operator_flow_block.count("pulse auth spotify") == 1, (
        "quickstart.md should list Spotify auth once in the common operator flow"
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


def test_env_example_lists_spotify_credentials() -> None:
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    missing_snippets = [
        snippet
        for snippet in ENV_EXAMPLE_REQUIRED_SNIPPETS
        if snippet not in env_example
    ]

    assert not missing_snippets, (
        ".env.example is missing required Spotify credential entries: "
        f"{missing_snippets}"
    )


def test_readme_reconciles_app_and_mcp_database_env_vars() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    missing_snippets = [
        snippet for snippet in README_REQUIRED_SNIPPETS if snippet not in readme
    ]

    assert not missing_snippets, (
        f"README.md is missing env-var reconciliation guidance: {missing_snippets}"
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
        assert f"`{repo_path.as_posix()}`" in wrapper, (
            f"{wrapper_path.as_posix()} should tell readers which repo doc it renders"
        )


def test_docs_index_explains_that_repo_docs_drive_deployed_docs() -> None:
    docs_index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")

    assert (
        "This file is the source of truth for the deployed docs page at `/docs/`."
        in docs_index
    )


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

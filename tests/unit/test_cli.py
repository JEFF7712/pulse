import pytest

from datetime import UTC, date, datetime
from pathlib import Path

from pulse.app.paths import PulsePaths
from pulse.app import cli
from pulse.app.config import LLMConfig, LLMRoleConfig, Settings
from pulse.app.commands import configure as configure_cmd
from pulse.app.commands import init_cmd, ops


def test_default_env_values_use_resolved_data_dir(tmp_path):
    paths = PulsePaths(
        config_dir=(tmp_path / "config").resolve(),
        data_dir=(tmp_path / "data").resolve(),
        toml_path=(tmp_path / "config" / "pulse.toml").resolve(),
    )

    values = configure_cmd.default_env_values(paths)

    assert values["PULSE_DATABASE_PATH"] == str(
        (tmp_path / "data" / "pulse.db").resolve()
    )
    assert values["PULSE_VAULT_PATH"] == str(
        (tmp_path / "data" / "Pulse-Vault").resolve()
    )


def test_build_parser_accepts_config_dir_for_run() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--config-dir", "/tmp/pulse-config"])
    assert args.config_dir == Path("/tmp/pulse-config")


def test_build_parser_accepts_config_dir_for_configure() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["configure", "--config-dir", "/tmp/pulse-config"])
    assert args.config_dir == Path("/tmp/pulse-config")


def test_status_shows_actionable_message_when_config_missing(tmp_path, capsys):
    with pytest.raises(SystemExit):
        ops.status(config_dir=tmp_path / "missing")

    out = capsys.readouterr().out
    assert "pulse configure" in out
    assert "PULSE_CONFIG_DIR" in out


def test_discover_uses_config_timezone_when_date_omitted(monkeypatch, tmp_path) -> None:
    import pulse.jobs.runners as runners

    observed: dict[str, object] = {}

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime(2026, 3, 28, 1, 30, tzinfo=UTC)
            return instant if tz is None else instant.astimezone(tz)

    async def fake_run_aggregation_job(*, day, database_path: str, timezone: str):
        observed["aggregation_day"] = day
        observed["aggregation_timezone"] = timezone

        class Result:
            status = "ok"
            detail = "done"

        return Result()

    config = Settings(
        database_path=str(tmp_path / "pulse.db"),
        vault_path=str(tmp_path / "vault"),
        timezone="America/Los_Angeles",
        llm=LLMConfig(
            discovery=LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-6"),
        ),
    )
    args = type("Args", (), {"date": None, "cadence": "daily"})()

    monkeypatch.setattr(ops, "datetime", FixedDateTime)
    monkeypatch.setattr(ops, "load_config", lambda: config)
    monkeypatch.setattr(runners, "run_aggregation_job", fake_run_aggregation_job)
    monkeypatch.setattr(ops.ui, "rule", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ops.ui, "say", lambda *_args, **_kwargs: None)

    ops.discover(args)

    assert observed["aggregation_day"] == date(2026, 3, 27)
    assert observed["aggregation_timezone"] == "America/Los_Angeles"


def test_init_profile_resolves_current_day_from_config_timezone(monkeypatch) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime(2026, 3, 28, 1, 30, tzinfo=UTC)
            return instant if tz is None else instant.astimezone(tz)

    monkeypatch.setattr(init_cmd, "datetime", FixedDateTime)

    config = Settings(timezone="America/Los_Angeles")

    assert init_cmd._resolve_current_day(config) == date(2026, 3, 27)

import json

import pytest

from pulse.app.commands import auth as auth_cmd
from pulse.app.commands.auth_registry import (
    all_status,
    resolve,
    source_names,
    status_for,
)
from pulse.app.config import ConnectorConfig, PulseConfig


def _config(tmp_path, **kw):
    kw.setdefault("connectors", {"spotify": ConnectorConfig(enabled=True)})
    return PulseConfig(database_path=str(tmp_path / "pulse.db"), **kw)


def _write_token(tmp_path, name, blob=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    if blob is None:
        blob = {"access_token": "a", "refresh_token": "r"}
    path.write_text(json.dumps(blob))
    return path


class _Args:
    def __init__(self, source=None):
        self.source = source
        self.config_dir = None


# ----------------------------------------------------------------------
# registry
# ----------------------------------------------------------------------


def test_google_aliases_resolve_to_one_token_set():
    """Gmail, Calendar and YouTube share google_tokens.json, so asking to authorize
    any of them must mean the same flow rather than a missing source."""
    for alias in ("gmail", "calendar", "youtube", "google"):
        assert resolve(alias).name == "google"
    assert resolve("GitHub").name == "github"
    assert resolve("nope") is None
    assert set(source_names()) == {"google", "github", "spotify", "plaid", "oura"}


def test_status_reports_missing_credentials_without_touching_the_network(tmp_path):
    st = status_for(resolve("spotify"), _config(tmp_path))
    assert st.authorized is False
    assert st.missing_config == ["spotify_client_id", "spotify_client_secret"]
    assert st.state == "needs credentials"
    assert st.ready is False


def test_status_detects_a_stored_token(tmp_path):
    _write_token(tmp_path, "spotify_tokens.json")
    st = status_for(
        resolve("spotify"),
        _config(tmp_path, spotify_client_id="c", spotify_client_secret="s"),
    )
    assert st.authorized is True
    assert st.state == "authorized"


def test_an_empty_or_corrupt_token_file_is_not_authorized(tmp_path):
    _write_token(tmp_path, "spotify_tokens.json", blob={})
    cfg = _config(tmp_path, spotify_client_id="c", spotify_client_secret="s")
    assert status_for(resolve("spotify"), cfg).authorized is False

    (tmp_path / "spotify_tokens.json").write_text("not json{")
    assert status_for(resolve("spotify"), cfg).authorized is False


def test_oura_personal_access_token_counts_as_credentials(tmp_path):
    cfg = _config(tmp_path, oura_personal_access_token="pat")
    assert status_for(resolve("oura"), cfg).missing_config == []


def test_status_lists_only_enabled_connectors_as_served(tmp_path):
    cfg = _config(
        tmp_path,
        connectors={
            "gmail": ConnectorConfig(enabled=True),
            "calendar": ConnectorConfig(enabled=False),
        },
    )
    st = status_for(resolve("google"), cfg)
    assert st.enabled_connectors == ["gmail"]


def test_all_status_covers_every_source(tmp_path):
    assert len(all_status(_config(tmp_path))) == len(source_names())


# ----------------------------------------------------------------------
# command
# ----------------------------------------------------------------------


def test_no_argument_prints_status_and_runs_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(auth_cmd, "load_config", lambda **kw: _config(tmp_path))
    for name, fn in auth_cmd._AUTH_RUNNERS.items():
        monkeypatch.setitem(
            auth_cmd._AUTH_RUNNERS,
            name,
            lambda: pytest.fail("no flow should run for a bare `pulse auth`"),
        )

    auth_cmd.auth(_Args())

    out = capsys.readouterr().out
    assert "spotify" in out and "google" in out


def test_unknown_source_exits_with_the_valid_choices(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(auth_cmd, "load_config", lambda **kw: _config(tmp_path))
    with pytest.raises(SystemExit):
        auth_cmd.auth(_Args("dropbox"))
    assert "Unknown source" in capsys.readouterr().out


def test_missing_credentials_stops_before_opening_a_browser(
    tmp_path, monkeypatch, capsys
):
    """Failing after the tab opens is confusing, and what to set is exactly what the
    user needs before visiting the provider's dashboard."""
    monkeypatch.setattr(auth_cmd, "load_config", lambda **kw: _config(tmp_path))
    monkeypatch.setitem(
        auth_cmd._AUTH_RUNNERS,
        "spotify",
        lambda: pytest.fail("browser flow must not start"),
    )

    with pytest.raises(SystemExit):
        auth_cmd.auth(_Args("spotify"))

    out = capsys.readouterr().out
    assert "spotify_client_id" in out
    assert "127.0.0.1:8888/callback" in out


def test_plaid_requires_its_connector_enabled(tmp_path, monkeypatch, capsys):
    cfg = _config(
        tmp_path,
        plaid_client_id="c",
        plaid_secret="s",
        connectors={"plaid": ConnectorConfig(enabled=False)},
    )
    monkeypatch.setattr(auth_cmd, "load_config", lambda **kw: cfg)
    monkeypatch.setitem(
        auth_cmd._AUTH_RUNNERS, "plaid", lambda: pytest.fail("must not start")
    )

    with pytest.raises(SystemExit):
        auth_cmd.auth(_Args("plaid"))
    assert "connectors.plaid" in capsys.readouterr().out


def test_a_ready_source_runs_its_flow(tmp_path, monkeypatch):
    cfg = _config(tmp_path, spotify_client_id="c", spotify_client_secret="s")
    monkeypatch.setattr(auth_cmd, "load_config", lambda **kw: cfg)
    ran = []
    monkeypatch.setitem(auth_cmd._AUTH_RUNNERS, "spotify", lambda: ran.append(True))

    auth_cmd.auth(_Args("spotify"))
    assert ran == [True]


def test_an_alias_runs_the_underlying_flow(tmp_path, monkeypatch):
    cfg = _config(
        tmp_path,
        google_client_id="c",
        google_client_secret="s",
        connectors={"gmail": ConnectorConfig(enabled=True)},
    )
    monkeypatch.setattr(auth_cmd, "load_config", lambda **kw: cfg)
    ran = []
    monkeypatch.setitem(auth_cmd._AUTH_RUNNERS, "google", lambda: ran.append("google"))

    auth_cmd.auth(_Args("youtube"))
    assert ran == ["google"]


def test_reauthorizing_warns_but_proceeds(tmp_path, monkeypatch, capsys):
    _write_token(tmp_path, "spotify_tokens.json")
    cfg = _config(tmp_path, spotify_client_id="c", spotify_client_secret="s")
    monkeypatch.setattr(auth_cmd, "load_config", lambda **kw: cfg)
    ran = []
    monkeypatch.setitem(auth_cmd._AUTH_RUNNERS, "spotify", lambda: ran.append(True))

    auth_cmd.auth(_Args("spotify"))

    assert ran == [True]
    assert "already authorized" in capsys.readouterr().out


def test_cli_registers_the_auth_subcommand():
    from pulse.app.cli import build_parser

    args = build_parser().parse_args(["auth", "spotify"])
    assert args.command == "auth"
    assert args.source == "spotify"

    bare = build_parser().parse_args(["auth"])
    assert bare.source is None

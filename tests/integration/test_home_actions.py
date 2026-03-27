from fastapi.testclient import TestClient

import pulse.app.home_actions as home_actions
import pulse.llm.anthropic as anthropic_module
from pulse.app.config import Settings
from pulse.app.dependencies import get_settings
from pulse.app.main import create_app


def test_pull_action_redirects_back_to_home_with_result_token(tmp_path) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(tmp_path / "pulse.db"),
        vault_path=str(tmp_path / "vault"),
    )
    client = TestClient(app)

    response = client.post("/actions/pull", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/?notice=pull-skipped"


def test_digest_action_redirects_back_to_home_with_result_token(tmp_path) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(tmp_path / "pulse.db"),
        vault_path=str(tmp_path / "vault"),
    )
    client = TestClient(app)

    response = client.post("/actions/digest", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/?notice=digest-complete"


def test_digest_action_logs_failures_and_redirects_with_error_token(
    tmp_path, monkeypatch, caplog
) -> None:
    async def fake_run_aggregation_job(*, day, database_path: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(home_actions, "run_aggregation_job", fake_run_aggregation_job)

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(tmp_path / "pulse.db"),
        vault_path=str(tmp_path / "vault"),
    )
    client = TestClient(app)

    with caplog.at_level("ERROR"):
        response = client.post("/actions/digest", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/?error=digest-failed"
    assert any(
        record.levelname == "ERROR" and record.message == "Digest action failed"
        for record in caplog.records
    )


def test_discover_action_redirects_back_to_home_with_result_token(tmp_path) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(tmp_path / "pulse.db"),
        vault_path=str(tmp_path / "vault"),
    )
    client = TestClient(app)

    response = client.post("/actions/discover", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/?error=discovery-not-configured"


def test_test_telegram_action_redirects_back_to_home_with_result_token(
    tmp_path,
) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(tmp_path / "pulse.db"),
        vault_path=str(tmp_path / "vault"),
    )
    client = TestClient(app)

    response = client.post("/actions/test-telegram", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/?error=telegram-not-configured"


def test_discover_action_creates_database_parent_directory_on_fresh_setup(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "missing" / "state" / "pulse.db"
    observed: dict[str, object] = {}

    class FakeAnthropicProvider:
        def __init__(self, api_key: str, model: str | None = None) -> None:
            observed["api_key"] = api_key
            observed["model"] = model

    async def fake_run_aggregation_job(*, day, database_path: str) -> None:
        observed["day"] = day
        observed["database_path"] = database_path
        assert database_path == str(database_path_obj)
        assert database_path_obj.parent.exists()

    async def fake_run_discovery_job(**kwargs) -> None:
        observed["discovery_kwargs"] = kwargs

    database_path_obj = database_path
    monkeypatch.setattr(home_actions, "run_aggregation_job", fake_run_aggregation_job)
    monkeypatch.setattr(home_actions, "run_discovery_job", fake_run_discovery_job)
    monkeypatch.setattr(anthropic_module, "AnthropicProvider", FakeAnthropicProvider)

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(database_path_obj),
        vault_path=str(tmp_path / "vault"),
        anthropic_api_key="test-key",
    )
    client = TestClient(app)

    response = client.post("/actions/discover", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/?notice=discovery-complete"
    assert observed["database_path"] == str(database_path_obj)
    assert observed["api_key"] == "test-key"


def test_homepage_shows_action_notice_after_redirect() -> None:
    client = TestClient(create_app())

    response = client.post("/actions/pull", follow_redirects=True)

    assert response.status_code == 200
    assert "pull skipped" in response.text.lower()

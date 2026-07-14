from fastapi.testclient import TestClient

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


def test_homepage_shows_action_notice_after_redirect() -> None:
    client = TestClient(create_app())

    response = client.post("/actions/pull", follow_redirects=True)

    assert response.status_code == 200
    assert "pull skipped" in response.text.lower()

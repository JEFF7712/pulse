from fastapi.testclient import TestClient

from pulse.app.main import create_app


def test_root_route_returns_html_homepage() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Pulse" in response.text


def test_root_route_includes_operator_content() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "server online" in response.text.lower()
    assert "/health" in response.text
    assert "self-hosted" in response.text.lower()


def test_root_route_lists_telegram_webhook_as_post_only() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "POST /webhooks/telegram" in response.text
    assert 'href="/webhooks/telegram"' not in response.text

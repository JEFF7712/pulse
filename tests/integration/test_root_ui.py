from fastapi.testclient import TestClient

from pulse.app.main import create_app


def test_root_route_returns_html_homepage() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Pulse" in response.text


def test_root_route_stays_functional_and_minimal() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "Pulse" in response.text
    assert "server online" in response.text.lower()
    assert "self-hosted node" in response.text.lower()
    assert "/health" in response.text
    assert "POST /webhooks/telegram" in response.text
    assert "operator overview" not in response.text.lower()


def test_root_route_lists_telegram_webhook_as_post_only() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "POST /webhooks/telegram" in response.text
    assert 'href="/webhooks/telegram"' not in response.text


def test_root_route_keeps_animated_pulse_markup() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "pulse-ring" in response.text
    assert "pulse-dot" in response.text
    assert "pulseExpand" in response.text

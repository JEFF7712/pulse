from fastapi import FastAPI
from fastapi.testclient import TestClient

from pulse.app.config import PulseConfig


def test_auth_dependency_passes_with_valid_token():
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(companion_token="test-secret-123")
    dep = build_require_companion_token(lambda: settings)

    app = FastAPI()

    @app.get("/protected")
    async def protected(_=dep):
        return {"ok": True}

    client = TestClient(app)

    response = client.get(
        "/protected", headers={"X-Pulse-Token": "test-secret-123"}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_dependency_rejects_missing_token():
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(companion_token="test-secret-123")

    app = FastAPI()
    dep = build_require_companion_token(lambda: settings)

    @app.get("/protected")
    async def protected(_=dep):
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/protected")
    assert response.status_code == 401


def test_auth_dependency_rejects_wrong_token():
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(companion_token="test-secret-123")

    app = FastAPI()
    dep = build_require_companion_token(lambda: settings)

    @app.get("/protected")
    async def protected(_=dep):
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/protected", headers={"X-Pulse-Token": "wrong-token"}
    )
    assert response.status_code == 401


def test_auth_dependency_rejects_when_no_token_configured():
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(companion_token=None)

    app = FastAPI()
    dep = build_require_companion_token(lambda: settings)

    @app.get("/protected")
    async def protected(_=dep):
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/protected", headers={"X-Pulse-Token": "anything"}
    )
    assert response.status_code == 401

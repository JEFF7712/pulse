import asyncio
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from pulse.app.config import Settings
from pulse.app.dependencies import get_settings
from pulse.app.main import create_app


def test_corrections_webhook_returns_404_when_secret_unset(tmp_path) -> None:
    db_path = tmp_path / "c.db"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(db_path),
        corrections_webhook_secret=None,
    )
    client = TestClient(app)
    response = client.post(
        "/webhooks/corrections",
        json={"context_id": "x", "message": "y"},
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 404


def test_corrections_webhook_returns_404_when_secret_blank(tmp_path) -> None:
    db_path = tmp_path / "c.db"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(db_path),
        corrections_webhook_secret="   ",
    )
    client = TestClient(app)
    response = client.post(
        "/webhooks/corrections",
        json={"context_id": "x", "message": "y"},
        headers={"Authorization": "Bearer x"},
    )
    assert response.status_code == 404


def test_corrections_webhook_bearer_accepts_and_stores(tmp_path) -> None:
    db_path = tmp_path / "c.db"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(db_path),
        corrections_webhook_secret="my-shared-secret",
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/corrections",
        json={"context_id": "digest-ctx", "message": "Please fix the title."},
        headers={"Authorization": "Bearer my-shared-secret"},
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    async def fetch() -> list[tuple[str, str]]:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            cursor = await db.execute(
                "SELECT context_id, message_text FROM corrections"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [(row[0], row[1]) for row in rows]

    assert asyncio.run(fetch()) == [
        ("digest-ctx", "Please fix the title."),
    ]


def test_corrections_webhook_bearer_invalid_returns_401(tmp_path) -> None:
    db_path = tmp_path / "c.db"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(db_path),
        corrections_webhook_secret="correct",
    )
    client = TestClient(app)
    response = client.post(
        "/webhooks/corrections",
        json={"context_id": "x", "message": "y"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_corrections_webhook_hmac_signature_accepts(tmp_path) -> None:
    db_path = tmp_path / "c.db"
    secret = "hmac-secret"
    body_obj = {"context_id": "2026-04-01", "message": "From HMAC client."}
    body_bytes = json.dumps(body_obj).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(db_path),
        corrections_webhook_secret=secret,
    )
    client = TestClient(app)
    response = client.post(
        "/webhooks/corrections",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Pulse-Signature": f"sha256={sig}",
        },
    )
    assert response.status_code == 202

    async def fetch() -> list[tuple[str, str]]:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            cursor = await db.execute(
                "SELECT context_id, message_text FROM corrections"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [(row[0], row[1]) for row in rows]

    assert asyncio.run(fetch()) == [("2026-04-01", "From HMAC client.")]

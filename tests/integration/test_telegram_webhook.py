from fastapi.testclient import TestClient

from pulse.app.config import Settings
from pulse.app.dependencies import get_settings
from pulse.app.main import create_app


def test_telegram_webhook_accepts_plain_message(tmp_path) -> None:
    db_path = tmp_path / "telegram-webhook.db"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(db_path)
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {
                "message_id": 200,
                "text": "Hello Pulse",
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


def test_telegram_webhook_rejects_missing_message() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={"update_id": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing message payload."


def test_telegram_webhook_rejects_blank_text() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {"message_id": 200, "text": "   "},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing message text."


def _seed_proposal(db_path, vault_path):
    """Queue one pending fact proposal and return its id."""
    import asyncio

    import aiosqlite

    from pulse.store.proposals import FactProposalRepository
    from pulse.store.schema import bootstrap_schema

    async def _go():
        async with aiosqlite.connect(db_path) as db:
            await bootstrap_schema(db)
            p = await FactProposalRepository(db).propose(
                field="Location",
                proposed_value="Columbus, OH",
                evidence="3 months of Columbus-timezone activity",
                current_value="Madison, WI",
            )
            return p.id

    (vault_path / "04-Config").mkdir(parents=True, exist_ok=True)
    return asyncio.run(_go())


def _client(tmp_path):
    db_path = tmp_path / "wh.db"
    vault = tmp_path / "vault"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(db_path), vault_path=str(vault), timezone="UTC"
    )
    return TestClient(app), db_path, vault


def test_replying_yes_applies_the_pending_fact(tmp_path) -> None:
    """The handler used to accept and discard every message, so a confirmation had
    nowhere to land and the whole loop was inert."""
    client, db_path, vault = _client(tmp_path)
    pid = _seed_proposal(db_path, vault)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {
                "message_id": 201,
                "text": "yes",
                "reply_to_message": {
                    "message_id": 200,
                    "text": f"Confirm a profile fact\n\nLocation\n\nContext: {pid}",
                },
            },
        },
    )

    assert response.status_code == 202
    assert "Columbus, OH" in response.json()["result"]
    facts = (vault / "04-Config" / "facts.md").read_text()
    assert "Columbus, OH" in facts


def test_an_unrelated_message_is_still_just_accepted(tmp_path) -> None:
    client, db_path, vault = _client(tmp_path)
    _seed_proposal(db_path, vault)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {"message_id": 202, "text": "what did I do yesterday?"},
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert not (vault / "04-Config" / "facts.md").exists()

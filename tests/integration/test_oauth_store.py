from datetime import datetime, UTC

import pytest

from pulse.store.db import connect_db
from pulse.store.schema import bootstrap_schema
from pulse.store.oauth import OAuthTokenRepository


@pytest.mark.asyncio
async def test_oauth_token_round_trip(tmp_path):
    async with connect_db(tmp_path / "pulse.db") as db:
        await bootstrap_schema(db)
        repo = OAuthTokenRepository(db)

        await repo.save(
            provider="google",
            access_token="access-123",
            refresh_token="refresh-456",
            expires_at=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
            scopes="calendar.readonly gmail.readonly",
        )

        token = await repo.load("google")
        assert token is not None
        assert token["access_token"] == "access-123"
        assert token["refresh_token"] == "refresh-456"
        assert token["scopes"] == "calendar.readonly gmail.readonly"


@pytest.mark.asyncio
async def test_oauth_token_returns_none_when_missing(tmp_path):
    async with connect_db(tmp_path / "pulse.db") as db:
        await bootstrap_schema(db)
        repo = OAuthTokenRepository(db)
        assert await repo.load("google") is None


@pytest.mark.asyncio
async def test_oauth_token_upsert_updates_existing(tmp_path):
    async with connect_db(tmp_path / "pulse.db") as db:
        await bootstrap_schema(db)
        repo = OAuthTokenRepository(db)

        await repo.save(
            provider="google",
            access_token="old",
            refresh_token="refresh-456",
            expires_at=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
            scopes="calendar.readonly",
        )
        await repo.save(
            provider="google",
            access_token="new",
            refresh_token="refresh-456",
            expires_at=datetime(2026, 3, 23, 13, 0, tzinfo=UTC),
            scopes="calendar.readonly",
        )

        token = await repo.load("google")
        assert token["access_token"] == "new"

"""Shared Plaid API client construction."""
from __future__ import annotations

from typing import TYPE_CHECKING

from plaid.api.plaid_api import PlaidApi
from plaid.api_client import ApiClient
from plaid.configuration import Configuration, Environment

if TYPE_CHECKING:
    from pulse.app.config import PulseConfig


def plaid_host_for_env(env: str | None) -> str:
    e = (env or "sandbox").lower().strip()
    if e == "production":
        return Environment.Production
    if e == "development":
        return "https://development.plaid.com"
    return Environment.Sandbox


def make_plaid_client(config: PulseConfig) -> tuple[PlaidApi, ApiClient]:
    if not config.plaid_client_id or not config.plaid_secret:
        raise RuntimeError("Plaid client id and secret must be configured.")
    host = plaid_host_for_env(config.plaid_env)
    configuration = Configuration(
        host=host,
        api_key={
            "clientId": config.plaid_client_id,
            "secret": config.plaid_secret,
        },
    )
    api_client = ApiClient(configuration)
    return PlaidApi(api_client), api_client

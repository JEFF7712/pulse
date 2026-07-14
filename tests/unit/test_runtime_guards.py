from __future__ import annotations

import pytest

from pulse.connectors.github import GitHubConnector
from pulse.connectors.oura import OuraConnector


def test_github_headers_require_auth_manager() -> None:
    connector = GitHubConnector(auth_manager=None)

    with pytest.raises(RuntimeError, match="Initialize GitHub auth manager"):
        connector._headers()


def test_oura_bearer_requires_auth_manager_without_personal_token() -> None:
    connector = OuraConnector(auth_manager=None, personal_access_token=None)

    with pytest.raises(RuntimeError, match="Initialize Oura auth manager"):
        connector._bearer()

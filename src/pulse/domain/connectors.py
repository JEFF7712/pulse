from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from pulse.domain.events import Event


class ConnectorAuthError(RuntimeError):
    """Raised when a connector cannot authenticate (expired token, revoked key, etc.)."""


class Connector(ABC):
    @abstractmethod
    async def pull(self, since: datetime | None = None) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def get_source_name(self) -> str:
        raise NotImplementedError

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=15)

    async def validate_config(self) -> bool:
        return True


class PushConnector(ABC):
    @abstractmethod
    def get_source_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_webhook_path(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def handle_webhook(self, payload: dict) -> list[Event]:
        raise NotImplementedError

    async def validate_config(self) -> bool:
        return True

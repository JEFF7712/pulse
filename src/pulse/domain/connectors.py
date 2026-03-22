from abc import ABC, abstractmethod
from datetime import datetime

from pulse.domain.events import Event


class Connector(ABC):
    @abstractmethod
    async def pull(self, since: datetime | None = None) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def get_source_name(self) -> str:
        raise NotImplementedError
